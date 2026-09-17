"""The image-OCR pass marks a page it has finished with, IN THE PDF, so the
next run does not render and read the same images again.

Every rule in `_ocr_image_regions` decides what to do with a reading after
the reading has been paid for, and the tool replaces the source PDF, so the
next run opens a file in which every decision has already landed — and
still paid for the render: a delivered folder read 494 image regions of a
2,043-page evidence file on every run, 11 to 27 minutes each time, to keep
nothing and correct the same 41 layer words. See `_IMG_OCR_MARK_KEY`.

Run:  cd PDF-Linker && python3 -m pytest tests/test_image_ocr_mark.py -v
"""
import logging
import sys
import types

import pytest

fitz = pytest.importorskip("fitz")

import pdf_linker as P

log = logging.getLogger("test_image_ocr_mark")

PAGE_TEXT = ("SUPERIOR COURT OF CALIFORNIA COUNTY OF LOS ANGELES\n"
             "ORDER OF DISMISSAL\n"
             "it is hereby ordered that the within action is dismissed\n")
SIGNATURE = "Alison Mackenzie / Judge"
SEAL = "SUPERIOR COURT OF CALIFORNIA COUNTY OF LOS ANGELES"


def _doc(img_rect=fitz.Rect(300, 500, 520, 590)):
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    y = 100
    for line in PAGE_TEXT.strip().split("\n"):
        pg.insert_text((72, y), line, fontsize=12)
        y += 20
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 220, 90))
    pix.clear_with(255)
    pg.insert_image(img_rect, pixmap=pix)
    return doc


def _stub_tesseract(monkeypatch, recognised, fail=False):
    calls = []

    def _to_pdf(img, extension="pdf", config=None, timeout=None):
        calls.append(config)
        if fail:
            raise RuntimeError("tesseract timed out")
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


def _save_and_reopen(doc, tmp_path, name="a.pdf"):
    """The way the next run meets the file: saved as the run saves it,
    opened fresh, with no per-run attribute left on the object."""
    p = tmp_path / name
    doc.save(str(p), garbage=3, deflate=True)
    doc.close()
    return fitz.open(str(p))


def test_a_kept_region_marks_the_page_and_the_next_run_renders_nothing(
        monkeypatch, tmp_path):
    calls = _stub_tesseract(monkeypatch, SIGNATURE)
    doc = _doc()
    assert P._ocr_image_regions(doc, log) == 1
    assert P._image_ocr_touched(doc)
    kind, _val = doc.xref_get_key(doc[0].xref, P._IMG_OCR_MARK_KEY)
    assert kind == "string"
    doc = _save_and_reopen(doc, tmp_path)
    n = len(calls)
    assert P._ocr_image_regions(doc, log) == 0
    assert len(calls) == n, "the marked page was rendered and read again"
    assert not P._image_ocr_touched(doc), "nothing changed, nothing to save"


def test_a_discarded_region_marks_the_page_too(monkeypatch, tmp_path):
    """The seal that only echoes the caption is the commonest case, and it
    was re-read on every run to be discarded on every run."""
    calls = _stub_tesseract(monkeypatch, SEAL)
    doc = _doc()
    assert P._ocr_image_regions(doc, log) == 0
    assert P._image_ocr_touched(doc), "the mark alone is a change to save"
    doc = _save_and_reopen(doc, tmp_path)
    n = len(calls)
    P._ocr_image_regions(doc, log)
    assert len(calls) == n


def test_a_region_that_could_not_be_read_leaves_no_mark(monkeypatch):
    _stub_tesseract(monkeypatch, SIGNATURE, fail=True)
    doc = _doc()
    P._ocr_image_regions(doc, log)
    kind, _val = doc.xref_get_key(doc[0].xref, P._IMG_OCR_MARK_KEY)
    assert kind == "null"
    assert not P._image_ocr_touched(doc)


def test_a_changed_image_is_read_again(monkeypatch, tmp_path):
    """The mark fingerprints the images by xref and placement: a page whose
    pictures moved or were replaced is not the page that was read."""
    calls = _stub_tesseract(monkeypatch, SEAL)
    doc = _doc()
    P._ocr_image_regions(doc, log)
    doc = _save_and_reopen(doc, tmp_path)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 220, 90))
    pix.clear_with(200)
    doc[0].insert_image(fitz.Rect(72, 600, 292, 690), pixmap=pix)
    n = len(calls)
    P._ocr_image_regions(doc, log)
    assert len(calls) > n


def test_a_rule_version_bump_reads_the_page_once_more(monkeypatch, tmp_path):
    calls = _stub_tesseract(monkeypatch, SEAL)
    doc = _doc()
    P._ocr_image_regions(doc, log)
    doc = _save_and_reopen(doc, tmp_path)
    monkeypatch.setattr(P, "_IMG_OCR_MARK_VERSION", P._IMG_OCR_MARK_VERSION + 1)
    n = len(calls)
    P._ocr_image_regions(doc, log)
    assert len(calls) > n


def test_a_page_this_run_read_whole_is_marked_for_the_next(monkeypatch, tmp_path):
    """Same engine, same dpi: the next run should not read its image either,
    and until now had no way to know."""
    calls = _stub_tesseract(monkeypatch, SIGNATURE)
    doc = _doc()
    P._note_ocr_read_page(doc[0])
    P._ocr_image_regions(doc, log)
    assert calls == []
    assert P._image_ocr_touched(doc)
    doc = _save_and_reopen(doc, tmp_path)
    P._ocr_image_regions(doc, log)
    assert calls == []


def test_the_pass_reports_a_layer_repair_as_a_change_to_save():
    """The repair rewrote the page and the return value said nothing, so on
    a PDF already linked the fast path closed the file unsaved and the same
    words were corrected again on the next run. `process_pdf` must ask
    `_image_ocr_touched` beside the region count."""
    import inspect
    src = inspect.getsource(P.process_pdf)
    i = src.index("_ocr_image_regions(doc, log)")
    j = src.index("_pdf_is_stamped(doc) and not relink and not ocr_changed")
    assert "_image_ocr_touched(doc)" in src[i:j]
