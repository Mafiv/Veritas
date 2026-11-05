"""Re-embed chunks that have no vector or were embedded by another model.

Run after migration 011 or after changing EMBEDDING_MODEL:

    python -m app.cli.reembed [--batch 64] [--all]
"""

from __future__ import annotations

import argparse
import asyncio
import time

from sqlalchemy import or_, select

from app.db.session import AsyncSessionLocal
from app.models.domain import Document, DocumentChunk
from app.services.ingestion.chunker import contextualize
from app.services.ingestion.embedder import Embedder
from app.services.ingestion.pipeline import IngestionService


async def reembed(batch_size: int, include_all: bool) -> int:
    embedder = Embedder()
    done = 0
    started = time.perf_counter()
    async with AsyncSessionLocal() as db:
        model = await IngestionService()._active_embedding_model(db)
        await db.commit()
        last_id = None
        while True:
            stmt = (
                select(DocumentChunk, Document.original_filename)
                .join(Document, Document.id == DocumentChunk.document_id)
                .order_by(DocumentChunk.id)
                .limit(batch_size)
            )
            if not include_all:
                stmt = stmt.where(
                    or_(
                        DocumentChunk.embedding.is_(None),
                        DocumentChunk.embedding_model_id.is_distinct_from(model.id),
                    )
                )
            if last_id is not None:
                stmt = stmt.where(DocumentChunk.id > last_id)
            rows = (await db.execute(stmt)).all()
            if not rows:
                break
            chunks = [chunk for chunk, _ in rows]
            vectors = await embedder.embed_texts(
                [contextualize(title, chunk.heading, chunk.content) for chunk, title in rows]
            )
            for chunk, vec in zip(chunks, vectors):
                chunk.embedding = vec
                chunk.embedding_model_id = model.id
            await db.commit()
            last_id = chunks[-1].id
            done += len(chunks)
            print(f"re-embedded {done} chunks ({time.perf_counter() - started:.1f}s)")
    return done


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, default=64)
    parser.add_argument("--all", action="store_true", help="re-embed every chunk")
    args = parser.parse_args()
    total = asyncio.run(reembed(args.batch, args.all))
    print(f"done: {total} chunks")


if __name__ == "__main__":
    main()
