"""An IMAGE on a page whose own text layer is fine is still text nobody read.

OCR was an all-or-nothing PAGE decision, and both existing passes rightly
decline such a page: `_ocr_pdf` only touches a page with NO text, and
`_reocr_garbled_pages` only rebuilds one whose text reads as gibberish. So an
Order of Dismissal whose 1,300 characters extract perfectly still said nothing
about who signed it — "Alison Mackenzie / Judge" lived in a 215x91 pt image and
appeared NOWHERE in the document's text layer. Neither pass ever looked at the
page.

The name was in clean printed type the whole time; only the signature scrawled
above it is unreadable.

`_ocr_image_regions` is ADDITIVE, which is what separates it from
`_reocr_garbled_pages`: nothing is redacted and no existing text is replaced, so
the worst case is a wasted render. The filter is NEWNESS — a region is kept only
when it carries words the page does not already have — which is why a logo's
letter-soup and a court seal's echo of the caption are both discarded without
any word list.

Run:  cd PDF-Linker && python3 -m pytest tests/test_image_region_ocr.py -v
"""
import io
import logging
import sys
import types

import pytest

import pdf_linker as P

fitz = pytest.importorskip("fitz")
log = logging.getLogger("test")

PAGE_TEXT = ("SUPERIOR COURT OF CALIFORNIA COUNTY OF LOS ANGELES\n"
             "ORDER OF DISMISSAL\n"
             "it is hereby ordered that the within action is dismissed\n")
SIGNATURE = "Alison Mackenzie / Judge"


def _doc(img_rect=fitz.Rect(300, 500, 520, 590), with_text=True):
    """A born-digital page carrying one image big enough to hold a line."""
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    if with_text:
        y = 100
        for line in PAGE_TEXT.strip().split("\n"):
            pg.insert_text((72, y), line, fontsize=12)
            y += 20
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 220, 90))
    pix.clear_with(255)
    pg.insert_image(img_rect, pixmap=pix)
    return doc


def _stub_tesseract(monkeypatch, recognised):
    """Stand in for Tesseract, returning an overlay PDF that carries
    `recognised` as its text — the shape `image_to_pdf_or_hocr` returns."""
    calls = []

    def _to_pdf(img, extension="pdf", config=None, timeout=None):
        calls.append(config)
        out = fitz.open()
        pg = out.new_page(width=220, height=90)
        pg.insert_text((5, 40), recognised, fontsize=9)
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
    return calls


# ── the name is recovered ───────────────────────────────────────────────────

def test_a_signature_block_is_read_into_the_page(monkeypatch):
    _stub_tesseract(monkeypatch, SIGNATURE)
    doc = _doc()
    assert "Mackenzie" not in doc[0].get_text("text")     # the whole problem
    assert P._ocr_image_regions(doc, log) == 1
    assert "Mackenzie" in doc[0].get_text("text")


def test_the_pages_own_text_is_untouched(monkeypatch):
    """ADDITIVE: unlike the garbled-page rebuild, nothing is redacted."""
    _stub_tesseract(monkeypatch, SIGNATURE)
    doc = _doc()
    before = doc[0].get_text("text")
    P._ocr_image_regions(doc, log)
    after = doc[0].get_text("text")
    for line in PAGE_TEXT.strip().split("\n"):
        assert line in after, line
    assert len(after) > len(before)


def test_the_page_is_banner_marked(monkeypatch):
    _stub_tesseract(monkeypatch, SIGNATURE)
    doc = _doc()
    P._ocr_image_regions(doc, log)
    assert getattr(doc, P._IMG_OCR_ATTR, {}).get(0) == 1


def test_the_ocr_config_is_passed(monkeypatch):
    # `preserve_interword_spaces` is passed at EVERY call site — a weld
    # manufactured at recognition time is upstream of every cure.
    calls = _stub_tesseract(monkeypatch, SIGNATURE)
    P._ocr_image_regions(_doc(), log)
    assert calls and all(c == P._OCR_CONFIG for c in calls)


# ── and nothing else is dragged in ──────────────────────────────────────────

def test_a_seal_that_only_echoes_the_page_is_discarded(monkeypatch):
    """A court seal OCRs to real words — and every one of them is already in
    the page's text, so the region carries nothing and is dropped."""
    _stub_tesseract(monkeypatch, "SUPERIOR COURT OF CALIFORNIA COUNTY OF "
                                 "LOS ANGELES")
    doc = _doc()
    assert P._ocr_image_regions(doc, log) == 0
    assert not getattr(doc, P._IMG_OCR_ATTR, {})


def test_a_logo_that_ocrs_to_soup_is_discarded(monkeypatch):
    _stub_tesseract(monkeypatch, "|| ~ @@ 1 //")
    assert P._ocr_image_regions(_doc(), log) == 0


def test_an_image_too_small_to_hold_a_line_is_never_rendered(monkeypatch):
    calls = _stub_tesseract(monkeypatch, SIGNATURE)
    doc = _doc(img_rect=fitz.Rect(300, 500, 318, 512))     # 18x12 pt
    assert P._ocr_image_regions(doc, log) == 0
    assert calls == [], "a tiny image should not reach Tesseract at all"


def test_a_page_with_no_text_is_left_to_the_whole_page_pass(monkeypatch):
    """`_ocr_pdf` owns that page — it gives the WHOLE page a text layer, which
    is strictly better than reading one image out of it."""
    calls = _stub_tesseract(monkeypatch, SIGNATURE)
    doc = _doc(with_text=False)
    assert P._ocr_image_regions(doc, log) == 0
    assert calls == []


def test_it_is_silent_without_tesseract(monkeypatch):
    _stub_tesseract(monkeypatch, SIGNATURE)
    monkeypatch.setattr(P, "_find_tesseract", lambda: None)
    assert P._ocr_image_regions(_doc(), log) == 0


# ── the newness filter itself ───────────────────────────────────────────────

def test_new_words_ignores_what_the_page_already_says():
    have = {"superior", "court", "california"}
    assert P._image_ocr_new_words("SUPERIOR COURT OF CALIFORNIA", have) == []
    assert P._image_ocr_new_words("Alison Mackenzie / Judge", have) == [
        "Alison", "Mackenzie", "Judge"]
    # Short tokens and punctuation are not words — a barcode offers nothing.
    assert P._image_ocr_new_words("|| ~ @@ 1 // ab", have) == []
