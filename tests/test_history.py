"""Trimming must never orphan a tool message."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.graph.nodes import _recent


def conversation(turns: int) -> list:
    """A history of question, tool call, tool reply, answer."""
    messages = []
    for i in range(turns):
        messages += [
            HumanMessage(f"q{i}"),
            AIMessage(
                "",
                tool_calls=[
                    {"name": "search_documents", "args": {"query": "x"}, "id": f"t{i}"}
                ],
            ),
            ToolMessage("chunks", tool_call_id=f"t{i}"),
            AIMessage(f"answer {i}"),
        ]
    return messages


def orphans(messages: list) -> list[int]:
    """Tool messages with no tool_calls immediately before them."""
    return [
        i
        for i, m in enumerate(messages)
        if m.type == "tool"
        and (i == 0 or not getattr(messages[i - 1], "tool_calls", None))
    ]


def test_long_history_leaves_no_orphan_tool_message():
    """A plain slice would cut between a tool call and its reply."""
    trimmed = _recent(conversation(5))
    assert orphans(trimmed) == []
    assert trimmed[0].type == "human"


def test_trimming_bounds_the_window():
    """12 past messages, plus the current turn kept whole.

    The fixture ends on a finished turn - question, tool call, chunks,
    answer - so the current part is 4. In the graph the answer does not
    exist yet when trimming runs, so it is 3 there.
    """
    trimmed = _recent(conversation(10))
    assert len(trimmed) <= 12 + 4


def test_older_tool_results_are_dropped():
    """Stale chunks in context make the model blend figures across turns."""
    trimmed = _recent(conversation(5))
    start = max(i for i, m in enumerate(trimmed) if m.type == "human")

    assert not [m for m in trimmed[:start] if m.type == "tool"]
    assert not [m for m in trimmed[:start] if getattr(m, "tool_calls", None)]
    assert [m for m in trimmed[start:] if m.type == "tool"]


def test_short_history_is_untouched():
    messages = [HumanMessage("hello"), AIMessage("hi")]
    assert len(_recent(messages)) == 2
