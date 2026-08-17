"""A SPREADSHEET printed into an exhibit must export as a table.

A billing export, a damages schedule, a payment history: the page is a grid, and
plain extraction reads it a cell at a time, top to bottom. Every value survives
and the document still says nothing, because a rate no longer sits beside the
entry it belongs to:

    Date / • / Type / Description / Matter / User / Qty / Rate($) /
    Non-billable ($) / Billable($) / 04/04/2025 / Telephonic conference with /
    Wrightson, Sharnbrook & / Buckminster / 0.40h / $375.00 / $150.00 / …

On a fee motion that is the exhibit the court actually reads.

The GATE is the symptom itself and costs nothing: a page whose text comes out as
a tall stack of very short lines is a grid that came apart into one cell per
line. Measured on the batch that reported this, the three billing pages ran
99-100% short lines at a median length of 10 characters, against 4-21% at a
median of 94 on the same document's prose pages. `find_tables` costs ~73 ms a
page against ~2 ms for the extraction itself, so it is only ever paid on a page
that already looks like this.

And the rendering has to PROVE it lost nothing, for the reason `_reocr_improves`
does: it replaces the page's own text for that region, and a cell the table
finder failed to read would be a value gone from the export with nothing to say
so.

Run:  cd PDF-Linker && python3 -m pytest tests/test_table_pages.py -v
"""
import logging

import pytest

import pdf_linker as P

fitz = pytest.importorskip("fitz")
log = logging.getLogger("test")

HEADERS = ["Date", "Description", "Matter", "User", "Qty", "Rate($)",
           "Billable($)"]
ENTRIES = [
    ["04/04/2025", "Telephonic conference with potential clients",
     "Rasho v. Quillmark", "Lathrop", "0.40h", "$375.00", "$150.00"],
    ["04/08/2025", "Review repair orders and service bulletins",
     "Rasho v. Quillmark", "Lathrop", "0.50h", "$375.00", "$187.50"],
    ["04/11/2025", "Further conference with clients re case",
     "Rasho v. Quillmark", "Lathrop", "0.30h", "$375.00", "$112.50"],
]
COLS = [40, 120, 330, 500, 570, 620, 690]


def _billing_page(ruled=True, before="Activities Export",
                  after="Total billable: $450.00"):
    doc = fitz.open()
    pg = doc.new_page(width=792, height=612)
    if before:
        pg.insert_text((40, 40), before, fontsize=12)
    y = 60
    for i, c in enumerate(HEADERS):
        pg.insert_text((COLS[i] + 2, y + 10), c, fontsize=7)
    yy = y + 14
    for row in ENTRIES:
        for i, c in enumerate(row):
            pg.insert_text((COLS[i] + 2, yy + 10), c, fontsize=7)
        yy += 14
    if ruled:
        for gy in range(y, yy + 1, 14):
            pg.draw_line(fitz.Point(40, gy), fitz.Point(750, gy))
        for x in COLS + [750]:
            pg.draw_line(fitz.Point(x, y), fitz.Point(x, yy))
    if after:
        pg.insert_text((40, yy + 30), after, fontsize=9)
    return doc, pg


def _prose_page(lines=45):
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    for i in range(lines):
        pg.insert_text((72, 72 + 15 * i),
                       f"{i + 1}  The Court finds that the motion is granted "
                       f"in part and denied in part.", fontsize=10)
    return doc, pg


# ── the gate ────────────────────────────────────────────────────────────────

def test_a_grid_that_came_apart_reads_as_cells():
    _doc, pg = _billing_page()
    assert P._page_reads_as_cells(P._page_flowing_text(pg))


def test_prose_does_not():
    _doc, pg = _prose_page()
    assert not P._page_reads_as_cells(P._page_flowing_text(pg))


@pytest.mark.parametrize("text,expected", [
    ("\n".join(["Date", "Type", "Qty", "Rate"] * 6), True),
    ("\n".join(["a fairly ordinary sentence of running prose here"] * 25),
     False),
    ("\n".join(["Date", "Type"]), False),          # too few lines to tell
    ("", False),
])
def test_the_shape_is_what_decides(text, expected):
    assert P._page_reads_as_cells(text) is expected


def test_an_ordinary_page_never_pays_for_table_finding(monkeypatch):
    """`find_tables` is ~35x the cost of the extraction itself."""
    _doc, pg = _prose_page()
    called = []
    monkeypatch.setattr(type(pg), "find_tables",
                        lambda self, **kw: called.append(1))
    assert P._page_table_text(pg) is None
    assert not called


