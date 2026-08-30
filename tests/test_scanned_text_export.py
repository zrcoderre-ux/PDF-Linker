"""A scanned-only PDF exported NOTHING, and the OCR had already read it.

`process_pdf` decides whether to write a `.txt` companion from the NATIVE text,
before OCR runs — and it has to: OCR adds a text layer to every scanned page,
so asking only afterwards would call every document text-based and the
"scanned-only PDFs are skipped" rule would mean nothing.

But a folder of 28 scanned filings then came back linked, bookmarked, and with
no `Text Files` folder at all — the deliverable — while that same OCR text was
good enough for the citation parse (83 citations on the first file), the
linking, the bookmarks and the leak scan that ran off it. The skip's stated
reason was that such an export "would be empty (or, if OCR ran,
lower-fidelity)"; empty is answered by MEASURING the OCR'd text instead of
assuming it, and lower-fidelity is what the low-confidence page banners are for.

So the pre-OCR answer stands where it was YES, and a NO is re-asked of the text
OCR actually produced — never the other way round, so a document already judged
text-based can never lose its export to a later pass.

Run:  cd PDF-Linker && python3 -m pytest tests/test_scanned_text_export.py -v
"""
import logging

import pytest

import pdf_linker as P

fitz = pytest.importorskip("fitz")
log = logging.getLogger("test")

BODY = ("MEMORANDUM OF POINTS AND AUTHORITIES IN SUPPORT OF THE MOTION "
        "TO COMPEL FURTHER RESPONSES TO REQUESTS FOR PRODUCTION filed by "
        "the plaintiff in this action and served on all parties of record "
        "together with the separate statement required by the rules")


def _scanned_pdf(folder, pages=2, name="brief.pdf"):
    """A page of pure image: no native text on any page — what every one of
    those 28 filings looked like when the export decision was made."""
    doc = fitz.open()
    for _ in range(pages):
        pg = doc.new_page(width=612, height=792)
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 600, 780))
        pix.clear_with(250)
        pg.insert_image(fitz.Rect(6, 6, 606, 786), pixmap=pix)
    p = folder / name
    doc.save(str(p))
    doc.close()
    return p


def _stub_ocr(monkeypatch, text=BODY, changed=True):
    """Stand in for `_ocr_pdf`: give every textless page the layer OCR would
    have given it. The decision under test is what `process_pdf` does with the
    result, not how the result was recognised."""
    def _fake(doc, log):
        if not changed:
            return False
        for page in doc:
            if page.get_text("text").strip():
                continue
            y = 60
            words = text.split()
            for i in range(0, len(words), 9):
                page.insert_text((40, y), " ".join(words[i:i + 9]),
                                 fontsize=11)
                y += 18
        return True

    monkeypatch.setattr(P, "_ocr_pdf", _fake)
    monkeypatch.setattr(P, "_ocr_image_regions", lambda doc, log: 0)


# ── the bug ────────────────────────────────────────────────────────────────

def test_a_scanned_pdf_that_ocrd_well_gets_its_text_export(tmp_path,
                                                           monkeypatch):
    _stub_ocr(monkeypatch)
    p = _scanned_pdf(tmp_path)
    assert P.process_pdf(p, log, extract_text=False) is True   # sanity: opens
    assert P.process_pdf(_scanned_pdf(tmp_path, name="b2.pdf"), log) is True
    assert (tmp_path / "Text Files" / "b2.txt").exists()


def test_the_export_carries_what_the_ocr_read(tmp_path, monkeypatch):
    _stub_ocr(monkeypatch)
    P.process_pdf(_scanned_pdf(tmp_path), log)
    body = (tmp_path / "Text Files" / "brief.txt").read_text(encoding="utf-8")
    flat = " ".join(body.split())          # the export wraps at the page width
    assert "MEMORANDUM OF POINTS AND AUTHORITIES" in flat
    assert "separate statement required by the rules" in flat


# ── …and what the re-ask must NOT do ───────────────────────────────────────

def test_a_scan_ocr_could_not_read_is_still_skipped(tmp_path, monkeypatch):
    """The real case the skip exists for survives: an unreadable scan fails the
    SAME measurement afterwards, so it still writes nothing."""
    _stub_ocr(monkeypatch, text="a b")          # two words on the page
    P.process_pdf(_scanned_pdf(tmp_path), log)
    assert not (tmp_path / "Text Files").exists()


def test_no_text_still_wins(tmp_path, monkeypatch):
    """`--no-text` is the operator saying no; the re-ask never overrides it."""
    _stub_ocr(monkeypatch)
    P.process_pdf(_scanned_pdf(tmp_path), log, extract_text=False)
    assert not (tmp_path / "Text Files").exists()


def test_nothing_is_re_asked_when_ocr_changed_nothing(tmp_path, monkeypatch):
    """An unchanged document cannot answer differently than it did a moment
    ago, so it is never measured twice — the log would just repeat itself."""
    _stub_ocr(monkeypatch, changed=False)
    asked = []
    real = P._pdf_has_text_layer
    monkeypatch.setattr(P, "_pdf_has_text_layer",
                        lambda doc, log, after_ocr=False:
                        asked.append(after_ocr) or real(doc, log, after_ocr))
    P.process_pdf(_scanned_pdf(tmp_path), log)
    assert asked == [False]


def test_a_native_document_is_never_re_asked(tmp_path, monkeypatch):
    """The pre-OCR YES stands: a document already judged text-based can never
    lose its export to a later pass."""
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    y = 60
    words = BODY.split()
    for i in range(0, len(words), 9):
        pg.insert_text((40, y), " ".join(words[i:i + 9]), fontsize=11)
        y += 18
    p = tmp_path / "native.pdf"
    doc.save(str(p))
    doc.close()

    asked = []
    real = P._pdf_has_text_layer
    monkeypatch.setattr(P, "_pdf_has_text_layer",
                        lambda d, log, after_ocr=False:
                        asked.append(after_ocr) or real(d, log, after_ocr))
    P.process_pdf(p, log)
    assert asked == [False]
    assert (tmp_path / "Text Files" / "native.txt").exists()


# ── the measurement itself is the same one, both times ─────────────────────

def test_the_after_ocr_label_does_not_change_the_answer(tmp_path):
    """`after_ocr` labels the log line and nothing else — two passes that
    measured differently could disagree about one document."""
    p = _scanned_pdf(tmp_path)
    doc = fitz.open(str(p))
    assert (P._pdf_has_text_layer(doc, log)
            is P._pdf_has_text_layer(doc, log, after_ocr=True))
    doc.close()


def test_the_log_says_which_pass_asked(tmp_path, caplog):
    p = _scanned_pdf(tmp_path)
    doc = fitz.open(str(p))
    with caplog.at_level(logging.INFO):
        P._pdf_has_text_layer(doc, logging.getLogger("test"), after_ocr=True)
    doc.close()
    assert "(after OCR)" in caplog.text
