"""RQ task: read a PDF, chunk it, embed it, store it."""

import os
from uuid import UUID

from app.db import postgres as db
from app.db.qdrant import upsert_chunks
from app.ingest.chunk import chunk_blocks
from app.ingest.embed import embed_texts
from app.ingest.extract import extract
from app.logging_config import get_logger, setup_logging

log = get_logger(__name__)


def _set_status(document_id: UUID, tenant_id: UUID, status: str, **fields) -> None:
    """Move a document to a new status, scoped to its tenant."""
    # Column names come from keyword arguments written in this file,
    # never from user input. Values are always parameterised.
    columns = ", ".join(f"{key} = %s" for key in fields)
    sets = f"status = %s{', ' + columns if columns else ''}"
    db.execute(
        f"UPDATE documents SET {sets} "
        "WHERE document_id = %s AND tenant_id = %s",
        (status, *fields.values(), document_id, tenant_id),
    )


def process_pdf_task(
    document_id: str,
    tenant_id: str,
    thread_id: str,
    filename: str,
    file_path: str,
) -> None:
    """Take one uploaded PDF from pending to ready."""
    setup_logging()
    db.pool.open()

    document_id = UUID(document_id)
    tenant_id = UUID(tenant_id)
    thread_id = UUID(thread_id)

    try:
        _set_status(document_id, tenant_id, "processing")
        log.info("processing %s doc=%s", filename, document_id)

        blocks, page_count = extract(file_path)
        chunks = chunk_blocks(blocks)

        if not chunks:
            # No text at all almost always means a scanned image.
            raise ValueError("Could not read this PDF, it may be a scan")

        vectors = embed_texts([chunk.text for chunk in chunks])

        upsert_chunks(
            tenant_id=tenant_id,
            thread_id=thread_id,
            document_id=document_id,
            filename=filename,
            chunks=chunks,
            vectors=vectors,
        )

        _set_status(
            document_id,
            tenant_id,
            "ready",
            chunk_count=len(chunks),
            page_count=page_count,
            error_message=None,
        )
        log.info(
            "ready doc=%s pages=%s chunks=%s tables=%s",
            document_id,
            page_count,
            len(chunks),
            sum(1 for c in chunks if c.chunk_type == "table"),
        )

    except Exception as exc:
        # The message reaches the user, so it has to say what to do.
        log.exception("failed doc=%s", document_id)
        _set_status(document_id, tenant_id, "failed", error_message=str(exc)[:500])
        raise

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
