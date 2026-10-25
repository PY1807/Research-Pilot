import math

from app.embeddings import EMBEDDING_DIM, HashEmbedder, get_embedder


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_tests_use_the_hash_embedder():
    assert isinstance(get_embedder(), HashEmbedder)


def test_hash_embedder_vectors_are_normalized_and_deterministic():
    embedder = HashEmbedder()
    first, second = embedder.embed_documents(["retrieval beats long context", "unrelated"])

    assert len(first) == EMBEDDING_DIM
    assert math.isclose(math.sqrt(sum(x * x for x in first)), 1.0)
    assert embedder.embed_query("retrieval beats long context") == first
    assert first != second


def test_hash_embedder_scores_shared_words_higher():
    embedder = HashEmbedder()
    query = embedder.embed_query("long context models")
    related, unrelated = embedder.embed_documents(
        ["Long context models read whole books.", "The recipe needs flour and sugar."]
    )

    assert _cosine(query, related) > _cosine(query, unrelated)
