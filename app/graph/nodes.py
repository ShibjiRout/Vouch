"""The agent node."""

from langchain_core.messages import SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import MessagesState

from app.config import (
    ANSWER_MODEL,
    CHAT_MODEL,
    MAX_TOOL_ITERATIONS,
    OPENAI_API_KEY,
)
from app.graph.prompts import SYSTEM_PROMPT
from app.graph.tools import search_documents
from app.logging_config import get_logger

log = get_logger(__name__)

# How many past messages reach the model. The checkpointer keeps the
# full history; only the tail is sent.
HISTORY_LIMIT = 12


def _recent(messages: list) -> list:
    """The tail of the conversation, carrying only this turn's chunks.

    Older tool results are dropped, not trimmed. Keeping them leaves
    stale chunks from previous questions in context, and the model
    answers by blending figures across them - it invented an operating
    profit that appears nowhere in the document while the correct
    chunk sat at rank one.

    Dropping a tool message also means dropping the tool_calls that
    requested it, or the request is left dangling and rejected.
    """
    starts = [i for i, m in enumerate(messages) if m.type == "human"]
    if not starts:
        return messages[-HISTORY_LIMIT:]

    history, current = messages[: starts[-1]], messages[starts[-1] :]

    kept = [
        m
        for m in history
        if m.type == "human"
        or (m.type == "ai" and m.content and not getattr(m, "tool_calls", None))
    ]
    return kept[-HISTORY_LIMIT:] + current


_router = ChatOpenAI(
    model=CHAT_MODEL, temperature=0, api_key=OPENAI_API_KEY
).bind_tools([search_documents])

_answerer = ChatOpenAI(
    model=ANSWER_MODEL, temperature=0, api_key=OPENAI_API_KEY
).bind_tools([search_documents])


def _searches_so_far(messages: list) -> int:
    """How many times the tool has already run this turn."""
    return sum(1 for message in messages if isinstance(message, ToolMessage))


def agent(state: MessagesState) -> dict:
    """Decide whether to search, or write the final answer."""
    messages = state["messages"]
    searched = _searches_so_far(messages)

    # Model by path, not by a grade of a previous answer. Routing and
    # small talk are cheap; a misread table is not.
    model = _answerer if searched else _router

    # Once the cap is reached the tool is taken away, so the model has
    # to answer with what it has instead of looping.
    if searched >= MAX_TOOL_ITERATIONS:
        model = ChatOpenAI(model=ANSWER_MODEL, temperature=0, api_key=OPENAI_API_KEY)

    reply = model.invoke([SystemMessage(SYSTEM_PROMPT), *_recent(messages)])

    log.info(
        "agent model=%s searches=%s tool_calls=%s",
        ANSWER_MODEL if searched else CHAT_MODEL,
        searched,
        len(getattr(reply, "tool_calls", []) or []),
    )
    return {"messages": [reply]}
