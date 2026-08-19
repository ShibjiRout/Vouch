"""Search a chat's chunks. Dense only for now."""

from dataclasses import dataclass
from uuid import UUID

from app.config import COLLECTION_NAME, DENSE_VECTOR, FETCH_LIMIT
from app.db.qdrant import client, search_filter
from app.ingest.embed import embed_query
from app.logging_config import get_logger

log = get_logger(__name__)


@dataclass
class Hit:
    """One retrieved chunk, with what it takes to cite it."""

    text: str
    filename: str
    page: int
    document_id: str
    chunk_type: str
    score: float


def search(
    question: str,
    tenant_id: UUID,
    thread_id: UUID,
    limit: int = FETCH_LIMIT,
) -> list[Hit]:
    """Find the chunks in this chat most like the question."""
    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=embed_query(question),
        using=DENSE_VECTOR,
        # Both keys, always. Neither is optional.
        query_filter=search_filter(tenant_id, thread_id),
        limit=limit,
    )

    hits = [
        Hit(
            text=point.payload["text"],
            filename=point.payload["filename"],
            page=point.payload["page"],
            document_id=point.payload["document_id"],
            chunk_type=point.payload["chunk_type"],
            score=point.score,
        )
        for point in results.points
    ]

    # Scores are logged so MIN_SCORE can be tuned against real values.
    # The chunk text is never logged.
    log.info(
        "search thread=%s hits=%s top=%.4f",
        thread_id,
        len(hits),
        hits[0].score if hits else 0.0,
    )
    return hits
