"""Document ingestion pipeline: parse → chunk → embed → summarize → entities."""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

import aiofiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.domain import (
    Document,
    DocumentChunk,
    DocumentEntity,
    DocumentStatus,
    DocumentSummary,
    DocumentVersion,
    EmbeddingModel,
    Entity,
    EntityType,
    IngestionJob,
    IngestionJobStage,
    SuggestedQuestion,
)
from app.services.ingestion.chunker import chunk_document, contextualize
from app.services.ingestion.embedder import Embedder
from app.services.ingestion import jobs as job_service
from app.services.ingestion.parser import parse_document
from app.services.llm.client import LLMClient
from app.services.notifications.service import notify_user


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

    async def _active_embedding_model(self, db: AsyncSession) -> EmbeddingModel:
        """Registry row for the model that actually produced these vectors."""
        model_id = self.settings.embedding_model
        row = (
            await db.execute(select(EmbeddingModel).where(EmbeddingModel.model_id == model_id))
        ).scalar_one_or_none()
        if row is None:
            row = EmbeddingModel(
                name=model_id.split("/")[-1][:120],
                provider=self.settings.embedding_provider,
                model_id=model_id,
                dimensions=self.settings.embedding_dimensions,
                is_default=False,
                is_active=True,
            )
            db.add(row)
            await db.flush()
        return row

    async def process_document(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        *,
        job_id: uuid.UUID | None = None,
    ) -> Document:
        result = await db.execute(select(Document).where(Document.id == document_id))
        doc = result.scalar_one()
        doc.status = DocumentStatus.PROCESSING
        await db.flush()

        job: IngestionJob | None = None
        if job_id:
            job = (
                await db.execute(select(IngestionJob).where(IngestionJob.id == job_id))
            ).scalar_one_or_none()
        if job is None:
            job = await job_service.latest_job(db, doc.id)
        if job is None:
            job = await job_service.create_job(
                db,
                workspace_id=doc.workspace_id,
                document_id=doc.id,
                document_version_id=doc.active_version_id,
            )
        await job_service.mark_processing(db, job, stage=IngestionJobStage.PARSE)

        try:
            path = Path(doc.storage_path)
            data = path.read_bytes()
            content_hash = hashlib.sha256(data).hexdigest()
            doc.content_hash = content_hash

            # Ensure a document_versions row exists for this upload
            version = await self._ensure_version(db, doc, content_hash)
            doc.active_version_id = version.id
            doc.version = version.version_number

            await job_service.mark_stage(db, job, IngestionJobStage.CHUNK)
            parsed = parse_document(doc.original_filename, doc.content_type, data)
            chunks = chunk_document(parsed)

            await job_service.mark_stage(db, job, IngestionJobStage.EMBED)
            embeddings = await self.embedder.embed_texts(
                [contextualize(doc.original_filename, c.heading, c.content) for c in chunks]
            )
            emb_model = await self._active_embedding_model(db)

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
                        document_version_id=version.id,
                        workspace_id=doc.workspace_id,
                        chunk_index=chunk.chunk_index,
                        content=chunk.content,
                        token_count=chunk.token_count,
                        page_number=chunk.page_number,
                        heading=chunk.heading,
                        embedding=emb,
                        embedding_model_id=emb_model.id,
                        meta=chunk.meta,
                    )
                )

            doc.page_count = parsed.page_count
            doc.chunk_count = len(chunks)
            doc.meta = {**(doc.meta or {}), **parsed.meta}

            await job_service.mark_stage(db, job, IngestionJobStage.SUMMARIZE)
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
                q.strip(" -•\t0123456789.") for q in questions_raw.splitlines() if q.strip()
            ][:5]

            doc.summary = summary
            doc.suggested_questions = questions

            # Normalized tables
            db.add(
                DocumentSummary(
                    document_id=doc.id,
                    document_version_id=version.id,
                    summary_text=summary,
                    summary_type="auto",
                    model_name=self.settings.chat_model,
                    token_count=max(1, len(summary) // 4),
                )
            )
            # Replace suggested questions rows
            old_q = await db.execute(
                select(SuggestedQuestion).where(SuggestedQuestion.document_id == doc.id)
            )
            for qrow in old_q.scalars().all():
                await db.delete(qrow)
            await db.flush()
            for i, q in enumerate(questions):
                db.add(
                    SuggestedQuestion(
                        document_id=doc.id,
                        question=q,
                        rank=i,
                        model_name=self.settings.chat_model,
                    )
                )

            await self._extract_entities(db, doc, parsed.text)

            doc.status = DocumentStatus.READY
            doc.error_message = None
            await job_service.mark_done(db, job)
            await db.flush()

            await notify_user(
                db,
                user_id=doc.uploaded_by,
                workspace_id=doc.workspace_id,
                type="document.ready",
                title="Document ready",
                body=f"{doc.original_filename} finished indexing ({doc.chunk_count} chunks).",
                link_url="/documents",
                meta={"document_id": str(doc.id)},
            )
            from app.services.enterprise.service import enqueue_webhook_deliveries

            await enqueue_webhook_deliveries(
                db,
                workspace_id=doc.workspace_id,
                event_type="document.ready",
                payload={
                    "document_id": str(doc.id),
                    "filename": doc.original_filename,
                    "chunk_count": doc.chunk_count,
                },
            )
            return doc
        except Exception as exc:  # noqa: BLE001
            doc.status = DocumentStatus.FAILED
            doc.error_message = str(exc)[:1000]
            if job:
                await job_service.mark_failed(db, job, str(exc))
            await db.flush()
            await notify_user(
                db,
                user_id=doc.uploaded_by,
                workspace_id=doc.workspace_id,
                type="document.failed",
                title="Document failed",
                body=f"{doc.original_filename} failed to index: {str(exc)[:200]}",
                link_url="/documents",
                meta={"document_id": str(doc.id)},
            )
            raise

    async def _ensure_version(
        self, db: AsyncSession, doc: Document, content_hash: str
    ) -> DocumentVersion:
        if doc.active_version_id:
            existing = (
                await db.execute(
                    select(DocumentVersion).where(DocumentVersion.id == doc.active_version_id)
                )
            ).scalar_one_or_none()
            if existing and existing.content_hash == content_hash:
                return existing

        # Deactivate prior versions
        prior = await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == doc.id,
                DocumentVersion.is_active.is_(True),
            )
        )
        for v in prior.scalars().all():
            v.is_active = False

        next_num = doc.version or 1
        # If versions already exist, bump
        latest = await db.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == doc.id)
            .order_by(DocumentVersion.version_number.desc())
            .limit(1)
        )
        last = latest.scalar_one_or_none()
        if last:
            next_num = last.version_number + 1

        version = DocumentVersion(
            document_id=doc.id,
            version_number=next_num,
            storage_path=doc.storage_path,
            content_hash=content_hash,
            file_size=doc.file_size,
            is_active=True,
            uploaded_by=doc.uploaded_by,
        )
        db.add(version)
        await db.flush()
        return version

    async def _extract_entities(self, db: AsyncSession, doc: Document, text: str) -> None:
        """Lightweight entity extraction — capitalized phrases + dates."""
        # Clear prior mentions for this document
        old = await db.execute(select(DocumentEntity).where(DocumentEntity.document_id == doc.id))
        for row in old.scalars().all():
            await db.delete(row)
        await db.flush()

        candidates: list[tuple[str, EntityType]] = []
        for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b", text[:20000]):
            name = m.group(1).strip()
            if len(name) < 3 or name.lower() in {"the", "this", "that", "and"}:
                continue
            candidates.append((name, EntityType.CONCEPT))
        for m in re.finditer(
            r"\b((?:19|20)\d{2}(?:-\d{2}-\d{2})?|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})\b",
            text[:20000],
        ):
            candidates.append((m.group(1), EntityType.DATE))

        seen: set[str] = set()
        for name, etype in candidates[:40]:
            key = f"{etype.value}:{name.lower()}"
            if key in seen:
                continue
            seen.add(key)
            normalized = name.lower()
            entity = (
                await db.execute(
                    select(Entity).where(
                        Entity.workspace_id == doc.workspace_id,
                        Entity.normalized_name == normalized,
                        Entity.entity_type == etype,
                    )
                )
            ).scalar_one_or_none()
            if not entity:
                entity = Entity(
                    workspace_id=doc.workspace_id,
                    name=name,
                    normalized_name=normalized,
                    entity_type=etype,
                )
                db.add(entity)
                await db.flush()
            db.add(
                DocumentEntity(
                    entity_id=entity.id,
                    document_id=doc.id,
                    mention_text=name,
                    confidence=0.5,
                )
            )
        await db.flush()
