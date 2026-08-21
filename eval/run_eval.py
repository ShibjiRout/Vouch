"""Score retrieval and generation against the Q&A sets in test_data.

Retrieval: did a chunk holding the expected figure reach the final 5.
Generation: does the answer state that figure.

Figures are the answer in financial Q&A, so a numeric match is a fair
proxy for correctness and needs no second model to judge it.
"""

import argparse
import json
import pathlib
import re
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.auth.jwt import create_access_token  # noqa: E402
from app.db import postgres as db  # noqa: E402
from app.retrieval.hybrid import search  # noqa: E402
from app.retrieval.rerank import rerank  # noqa: E402

TEST_DATA = pathlib.Path(__file__).resolve().parents[1] / "test_data"

# Both heading styles used across the question files.
QUESTION_RE = re.compile(r"^#{3,4}\s*(?:Q)?\d+[:.]\s*(.+?)\s*$", re.M)
ANSWER_RE = re.compile(r"^\*\*Answer:\*\*\s*(.+?)\s*$", re.M)

# A figure worth matching: at least four digits, or a decimal. Bare
# small integers are too common to mean anything.
FIGURE_RE = re.compile(r"\d[\d,]{3,}(?:\.\d+)?|\d+\.\d+")


def load(path: pathlib.Path) -> list[dict]:
    """Pair each question with its answer, in file order."""
    text = path.read_text(encoding="utf-8")
    questions = QUESTION_RE.findall(text)
    answers = ANSWER_RE.findall(text)
    return [
        {"question": q, "expected": a}
        for q, a in zip(questions, answers)
    ]


def figures(text: str) -> set[str]:
    """The numbers a correct answer has to contain."""
    return {f.replace(",", "") for f in FIGURE_RE.findall(text)}


def found_in(text: str, wanted: set[str]) -> bool:
    """True if any expected figure appears, commas ignored."""
    flat = text.replace(",", "")
    return any(f in flat for f in wanted)


def evaluate(case: dict, tenant: uuid.UUID, thread: uuid.UUID, client=None) -> dict:
    """Score one question for retrieval, and generation if asked."""
    wanted = figures(case["expected"])
    result = {"question": case["question"], "expected_figures": sorted(wanted)}

    if not wanted:
        result["skipped"] = "no figure in expected answer"
        return result

    hits = rerank(case["question"], search(case["question"], tenant, thread))
    result["retrieved"] = any(found_in(h.text, wanted) for h in hits)
    result["pages"] = [h.page for h in hits]

    if client is not None:
        response = client["post"](case["question"])
        result["answer"] = response
        result["correct"] = found_in(response, wanted)

    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--thread", required=True)
    parser.add_argument("--questions", required=True, help="markdown file")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--generate", action="store_true", help="also call the chat endpoint")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    db.pool.open()
    row = db.fetch_one(
        "SELECT tenant_id FROM threads WHERE thread_id = %s", (args.thread,)
    )
    if row is None:
        raise SystemExit(f"no such thread: {args.thread}")
    tenant = row["tenant_id"]

    client = None
    if args.generate:
        from fastapi.testclient import TestClient

        from app.api.main import app

        user = db.fetch_one(
            "SELECT user_id, tenant_id, role FROM users WHERE tenant_id = %s LIMIT 1",
            (tenant,),
        )
        token = create_access_token(user["user_id"], user["tenant_id"], user["role"])
        api = TestClient(app)
        headers = {"Authorization": f"Bearer {token}"}
        client = {
            "post": lambda q: api.post(
                f"/threads/{args.thread}/chat", json={"message": q}, headers=headers
            ).json()["answer"]
        }

    cases = load(TEST_DATA / args.questions)[: args.limit]
    results = [
        evaluate(c, tenant, uuid.UUID(args.thread), client) for c in cases
    ]

    scored = [r for r in results if "retrieved" in r]
    recall = sum(r["retrieved"] for r in scored)
    print(f"\n{args.questions}  ({len(scored)} scored, {len(results) - len(scored)} skipped)")
    print(f"  Recall@5   {recall}/{len(scored)}  ({recall / len(scored):.0%})")

    if args.generate:
        correct = sum(r.get("correct", False) for r in scored)
        grounded = [r for r in scored if r["retrieved"]]
        hit = sum(r.get("correct", False) for r in grounded)
        print(f"  Correct    {correct}/{len(scored)}  ({correct / len(scored):.0%})")
        if grounded:
            print(f"  Correct when retrieved  {hit}/{len(grounded)}  ({hit / len(grounded):.0%})")

    if args.out:
        pathlib.Path(args.out).write_text(
            json.dumps(results, indent=2, default=str), encoding="utf-8"
        )
        print(f"  written to {args.out}")


if __name__ == "__main__":
    main()
