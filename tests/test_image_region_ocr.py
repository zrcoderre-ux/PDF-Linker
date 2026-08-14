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


# ── …and a page that was already read is not read AGAIN ────────────────────
# The newness filter asks whether the region carries anything the PAGE lacks.
# That is the right question for a seal echoing the caption and the wrong one
# for a scanned exhibit arriving with its filer's own OCR layer over it: there
# the page's text IS the image's text, so the only "new" words are the handful
# the two engines read differently — and the overlay then lands a SECOND
# reading of the whole page on top of the first.

SCAN = ("DECLARATION OF SERVICE I am employed in the County of Los Angeles "
        "I served the foregoing document on the interested parties herein")
# What a second engine makes of the same page: two words differently.
REREAD = SCAN.replace("foregoing", "foregolng").replace("interested",
                                                        "lnterested")


def _scanned_doc(layer=SCAN):
    """A scanned page whose filer's OCR layer already sits over the image."""
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 612, 792))
    pix.clear_with(250)
    pg.insert_image(fitz.Rect(0, 0, 612, 792), pixmap=pix)
    y = 100
    for i in range(0, len(layer), 60):
        pg.insert_text((60, y), layer[i:i + 60], fontsize=11)
        y += 16
    return doc


def test_a_scan_that_already_carries_an_ocr_layer_is_not_read_again(monkeypatch):
    _stub_tesseract(monkeypatch, REREAD)
    doc = _scanned_doc()
    before = doc[0].get_text("text")
    assert P._ocr_image_regions(doc, log) == 0
    assert doc[0].get_text("text") == before


def test_the_export_does_not_carry_the_page_twice(monkeypatch):
    """The symptom, counted: 23 words became 46."""
    _stub_tesseract(monkeypatch, REREAD)
    doc = _scanned_doc()
    before = len(doc[0].get_text("text").split())
    P._ocr_image_regions(doc, log)
    assert len(doc[0].get_text("text").split()) == before


def test_the_words_the_two_engines_read_differently_are_not_a_find(monkeypatch):
    """`foregolng` and `lnterested` clear `_IMG_OCR_MIN_NEW` on any page of
    prose — which is why the page-wide test cannot be the only one."""
    have = {w.lower() for w in P._IMG_OCR_WORD_RE.findall(SCAN)}
    assert len(P._image_ocr_new_words(REREAD, have)) >= P._IMG_OCR_MIN_NEW


def test_running_the_pass_twice_adds_nothing(monkeypatch):
    """The tool REPLACES the source PDF, so the overlay is in the file the next
    run opens. Idempotence used to rest on our own OCR being deterministic;
    now the region says it has been read."""
    _stub_tesseract(monkeypatch, SIGNATURE)
    doc = _doc()
    assert P._ocr_image_regions(doc, log) == 1
    once = doc[0].get_text("text")
    assert P._ocr_image_regions(doc, log) == 0
    assert doc[0].get_text("text") == once


def test_a_signature_block_beside_body_text_is_still_read(monkeypatch):
    """The rule is scoped to the RECT, so text elsewhere on the page — even
    text the OCR happens to echo — never suppresses a real find."""
    _stub_tesseract(monkeypatch, SIGNATURE)
    doc = _doc()
    assert P._ocr_image_regions(doc, log) == 1
    assert "Mackenzie" in doc[0].get_text("text")


@pytest.mark.parametrize("found,expected", [
    (SCAN, True),                 # exactly what is printed there
    (REREAD, True),               # the same page, read a second way
    ("Alison Mackenzie Judge", False),        # nothing of it is there
    ("", False),                  # a logo: no words at all
])
def test_already_read_is_measured_inside_the_rect(found, expected):
    doc = _scanned_doc()
    rect = fitz.Rect(0, 0, 612, 792)
    assert P._image_ocr_already_read(doc[0], rect, found) is expected
