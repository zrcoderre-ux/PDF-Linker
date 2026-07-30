"""
Fillable Judicial Council forms (a default-judgment packet's CIV-100, the
discretionary complaint forms PLD-C-001 / PLD-PI-001 and their cause-of-action
attachments) are AcroForms: the answers live in WIDGET annotations, not in the
page content stream. Ordinary extraction prints the blank form's boilerplate and
then every answer in one unanchored heap, and a checkbox comes out worse than
that — a CHECKED box paints the ZapfDingbats check glyph, which extracts as a
bare "3", while an UNCHECKED box paints nothing at all. So nothing in the export
distinguished "clerk's judgment requested" from "not requested".

These pages are rebuilt from their widgets instead: [X]/[ ] beside the caption
each box governs, every field value inlined at its own label.

Run:  cd PDF-Linker && python3 -m pytest tests/test_form_fields.py -v
"""
import importlib.util
import logging
from pathlib import Path

import fitz
import pytest

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pdf_linker", _ROOT / "pdf_linker.py")
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)

log = logging.getLogger("test")
DET = {k: pl._PN_DETECTORS[k] for k in pl._PN_DEFAULT_DETECTORS}


# ── fixtures: minimal but structurally faithful Judicial Council forms ───────

def _page(doc):
    return doc.new_page(width=612, height=792)


def _static(page, x, y, s, size=9):
    page.insert_text((x, y), s, fontsize=size, fontname="helv")


def _checkbox(page, name, x, y, on, size=10.0):
    w = fitz.Widget()
    w.field_name = name
    w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    w.rect = fitz.Rect(x, y, x + size, y + size)
    w.field_value = on
    # A real form's checkbox is a PRINTED square, so the fixture draws one too:
    # it is what survives when the widgets are flattened away.
    w.border_width = 0.7
    w.border_color = (0, 0, 0)
    page.add_widget(w)


def _text(page, name, x, y, value, w_=200.0, h=15.0):
    w = fitz.Widget()
    w.field_name = name
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.rect = fitz.Rect(x, y, x + w_, y + h)
    w.field_value = value
    w.text_fontsize = 8
    page.add_widget(w)


def _civ100():
    """A filled CIV-100 (Request for Entry of Default) — the mandatory form at
    the front of every default-judgment packet."""
    doc = fitz.open()
    p = _page(doc)
    _static(p, 40, 110, "SUPERIOR COURT OF CALIFORNIA, COUNTY OF", 7)
    _static(p, 40, 150, "PLAINTIFF:", 7)
    _static(p, 40, 170, "DEFENDANT:", 7)
    _static(p, 400, 150, "CASE NUMBER:", 7)
    _static(p, 60, 230, "1. TO THE CLERK: On the complaint filed", 8)
    _static(p, 75, 250, "a. Enter default of defendant (names):", 8)
    _static(p, 75, 275, "b. Enter clerk's judgment", 8)
    _static(p, 90, 295, "(1) For restitution of the premises only", 8)
    _static(p, 90, 315, "(2) Under Code of Civil Procedure section 585(a)", 8)
    _static(p, 75, 340, "c. Enter court judgment under CCP 585(b)", 8)
    _static(p, 75, 390, "a. Demand of complaint", 8)
    _static(p, 300, 390, "$", 8)
    _static(p, 40, 745, "CIV-100 [Rev. January 1, 2023]", 6)
    _text(p, "county", 250, 103, "LOS ANGELES", 150.0)
    _text(p, "plaintiff", 95, 143, "ACME LENDING, LLC")
    _text(p, "defendant", 100, 163, "ERNEST N RAMIREZ")
    _text(p, "caseno", 460, 143, "24STCV24253", 100.0)
    _checkbox(p, "cb_1a", 62, 244, True)
    _text(p, "f_1a", 240, 243, "ERNEST N RAMIREZ")
    _checkbox(p, "cb_1b", 62, 269, False)
    _checkbox(p, "cb_1b1", 78, 289, False)
    _checkbox(p, "cb_1b2", 78, 309, True)
    _checkbox(p, "cb_1c", 62, 334, True)
    _text(p, "f_2a", 310, 383, "12,500.00", 90.0)
    return doc


def _pldc001():
    """A filled PLD-C-001 (Complaint—Contract): the discretionary complaint form,
    whose causes of action are selected purely by checkbox."""
    doc = fitz.open()
    p = _page(doc)
    _static(p, 60, 200, "1. This pleading includes the following:", 8)
    _static(p, 80, 225, "a. Breach of Contract", 8)
    _static(p, 80, 245, "b. Common Counts", 8)
    _static(p, 80, 265, "c. Fraud", 8)
    _static(p, 60, 300, "2. Plaintiff is", 8)
    _static(p, 80, 325, "an individual", 8)
    _static(p, 80, 345, "a corporation", 8)
    _static(p, 40, 745, "PLD-C-001 [Rev. January 1, 2007]", 6)
    _checkbox(p, "coa_a", 64, 219, True)
    _checkbox(p, "coa_b", 64, 239, True)
    _checkbox(p, "coa_c", 64, 259, False)
    _checkbox(p, "kind_ind", 64, 319, False)
    _checkbox(p, "kind_corp", 64, 339, True)
    return doc


