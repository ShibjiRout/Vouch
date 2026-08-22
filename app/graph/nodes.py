"""The graph nodes.

Two nodes. `agent` decides whether to search and writes the answer,
`search` fetches chunks.

Memory is not a node. Extraction used to run as one, and it cost four
to seven seconds on every turn - once a hundred and fifty-eight -
against an answer that was ready in under three. It now runs in a
background thread after the graph has returned, so the user never waits
for it. See app/graph/memory.py.
"""

from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import MessagesState

from app.config import ANSWER_MODEL, MAX_TOOL_ITERATIONS, OPENAI_API_KEY
from app.graph.memory import recall, render
from app.graph.prompts import SYSTEM_PROMPT
from app.graph.tools import search_documents
from app.logging_config import get_logger

log = get_logger(__name__)

# One previous exchange. Enough for "and what about last year", short
# enough not to look like a template the model should continue.
HISTORY_LIMIT = 2

_llm = ChatOpenAI(model=ANSWER_MODEL, temperature=0, api_key=OPENAI_API_KEY)
_with_tool = _llm.bind_tools([search_documents])


def _recent(messages: list) -> list:
    """The current turn, and the one exchange before it.

    Older tool results are dropped rather than trimmed. Keeping them
    leaves stale chunks from earlier questions in context and the model
    blends figures across them. Dropping a tool message also means
    dropping the tool_calls that asked for it, or the request dangles
    and the API rejects it.
    """
    starts = [i for i, m in enumerate(messages) if m.type == "human"]
    if not starts:
        return messages

    history, current = messages[: starts[-1]], messages[starts[-1] :]

    kept = [
        m
        for m in history
        if m.type == "human"
        or (m.type == "ai" and m.content and not getattr(m, "tool_calls", None))
    ]
    return kept[-HISTORY_LIMIT:] + current


def _searches_so_far(messages: list) -> int:
    """How many searches have run since the current question.

    Counting the whole conversation instead withdraws the tool for good
    once a thread has run MAX_TOOL_ITERATIONS searches in total. The
    model then says it needs to search while having nothing to call.
    """
    starts = [i for i, m in enumerate(messages) if m.type == "human"]
    turn = messages[starts[-1] :] if starts else messages
    return sum(1 for message in turn if isinstance(message, ToolMessage))


def _question(messages: list) -> str:
    """The question being answered."""
    for message in reversed(messages):
        if message.type == "human":
            return str(message.content)
    return ""


def agent(state: MessagesState, config: RunnableConfig) -> dict:
    """Decide whether to search, or write the answer."""
    messages = state["messages"]
    searched = _searches_so_far(messages)

    # At the cap the tool is withheld, so the model answers with what it
    # has rather than looping.
    model = _llm if searched >= MAX_TOOL_ITERATIONS else _with_tool

    prompt = [SystemMessage(SYSTEM_PROMPT)]
    thread_id = config["configurable"]["thread_id"]
    known = render(recall(thread_id, _question(messages)))
    if known:
        prompt.append(SystemMessage(known))
    prompt += _recent(messages)

    reply = model.invoke(prompt)

    log.info(
        "agent searches=%s recalled=%s tool_calls=%s",
        searched,
        bool(known),
        len(getattr(reply, "tool_calls", []) or []),
    )
    return {"messages": [reply]}


def search(state: MessagesState) -> dict:
    """Fetch chunks for whatever the agent asked."""
    last = state["messages"][-1]
    return {
        "messages": [
            ToolMessage(
                content=search_documents.invoke(call["args"]),
                tool_call_id=call["id"],
            )
            for call in last.tool_calls
        ]
    }
