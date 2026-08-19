"""Qdrant client, collection setup, and scoped filters."""

from uuid import UUID, uuid4

from qdrant_client import QdrantClient, models

from app.config import (
    COLLECTION_NAME,
    DENSE_VECTOR,
    EMBEDDING_DIM,
    QDRANT_API_KEY,
    QDRANT_URL,
    SPARSE_VECTOR,
)

client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)

UPSERT_BATCH = 256


def ensure_collection() -> None:
    """Create the collection and its indexes if missing."""
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config={
                DENSE_VECTOR: models.VectorParams(
                    size=EMBEDDING_DIM,
                    distance=models.Distance.COSINE,
                )
            },
            # Declared now even though phase 2 writes dense only, so
            # adding BM25 later does not mean rebuilding the collection.
            sparse_vectors_config={
                SPARSE_VECTOR: models.SparseVectorParams(
                    modifier=models.Modifier.IDF,
                )
            },
        )

    # is_tenant=True stores each tenant's points together on disk.
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="tenant_id",
        field_schema=models.KeywordIndexParams(type="keyword", is_tenant=True),
    )
    # Filtered on every query, but not what partitions the data.
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="thread_id",
        field_schema=models.PayloadSchemaType.KEYWORD,
    )
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="document_id",
        field_schema=models.PayloadSchemaType.KEYWORD,
    )


def upsert_chunks(
    tenant_id: UUID,
    thread_id: UUID,
    document_id: UUID,
    filename: str,
    chunks: list,
    vectors: list[list[float]],
    sparse: list | None = None,
) -> None:
    """Write a document's chunks, carrying both scope keys."""
    sparse = sparse or [None] * len(chunks)
    points = [
        models.PointStruct(
            id=str(uuid4()),
            vector=(
                {DENSE_VECTOR: vector, SPARSE_VECTOR: sparse_vector}
                if sparse_vector is not None
                else {DENSE_VECTOR: vector}
            ),
            payload={
                "tenant_id": str(tenant_id),
                "thread_id": str(thread_id),
                "document_id": str(document_id),
                "filename": filename,
                "page": chunk.page,
                "chunk_index": chunk.chunk_index,
                "chunk_type": chunk.chunk_type,
                "text": chunk.text,
            },
        )
        for chunk, vector, sparse_vector in zip(chunks, vectors, sparse)
    ]

    # Batched so one oversized request cannot fail a whole document.
    for start in range(0, len(points), UPSERT_BATCH):
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=points[start : start + UPSERT_BATCH],
        )


def _filter(**fields: UUID | str) -> models.Filter:
    """Build a must-match filter from the given fields."""
    return models.Filter(
        must=[
            models.FieldCondition(key=key, match=models.MatchValue(value=str(value)))
            for key, value in fields.items()
        ]
    )


def search_filter(tenant_id: UUID, thread_id: UUID) -> models.Filter:
    """Scope a search. Both arguments are required, always."""
    return _filter(tenant_id=tenant_id, thread_id=thread_id)


def delete_document(tenant_id: UUID, document_id: UUID) -> None:
    """Remove every point belonging to one document."""
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=_filter(tenant_id=tenant_id, document_id=document_id),
    )


def delete_thread(tenant_id: UUID, thread_id: UUID) -> None:
    """Remove every point belonging to one chat."""
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=_filter(tenant_id=tenant_id, thread_id=thread_id),
    )
