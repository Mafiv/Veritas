# Retrieval evaluation results

| Pipeline | R@1 | R@5 | R@10 | MRR@10 | R@5 (paraphrased Qs) | p50 latency |
|---|---|---|---|---|---|---|
| legacy (in-memory) | 0.58 | 0.93 | 0.95 | 0.73 | 0.92 | 198 ms |
| vector | 0.39 | 0.78 | 0.88 | 0.56 | 0.76 | 28 ms |
| keyword (BM25) | 0.63 | 0.88 | 0.90 | 0.73 | 0.88 | 71 ms |
| hybrid | 0.49 | 0.85 | 0.93 | 0.64 | 0.80 | 83 ms |
| **hybrid + lexical rerank** (default) | 0.63 | 0.93 | 0.95 | 0.76 | 0.92 | 87 ms |
| hybrid + cross-encoder | 0.56 | 0.85 | 0.88 | 0.68 | 0.88 | 3193 ms |

41 answerable + 6 unanswerable questions over 10 PEPs (167 chunks). Embeddings: `BAAI/bge-small-en-v1.5`; cross-encoder: `Xenova/ms-marco-MiniLM-L-6-v2`. Latency is retrieval only (query embedding + search + rerank), CPU, single process.

Abstention (`MIN_RELEVANCE_SCORE`): the configured **0.2** keeps 100% of answerable questions and abstains on 50% of unanswerable ones. The best-separating value on this set is 0.28 (98% kept / 100% abstained), but it is fit on only 6 negatives.
