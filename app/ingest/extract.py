"""Pull text and tables out of a PDF with pdfplumber."""

import re
from dataclasses import dataclass

import pdfplumber

# How far above a table to look for its caption, in points.
CAPTION_HEIGHT = 70

# A caption usually announces itself. When one of these starts a line,
# the caption runs from there to the table.
CAPTION_START = re.compile(r"^(table|figure|exhibit|schedule)\s*\d+", re.I)

# Detected regions that fail these are not tables. Figures drawn on a
# grid — attention heatmaps, plots — are found by find_tables() and
# come back as dozens of near-empty columns holding rotated fragments.
MAX_COLUMNS = 15
MIN_FILL_RATIO = 0.5
MIN_AVG_CELL_LENGTH = 2


@dataclass
class Block:
    """One piece of a page: either prose or a whole table."""

    kind: str  # "text" or "table"
    page: int
    text: str


def is_real_table(rows: list[list]) -> bool:
    """Reject grid-shaped figures that only look like tables."""
    if not rows:
        return False

    cells = [cell for row in rows for cell in row]
    if not cells:
        return False

    filled = [(cell or "").strip() for cell in cells]
    filled = [cell for cell in filled if cell]
    if not filled:
        return False

    columns = max(len(row) for row in rows)
    fill_ratio = len(filled) / len(cells)
    avg_length = sum(len(cell) for cell in filled) / len(filled)

    return (
        columns <= MAX_COLUMNS
        and fill_ratio >= MIN_FILL_RATIO
        and avg_length >= MIN_AVG_CELL_LENGTH
    )


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
    _, top, _, _ = bbox
    if top <= 0:
        return ""
    # Full page width, not the table's — cropping to the table's x
    # range slices words in half and yields fragments like "dperplexities".
    region = page.crop((0, max(0, top - CAPTION_HEIGHT), page.width, top))
    lines = [line.strip() for line in (region.extract_text() or "").splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return ""

    # A wrapped caption spans several lines; taking only the last one
    # yields a fragment like "per-wordperplexities".
    for index, line in enumerate(lines):
        if CAPTION_START.match(line):
            return " ".join(lines[index:])
    return lines[-1]


def _table_to_text(rows: list[list], caption: str) -> str:
    """Render a table as text, header row first."""
    lines = []
    for row in rows:
        cells = [(cell or "").replace("\n", " ").strip() for cell in row]
        if any(cells):
            lines.append(" | ".join(cells) if len(cells) > 1 else cells[0])
    body = "\n".join(lines)
    return f"{caption}\n{body}".strip() if caption else body


def extract(path: str) -> tuple[list[Block], int]:
    """Return the blocks of a PDF and its page count."""
    blocks: list[Block] = []

    with pdfplumber.open(path) as pdf:
        page_count = len(pdf.pages)

        for number, page in enumerate(pdf.pages, start=1):
            bboxes = []

            for table in page.find_tables():
                rows = table.extract()
                if not is_real_table(rows):
                    # Left in the page text, since it is prose or a figure.
                    continue

                text = _table_to_text(rows, _caption(page, table.bbox))
                if text:
                    blocks.append(Block("table", number, text))
                    bboxes.append(table.bbox)

            # Words inside an accepted table are dropped here so the same
            # figures do not appear twice, once as prose and once as a table.
            body = page.filter(lambda obj: _outside(obj, bboxes)).extract_text()
            if body and body.strip():
                blocks.append(Block("text", number, body.strip()))

    return blocks, page_count
