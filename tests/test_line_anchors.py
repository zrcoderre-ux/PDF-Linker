"""Unit tests for pdf_linker's pleading-paper line-anchor detection.

Unlike the pseudonymization tests these need geometry, so each test synthesises
a one-page PDF in memory with PyMuPDF — no fixture files are checked in. The
page imitates the layout that broke the extractor in the wild: a 24 pt gutter of
line numbers beside a caption whose right-hand column runs at a ~11 pt lead, so
one gutter number owns two or three physical rows.

Run with: pytest tests/test_line_anchors.py
"""
import importlib.util
import re
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


def _rows(page):
    """(line_num, body_text) in reading order — keeps continuation rows
    (line_num=None) that a line_num-keyed dict would collapse."""
    return [(a["line_num"], a["body_text"])
            for a in sorted(pl._detect_line_anchors(page), key=lambda a: a["y_mid"])]


class TestReadingOrder:
    """Rows sharing one gutter number must not interleave, and rows STACKED in
    one column under a number must stay on their own lines (a dense letterhead),
    not weld into one."""

    def test_two_rows_under_one_number_stay_on_their_own_lines(self):
        page = _page([
            (LEFT_X, FIRST_Y - 8, "SCHILLECI & TORTORICI, P.C."),
            (LEFT_X, FIRST_Y + 4, "JASON P. TORTORICI, STATE BAR NO. 207972"),
        ])
        rows = _rows(page)
        assert (1, "SCHILLECI & TORTORICI, P.C.") in rows
        assert (None, "JASON P. TORTORICI, STATE BAR NO. 207972") in rows
        # The number owns the first row; the second is a continuation, in order.
        i = rows.index((1, "SCHILLECI & TORTORICI, P.C."))
        assert rows[i + 1] == (None, "JASON P. TORTORICI, STATE BAR NO. 207972")

    def test_caption_columns_pair_left_to_right_then_continue(self):
        """Left party column + a right column running at half the gutter lead:
        the party name pairs with the first caption line; the second caption
        line continues below."""
        page = _page([
            (LEFT_X, FIRST_Y + 7 * LEAD, "ROXANE ESTRADA,"),
            (RIGHT_X, FIRST_Y + 7 * LEAD - 5, "Case No.: 25STCV37838"),
            (RIGHT_X, FIRST_Y + 7 * LEAD + 6, "Complaint Filed: Dec 29, 2025"),
        ])
        rows = _rows(page)
        assert (8, "ROXANE ESTRADA, Case No.: 25STCV37838") in rows
        assert (None, "Complaint Filed: Dec 29, 2025") in rows

    def test_left_column_is_never_reordered_into_the_right(self):
        page = _page([
            (LEFT_X, FIRST_Y + 9 * LEAD, "AZUL CONCRETO, INC.,"),
            (RIGHT_X, FIRST_Y + 9 * LEAD - 5, "NOTICE AND MOTION TO STRIKE"),
        ])
        body = _lines(page)[10]
        assert body.index("AZUL") < body.index("NOTICE")

    def test_segments_stay_per_column(self):
        # The right column needs _COLUMN_BAND_MIN_ROWS rows of support to be a
        # page column at all (as any real caption column has).
        page = _page([
            (LEFT_X, FIRST_Y + 7 * LEAD, "ROXANE ESTRADA,"),
            (RIGHT_X, FIRST_Y + 7 * LEAD, "Case No.: 25STCV37838"),
            (RIGHT_X, FIRST_Y + 8 * LEAD, "NOTICE OF MOTION AND"),
            (RIGHT_X, FIRST_Y + 9 * LEAD, "MOTION TO STRIKE"),
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


class TestPrescanOrderIndependence:
    """The folder-wide pre-scan must learn localities/identifiers from every
    file before any file is scrubbed, regardless of processing order."""

    def _text_pdf(self, path, lines):
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        for i, ln in enumerate(lines):
            page.insert_text((72, 100 + i * 24), ln, fontsize=11)
        doc.save(str(path))
        doc.close()

    def test_localities_kept_verbatim_folder_wide(self, tmp_path):
        import logging
        # Under the current policy the locality (city/state/ZIP) is kept
        # verbatim — only the house number and street name inside an address
        # are faked — so register_localities registers nothing and a bare city
        # or ZIP is left as written no matter which file taught the address.
        self._text_pdf(tmp_path / "a_bare.pdf",
                       ["Plaintiff resides in Montebello, California."])
        self._text_pdf(tmp_path / "b_addr.pdf",
                       ["Service at 414 S. Maple Ave. Montebello, CA 90640."])
        reg = pl._PnFakeRegistry()
        pz = pl.Pseudonymizer(pl._pn_build_terms([], [], [], reg),
                              list(pl._PN_DEFAULT_DETECTORS), reg)
        pdfs = sorted((tmp_path).glob("*.pdf"))
        pl._pn_prescan_folder(pdfs, pz, logging.getLogger("t"))
        assert not any(r["category"] in ("city", "zip") for r in pz.records.values())
        out = pz.apply("resides in Montebello, California.")
        assert "Montebello" in out and "California" in out

    def test_identifier_learned_folder_wide(self, tmp_path):
        import logging
        self._text_pdf(tmp_path / "one.pdf", ["STATE BAR NO. 207972"])
        reg = pl._PnFakeRegistry()
        pz = pl.Pseudonymizer(pl._pn_build_terms([], [], [], reg),
                              list(pl._PN_DEFAULT_DETECTORS), reg)
        pl._pn_prescan_folder(sorted(tmp_path.glob("*.pdf")), pz,
                              logging.getLogger("t"))
        assert any(r["category"] == "bar_number" for r in pz.records.values())


class TestSuperscriptReattachment:
    """A superscript ("5th", a footnote mark) is set smaller than the body and
    its raised baseline pulls it onto the row above, where it lands as an orphan
    segment and skews that row toward the wrong gutter number. It must attach to
    the base word instead."""

    def _page_with_superscript(self):
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        for i in range(28):
            page.insert_text((GUTTER_X, FIRST_Y + i * LEAD), str(i + 1), fontsize=12)
        # Line 1 body, then a base word "5" on line 2 with a raised "th".
        page.insert_text((LEFT_X, FIRST_Y), "LAW OFFICE OF EXAMPLE", fontsize=11)
        base_y = FIRST_Y + LEAD
        page.insert_text((LEFT_X, base_y), "1055 E Colorado Blvd., 5", fontsize=11)
        page.insert_text((LEFT_X + 150, base_y - 4), "th", fontsize=8)   # superscript
        page.insert_text((LEFT_X + 162, base_y), "Floor", fontsize=11)
        page._doc_ref = doc
        return page

    def test_superscript_joins_its_base_word(self):
        lines = _lines(self._page_with_superscript())
        assert "5th" in lines[2].replace(" th", "th")  # base + superscript reunited
        assert "th" not in lines[1]                     # not orphaned onto line 1

    def test_base_row_maps_to_its_own_gutter_number(self):
        lines = _lines(self._page_with_superscript())
        assert "1055 E Colorado Blvd." in lines[2]
        assert "1055" not in lines.get(1, "")


class TestDenseLetterheadDoesNotCollapse:
    """A tightly-set attorney letterhead runs at ~half the numbered-body lead,
    so two physical rows fall under one gutter number. They must stay on their
    own lines instead of welding into 'Paul Green, Esq. (SBN 237707) LAW OFFICE
    OF PAUL GREEN'."""

    def _letterhead_page(self):
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        for i in range(28):
            page.insert_text((GUTTER_X, FIRST_Y + i * LEAD), str(i + 1), fontsize=12)
        # Two single-spaced letterhead rows in the vertical span of gutter 1.
        page.insert_text((LEFT_X, FIRST_Y - 10), "Paul Green, Esq. (SBN 237707)", fontsize=11)
        page.insert_text((LEFT_X, FIRST_Y + 2), "LAW OFFICE OF PAUL GREEN", fontsize=11)
        page._doc_ref = doc
        return page

    def test_letterhead_rows_are_not_welded(self):
        bodies = [b for _n, b in _rows(self._letterhead_page())]
        assert "Paul Green, Esq. (SBN 237707)" in bodies
        assert "LAW OFFICE OF PAUL GREEN" in bodies
        # No line contains BOTH names welded together.
        assert not any("Esq." in b and "LAW OFFICE" in b for b in bodies)

    def test_first_row_keeps_the_number_second_is_a_continuation(self):
        rows = _rows(self._letterhead_page())
        assert rows[0] == (1, "Paul Green, Esq. (SBN 237707)")
        assert rows[1] == (None, "LAW OFFICE OF PAUL GREEN")


class TestLabelValueGapsAreNotColumns:
    """Column-splice-aware banding: a wide gap inside a caption's right column
    ("Trial Date:   November 16, 2026", "Department:   55") is a tab, not a
    page column — only an x where several distinct rows break is a column.
    Cutting those pairs into separate column streams hid the value from its
    label-anchored detector, so the REAL department number rode along into
    the export."""

    def _caption_page(self):
        y = FIRST_Y + 10 * LEAD
        return _page([
            # Letterhead above the caption, as on a real filing's page 1.
            (LEFT_X, FIRST_Y, "Parth Shah (SBN 304347)"),
            (LEFT_X, FIRST_Y + LEAD, "DORIOTT, POSTAJIAN & SHAH"),
            (LEFT_X, FIRST_Y + 2 * LEAD, "1310 Westwood Blvd."),
            (LEFT_X, FIRST_Y + 3 * LEAD, "Los Angeles, CA 90024"),
            (LEFT_X, FIRST_Y + 4 * LEAD, "(424) 248-0595"),
            (LEFT_X, FIRST_Y + 5 * LEAD, "Attorneys for Plaintiff"),
            (LEFT_X, FIRST_Y + 7 * LEAD, "SUPERIOR COURT OF CALIFORNIA"),
            (LEFT_X, FIRST_Y + 8 * LEAD, "COUNTY OF LOS ANGELES"),
            # Left column: the party block (well-supported band).
            (LEFT_X, y, "JOSEPH PALLADINO (an individual),"),
            (LEFT_X, y + LEAD, "vs."),
            (LEFT_X, y + 2 * LEAD, "RTX CORPORATION (a Delaware"),
            (LEFT_X, y + 3 * LEAD, "corporation); and DOES 1 to 100,"),
            # Right column: the caption block (well-supported band) with
            # label-value tab gaps that must NOT band on their own.
            (RIGHT_X, y, "Case No.: 23STCV31247"),
            (RIGHT_X, y + LEAD, "Trial Date:"),
            (RIGHT_X + 95, y + LEAD, "November 16, 2026"),
            (RIGHT_X, y + 2 * LEAD, "Department:"),
            (RIGHT_X + 95, y + 2 * LEAD, "55"),
        ])

    def test_label_and_value_stay_in_one_segment(self):
        rows = {a["line_num"]: [t for _x, t in a["segments"]]
                for a in pl._detect_line_anchors(self._caption_page())}
        assert rows[12] == ["vs.", "Trial Date: November 16, 2026"]
        assert rows[13] == ["RTX CORPORATION (a Delaware", "Department: 55"]

    def test_supported_columns_still_split(self):
        rows = {a["line_num"]: [t for _x, t in a["segments"]]
                for a in pl._detect_line_anchors(self._caption_page())}
        assert rows[11] == ["JOSEPH PALLADINO (an individual),",
                            "Case No.: 23STCV31247"]

    def test_detect_text_keeps_the_pair_on_one_line(self):
        text = pl._page_detect_text(self._caption_page())
        assert "Department: 55" in text.splitlines()

    def test_department_number_is_faked_from_a_caption(self):
        """End to end: the label-anchored department detector sees the pair
        the extraction hands it, so the real number is registered and faked."""
        z = pl.Pseudonymizer([], {}, registry=pl._PnFakeRegistry())
        z.register_court_names(pl._page_detect_text(self._caption_page()))
        rows = pl._page_lined_rows(self._caption_page())
        bodies = "\n".join(pl._pn_apply_page_rows(z, rows))
        assert "Department: 55" not in bodies
        assert re.search(r"Department: \d+", bodies)


class TestDespliceGeometry:
    """Normalize-before-detect: character-geometry de-splicing of welded spans
    (`_split_char_runs`, `_despliced_body_spans`, and the `_page_lined_rows`
    retry). The pure splitter is exercised on synthetic glyph boxes; the
    rawdict plumbing on a real (clean) page, where it must change nothing."""

    def test_char_runs_split_at_column_jumps(self):
        def ch(x, w, c):
            return (x, x + w, c, 700.0)
        chars = []
        x = 100.0
        for c in "CULTUREEDIT,":
            chars.append(ch(x, 6, c)); x += 6
        x = 350.0                              # forward jump: other column
        for c in "Attorneys":
            chars.append(ch(x, 6, c)); x += 6
        x = 172.0                              # backward jump: interleave
        for c in " LLC":
            chars.append(ch(x, 6, c)); x += 6
        runs = pl._split_char_runs(chars)
        assert [r[3].strip() for r in runs] == ["CULTUREEDIT,", "Attorneys", "LLC"]

    def test_char_runs_keep_kerned_text_whole(self):
        chars, x = [], 100.0
        for c in "Hello World":
            chars.append((x, x + 6, c, 700.0)); x += 5.5   # slight overlap
        runs = pl._split_char_runs(chars)
        assert len(runs) == 1 and runs[0][3] == "Hello World"

    def test_desplice_is_identity_on_clean_page(self):
        page = _page([(LEFT_X, FIRST_Y, "ALEJANDRO ORELLANA,"),
                      (RIGHT_X, FIRST_Y, "Case No. 24STCV06764"),
                      (LEFT_X, FIRST_Y + LEAD, "Plaintiff,")])
        normal = [(a["line_num"], a["body_text"])
                  for a in pl._detect_line_anchors(page)]
        cured = [(a["line_num"], a["body_text"])
                 for a in pl._detect_line_anchors(page, desplice=True)]
        assert normal == cured

    def test_lined_rows_adopt_cure_when_it_clears_the_splice(self, monkeypatch):
        welded = [{"line_num": 1, "y_mid": 90.0,
                   "segments": [(110.0, "CULTUREEDITservice of process")],
                   "body_text": "CULTUREEDITservice of process"}]
        clean = [{"line_num": 1, "y_mid": 90.0,
                  "segments": [(110.0, "CULTUREEDIT, LLC"),
                               (380.0, "service of process")],
                  "body_text": "CULTUREEDIT, LLC service of process"}]
        def fake_detect(page, desplice=False):
            return clean if desplice else welded
        monkeypatch.setattr(pl, "_detect_line_anchors", fake_detect)
        rows = pl._page_lined_rows(object())
        assert rows == [(1, [(110.0, "CULTUREEDIT, LLC"),
                             (380.0, "service of process")])]

    def test_lined_rows_keep_original_when_cure_does_not_help(self, monkeypatch):
        welded = [{"line_num": 1, "y_mid": 90.0,
                   "segments": [(110.0, "CULTUREEDITservice of process")],
                   "body_text": "CULTUREEDITservice of process"}]
        def fake_detect(page, desplice=False):
            return welded
        monkeypatch.setattr(pl, "_detect_line_anchors", fake_detect)
        rows = pl._page_lined_rows(object())
        assert rows == [(1, [(110.0, "CULTUREEDITservice of process")])]
