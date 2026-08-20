"""The .txt export mirrors the page's own geometry, so it can be read SIDE BY
SIDE with the PDF.

A rendering that joins a row's pieces with one space destroys exactly what the
eye lines the two up by: a two-column caption collapses into one run, a
centered heading lands flush left, and the case-number column floats to
wherever the party name ends. Rows are laid out on a character grid derived
from each segment's own x instead (`_visual_row_text`, the `_form_layout` rule
at body-text width), and a plain page — an exhibit, a letter, an order off
pleading paper — is rendered positionally from its spans
(`_page_visual_text`), with real vertical gaps kept as blank lines.

The layout must cost the pipeline nothing it relies on: a body line at the
page's body-left edge renders byte-identically to the old join; running prose
split into spans at a style change is never padded apart (the citation parser
must not meet space runs this pass invented); the gutter regex still hands an
indented heading its own line number; and a Context quote collapses the
padding back out.

Run:  cd PDF-Linker && python3 -m pytest tests/test_visual_layout.py -v
"""
import logging

import pytest

fitz = pytest.importorskip("fitz")

import pdf_linker as P


# ── the row layout rule ──────────────────────────────────────────────────────

class TestVisualRowText:
    def test_body_left_line_is_byte_identical_to_the_old_join(self):
        # Column 0 must add nothing: ordinary body prose does not move.
        assert (P._visual_row_text([(110.0, "ordinary body text")], 110.0)
                == "ordinary body text")

    def test_second_column_lands_at_its_printed_column(self):
        line = P._visual_row_text(
            [(110.0, "ROXANE ESTRADA,"), (380.0, "Case No.: 25STCV37838")],
            110.0)
        assert line.index("Case No.") == round((380.0 - 110.0) / P._VIS_CHAR_W)

    def test_the_case_number_column_aligns_across_rows(self):
        # The point of the exercise: two rows whose right cells share an x
        # share a column, whatever their left cells' lengths.
        rows = [[(110.0, "ROXANE ESTRADA,"), (380.0, "Case No.: 25STCV37838")],
                [(110.0, "vs."), (380.0, "Dept.: 55")]]
        a, b = (P._visual_row_text(r, 110.0) for r in rows)
        assert a.index("Case No.") == b.index("Dept.")

    def test_an_indented_first_segment_keeps_its_indent(self):
        line = P._visual_row_text([(250.0, "NOTICE OF MOTION")], 110.0)
        assert line.startswith(" " * round(140.0 / P._VIS_CHAR_W) + "NOTICE")

    def test_a_segment_left_of_column_zero_is_clamped_not_negative(self):
        assert P._visual_row_text([(20.0, "MARGIN LABEL")], 110.0) \
            == "MARGIN LABEL"

    def test_overlapping_columns_never_weld(self):
        # A long scrubbed cell can run past the next cell's column; the
        # printed boundary becomes a single space, never a weld.
        line = P._visual_row_text(
            [(110.0, "A VERY LONG PARTY NAME THAT RUNS PAST"), (150.0, "X")],
            110.0)
        assert "PAST X" in line

    def test_a_stray_far_right_x_is_capped(self):
        line = P._visual_row_text([(110.0, "a"), (9000.0, "b")], 110.0)
        assert len(line) <= P._FORM_MAX_COL + 1

    def test_body_left_comes_from_numbered_rows_only(self):
        # An out-of-band margin label left of the body must not own column 0
        # and indent every body line by the width of the margin.
        rows = [(None, [(20.0, "FIRM SIDEBAR")]),
                (1, [(110.0, "Body line one.")]),
                (2, [(110.0, "Body line two.")])]
        assert P._rows_body_left(rows) == 110.0


# ── the pleading page, end to end ────────────────────────────────────────────