def _lines(text):
    return [ln for ln in text.split("\n")]


def _line_with(text, needle):
    hits = [ln for ln in _lines(text) if needle in ln]
    assert hits, f"no line containing {needle!r} in:\n{text}"
    return hits[0]


# ── what plain extraction does, and why the form path exists ─────────────────

def test_plain_extraction_cannot_represent_a_checkbox():
    # The premise of the whole feature: with ordinary extraction a checked box is
    # an anonymous "3" and an unchecked box is nothing at all, so the export
    # cannot say which items were selected.
    doc = _civ100()
    raw = doc[0].get_text("text")
    assert "3" in raw                                   # the check glyph
    assert "[X]" not in raw and "[ ]" not in raw
    # ...and the answers are nowhere near the labels they answer
    lines = _lines(raw)
    assert lines.index("ACME LENDING, LLC") > lines.index("PLAINTIFF:") + 1


# ── checkbox state, the load-bearing fact ───────────────────────────────────

def test_every_checkbox_state_is_rendered_beside_its_caption():
    text = pl._form_page_text(_civ100()[0])
    assert "[X] a. Enter default of defendant" in text
    assert "[ ] b. Enter clerk's judgment" in text
    assert "[ ] (1) For restitution of the premises only" in text
    assert "[X] (2) Under Code of Civil Procedure section 585(a)" in text
    assert "[X] c. Enter court judgment under CCP 585(b)" in text
    # exactly the five boxes, three of them checked — and the raw ZapfDingbats
    # check glyph (a bare "3") never survives beside the rendered state
    assert text.count("[X]") == 3 and text.count("[ ]") == 2
    body = _lines(text)[1:]                            # past the banner
    assert not [ln for ln in body if ln.strip() == "3"]


def test_unchecked_causes_of_action_are_distinguishable():
    # On a discretionary complaint form the checkboxes ARE the pleading: which
    # causes of action are alleged is nothing but their state.
    text = pl._form_page_text(_pldc001()[0])
    assert "[X] a. Breach of Contract" in text
    assert "[X] b. Common Counts" in text
    assert "[ ] c. Fraud" in text
    assert "[ ] an individual" in text
    assert "[X] a corporation" in text


def test_banner_names_the_form_and_tallies_the_boxes():
    civ = pl._form_page_text(_civ100()[0])
    assert civ.startswith("[fillable form CIV-100: 5 checkbox(es), 3 checked]")
    pld = pl._form_page_text(_pldc001()[0])
    assert pld.startswith("[fillable form PLD-C-001: 5 checkbox(es), 3 checked]")


# ── field values land beside their own labels ───────────────────────────────

def test_field_values_are_inlined_at_their_labels():
    text = pl._form_page_text(_civ100()[0])
    assert "ACME LENDING, LLC" in _line_with(text, "PLAINTIFF:")
    assert "ERNEST N RAMIREZ" in _line_with(text, "DEFENDANT:")
    assert "LOS ANGELES" in _line_with(text, "COUNTY OF")
    # a label and value printed on the same row stay on one row
    assert "24STCV24253" in _line_with(text, "CASE NUMBER:")
    assert "12,500.00" in _line_with(text, "a. Demand of complaint")


def test_a_multi_line_field_keeps_its_lines():
    doc = fitz.open()
    p = _page(doc)
    _static(p, 40, 40, "ATTORNEY OR PARTY WITHOUT ATTORNEY:", 6)
    _text(p, "atty", 40, 50, "Jane Roe, Esq.\nRoe & Roe LLP\n100 Main St",
          210.0, 50.0)
    _checkbox(p, "x", 60, 200, True)
    text = pl._form_page_text(p)
    assert "Jane Roe, Esq." in text
    assert "Roe & Roe LLP" in text
    assert "100 Main St" in text
    # three separate rows, not one welded run
    assert "Jane Roe, Esq.Roe & Roe LLP" not in text
    assert _lines(text).index("Roe & Roe LLP") < _lines(text).index("100 Main St")


