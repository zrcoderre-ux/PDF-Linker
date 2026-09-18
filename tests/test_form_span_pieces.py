"""A form pads INSIDE one span as readily as in front of it, and the export
cuts the span at the gap (`_form_text_pieces`, `_form_span_cells`).

MC-350EX sets the whole of item 18b as a single text object — "The attorney",
152 spaces, "attorney's fees or" — with the two checkboxes it asks about drawn
over the gap. Cut to its visible text that is ONE cell of 174 characters
opening at column 7, and the page came out 280 characters wide on a 140-column
sheet with the tail of the sentence sorted ahead of its own boxes.

Run:  cd PDF-Linker && python3 -m pytest tests/test_form_span_pieces.py -v
"""
import pathlib

import pytest

fitz = pytest.importorskip("fitz")

import pdf_linker as P

BLANK = (pathlib.Path(__file__).resolve().parent.parent / "Form Templates"
         / "MC-350EX Petition for Expedited Approval of Compromise of Claim "
           "(Minor or Person With a Disability).pdf")


def _pieces(*a, **k):
    return [(round(x, 1), t) for x, _r, t in P._form_text_pieces(*a, **k)]


class TestTheSplit:
    def test_a_wide_internal_gap_starts_a_new_piece(self):
        """The shape that produced the failure: two phrases in one span with
        the checkboxes they belong to drawn between them."""
        text = "The attorney" + " " * 157 + "attorney's fees or"
        got = _pieces(65.39, text, 9.0, x1=577.48)   # the blank's own span
        assert [t for _x, t in got] == ["The attorney", "attorney's fees or"]
        # Both ends are anchored on the span's own bbox, so the first piece
        # opens where the span does and the second lands near its right edge.
        assert got[0][0] == pytest.approx(65.4, abs=0.1)
        assert got[1][0] == pytest.approx(506.2, abs=5)   # measured: 506.23

    def test_running_prose_is_one_cell(self):
        """Nothing narrower than `_VIS_GAP_PT` is touched: a double space
        after a full stop is ~5 pt at 9 pt type, so a sentence stays whole."""
        text = ("the court does not otherwise order.  If your compromise "
                "qualifies and you choose to use this form")
        assert len(_pieces(36.0, text, 9.0, x1=520.0)) == 1

    def test_leading_padding_still_places_the_first_piece(self):
        """The rule `_form_text_x` states, read back off the pieces: a span
        that opens with forty spaces stands where its padding ends."""
        text = " " * 40 + "(describe):"
        got = _pieces(109.7, text, 9.0)
        assert [t for _x, t in got] == ["(describe):"]
        assert got[0][0] == pytest.approx(209.8, abs=1.0)
        # …and it is the SAME answer `_form_text_x` gives, which is where
        # that rule is written down: the splitter must not move a span the
        # form positions the way that one describes.
        assert got[0][0] == pytest.approx(P._form_text_x(109.7, text, 9.0),
                                          abs=0.1)

    def test_the_characters_own_boxes_need_no_advance_at_all(self):
        """Where the caller read them (`_form_raw_spans`), the gap is measured
        between the printed glyphs and the split needs no estimate — and a
        span drawn with no space characters between its pieces at all is cut
        just the same."""
        chars = ([(100.0 + 5 * i, 105.0 + 5 * i, c) for i, c in enumerate("Yes")]
                 + [(400.0 + 5 * i, 405.0 + 5 * i, c) for i, c in enumerate("No")])
        assert _pieces(100.0, "YesNo", 9.0, chars=chars) == [(100.0, "Yes"),
                                                             (400.0, "No")]


class TestTheBlankOnDisk:
    """The committed blank is the page the failure was found on."""

    def _pages(self):
        doc = fitz.open(BLANK)
        for pg in doc:
            yield pg, str(P._form_page_text(pg)).split("\n")

    def test_no_page_runs_past_its_own_width(self):
        """A pushed column stop is never clamped, so an overflowing cell used
        to drag every column right of it: page 5 ran to 280 characters."""
        for pg, lines in self._pages():
            cw, _rules, _pw = P._form_page_geometry(pg)
            cap = int(pg.rect.width / cw) + 8
            longest = max(len(l) for l in lines)
            assert longest <= cap, (pg.number + 1, longest, cap)

    def test_item_18b_reads_in_printed_order(self):
        """The whole span took the x of its FIRST word, so the tail of the
        sentence sorted ahead of the boxes it belongs to."""
        for pg, lines in self._pages():
            if pg.number != 4:
                continue
            row = next(l for l in lines if l.lstrip().startswith("b. The attorney"))
            assert row.index("has neither received") < row.index("has received or")
            assert row.index("has received or") < row.index("attorney's fees or")

    def test_a_field_box_no_longer_swallows_the_line_around_it(self):
        """The widget-drop test was asked of the SPAN's midpoint, and item
        19a(2) sets its sentence as one span with the amount field in the
        middle of it — so the page exported with the sentence gone and a bare
        `$` on the line where it had been. Asked of each PIECE, the words on
        either side of the box stand and only the box's own copy is dropped."""
        for pg, lines in self._pages():
            if pg.number != 5:
                continue
            assert any("requests authority to deposit or invest" in l
                       and "of the money or other property" in l for l in lines)
