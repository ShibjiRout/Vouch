"""Clearing everything a chat owns outside its Postgres row."""

from uuid import UUID

from app.config import UPLOAD_DIR
from app.db import postgres as db
from app.db.qdrant import delete_thread as delete_thread_points
from app.graph.builder import delete_checkpoints
from app.graph.memory import forget
from app.logging_config import get_logger

log = get_logger(__name__)


def purge_thread(tenant_id: UUID, thread_id: UUID) -> None:
    """Clear a chat's chunks, messages, facts, and unread uploads.

    Four stores hold a chat's data and only one of them is Postgres.
    ON DELETE CASCADE reaches the document rows and nothing else, so
    everything here runs before the caller deletes the thread. If one
    step fails the row survives and the delete can be retried; the
    other order leaves data with nothing pointing at it.
    """
    delete_thread_points(tenant_id, thread_id)
    delete_checkpoints(str(thread_id))
    forget(str(thread_id))

    # A file is only still here if the worker never got to it.
    rows = db.fetch_all(
        "SELECT document_id FROM documents WHERE thread_id = %s AND tenant_id = %s",
        (thread_id, tenant_id),
    )
    for row in rows:
        (UPLOAD_DIR / f"{row['document_id']}.pdf").unlink(missing_ok=True)

    log.info("purged thread %s documents=%s", thread_id, len(rows))