def test_an_empty_field_prints_nothing():
    doc = fitz.open()
    p = _page(doc)
    _static(p, 80, 100, "b. Statement of damages", 8)
    _static(p, 300, 100, "$", 8)
    _text(p, "blank", 310, 93, "")
    _checkbox(p, "cb", 60, 93, False)
    text = pl._form_page_text(p)
    assert "[ ] b. Statement of damages" in text
    # a blank on the form stays blank: no placeholder, no stray "None"
    assert "None" not in text
    assert _line_with(text, "Statement of damages").rstrip().endswith("$")


# ── radio groups ────────────────────────────────────────────────────────────

class _FakeWidget:
    """A widget stand-in: PyMuPDF's high-level API cannot build a real radio
    GROUP (it needs a /Parent with /Kids), and the state logic is what matters."""

    def __init__(self, field_type, field_value, on="Yes"):
        self.field_type = field_type
        self.field_value = field_value
        self._on = on

    def on_state(self):
        return self._on


def test_widget_is_on_reads_the_pdf_off_state():
    # `Off` is the state name the PDF spec reserves for off, so anything else is
    # on — that is what carries the export values real forms use.
    for val, want in (("Off", False), ("off", False), ("", False), (None, False),
                      (False, False), ("Yes", True), ("On", True), ("1", True),
                      (True, True)):
        assert pl._widget_is_on(_FakeWidget(None, val)) is want, val


def test_only_the_selected_radio_in_a_group_reads_checked():
    # Every widget in a radio group carries the GROUP's value, so comparing to
    # `Off` alone reports all of them checked the moment one is. A radio has to
    # match its OWN on-state.
    rb = fitz.PDF_WIDGET_TYPE_RADIOBUTTON
    group_value = "corp"
    assert pl._widget_is_on(_FakeWidget(rb, group_value, on="corp")) is True
    assert pl._widget_is_on(_FakeWidget(rb, group_value, on="indiv")) is False
    # and an unselected group is off for every member
    assert pl._widget_is_on(_FakeWidget(rb, "Off", on="corp")) is False


def test_a_radio_renders_a_state_box_like_a_checkbox():
    rb = fitz.PDF_WIDGET_TYPE_RADIOBUTTON
    rect = fitz.Rect(60, 90, 70, 100)
    on = pl._form_widget_cells(_FakeWidget(rb, "corp", on="corp"), rect)
    off = pl._form_widget_cells(_FakeWidget(rb, "corp", on="indiv"), rect)
    assert [c[3] for c in on] == ["[X]"]
    assert [c[3] for c in off] == ["[ ]"]


# ── integration: the export, the leak scan, and non-form regressions ─────────

def _pz():
    reg = pl._PnFakeRegistry()
    terms = pl._pn_build_terms(["Ernest N Ramirez"], ["24STCV24253"], [],
                               registry=reg)
    return pl.Pseudonymizer(terms, DET, registry=reg)


def test_export_carries_the_form_view_and_is_still_scrubbed(tmp_path):
    doc = _civ100()
    src = tmp_path / "Request for Default.pdf"
    doc.save(src)
    pz = _pz()
    assert pl._write_text_version(src, fitz.open(src), log, pseudonymizer=pz)
    out = next((tmp_path / "Text Files").glob("*.txt"))
    body = out.read_text(encoding="utf-8")
    assert "[X] a. Enter default of defendant" in body
    assert "[ ] b. Enter clerk's judgment" in body
    # the party names reached the scrubber even though they live in widgets
    assert "ERNEST N RAMIREZ" not in body.upper()
    assert "24STCV24253" not in body
    # the form number is court-form boilerplate — never faked
    assert "CIV-100" in body


def test_form_values_are_visible_to_the_leak_scan(tmp_path):
    # A name that exists ONLY in a widget must still be seen by detection, or an
    # unscrubbed party would be certified clean.
    doc = _civ100()
    src = tmp_path / "CIV-100.pdf"
    doc.save(src)
    detect = pl._page_detect_text(fitz.open(src)[0])
    assert "ACME LENDING, LLC" in detect
    assert "ERNEST N RAMIREZ" in detect


def test_a_page_without_widgets_is_untouched():
    doc = fitz.open()
    p = _page(doc)
    p.insert_text((72, 100), "Plaintiff Ernest N Ramirez sued.", fontsize=11)
    assert pl._form_page_text(p) is None
    assert pl._doc_has_form_fields(doc) is False


def test_text_only_form_on_pleading_paper_keeps_its_line_numbers():
    # A widget page with NO checkbox has nothing the form path uniquely recovers,
    # so a line-numbered page (an MC-025 attachment) keeps its gutter numbers —
    # losing "p.3:7" pinpoint cites is only worth it for checkbox state.
    doc = fitz.open()
    p = _page(doc)
    for i in range(1, 29):
        y = 70 + i * 24
        _static(p, 40, y, str(i), 10)
        _static(p, 80, y, f"Averment number {i} of the pleading text.", 11)
    _text(p, "f", 300, 100, "FIELD VALUE", 90.0)
    rows = pl._page_lined_rows(p)
    form = pl._form_page_text(p)
    assert rows is not None                       # pleading paper, recognised
    assert form is not None                       # the form path COULD run...
    assert pl._form_has_state_boxes(form) is False
    # ...and the routing rule in _write_text_version declines it
    assert not (rows is None or pl._form_has_state_boxes(form))


