"""Retrieval only. No agent, no answers, no model.

For every question in a Q&A file, run search and reranking and save the
five chunks that would reach the agent. Nothing is generated, so this
costs embedding calls and nothing else, and the result measures search on
its own - separate from whether the agent chose to use it.

    uv run eval/run_retrieval.py --thread <uuid> \
        --questions greggs-memory-test.md \
        --out metrics/retrieval_greggs.json
"""

import argparse
import json
import pathlib
import re
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.db import postgres as db  # noqa: E402
from app.retrieval.hybrid import search  # noqa: E402
from app.retrieval.rerank import rerank  # noqa: E402

TEST_DATA = pathlib.Path(__file__).resolve().parents[1] / "test_data"

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

    cases = load(TEST_DATA / args.questions)
    if args.limit:
        cases = cases[: args.limit]

    rows = []
    for index, case in enumerate(cases, 1):
        hits = rerank(case["question"], search(case["question"], tenant, thread))
        rows.append(
            {
                "question": case["question"],
                "reference": case["reference"],
                "contexts": [h.text for h in hits],
                "pages": [h.page for h in hits],
                "scores": [round(float(h.score), 3) for h in hits],
            }
        )
        print(f"  {index}/{len(cases)}  {case['question'][:70]}")

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print(f"\n{len(rows)} questions retrieved, none skipped")
    print(f"  written to {out}")


if __name__ == "__main__":
    main()
