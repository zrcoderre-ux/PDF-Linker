"""
A /Rotate page keeps two coordinate systems, and the OCR family mixed them.

PyMuPDF's `get_text`, span geometry, redaction rects and `show_pdf_page`
targets live in the UNROTATED page space, while `page.rect` and `get_pixmap`
are DISPLAY space — and rotated pages are precisely the scanned exhibits the
OCR passes exist for. Mixing the two cost real content, four separate ways:

* the Tesseract overlay was placed with `show_pdf_page(page.rect, …)`, which
  put the text 90° off and CLIPPED every word past the unrotated mediabox out
  of extraction — a whole band of every rotated scan silently lost (and for
  the garbled-page rebuild, lost IRREVERSIBLY, the old layer having been
  redacted);
* that same redaction used `page.rect`, which on a rotated page misses a band
  of the unrotated space — so garbled text survived UNDER the fresh overlay,
  the doubled-layer shape `_drop_overdrawn_spans` exists to fight;
* `_ocr_image_regions` clipped its render with an unrotated rect, which
  `get_pixmap` reads as display space — the region rendered BLANK and the
  judge's-signature image was never read on any rotated page;
* `_InkRaster` probed display-space pixels with unrotated windows (so a
  scanned form lost every checkbox state) and `_form_page_number` clipped a
  display-space band with `get_text` (so the ink gate's form-id arm went
  blind).

Run:  cd PDF-Linker && python3 -m pytest tests/test_rotated_pages.py -v
"""
import io
import logging
import sys
import types

import pytest

import pdf_linker as P

fitz = pytest.importorskip("fitz")
log = logging.getLogger("test")


def _display_pos(page, word_rect):
    r = fitz.Rect(word_rect) * page.rotation_matrix
    r.normalize()
    return r


# ── the whole-page overlay lands, whole and upright ─────────────────────────

def _ocr_result_doc():
    """The shape Tesseract returns for a rot-90 letter page: a 792x612
    display-oriented page, with words at its corners."""
    od = fitz.open()
    p = od.new_page(width=792, height=612)
    p.insert_text((10, 20), "LEFTTOP")
    p.insert_text((700, 20), "RIGHTTOP")
    p.insert_text((10, 600), "LEFTBOTTOM")
    p.insert_text((700, 600), "RIGHTBOTTOM")
    return od


def test_the_overlay_keeps_every_corner_of_a_rotated_page():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.set_rotation(90)
    od = _ocr_result_doc()
    P._overlay_ocr_layer(page, od)
    od.close()
    words = {w[4]: w[:4] for w in page.get_text("words")}
    assert set(words) == {"LEFTTOP", "RIGHTTOP", "LEFTBOTTOM", "RIGHTBOTTOM"}
    # …and each sits where the reader sees it: LEFTTOP near the display origin.
    lt = _display_pos(page, words["LEFTTOP"])
    rb = _display_pos(page, words["RIGHTBOTTOM"])
    assert lt.x0 < 40 and lt.y0 < 40
    assert rb.x0 > 600 and rb.y0 > 500
    doc.close()


def test_an_unrotated_page_overlays_exactly_as_before():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    od = fitz.open()
    p = od.new_page(width=612, height=792)
    p.insert_text((100, 700), "BOTTOMWORD")
    P._overlay_ocr_layer(page, od)
    od.close()
    words = {w[4] for w in page.get_text("words")}
    assert words == {"BOTTOMWORD"}
    doc.close()


# ── the rebuild's redaction reaches the whole page ──────────────────────────

def test_the_redaction_bound_covers_a_rotated_page():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((100, 100), "TOPWORD")
    page.insert_text((100, 700), "BOTTOMWORD")   # the band page.rect missed
    page.set_rotation(90)
    page.add_redact_annot(P._unrotated_bound(page), fill=False)
    page.apply_redactions()
    assert page.get_text("text").strip() == ""
    doc.close()


# ── an image region on a rotated page is read ───────────────────────────────

def _stub_tesseract(monkeypatch, recognised):
    """Tesseract stand-in that recognises `recognised` ONLY when the rendered
    clip actually contains ink — a blank render (the rotated-clip bug) comes
    back empty, exactly as the real engine would return nothing."""
    def _to_pdf(img, extension="pdf", config=None, timeout=None):
        pix = fitz.Pixmap(img.getvalue())
        gray = fitz.Pixmap(fitz.csGRAY, pix) if pix.n > 2 else pix
        dark = sum(1 for b in gray.samples if b < 128)
        out = fitz.open()
        pg = out.new_page(width=pix.width * 72 / 150, height=pix.height * 72 / 150)
        if dark:
            pg.insert_text((5, pg.rect.height / 2), recognised, fontsize=9)
        data = out.tobytes()
        out.close()
        return data

    fake = types.ModuleType("pytesseract")
    fake.pytesseract = types.SimpleNamespace(tesseract_cmd=None)
    fake.image_to_pdf_or_hocr = _to_pdf
    monkeypatch.setitem(sys.modules, "pytesseract", fake)
    pil = types.ModuleType("PIL")
    pil.Image = types.SimpleNamespace(open=lambda b: b)
    monkeypatch.setitem(sys.modules, "PIL", pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", pil.Image)
    monkeypatch.setattr(P, "_find_tesseract", lambda: "/usr/bin/tesseract")
    monkeypatch.setattr(P, "_tesseract_usable", lambda t, l: True)


def test_an_image_on_a_rotated_page_is_read(monkeypatch):
    _stub_tesseract(monkeypatch, "Alison Mackenzie / Judge")
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    y = 100
    for line in ["ORDER OF DISMISSAL",
                 "it is ordered that the action is dismissed"]:
        page.insert_text((72, y), line, fontsize=12)
        y += 20
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 220, 90))
    pix.clear_with(0)                            # ink, so the stub recognises
    page.insert_image(fitz.Rect(300, 500, 520, 590), pixmap=pix)
    page.set_rotation(90)
    assert P._ocr_image_regions(doc, log) == 1
    assert "Mackenzie" in doc[0].get_text("text")
    doc.close()


# ── ink checkboxes and the form-id gate survive rotation ────────────────────

def test_a_checkbox_is_measured_through_the_rotation():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.draw_rect(fitz.Rect(100, 100, 112, 112), color=0, width=1.2)
    page.set_rotation(90)
    raster = P._InkRaster(page)
    hit = raster.box_fill(fitz.Rect(94, 94, 130, 118))   # unrotated window
    assert hit is not None
    fill, rect = hit
    assert fill <= P._INK_EMPTY_FILL                     # an empty box
    # …and the measured box comes back in UNROTATED space, where the drawn
    # square is.
    assert fitz.Rect(94, 94, 130, 118).contains(rect)
    doc.close()


def test_the_form_id_is_found_in_a_rotated_footer():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # Placed so it DISPLAYS in the bottom band of the rotated page: display y
    # is unrotated x, so the whole string sits at unrotated x in [502, 612].
    page.insert_text((505, 392), "PLD-PI-001", fontsize=8)
    page.set_rotation(90)
    assert P._form_page_number(page) == "PLD-PI-001"
    doc.close()


def test_the_form_id_is_still_found_on_an_unrotated_footer():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((280, 770), "PLD-PI-001", fontsize=8)
    assert P._form_page_number(page) == "PLD-PI-001"
    doc.close()