def test_text_only_form_off_pleading_paper_still_anchors_its_values():
    # The other half of that rule: with no gutter to protect, a text-only form
    # still needs the form path, or its values stay in an unanchored heap.
    doc = fitz.open()
    p = _page(doc)
    _static(p, 40, 150, "PLAINTIFF:", 8)
    _text(p, "pl", 100, 143, "ACME LENDING, LLC")
    assert pl._page_lined_rows(p) is None
    text = pl._form_page_text(p)
    assert "ACME LENDING, LLC" in _line_with(text, "PLAINTIFF:")


# ── the same forms, filled with INK (no widgets left) ───────────────────────
# Printed, marked by hand and scanned — or filled on screen and flattened. The
# checkbox is a printed square and the answer is ink inside it, so the state has
# to be measured rather than read.

_INK_ITEMS = [      # (caption baseline, box x, caption x, caption, marked?)
    (250, 62, 75, "a. Enter default of defendant (names): ERNEST N RAMIREZ", True),
    (275, 62, 75, "b. Enter clerk's judgment", False),
    (295, 78, 90, "(1) For restitution of the premises only", False),
    (315, 78, 90, "(2) Under Code of Civil Procedure section 585(a)", True),
    (340, 62, 75, "c. Enter court judgment under CCP 585(b)", True),
    (380, 62, 75, "d. Enter default of cross-defendant", False),
]
_INK_BOX = 9.5


def _printed(mark="vector", box_gap=0.0):
    """A PRINTED CIV-100: box borders are template line art. `mark` says how a
    checked box is inked — 'glyph' (a flattened check), 'vector' (a pen stroke
    flattened into the page) or 'none' (a blank form). `box_gap` moves every box
    away from its caption, so the ink pass can be shown not to depend on the
    distance it guesses."""
    doc = fitz.open()
    p = _page(doc)
    _static(p, 40, 150, "PLAINTIFF: ACME LENDING, LLC", 7)
    _static(p, 40, 170, "DEFENDANT: ERNEST N RAMIREZ", 7)
    _static(p, 400, 150, "CASE NUMBER: 24STCV24253", 7)
    _static(p, 60, 230, "1. TO THE CLERK: On the complaint filed", 8)
    for y, bx, cx, cap, on in _INK_ITEMS:
        bx -= box_gap
        _static(p, cx, y, cap, 8)
        top = y - _INK_BOX + 1.5
        p.draw_rect(fitz.Rect(bx, top, bx + _INK_BOX, top + _INK_BOX),
                    color=(0, 0, 0), width=0.7)          # the printed box
        if not on:
            continue
        if mark == "glyph":
            p.insert_text((bx + 1, y - 1), "3", fontsize=9, fontname="zadb")
        elif mark == "vector":
            p.draw_line(fitz.Point(bx + 1.5, top + 5), fitz.Point(bx + 4, top + 8),
                        color=(0, 0, 0.4), width=1.1)
            p.draw_line(fitz.Point(bx + 4, top + 8), fitz.Point(bx + 8.5, top + 1),
                        color=(0, 0, 0.4), width=1.1)
    _static(p, 40, 745, "CIV-100 [Rev. January 1, 2023]", 6)
    return doc


def _scanned(src_doc, dpi=200):
    """The page as it comes back from the court's scanner, after OCR: a raster
    image plus an invisible text layer. No vectors and no mark glyph survive —
    dark pixels are all the evidence there is."""
    src = src_doc[0]
    pix = src.get_pixmap(dpi=dpi)
    out = fitz.open()
    q = out.new_page(width=src.rect.width, height=src.rect.height)
    q.insert_image(q.rect, pixmap=pix)
    for blk in src.get_text("dict")["blocks"]:
        for ln in blk.get("lines", []):
            for sp in ln["spans"]:
                if sp["font"].lower().startswith("zadb"):
                    continue                  # the scanner sees ink, not a glyph
                q.insert_text((sp["bbox"][0], sp["bbox"][3] - 1.5), sp["text"],
                              fontsize=sp["size"], fontname="helv",
                              render_mode=3)  # invisible, like an OCR layer
    return out


