"""Graph construction and the chat checkpointer."""

from langchain_core.messages import AIMessage
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import DATABASE_URL, MAX_TOOL_ITERATIONS
from app.graph.nodes import _searches_so_far, agent, search
from app.logging_config import get_logger

log = get_logger(__name__)

# PostgresSaver needs autocommit, so it gets its own pool rather than
# sharing the one the API queries with.
checkpoint_pool = ConnectionPool(
    DATABASE_URL,
    min_size=1,
    max_size=5,
    open=False,
    kwargs={"autocommit": True, "row_factory": dict_row},
)

_graph = None


def route(state: MessagesState) -> str:
    """Search if the agent asked to, otherwise stop.

    The cap is counted per question. Counting the whole thread would
    stop every search after the third one in a conversation.
    """
    last = state["messages"][-1]
    wants_tool = isinstance(last, AIMessage) and bool(last.tool_calls)
    searched = _searches_so_far(state["messages"])

    return "search" if wants_tool and searched < MAX_TOOL_ITERATIONS else END


def build() -> object:
    """Two nodes, one loop. Memory is written outside the graph."""
    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent)
    graph.add_node("search", search)

    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route, {"search": "search", END: END})
    graph.add_edge("search", "agent")

    checkpointer = PostgresSaver(checkpoint_pool)
    checkpointer.setup()
    return graph.compile(checkpointer=checkpointer)


def get_graph():
    """Build the graph once, on first use."""
    global _graph
    if _graph is None:
        checkpoint_pool.open()
        _graph = build()
        log.info("graph ready")
    return _graph
