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
