"""Retrieval evaluation: ingest a fixed corpus, score several pipelines, report.

    python -m evaluation.run                    # print + write results/latest.{json,md}
    python -m evaluation.run --check            # also fail on regression vs baseline.json
    python -m evaluation.run --write-baseline   # accept current numbers (baseline.json, RESULTS.md)
    python -m evaluation.run --fast --check     # CI: skip the slow cross-encoder comparison

Needs a migrated Postgres with pgvector (DATABASE_URL). Everything happens in
one transaction that is rolled back, so the database is left untouched.
Summaries use the mock LLM; embeddings and reranking use the real local models.
"""

from __future__ import annotations

import os

# Must be set before app settings are first read.
os.environ.setdefault("USE_MOCK_LLM", "true")
os.environ.setdefault("EMBEDDING_PROVIDER", "local")
os.environ.setdefault("DEBUG", "false")

import argparse  # noqa: E402
import asyncio  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import statistics  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from collections.abc import Awaitable, Callable  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

os.environ.setdefault("LOCAL_STORAGE_PATH", tempfile.mkdtemp(prefix="veritas-eval-"))

from sqlalchemy import func, select  # noqa: E402
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
from app.services.ingestion import jobs as job_service  # noqa: E402
from app.services.ingestion.embedder import Embedder  # noqa: E402
from app.services.ingestion.pipeline import IngestionService  # noqa: E402
from app.services.retrieval.hybrid_search import HybridSearcher, ScoredChunk  # noqa: E402
from app.services.retrieval.reranker import CrossEncoderReranker, LexicalReranker  # noqa: E402
from evaluation.legacy import legacy_search  # noqa: E402

ROOT = Path(__file__).parent
DEPTH = 10  # rankings are scored to this depth
KS = (1, 3, 5, 10)
LEXICAL = "hybrid + lexical rerank"
CROSS = "hybrid + cross-encoder"

Ranker = Callable[[AsyncSession, uuid.UUID, str, list[float]], Awaitable[list[ScoredChunk]]]


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


@dataclass
class Question:
    id: str
    question: str
    doc: str | None
    evidence: str | None
    style: str

    def relevant(self, hit: ScoredChunk) -> bool:
        return (
            self.doc is not None
            and self.evidence is not None
            and hit.document.original_filename == self.doc
            and norm(self.evidence) in norm(hit.chunk.content)
        )


@dataclass
class ConfigResult:
    name: str
    ranks: dict[str, int | None] = field(default_factory=dict)  # 1-based, None = miss
    latencies_ms: list[float] = field(default_factory=list)
    top_scores: dict[str, float] = field(default_factory=dict)

    def metrics(self, questions: list[Question]) -> dict[str, Any]:
        answerable = [q for q in questions if q.doc]
        ranks = [self.ranks[q.id] for q in answerable]
        out: dict[str, Any] = {
            f"recall@{k}": round(sum(1 for r in ranks if r and r <= k) / len(ranks), 3) for k in KS
        }
        out["mrr@10"] = round(sum(1 / r for r in ranks if r) / len(ranks), 3)
        for style in ("lexical", "paraphrase"):
            subset = [self.ranks[q.id] for q in answerable if q.style == style]
            out[f"recall@5_{style}"] = round(
                sum(1 for r in subset if r and r <= 5) / max(1, len(subset)), 3
            )
        lat = sorted(self.latencies_ms)
        out["latency_p50_ms"] = round(statistics.median(lat), 1)
        out["latency_p95_ms"] = round(lat[min(len(lat) - 1, int(0.95 * len(lat)))], 1)
        return out


def load_questions() -> list[Question]:
    data = json.loads((ROOT / "dataset.json").read_text())
    questions = [Question(**q) for q in data["questions"]]
    corpus = {p.name: norm(p.read_text()) for p in (ROOT / "corpus").glob("*.txt")}
    for q in questions:
        if q.doc and norm(q.evidence or "") not in corpus.get(q.doc, ""):
            raise SystemExit(f"dataset error: evidence for {q.id!r} not found in {q.doc}")
    return questions


