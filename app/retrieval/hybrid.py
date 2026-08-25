"""Search a chat's chunks: dense and BM25, merged with RRF."""

from dataclasses import dataclass
from uuid import UUID

from qdrant_client import models

from app.config import (
    COLLECTION_NAME,
    DENSE_VECTOR,
    FETCH_LIMIT,
    SPARSE_VECTOR,
)
from app.db.qdrant import client, search_filter
from app.ingest.embed import embed_query, sparse_query
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
    context: str = ""

    @property
    def for_ranking(self) -> str:
        """Text as the reranker should read it, context line included."""
        return f"{self.context}\n{self.text}" if self.context else self.text


def search(
    question: str,
    tenant_id: UUID,
    thread_id: UUID,
    limit: int = FETCH_LIMIT,
) -> list[Hit]:
    """Find the chunks in this chat most like the question."""
    # Both searches run every time. Dense understands meaning; BM25
    # finds exact strings like "Note 14" or a specific figure, which
    # carry little meaning on their own.
    results = client.query_points(
        collection_name=COLLECTION_NAME,
        prefetch=[
            models.Prefetch(
                query=embed_query(question), using=DENSE_VECTOR, limit=limit
            ),
            models.Prefetch(
                query=sparse_query(question), using=SPARSE_VECTOR, limit=limit
            ),
        ],
        # The two score on different scales, so RRF throws the scores
        # away and merges on position instead.
        query=models.FusionQuery(fusion=models.Fusion.RRF),
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
            context=point.payload.get("context", ""),
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