def _states(text):
    """[(state, caption)] for every line that carries a checkbox state."""
    out = []
    for ln in _lines(text):
        s = ln.strip()
        for mark in ("[X]", "[ ]", "[?]"):
            if s.startswith(mark):
                out.append((mark, s[len(mark):].strip()))
                break
    return out


def _expected():
    return [("[X]" if on else "[ ]", cap) for _y, _bx, _cx, cap, on in _INK_ITEMS]


def test_a_flattened_form_is_read_from_its_line_art():
    # Filled on screen then flattened: the check survives as a glyph inside the
    # printed square. Exact — a glyph is either there or it is not.
    text = pl._form_page_text(_printed("glyph")[0])
    assert _states(text) == _expected()
    assert text.startswith("[printed form CIV-100 — marks read from the page's "
                           "line art: 6 box(es), 3 marked]")


def test_a_flattened_pen_stroke_is_read_as_a_mark():
    text = pl._form_page_text(_printed("vector")[0])
    assert _states(text) == _expected()
    assert "line art" in _lines(text)[0]


def test_a_blank_printed_form_reports_nothing_marked():
    text = pl._form_page_text(_printed("none")[0])
    assert [s for s, _c in _states(text)] == ["[ ]"] * 6
    assert "0 marked" in _lines(text)[0]


def test_a_scanned_form_is_read_from_the_ink():
    # The case this exists for: nothing but dark pixels to go on.
    doc = _scanned(_printed("vector"))
    assert not list(doc[0].widgets())
    assert pl._ink_square_drawings(doc[0])[0] == []      # no line art either
    text = pl._form_page_text(doc[0])
    assert _states(text) == _expected()
    # ...and it says so, because an inferred checkbox decides a default judgment
    assert "READ FROM INK" in _lines(text)[0]
    assert "VERIFY against the PDF" in _lines(text)[0]


def test_a_scanned_blank_form_invents_no_marks():
    # The dangerous direction: reporting [X] on an empty box would say a party
    # requested relief it never asked for.
    text = pl._form_page_text(_scanned(_printed("none"))[0])
    assert [s for s, _c in _states(text)] == ["[ ]"] * 6
    assert "0 marked" in _lines(text)[0]


def test_the_ink_pass_does_not_depend_on_the_box_to_caption_distance():
    # The box is FOUND in the raster rather than centred by estimate — which is
    # what makes it work. Moving every box further from its caption must not
    # change a single state.
    for gap in (0.0, 3.0, 6.0):
        text = pl._form_page_text(_scanned(_printed("vector", box_gap=gap))[0])
        assert _states(text) == _expected(), gap


def test_an_ordinary_page_never_reaches_the_ink_pass():
    # No form id in the footer and no checkbox-sized line art: an ordinary filing
    # must not pay for a raster render, let alone get checkbox markers.
    doc = fitz.open()
    p = _page(doc)
    for i in range(1, 29):
        y = 70 + i * 24
        _static(p, 40, y, str(i), 10)
        _static(p, 80, y, f"Averment number {i} of the pleading text.", 11)
    assert pl._ink_form_cells(p) is None
    assert pl._form_page_text(p) is None


def test_a_rule_line_beside_a_caption_is_not_a_checkbox():
    doc = fitz.open()
    p = _page(doc)
    _static(p, 40, 745, "CIV-100 [Rev. January 1, 2023]", 6)   # passes the gate
    for i, y in enumerate((200, 220, 240)):
        _static(p, 90, y, f"item {i} of the form", 8)
        p.draw_line(fitz.Point(66, y - 3), fitz.Point(88, y - 3), width=0.7)
    got = pl._ink_form_cells(p)
    assert got is None or got[1] == 0          # no box counted


def test_a_fill_it_cannot_settle_is_unreadable_not_rounded():
    # The safety property of the whole ink pass: a mark too faint to separate
    # from scanner speckle is reported as unreadable, never rounded to the nearer
    # answer. On a default-judgment packet the checkbox decides the disposition.
    assert pl._ink_state_from_fill(0.40) is True
    assert pl._ink_state_from_fill(pl._INK_MARK_FILL) is True
    assert pl._ink_state_from_fill(0.00) is False
    assert pl._ink_state_from_fill(pl._INK_EMPTY_FILL) is False
    mid = (pl._INK_EMPTY_FILL + pl._INK_MARK_FILL) / 2
    assert pl._ink_state_from_fill(mid) is None


