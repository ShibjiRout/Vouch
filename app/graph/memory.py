"""Semantic memory, via LangMem.

What the user tells us about themselves, and values read out of the
documents. Both are facts; neither needs a search to be worth keeping -
"hi, my name is Shibji" has nothing to look up and everything to
remember.

Extraction runs in a background thread after the graph has already
returned, so it costs the user nothing. Writing it inline cost 4 to 7
seconds on every turn, and 158 on one, against an answer that was ready
in under three.
"""

from langgraph.store.postgres import PostgresStore
from langmem import ReflectionExecutor, create_memory_store_manager
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

from app.config import CHAT_MODEL, DATABASE_URL
from app.logging_config import get_logger

log = get_logger(__name__)

# How many memories to put in front of the model. More than this and
# the table starts competing with the chunks for attention.
RECALL_LIMIT = 12


class Fact(BaseModel):
    """One thing worth remembering."""

    key: str = Field(description="what it is, e.g. name, or revenue 2025")
    value: str = Field(description="the value exactly as written")
    source: str = Field(description="the filename it was read from, or 'user'")
    page: int = Field(description="the page it came from, or 0 if from the user")


INSTRUCTIONS = """Record only what a later question in this conversation would \
need.

Two kinds of thing qualify:

1. What the user tells you about themselves or their focus - name, role, the \
company or period they care about. Use source "user" and page 0.

2. Values the search results state, but only those bearing on what was asked. \
Use the filename and page of the chunk each came from.

Do not record every value in a table. A table row usually carries the current \
period, the one before, and the change; record the ones the question was about \
and leave the rest.

Copy values character for character. Never calculate, convert or infer. If \
nothing here is worth keeping, record nothing."""

# The store needs autocommit, so it gets its own pool rather than
# sharing the one the API queries with. from_conn_string() hands back a
# context manager whose connection closes as soon as it is collected.
store_pool = ConnectionPool(
    DATABASE_URL,
    min_size=1,
    max_size=5,
    open=False,
    kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
)

# ReflectionExecutor is a factory function, not a class, so neither of
# these is annotated with it.
_store = None
_executor = None


def _ensure():
    """Open the store and the background extractor once."""
    global _store, _executor
    if _executor is None:
        store_pool.open()
        _store = PostgresStore(store_pool)
        _store.setup()
        manager = create_memory_store_manager(
            f"openai:{CHAT_MODEL}",
            schemas=[Fact],
            instructions=INSTRUCTIONS,
            namespace=("facts", "{thread_id}"),
            store=_store,
            enable_inserts=True,
        )
        _executor = ReflectionExecutor(manager, store=_store)
        log.info("memory ready")
    return _store, _executor


def remember_later(messages: list, thread_id: str) -> None:
    """Queue extraction. Returns at once; the work happens after."""
    _, executor = _ensure()
    executor.submit(
        {"messages": messages},
        config={"configurable": {"thread_id": str(thread_id)}},
    )


def recall(thread_id: str, query: str) -> list[Fact]:
    """The facts most relevant to this question."""
    store, _ = _ensure()
    items = store.search(("facts", str(thread_id)), query=query, limit=RECALL_LIMIT)
    facts = []
    for item in items:
        try:
            facts.append(Fact(**item.value["content"]))
        except Exception:
            continue
    return facts


def render(facts: list[Fact]) -> str:
    """The facts as one block for the model to read."""
    if not facts:
        return ""

    lines = []
    for f in facts:
        where = "you were told" if f.source == "user" else f"{f.source}, page {f.page}"
        lines.append(f"- {f.key}: {f.value} [{where}]")

    return (
        "What you already know in this conversation:\n"
        + "\n".join(lines)
        + "\n\nUse a value from here when it answers the question exactly - "
        "same measure, same period, same basis - and do not search for it "
        "again. Anything else needs a search."
    )


def forget(thread_id: str) -> None:
    """Drop a chat's facts. Called when the chat is deleted."""
    store, _ = _ensure()
    namespace = ("facts", str(thread_id))
    for item in store.search(namespace, limit=1000):
        store.delete(namespace, item.key)
    log.info("memory cleared for thread %s", thread_id)