async def ingest_corpus(db: AsyncSession) -> tuple[uuid.UUID, int, float]:
    suffix = uuid.uuid4().hex[:8]
    user = User(email=f"eval-{suffix}@example.com", full_name="Eval")
    db.add(user)
    await db.flush()
    ws = Workspace(name="Eval", slug=f"eval-{suffix}", owner_id=user.id)
    db.add(ws)
    await db.flush()

    service = IngestionService()
    started = time.perf_counter()
    for path in sorted((ROOT / "corpus").glob("*.txt")):
        data = path.read_bytes()
        doc = Document(
            workspace_id=ws.id,
            uploaded_by=user.id,
            filename=path.name,
            original_filename=path.name,
            content_type="text/plain",
            doc_type=DocumentType.TEXT,
            status=DocumentStatus.PENDING,
            storage_path=await service.store_file(ws.id, path.name, data),
            file_size=len(data),
        )
        db.add(doc)
        await db.flush()
        job = await job_service.create_job(db, workspace_id=ws.id, document_id=doc.id)
        await service.process_document(db, doc.id, job_id=job.id)
    chunks = (
        await db.execute(select(func.count()).where(DocumentChunk.workspace_id == ws.id))
    ).scalar_one()
    return ws.id, int(chunks), time.perf_counter() - started


def build_rankers(fast: bool = False) -> dict[str, Ranker]:
    searcher = HybridSearcher()
    reranker = CrossEncoderReranker()
    settings = get_settings()

    def mode(name: str) -> Ranker:
        async def run(
            db: AsyncSession, ws: uuid.UUID, q: str, emb: list[float]
        ) -> list[ScoredChunk]:
            return await searcher.search(
                db,
                workspace_id=ws,
                query=q,
                query_embedding=emb,
                top_k=DEPTH,
                mode=name,  # type: ignore[arg-type]
            )

        return run

    async def legacy(
        db: AsyncSession, ws: uuid.UUID, q: str, emb: list[float]
    ) -> list[ScoredChunk]:
        return await legacy_search(db, workspace_id=ws, query=q, query_embedding=emb)

    def reranked(rr: Any) -> Ranker:
        async def run(
            db: AsyncSession, ws: uuid.UUID, q: str, emb: list[float]
        ) -> list[ScoredChunk]:
            candidates = await searcher.search(
                db, workspace_id=ws, query=q, query_embedding=emb, top_k=settings.retrieval_top_k
            )
            return await rr.rerank(q, candidates, top_k=DEPTH)

        return run

    rankers = {
        "legacy (in-memory)": legacy,
        "vector": mode("vector"),
        "keyword (BM25)": mode("keyword"),
        "hybrid": mode("hybrid"),
        LEXICAL: reranked(LexicalReranker()),
        CROSS: reranked(reranker),
    }
    if fast:  # CI: skip the slow non-default reranker comparison
        rankers = {k: v for k, v in rankers.items() if k != CROSS or shipped_name() == CROSS}
    return rankers


def shipped_name() -> str:
    return CROSS if get_settings().reranker_backend == "cross_encoder" else LEXICAL