def test_a_faint_pencil_tick_is_not_reported_as_checked():
    # ...and end to end: whatever a faint mark resolves to, the tally always
    # accounts for every box, and a blank form never gains a mark.
    doc = _printed("none")
    p = doc[0]
    for y, bx, _cx, _cap, on in _INK_ITEMS:
        if on:
            top = y - _INK_BOX + 1.5
            p.draw_line(fitz.Point(bx + 2, top + 5), fitz.Point(bx + 7, top + 2),
                        color=(0.55, 0.55, 0.6), width=0.3)     # barely there
    text = pl._form_page_text(_scanned(doc)[0])
    states = [s for s, _c in _states(text)]
    assert len(states) == 6
    banner = _lines(text)[0]
    marked = states.count("[X]")
    unsure = states.count("[?]")
    assert f"{marked} marked" in banner
    if unsure:
        assert f"{unsure} unreadable" in banner
    # the three boxes that were never touched stay unmarked, whatever the rest do
    assert states[1] == states[2] == states[5] == "[ ]"


def test_an_empty_box_glyph_reads_as_unchecked():
    # Some flattened forms print the empty box as a character. Reading it as a
    # mark would report relief the party never requested.
    for ch, want in (("□", False), ("☐", False), ("✓", True), ("X", True),
                     ("☒", True)):
        got = pl._ink_glyph_state({"text": ch, "font": "Helvetica"})
        assert got is want, (ch, got)
    # a lone DIGIT is not a check: the dingbat font settles the real check glyph,
    # and on a scan the raster pass measures the actual ink
    assert pl._ink_glyph_state({"text": "3", "font": "Helvetica"}) is None
    assert pl._ink_glyph_state({"text": "3", "font": "ZapfDingbats"}) is True
    # ...and anything long enough to be a WORD is not a state glyph at all, so a
    # caption that drifted into the window can never be read as a check
    assert pl._ink_glyph_state({"text": "Enter", "font": "Helvetica"}) is None
    assert pl._ink_glyph_state({"text": "individual", "font": "ZapfDingbats"}) is None


def test_the_banner_names_unreadable_boxes():
    # A state the ink could not settle is reported as [?] and counted, never
    # rounded to checked or unchecked.
    page = _printed("none")[0]
    assert "1 unreadable ([?])" in pl._form_banner(page, 6, 3, 1, "ink")
    assert "unreadable" not in pl._form_banner(page, 6, 3, 0, "ink")
    assert "READ FROM INK" in pl._form_banner(page, 6, 3, 0, "ink")
    assert "READ FROM INK" not in pl._form_banner(page, 6, 3, 0, "fields")


def test_widgets_win_over_ink_when_both_are_available():
    # A form whose fields are intact must be read from them: the widget is
    # authoritative, the ink is inferred.
    text = pl._form_page_text(_civ100()[0])
    assert text.startswith("[fillable form CIV-100:")
    assert "READ FROM INK" not in text


def test_an_ink_form_page_is_still_scrubbed(tmp_path):
    src = tmp_path / "Scanned CIV-100.pdf"
    _scanned(_printed("vector")).save(src)
    pz = _pz()
    assert pl._write_text_version(src, fitz.open(src), log, pseudonymizer=pz)
    body = next((tmp_path / "Text Files").glob("*.txt")).read_text(encoding="utf-8")
    assert "[X] a. Enter default of defendant" in body
    assert "ERNEST N RAMIREZ" not in body.upper()
    assert "24STCV24253" not in body
    assert "CIV-100" in body                   # form boilerplate, never faked


def test_several_checkboxes_on_one_printed_row():
    # The header of every cause-of-action attachment: two boxes and two captions
    # on a single row. They must stay on one line, each state beside its own
    # caption, in printed order.
    doc = fitz.open()
    p = _page(doc)
    _static(p, 40, 100, "ATTACHMENT TO", 8)
    _static(p, 130, 100, "Complaint", 8)
    _static(p, 220, 100, "Cross-Complaint", 8)
    _static(p, 40, 745, "PLD-C-001(2) [Rev. January 1, 2007]", 6)
    _checkbox(p, "to_c", 115, 93, False)
    _checkbox(p, "to_xc", 205, 93, True)
    line = _line_with(pl._form_page_text(p), "ATTACHMENT TO")
    assert line.split() == ["ATTACHMENT", "TO", "[", "]", "Complaint",
                            "[X]", "Cross-Complaint"]
    assert pl._form_page_text(p).startswith("[fillable form PLD-C-001(2):")


# ── a NUMBERED form: the item index is not a checkbox ────────────────────────
# PLD-PI-001 and its cause-of-action attachments index every allegation — "2.",
# "a.", "(1)", "MV-2." — and print the number in exactly the place a checkbox
# would sit: just left of the caption it governs. The raster cannot tell a
# printed square from a glyph on size and aspect alone, so every numbered
# paragraph came out `[X]` with its number swallowed, and the banner tallied a
# page of boxes that reported relief nobody had requested.

