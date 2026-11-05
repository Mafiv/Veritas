"""Retrieval latency vs workspace size: legacy in-memory pipeline vs Postgres engine.

    python -m evaluation.bench_scale [--sizes 1000 5000 20000] [--queries 15]

Synthetic chunks: text from the eval corpus, random unit vectors (latency only;
quality is measured by evaluation.run). Runs in a rolled-back transaction.
Both pipelines include the same lexical rerank, so the difference is the search.
"""

from __future__ import annotations

import os

os.environ.setdefault("USE_MOCK_LLM", "true")
os.environ.setdefault("EMBEDDING_PROVIDER", "local")
os.environ.setdefault("DEBUG", "false")

import argparse  # noqa: E402
import asyncio  # noqa: E402
import json  # noqa: E402
import random  # noqa: E402
import statistics  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
from sqlalchemy import insert, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.models.domain import (  # noqa: E402
    Document,
    DocumentChunk,
    DocumentStatus,
    DocumentType,
    User,
    Workspace,
)
from app.services.ingestion.embedder import Embedder  # noqa: E402
from app.services.retrieval.hybrid_search import HybridSearcher  # noqa: E402
from app.services.retrieval.reranker import LexicalReranker  # noqa: E402
from evaluation.legacy import legacy_search  # noqa: E402

ROOT = Path(__file__).parent


def paragraphs() -> list[str]:
    out: list[str] = []
    for p in sorted((ROOT / "corpus").glob("*.txt")):
        out += [x.strip() for x in p.read_text().split("\n\n") if len(x.strip()) > 200]
    return out


async def grow(db: AsyncSession, ws: uuid.UUID, doc: uuid.UUID, start: int, end: int) -> None:
    rng = np.random.default_rng(start)
    texts = paragraphs()
    batch = 1000
    for lo in range(start, end, batch):
        n = min(batch, end - lo)
        vecs = rng.normal(size=(n, get_settings().embedding_dimensions)).astype(np.float32)
        vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
        await db.execute(
            insert(DocumentChunk),
            [
                {
                    "id": uuid.uuid4(),
                    "document_id": doc,
                    "workspace_id": ws,
                    "chunk_index": lo + i,
                    "content": texts[(lo + i) % len(texts)],
                    "token_count": len(texts[(lo + i) % len(texts)]) // 4,
                    "embedding": vecs[i].tolist(),
                }
                for i in range(n)
            ],
        )


async def main(sizes: list[int], n_queries: int) -> list[dict]:
    questions = [
        q["question"] for q in json.loads((ROOT / "dataset.json").read_text())["questions"]
    ]
    random.Random(0).shuffle(questions)
    questions = questions[:n_queries]
    embedder = Embedder()
    embeddings = [await embedder.embed_query(q) for q in questions]
    searcher, lexical = HybridSearcher(embedder), LexicalReranker()

    engine = create_async_engine(get_settings().database_url)
    rows: list[dict] = []
    async with engine.connect() as conn:
        trans = await conn.begin()
        db = AsyncSession(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            user = User(email=f"bench-{uuid.uuid4().hex[:8]}@example.com", full_name="Bench")
            db.add(user)
            await db.flush()
            ws = Workspace(name="Bench", slug=f"bench-{uuid.uuid4().hex[:8]}", owner_id=user.id)
            db.add(ws)
            await db.flush()
            doc = Document(
                workspace_id=ws.id,
                uploaded_by=user.id,
                filename="synthetic.txt",
                original_filename="synthetic.txt",
                content_type="text/plain",
                doc_type=DocumentType.TEXT,
                status=DocumentStatus.READY,
                storage_path="/dev/null",
            )
            db.add(doc)
            await db.flush()

            have = 0
            for size in sizes:
                await grow(db, ws.id, doc.id, have, size)
                have = size
                await db.execute(text("ANALYZE document_chunks"))
                timings: dict[str, list[float]] = {"legacy": [], "postgres": []}
                for q, e in zip(questions, embeddings):
                    t0 = time.perf_counter()
                    await legacy_search(db, workspace_id=ws.id, query=q, query_embedding=e)
                    timings["legacy"].append((time.perf_counter() - t0) * 1000)
                    db.expunge_all()  # don't let the identity map hide load cost
                    t0 = time.perf_counter()
                    cands = await searcher.search(
                        db, workspace_id=ws.id, query=q, query_embedding=e
                    )
                    await lexical.rerank(q, cands, top_k=10)
                    timings["postgres"].append((time.perf_counter() - t0) * 1000)
                    db.expunge_all()
                row = {
                    "chunks": size,
                    "legacy_p50_ms": round(statistics.median(timings["legacy"]), 1),
                    "postgres_p50_ms": round(statistics.median(timings["postgres"]), 1),
                }
                rows.append(row)
                print(row, flush=True)
        finally:
            await db.close()
            await trans.rollback()
    await engine.dispose()
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[1000, 5000, 20000])
    parser.add_argument("--queries", type=int, default=15)
    args = parser.parse_args()
    result = asyncio.run(main(sorted(args.sizes), args.queries))
    lines = [
        "| Chunks in workspace | Legacy (in-memory) p50 | Postgres engine p50 |",
        "|---|---|---|",
    ]
    lines += [
        f"| {r['chunks']:,} | {r['legacy_p50_ms']:,.0f} ms | {r['postgres_p50_ms']:,.0f} ms |"
        for r in result
    ]
    print("\n".join(lines))
