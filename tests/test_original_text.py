"""
Two-folder output: when keep_original_text is on, the tool writes the scrubbed
text to the shareable folder AND the unscrubbed text to a clearly-flagged
sibling folder (for QA / reference). The original copy carries real names by
design, so it is never tracked for the leak gate and never quarantined.

Run:  cd PDF-Linker && python3 -m pytest tests/test_original_text.py -v
"""
import importlib.util
from pathlib import Path

import fitz
import pytest

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pdf_linker", _ROOT / "pdf_linker.py")
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)

log = __import__("logging").getLogger("test")
DET = {k: pl._PN_DETECTORS[k] for k in pl._PN_DEFAULT_DETECTORS}


def _doc():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "Plaintiff Ernest N Ramirez sued Ford Motor "
                                "Company.", fontsize=11)
    page.insert_text((72, 130), "See Donlen v. Ford Motor Co., 217 "
                                "Cal.App.4th 138 (2013).", fontsize=11)
    return doc


def _pz():
    reg = pl._PnFakeRegistry()
    terms = pl._pn_build_terms(["Ernest N Ramirez", "Ford Motor Company"],
                               ["24STCV23198"], [], registry=reg)
    return pl.Pseudonymizer(terms, DET, registry=reg)


def test_two_folders_written_scrubbed_and_original(tmp_path):
    pdf = tmp_path / "Motion.pdf"
    _doc().save(pdf)
    z = _pz()
    with fitz.open(pdf) as doc:
        pl._write_text_version(pdf, doc, log, z, "Text Files",
                               "Original Text (real names - do not share)")

    shareable = tmp_path / "Text Files"
    original = tmp_path / "Original Text (real names - do not share)"
    stxt = list(shareable.glob("*.txt"))
    otxt = list(original.glob("*.txt"))
    assert stxt and otxt, "both folders should hold a .txt"

    scrubbed = stxt[0].read_text()
    orig = otxt[0].read_text()
    # shareable: party names gone, cited authority preserved
    assert "Ramirez" not in scrubbed and "Ford Motor Company" not in scrubbed
    assert "Donlen v. Ford Motor Co., 217 Cal.App.4th 138" in scrubbed
    # original: real names present, under the REAL filename
    assert otxt[0].name == "Motion.txt"
    assert "Ernest N Ramirez" in orig and "Ford Motor Company" in orig

    # the original copy is NOT tracked for the leak gate
    assert all(p.parent.name == "Text Files" for p in z.written)


def test_the_original_is_written_before_the_export(tmp_path):
    """The unscrubbed copy lands FIRST, because nothing about it has to wait.

    `build_body(None)` is pure string assembly over pages already extracted, so
    it depends on the extraction and on nothing else — while the scrub and the
    leak scans that used to run ahead of it depend on every term and record in
    the case. Measured on a 130-page filing that is 1 second of work sitting
    behind 90, and on the folder that prompted this (before the quadratic in
    `_in_name_run` was found) 5 seconds sitting behind 65 MINUTES. The reference
    copy is what an operator reads while the export is still being checked, so
    the wait was pure cost.

    Asserted on the LOG ORDER rather than on file mtimes: a fast machine writes
    both inside one filesystem timestamp tick, so mtimes cannot tell them apart.
    """
    pdf = tmp_path / "Motion.pdf"
    _doc().save(pdf)
    seen = []

    class _Recorder:
        def info(self, msg, *a, **k):
            seen.append(str(msg))
        warning = error = critical = debug = info

    with fitz.open(pdf) as doc:
        pl._write_text_version(pdf, doc, _Recorder(), _pz(), "Text Files",
                               "Original Text (real names - do not share)")

    def first(fragment):
        return next(i for i, m in enumerate(seen) if fragment in m)

    i_orig = first("Wrote original text version")
    i_export = first("Wrote pseudonymized text version")
    assert i_orig < i_export, seen
    # ...and ahead of the two long phases, not merely ahead of the write.
    assert i_orig < first("scrubbing"), seen
    assert i_orig < first("running the leak scans"), seen


def test_the_evidence_pass_still_has_the_original(tmp_path):
    # Moving the build earlier must not cost `confirm_findings` its evidence:
    # `note_original` has to have run by the time the file is done, whichever
    # side of the scrub it happens on.
    pdf = tmp_path / "Motion.pdf"
    _doc().save(pdf)
    z = _pz()
    with fitz.open(pdf) as doc:
        pl._write_text_version(pdf, doc, log, z, "Text Files", None)
    # The original is recorded even with NO reference folder requested — the
    # check must never depend on an output preference.
    assert z._orig_words, "the unscrubbed body was never noted as evidence"
    assert "ramirez" in {w.lower() for w in z._orig_words}


def test_no_original_folder_when_disabled(tmp_path):
    pdf = tmp_path / "Motion.pdf"
    _doc().save(pdf)
    z = _pz()
    with fitz.open(pdf) as doc:
        pl._write_text_version(pdf, doc, log, z, "Text Files", None)
    assert (tmp_path / "Text Files").is_dir()
    # no sibling original folder created
    assert [d for d in tmp_path.iterdir() if d.is_dir()] == [tmp_path / "Text Files"]