_NUM_ITEMS = [      # (index label, has a printed box?, caption, marked?)
    ("2.", False, "This pleading, including attachments, consists of pages: 4", False),
    ("3.", False, "Each plaintiff named above is a competent adult", False),
    ("a.", True, "except plaintiff (name):", False),
    ("(1)", True, "a corporation qualified to do business in California", True),
    ("(2)", True, "an unincorporated entity (describe):", False),
    ("4.", False, "The true names of defendants sued as Does are unknown", False),
    ("a.", True, "Doe defendants were the agents or employees", True),
    ("b.", True, "Doe defendants are persons whose capacities are unknown", False),
]


def _numbered():
    """A PLD-PI-001 body page: numbered allegations, some of which carry a
    printed checkbox and some of which do not. Returns (doc, [(rect, on)])."""
    doc = fitz.open()
    p = _page(doc)
    _static(p, 40, 100, "SHORT TITLE: SMITH vs. JONES", 7)
    boxes = []
    for i, (label, has_box, cap, on) in enumerate(_NUM_ITEMS):
        y = 150 + i * 26
        _static(p, 60, y, label, 9)
        if not has_box:
            _static(p, 82, y, cap, 9)
            continue
        top = y - _INK_BOX + 1.5
        r = fitz.Rect(92, top, 92 + _INK_BOX, top + _INK_BOX)
        p.draw_rect(r, color=(0, 0, 0), width=0.7)
        boxes.append((r, on))
        if on:
            p.draw_line(fitz.Point(93.5, top + 5), fitz.Point(96, top + 8),
                        color=(0, 0, 0.4), width=1.1)
            p.draw_line(fitz.Point(96, top + 8), fitz.Point(100, top + 1.5),
                        color=(0, 0, 0.4), width=1.1)
        _static(p, 110, y, cap, 9)
    _static(p, 40, 745, "PLD-PI-001 [Rev. January 1, 2007]", 6)
    return doc, boxes


def _scan_boxes_as(doc, boxes, ocr):
    """`doc` scanned, with `ocr` standing in for each printed square in the text
    layer — what OCR hands back when it has no character for an empty box."""
    out = _scanned(doc)
    q = out[0]
    for r, on in boxes:
        q.insert_text((r.x0, r.y1 - 1), ocr, fontsize=9, fontname="helv",
                      render_mode=3)
        if on:
            q.insert_text((r.x0 + 2, r.y1 - 1), "x", fontsize=8,
                          fontname="helv", render_mode=3)
    return out


def _marked_lines(text):
    """[(state, what follows it)] for every line carrying a state box. Unlike
    `_states`, the mark need not start the line: on a numbered form the item
    index is printed to the LEFT of the box it indexes."""
    out = []
    for ln in _lines(text):
        hits = [(ln.index(m), m) for m in ("[X]", "[ ]", "[?]") if m in ln]
        if hits:
            i, m = min(hits)
            out.append((m, ln[i + len(m):].strip()))
    return out


def _numbered_expected():
    return [("[X]" if on else "[ ]", cap)
            for _l, has_box, cap, on in _NUM_ITEMS if has_box]


def test_a_numbered_paragraph_is_never_read_as_a_checkbox():
    # The page that started this: a form body with an index number beside every
    # allegation and NO checkbox anywhere. Not one box may be reported — and
    # because none is, the page is not a checkbox form at all and falls back to
    # ordinary extraction, which keeps the numbering the pleading is cited by.
    doc = fitz.open()
    p = _page(doc)
    for i, (label, _b, cap, _on) in enumerate(_NUM_ITEMS):
        _static(p, 60, 150 + i * 26, label, 9)
        _static(p, 82, 150 + i * 26, cap, 9)
    _static(p, 40, 745, "PLD-PI-001 [Rev. January 1, 2007]", 6)
    for page in (p, _scanned(doc)[0]):
        assert pl._ink_form_cells(page) is None
        assert pl._form_page_text(page) is None


@pytest.mark.parametrize("render", ["flat", "scan", "scan-ocr-box"])
def test_a_numbered_form_keeps_its_numbers_and_reads_its_boxes(render):
    # ...and the mixed page, however it reaches us: the five real boxes are read
    # and the three bare index numbers stay text. All three renderings have to
    # agree, because the state is the pleading and the numbering indexes it.
    doc, boxes = _numbered()
    page = {"flat": lambda: doc[0],
            "scan": lambda: _scanned(doc)[0],
            "scan-ocr-box": lambda: _scan_boxes_as(doc, boxes, "CJ")[0]}[render]()
    text = pl._form_page_text(page)
    assert _marked_lines(text) == _numbered_expected()
    assert "5 box(es), 2 marked" in _lines(text)[0]
    # the unboxed allegations keep their numbers and gain no state
    for label, has_box, cap, _on in _NUM_ITEMS:
        if not has_box:
            assert _line_with(text, cap).strip().startswith(label)
    assert "CJ" not in text            # the artifact the state box stands for


