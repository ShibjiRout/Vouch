-- DocLense — Postgres schema
-- tenant_id is the ownership key. Documents belong to a chat.
-- LangGraph PostgresSaver creates its own checkpoint tables
-- separately via .setup() — do not hand-write those.

CREATE EXTENSION IF NOT EXISTS citext;

-- 1. TENANTS -----------------------------------------------------
-- The unit of data ownership. Everything cascades from here.
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. USERS -------------------------------------------------------
-- email is UNIQUE. A duplicate signup fails on this constraint —
-- do not SELECT first to check. See ARCHITECTURE §10.
CREATE TABLE IF NOT EXISTS users (
    user_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    email          CITEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    role           TEXT NOT NULL DEFAULT 'member',
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at  TIMESTAMPTZ,
    CONSTRAINT chk_role CHECK (role IN ('admin','member'))
);

CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);

-- 3. THREADS -----------------------------------------------------
-- One row per conversation. A thread owns its documents.
-- The messages live in the checkpointer, keyed by this thread_id.
CREATE TABLE IF NOT EXISTS threads (
    thread_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    created_by    UUID REFERENCES users(user_id) ON DELETE SET NULL,
    title         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_msg_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_threads_tenant ON threads(tenant_id, last_msg_at DESC NULLS LAST);

-- 4. DOCUMENTS ---------------------------------------------------
-- One row per uploaded PDF, belonging to exactly one thread.
-- tenant_id is denormalised onto the row so a document can be
-- scoped without joining through threads.
--
-- ON DELETE CASCADE removes the rows when a thread goes, but the
-- Qdrant points must be deleted first, in code. See ARCHITECTURE §9.
CREATE TABLE IF NOT EXISTS documents (
    document_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id     UUID NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
    tenant_id     UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    uploaded_by   UUID REFERENCES users(user_id) ON DELETE SET NULL,
    filename      TEXT NOT NULL,
    page_count    INTEGER,
    status        TEXT NOT NULL DEFAULT 'pending',
    chunk_count   INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_status CHECK (status IN ('pending','processing','ready','failed'))
);

CREATE INDEX IF NOT EXISTS idx_documents_thread ON documents(thread_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_tenant ON documents(tenant_id);
