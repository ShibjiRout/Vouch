"""Pull text and tables out of a PDF with pdfplumber."""

from dataclasses import dataclass

import pdfplumber

# How far above a table to look for its caption, in points.
CAPTION_HEIGHT = 40


@dataclass
class Block:
    """One piece of a page: either prose or a whole table."""

    kind: str  # "text" or "table"
    page: int
    text: str


def _outside(obj: dict, bboxes: list[tuple]) -> bool:
    """True if this word sits outside every table area."""
    h_mid = (obj["x0"] + obj["x1"]) / 2
    v_mid = (obj["top"] + obj["bottom"]) / 2
    return not any(
        x0 <= h_mid < x1 and top <= v_mid < bottom
        for x0, top, x1, bottom in bboxes
    )


def _caption(page, bbox: tuple) -> str:
    """Read the line of text directly above a table."""
    x0, top, x1, _ = bbox
    if top <= 0:
        return ""
    region = page.crop((x0, max(0, top - CAPTION_HEIGHT), x1, top))
    lines = [line.strip() for line in (region.extract_text() or "").splitlines()]
    lines = [line for line in lines if line]
    return lines[-1] if lines else ""


def _table_to_text(rows: list[list], caption: str) -> str:
    """Render a table as text, header row first."""
    lines = []
    for row in rows:
        cells = [(cell or "").replace("\n", " ").strip() for cell in row]
        if any(cells):
            lines.append(" | ".join(cells))
    body = "\n".join(lines)
    return f"{caption}\n{body}".strip() if caption else body


def extract(path: str) -> tuple[list[Block], int]:
    """Return the blocks of a PDF and its page count."""
    blocks: list[Block] = []

    with pdfplumber.open(path) as pdf:
        page_count = len(pdf.pages)

        for number, page in enumerate(pdf.pages, start=1):
            tables = page.find_tables()
            bboxes = [table.bbox for table in tables]

            for table in tables:
                rows = table.extract()
                if not rows:
                    continue
                text = _table_to_text(rows, _caption(page, table.bbox))
                if text:
                    blocks.append(Block("table", number, text))

            # Words inside a table are dropped here so the same figures
            # do not appear twice, once as prose and once as a table.
            body = page.filter(lambda obj: _outside(obj, bboxes)).extract_text()
            if body and body.strip():
                blocks.append(Block("text", number, body.strip()))

    return blocks, page_count
