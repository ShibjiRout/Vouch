"""Answer every question in a Q&A file and save what retrieval returned.

This scores nothing. It produces the record a judge needs: the question,
the written answer, the answer the system gave, and the exact text of the
five chunks it was given.

Unlike run_eval.py, no question is skipped. A question whose answer is
prose - an accounting policy, a notice period - is one a real user asks,
and dropping it hides how the system handles it.

    uv run eval/run_answers.py --thread <uuid> \
        --questions dominos-financial-qa-v2.md \
        --out metrics/answers_dominos.json
"""

import argparse
import json
import os
import pathlib
import re
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import app  # noqa: E402
from app.auth.jwt import create_access_token  # noqa: E402
from app.db import postgres as db  # noqa: E402
from app.graph.builder import get_graph  # noqa: E402
from app.retrieval.hybrid import search  # noqa: E402
from app.retrieval.rerank import rerank  # noqa: E402

TEST_DATA = pathlib.Path(__file__).resolve().parents[1] / "test_data"

# Both heading styles used across the question files.
QUESTION_RE = re.compile(r"^#{3,4}\s*(?:Q)?\d+[:.]\s*(.+?)\s*$", re.M)
ANSWER_RE = re.compile(r"^\*\*Answer:\*\*\s*(.+?)\s*$", re.M)


def load(path: pathlib.Path) -> list[dict]:
    """Pair each question with the answer written beside it."""
    text = path.read_text(encoding="utf-8")
    questions = QUESTION_RE.findall(text)
    answers = ANSWER_RE.findall(text)
    if len(questions) != len(answers):
        print(f"warning: {len(questions)} questions, {len(answers)} answers")
    return [{"question": q, "reference": a} for q, a in zip(questions, answers)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--thread", required=True)
    parser.add_argument("--questions", required=True, help="file in test_data/")
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    db.pool.open()
    row = db.fetch_one(
        "SELECT tenant_id FROM threads WHERE thread_id = %s", (args.thread,)
    )
    if row is None:
        raise SystemExit(f"no such thread: {args.thread}")
    tenant = row["tenant_id"]
    thread = uuid.UUID(args.thread)

    user = db.fetch_one(
        "SELECT user_id, tenant_id, role FROM users WHERE tenant_id = %s LIMIT 1",
        (tenant,),
    )
    token = create_access_token(user["user_id"], user["tenant_id"], user["role"])
    api = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}

    graph = get_graph()
    scope = {"configurable": {"thread_id": args.thread, "tenant_id": str(tenant)}}

    def searches_last_turn() -> int:
        """Tool calls made answering the most recent question.

        Read from the graph, not from the response: a search that
        returned nothing still ran, but produces no sources.
        """
        messages = graph.get_state(scope).values.get("messages", [])
        starts = [i for i, m in enumerate(messages) if m.type == "human"]
        turn = messages[starts[-1] :] if starts else messages
        return sum(1 for m in turn if m.type == "tool")

    # A bare filename means test_data/. A path is taken as written, so a
    # filtered subset can be run without adding it to test_data.
    path = pathlib.Path(args.questions)
    cases = load(path if path.exists() else TEST_DATA / args.questions)
    if args.limit:
        cases = cases[: args.limit]

    rows = []
    for index, case in enumerate(cases, 1):
        question = case["question"]

        # Retrieval is captured separately from the agent's own search so
        # the judge sees the same five chunks every time, whether or not
        # the agent chose to search.
        hits = rerank(question, search(question, tenant, thread))

        answer = api.post(
            f"/threads/{args.thread}/chat",
            json={"message": question},
            headers=headers,
        ).json()["answer"]

        rows.append(
            {
                "question": question,
                "reference": case["reference"],
                "answer": answer,
                "contexts": [h.text for h in hits],
                "pages": [h.page for h in hits],
                "scores": [round(float(h.score), 3) for h in hits],
                "searches": searches_last_turn(),
            }
        )
        print(f"  {index}/{len(cases)}  {question[:70]}")

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")

    searched = sum(1 for r in rows if r["searches"])
    print(f"\n{len(rows)} answered, none skipped")
    print(f"  searched {searched}/{len(rows)} turns")
    print(f"  written to {out}")


if __name__ == "__main__":
    main()
    # LangMem's extractor thread is not a daemon, so Python waits for a
    # queue that never drains. The file is written; stop.
    os._exit(0)
