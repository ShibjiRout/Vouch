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

# A long financial table is often detected as a stack of small ones,
# which strips the column headers off every part but the first.
# Regions this close together, sharing a column span, are one table.
MERGE_MAX_GAP = 25
MERGE_MIN_OVERLAP = 0.5


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


def _merge_adjacent(tables: list) -> list[list]:
    """Group detected regions that are really one table."""
    if not tables:
        return []

    tables = sorted(tables, key=lambda t: t.bbox[1])
    groups = [[tables[0]]]

    for table in tables[1:]:
        px0, _, px1, pbottom = groups[-1][-1].bbox
        x0, top, x1, _ = table.bbox

        overlap = min(px1, x1) - max(px0, x0)
        narrower = min(px1 - px0, x1 - x0)
        share = overlap / narrower if narrower > 0 else 0

        if top - pbottom <= MERGE_MAX_GAP and share >= MERGE_MIN_OVERLAP:
            groups[-1].append(table)
        else:
            groups.append([table])

    return groups


def _union(bboxes: list[tuple]) -> tuple:
    """Smallest box containing all of them."""
    return (
        min(b[0] for b in bboxes),
        min(b[1] for b in bboxes),
        max(b[2] for b in bboxes),
        max(b[3] for b in bboxes),
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

            for group in _merge_adjacent(page.find_tables()):
                rows = [row for table in group for row in (table.extract() or [])]
                if not is_real_table(rows):
                    # Left in the page text, since it is prose or a figure.
                    continue

                bbox = _union([table.bbox for table in group])
                text = _table_to_text(rows, _caption(page, bbox))
                if text:
                    blocks.append(Block("table", number, text))
                    bboxes.append(bbox)

            # Words inside an accepted table are dropped here so the same
            # figures do not appear twice, once as prose and once as a table.
            body = page.filter(lambda obj: _outside(obj, bboxes)).extract_text()
            if body and body.strip():
                blocks.append(Block("text", number, body.strip()))

    return blocks, page_count
