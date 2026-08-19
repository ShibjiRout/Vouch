"""The one tool the agent can call."""

from uuid import UUID

from langchain_core.tools import tool
from langgraph.config import get_config

from app.config import FINAL_K
from app.retrieval.hybrid import Hit, search


def format_hits(hits: list[Hit]) -> str:
    """Render chunks as delimited blocks the agent can cite."""
    if not hits:
        return "NO_RESULTS"

    blocks = []
    for hit in hits:
        blocks.append(
            f"<chunk filename=\"{hit.filename}\" page=\"{hit.page}\">\n"
            f"{hit.text}\n"
            f"</chunk>"
        )
    return "\n\n".join(blocks)


@tool
def search_documents(query: str) -> str:
    """Search this chat's uploaded documents. Use for any question about their content."""
    # Scope keys come from the graph config, never from the model's
    # arguments — so nothing the model writes can widen the search.
    configurable = get_config()["configurable"]
    tenant_id = UUID(str(configurable["tenant_id"]))
    thread_id = UUID(str(configurable["thread_id"]))

    hits = search(query, tenant_id, thread_id)
    return format_hits(hits[:FINAL_K])
