"""
A really large scanned page could make Tesseract stall indefinitely. pytesseract
defaults to no timeout, so one stuck page hung the WHOLE run (python.exe idle at
0% CPU, never finishing). Each page now gets a timeout so a stall costs a skip,
not the job, and the rasterised image is capped so a pathologically large page
can't produce a bitmap Tesseract chokes on.

Run:  cd PDF-Linker && python3 -m pytest tests/test_ocr_timeout.py -v
"""
import fitz
import pytest

import pdf_linker as P


def test_ocr_timeout_default_and_env(monkeypatch):
    monkeypatch.setattr(P, "_OCR_PAGE_TIMEOUT", None)
    monkeypatch.delenv("PDF_LINKER_OCR_TIMEOUT", raising=False)
    assert P._ocr_page_timeout() == 300                 # sensible default

    monkeypatch.setattr(P, "_OCR_PAGE_TIMEOUT", None)
    monkeypatch.setenv("PDF_LINKER_OCR_TIMEOUT", "600")
    assert P._ocr_page_timeout() == 600                 # overridable

    monkeypatch.setattr(P, "_OCR_PAGE_TIMEOUT", None)
    monkeypatch.setenv("PDF_LINKER_OCR_TIMEOUT", "5")
    assert P._ocr_page_timeout() == 30                  # floor: never trivially small

    monkeypatch.setattr(P, "_OCR_PAGE_TIMEOUT", None)
    monkeypatch.setenv("PDF_LINKER_OCR_TIMEOUT", "not-a-number")
    assert P._ocr_page_timeout() == 300                 # garbage -> default


def test_ocr_pixmap_leaves_a_normal_page_at_300_dpi():
    d = fitz.open()
    d.new_page(width=612, height=792)                   # US Letter
    pix = P._ocr_pixmap(d[0])
    # 8.5in * 300 = 2550, 11in * 300 = 3300
    assert pix.width == 2550 and pix.height == 3300
    d.close()


def test_ocr_pixmap_caps_a_large_page():
    d = fitz.open()
    d.new_page(width=2384, height=3370)                 # ISO A0 (33 x 47 in)
    pix = P._ocr_pixmap(d[0])
    # At a flat 300 dpi this page would be ~1.4e8 px; the cap holds it down.
    assert pix.width * pix.height <= P._OCR_MAX_PIXELS
    assert pix.width > 0 and pix.height > 0
    d.close()


def test_both_ocr_paths_pass_a_timeout(monkeypatch):
    # Guard against a future edit dropping the timeout on either call site: a
    # fake pytesseract records the timeout it is handed. PIL is stubbed so the
    # test runs even where Pillow/pytesseract aren't installed.
    import sys
    import types

    calls = []

    fake_pyt = types.ModuleType("pytesseract")
    fake_pyt.pytesseract = types.SimpleNamespace(tesseract_cmd=None)

    def _fake_ocr(img, extension="", timeout=0):
        calls.append(timeout)
        raise RuntimeError("stop here — we only care about the timeout arg")
    fake_pyt.image_to_pdf_or_hocr = _fake_ocr

    fake_pil = types.ModuleType("PIL")
    fake_image = types.ModuleType("PIL.Image")
    fake_image.open = lambda *a, **k: object()
    fake_pil.Image = fake_image

    monkeypatch.setitem(sys.modules, "pytesseract", fake_pyt)
    monkeypatch.setitem(sys.modules, "PIL", fake_pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", fake_image)
    monkeypatch.setattr(P, "_find_tesseract", lambda: "tesseract")
    monkeypatch.setattr(P, "_tesseract_usable", lambda *a, **k: True)

    import logging
    log = logging.getLogger("test")

    d = fitz.open()
    d.new_page(width=612, height=792)                   # blank -> no text -> OCR
    P._ocr_pdf(d, log)
    d.close()

    assert calls and all(t == P._ocr_page_timeout() for t in calls)
