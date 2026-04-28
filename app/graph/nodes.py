from typing import TypedDict, Literal
from app.graph.prompts import (
    SYSTEM_PROMPT, RAG_PROMPT, EVAL_SYSTEM_PROMPT,
    llm_mini, llm_heavy, evaluator_llm,
    INTENT_PROMPT, intent_classifier
)
from app.services.embedding_service import get_embedding
from app.services.qdrant_service import search_chunks
from app.services.mongo_service import store_message, get_chat_history
from app.services.redis_service import is_processing

# ----------------------------
# State
# ----------------------------
class GraphState(TypedDict):
    case_id: str
    question: str
    context: str
    chat_history: str
    answer: str
    sources: int
    still_processing: bool
    is_good: bool
    is_greeting: bool


# ----------------------------
# Nodes
# ----------------------------
async def classify_intent(state: GraphState) -> GraphState:
    try:
        messages = [
            {"role": "system", "content": INTENT_PROMPT},
            {"role": "user", "content": state["question"]}
        ]
        result = await intent_classifier.ainvoke(messages)
        return {"is_greeting": result.intent == "chat"}
    except Exception:
        return {"is_greeting": False}


async def generate_direct(state: GraphState) -> GraphState:
    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": state["question"]}
        ]
        response = await llm_mini.ainvoke(messages)
        return {"answer": response.content, "sources": 0}
    except Exception as e:
        raise Exception(f"Failed to generate direct response: {e}")


async def check_processing(state: GraphState) -> GraphState:
    try:
        processing = is_processing(state["case_id"])
        return {"still_processing": processing}
    except Exception as e:
        raise Exception(f"Failed to check processing status: {e}")


async def retrieve_history(state: GraphState) -> GraphState:
    try:
        history = await get_chat_history(state["case_id"])
        formatted = ""
        for msg in history:
            role = "User" if msg["role"] == "user" else "Assistant"
            formatted += f"{role}: {msg['content']}\n"
        return {"chat_history": formatted}
    except Exception as e:
        raise Exception(f"Failed to retrieve chat history: {e}")


async def retrieve_chunks(state: GraphState) -> GraphState:
    try:
        if state["still_processing"]:
            return {"context": "", "sources": 0}

        query_vector = get_embedding(state["question"])
        results = search_chunks(state["case_id"], query_vector, top_k=15)

        if not results:
            return {"context": "", "sources": 0}

        context = "\n\n---\n\n".join([r["text"] for r in results])
        return {"context": context, "sources": len(results)}
    except Exception as e:
        raise Exception(f"Failed to retrieve chunks: {e}")


async def generate_answer_mini(state: GraphState) -> GraphState:
    try:
        has_context = state["context"].strip() != ""

        if not has_context and not state["still_processing"]:
            return {"answer": "No documents have been uploaded for this case ID yet. Please upload a PDF first."}

        if not has_context and state["still_processing"]:
            return {"answer": "Your document is still being processed. Please wait a moment and try again."}

        processing_note = ""
        if state["still_processing"]:
            processing_note = "\n\nNote: A new document is currently being processed. This answer is based on previously uploaded documents only."

        prompt = RAG_PROMPT.format(
            context=state["context"],
            chat_history=state["chat_history"],
            question=state["question"]
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]

        response = await llm_mini.ainvoke(messages)
        return {"answer": response.content + processing_note}
    except Exception as e:
        raise Exception(f"Failed to generate answer with mini model: {e}")


async def evaluate_answer(state: GraphState) -> GraphState:
    try:
        skip_phrases = [
            "No documents have been uploaded",
            "still being processed",
            "don't have sufficient information",
        ]
        if any(phrase in state["answer"] for phrase in skip_phrases):
            return {"is_good": True}

        # Truncate context to first 2000 chars — enough for evaluation, avoids token overuse
        truncated_context = state["context"][:2000]

        eval_prompt = f"""## Document Context (source of truth)
{truncated_context}

## User Question
{state["question"]}

## Assistant Answer
{state["answer"]}

Evaluate the Assistant Answer against all four criteria: grounded, accurate, relevant, and complete."""

        messages = [
            {"role": "system", "content": EVAL_SYSTEM_PROMPT},
            {"role": "user", "content": eval_prompt}
        ]

        result = await evaluator_llm.ainvoke(messages)
        return {"is_good": result.is_good}
    except Exception as e:
        raise Exception(f"Failed to evaluate answer: {e}")


async def generate_answer_heavy(state: GraphState) -> GraphState:
    try:
        print("\n[ROUTER] Mini model failed. Falling back to GPT-4o...\n")

        processing_note = ""
        if state["still_processing"]:
            processing_note = "\n\nNote: A new document is currently being processed. This answer is based on previously uploaded documents only."

        prompt = RAG_PROMPT.format(
            context=state["context"],
            chat_history=state["chat_history"],
            question=state["question"]
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]

        response = await llm_heavy.ainvoke(messages)
        return {"answer": response.content + processing_note}
    except Exception as e:
        raise Exception(f"Failed to generate answer with heavy model: {e}")


async def save_conversation(state: GraphState) -> GraphState:
    try:
        await store_message(state["case_id"], "user", state["question"])
        await store_message(state["case_id"], "assistant", state["answer"])
        return {}
    except Exception as e:
        raise Exception(f"Failed to save conversation: {e}")


def route_intent(state: GraphState) -> Literal["generate_direct", "check_processing"]:
    return "generate_direct" if state["is_greeting"] else "check_processing"


def route_evaluation(state: GraphState) -> Literal["save_conversation", "generate_answer_heavy"]:
    if state["is_good"]:
        return "save_conversation"
    return "generate_answer_heavy"
