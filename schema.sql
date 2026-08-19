-- DocLense — Postgres schema
-- Documents are scoped to chats. thread_id is the isolation key.
-- LangGraph PostgresSaver creates its own checkpoint tables
-- separately via .setup() — do not hand-write those.

-- 1. THREADS -----------------------------------------------------
-- One row per conversation. This is the unit of ownership:
-- a thread owns its documents, and every Qdrant query filters
-- on thread_id. The messages themselves live in the checkpointer,
-- keyed by this same thread_id.
CREATE TABLE IF NOT EXISTS threads (
    thread_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_msg_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_threads_recent ON threads(last_msg_at DESC NULLS LAST);

-- 2. DOCUMENTS ---------------------------------------------------
-- One row per uploaded PDF, belonging to exactly one thread.
-- Chunks live in Qdrant keyed by document_id and thread_id.
--
-- ON DELETE CASCADE removes the rows when a thread goes, but the
-- Qdrant points must be deleted first, in code. See ARCHITECTURE §9.
CREATE TABLE IF NOT EXISTS documents (
    document_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id     UUID NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
    filename      TEXT NOT NULL,
    page_count    INTEGER,
    status        TEXT NOT NULL DEFAULT 'pending',
    chunk_count   INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_status CHECK (status IN ('pending','processing','ready','failed'))
);

CREATE INDEX IF NOT EXISTS idx_documents_thread ON documents(thread_id, created_at DESC);
