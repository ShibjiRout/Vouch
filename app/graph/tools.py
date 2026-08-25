"""The one tool the agent can call."""

import re
from uuid import UUID

from langchain_core.tools import tool
from langgraph.config import get_config

from app.config import FINAL_K, MIN_SCORE
from app.db import postgres as db
from app.logging_config import get_logger
from app.retrieval.hybrid import Hit, search
from app.retrieval.rerank import rerank

log = get_logger(__name__)

CHUNK_RE = re.compile(
    r'<chunk filename="(?P<filename>[^"]*)" page="(?P<page>\d+)">\n'
    r"(?P<text>.*?)\n</chunk>",
    re.S,
)


def still_reading(tenant_id: UUID, thread_id: UUID) -> int:
    """How many of this chat's documents have not finished processing."""
    row = db.fetch_one(
        "SELECT count(*) AS n FROM documents "
        "WHERE thread_id = %s AND tenant_id = %s "
        "AND status IN ('pending','processing')",
        (thread_id, tenant_id),
    )
    return row["n"] if row else 0


def no_results(tenant_id: UUID, thread_id: UUID) -> str:
    """Nothing found - and whether that is because a PDF is still being read.

    The prompt has a separate refusal for a document that is not ready
    yet, but nothing used to tell the model which case it was in, so it
    guessed. This is the only place that knows.
    """
    pending = still_reading(tenant_id, thread_id)
    if pending:
        return (
            f"NO_RESULTS_STILL_PROCESSING: {pending} document"
            f"{'s are' if pending > 1 else ' is'} still being read. "
            "Anything in them cannot be searched yet."
        )
    return "NO_RESULTS"


def format_hits(hits: list[Hit]) -> str:
    """Render chunks as delimited blocks the agent can cite."""
    if not hits:
        return "NO_RESULTS"

    return "\n\n".join(
        f'<chunk filename="{hit.filename}" page="{hit.page}">\n'
        f"{hit.text}\n"
        f"</chunk>"
        for hit in hits
    )


def parse_chunks(rendered: str) -> list[dict]:
    """Read back what format_hits wrote, for the API's citations."""
    return [
        {
            "filename": match.group("filename"),
            "page": int(match.group("page")),
            "text": match.group("text"),
        }
        for match in CHUNK_RE.finditer(rendered)
    ]


@tool
def search_documents(query: str) -> str:
    """Search this chat's uploaded documents. Use for any question about their content."""
    # Scope keys come from the graph config, never from the model's
    # arguments — so nothing the model writes can widen the search.
    configurable = get_config()["configurable"]
    tenant_id = UUID(str(configurable["tenant_id"]))
    thread_id = UUID(str(configurable["thread_id"]))

    candidates = search(query, tenant_id, thread_id)
    hits = rerank(query, candidates, top_k=FINAL_K)

    # Weak results are worse than none: answering from them produces a
    # confident wrong figure, which is the failure this cannot afford.
    if hits and hits[0].score < MIN_SCORE:
        log.info(
            "refused thread=%s top=%.2f below MIN_SCORE=%s",
            thread_id,
            hits[0].score,
            MIN_SCORE,
        )
        return no_results(tenant_id, thread_id)

    if not hits:
        return no_results(tenant_id, thread_id)

    return format_hits(hits)
