"""A page whose /Annots cannot be appended to kills the whole run.

`/Annots 175 0 R` is legal PDF — "my annotations are over there". Word's
e-filing export writes exactly that and then emits `175 0 obj null` for a page
that ended up with none. Reading tolerates it, so the document looks fine right
up to the moment a citation link is inserted: appending resolves the reference,
gets a null, and MuPDF raises "not an array (null)" from OUTSIDE a fz_try, so
its default handler calls abort(). No Python exception is raised and nothing can
catch it — the run stops mid-file with the log ending after "Found N citations",
and on Windows leaves a python process sitting at 0% CPU.

Because the failure kills the interpreter, the end-to-end check has to run in a
subprocess: an assertion could not survive it.

Run:  cd PDF-Linker && python3 -m pytest tests/test_annots_repair.py -v
"""
import importlib.util
import logging
import subprocess
import sys
import textwrap
from pathlib import Path

import fitz
import pytest

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pdf_linker", _ROOT / "pdf_linker.py")
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)

log = logging.getLogger("test")


def _page_with(shape):
    """A one-page doc whose /Annots takes `shape`. Returns (doc, page)."""
    doc = fitz.open()
    page = doc.new_page()
    if shape == "absent":
        pass
    elif shape == "direct-null":
        doc.xref_set_key(page.xref, "Annots", "null")
    elif shape == "direct-array":
        doc.xref_set_key(page.xref, "Annots", "[]")
    elif shape == "indirect-array":
        x = doc.get_new_xref()
        doc.update_object(x, "[ ]")
        doc.xref_set_key(page.xref, "Annots", f"{x} 0 R")
    elif shape == "indirect-null":
        x = doc.get_new_xref()
        doc.update_object(x, "null")
        doc.xref_set_key(page.xref, "Annots", f"{x} 0 R")
    elif shape == "indirect-dict":
        x = doc.get_new_xref()
        doc.update_object(x, "<< /Type /Bogus >>")
        doc.xref_set_key(page.xref, "Annots", f"{x} 0 R")
    elif shape == "indirect-missing":
        # the reference points at an object that is not in the xref at all
        doc.xref_set_key(page.xref, "Annots", "9999 0 R")
    else:                                          # pragma: no cover
        raise AssertionError(shape)
    return doc, page


# The three shapes MuPDF already appends to happily, and the three it aborts on.
_SAFE = ["absent", "direct-null", "direct-array", "indirect-array"]
_FATAL = ["indirect-null", "indirect-dict", "indirect-missing"]


@pytest.mark.parametrize("shape", _FATAL)
def test_an_unappendable_annots_is_repaired(shape):
    doc, page = _page_with(shape)
    assert pl._repair_page_annots(doc, log) == 1
    assert doc.xref_get_key(page.xref, "Annots")[0] == "array"


@pytest.mark.parametrize("shape", _SAFE)
def test_a_usable_annots_is_left_alone(shape):
    # The repair must not touch a page MuPDF already handles — in particular an
    # indirect reference to a REAL array, which is both legal and common.
    doc, page = _page_with(shape)
    before = doc.xref_get_key(page.xref, "Annots")
    assert pl._repair_page_annots(doc, log) == 0
    assert doc.xref_get_key(page.xref, "Annots") == before


def test_existing_annotations_survive_the_pass(tmp_path):
    # An annotation already on the page keeps it: the repair replaces only what
    # resolves to nothing. Round-tripped through a save, because a freshly
    # inserted link is invisible to get_links() until the doc is written.
    doc = fitz.open()
    doc.new_page().insert_link(
        {"kind": fitz.LINK_URI, "from": fitz.Rect(10, 10, 100, 20),
         "uri": "https://example.com/first"})
    out = tmp_path / "one.pdf"
    doc.save(str(out))
    doc = fitz.open(str(out))
    assert pl._repair_page_annots(doc, log) == 0
    assert [ln["uri"] for ln in doc[0].get_links()] == ["https://example.com/first"]


def test_only_the_broken_pages_are_repaired():
    # Page handles go stale as pages are added, so everything is addressed by
    # index after the document is built.
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    doc.xref_set_key(doc[0].xref, "Annots", "[]")
    x = doc.get_new_xref()
    doc.update_object(x, "null")
    doc.xref_set_key(doc[1].xref, "Annots", f"{x} 0 R")
    assert pl._repair_page_annots(doc, log) == 1
    assert doc.xref_get_key(doc[0].xref, "Annots") == ("array", "[]")


# ── the property the whole thing exists for ─────────────────────────────────
# Asserting it in-process is not possible: if the repair regressed, MuPDF would
# abort the test runner rather than fail a test.

_CHILD = """
import sys, importlib.util, fitz
spec = importlib.util.spec_from_file_location("pdf_linker", {mod!r})
pl = importlib.util.module_from_spec(spec); spec.loader.exec_module(pl)
doc = fitz.open(); page = doc.new_page()
x = doc.get_new_xref(); doc.update_object(x, {target!r})
doc.xref_set_key(page.xref, "Annots", f"{{x}} 0 R")
{repair}
page.insert_link({{"kind": fitz.LINK_URI, "from": fitz.Rect(10, 10, 100, 20),
                  "uri": "https://example.com"}})
out = sys.argv[1]
doc.save(out)                 # a fresh link is invisible until the doc is written
print("SURVIVED", len(fitz.open(out)[0].get_links()))
"""


def _run_child(target, repair, tmp_path):
    src = _CHILD.format(mod=str(_ROOT / "pdf_linker.py"), target=target,
                        repair=repair)
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(src), str(tmp_path / "out.pdf")],
        capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("target", ["null", "<< /Type /Bogus >>"])
def test_inserting_a_link_no_longer_aborts_the_process(target, tmp_path):
    done = _run_child(target, "pl._repair_page_annots(doc)", tmp_path)
    assert "SURVIVED 1" in done.stdout, (done.stdout, done.stderr)
    assert "aborting process" not in done.stderr


def test_without_the_repair_it_really_does_abort(tmp_path):
    # Pins the failure this guards against: same page, repair removed. If MuPDF
    # ever stops aborting here the guard is still correct, so this only asserts
    # that the unrepaired page does not quietly succeed.
    done = _run_child("null", "pass", tmp_path)
    assert "SURVIVED" not in done.stdout, (done.stdout, done.stderr)
