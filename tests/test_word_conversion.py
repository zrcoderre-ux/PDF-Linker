"""
Bulk Word-document conversion: when a case folder holds a real stack of Word
filings (>= word_doc_min, default 5) beside the PDFs, each .docx/.docm is
converted to the same scrubbed .txt export a PDF gets — pseudonymized, leak-
reported, name-scrubbed filename — but never hyperlinked. Below the threshold a
couple of Word docs are left alone so the usual mostly-PDF workflow is
unaffected. These tests need neither fitz nor openpyxl.

Run:  cd PDF-Linker && python3 -m pytest tests/test_word_conversion.py -v
"""
import importlib.util
import logging
import sys
import zipfile
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pdf_linker", _ROOT / "pdf_linker.py")
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)

log = logging.getLogger("test")
DET = {k: pl._PN_DETECTORS[k] for k in pl._PN_DEFAULT_DETECTORS}
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _docx(path, body_xml):
    """Write a minimal .docx whose word/document.xml body is `body_xml`."""
    doc = (f'<?xml version="1.0" encoding="UTF-8"?>'
           f'<w:document xmlns:w="{_W}"><w:body>{body_xml}</w:body></w:document>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", doc)
    return path


def _para(*runs):
    inner = "".join(f'<w:r><w:t xml:space="preserve">{t}</w:t></w:r>' for t in runs)
    return f"<w:p>{inner}</w:p>"


def _pz():
    reg = pl._PnFakeRegistry()
    terms = pl._pn_build_terms(["Ernest N Ramirez", "Ford Motor Company"],
                               ["24STCV23198"], [], registry=reg)
    return pl.Pseudonymizer(terms, DET, registry=reg)


# ── extraction ───────────────────────────────────────────────────────────────

def test_extract_paragraphs(tmp_path):
    p = _docx(tmp_path / "a.docx", _para("Hello ", "world") + _para("Second line"))
    assert pl._extract_docx_text(p) == "Hello world\nSecond line"


def test_extract_tab_and_break(tmp_path):
    body = ("<w:p><w:r><w:t>Left</w:t><w:tab/><w:t>Right</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>One</w:t><w:br/><w:t>Two</w:t></w:r></w:p>")
    p = _docx(tmp_path / "a.docx", body)
    assert pl._extract_docx_text(p) == "Left\tRight\nOne\nTwo"


def test_extract_table_cells_become_lines(tmp_path):
    body = ("<w:tbl><w:tr>"
            "<w:tc>" + _para("Cell A") + "</w:tc>"
            "<w:tc>" + _para("Cell B") + "</w:tc>"
            "</w:tr></w:tbl>")
    p = _docx(tmp_path / "a.docx", body)
    assert pl._extract_docx_text(p) == "Cell A\nCell B"


def test_extract_bad_file_raises(tmp_path):
    bad = tmp_path / "notzip.docx"
    bad.write_text("this is not a zip", encoding="utf-8")
    with pytest.raises(Exception):
        pl._extract_docx_text(bad)


# ── folder scan ──────────────────────────────────────────────────────────────

def test_word_docs_skips_lock_and_legacy(tmp_path):
    _docx(tmp_path / "Brief.docx", _para("x"))
    _docx(tmp_path / "Reply.docm", _para("x"))
    (tmp_path / "~$Brief.docx").write_text("lock", encoding="utf-8")  # Word lock file
    (tmp_path / "Old.doc").write_text("legacy binary", encoding="utf-8")
    names = [p.name for p in pl._word_docs_in_folder(tmp_path)]
    assert names == ["Brief.docx", "Reply.docm"]


# ── conversion + pseudonymization ────────────────────────────────────────────

def test_convert_scrubs_content_and_filename(tmp_path):
    src = _docx(tmp_path / "Ramirez Declaration.docx",
                _para("Plaintiff Ernest N Ramirez sued Ford Motor Company.")
                + _para("Case No. 24STCV23198."))
    z = _pz()
    text = pl._extract_docx_text(src)
    n = pl._convert_word_docs([(src, text)], log, z, "Text Files", None)
    assert n == 1

    out = list((tmp_path / "Text Files").glob("*.txt"))
    assert len(out) == 1
    body = out[0].read_text()
    # names scrubbed in the body
    assert "Ramirez" not in body and "Ford Motor Company" not in body
    assert "24STCV23198" not in body
    # filename scrubbed too — the real party name must not survive in the name
    assert "Ramirez" not in out[0].name
    # export is tracked for the leak gate
    assert z.written == out


def test_convert_off_writes_raw_text(tmp_path):
    src = _docx(tmp_path / "Memo.docx", _para("Ernest N Ramirez"))
    text = pl._extract_docx_text(src)
    n = pl._convert_word_docs([(src, text)], log, None, "Text Files", None)
    assert n == 1
    out = tmp_path / "Text Files" / "Memo.txt"
    assert out.is_file()
    # pseudonymization off → text is verbatim, filename unchanged
    assert out.read_text().strip() == "Ernest N Ramirez"


# ── the 5-doc gate, exercised through main() (pseudonymize off → no fitz) ─────

def _run_main(folder, monkeypatch):
    monkeypatch.setattr(sys, "argv",
                        ["pdf_linker.py", str(folder), "--no-pseudonymize"])
    pl.main()


def test_gate_triggers_at_five(tmp_path, monkeypatch):
    for i in range(5):
        _docx(tmp_path / f"Filing{i}.docx", _para(f"Body {i}"))
    _run_main(tmp_path, monkeypatch)
    out = sorted(p.name for p in (tmp_path / "Text Files").glob("*.txt"))
    assert len(out) == 5


def test_gate_leaves_four_alone(tmp_path, monkeypatch):
    for i in range(4):
        _docx(tmp_path / f"Filing{i}.docx", _para(f"Body {i}"))
    _run_main(tmp_path, monkeypatch)
    assert not (tmp_path / "Text Files").exists()
