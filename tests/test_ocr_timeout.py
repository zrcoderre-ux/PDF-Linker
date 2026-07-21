"""
A really large scanned page could make Tesseract stall indefinitely. pytesseract
defaults to no timeout, so one stuck page hung the WHOLE run (python.exe idle at
0% CPU, never finishing). Each OCR ATTEMPT is now bounded so a stall is
escapable, but the page is never skipped: on timeout it is re-rendered at a lower
resolution and retried, grinding down until Tesseract completes — every page
still gets a text layer. The rasterised image is also capped so a pathologically
large page can't produce a bitmap Tesseract chokes on.

Run:  cd PDF-Linker && python3 -m pytest tests/test_ocr_timeout.py -v
"""
import io as _io
import logging
import sys
import types

import fitz
import pytest

import pdf_linker as P

log = logging.getLogger("test")


def test_ocr_timeout_default_and_env(monkeypatch):
    monkeypatch.setattr(P, "_OCR_PAGE_TIMEOUT", None)
    monkeypatch.delenv("PDF_LINKER_OCR_TIMEOUT", raising=False)
    assert P._ocr_page_timeout() == 600                 # 10-minute grind budget

    monkeypatch.setattr(P, "_OCR_PAGE_TIMEOUT", None)
    monkeypatch.setenv("PDF_LINKER_OCR_TIMEOUT", "900")
    assert P._ocr_page_timeout() == 900                 # overridable

    monkeypatch.setattr(P, "_OCR_PAGE_TIMEOUT", None)
    monkeypatch.setenv("PDF_LINKER_OCR_TIMEOUT", "5")
    assert P._ocr_page_timeout() == 30                  # floor: never trivially small

    monkeypatch.setattr(P, "_OCR_PAGE_TIMEOUT", None)
    monkeypatch.setenv("PDF_LINKER_OCR_TIMEOUT", "not-a-number")
    assert P._ocr_page_timeout() == 600                 # garbage -> default


def test_ocr_pixmap_leaves_a_normal_page_at_300_dpi():
    d = fitz.open()
    d.new_page(width=612, height=792)                   # US Letter
    pix = P._ocr_pixmap(d[0])
    assert pix.width == 2550 and pix.height == 3300     # 8.5in/11in * 300
    d.close()


def test_ocr_pixmap_caps_a_large_page():
    d = fitz.open()
    d.new_page(width=2384, height=3370)                 # ISO A0 (33 x 47 in)
    pix = P._ocr_pixmap(d[0])
    assert pix.width * pix.height <= P._OCR_MAX_PIXELS   # held under the cap
    assert pix.width > 0 and pix.height > 0
    d.close()


def _fake_pil(monkeypatch):
    fake_pil = types.ModuleType("PIL")
    fake_image = types.ModuleType("PIL.Image")
    fake_image.open = lambda *a, **k: object()
    fake_pil.Image = fake_image
    monkeypatch.setitem(sys.modules, "PIL", fake_pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", fake_image)


def test_stalled_page_grinds_to_lower_res_instead_of_skipping(monkeypatch):
    # Tesseract "times out" at the first two resolutions, then succeeds — the
    # page must end up with a text layer (grind, not skip), and the retries must
    # step DOWN in dpi.
    good = fitz.open()
    good.new_page(width=612, height=792).insert_text((72, 100), "GRINDTEXT")
    good_bytes = good.tobytes()
    good.close()

    dpis, n = [], {"calls": 0}

    def _fake_ocr(img, extension="", timeout=0):
        n["calls"] += 1
        if n["calls"] <= 2:
            raise RuntimeError("Tesseract process timeout")   # stall
        return good_bytes

    fake_pyt = types.ModuleType("pytesseract")
    fake_pyt.pytesseract = types.SimpleNamespace(tesseract_cmd=None)
    fake_pyt.image_to_pdf_or_hocr = _fake_ocr
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pyt)
    _fake_pil(monkeypatch)
    monkeypatch.setattr(P, "_find_tesseract", lambda: "tesseract")
    monkeypatch.setattr(P, "_tesseract_usable", lambda *a, **k: True)

    real_get_pixmap = fitz.Page.get_pixmap

    def _spy_get_pixmap(self, *a, **k):
        dpis.append(k.get("dpi"))
        return real_get_pixmap(self, *a, **k)
    monkeypatch.setattr(fitz.Page, "get_pixmap", _spy_get_pixmap)

    d = fitz.open()
    d.new_page(width=612, height=792)                   # blank -> needs OCR
    assert P._ocr_pdf(d, log) is True                   # a page WAS OCR'd
    assert "GRINDTEXT" in d[0].get_text()               # text layer added, not skipped
    d.close()

    assert n["calls"] == 3                              # two stalls, then success
    assert dpis == sorted(dpis, reverse=True)           # resolution stepped down
    assert dpis[0] > dpis[-1]


def test_timeout_is_passed_on_every_attempt(monkeypatch):
    # Guard against an edit dropping the timeout: every attempt must carry it.
    seen = []

    def _fake_ocr(img, extension="", timeout=0):
        seen.append(timeout)
        raise RuntimeError("timeout")                   # never succeeds -> all attempts run

    fake_pyt = types.ModuleType("pytesseract")
    fake_pyt.pytesseract = types.SimpleNamespace(tesseract_cmd=None)
    fake_pyt.image_to_pdf_or_hocr = _fake_ocr
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pyt)
    _fake_pil(monkeypatch)
    monkeypatch.setattr(P, "_find_tesseract", lambda: "tesseract")
    monkeypatch.setattr(P, "_tesseract_usable", lambda *a, **k: True)

    d = fitz.open()
    d.new_page(width=612, height=792)
    P._ocr_pdf(d, log)
    d.close()

    assert len(seen) == len(P._OCR_RETRY_FACTORS)       # it ground through every rung
    assert all(t == P._ocr_page_timeout() for t in seen)
