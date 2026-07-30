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


def test_a_flattened_form_falls_through_to_ordinary_extraction(tmp_path):
    # Printed, signed and scanned: the widgets are gone and the checkboxes are
    # ink. Nothing here applies, and the page must still export.
    src = tmp_path / "flat.pdf"
    doc = _civ100()
    doc.bake()                      # flatten the widgets into page content
    doc.save(src)
    flat = fitz.open(src)
    assert pl._form_page_text(flat[0]) is None
    assert pl._write_text_version(src, flat, log, pseudonymizer=_pz())
    body = next((tmp_path / "Text Files").glob("*.txt")).read_text()
    assert "Enter default of defendant" in body


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
    assert rows is not None                       # pleading paper, recognised
    assert pl._page_has_choice_widgets(p) is False
    assert pl._form_page_text(p) is not None      # the form path COULD run...
    # ...and the routing rule in _write_text_version declines it
    assert not (rows is None or pl._page_has_choice_widgets(p))


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
