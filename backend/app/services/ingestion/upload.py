"""Upload hardening and ingestion dispatch.

- Bounded reads: the request body is read in 1 MiB steps and rejected with
  413 as soon as it exceeds ``MAX_UPLOAD_MB`` (never fully buffered first).
- Content sniffing: the declared type must match the bytes (PDF magic, DOCX
  zip container, UTF-8 for text formats) — the client's Content-Type is not
  trusted.
- Filenames are reduced to a safe basename before touching the filesystem.
- Dispatch: Celery in normal operation; inline when ``INGEST_INLINE=true``
  (local dev without a worker) or if the broker is unreachable.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import VeritasError
from app.models.domain import Document, DocumentType, IngestionJob
from app.services.monitoring.logger import get_logger

log = get_logger("veritas.upload")

CHUNK = 1024 * 1024
_UNSAFE = re.compile(r"[^\w.\- ()]+")


class PayloadTooLargeError(VeritasError):
    def __init__(self, limit_mb: int) -> None:
        super().__init__(
            f"File exceeds the {limit_mb} MB upload limit", code="file_too_large", status_code=413
        )


class UnsupportedFileError(VeritasError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="unsupported_file", status_code=415)


class _Readable(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


def sanitize_filename(name: str | None) -> str:
    """Basename only, no control/path characters, bounded length."""
    raw = (name or "").replace("\\", "/").split("/")[-1]
    raw = unicodedata.normalize("NFKC", raw)
    cleaned = _UNSAFE.sub("_", raw).strip(" ._") or "upload.txt"
    stem, dot, ext = cleaned.rpartition(".")
    if dot and len(ext) <= 10:
        return f"{stem[:180]}.{ext}"
    return cleaned[:190]


async def read_limited(file: _Readable, max_mb: int | None = None) -> bytes:
    limit_mb = max_mb or get_settings().max_upload_mb
    limit = limit_mb * 1024 * 1024
    buf = bytearray()
    while chunk := await file.read(CHUNK):
        buf.extend(chunk)
        if len(buf) > limit:
            raise PayloadTooLargeError(limit_mb)
    if not buf:
        raise UnsupportedFileError("File is empty")
    return bytes(buf)


def validate_content(doc_type: DocumentType, data: bytes) -> None:
    if doc_type == DocumentType.PDF:
        if not data.lstrip()[:5] == b"%PDF-":
            raise UnsupportedFileError("File is named/declared as PDF but is not a PDF")
        return
    if doc_type == DocumentType.DOCX:
        if not data.startswith(b"PK\x03\x04"):
            raise UnsupportedFileError("File is named/declared as DOCX but is not a DOCX")
        return
    if b"\x00" in data[:8192]:
        raise UnsupportedFileError("Binary files are not supported; upload PDF, DOCX, MD or text")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnsupportedFileError("Text files must be UTF-8 encoded") from exc


async def dispatch_ingestion(
    db: AsyncSession, doc: Document, job: IngestionJob
) -> Literal["queued", "inline"]:
    """Queue ingestion on Celery, or run it in-process when configured/needed."""
    from app.services.ingestion.pipeline import IngestionService

    if not get_settings().ingest_inline:
        # The worker reads these rows from its own connection: commit first.
        await db.commit()
        try:
            from app.tasks.embedding_tasks import process_document

            result = process_document.delay(str(doc.id), str(job.id))
            job.celery_task_id = result.id
            return "queued"
        except Exception as exc:  # noqa: BLE001 - broker down: degrade, don't lose the upload
            log.error("ingestion.enqueue_failed_running_inline", error=str(exc))

    try:
        await IngestionService().process_document(db, doc.id, job_id=job.id)
    except Exception as exc:  # noqa: BLE001 - status/job/notification already record it
        log.warning("ingestion.failed", document_id=str(doc.id), error=str(exc))
    return "inline"
