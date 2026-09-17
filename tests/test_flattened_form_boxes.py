"""A FLATTENED court form reads its checkboxes at the template's positions.

A form filled on screen and flattened — e-signed through Docusign, which is
most of what arrives now — keeps no widgets, and its flattener draws the
square for NEITHER state: a checked box is a bare mark glyph and an unchecked
one is nothing at all. So the ink pass found no box on any page and declined
the whole rendering, and a seven-page MC-350EX exported with its marks
standing as stray letters ("a. m Is not the subject of a pending action") and
its empty boxes as whitespace — the export unable to say which relief the
petition requested, on the one kind of document where the checkbox IS the
pleading.

The template knows where every box is. The gate that kept it out belonged to
LABEL RESTORATION (a born-digital page's labels are the template's own
already) and said nothing about a box, so it now sits on that pass.

Run:  cd PDF-Linker && python3 -m pytest tests/test_flattened_form_boxes.py -v
"""
import pytest

fitz = pytest.importorskip("fitz")

import pdf_linker as P

from test_form_templates import (  # noqa: E402  — the blank form and its geometry
    BOXES, FOOTER, LABELS, VALUES, _library,
)


def _flattened(marked=(), misreads=None):
    """The form filled and FLATTENED: every label and value VISIBLE text at
    its printed place, no widgets left, no square drawn for any box, and a
    lone mark glyph standing in each box of `marked`. Born-digital — the page
    carries no OCR layer and nothing marks it as read."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for text, x, y in LABELS:
        if misreads:
            text = " ".join(misreads.get(w, w) for w in text.split())
        page.insert_text((x, y), text, fontsize=8, fontname="helv")
    page.insert_text((40, 775), FOOTER, fontsize=7, fontname="helv")
    for text, x, y in VALUES:
        page.insert_text((x, y), text, fontsize=9, fontname="helv")
    for i in marked:
        x0, y0, x1, y1 = BOXES[i]
        # The mark as the delivered document carried it: a bare "m" in a text
        # font, which is neither a check character nor a dingbat — the
        # flattener's own glyph, and no list will ever hold every one.
        page.insert_text((x0 + 1, y1 - 1.5), "m", fontsize=7, fontname="helv")
    return doc, page


# ── the shape this exists for ────────────────────────────────────────────────

def test_a_flattened_form_draws_no_square_and_keeps_no_widget(tmp_path, monkeypatch):
    """The precondition: nothing on the page says where a checkbox is."""
    _library(tmp_path, monkeypatch)
    doc, page = _flattened(marked=(1,))
    try:
        assert not list(page.widgets())
        squares, all_rects = P._ink_square_drawings(page)
        assert not squares and not all_rects
        # ...and the page reads perfectly, so nothing here came out of OCR.
        assert not P._page_text_is_ocr(page)
    finally:
        doc.close()


def test_the_template_supplies_every_box_of_a_flattened_form(tmp_path, monkeypatch):
    _library(tmp_path, monkeypatch)
    doc, page = _flattened(marked=(1,))
    try:
        render = P._form_page_render(page)
        assert render is not None, "the flattened form earned no rendering"
        assert render["boxes"] == len(BOXES)
        assert render["text"].count("[X]") == 1
        assert render["text"].count("[ ]") == len(BOXES) - 1
        # The states came from the template's own positions, and the page's
        # banner says so.
        got = getattr(doc, P._TEMPLATE_ATTR, {}).get(page.number)
        assert got and got["boxes"] == len(BOXES)
        # ...and the rendering earns the page, since the footer names the form.
        assert P._form_displaces_rows(render)
    finally:
        doc.close()


def test_the_mark_is_not_left_standing_beside_its_own_state(tmp_path, monkeypatch):
    """The flattened check is what the state box stands for, so the export
    must not read "[X] m Amount demanded" — which is the shape the delivered
    export carried on every page the rendering was declined for
    ("a. m Is not the subject of a pending action")."""
    _library(tmp_path, monkeypatch)
    doc, page = _flattened(marked=(1,))
    try:
        text = P._form_page_render(page)["text"]
        line = next(ln for ln in text.split("\n") if "Amount demanded does not" in ln)
        assert "[X]" in line and " m " not in line
    finally:
        doc.close()


def test_a_flattened_forms_states_are_exact(tmp_path, monkeypatch):
    """The page's own content is not an inference: no raster is measured and
    the banner does not ask the operator to verify what the page draws."""
    _library(tmp_path, monkeypatch)
    doc, page = _flattened(marked=(1,))
    try:
        render = P._form_page_render(page)
        assert render["source"] == "exact"
        assert "VERIFY" not in render["text"].split("\n")[0]
        assert "[?]" not in render["text"]
    finally:
        doc.close()


def test_without_the_library_the_flattened_form_is_still_declined(tmp_path, monkeypatch):
    """Nothing here infers a box from the page: with no template to ask, the
    page has no square and no state, and the rendering is refused as before."""
    monkeypatch.setenv(P._TEMPLATE_ENV, str(tmp_path / "nowhere"))
    monkeypatch.setattr(P, "_TEMPLATE_DIR_OVERRIDE", None)
    P._TEMPLATE_CACHE.clear()
    doc, page = _flattened(marked=(1,))
    try:
        assert P._form_page_render(page) is None
    finally:
        doc.close()


# ── what the OCR gate still holds ────────────────────────────────────────────

def test_a_born_digital_page_has_no_label_restored(tmp_path, monkeypatch):
    """Restoration keeps its own gate: a page that reads perfectly has the
    template's labels already, and one whose own text says "WlTHOUT" is not
    a scan — it is the document — so it is left exactly as it stands."""
    _library(tmp_path, monkeypatch)
    doc, page = _flattened(marked=(1,), misreads={"WITHOUT": "WlTHOUT"})
    try:
        spans = P._page_text_spans(page)
        before = [sp["text"] for sp in spans]
        P._restore_template_labels(spans, page)
        assert [sp["text"] for sp in spans] == before
        assert "WlTHOUT" in " ".join(before)
    finally:
        doc.close()


def test_a_born_digital_page_harvests_no_field_value(tmp_path, monkeypatch):
    """The field harvest keeps its own gate too: it reads a SCAN's words out
    of a classified field, and a born-digital form reaches every other
    harvest as ordinary text."""
    _library(tmp_path, monkeypatch)
    doc, page = _flattened(marked=(1,))
    try:
        assert P._template_field_values(page) == []
    finally:
        doc.close()


def test_a_scan_still_has_its_labels_restored(tmp_path, monkeypatch):
    """The gate moved; it did not go away."""
    from test_form_templates import _scan
    _library(tmp_path, monkeypatch)
    doc, page = _scan()
    try:
        spans = P._page_text_spans(page)
        P._restore_template_labels(spans, page)
        joined = " ".join(sp["text"] for sp in spans)
        assert "WITHOUT" in joined and "WlTHOUT" not in joined
    finally:
        doc.close()


def test_a_box_with_a_picture_over_it_is_the_rasters(tmp_path, monkeypatch):
    """The page's own content answers only where the page is what is SHOWN.
    A scan pasted in strips covers no single box's worth of the page by the
    page-wide measure, and a box under a picture has its state in the
    picture — which only the raster can read."""
    _library(tmp_path, monkeypatch)
    doc, page = _flattened(marked=(1,))
    try:
        x0, y0, x1, y1 = BOXES[0]
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40))
        pix.clear_with(255)
        page.insert_image(fitz.Rect(x0 - 4, y0 - 4, x1 + 4, y1 + 4), pixmap=pix)
        render = P._form_page_render(page)
        assert render["boxes"] == len(BOXES)
        # The covered box is measured, so the page's states are no longer
        # exact and the banner asks for a check; the others are unmoved.
        assert render["source"] == "ink"
        assert render["text"].count("[X]") == 1
    finally:
        doc.close()


# ── the CAPTION BOX: the template draws what a scan lost ─────────────────────

def _no_line_art(marked=()):
    """A recognised form page that draws NO line art of its own — the shape a
    SCAN takes, its rules being ink in the picture where `_page_rules` reads
    nothing — plus the one short underline that stopped `_page_art_rules`
    reaching its raster fallback on the delivered petition."""
    doc, page = _flattened(marked=marked)
    page.draw_line(fitz.Point(120, 600), fitz.Point(180, 600), width=0.6)
    return doc, page


def test_a_scanned_form_draws_the_caption_box_from_its_template(tmp_path, monkeypatch):
    """The user's report: page 1 came out with no caption box at all."""
    from test_form_templates import RULES_H, RULES_V
    _library(tmp_path, monkeypatch)
    doc, page = _no_line_art(marked=(1,))
    try:
        own_v, own_h = P._page_rules(page, min_len=P._FORM_RULE_MIN)
        assert not own_v            # the page draws the caption box nowhere
        assert len(own_h) == 1      # ...only its one underline
        _cw, (vert, horiz), _w = P._form_page_geometry(page)
        # Every rule of the blank form is placed, and the page's own kept.
        for x, _y0, _y1 in RULES_V:
            assert any(abs(x - q) <= 1.5 for q, _a, _b in vert), x
        for y, _x0, _x1 in RULES_H:
            assert any(abs(y - q) <= 1.5 for q, _a, _b in horiz), y
        assert any(abs(600 - q) <= 1.5 for q, _a, _b in horiz)
        text = P._form_page_render(page)["text"]
        assert "│" in text     # ...and the export draws the box
        assert text.count("─") > 20
    finally:
        doc.close()