async def evaluate(questions: list[Question], fast: bool = False) -> dict[str, Any]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    embedder = Embedder()
    async with engine.connect() as conn:
        trans = await conn.begin()
        db = AsyncSession(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            ws, n_chunks, ingest_s = await ingest_corpus(db)
            print(f"ingested {n_chunks} chunks in {ingest_s:.1f}s", file=sys.stderr)
            rankers = build_rankers(fast)
            # Warm up models so the first measured query is not a cold start.
            warm = await embedder.embed_query("warm up")
            for ranker in rankers.values():
                await ranker(db, ws, "warm up", warm)

            results = {name: ConfigResult(name) for name in rankers}
            for q in questions:
                for name, ranker in rankers.items():
                    t0 = time.perf_counter()
                    emb = await embedder.embed_query(q.question)
                    hits = await ranker(db, ws, q.question, emb)
                    results[name].latencies_ms.append((time.perf_counter() - t0) * 1000)
                    rank = next((i for i, h in enumerate(hits, 1) if q.relevant(h)), None)
                    results[name].ranks[q.id] = rank
                    results[name].top_scores[q.id] = hits[0].score if hits else 0.0
        finally:
            await db.close()
            await trans.rollback()
    await engine.dispose()

    shipped = results[shipped_name()]
    return {
        "dataset": "veritas-peps-v1",
        "corpus": {"documents": 10, "chunks": n_chunks, "ingest_seconds": round(ingest_s, 1)},
        "questions": {
            "answerable": sum(1 for q in questions if q.doc),
            "unanswerable": sum(1 for q in questions if not q.doc),
        },
        "embedding_model": settings.embedding_model,
        "reranker_model": settings.reranker_model,
        "shipped": shipped_name(),
        "configs": {name: r.metrics(questions) for name, r in results.items()},
        "abstention": calibrate(questions, shipped),
        "per_question": {
            q.id: {
                "style": q.style,
                "rank": {name: r.ranks[q.id] for name, r in results.items()},
                "shipped_top_score": round(shipped.top_scores[q.id], 4),
            }
            for q in questions
        },
    }


def calibrate(questions: list[Question], shipped: ConfigResult) -> dict[str, Any]:
    """Pick the reranker-score threshold that best separates answerable from not."""
    pos = sorted(shipped.top_scores[q.id] for q in questions if q.doc)
    neg = sorted(shipped.top_scores[q.id] for q in questions if not q.doc)
    best = (0.0, -1.0)
    for t in sorted(set(pos + neg)):
        kept = sum(1 for s in pos if s >= t) / len(pos)
        abstained = sum(1 for s in neg if s < t) / len(neg)
        score = kept + abstained
        if score > best[1]:
            best = (t, score)
    t = best[0]
    configured = get_settings().min_relevance_score
    return {
        "configured_min_relevance_score": configured,
        "configured_answerable_kept": round(sum(1 for s in pos if s >= configured) / len(pos), 3),
        "configured_unanswerable_abstained": round(
            sum(1 for s in neg if s < configured) / len(neg), 3
        ),
        "suggested_min_relevance_score": round(t, 4),
        "answerable_kept": round(sum(1 for s in pos if s >= t) / len(pos), 3),
        "unanswerable_abstained": round(sum(1 for s in neg if s < t) / len(neg), 3),
        "answerable_top_score_p10": round(pos[max(0, len(pos) // 10)], 4),
        "unanswerable_top_score_max": round(max(neg), 4),
    }


def to_markdown(report: dict[str, Any]) -> str:
    cols = ["recall@1", "recall@5", "recall@10", "mrr@10", "recall@5_paraphrase", "latency_p50_ms"]
    head = "| Pipeline | R@1 | R@5 | R@10 | MRR@10 | R@5 (paraphrased Qs) | p50 latency |"
    lines = [head, "|---|---|---|---|---|---|---|"]
    for name, m in report["configs"].items():
        cells = [f"{m[c]:.2f}" if c != "latency_p50_ms" else f"{m[c]:.0f} ms" for c in cols]
        label = f"**{name}** (default)" if name == report["shipped"] else name
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    c, q, a = report["corpus"], report["questions"], report["abstention"]
    lines += [
        "",
        f"{q['answerable']} answerable + {q['unanswerable']} unanswerable questions over "
        f"{c['documents']} PEPs ({c['chunks']} chunks). Embeddings: `{report['embedding_model']}`; "
        f"cross-encoder: `{report['reranker_model']}`. Latency is retrieval only (query "
        "embedding + search + rerank), CPU, single process.",
        "",
        f"Abstention (`MIN_RELEVANCE_SCORE`): the configured **{a['configured_min_relevance_score']}** "
        f"keeps {a['configured_answerable_kept']:.0%} of answerable questions and abstains on "
        f"{a['configured_unanswerable_abstained']:.0%} of unanswerable ones. The best-separating "
        f"value on this set is {a['suggested_min_relevance_score']} "
        f"({a['answerable_kept']:.0%} kept / {a['unanswerable_abstained']:.0%} abstained), "
        "but it is fit on only "
        f"{report['questions']['unanswerable']} negatives.",
    ]
    return "\n".join(lines) + "\n"


def check(report: dict[str, Any], baseline_path: Path, tolerance: float = 0.02) -> list[str]:
    baseline = json.loads(baseline_path.read_text())
    failures = []
    name = report["shipped"]
    for metric in ("recall@5", "recall@10", "mrr@10"):
        now = report["configs"][name][metric]
        before = baseline["configs"][name][metric]
        if now < before - tolerance:
            failures.append(f"{name} {metric} regressed: {before:.3f} -> {now:.3f}")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--check", action="store_true", help="fail on regression vs baseline.json")
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--fast", action="store_true", help="skip the cross-encoder comparison")
    args = parser.parse_args()

    report = asyncio.run(evaluate(load_questions(), fast=args.fast))
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    (out / "latest.json").write_text(json.dumps(report, indent=2) + "\n")
    md = to_markdown(report)
    (out / "latest.md").write_text(md)
    print(md)

    if args.write_baseline:
        (ROOT / "baseline.json").write_text(json.dumps(report, indent=2) + "\n")
        (ROOT / "RESULTS.md").write_text("# Retrieval evaluation results\n\n" + md)
        print("baseline updated", file=sys.stderr)
    if args.check:
        failures = check(report, ROOT / "baseline.json")
        if failures:
            print("\n".join(failures), file=sys.stderr)
            raise SystemExit(1)
        print("no regression vs baseline", file=sys.stderr)


if __name__ == "__main__":
    main()
