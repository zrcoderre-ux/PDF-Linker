"""The gutter a page-wide OCR pass threw away.

A pleading page's line numbers are a narrow column of one- and two-digit
numbers in the left margin, and a page-wide OCR pass routinely drops the whole
column: Tesseract's layout analysis reads a strip that far from the block it is
segmenting as furniture. Measured on a scanned third amended complaint, the
page's own OCR recovered every word of the caption — the attorney block, both
caption columns, the FILED stamp — and not ONE of the numbers 1 through 28.

What that costs is not the numbering. `_pleading_gutter` finding no column makes
`_page_lined_rows` decline the page, and with it goes everything the pleading
path does: the two-column caption split, the firm-sidebar exclusion, the
per-column scrub and any "p.X:Y" to cite the page by. So the TITLE PAGE of that
complaint exported as one positional run with the rotated "Electronically
Received" margin stamp laid word by word through the middle of its caption, the
party column and the case-number column collapsed together — a scanned pleading
rendered as though it were an exhibit photograph.

The numbers were legible the whole time: cropping to the margin removes the
layout decision that discarded them, and the strip reads back 1-28.

Run:  cd PDF-Linker && python3 -m pytest tests/test_gutter_column_ocr.py -v
"""
import logging
import sys
import types

import pytest

import pdf_linker as P

fitz = pytest.importorskip("fitz")
log = logging.getLogger("test")

LEFT = ["HELEN RASHO, an individual,", "and DOES 1 through 30,",
        "                 Plaintiffs,", "         vs.",
        "QUILLMARK BUILDERS, LLC,", "a California corporation,",
        "                 Defendants.", "", "", "", "", "", "", ""]
RIGHT = ["Case No. 25STCV37838", "", "COMPLAINT FOR DAMAGES", "",
         "1. Breach of Contract", "2. Negligence", "", "", "", "", "", "",
         "", ""]


def _page(numbers=False, sideways=True, rows=len(LEFT)):
    """A scanned pleading page as its page-wide OCR left it: body text, a
    rotated e-filing stamp in the margin, and — unless `numbers` — no gutter."""
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    y = 90
    for i in range(rows):
        if numbers:
            pg.insert_text((36, y), str(i + 1), fontsize=11)
        pg.insert_text((72, y), LEFT[i] or "x", fontsize=11)
        if RIGHT[i]:
            pg.insert_text((330, y), RIGHT[i], fontsize=11)
        y += 24
    if sideways:
        pg.insert_text((14, 560), "Electronically Received 12/12/2022",
                       fontsize=9, rotate=90)
    return doc


def _stub_tesseract(monkeypatch, numbers, ys=None):
    """Stand in for Tesseract reading the margin strip: an overlay PDF holding
    `numbers` down the page, the shape `image_to_pdf_or_hocr` returns."""
    calls = []

    def _to_pdf(img, extension="pdf", config=None, timeout=None):
        calls.append(config)
        out = fitz.open()
        pg = out.new_page(width=34, height=792)
        for k, n in enumerate(numbers):
            pg.insert_text((6, (ys or [90 + 24 * i for i in range(len(numbers))])[k]),
                           str(n), fontsize=11)
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


# ── the column comes back ───────────────────────────────────────────────────

def test_the_strip_is_the_margin_between_the_sidebar_and_the_body():
    rect = P._gutter_probe_strip(_page()[0])
    assert rect is not None
    assert rect.x0 > 14                      # clear of the rotated stamp
    assert rect.x1 < 72                      # clear of the body's first word


def test_a_page_that_lost_its_numbers_gets_them_back(monkeypatch):
    _stub_tesseract(monkeypatch, range(1, 15))
    doc = _page()
    assert P._pleading_gutter(doc[0]) is None            # the whole problem
    assert P._page_lined_rows(doc[0]) is None
    assert P._ocr_gutter_column(doc, log) == 1
    assert P._pleading_gutter(doc[0]) is not None


