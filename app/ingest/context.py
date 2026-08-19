"""Write one sentence per chunk saying what it is.

A chunk reading "revenue rose to 4.2m" carries no year, and a table of
figures does not say which population it covers. The generated line
gives the chunk its own context without asking anyone to type metadata
the document does not have.

This is the only improvement written into the stored vector. Changing
the wording later means re-processing every document.
"""

import asyncio

from langchain_openai import ChatOpenAI

from app.config import (
    CHAT_MODEL,
    CONTEXT_LINE_CONCURRENCY,
    OPENAI_API_KEY,
)
from app.ingest.chunk import Chunk
from app.logging_config import get_logger

log = get_logger(__name__)

# Enough of the document to place a chunk, without paying for all of it
# on every call.
SUMMARY_CHARS = 3000
CHUNK_CHARS = 2000

# The heading that says which population or period a table covers sits
# in the chunk before it, not in the figures themselves. Without this
# the model can only guess, and guesses come out as boilerplate.
NEIGHBOUR_CHARS = 700

PROMPT = """Here is the start of a document:
<document>
{summary}
</document>

Here is the text immediately before the chunk, from the same document:
<preceding>
{before}
</preceding>

Here is a chunk from page {page} of that document:
<chunk>
{chunk}
</chunk>

Write ONE short sentence placing this chunk in the document: what it is,
which entity or population it covers, and which period. Use only what the
document states. No preamble, no quotes, just the sentence."""

_llm = ChatOpenAI(model=CHAT_MODEL, temperature=0, api_key=OPENAI_API_KEY)


async def _one(
    chunk: Chunk, before: str, summary: str, guard: asyncio.Semaphore
) -> str:
    """Ask for a single chunk's context line."""
    async with guard:
        try:
            reply = await _llm.ainvoke(
                PROMPT.format(
                    summary=summary,
                    before=before,
                    page=chunk.page,
                    chunk=chunk.text[:CHUNK_CHARS],
                )
            )
            return reply.content.strip().replace("\n", " ")
        except Exception:
            # A missing line costs some recall. A failed upload costs
            # the whole document.
            log.warning("context line failed for chunk %s", chunk.chunk_index)
            return ""


async def _all(chunks: list[Chunk], summary: str) -> list[str]:
    guard = asyncio.Semaphore(CONTEXT_LINE_CONCURRENCY)
    befores = [""] + [c.text[-NEIGHBOUR_CHARS:] for c in chunks[:-1]]
    return await asyncio.gather(
        *(_one(c, b, summary, guard) for c, b in zip(chunks, befores))
    )


def add_context(chunks: list[Chunk]) -> list[str]:
    """Return one context line per chunk, generated concurrently.

    Serially this is nine minutes for a 200-page PDF instead of thirty
    seconds. The concurrency is the feature working, not an optimisation.
    """
    if not chunks:
        return []

    summary = "\n".join(c.text for c in chunks[:6])[:SUMMARY_CHARS]
    lines = asyncio.run(_all(chunks, summary))

    written = sum(1 for line in lines if line)
    log.info("context lines written=%s of %s", written, len(chunks))
    return lines
