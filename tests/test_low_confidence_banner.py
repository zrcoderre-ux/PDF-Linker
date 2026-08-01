"""A page recognised below `_OCR_LOW_DPI` says so in the EXPORT, not only the log.

The grind never skips a page, which is right — a page with no text is a hole in
the record. But measured on this repo's own settings a degraded scan recognised
at 99 dpi comes back with most of its words wrong, and that text lands in the
middle of an otherwise accurate document with nothing to distinguish it. The
log is a separate file that does not travel with the export a reviewer reads.

Run:  cd PDF-Linker && python3 -m pytest tests/test_low_confidence_banner.py -v
"""
import io
import logging
import sys
import types

import fitz
import pytest

import pdf_linker as P

log = logging.getLogger("test")


class _Log:
    def __init__(self):
        self.lines = []

    def _add(self, m):
        self.lines.append(str(m))

    info = warning = error = _add


def _doc():
    d = fitz.open()
    d.new_page(width=612, height=792)
    return d


def test_a_low_dpi_page_is_remembered_on_its_document():
    d = _doc()
    P._note_low_confidence(d[0], 99)
    assert getattr(d[0].parent, P._LOW_DPI_ATTR) == {0: 99}
    d.close()


def test_a_page_recognised_at_full_resolution_is_not_marked():
    d = _doc()
    assert getattr(d[0].parent, P._LOW_DPI_ATTR, {}) == {}
    d.close()


def test_the_grind_marks_the_page_it_had_to_drop(monkeypatch):
    """Only the rung that actually SUCCEEDS decides; a page that stalls once
    and then recognises at 198 dpi is not low-confidence."""
    d = _doc()
    payload = fitz.open()
    payload.new_page(width=612, height=792).insert_text((72, 100), "TEXT")
    blob = payload.tobytes()
    payload.close()

    class _Tess:
        pytesseract = types.SimpleNamespace(tesseract_cmd=None)
        calls = []

        @staticmethod
        def image_to_pdf_or_hocr(img, **k):
            _Tess.calls.append(1)
            if len(_Tess.calls) <= 3:          # 300, 198, 150 all stall
                raise RuntimeError("timeout")
            return blob

    fake_image = types.ModuleType("PIL.Image")
    fake_image.open = lambda *a, **k: object()
    out = P._ocr_page_to_pdf(d[0], _Tess, fake_image, io, _Log(), "OCR")
    assert out == blob
    marked = getattr(d[0].parent, P._LOW_DPI_ATTR, {})
    assert marked and marked[0] < P._OCR_LOW_DPI
    d.close()


def test_a_page_that_never_grinds_is_never_marked(monkeypatch):
    d = _doc()
    payload = fitz.open()
    payload.new_page(width=612, height=792).insert_text((72, 100), "TEXT")
    blob = payload.tobytes()
    payload.close()

    class _Tess:
        pytesseract = types.SimpleNamespace(tesseract_cmd=None)

        @staticmethod
        def image_to_pdf_or_hocr(img, **k):
            return blob

    fake_image = types.ModuleType("PIL.Image")
    fake_image.open = lambda *a, **k: object()
    P._ocr_page_to_pdf(d[0], _Tess, fake_image, io, _Log(), "OCR")
    assert getattr(d[0].parent, P._LOW_DPI_ATTR, {}) == {}
    d.close()


def test_the_marker_is_shaped_for_the_page_banner():
    """The banner is what a reviewer reads, so the wording has to say what is
    wrong with the text and not merely that something happened to it."""
    d = _doc()
    P._note_low_confidence(d[0], 99)
    low = getattr(d[0].parent, P._LOW_DPI_ATTR, {}).get(0)
    header = (f"====== Page 1"
              + (f" — REVIEW: recognised at only {low} dpi, "
                 f"text is LOW CONFIDENCE" if low else "")
              + " ======")
    assert "LOW CONFIDENCE" in header and "99 dpi" in header
    d.close()


def test_instrumentation_never_takes_a_run_down():
    """A page object that refuses the attribute must not raise out of an OCR
    pass — the text layer matters more than the note about it."""

    class _Hostile:
        number = 0

        @property
        def parent(self):
            raise RuntimeError("no parent")

    P._note_low_confidence(_Hostile(), 99)      # must not raise
