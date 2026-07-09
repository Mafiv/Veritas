"""Unit tests for hybrid search helpers."""

from app.services.retrieval.hybrid_search import BM25Index, reciprocal_rank_fusion, tokenize
from app.services.ingestion.embedder import cosine_similarity, _mock_embedding


def test_tokenize():
    assert tokenize("Hello, Veritas-RAG!") == ["hello", "veritas", "rag"]


def test_bm25_ranks_relevant_doc_higher():
    corpus = [
        "cats sit on mats",
        "hybrid search combines vector similarity with bm25 keyword matching",
        "unrelated cooking recipe for pasta",
    ]
    index = BM25Index()
    index.fit(corpus)
    scores = index.score("hybrid bm25 search")
    assert scores[1] > scores[0]
    assert scores[1] > scores[2]


def test_rrf_merges_rankings():
    fused = reciprocal_rank_fusion([[0, 1, 2], [1, 0, 2]], weights=[0.6, 0.4])
    assert set(fused.keys()) == {0, 1, 2}
    # index 0 and 1 should dominate over 2
    assert fused[2] < fused[0]
    assert fused[2] < fused[1]


def test_mock_embedding_normalized_and_deterministic():
    a = _mock_embedding("veritas grounded answers", 64)
    b = _mock_embedding("veritas grounded answers", 64)
    c = _mock_embedding("completely different text", 64)
    assert a == b
    assert abs(sum(x * x for x in a) - 1.0) < 1e-6
    assert cosine_similarity(a, b) > 0.99
    assert cosine_similarity(a, c) < 0.99
