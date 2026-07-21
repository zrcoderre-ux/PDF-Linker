"""
OCR is the dominant cost on a scanned set and Tesseract runs as a subprocess, so
pages are OCR'd across a thread pool (rendering stays on the main thread because
PyMuPDF is not thread-safe). Every page still gets its text layer, and a page
that stalls at full resolution is ground down afterwards — parallel speed without
losing grind-don't-skip.

Run:  cd PDF-Linker && python3 -m pytest tests/test_ocr_parallel.py -v
"""
import logging
import sys
import types

import fitz
import pytest

import pdf_linker as P

log = logging.getLogger("test")


def _fake_pil(monkeypatch):
    fake_pil = types.ModuleType("PIL")
    fake_image = types.ModuleType("PIL.Image")
    fake_image.open = lambda *a, **k: object()
    fake_pil.Image = fake_image
    monkeypatch.setitem(sys.modules, "PIL", fake_pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", fake_image)


def _good_overlay_bytes():
    good = fitz.open()
    good.new_page(width=612, height=792).insert_text((72, 100), "GRINDTEXT")
    b = good.tobytes()
    good.close()
    return b


def _install_fake_tess(monkeypatch, ocr_fn):
    fake = types.ModuleType("pytesseract")
    fake.pytesseract = types.SimpleNamespace(tesseract_cmd=None)
    fake.image_to_pdf_or_hocr = ocr_fn
    monkeypatch.setitem(sys.modules, "pytesseract", fake)
    _fake_pil(monkeypatch)
    monkeypatch.setattr(P, "_find_tesseract", lambda: "tesseract")
    monkeypatch.setattr(P, "_tesseract_usable", lambda *a, **k: True)


def test_ocr_workers_default_and_env(monkeypatch):
    monkeypatch.setattr(P, "_OCR_WORKERS", None)
    monkeypatch.setenv("PDF_LINKER_OCR_WORKERS", "3")
    assert P._ocr_workers() == 3
    monkeypatch.setattr(P, "_OCR_WORKERS", None)
    monkeypatch.setenv("PDF_LINKER_OCR_WORKERS", "0")
    assert P._ocr_workers() == 1                      # floored at 1
    monkeypatch.setattr(P, "_OCR_WORKERS", None)
    monkeypatch.setenv("PDF_LINKER_OCR_WORKERS", "junk")
    assert P._ocr_workers() == 1
    monkeypatch.setattr(P, "_OCR_WORKERS", None)
    monkeypatch.delenv("PDF_LINKER_OCR_WORKERS", raising=False)
    assert 1 <= P._ocr_workers() <= 6                 # cores-1, capped


def test_parallel_every_page_gets_its_text_layer(monkeypatch):
    good = _good_overlay_bytes()
    calls = []

    def _ocr(img, extension="", timeout=0):
        calls.append(timeout)
        return good

    _install_fake_tess(monkeypatch, _ocr)
    monkeypatch.setattr(P, "_OCR_WORKERS", 3)          # force the parallel path

    d = fitz.open()
    for _ in range(6):
        d.new_page(width=612, height=792)              # 6 blank pages -> all OCR
    assert P._ocr_pdf(d, log) is True
    for pno in range(6):
        assert "GRINDTEXT" in d[pno].get_text(), pno   # none skipped
    d.close()

    assert len(calls) == 6                             # one OCR per page
    assert all(t == P._ocr_page_timeout() for t in calls)


def test_parallel_stall_is_ground_down_not_skipped(monkeypatch):
    # First OCR call (full-res, in the pool) stalls; every later call succeeds —
    # so the stalled page is collected and ground down afterwards, still getting
    # its text layer. With one worker the pool runs pages one at a time, making
    # "the first call" deterministic.
    good = _good_overlay_bytes()
    state = {"n": 0}

    def _ocr(img, extension="", timeout=0):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("Tesseract process timeout")
        return good

    _install_fake_tess(monkeypatch, _ocr)
    monkeypatch.setattr(P, "_OCR_WORKERS", 2)          # parallel path (2 pages)

    d = fitz.open()
    for _ in range(2):
        d.new_page(width=612, height=792)
    assert P._ocr_pdf(d, log) is True
    # Both pages end up with text: the one that stalled was ground down, not
    # skipped.
    assert "GRINDTEXT" in d[0].get_text()
    assert "GRINDTEXT" in d[1].get_text()
    d.close()
