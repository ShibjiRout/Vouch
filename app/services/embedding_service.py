from langchain_openai import OpenAIEmbeddings
from app.config import OPENAI_API_KEY

embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    openai_api_key=OPENAI_API_KEY
)


def get_embedding(text: str) -> list[float]:
    try:
        return embeddings.embed_query(text)
    except Exception as e:
        raise Exception(f"Failed to generate embedding: {e}")


def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    try:
        return embeddings.embed_documents(texts)
    except Exception as e:
        raise Exception(f"Failed to generate batch embeddings: {e}")