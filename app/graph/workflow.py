from langgraph.graph import StateGraph, START, END
from app.graph.nodes import (
    GraphState,
    classify_intent,
    generate_direct,
    check_processing,
    retrieve_history,
    retrieve_chunks,
    generate_answer_mini,
    evaluate_answer,
    generate_answer_heavy,
    save_conversation,
    route_intent,
    route_evaluation,
)

def build_graph():
    graph = StateGraph(GraphState)

    graph.add_node("classify_intent", classify_intent)
    graph.add_node("generate_direct", generate_direct)
    graph.add_node("check_processing", check_processing)
    graph.add_node("retrieve_history", retrieve_history)
    graph.add_node("retrieve_chunks", retrieve_chunks)
    graph.add_node("generate_answer_mini", generate_answer_mini)
    graph.add_node("evaluate_answer", evaluate_answer)
    graph.add_node("generate_answer_heavy", generate_answer_heavy)
    graph.add_node("save_conversation", save_conversation)

    graph.add_edge(START, "classify_intent")

    graph.add_conditional_edges(
        "classify_intent",
        route_intent,
        {
            "generate_direct": "generate_direct",
            "check_processing": "retrieve_history",
        }
    )

    # Greeting fast path
    graph.add_edge("generate_direct", "save_conversation")

    # Document question path
    graph.add_edge("retrieve_history", "check_processing")
    graph.add_edge("check_processing", "retrieve_chunks")
    graph.add_edge("retrieve_chunks", "generate_answer_mini")
    graph.add_edge("generate_answer_mini", "evaluate_answer")

    graph.add_conditional_edges(
        "evaluate_answer",
        route_evaluation,
        {
            "save_conversation": "save_conversation",
            "generate_answer_heavy": "generate_answer_heavy",
        }
    )

    graph.add_edge("generate_answer_heavy", "save_conversation")
    graph.add_edge("save_conversation", END)

    return graph.compile()


rag_chain = build_graph()


async def ask_question(case_id: str, question: str) -> dict:
    try:
        result = await rag_chain.ainvoke({
            "case_id": case_id,
            "question": question,
            "context": "",
            "chat_history": "",
            "answer": "",
            "sources": 0,
            "still_processing": False,
            "is_good": False,
            "is_greeting": False,
        })
        return {"answer": result["answer"], "sources": result["sources"]}
    except Exception as e:
        raise Exception(f"Failed to process question: {e}")