"""Rerank retrieved chunks with a local cross-encoder.

Search compares numbers computed before the question existed. The
cross-encoder reads the question and the chunk together, so nothing
can be precomputed and it runs once per candidate — accurate, slower,
only affordable on the shortlist.

Everything goes through rerank(). Swapping the model, or moving to a
hosted service, is then a change to this file alone.
"""

from fastembed.rerank.cross_encoder import TextCrossEncoder

from app.config import FINAL_K, RERANK_MODEL
from app.logging_config import get_logger
from app.retrieval.hybrid import Hit

log = get_logger(__name__)

_model: TextCrossEncoder | None = None


def _encoder() -> TextCrossEncoder:
    """Load on first use; the model file is about 90MB."""
    global _model
    if _model is None:
        _model = TextCrossEncoder(model_name=RERANK_MODEL)
    return _model


def warm() -> None:
    """Download and load at startup, not on a user's question."""
    _encoder().rerank("warm", ["warm"])


def rerank(question: str, hits: list[Hit], top_k: int = FINAL_K) -> list[Hit]:
    """Score each chunk against the question, keep the best."""
    if not hits:
        return []

    scores = list(_encoder().rerank(question, [hit.text for hit in hits]))

    ranked = sorted(zip(scores, hits), key=lambda pair: pair[0], reverse=True)
    best = [
        Hit(
            text=hit.text,
            filename=hit.filename,
            page=hit.page,
            document_id=hit.document_id,
            chunk_type=hit.chunk_type,
            # The cross-encoder's scale, not the search scale. Raw
            # logits, roughly -11 to +11.
            score=float(score),
        )
        for score, hit in ranked[:top_k]
    ]

    log.info(
        "rerank candidates=%s kept=%s top=%.3f",
        len(hits),
        len(best),
        best[0].score if best else 0.0,
    )
    return best
