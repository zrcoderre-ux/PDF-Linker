"""
A run can be TAKEN OVER, and what it finished is not redone.

Two halves. `--takeover` ends the run holding the folder (its PID is in the
lock file, or found on the process table for a lock an older build wrote)
and takes the lock. And an already-linked PDF that an OCR pass changed is
SAVED with that change and never re-linked: the links and bookmarks are
already in the file, and re-deriving them cost two hours per evidence
compendium on every run.

Run:  cd PDF-Linker && python3 -m pytest tests/test_takeover.py -v
"""
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import fitz
import pytest

import pdf_linker as P

log = logging.getLogger("test")
_ROOT = Path(__file__).resolve().parent.parent


def _make_pdf(path):
    d = fitz.open()
    d.new_page().insert_text(
        (72, 100), "See Smith v. Jones (2017) 13 Cal.App.5th 1152.")
    d.save(str(path))
    d.close()


# ── the fast path saves an OCR change without re-linking ────────────────────

def _count_calls(monkeypatch, names):
    calls = {n: 0 for n in names}
    for n in names:
        orig = getattr(P, n)

        def wrapped(*a, _n=n, _o=orig, **k):
            calls[_n] += 1
            return _o(*a, **k)
        monkeypatch.setattr(P, n, wrapped)
    return calls


# The text export parses citations for its own appendix, so
# `find_all_citations` is not evidence of the link pass; the detection and
# bookmark passes are.
_PASSES = ("_detect_section_headings", "_link_exhibit_references",
           "_set_bookmarks", "_repair_page_annots")


def test_an_ocr_change_on_a_linked_pdf_is_saved_and_not_relinked(
        tmp_path, monkeypatch):
    pdf = tmp_path / "Brief.pdf"
    _make_pdf(pdf)
    assert P.process_pdf(pdf, log) is True             # run 1: link + stamp
    d = fitz.open(str(pdf))
    links_before = sum(len(p.get_links()) for p in d)
    assert P._pdf_is_stamped(d) and links_before >= 1
    d.close()
    m1 = pdf.stat().st_mtime

    # Run 2: an OCR pass reports a change (a layer repair, a page mark).
    monkeypatch.setattr(P, "_ocr_image_regions", lambda doc, log: True)
    calls = _count_calls(monkeypatch, _PASSES)
    time.sleep(0.05)
    assert P.process_pdf(pdf, log) is True
    assert pdf.stat().st_mtime != m1                   # the change was SAVED
    assert all(v == 0 for v in calls.values()), calls  # nothing re-derived
    d = fitz.open(str(pdf))
    assert P._pdf_is_stamped(d)                        # still stamped
    assert sum(len(p.get_links()) for p in d) == links_before
    d.close()
    assert (tmp_path / "Text Files" / "Brief.txt").exists()

    # --relink still forces the full pass.
    calls = _count_calls(monkeypatch, _PASSES)
    assert P.process_pdf(pdf, log, relink=True) is True
    assert calls["_set_bookmarks"] == 1 and calls["_repair_page_annots"] == 1


def test_the_save_tail_is_shared_by_both_paths():
    """One save function for the full pass and the OCR-only save, so the two
    cannot write a PDF differently."""
    import inspect
    src = inspect.getsource(P.process_pdf)
    assert src.count("_save_linked_pdf(") == 2
    assert "doc.save(" not in src


# ── the lock names its holder, and a takeover ends it ───────────────────────

def _hold_lock_in_child(folder):
    """A child process that takes `folder`'s lock and sleeps, like a run."""
    code = (f"import sys, pathlib, time, logging; sys.path.insert(0, {str(_ROOT)!r}); "
            f"import pdf_linker as pl; "
            f"ok = pl._acquire_folder_lock(pathlib.Path({str(folder)!r}), "
            f"logging.getLogger('x')); print('LOCKED', ok, flush=True); "
            f"time.sleep(120)")
    proc = subprocess.Popen([sys.executable, "-c", code],
                            stdout=subprocess.PIPE, text=True)
    line = proc.stdout.readline()
    assert line.startswith("LOCKED True"), line
    return proc


def _release_ours(folder):
    P._release_folder_lock(P._folder_lock_file(folder))


def test_the_lock_file_names_the_run_holding_it(tmp_path):
    assert P._acquire_folder_lock(tmp_path, log) is True
    try:
        assert P._lock_holder_pid(P._folder_lock_file(tmp_path)) == os.getpid()
    finally:
        _release_ours(tmp_path)
    # An older build's empty lock file names nobody.
    empty = tmp_path / "old.lock"
    empty.write_bytes(b"")
    assert P._lock_holder_pid(empty) is None
    assert P._lock_holder_pid(tmp_path / "missing.lock") is None


def test_a_takeover_ends_the_holder_and_takes_the_lock(tmp_path):
    proc = _hold_lock_in_child(tmp_path)
    try:
        assert P._acquire_folder_lock(tmp_path, log) is False   # held
        assert P._lock_holder_pid(P._folder_lock_file(tmp_path)) == proc.pid
        assert P._take_over_folder(tmp_path, log) is True
        assert proc.poll() is not None                          # it is gone
        # …and this process now holds the folder: a child is refused.
        child = subprocess.run(
            [sys.executable, "-c",
             f"import sys, pathlib, logging; sys.path.insert(0, {str(_ROOT)!r}); "
             f"import pdf_linker as pl; print('GOT', pl._acquire_folder_lock("
             f"pathlib.Path({str(tmp_path)!r}), logging.getLogger('x')))"],
            capture_output=True, text=True, timeout=120)
        assert "GOT False" in child.stdout, (child.stdout, child.stderr)
    finally:
        if proc.poll() is None:
            proc.kill()
        _release_ours(tmp_path)


@pytest.mark.skipif(os.name == "nt", reason="ps-based; the Windows arm "
                    "reads Get-CimInstance and is exercised by hand")
def test_a_run_with_no_pid_in_its_lock_is_found_by_its_command_line(tmp_path):
    """An older build's lock carries no PID, so the run is found on the
    process table by the tool's name and the folder's path — and this
    process, whose command line names both, is never its own target."""
    folder = tmp_path / "23STCV00001 Case"
    folder.mkdir()
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(120)",
         "pdf_linker.py", str(folder)])
    try:
        time.sleep(0.3)
        found = P._runs_of_folder(folder)
        assert proc.pid in found, found
        assert os.getpid() not in found
        # A process naming the folder but not the tool is not a run of it.
        other = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(120)", str(folder)])
        try:
            time.sleep(0.3)
            assert other.pid not in P._runs_of_folder(folder)
        finally:
            other.kill()
    finally:
        proc.kill()


def test_a_takeover_with_nothing_to_end_says_so_and_declines(tmp_path):
    assert P._take_over_folder(tmp_path, log) is False


# ── the launchers ask for it ────────────────────────────────────────────────

def test_both_launchers_pass_takeover():
    for windows in (True, False):
        for deferred in (True, False):
            name, content, _ = P._rerun_launcher_spec(
                "python", "pdf_linker.py", "lexis", True, windows,
                deferred=deferred) if "deferred" in \
                P._rerun_launcher_spec.__code__.co_varnames else \
                P._rerun_launcher_spec("python", "pdf_linker.py", "lexis",
                                       True, windows)
            assert "--takeover" in content and "--no-defer" in content