def test_a_form_that_draws_its_own_rules_is_rendered_exactly_as_it_was(tmp_path, monkeypatch):
    """A born-digital form draws every one of the template's rules itself, so
    the template adds nothing and the export does not move."""
    _library(tmp_path, monkeypatch)
    from test_form_templates import RULES_H, RULES_V
    doc, page = _flattened(marked=(1,))
    try:
        for x, y0, y1 in RULES_V:
            page.draw_line(fitz.Point(x, y0), fitz.Point(x, y1), width=0.8)
        for y, x0, x1 in RULES_H:
            page.draw_line(fitz.Point(x0, y), fitz.Point(x1, y), width=0.8)
        own = P._page_rules(page, min_len=P._FORM_RULE_MIN)
        _cw, laid, _w = P._form_page_geometry(page)
        assert len(laid[0]) == len(own[0]) and len(laid[1]) == len(own[1])
        for (a, b, c), (d, e, f) in zip(laid[0] + laid[1], own[0] + own[1]):
            assert abs(a - d) < 0.6 and abs(b - e) < 0.6 and abs(c - f) < 0.6
    finally:
        doc.close()


def test_the_page_keeps_a_rule_the_template_does_not_name(tmp_path, monkeypatch):
    """A rule the FILER drew — a stamp's frame, a table typed into an
    attachment — is the page's own and is never dropped for the template's."""
    _library(tmp_path, monkeypatch)
    doc, page = _no_line_art()
    try:
        page.draw_line(fitz.Point(450, 620), fitz.Point(450, 700), width=0.8)
        _cw, (vert, _h), _w = P._form_page_geometry(page)
        kept = [r for r in vert if abs(r[0] - 450) <= 1.5]
        assert kept and kept[0][1] > 600
    finally:
        doc.close()


def test_a_page_the_library_does_not_recognise_draws_only_its_own(tmp_path, monkeypatch):
    """No template, no rules laid: the one safety of taking line art from a
    blank form is that the recognition has to pass first."""
    monkeypatch.setattr(P, "_TEMPLATE_CACHE", {})
    monkeypatch.setenv("PDF_LINKER_FORM_TEMPLATES", str(tmp_path / "none"))
    doc, page = _no_line_art(marked=(1,))
    try:
        assert P._template_recognise(page, P._page_text_spans(page)) is None
        _cw, (vert, horiz), _w = P._form_page_geometry(page)
        assert not vert and len(horiz) == 1
    finally:
        doc.close()
