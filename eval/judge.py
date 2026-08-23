"""Grade a saved run with an LLM judge. Two retrieval metrics, two generation.

Retrieval
    Context Recall     did the five chunks hold what the answer needed
    Context Precision  were the useful ones ranked at the top

Generation
    Faithfulness       is every claim in the answer in the chunks it was given
    Answer Correctness does the answer say what the written answer says

The first pair fails when search missed. The second fails when search
worked and the model still got it wrong. Faithfulness and Correctness
disagreeing is the interesting case: an answer faithful to the chunks but
wrong means the wrong chunk arrived.

Runs in .venv-eval, not the app venv - ragas 0.3.9 needs
langchain-community < 0.4, and the app is on 0.4.

    .venv-eval/Scripts/python.exe eval/judge.py \
        --run metrics/answers_dominos.json
"""

import argparse
import json
import os
import pathlib

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas import evaluate
from ragas.dataset_schema import EvaluationDataset, SingleTurnSample
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (
    AnswerCorrectness,
    Faithfulness,
    LLMContextPrecisionWithReference,
    LLMContextRecall,
)
from ragas.run_config import RunConfig

load_dotenv()

# Judged by a different model from the one that answered. gpt-4o-mini
# grading its own output scores itself generously.
JUDGE_MODEL = "gpt-4.1-mini"

# Claim-level only. Semantic similarity is switched off: two sentences
# can read alike and carry different figures, which is the failure being
# measured.
FACTUAL_ONLY = [1.0, 0.0]

# Above this a metric counts as a pass, for the headline percentages.
PASS = 0.7

METRICS = [
    "context_recall",
    "llm_context_precision_with_reference",
    "faithfulness",
    "answer_correctness",
]

LABELS = {
    "context_recall": "Context Recall      (retrieval)",
    "llm_context_precision_with_reference": "Context Precision   (retrieval)",
    "faithfulness": "Faithfulness        (generation)",
    "answer_correctness": "Answer Correctness  (generation)",
}

REFUSALS = (
    "could not find",
    "cannot answer",
    "can't answer",
    "not whether to buy",
    "still being read",
    "do not have",
    "don't have",
)


def refused(answer: str) -> bool:
    """True if the answer declines rather than states something."""
    low = answer.lower()
    return any(phrase in low for phrase in REFUSALS)


def mean(values: list) -> float:
    """Average, ignoring the scores ragas could not produce."""
    real = [v for v in values if v == v]  # NaN fails this
    return sum(real) / len(real) if real else float("nan")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, help="from run_answers.py")
    parser.add_argument("--out", help="where to write the verdicts")
    parser.add_argument("--limit", type=int, help="judge only the first N")
    parser.add_argument(
        "--only",
        choices=["retrieval", "generation"],
        help="run one pair of metrics instead of all four",
    )
    # Ragas defaults to 180s and drops a score when a call runs over.
    # gpt-4o blew through that on 49 of 200 calls.
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--workers", type=int, default=5)
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set")

    rows = json.loads(pathlib.Path(args.run).read_text(encoding="utf-8"))
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        raise SystemExit("nothing to judge")

    judge = LangchainLLMWrapper(ChatOpenAI(model=JUDGE_MODEL, temperature=0))
    embeddings = LangchainEmbeddingsWrapper(OpenAIEmbeddings())

    retrieval = [LLMContextRecall(llm=judge), LLMContextPrecisionWithReference(llm=judge)]
    generation = [
        Faithfulness(llm=judge),
        AnswerCorrectness(llm=judge, embeddings=embeddings, weights=FACTUAL_ONLY),
    ]
    metrics = {"retrieval": retrieval, "generation": generation}.get(
        args.only, retrieval + generation
    )
    wanted = [m.name for m in metrics]

    dataset = EvaluationDataset(
        samples=[
            SingleTurnSample(
                user_input=row["question"],
                # Empty for a retrieval-only run. Context Recall and
                # Context Precision do not read it.
                response=row.get("answer", ""),
                reference=row["reference"],
                retrieved_contexts=row["contexts"],
            )
            for row in rows
        ]
    )

    print(f"judging {len(rows)} answers with {JUDGE_MODEL} on {len(metrics)} metrics...")
    frame = evaluate(
        dataset,
        metrics=metrics,
        llm=judge,
        # Ragas fires 16 calls at once by default and records nothing for
        # a row that fails. Sixteen blows through a 30,000 tokens-per-
        # minute limit, so most rows came back empty.
        run_config=RunConfig(
            timeout=args.timeout, max_retries=10, max_workers=args.workers
        ),
    ).to_pandas()

    verdicts = []
    for row, (_, scored) in zip(rows, frame.iterrows()):
        verdict = {
            "question": row["question"],
            "reference": row["reference"],
            "answer": row.get("answer", ""),
            "pages": row.get("pages"),
            "refused": refused(row.get("answer", "")),
            "searched": bool(row.get("searches")),
        }
        for name in wanted:
            value = scored.get(name)
            verdict[name] = None if value != value else round(float(value), 3)
        verdicts.append(verdict)

    out = pathlib.Path(args.out or args.run.replace(".json", "_judged.json"))
    out.write_text(json.dumps(verdicts, indent=2), encoding="utf-8")

    n = len(verdicts)
    print(f"\n{args.run}  ({n} questions, none skipped)\n")
    for name in wanted:
        values = [v[name] for v in verdicts if v[name] is not None]
        if not values:
            print(f"  {LABELS[name]}   no scores - every call timed out")
            continue
        passed = sum(1 for value in values if value >= PASS)
        missing = f"   ({n - len(values)} unscored)" if len(values) < n else ""
        print(f"  {LABELS[name]}   mean {mean(values):.2f}   "
              f"pass {passed}/{len(values)} ({passed / len(values):.0%}){missing}")

    refusals = sum(v["refused"] for v in verdicts)
    searched = sum(v["searched"] for v in verdicts)
    print(f"\n  Refused    {refusals}/{n} ({refusals / n:.0%})")
    print(f"  Searched   {searched}/{n} ({searched / n:.0%})")

    if args.only == "retrieval":
        print(f"\n  verdicts written to {out}")
        return

    # The diagnosis. Faithful but wrong means the wrong chunk arrived;
    # unfaithful means the model invented something it was not given.
    both = [v for v in verdicts
            if v["faithfulness"] is not None and v["answer_correctness"] is not None]
    invented = sum(1 for v in both
                   if v["faithfulness"] < PASS and v["answer_correctness"] < PASS)
    wrong_chunk = sum(1 for v in both
                      if v["faithfulness"] >= PASS and v["answer_correctness"] < PASS)
    print(f"\n  Wrong, but faithful to its chunks   {wrong_chunk}  <- retrieval")
    print(f"  Wrong and not in its chunks         {invented}  <- the model")

    print(f"\n  verdicts written to {out}")
    print("  read them - every score sits beside the answer and the reference")


if __name__ == "__main__":
    main()
