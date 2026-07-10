"""Unit tests for pdf_linker's pleading-paper line-anchor detection.

Unlike the pseudonymization tests these need geometry, so each test synthesises
a one-page PDF in memory with PyMuPDF — no fixture files are checked in. The
page imitates the layout that broke the extractor in the wild: a 24 pt gutter of
line numbers beside a caption whose right-hand column runs at a ~11 pt lead, so
one gutter number owns two or three physical rows.

Run with: pytest tests/test_line_anchors.py
"""
import importlib.util
from pathlib import Path

import fitz
import pytest

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pdf_linker", _ROOT / "pdf_linker.py")
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)

GUTTER_X = 80.0
LEFT_X = 110.0
RIGHT_X = 380.0
FIRST_Y = 90.0
LEAD = 24.0


def _page(rows, n_numbers=28):
    """A page with `n_numbers` gutter numbers at a 24 pt lead and `rows` of body
    text, each row a (x, y, text) triple. Returns the fitz.Page."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for i in range(n_numbers):
        page.insert_text((GUTTER_X, FIRST_Y + i * LEAD), str(i + 1), fontsize=12)
    for x, y, text in rows:
        page.insert_text((x, y), text, fontsize=11)
    # Keep the doc alive for the caller.
    page._doc_ref = doc
    return page


def _lines(page):
    return {a["line_num"]: a["body_text"] for a in pl._detect_line_anchors(page)}


class TestReadingOrder:
    """Rows sharing one gutter number must not interleave."""

    def test_two_rows_under_one_number_stay_in_order(self):
        page = _page([
            (LEFT_X, FIRST_Y - 8, "SCHILLECI & TORTORICI, P.C."),
            (LEFT_X, FIRST_Y + 4, "JASON P. TORTORICI, STATE BAR NO. 207972"),
        ])
        assert _lines(page)[1] == (
            "SCHILLECI & TORTORICI, P.C. JASON P. TORTORICI, STATE BAR NO. 207972")

    def test_caption_columns_do_not_splice(self):
        """Left party column + a right column running at half the gutter lead."""
        page = _page([
            (LEFT_X, FIRST_Y + 7 * LEAD, "ROXANE ESTRADA,"),
            (RIGHT_X, FIRST_Y + 7 * LEAD - 5, "Case No.: 25STCV37838"),
            (RIGHT_X, FIRST_Y + 7 * LEAD + 6, "Complaint Filed: Dec 29, 2025"),
        ])
        body = _lines(page)[8]
        assert body == ("ROXANE ESTRADA, Case No.: 25STCV37838 "
                        "Complaint Filed: Dec 29, 2025")

    def test_left_column_is_never_reordered_into_the_right(self):
        page = _page([
            (LEFT_X, FIRST_Y + 9 * LEAD, "AZUL CONCRETO, INC.,"),
            (RIGHT_X, FIRST_Y + 9 * LEAD - 5, "NOTICE AND MOTION TO STRIKE"),
        ])
        body = _lines(page)[10]
        assert body.index("AZUL") < body.index("NOTICE")

    def test_segments_stay_per_column(self):
        page = _page([
            (LEFT_X, FIRST_Y + 7 * LEAD, "ROXANE ESTRADA,"),
            (RIGHT_X, FIRST_Y + 7 * LEAD, "Case No.: 25STCV37838"),
        ])
        anchor = [a for a in pl._detect_line_anchors(page) if a["line_num"] == 8][0]
        assert [t for _x, t in anchor["segments"]] == [
            "ROXANE ESTRADA,", "Case No.: 25STCV37838"]


class TestFooterExclusion:
    """Running footers and printed page numbers never join a numbered line."""

    def test_page_number_below_the_last_line_is_dropped(self):
        last_y = FIRST_Y + 27 * LEAD
        page = _page([
            (LEFT_X, last_y, "(FAC, p. 8:17-18.)"),
            (RIGHT_X, last_y + 18, "1"),                 # printed page number
        ])
        assert _lines(page)[28] == "(FAC, p. 8:17-18.)"

    def test_running_footer_is_dropped(self):
        last_y = FIRST_Y + 27 * LEAD
        page = _page([
            (LEFT_X, last_y, "resulting in a flood on"),
            (LEFT_X, last_y + 20, "OPPOSITION TO DEFENDANT'S MOTION TO STRIKE"),
        ])
        assert _lines(page)[28] == "resulting in a flood on"

    def test_tolerance_is_half_the_page_lead(self):
        """A row 13 pt from its number (>= half of a 24 pt lead) is furniture."""
        page = _page([(LEFT_X, FIRST_Y + 13, "orphan")])
        assert 1 not in _lines(page)

    def test_row_within_half_a_lead_is_kept(self):
        page = _page([(LEFT_X, FIRST_Y + 10, "adopted")])
        assert _lines(page).get(1) == "adopted"


class TestCaptionDivider:
    def test_brace_column_is_dropped(self):
        page = _page([
            (LEFT_X, FIRST_Y + 13 * LEAD, "Dept. 53"),
            (300.0, FIRST_Y + 13 * LEAD + 4, ")"),
        ])
        assert _lines(page)[14] == "Dept. 53"

    def test_regex_matches_only_bare_punctuation(self):
        assert pl._CAPTION_DIVIDER_RE.match(")")
        assert pl._CAPTION_DIVIDER_RE.match("))")
        assert not pl._CAPTION_DIVIDER_RE.match(") Dept. 53")


class TestNonPleadingPages:
    def test_page_without_a_gutter_returns_empty(self):
        page = _page([(LEFT_X, 200.0, "EXHIBIT A")], n_numbers=0)
        assert pl._detect_line_anchors(page) == []

    def test_too_few_line_numbers_returns_empty(self):
        page = _page([(LEFT_X, 200.0, "cover sheet")], n_numbers=3)
        assert pl._detect_line_anchors(page) == []


class TestCaptionDividerGluedToText:
    def test_leading_brace_is_stripped(self):
        page = _page([
            (LEFT_X, FIRST_Y + 7 * LEAD, "ROXANE ESTRADA,"),
            (RIGHT_X, FIRST_Y + 7 * LEAD, ") Case No.: 25STCV37838"),
        ])
        assert _lines(page)[8] == "ROXANE ESTRADA, Case No.: 25STCV37838"

    def test_an_opening_paren_is_never_stripped(self):
        page = _page([(LEFT_X, FIRST_Y + 27 * LEAD, "(FAC, p. 8:17-18.)")])
        assert _lines(page)[28] == "(FAC, p. 8:17-18.)"

    def test_lead_regex_needs_trailing_space(self):
        assert pl._CAPTION_DIVIDER_LEAD_RE.match(") Case No.")
        assert not pl._CAPTION_DIVIDER_LEAD_RE.match(")Case")
        assert not pl._CAPTION_DIVIDER_LEAD_RE.match("(FAC, p. 8:17-18.)")
