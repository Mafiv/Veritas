"""Document ingestion pipeline: parse → chunk → embed → store."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import aiofiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.domain import Document, DocumentChunk, DocumentStatus
from app.services.ingestion.chunker import chunk_document
from app.services.ingestion.embedder import Embedder
from app.services.ingestion.parser import parse_document
from app.services.llm.client import LLMClient


class IngestionService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.embedder = Embedder()
        self.llm = LLMClient()
        Path(self.settings.local_storage_path).mkdir(parents=True, exist_ok=True)

    async def store_file(self, workspace_id: uuid.UUID, filename: str, data: bytes) -> str:
        folder = Path(self.settings.local_storage_path) / str(workspace_id)
        folder.mkdir(parents=True, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex}_{filename}"
        path = folder / safe_name
        async with aiofiles.open(path, "wb") as f:
            await f.write(data)
        return str(path)

    async def process_document(self, db: AsyncSession, document_id: uuid.UUID) -> Document:
        result = await db.execute(select(Document).where(Document.id == document_id))
        doc = result.scalar_one()
        doc.status = DocumentStatus.PROCESSING
        await db.flush()

        try:
            path = Path(doc.storage_path)
            data = path.read_bytes()
            doc.content_hash = hashlib.sha256(data).hexdigest()

            parsed = parse_document(doc.original_filename, doc.content_type, data)
            chunks = chunk_document(parsed)
            embeddings = await self.embedder.embed_texts([c.content for c in chunks])

            # Clear old chunks on reprocess
            existing = await db.execute(
                select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
            )
            for old in existing.scalars().all():
                await db.delete(old)
            await db.flush()

            for chunk, emb in zip(chunks, embeddings):
                db.add(
                    DocumentChunk(
                        document_id=doc.id,
                        workspace_id=doc.workspace_id,
                        chunk_index=chunk.chunk_index,
                        content=chunk.content,
                        token_count=chunk.token_count,
                        page_number=chunk.page_number,
                        heading=chunk.heading,
                        embedding=emb,
                        meta=chunk.meta,
                    )
                )

            doc.page_count = parsed.page_count
            doc.chunk_count = len(chunks)
            doc.meta = {**(doc.meta or {}), **parsed.meta}

            # Summary + suggested questions
            summary = await self.llm.complete(
                system="Summarize the document in 2-3 concise sentences for a research assistant preview.",
                user=parsed.text[:6000],
                max_tokens=200,
            )
            questions_raw = await self.llm.complete(
                system=(
                    "Suggest 5 insightful questions a user could ask about this document. "
                    "One question per line."
                ),
                user=parsed.text[:4000],
                max_tokens=250,
            )
            questions = [
                q.strip(" -•\t0123456789.")
                for q in questions_raw.splitlines()
                if q.strip()
            ][:5]

            doc.summary = summary
            doc.suggested_questions = questions
            doc.status = DocumentStatus.READY
            doc.error_message = None
            await db.flush()
            return doc
        except Exception as exc:  # noqa: BLE001
            doc.status = DocumentStatus.FAILED
            doc.error_message = str(exc)[:1000]
            await db.flush()
            raise