class TestPleadingExport:
    @pytest.fixture
    def txt(self, tmp_path):
        doc = fitz.open()
        pg = doc.new_page()
        y = 90
        for i in range(1, 20):
            pg.insert_text((40, y), f"{i:>2}", fontsize=10)
            y += 20
        # Caption rows: party column + case-number column (3 rows, so the
        # page-level column band has the multi-row support it requires).
        pg.insert_text((80, 90), "ROXANE ESTRADA, an individual,", fontsize=10)
        pg.insert_text((380, 90), "Case No.: 25STCV37838", fontsize=10)
        pg.insert_text((80, 110), "vs.", fontsize=10)
        pg.insert_text((380, 110), "Dept.: 55", fontsize=10)
        pg.insert_text((380, 130), "Hearing Date: 9/9/2026", fontsize=10)
        # A centered heading on its own numbered line, then ordinary body.
        pg.insert_text((250, 150), "NOTICE OF MOTION", fontsize=10)
        for i in range(5, 20):
            pg.insert_text((80, 90 + (i - 1) * 20),
                           f"Body line {i} of the memorandum.", fontsize=10)
        path = tmp_path / "pleading.pdf"
        doc.save(path)
        doc.close()
        doc = fitz.open(path)
        assert P._write_text_version(path, doc, logging.getLogger("t"))
        return (tmp_path / "Text Files" / "pleading.txt").read_text("utf-8")

    def test_the_case_number_column_aligns_down_the_caption(self, txt):
        lines = txt.splitlines()
        a = next(l for l in lines if "Case No.:" in l)
        b = next(l for l in lines if "Dept.:" in l)
        assert a.index("Case No.:") == b.index("Dept.:")
        assert a.index("Case No.:") > len(" 1  ROXANE ESTRADA, an individual,")

    def test_a_centered_heading_is_indented(self, txt):
        line = next(l for l in txt.splitlines() if "NOTICE OF MOTION" in l)
        # After the 4-char gutter prefix the body carries its own indent.
        assert line.startswith(" 4      ")

    def test_an_ordinary_body_line_does_not_move(self, txt):
        # Body-left text keeps the exact old rendering: number, two spaces,
        # text at column 0.
        assert "\n 5  Body line 5 of the memorandum." in txt

    def test_the_gutter_regex_still_owns_an_indented_heading(self, txt):
        parsed = P._pn_body_lines(txt)
        gutter = next(g for _p, g, t in parsed if "NOTICE OF MOTION" in t)
        assert gutter == "4"

    def test_a_context_quote_collapses_the_padding(self, txt):
        parsed = P._pn_body_lines(txt)
        quote = P._pn_context(parsed, "Estrada")
        assert "ESTRADA" in quote.upper()
        assert "  " not in quote


# ── the plain page ───────────────────────────────────────────────────────────

class TestPlainPageVisualText:
    def _page(self, draw):
        doc = fitz.open()
        pg = doc.new_page()
        draw(pg)
        pg._doc_ref = doc
        return pg

    def test_columns_and_indent_land_where_printed(self):
        pg = self._page(lambda p: (
            p.insert_text((250, 80), "ORDER OF DISMISSAL", fontsize=11),
            p.insert_text((72, 120), "The court orders as follows.", fontsize=11),
            p.insert_text((72, 140), "Date:", fontsize=11),
            p.insert_text((300, 140), "Judge of the Superior Court", fontsize=11),
        ))
        out = P._page_visual_text(pg)
        lines = out.splitlines()
        title = next(l for l in lines if "ORDER OF DISMISSAL" in l)
        assert title.index("ORDER") == round((250 - 72) / P._VIS_CHAR_W)
        date = next(l for l in lines if "Date:" in l)
        assert date.index("Judge") == round((300 - 72) / P._VIS_CHAR_W)

    def test_a_real_vertical_gap_is_a_blank_line(self):
        pg = self._page(lambda p: (
            [p.insert_text((72, 80 + i * 14), f"line {i}", fontsize=11)
             for i in range(5)],
            p.insert_text((72, 300), "signature block", fontsize=11),
        ))
        out = P._page_visual_text(pg)
        assert "\n\n" in out          # the gap survives
        blanks = out.split("signature")[0].splitlines()
        assert blanks[-P._VIS_MAX_BLANKS - 2] != ""  # …and is capped

    def test_running_prose_is_never_padded_apart(self):
        # A style change splits a line into spans a point or two apart; the
        # citation parser must never meet a space run this pass invented.
        def draw(p):
            w = fitz.get_text_length("Ewald v. Nationstar Mortgage, LLC ",
                                     fontsize=11)
            p.insert_text((72, 100), "Ewald v. Nationstar Mortgage, LLC ",
                          fontsize=11)
            p.insert_text((72 + w + 1.0, 100), "(2017) 13 Cal.App.5th 947",
                          fontsize=11)
        out = P._page_visual_text(self._page(draw))
        assert "LLC (2017) 13 Cal.App.5th 947" in out

    def test_an_empty_page_yields_none(self):
        assert P._page_visual_text(self._page(lambda p: None)) is None

    def test_the_export_writer_uses_it_for_plain_pages(self, tmp_path):
        doc = fitz.open()
        pg = doc.new_page()
        pg.insert_text((250, 80), "EXHIBIT A", fontsize=11)
        pg.insert_text((72, 140), "A letter, left aligned.", fontsize=11)
        path = tmp_path / "exhibit.pdf"
        doc.save(path)
        doc.close()
        doc = fitz.open(path)
        assert P._write_text_version(path, doc, logging.getLogger("t"))
        txt = (tmp_path / "Text Files" / "exhibit.txt").read_text("utf-8")
        line = next(l for l in txt.splitlines() if "EXHIBIT A" in l)
        assert line.index("EXHIBIT") == round((250 - 72) / P._VIS_CHAR_W)
