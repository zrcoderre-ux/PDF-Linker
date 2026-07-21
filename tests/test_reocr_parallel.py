"""
Re-OCR of garbled-text pages (the path a big scanned exhibit with broken text
layers actually takes) now runs its render+OCR across the worker pool, like the
no-text OCR path — rendering stays on the main thread, Tesseract runs in
parallel, and the redact+overlay stays serial. Every garbled page still gets a
fresh text layer.

Run:  cd PDF-Linker && python3 -m pytest tests/test_reocr_parallel.py -v
"""
import logging
import sys
import types

import fitz
import pytest

import pdf_linker as P

log = logging.getLogger("test")


def _good_overlay_bytes():
    d = fitz.open()
    d.new_page(width=612, height=792).insert_text((72, 100), "FRESHOCRTEXT")
    b = d.tobytes()
    d.close()
    return b


def _install(monkeypatch, ocr_fn):
    fake = types.ModuleType("pytesseract")
    fake.pytesseract = types.SimpleNamespace(tesseract_cmd=None)
    fake.image_to_pdf_or_hocr = ocr_fn
    monkeypatch.setitem(sys.modules, "pytesseract", fake)
    fake_pil = types.ModuleType("PIL")
    fake_image = types.ModuleType("PIL.Image")
    fake_image.open = lambda *a, **k: object()
    fake_pil.Image = fake_image
    monkeypatch.setitem(sys.modules, "PIL", fake_pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", fake_image)
    monkeypatch.setattr(P, "_find_tesseract", lambda: "tesseract")
    monkeypatch.setattr(P, "_tesseract_usable", lambda *a, **k: True)
    # Treat every page as garbled so the re-OCR path fires.
    monkeypatch.setattr(P, "_text_looks_garbled", lambda t: True)


def test_reocr_parallel_relayers_every_page(monkeypatch):
    good = _good_overlay_bytes()
    calls = []

    def _ocr(img, extension="", timeout=0):
        calls.append(timeout)
        return good

    _install(monkeypatch, _ocr)
    monkeypatch.setattr(P, "_OCR_WORKERS", 3)          # force the parallel path

    d = fitz.open()
    for i in range(6):
        d.new_page(width=612, height=792).insert_text((72, 100), f"garbled {i}")
    n = P._reocr_garbled_pages(d, log)
    assert n == 6                                       # all re-OCR'd
    for pno in range(6):
        assert "FRESHOCRTEXT" in d[pno].get_text(), pno
    d.close()
    assert len(calls) == 6 and all(t == P._ocr_page_timeout() for t in calls)


def test_reocr_stall_is_ground_down_not_skipped(monkeypatch):
    good = _good_overlay_bytes()
    state = {"n": 0}

    def _ocr(img, extension="", timeout=0):
        state["n"] += 1
        if state["n"] == 1:                             # first page stalls once
            raise RuntimeError("Tesseract process timeout")
        return good

    _install(monkeypatch, _ocr)
    monkeypatch.setattr(P, "_OCR_WORKERS", 2)

    d = fitz.open()
    for i in range(2):
        d.new_page(width=612, height=792).insert_text((72, 100), f"garbled {i}")
    n = P._reocr_garbled_pages(d, log)
    assert n == 2                                       # stalled page ground down
    assert "FRESHOCRTEXT" in d[0].get_text()
    assert "FRESHOCRTEXT" in d[1].get_text()
    d.close()
