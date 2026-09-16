"""The export's character grid is MEASURED off the page and a column is one
column all the way down it.

The positional layout (`_visual_row_text`, `_page_visual_text`) divided an x
offset by a fixed 6 pt — the width of one 12 pt character — and resolved an
overflow per row. Two failures followed, both reported as "the columns don't
line up": an exhibit set in 8 pt fits half again as many characters into a
printed column, so a cell that FIT on the page ran past its grid slot in the
export; and when it did, only that row's next cell was pushed right, so a
ledger came out with its short rows aligned and its long rows ragged.

`_spans_char_width` takes the unit from the page's own type; `_column_stops`
lays the page out on ONE grid, moving a whole column right where any row's
cell runs past it.

Run:  cd PDF-Linker && python3 -m pytest tests/test_measured_grid.py -v
"""
import pytest

fitz = pytest.importorskip("fitz")

import pdf_linker as P


def _page(draw):
    doc = fitz.open()
    pg = doc.new_page()
    draw(pg)
    pg._doc_ref = doc
    return pg


def _cols(line, *words):
    return [line.index(w) for w in words]


# ── the unit ────────────────────────────────────────────────────────────────

class TestCharWidth:
    def test_small_type_measures_narrower_than_large(self):
        small = _page(lambda p: [p.insert_text((72, 80 + 12 * i),
                                               "The quick brown fox jumps over the lazy dog.",
                                               fontsize=8, fontname="helv")
                                 for i in range(3)])
        large = _page(lambda p: [p.insert_text((72, 80 + 18 * i),
                                               "The quick brown fox jumps over the lazy dog.",
                                               fontsize=14, fontname="helv")
                                 for i in range(3)])
        cw_s = P._spans_char_width(P._page_text_spans(small))
        cw_l = P._spans_char_width(P._page_text_spans(large))
        assert cw_s < P._VIS_CHAR_W < cw_l

    def test_the_body_outvotes_a_large_heading(self):
        pg = _page(lambda p: (
            p.insert_text((150, 72), "NOTICE OF DEFAULT AND ELECTION TO SELL",
                          fontsize=18, fontname="helv"),
            [p.insert_text((72, 110 + 12 * i),
                           "You are hereby notified that the account is in default.",
                           fontsize=9, fontname="helv") for i in range(6)]))
        body = _page(lambda p: [p.insert_text((72, 110 + 12 * i),
                                              "You are hereby notified that the account is in default.",
                                              fontsize=9, fontname="helv") for i in range(6)])
        cw = P._spans_char_width(P._page_text_spans(pg))
        assert cw == pytest.approx(P._spans_char_width(P._page_text_spans(body)), abs=0.05)

    def test_too_little_text_keeps_the_default(self):
        pg = _page(lambda p: p.insert_text((250, 80), "EXHIBIT A", fontsize=11))
        assert P._spans_char_width(P._page_text_spans(pg)) == P._VIS_CHAR_W

    def test_the_unit_is_bounded(self):
        assert P._spans_char_width([{"bbox": (0, 0, 1.0, 10), "text": "x" * 100}]) == P._VIS_CW_MIN
        assert P._spans_char_width([{"bbox": (0, 0, 5000.0, 10), "text": "x" * 100}]) == P._VIS_CW_MAX


# ── the page-wide column ────────────────────────────────────────────────────

class TestColumnStops:
    def test_a_long_cell_moves_the_column_for_every_row(self):
        rows = [[(72.0, "Date"), (200.0, "Amount")],
                [(72.0, "A cell far longer than the slot its x allows"), (200.0, "1.00")],
                [(72.0, "Short"), (200.0, "2.00")]]
        lines = P._visual_rows_text(rows, 72.0)
        cols = [l.index(w) for l, w in zip(lines, ("Amount", "1.00", "2.00"))]
        assert len(set(cols)) == 1, lines
        assert cols[0] > len(rows[1][0][1])

    def test_a_prose_row_constrains_nothing(self):
        rows = [[(72.0, "x" * 90)],                       # one long prose line
                [(72.0, "Date"), (200.0, "Amount")]]
        lines = P._visual_rows_text(rows, 72.0)
        assert lines[1].index("Amount") == round((200.0 - 72.0) / P._VIS_CHAR_W)

    def test_cells_a_hair_apart_share_a_column(self):
        rows = [[(72.0, "a"), (200.0, "b")], [(72.0, "c"), (201.5, "d")]]
        lines = P._visual_rows_text(rows, 72.0)
        assert lines[0].index("b") == lines[1].index("d")

    def test_column_zero_still_adds_nothing(self):
        assert P._visual_rows_text([[(72.0, "body prose")]], 72.0) == ["body prose"]

    def test_a_single_row_reads_as_before(self):
        segs = [(110.0, "ROXANE ESTRADA,"), (380.0, "Case No.: 25STCV37838")]
        assert P._visual_rows_text([segs], 110.0) == [P._visual_row_text(segs, 110.0)]


# ── end to end on a page ────────────────────────────────────────────────────

def _ledger(fontsize):
    cols = [72, 300, 360, 420, 480]
    rows = [("Description of Services Rendered", "Hours", "Rate", "Total", "Bill?"),
            ("Telephone conference with client re discovery responses", "0.8", "450", "360.00", "Y"),
            ("Review file", "0.2", "450", "90.00", "Y"),
            ("Draft and revise opposition to motion to compel arb.", "4.5", "450", "2,025.00", "Y"),
            ("Email to opposing counsel", "0.1", "450", "45.00", "N")]

    def draw(p):
        y = 72
        for r in rows:
            for x, t in zip(cols, r):
                p.insert_text((x, y), t, fontsize=fontsize, fontname="helv")
            y += fontsize + 3
    return _page(draw)


def test_a_small_type_ledger_keeps_its_columns():
    """Every cell fits its printed column on the page; every row must show
    the Hours/Rate/Total/Bill? cells at one column apiece in the export."""
    lines = [l for l in P._page_visual_text(_ledger(8)).splitlines() if l.strip()]
    assert len(lines) == 5
    for i, words in enumerate([("Hours", "Rate", "Total", "Bill?"),
                               ("0.8", "450", "360.00", "Y"),
                               ("0.2", "450", "90.00", "Y"),
                               ("4.5", "450", "2,025.00", "Y"),
                               ("0.1", "450", "45.00", "N")]):
        assert _cols(lines[i], *words) == _cols(lines[0], "Hours", "Rate", "Total", "Bill?"), lines


def test_the_pleading_row_path_takes_the_same_grid():
    """`_pn_apply_page_rows` and the unscrubbed row writer lay a page out on
    one grid too: a scrubbed cell that grows moves the column, never the row."""
    class _PZ:
        records = {}                 # nothing for the caption rebuild to read

        def apply_lines(self, bodies):
            return [b.replace("Doe", "A Much Longer Stand-In") for b in bodies]
    rows = [(1, [(110.0, "John Doe,"), (380.0, "Case No.: 25STCV37838")]),
            (2, [(110.0, "Plaintiff,"), (380.0, "Dept.: 55")])]
    a, b = P._pn_apply_page_rows(_PZ(), rows, 5.0)
    assert a.index("Case No.") == b.index("Dept.")
    assert a.index("Case No.") > len("John A Much Longer Stand-In,")
    # …and the unscrubbed writer, on the same rows, the same way.
    c, d = P._visual_rows_text([segs for _n, segs in rows], 110.0, 5.0)
    assert c.index("Case No.") == d.index("Dept.") == round((380.0 - 110.0) / 5.0)
