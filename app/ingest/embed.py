"""Dense embeddings via OpenAI."""

from langchain_openai import OpenAIEmbeddings

from app.config import EMBEDDING_MODEL, OPENAI_API_KEY

# Batch size for embedding at ingestion. The API accepts more, but a
# failure costs the whole batch.
BATCH_SIZE = 100

_embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY)


def embed_query(text: str) -> list[float]:
    """Embed one question."""
    return _embeddings.embed_query(text)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed many chunks, in batches."""
    vectors: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        vectors.extend(_embeddings.embed_documents(texts[start : start + BATCH_SIZE]))
    return vectors
