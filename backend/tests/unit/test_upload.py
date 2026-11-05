"""Upload hardening: filename sanitising, size limit, content sniffing."""

from __future__ import annotations

import pytest

from app.models.domain import DocumentType
from app.services.ingestion.upload import (
    PayloadTooLargeError,
    UnsupportedFileError,
    read_limited,
    sanitize_filename,
    validate_content,
)


class _File:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.reads = 0

    async def read(self, size: int = -1) -> bytes:
        self.reads += 1
        chunk, self.data = self.data[:size], self.data[size:]
        return chunk


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\me\\report.pdf", "report.pdf"),
        ("my notes (v2).md", "my notes (v2).md"),
        ("evil\x00name;rm -rf.txt", "evil_name_rm -rf.txt"),
        ("", "upload.txt"),
        (None, "upload.txt"),
    ],
)
def test_sanitize_filename(raw: str | None, expected: str) -> None:
    assert sanitize_filename(raw) == expected


def test_sanitize_filename_bounds_length() -> None:
    assert len(sanitize_filename("a" * 1000 + ".pdf")) <= 190


async def test_read_limited_rejects_oversized_without_buffering_everything() -> None:
    f = _File(b"x" * (3 * 1024 * 1024))
    with pytest.raises(PayloadTooLargeError) as err:
        await read_limited(f, max_mb=1)
    assert err.value.status_code == 413
    assert f.reads <= 3  # stopped as soon as the limit was crossed


async def test_read_limited_rejects_empty() -> None:
    with pytest.raises(UnsupportedFileError):
        await read_limited(_File(b""), max_mb=1)


def test_validate_content_checks_magic_bytes() -> None:
    validate_content(DocumentType.PDF, b"%PDF-1.7 ...")
    validate_content(DocumentType.DOCX, b"PK\x03\x04...")
    validate_content(DocumentType.MARKDOWN, "# Héllo".encode())
    with pytest.raises(UnsupportedFileError):
        validate_content(DocumentType.PDF, b"MZ\x90\x00 not a pdf")
    with pytest.raises(UnsupportedFileError):
        validate_content(DocumentType.DOCX, b"%PDF-1.7")
    with pytest.raises(UnsupportedFileError):
        validate_content(DocumentType.TEXT, b"\x00\x01binary")
    with pytest.raises(UnsupportedFileError):
        validate_content(DocumentType.TEXT, "café".encode("latin-1"))
