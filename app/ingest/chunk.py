"""Split blocks into chunks. Tables are never split."""

from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import CHUNK_OVERLAP, CHUNK_SIZE
from app.ingest.extract import Block

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
)


@dataclass
class Chunk:
    """One unit of retrieval, with the position that cites it."""

    text: str
    page: int
    chunk_type: str
    chunk_index: int


def chunk_blocks(blocks: list[Block]) -> list[Chunk]:
    """Split prose at 1000/200. Keep each table whole."""
    chunks: list[Chunk] = []

    for block in blocks:
        if block.kind == "table":
            # One table per chunk regardless of size. A figure cut
            # away from its row label produces a confident wrong answer.
            pieces = [block.text]
        else:
            pieces = _splitter.split_text(block.text)

        for piece in pieces:
            if not piece.strip():
                continue
            chunks.append(
                Chunk(
                    text=piece,
                    page=block.page,
                    chunk_type=block.kind,
                    chunk_index=len(chunks),
                )
            )

    return chunks
