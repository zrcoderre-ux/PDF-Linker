"""
OCR settings that bear on welding and on how far a page's text can be trusted.

Two gaps, both on the recognition side:

  * No Tesseract config was passed anywhere, so `preserve_interword_spaces` was
    off and Tesseract collapsed the run of spaces a two-column caption needs to
    keep. That is a weld manufactured at recognition time, upstream of every
    cure the pseudonymizer has.
  * The grind path re-renders a stalled page at successively lower resolution
    (`_OCR_RETRY_FACTORS` down to 0.24x, floor `_OCR_MIN_DPI` 60). Never
    skipping the page is right, but a page recognised at 72 dpi is not worth the
    same confidence as one at 300, and nothing said so.

Run:  cd PDF-Linker && python3 -m pytest tests/test_ocr_quality.py -v
"""
import logging
import sys
import types

import fitz
import pdf_linker as P

log = logging.getLogger("test")


def _fake_pil(monkeypatch):
    fake_pil = types.ModuleType("PIL")
    fake_image = types.ModuleType("PIL.Image")
    fake_image.open = lambda *a, **k: object()
    fake_pil.Image = fake_image
    monkeypatch.setitem(sys.modules, "PIL", fake_pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", fake_image)


def _layer_bytes(text="OCRTEXT"):
    d = fitz.open()
    d.new_page(width=612, height=792).insert_text((72, 100), text)
    b = d.tobytes()
    d.close()
    return b


def _install(monkeypatch, ocr):
    fake = types.ModuleType("pytesseract")
    fake.pytesseract = types.SimpleNamespace(tesseract_cmd=None)
    fake.image_to_pdf_or_hocr = ocr
    monkeypatch.setitem(sys.modules, "pytesseract", fake)
    _fake_pil(monkeypatch)
    monkeypatch.setattr(P, "_find_tesseract", lambda: "tesseract")
    monkeypatch.setattr(P, "_tesseract_usable", lambda *a, **k: True)


def test_interword_spaces_are_preserved_on_every_attempt():
    # The setting exists and says what it must — a collapsed space run is the
    # weld the whole reduced pass exists to undo.
    assert "preserve_interword_spaces=1" in P._OCR_CONFIG


def test_config_is_passed_to_tesseract(monkeypatch):
    seen = []
    good = _layer_bytes()

    def _ocr(img, extension="", config="", timeout=0):
        seen.append(config)
        return good

    _install(monkeypatch, _ocr)
    d = fitz.open()
    d.new_page(width=612, height=792)               # blank -> needs OCR
    assert P._ocr_pdf(d, log) is True
    d.close()
    assert seen and all(c == P._OCR_CONFIG for c in seen), seen


def test_config_survives_the_grind(monkeypatch):
    # Every retry rung must carry it too, not just the first attempt.
    seen, n = [], {"calls": 0}
    good = _layer_bytes()

    def _ocr(img, extension="", config="", timeout=0):
        seen.append(config)
        n["calls"] += 1
        if n["calls"] <= 2:
            raise RuntimeError("Tesseract process timeout")
        return good

    _install(monkeypatch, _ocr)
    d = fitz.open()
    d.new_page(width=612, height=792)
    assert P._ocr_pdf(d, log) is True
    d.close()
    assert len(seen) == 3
    assert all(c == P._OCR_CONFIG for c in seen), seen


def test_a_page_ground_below_the_dpi_floor_is_flagged(monkeypatch, caplog):
    # It still gets its text layer — never skipped — but the operator is told
    # which pages were recognised at a resolution worth distrusting.
    n = {"calls": 0}
    good = _layer_bytes()

    def _ocr(img, extension="", config="", timeout=0):
        n["calls"] += 1
        if n["calls"] < len(P._OCR_RETRY_FACTORS):
            raise RuntimeError("Tesseract process timeout")
        return good

    _install(monkeypatch, _ocr)
    d = fitz.open()
    d.new_page(width=612, height=792)
    with caplog.at_level(logging.WARNING):
        assert P._ocr_pdf(d, log) is True
    assert "OCRTEXT" in d[0].get_text()             # ground down, not skipped
    d.close()
    assert any("low-confidence" in r.message for r in caplog.records), \
        [r.message for r in caplog.records]


def test_a_full_resolution_page_is_not_flagged(monkeypatch, caplog):
    good = _layer_bytes()
    _install(monkeypatch, lambda img, extension="", config="", timeout=0: good)
    d = fitz.open()
    d.new_page(width=612, height=792)
    with caplog.at_level(logging.WARNING):
        assert P._ocr_pdf(d, log) is True
    d.close()
    assert not any("low-confidence" in r.message for r in caplog.records)
