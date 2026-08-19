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

    reply = model.invoke([SystemMessage(SYSTEM_PROMPT), *messages[-HISTORY_LIMIT:]])

    log.info(
        "agent model=%s searches=%s tool_calls=%s",
        ANSWER_MODEL if searched else CHAT_MODEL,
        searched,
        len(getattr(reply, "tool_calls", []) or []),
    )
    return {"messages": [reply]}
