"""FastAPI application: startup and routes.

The API serves no pages. The frontend is a separate deployment on its
own host, which is why CORS below is not decoration.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, chat, documents, threads, users
from app.config import ALLOWED_ORIGINS
from app.db import postgres as db
from app.db.qdrant import ensure_collection
from app.retrieval.rerank import warm
from app.logging_config import get_logger, setup_logging

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Open the pool, apply the schema, prepare Qdrant."""
    setup_logging()
    db.pool.open()
    db.apply_schema()
    ensure_collection()
    warm()
    log.info("startup complete")
    yield
    db.pool.close()


app = FastAPI(title="Vouch", version="2.0.0", lifespan=lifespan)

# The frontend is on another host, so the browser will not send the
# Authorization header without this. Name the origins in .env rather
# than leaving "*" — with credentials that is a hole, and it is also
# the one setting that breaks silently in the browser and nowhere else.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(threads.router)
app.include_router(documents.router)
app.include_router(users.router)
app.include_router(chat.router)


@app.get("/health")
def health() -> dict:
    """Report whether the dependencies are reachable."""
    checks = {"postgres": False, "qdrant": False}
    try:
        db.fetch_one("SELECT 1 AS ok")
        checks["postgres"] = True
    except Exception:
        log.exception("postgres health check failed")
    try:
        ensure_collection()
        checks["qdrant"] = True
    except Exception:
        log.exception("qdrant health check failed")

    return {"status": "ok" if all(checks.values()) else "degraded", **checks}