def test_and_the_page_is_then_rendered_as_pleading_paper(monkeypatch):
    """The numbering is not the point of it: what the gutter buys is the whole
    pleading path — numbered rows, and the caption's two columns apart."""
    _stub_tesseract(monkeypatch, range(1, 15))
    doc = _page()
    P._ocr_gutter_column(doc, log)
    rows = P._page_lined_rows(doc[0])
    assert rows
    first = next(segs for num, segs in rows if num == 1)
    assert [t for _x, t in first] == ["HELEN RASHO, an individual,",
                                      "Case No. 25STCV37838"]


def test_the_sidebar_stamp_does_not_reach_the_rows(monkeypatch):
    _stub_tesseract(monkeypatch, range(1, 15))
    doc = _page()
    P._ocr_gutter_column(doc, log)
    rows = P._page_lined_rows(doc[0])
    assert "Electronically" not in " ".join(t for _n, segs in rows
                                            for _x, t in segs)


# ── and only where it is really a gutter ────────────────────────────────────

def test_a_page_that_already_has_its_numbers_is_not_probed(monkeypatch):
    calls = _stub_tesseract(monkeypatch, range(1, 15))
    doc = _page(numbers=True)
    assert P._ocr_gutter_column(doc, log) == 0
    assert calls == []                        # nothing rendered at all


def test_a_margin_reading_as_anything_but_numbering_is_discarded(monkeypatch):
    """The adoption test is what lets the gate stay loose: small integers
    ASCENDING down the strip, and nothing else. A stamp's date, a Bates number
    and a page fraction all put digits in a margin, in no order."""
    _stub_tesseract(monkeypatch, [12, 3, 28, 7, 1, 19])
    doc = _page()
    assert P._ocr_gutter_column(doc, log) == 0
    assert P._pleading_gutter(doc[0]) is None


def test_too_few_numbers_is_not_a_column(monkeypatch):
    _stub_tesseract(monkeypatch, [1, 2, 3, 4])            # under the floor
    doc = _page()
    assert P._ocr_gutter_column(doc, log) == 0


def test_a_page_with_too_few_rows_is_never_rendered(monkeypatch):
    """An exhibit photograph, a slip sheet, a cover page: probing every scanned
    page of a 119-page exhibit set would spend ~0.3 s a page to find nothing."""
    calls = _stub_tesseract(monkeypatch, range(1, 15))
    doc = _page(rows=4)
    assert P._ocr_gutter_column(doc, log) == 0
    assert calls == []


def test_a_page_with_no_margin_to_read_is_never_rendered(monkeypatch):
    calls = _stub_tesseract(monkeypatch, range(1, 15))
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    for i in range(len(LEFT)):                # body hard against the left edge
        pg.insert_text((3, 90 + 24 * i), LEFT[i] or "x", fontsize=11)
    assert P._gutter_probe_strip(pg) is None
    assert P._ocr_gutter_column(doc, log) == 0
    assert calls == []


def test_a_textless_page_is_left_to_the_whole_page_pass(monkeypatch):
    calls = _stub_tesseract(monkeypatch, range(1, 15))
    doc = fitz.open()
    doc.new_page(width=612, height=792)
    assert P._ocr_gutter_column(doc, log) == 0
    assert calls == []


def test_the_probe_reads_digits_only(monkeypatch):
    """Digits only, so the pass cannot put a WORD into the margin however it
    reads the sidebar's letters."""
    calls = _stub_tesseract(monkeypatch, range(1, 15))
    P._ocr_gutter_column(_page(), log)
    assert calls and all("tessedit_char_whitelist=0123456789" in c
                         for c in calls)


def test_without_tesseract_the_pass_does_nothing(monkeypatch):
    monkeypatch.setattr(P, "_find_tesseract", lambda: None)
    doc = _page()
    assert P._ocr_gutter_column(doc, log) == 0
