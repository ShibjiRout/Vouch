"""FastAPI application: startup, routes, static files."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import auth, documents, threads, users
from app.db import postgres as db
from app.db.qdrant import ensure_collection
from app.logging_config import get_logger, setup_logging

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Open the pool, apply the schema, prepare Qdrant."""
    setup_logging()
    db.pool.open()
    db.apply_schema()
    ensure_collection()
    log.info("startup complete")
    yield
    db.pool.close()


app = FastAPI(title="DocLense", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(threads.router)
app.include_router(documents.router)
app.include_router(users.router)


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


# Static files MUST stay last. Mounting "/" catches every route
# declared below it.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
