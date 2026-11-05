# Retrieval evaluation

Measures whether the right passage reaches the LLM. Generation quality is not
scored here; this harness isolates retrieval so every change to chunking,
search or reranking gets a number.

```bash
cd backend
alembic upgrade head                    # needs Postgres + pgvector (DATABASE_URL)
python -m evaluation.run                # full comparison, writes results/latest.{json,md}
python -m evaluation.run --fast --check # what CI runs: fails on regression vs baseline.json
python -m evaluation.run --write-baseline
```

Current numbers: [`RESULTS.md`](RESULTS.md).

## Method

- **Corpus**: 10 Python PEPs (public domain / CC0), about 244 KB, ingested
  through the real pipeline (parse, chunk, contextual embedding). Everything runs
  in one transaction that is rolled back, so the database is left untouched.
- **Questions** ([`dataset.json`](dataset.json)): 41 answerable questions,
  hand-written, 25 of them deliberately paraphrased so they share few words with
  the source, plus 6 questions the corpus cannot answer.
- **Relevance**: a retrieved chunk counts if it comes from the gold document
  and contains the gold `evidence` phrase (whitespace- and case-normalised).
  Labels are tied to text rather than chunk ids, so they stay valid when the
  chunker changes. The loader refuses to run if any evidence phrase is missing
  from its document.
- **Metrics**: Recall@{1,3,5,10} and MRR@10 over answerable questions;
  Recall@5 split by lexical/paraphrased questions; p50/p95 retrieval latency
  (query embedding + search + rerank, CPU, single process).
- **Abstention**: the top reranker score for answerable vs unanswerable
  questions, which is used to set `MIN_RELEVANCE_SCORE`.
- **Baseline**: `legacy.py` reproduces the pre-pgvector pipeline
  (load every chunk, Python cosine + in-memory BM25, RRF, term-overlap rerank)
  over the same stored embeddings.

## Decisions it drove

1. **BM25 over Postgres candidates.** `ts_rank_cd` has no IDF, and keyword-only
   R@5 was 0.78. Scoring GIN-matched candidates with BM25 raised it to 0.88.
2. **Lexical reranker by default.** The MS MARCO MiniLM cross-encoder scored
   R@5 0.85 vs 0.93 and added about 3 s per query on CPU. It is still
   available with `RERANKER_BACKEND=cross_encoder`.
3. **Abstention threshold 0.20**, set below the best-separating value of 0.28
   because only 6 unanswerable questions back that value.

## Limits

41 questions over one domain is a smoke-level benchmark: differences of a
couple of points are noise. Generation faithfulness (an LLM judge) and HyDE /
multi-query (which need a real LLM) are not evaluated yet.
