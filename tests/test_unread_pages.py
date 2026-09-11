"""A page nothing could READ says so — in the export, in the log, and by name.

The failure this pins: a 119-page declaration was delivered with 113 pages of
exhibits blank. The pages had no text layer, OCR could not run because
pytesseract/Pillow were not installed for the interpreter the launcher uses,
and the whole of what the run said about it was two lines at line 66 of a
535-line log ("pytesseract or Pillow not installed - skipping OCR"). The
export gave no sign at all: 113 `====== Page N ======` headers with nothing
under them, which reads exactly like a document that has blank pages. The run
then stamped the folder DONE.

This is the inverse of the low-dpi, rebuilt-layer and ink-form banners. Those
exist because an inferred reading must never be presented as equal to a read
one; here there is no reading at all, and an empty page is the most
convincing-looking output there is.

Run:  cd PDF-Linker && python3 -m pytest tests/test_unread_pages.py -v
"""
import builtins
import logging
import sys
from pathlib import Path

import fitz
import pytest

import pdf_linker as P


class _Log:
    def __init__(self):
        self.info_lines = []
        self.warn_lines = []

    def info(self, m):
        self.info_lines.append(str(m))

    def warning(self, m):
        self.warn_lines.append(str(m))

    error = warning

    @property
    def text(self):
        return "\n".join(self.info_lines + self.warn_lines)


@pytest.fixture(autouse=True)
def _clean_tally():
    P._UNREAD_RUN.clear()
    yield
    P._UNREAD_RUN.clear()


def _textless_doc(pages=3):
    """A document whose pages carry no text at all — a scanned exhibit set."""
    d = fitz.open()
    for _ in range(pages):
        d.new_page(width=612, height=792)
    return d


def _textless_file(tmp_path, name, pages):
    """The same, saved and reopened, so the doc carries a real file NAME —
    which is what the end-of-run tally reports each miss under."""
    d = _textless_doc(pages)
    path = tmp_path / name
    d.save(path)
    d.close()
    return fitz.open(path)


def _no_pytesseract(monkeypatch):
    real = builtins.__import__

    def fake(name, *a, **k):
        if name in ("pytesseract", "PIL", "PIL.Image"):
            raise ImportError("No module named 'pytesseract'")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)
    monkeypatch.delitem(sys.modules, "pytesseract", raising=False)


class TestTheDeclineIsRecorded:
    def test_a_missing_dependency_marks_every_textless_page(self, monkeypatch):
        _no_pytesseract(monkeypatch)
        d = _textless_doc(3)
        assert P._ocr_pdf(d, _Log()) is False
        marked = getattr(d, P._UNREAD_ATTR, {})
        assert set(marked) == {0, 1, 2}
        assert "pytesseract" in marked[0]
        d.close()

    def test_the_warning_names_the_cost_in_pages(self, monkeypatch):
        _no_pytesseract(monkeypatch)
        d = _textless_doc(3)
        log = _Log()
        P._ocr_pdf(d, log)
        joined = "\n".join(log.warn_lines)
        assert "3 page(s)" in joined
        assert "CANNOT BE READ" in joined
        # The pages, as the operator counts them (1-based).
        assert "1, 2, 3" in joined
        d.close()

    def test_the_warning_names_THIS_interpreter_and_the_pip_line(
            self, monkeypatch):
        """A bare `pip install` at whichever Python is on PATH is exactly how a
        folder comes to work on one machine and not another."""
        _no_pytesseract(monkeypatch)
        d = _textless_doc(1)
        log = _Log()
        P._ocr_pdf(d, log)
        joined = "\n".join(log.warn_lines)
        assert "-m pip install pytesseract pillow" in joined
        assert str(P._console_python()) in joined
        # Tesseract is a separate program and the operator needs both.
        assert "tesseract" in joined.lower()
        d.close()

    def test_a_missing_tesseract_marks_the_pages_too(self, monkeypatch):
        """Every route out of `_ocr_pdf` without a text layer costs the same
        pages, so every route reports."""
        monkeypatch.setattr(P, "_find_tesseract", lambda: None)
        d = _textless_doc(2)
        log = _Log()
        assert P._ocr_pdf(d, log) is False
        marked = getattr(d, P._UNREAD_ATTR, {})
        assert set(marked) == {0, 1}
        assert "Tesseract" in "\n".join(log.warn_lines)
        d.close()

    def test_a_tesseract_that_will_not_start_marks_the_pages(self, monkeypatch):
        monkeypatch.setattr(P, "_find_tesseract", lambda: "/usr/bin/tesseract")
        monkeypatch.setattr(P, "_tesseract_usable", lambda t, log: False)
        d = _textless_doc(2)
        assert P._ocr_pdf(d, _Log()) is False
        assert set(getattr(d, P._UNREAD_ATTR, {})) == {0, 1}
        d.close()

    def test_a_document_with_nothing_to_read_says_nothing(self, monkeypatch):
        """No textless page is not a miss. The old code warned about the
        missing dependency whether or not it had cost anything."""
        _no_pytesseract(monkeypatch)
        d = fitz.open()
        d.new_page(width=612, height=792).insert_text((72, 100), "REAL TEXT")
        log = _Log()
        assert P._ocr_pdf(d, log) is False
        assert getattr(d, P._UNREAD_ATTR, {}) == {}
        assert log.warn_lines == []
        assert P._UNREAD_RUN == []
        d.close()

    def test_instrumentation_never_takes_a_run_down(self):
        class _Hostile:
            name = "x.pdf"

            def __setattr__(self, k, v):
                raise RuntimeError("no attributes here")

        P._note_unread_pages(_Hostile(), [0, 1], "why")      # must not raise