def test_a_box_ocr_read_as_letters_is_measured_not_believed():
    # A scanner with no character for an empty square hands back a letter of
    # roughly its shape ("CJ", "D"). Two alphanumerics blocked the window, so a
    # scanned form found no box at all and left "CJ x MOTOR VEHICLE" in the
    # export. The artifact is now transparent — but it is never read AS a state:
    # a checked box scans as the same letters plus the mark, so the raster still
    # measures the square underneath.
    doc, boxes = _numbered()
    for ocr in ("CJ", "D", "O"):
        text = pl._form_page_text(_scan_boxes_as(doc, boxes, ocr)[0])
        assert _marked_lines(text) == _numbered_expected(), ocr


def test_a_lone_letter_is_only_a_box_when_it_repeats():
    # The exemption above is what keeps a middle initial safe: an artifact of
    # the template repeats across the page (a form carries dozens of boxes), a
    # name does not, so a one-off "D" is still real text that blocks the window.
    many = [{"text": "CJ"}] * pl._INK_BOX_OCR_MIN
    assert pl._ink_box_artifacts(many) == {"cj"}
    assert not pl._ink_span_blocks_window({"text": "CJ"},
                                          pl._ink_box_artifacts(many))
    lone = [{"text": "CJ"}, {"text": "Redmond L. Parrish"}]
    assert pl._ink_box_artifacts(lone) == frozenset()
    assert pl._ink_span_blocks_window({"text": "CJ"}, pl._ink_box_artifacts(lone))
    # ...and nothing widens what counts as box-shaped: a two-letter word that
    # repeats is still text, whatever else is on the page.
    assert pl._ink_box_artifacts([{"text": "Re"}] * 9) == frozenset()


def test_one_printed_box_reports_one_state():
    # Two captions within reach of the same square each reported it, which is
    # where "[X] [X] [X] except defendant" and a box tally several times the
    # page's came from. One printed box, one state cell.
    doc = fitz.open()
    p = _page(doc)
    for i, y in enumerate((200, 230)):
        top = y - _INK_BOX + 1.5
        p.draw_rect(fitz.Rect(92, top, 92 + _INK_BOX, top + _INK_BOX),
                    color=(0, 0, 0), width=0.7)
        _static(p, 106, y, "ab"[i], 9)          # a lettered sub-item...
        _static(p, 118, y, "a corporation qualified to do business", 9)
    _static(p, 40, 745, "PLD-PI-001 [Rev. January 1, 2007]", 6)
    text = pl._form_page_text(p)
    assert [s for s, _c in _states(text)] == ["[ ]", "[ ]"]
    assert "2 box(es), 0 marked" in _lines(text)[0]


def test_a_printed_box_is_a_ring_and_a_glyph_is_not():
    # The measurement the whole distinction rests on: a printed checkbox is dark
    # the whole way round its border, an item number's ink is its own strokes.
    # A ring of any thickness passes; a solid blob and an open bracket do not.
    ring = [list(range(0, 20)) if y in (0, 1, 18, 19)
            else [0, 1, 18, 19] for y in range(20)]
    assert pl._InkRaster._has_border(ring, 0, 19, 0, 19)
    solid = [list(range(0, 20)) for _y in range(20)]
    assert pl._InkRaster._has_border(solid, 0, 19, 0, 19)     # a filled box
    blob = [list(range(6, 14)) for _y in range(20)]           # a stroke, no edges
    assert not pl._InkRaster._has_border(blob, 0, 19, 0, 19)
    bracket = [[0, 1] for _y in range(20)]                    # "(" — one edge only
    assert not pl._InkRaster._has_border(bracket, 0, 19, 0, 19)


def test_an_ocr_damaged_form_id_still_reaches_the_form_path():
    # A scan reads the "I" of PLD-PI-001 as an "l" about as often as not. The
    # footer id gates the ink pass, so a strict match denied the page the form
    # treatment entirely and a cause-of-action attachment came back as
    # unanchored OCR with its checkboxes left as stray letters.
    doc, boxes = _numbered()
    p = _scanned(doc)[0]
    for footer in ("PLD-PI-001(2) [Rev. January 1, 2007]",
                   "PLD-Pl-001(2) [Rev. January 1, 2007]"):
        assert pl._JC_FORM_NO_RE.search(footer), footer
    # ...but what a value is PROTECTED from faking by stays strict: case
    # tolerance there would start shielding ordinary text.
    assert pl._pn_is_never_fake("PLD-PI-001")
    assert not pl._pn_is_never_fake("PLD-Pl-001")
    assert _marked_lines(pl._form_page_text(p)) == _numbered_expected()
