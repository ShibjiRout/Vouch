"""Dense embeddings via OpenAI, sparse BM25 locally."""

from fastembed import SparseTextEmbedding
from langchain_openai import OpenAIEmbeddings
from qdrant_client import models

from app.config import EMBEDDING_MODEL, OPENAI_API_KEY, SPARSE_MODEL

# Batch size for embedding at ingestion. The API accepts more, but a
# failure costs the whole batch.
BATCH_SIZE = 100

_dense = OpenAIEmbeddings(model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY)
_sparse: SparseTextEmbedding | None = None


def _sparse_model() -> SparseTextEmbedding:
    """Load BM25 on first use; it downloads about 10MB."""
    global _sparse
    if _sparse is None:
        _sparse = SparseTextEmbedding(SPARSE_MODEL)
    return _sparse


def embed_query(text: str) -> list[float]:
    """Embed one question."""
    return _dense.embed_query(text)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed many chunks, in batches."""
    vectors: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        vectors.extend(_dense.embed_documents(texts[start : start + BATCH_SIZE]))
    return vectors


def _to_sparse(embedding) -> models.SparseVector:
    return models.SparseVector(
        indices=embedding.indices.tolist(),
        values=embedding.values.tolist(),
    )


def sparse_texts(texts: list[str]) -> list[models.SparseVector]:
    """BM25 vectors for chunks, with term frequency weighting."""
    return [_to_sparse(e) for e in _sparse_model().embed(texts)]


def sparse_query(text: str) -> models.SparseVector:
    """BM25 vector for a question. Weighted differently to a chunk."""
    return _to_sparse(next(iter(_sparse_model().query_embed(text))))