class TestTheExportSaysSo:
    """The log is a separate file that does not travel with the export."""

    def _export(self, tmp_path, monkeypatch, pages=3):
        _no_pytesseract(monkeypatch)
        d = _textless_doc(pages)
        # Page 1 carries text so the document has a body to export; the rest
        # are the scanned exhibits behind it, which is the real shape.
        d[0].insert_text((72, 100), "DECLARATION OF RUTLEDGE ONDINE")
        path = tmp_path / "Clark Decl..pdf"
        d.save(path)
        d.close()
        doc = fitz.open(path)
        P._ocr_pdf(doc, _Log())
        assert P._write_text_version(path, doc, logging.getLogger("t"))
        doc.close()
        return (tmp_path / "Text Files" / "Clark Decl..txt").read_text("utf-8")

    def test_an_unread_page_is_banner_marked(self, tmp_path, monkeypatch):
        txt = self._export(tmp_path, monkeypatch)
        heads = [l for l in txt.splitlines() if l.startswith("====== Page")]
        assert "NOT READ" in heads[1] and "NOT READ" in heads[2]
        assert "no text layer" in heads[1]
        assert "pytesseract/Pillow not installed" in heads[1]
        # The banner is repeated on every unread page — 113 of them on the
        # filing that produced this — so the reason there is a PHRASE and the
        # log carries the sentence and the fix line.
        assert len(heads[1]) < 140

    def test_the_page_that_WAS_read_carries_no_banner(self, tmp_path,
                                                      monkeypatch):
        txt = self._export(tmp_path, monkeypatch)
        head = next(l for l in txt.splitlines() if l.startswith("====== Page 1"))
        assert "NOT READ" not in head

    def test_the_banner_still_parses_as_a_page_header(self, tmp_path,
                                                      monkeypatch):
        """A header that does not match `_PN_PAGE_HEADER_RE` does not merely
        lose its own page: the parser keeps the LAST page it did match, so
        every line after it is located at that page's number."""
        txt = self._export(tmp_path, monkeypatch)
        nums = [P._PN_PAGE_HEADER_RE.match(l).group(1)
                for l in txt.splitlines() if l.startswith("====== Page")]
        assert nums == ["1", "2", "3"]


class TestTheRunSaysSoOnce:
    def test_the_tally_groups_by_cause(self, tmp_path, monkeypatch):
        _no_pytesseract(monkeypatch)
        for name, n in (("Clark Decl..pdf", 113), ("Petition.pdf", 66)):
            d = _textless_file(tmp_path, name, n)
            P._ocr_pdf(d, _Log())
            d.close()
        assert [r[0] for r in P._UNREAD_RUN] == ["Clark Decl..pdf",
                                                 "Petition.pdf"]
        assert sum(r[1] for r in P._UNREAD_RUN) == 179
        assert len({r[2] for r in P._UNREAD_RUN}) == 1     # one machine, one cause


def test_the_interpreter_named_is_a_console_build(monkeypatch, tmp_path):
    """pip run under pythonw.exe prints nothing, so the line an operator copies
    has to name python.exe beside it — the same answer `_require_pymupdf` gives,
    through the same function, or the two would drift."""
    (tmp_path / "python.exe").write_text("")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "pythonw.exe"))
    assert P._console_python().name == "python.exe"


def test_a_plain_interpreter_is_named_as_it_stands(monkeypatch):
    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
    assert P._console_python() == Path("/usr/bin/python3")


class TestTheLogSaysWhichMachineRanIt:
    """A log records the folder and nothing about where it came from, so a log
    read on one computer says nothing about the computer that produced it — and
    a case folder routinely moves between two."""

    def test_the_machine_is_named(self):
        import platform
        assert P._machine_name() == (platform.node() or "?")

    def test_a_host_with_no_name_is_not_a_failed_run(self, monkeypatch):
        import platform
        monkeypatch.setattr(platform, "node", lambda: "")
        assert P._machine_name() == "?"

    def test_a_host_that_raises_is_not_a_failed_run(self, monkeypatch):
        import platform

        def boom():
            raise OSError("no host")

        monkeypatch.setattr(platform, "node", boom)
        assert P._machine_name() == "?"
