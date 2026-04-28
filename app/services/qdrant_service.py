from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, Distance, PointStruct,
    Filter, FieldCondition, MatchValue,
    PayloadSchemaType
)
import uuid
from app.config import QDRANT_URL, COLLECTION_NAME, QDRANT_API_KEY


client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY if QDRANT_API_KEY else None)


def create_collection():
    try:
        collections = [c.name for c in client.get_collections().collections]
        if COLLECTION_NAME not in collections:
            client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=1536, distance=Distance.COSINE)
            )
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="case_id",
            field_schema=PayloadSchemaType.KEYWORD
        )
    except Exception as e:
        raise Exception(f"Failed to create Qdrant collection: {e}")


def store_chunks(case_id: str, chunks: list[str], vectors: list[list[float]]):
    try:
        points = []
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={"case_id": case_id, "text": chunk, "chunk_index": i}
            ))
        client.upsert(collection_name=COLLECTION_NAME, points=points)
    except Exception as e:
        raise Exception(f"Failed to store chunks in Qdrant: {e}")


def search_chunks(case_id: str, query_vector: list[float], top_k: int = 25):
    try:
        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            query_filter=Filter(
                must=[FieldCondition(key="case_id", match=MatchValue(value=case_id))]
            ),
            limit=top_k
        )
        return [{"text": r.payload["text"], "score": r.score} for r in results.points]
    except Exception as e:
        raise Exception(f"Failed to search Qdrant: {e}")


def delete_chunks(case_id: str):
    try:
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=Filter(
                must=[FieldCondition(key="case_id", match=MatchValue(value=case_id))]
            )
        )
    except Exception as e:
        raise Exception(f"Failed to delete chunks from Qdrant: {e}")