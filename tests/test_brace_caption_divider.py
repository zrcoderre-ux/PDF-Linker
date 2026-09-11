"""Some title pages draw the box around the parties with RIGHT PARENTHESES.

The older California caption rules the party column's right edge with a run of
closing parentheses, one to a printed line, where another filing draws a
vertical rule. `_page_rules` reads LINE ART and sees nothing of it, so such a
page had no column boundary at all: the party names and the case-number column
came apart only where the printed gap happened to exceed `_COLUMN_GAP_MIN`, and
a caption sets the brace hard against both — so the two columns welded into a
run that exists nowhere on the page, with the ")" riding along inside it:

    'in interest to THE ESTATE OF JEPHSON RASHO, ) Consolidated Case No. …'

That is the extraction failure `_split_row_columns` exists to prevent, arriving
from the one direction it could not see — and a name spliced like that matches
no pseudonymizer term, so it is a disclosure bug as well as an ugly export.

A brace column is the page saying where the column ends, exactly as a rule
does, so it is READ AS ONE and handed to `_split_row_columns` through the same
`rules=` seam. The corroboration is REPETITION AT ONE X, which is also what
lets the class admit the shapes a SCAN makes of a parenthesis.

Run:  cd PDF-Linker && python3 -m pytest tests/test_brace_caption_divider.py -v
"""
import pytest

import pdf_linker as P

fitz = pytest.importorskip("fitz")

LEFT = ["HELEN RASHO, an individual and as successor",
        "in interest to THE ESTATE OF JEPHSON RASHO,",
        "deceased, and GABLE RAMSEY, individually,",
        "                              Plaintiffs,",
        "                              vs.",
        "QUILLMARK BUILDERS, LLC, a California corp.,",
        "THORNFIELD QUARRY, INC.; and DOES 1 to 30,",
        "                              Defendants."]
RIGHT = ["Case No. 25STCV37838", "Consolidated Case No. 20STCV27618",
         "COMPLAINT FOR DAMAGES", "1. Breach of Contract", "2. Negligence",
         "3. Fraud", "4. Conversion", "5. Unjust Enrichment"]
# Set the divider a few points past the LONGEST party line and the right
# column a few points past the divider, so every printed gap on the page is
# under `_COLUMN_GAP_MIN` and only a rule can part the two columns — which is
# how a real caption is set.
_DIV_X = 72 + max(fitz.Font("helv").text_length(t, 10) for t in LEFT) + 4.0
_RIGHT_X = _DIV_X + fitz.Font("helv").text_length(")", 10) + 8.0


def _page(divider=")", rows=len(LEFT)):
    doc = fitz.open()
    pg = doc.new_page(width=792, height=792)
    for i in range(rows):
        y = 100 + 26 * i
        pg.insert_text((40, y), str(i + 1), fontsize=11)
        pg.insert_text((72, y), LEFT[i % len(LEFT)], fontsize=10)
        if divider:
            pg.insert_text((_DIV_X, y), divider, fontsize=10)
        pg.insert_text((_RIGHT_X, y), RIGHT[i % len(RIGHT)], fontsize=10)
    return doc


def _segments(doc):
    return [[t for _x, t in segs] for _num, segs in (P._page_lined_rows(doc[0]) or [])]


# ── the columns come apart ──────────────────────────────────────────────────

def test_a_brace_column_is_read_as_a_vertical_rule():
    rules = P._page_brace_rules(P._cluster_rows(P._page_text_spans(_page()[0])))
    assert len(rules) == 1
    x0, x1 = rules[0]
    assert x0 <= _DIV_X + 1 and x1 >= _DIV_X


def test_the_party_column_is_parted_from_the_case_number_column():
    for row in _segments(_page()):
        assert len(row) == 2, row
        assert "Case No." not in row[0]


def test_the_brace_itself_never_reaches_the_export():
    assert ")" not in " ".join(t for row in _segments(_page()) for t in row)


def test_without_the_rule_the_two_columns_weld(monkeypatch):
    """The behaviour being fixed, pinned from the other side: with the brace
    column unread, the gap test alone cannot part a caption set this way."""
    monkeypatch.setattr(P, "_page_brace_rules", lambda rows: [])
    welded = [r for r in _segments(_page()) if len(r) == 1]
    assert welded and any("Case No." in r[0] for r in welded)


def test_a_page_that_draws_nothing_is_untouched():
    assert P._page_brace_rules(
        P._cluster_rows(P._page_text_spans(_page(divider=None)[0]))) == []


# ── and only where it is really a divider ───────────────────────────────────

def test_a_scans_look_alikes_ride_with_the_braces():
    """OCR reads a column of ")" as "|", "J", "l" or "1" about as often as not.
    None is a word on its own, and none repeats down one column by accident —
    the repetition is the corroboration."""
    doc = fitz.open()
    pg = doc.new_page(width=792, height=792)
    for i, mark in enumerate([")", "|", "J", ")", "l", ")", "1", ")"]):
        y = 100 + 26 * i
        pg.insert_text((40, y), str(i + 1), fontsize=11)
        pg.insert_text((72, y), LEFT[i], fontsize=10)
        pg.insert_text((_DIV_X, y), mark, fontsize=10)
        pg.insert_text((_RIGHT_X, y), RIGHT[i], fontsize=10)
    assert len(P._page_brace_rules(P._cluster_rows(P._page_text_spans(pg)))) == 1


def test_but_a_column_of_look_alikes_alone_is_not_a_divider():
    """A MAJORITY must still be a true brace, or a column of "I" qualifies
    however often it repeats."""
    doc = fitz.open()
    pg = doc.new_page(width=792, height=792)
    for i, mark in enumerate(["I", "l", "J", "1", "I", "l", "J", "1"]):
        y = 100 + 26 * i
        pg.insert_text((40, y), str(i + 1), fontsize=11)
        pg.insert_text((72, y), LEFT[i], fontsize=10)
        pg.insert_text((_DIV_X, y), mark, fontsize=10)
        pg.insert_text((_RIGHT_X, y), RIGHT[i], fontsize=10)
    assert P._page_brace_rules(P._cluster_rows(P._page_text_spans(pg))) == []


def test_too_few_rows_is_punctuation():
    assert P._page_brace_rules(
        P._cluster_rows(P._page_text_spans(_page(rows=3)[0]))) == []


def test_a_brace_with_nothing_on_one_side_is_punctuation():
    """A trailing ")" closing every line of a parenthetical repeats at one x
    down many rows and divides nothing."""
    doc = fitz.open()
    pg = doc.new_page(width=792, height=792)
    for i in range(len(LEFT)):
        y = 100 + 26 * i
        pg.insert_text((40, y), str(i + 1), fontsize=11)
        pg.insert_text((72, y), LEFT[i], fontsize=10)
        pg.insert_text((_DIV_X, y), ")", fontsize=10)
    assert P._page_brace_rules(P._cluster_rows(P._page_text_spans(pg))) == []


def test_a_word_is_never_a_divider_segment():
    for t in ("Plaintiff,", "(2020)", "1.", "II.", "(a)", ")))) "):
        assert not P._brace_rule_segment(t), t
    for t in (")", "))", "|", "]", "J"):
        assert P._brace_rule_segment(t), t
