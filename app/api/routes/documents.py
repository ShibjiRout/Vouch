"""Upload, list, poll, and delete a chat's documents."""

import shutil
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.routes.threads import get_owned_thread
from app.auth.deps import CurrentUser, get_current_user
from app.config import UPLOAD_DIR
from app.db import postgres as db
from app.db.qdrant import delete_document as delete_document_points
from app.logging_config import get_logger
from app.models.schemas import DocumentOut
from app.services.redis_service import enqueue_job
from app.worker.process_pdf import process_pdf_task

router = APIRouter(prefix="/threads/{thread_id}/documents", tags=["documents"])
log = get_logger(__name__)

UPLOAD_DIR.mkdir(exist_ok=True)

DOCUMENT_COLUMNS = (
    "document_id, thread_id, filename, status, chunk_count, "
    "page_count, error_message, created_at"
)

# Same columns, qualified, for the query that joins through threads.
OWNED_COLUMNS = ", ".join(f"d.{name}" for name in DOCUMENT_COLUMNS.split(", "))


def get_owned_document(document_id: UUID, thread_id: UUID, user: CurrentUser) -> dict:
    """Fetch a document scoped to its chat, tenant, and owner, or 404."""
    # The join carries created_by, so guessing both ids gets you a 404
    # unless the chat is yours.
    row = db.fetch_one(
        f"SELECT {OWNED_COLUMNS} FROM documents d "
        "JOIN threads t ON t.thread_id = d.thread_id "
        "WHERE d.document_id = %s AND d.thread_id = %s AND d.tenant_id = %s "
        "AND t.created_by = %s",
        (document_id, thread_id, user.tenant_id, user.user_id),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return row


@router.post("", response_model=DocumentOut, status_code=202)
def upload_document(
    thread_id: UUID,
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
) -> DocumentOut:
    """Accept a PDF and queue it. Returns immediately."""
    get_owned_thread(thread_id, user)

    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    row = db.fetch_one(
        "INSERT INTO documents (thread_id, tenant_id, uploaded_by, filename) "
        f"VALUES (%s, %s, %s, %s) RETURNING {DOCUMENT_COLUMNS}",
        (thread_id, user.tenant_id, user.user_id, file.filename),
    )
    document_id = row["document_id"]

    # Named by document_id, not by the uploaded filename, which is
    # attacker-controlled and could contain path separators.
    path = UPLOAD_DIR / f"{document_id}.pdf"
    with path.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    enqueue_job(
        process_pdf_task,
        str(document_id),
        str(user.tenant_id),
        str(thread_id),
        file.filename,
        str(path),
        job_timeout="15m",
    )

    log.info("queued doc=%s thread=%s", document_id, thread_id)
    return DocumentOut(**row)


@router.get("", response_model=list[DocumentOut])
def list_documents(
    thread_id: UUID,
    user: CurrentUser = Depends(get_current_user),
) -> list[DocumentOut]:
    """List the documents in this chat."""
    get_owned_thread(thread_id, user)

    rows = db.fetch_all(
        f"SELECT {DOCUMENT_COLUMNS} FROM documents "
        "WHERE thread_id = %s AND tenant_id = %s ORDER BY created_at",
        (thread_id, user.tenant_id),
    )
    return [DocumentOut(**row) for row in rows]


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    thread_id: UUID,
    document_id: UUID,
    user: CurrentUser = Depends(get_current_user),
) -> DocumentOut:
    """Poll one document's status."""
    return DocumentOut(**get_owned_document(document_id, thread_id, user))


@router.delete("/{document_id}", status_code=204)
def delete_document(
    thread_id: UUID,
    document_id: UUID,
    user: CurrentUser = Depends(get_current_user),
) -> None:
    """Delete a document and its chunks."""
    # The lookup joins through threads on created_by, so reaching a
    # document at all means the chat is the caller's.
    get_owned_document(document_id, thread_id, user)

    # Qdrant first — the other order leaves orphan chunks.
    delete_document_points(user.tenant_id, document_id)

    # Only still on disk if the worker never read it.
    (UPLOAD_DIR / f"{document_id}.pdf").unlink(missing_ok=True)

    db.execute(
        "DELETE FROM documents WHERE document_id = %s AND tenant_id = %s",
        (document_id, user.tenant_id),
    )
    log.info("document deleted %s thread=%s", document_id, thread_id)
