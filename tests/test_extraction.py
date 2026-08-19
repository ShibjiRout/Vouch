"""Table detection: keep real tables, reject grid-shaped figures."""

from app.ingest.chunk import chunk_blocks
from app.ingest.extract import Block, is_real_table


def test_accepts_a_normal_table():
    rows = [["Year", "Revenue", "EBITDA"], ["2024", "4.2m", "3.1m"]]
    assert is_real_table(rows)


def test_accepts_a_single_column_table():
    """Booktabs tables have no vertical rules, so each row is one cell."""
    rows = [["N dmodel dff h dk dv"], ["6 512 2048 8 64 64"], ["2 512 2048 8 64 64"]]
    assert is_real_table(rows)


def test_rejects_a_heatmap_figure():
    """An attention plot: many columns, mostly empty, tiny fragments."""
    rows = [[""] * 39 for _ in range(9)]
    for row in rows[:3]:
        row[0], row[5], row[9] = "st", "n", "ne"
    assert not is_real_table(rows)


def test_rejects_empty_and_blank():
    assert not is_real_table([])
    assert not is_real_table([["", ""], [None, None]])


def test_table_survives_chunking_whole():
    big = "\n".join(f"20{i:02d} | {i}.1m" for i in range(400))
    chunks = chunk_blocks([Block("table", 2, big)])
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "table"
    assert len(chunks[0].text) > 3000


class FakeTable:
    """Stands in for a pdfplumber Table."""

    def __init__(self, bbox, rows):
        self.bbox = bbox
        self._rows = rows

    def extract(self):
        return self._rows


def test_merges_a_table_split_into_strips():
    """A long financial table is detected as a stack of small ones."""
    from app.ingest.extract import _merge_adjacent

    strips = [
        FakeTable((50, 100 + i * 20, 550, 115 + i * 20), [[f"row{i}", "1", "2"]])
        for i in range(6)
    ]
    groups = _merge_adjacent(strips)
    assert len(groups) == 1, "vertically adjacent strips are one table"
    assert len(groups[0]) == 6


def test_keeps_separate_tables_apart():
    """Two tables with a paragraph between them stay separate."""
    from app.ingest.extract import _merge_adjacent

    first = FakeTable((50, 100, 550, 200), [["a"]])
    second = FakeTable((50, 400, 550, 500), [["b"]])
    assert len(_merge_adjacent([first, second])) == 2


def test_keeps_side_by_side_tables_apart():
    """Two columns of table on one page do not share a column span."""
    from app.ingest.extract import _merge_adjacent

    left = FakeTable((50, 100, 280, 200), [["a"]])
    right = FakeTable((300, 210, 550, 300), [["b"]])
    assert len(_merge_adjacent([left, right])) == 2
