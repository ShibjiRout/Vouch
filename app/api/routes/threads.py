"""Create, list, and delete chats."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.deps import CurrentUser, get_current_user
from app.db import postgres as db
from app.db.qdrant import delete_thread as delete_thread_points
from app.graph.memory import forget
from app.logging_config import get_logger
from app.models.schemas import ThreadCreate, ThreadOut

router = APIRouter(prefix="/threads", tags=["threads"])
log = get_logger(__name__)


def get_owned_thread(thread_id: UUID, user: CurrentUser) -> dict:
    """Fetch a thread scoped to the caller's tenant, or 404."""
    row = db.fetch_one(
        "SELECT thread_id, tenant_id, created_by, title, created_at, last_msg_at "
        "FROM threads WHERE thread_id = %s AND tenant_id = %s",
        (thread_id, user.tenant_id),
    )
    if row is None:
        # 404 rather than 403 — a 403 would confirm the id was real.
        raise HTTPException(status_code=404, detail="Thread not found")
    return row


@router.post("", response_model=ThreadOut, status_code=201)
def create_thread(
    body: ThreadCreate,
    user: CurrentUser = Depends(get_current_user),
) -> ThreadOut:
    """Start a new chat."""
    row = db.fetch_one(
        "INSERT INTO threads (tenant_id, created_by, title) VALUES (%s, %s, %s) "
        "RETURNING thread_id, title, created_at, last_msg_at",
        (user.tenant_id, user.user_id, body.title),
    )
    log.info("thread created %s tenant=%s", row["thread_id"], user.tenant_id)
    return ThreadOut(**row)


@router.get("", response_model=list[ThreadOut])
def list_threads(user: CurrentUser = Depends(get_current_user)) -> list[ThreadOut]:
    """List this tenant's chats, most recently used first."""
    rows = db.fetch_all(
        "SELECT thread_id, title, created_at, last_msg_at FROM threads "
        "WHERE tenant_id = %s "
        "ORDER BY last_msg_at DESC NULLS LAST, created_at DESC",
        (user.tenant_id,),
    )
    return [ThreadOut(**row) for row in rows]


@router.get("/{thread_id}", response_model=ThreadOut)
def get_thread(
    thread_id: UUID,
    user: CurrentUser = Depends(get_current_user),
) -> ThreadOut:
    """Return one chat."""
    return ThreadOut(**get_owned_thread(thread_id, user))


@router.delete("/{thread_id}", status_code=204)
def delete_thread(
    thread_id: UUID,
    user: CurrentUser = Depends(get_current_user),
) -> None:
    """Delete a chat, its documents, and their chunks."""
    thread = get_owned_thread(thread_id, user)

    # Members may only delete their own chats. Admins may delete any
    # chat in the tenant — but never another tenant's, which the
    # scoped lookup above already prevents.
    if user.role != "admin" and thread["created_by"] != user.user_id:
        raise HTTPException(status_code=403, detail="Not allowed")

    # Everything outside Postgres goes first. If one of these fails the
    # row survives and the delete can be retried; the other order
    # leaves chunks and facts with nothing pointing at them.
    delete_thread_points(user.tenant_id, thread_id)
    forget(str(thread_id))

    # ON DELETE CASCADE removes the document rows.
    db.execute(
        "DELETE FROM threads WHERE thread_id = %s AND tenant_id = %s",
        (thread_id, user.tenant_id),
    )
    log.info("thread deleted %s tenant=%s", thread_id, user.tenant_id)