# ── the rendering ───────────────────────────────────────────────────────────

def test_a_ruled_table_renders_as_a_grid():
    _doc, pg = _billing_page()
    out = P._page_table_text(pg)
    assert out and "| Date | Description |" in out
    assert "| --- |" in out
    for row in ENTRIES:
        assert f"| {row[0]} |" in out
        assert row[-1] in out


def test_every_entry_keeps_its_own_rate():
    """The whole point: a rate beside the entry it belongs to."""
    _doc, pg = _billing_page()
    out = P._page_table_text(pg)
    for row in ENTRIES:
        line = next(ln for ln in out.splitlines() if ln.startswith(f"| {row[0]}"))
        assert row[4] in line and row[6] in line, line


def test_no_word_of_the_page_is_lost():
    _doc, pg = _billing_page()
    out = P._page_table_text(pg)
    for word in P._page_flowing_text(pg).split():
        assert word in out, word


def test_the_text_around_the_table_stays_in_reading_order():
    _doc, pg = _billing_page()
    out = P._page_table_text(pg)
    assert out.index("Activities Export") < out.index("| Date")
    assert out.index("| Date") < out.index("Total billable")


def test_an_unruled_grid_is_read_by_the_text_strategy():
    """A UI export separates its rows by shading or by nothing at all, which
    the line strategy cannot see. Eager, so it runs only where the line
    strategy found nothing — and faces the same no-loss test."""
    _doc, pg = _billing_page(ruled=False)
    out = P._page_table_text(pg)
    assert out and out.count("\n|") >= len(ENTRIES)
    for word in P._page_flowing_text(pg).split():
        assert word in out, word


# ── it must prove it lost nothing ───────────────────────────────────────────

class _StubTable:
    def __init__(self, rows, bbox=(0, 0, 800, 600)):
        self._rows, self.bbox = rows, bbox

    def extract(self):
        return self._rows


def test_a_grid_that_drops_a_cell_is_refused():
    _doc, pg = _billing_page()
    grid = P._table_grid(_StubTable([HEADERS, ENTRIES[0], ENTRIES[1]]))
    assert grid                                   # it renders…
    assert not P._table_keeps_every_word(pg, (0, 0, 792, 612), grid)  # …but loses


def test_a_grid_that_keeps_everything_passes():
    _doc, pg = _billing_page(before="", after="")
    grid = P._table_grid(_StubTable([HEADERS] + ENTRIES))
    assert P._table_keeps_every_word(pg, (0, 0, 792, 612), grid)


@pytest.mark.parametrize("rows", [
    [["a", "b"]],                                  # one row
    [["a", "b"], ["c", "d"]],                      # two
    [["only"], ["one"], ["column"]],               # one column
    [["a", ""], ["", ""], ["", "d"], ["", ""]],    # mostly empty
])
def test_too_small_or_too_empty_is_not_a_table(rows):
    assert P._table_grid(_StubTable(rows)) is None


def test_a_delimiter_inside_a_cell_is_escaped():
    grid = P._table_grid(_StubTable([["a|b", "c"], ["d", "e"], ["f", "g"]]))
    assert r"a\|b" in grid


def test_a_wrapped_cell_becomes_one_line():
    grid = P._table_grid(_StubTable([["Telephonic conference\nwith clients", "x"],
                                     ["b", "y"], ["c", "z"]]))
    assert "Telephonic conference with clients" in grid
    assert len(grid.splitlines()) == 4            # 3 rows + the header rule


# ── detection reads exactly what the export writes ─────────────────────────

def test_detection_sees_the_grid_too():
    """The rule the form path already follows — a party named in a cell has to
    be contiguous for the scrubber and the leak scan, not scattered."""
    _doc, pg = _billing_page()
    assert P._page_detect_text(pg) == P._page_table_text(pg)


def test_a_pleading_page_keeps_its_rows():
    """Pleading paper has its own rendering, and swapping the page to a grid
    would cost the gutter numbers a pinpoint cite lands on."""
    _doc, pg = _prose_page()
    assert P._page_table_text(pg) is None
    assert "The Court finds" in P._page_detect_text(pg)


def test_the_answer_is_memoized_per_page():
    _doc, pg = _billing_page()
    first = P._page_table_text(pg)
    assert P._page_table_text(pg) is first
