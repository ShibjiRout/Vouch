"""Send a message to a chat, and read its history."""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.routes.threads import get_owned_thread
from app.auth.deps import CurrentUser, get_current_user
from app.db import postgres as db
from app.graph.builder import get_graph
from app.graph.tools import parse_chunks
from app.logging_config import get_logger
from app.models.schemas import ChatRequest, ChatResponse, MessageOut, Source

router = APIRouter(prefix="/threads/{thread_id}", tags=["chat"])
log = get_logger(__name__)


def _scope(thread_id: UUID, user: CurrentUser) -> dict:
    """Config the graph runs under. Never part of the message state."""
    return {
        "configurable": {
            "thread_id": str(thread_id),
            "tenant_id": str(user.tenant_id),
        }
    }


def _sources_from(messages: list) -> list[Source]:
    """Collect the chunks the agent was shown, newest search first."""
    seen: set[tuple] = set()
    sources: list[Source] = []
    for message in messages:
        if message.type != "tool":
            continue
        for chunk in parse_chunks(str(message.content)):
            key = (chunk["filename"], chunk["page"], chunk["text"][:60])
            if key not in seen:
                seen.add(key)
                sources.append(Source(**chunk))
    return sources


@router.post("/chat", response_model=ChatResponse)
def chat(
    thread_id: UUID,
    body: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
) -> ChatResponse:
    """Ask a question and get an answer with its citations."""
    get_owned_thread(thread_id, user)

    result = get_graph().invoke(
        {"messages": [{"role": "user", "content": body.message}]},
        config=_scope(thread_id, user),
    )

    messages = result["messages"]
    answer = messages[-1].content

    # Only the chunks from this turn, not every search in the thread.
    turn = messages[_last_user_index(messages) :]
    sources = _sources_from(turn)

    db.execute(
        "UPDATE threads SET last_msg_at = now() "
        "WHERE thread_id = %s AND tenant_id = %s",
        (thread_id, user.tenant_id),
    )

    log.info("chat thread=%s sources=%s", thread_id, len(sources))
    return ChatResponse(answer=answer, sources=sources)


def _last_user_index(messages: list) -> int:
    """Where the current turn started."""
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].type == "human":
            return index
    return 0


@router.get("/messages", response_model=list[MessageOut])
def messages(
    thread_id: UUID,
    user: CurrentUser = Depends(get_current_user),
) -> list[MessageOut]:
    """Return the conversation so far."""
    get_owned_thread(thread_id, user)

    state = get_graph().get_state(_scope(thread_id, user))
    history = state.values.get("messages", []) if state.values else []

    out: list[MessageOut] = []
    pending: list[Source] = []

    for message in history:
        if message.type == "tool":
            pending.extend(_sources_from([message]))
        elif message.type == "human":
            out.append(MessageOut(role="user", content=message.content))
            pending = []
        elif message.type == "ai" and message.content:
            out.append(
                MessageOut(role="assistant", content=message.content, sources=pending)
            )
            pending = []

    return out
