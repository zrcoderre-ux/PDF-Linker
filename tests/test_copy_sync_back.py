"""
The copy can be the folder that is AHEAD.

The destination syncs between machines, so a case deferred here and processed
THERE comes back to a source folder that has never been run. Re-running it is
the expensive way to obtain files that already exist a folder away, so the
start of every run asks whether the copy finished a run this folder has not —
the folders' own DONE/ETA markers are the evidence — and brings it back if so.

Nothing is ever deleted, and a file is taken only when this folder has no
version or an older one: a worksheet the operator typed Fix? decisions into
here is irreplaceable, and the copy's version has none of them.

Run:  cd PDF-Linker && python3 -m pytest tests/test_copy_sync_back.py -v
"""
import importlib.util
import logging
import os
import sys
import time
import zipfile
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pdf_linker", _ROOT / "pdf_linker.py")
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)

log = logging.getLogger("test")
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_HOUR = 3600.0


def _docx(path, text):
    body = f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'
    doc = (f'<?xml version="1.0" encoding="UTF-8"?>'
           f'<w:document xmlns:w="{_W}"><w:body>{body}</w:body></w:document>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", doc)
    return path


def _stamp(path, when):
    os.utime(path, (when, when))
    return path


def _marker(folder, name, when):
    """A run marker as the tool writes one: zero bytes, stamped."""
    p = folder / name
    p.write_text("", encoding="utf-8")
    return _stamp(p, when)


# ── is the copy ahead? ───────────────────────────────────────────────────────

def _pair(tmp_path):
    src = tmp_path / "src" / "Smith v Jones"
    dest = tmp_path / "dest" / "Smith v Jones"
    src.mkdir(parents=True)
    dest.mkdir(parents=True)
    return src, dest


def test_a_copy_that_finished_a_run_this_folder_never_did_is_ahead(tmp_path):
    src, dest = _pair(tmp_path)
    _marker(dest, "DONE 9.15AM.txt", time.time())
    ahead, why = pl._copy_is_ahead(src, dest)
    assert ahead and "never finished" in why


def test_an_untouched_copy_is_not_ahead(tmp_path):
    src, dest = _pair(tmp_path)
    ahead, why = pl._copy_is_ahead(src, dest)
    assert not ahead and "never finished a run" in why


def test_a_copy_mid_run_is_never_taken(tmp_path):
    # An ETA marker written after the DONE stamp means a run started there and
    # has not finished — it is either going now or it died part-way.
    src, dest = _pair(tmp_path)
    now = time.time()
    _marker(dest, "DONE 9.15AM.txt", now - 600)
    _marker(dest, "ETA ~10.30AM (3 of 9).txt", now)
    ahead, why = pl._copy_is_ahead(src, dest)
    assert not ahead and "in progress" in why


def test_our_own_newer_run_wins(tmp_path):
    src, dest = _pair(tmp_path)
    now = time.time()
    _marker(dest, "DONE 9.15AM.txt", now - _HOUR)
    _marker(src, "DONE 10.15AM.txt", now)
    ahead, why = pl._copy_is_ahead(src, dest)
    assert not ahead and "this folder's own run" in why


def test_the_copy_we_pushed_ourselves_is_not_ahead(tmp_path):
    # shutil.copy2 preserves mtimes, so a copy this folder pushed carries this
    # machine's own stamp and reads as exactly equal — never as ahead, or every
    # run would pull back what it had just written.
    src, dest = _pair(tmp_path)
    now = time.time()
    _marker(src, "DONE 9.15AM.txt", now)
    _marker(dest, "DONE 9.15AM.txt", now)
    assert pl._copy_is_ahead(src, dest)[0] is False


def test_a_marker_shaped_file_with_content_is_not_a_run_stamp(tmp_path):
    # Same scoping `_clear_eta_markers` uses: the stamps are zero-byte.
    src, dest = _pair(tmp_path)
    (dest / "DONE reading the exhibits.txt").write_text("notes to self")
    _stamp(dest / "DONE reading the exhibits.txt", time.time())
    assert pl._copy_is_ahead(src, dest)[0] is False


# ── bringing it back ─────────────────────────────────────────────────────────

def test_the_copys_work_comes_back(tmp_path):
    src, dest = _pair(tmp_path)
    (dest / "Text Files").mkdir()
    (dest / "Text Files" / "Motion.txt").write_text("scrubbed body")
    (dest / "pseudonym_key.xlsx").write_bytes(b"PK stub")
    _marker(dest, "DONE 9.15AM.txt", time.time())
    pl._pull_back_from_copy(src, dest, log)
    assert (src / "Text Files" / "Motion.txt").read_text() == "scrubbed body"
    assert (src / "pseudonym_key.xlsx").exists()
    assert list(src.glob("DONE *.txt"))


def test_a_newer_file_here_is_never_overwritten(tmp_path):
    # The operator's own Fix? decisions, typed on this machine, are exactly the
    # thing that must survive a sync-back.
    src, dest = _pair(tmp_path)
    now = time.time()
    (dest / "LEAKS.xlsx").write_text("from the other machine")
    _stamp(dest / "LEAKS.xlsx", now - _HOUR)
    (src / "LEAKS.xlsx").write_text("my triage decisions")
    _stamp(src / "LEAKS.xlsx", now)
    pl._pull_back_from_copy(src, dest, log)
    assert (src / "LEAKS.xlsx").read_text() == "my triage decisions"


def test_nothing_here_is_deleted(tmp_path):
    # A document that exists only on this machine survives, and the run that
    # follows the sync-back is what processes it.
    src, dest = _pair(tmp_path)
    _docx(src / "Late Filing.docx", "Body")
    _marker(dest, "DONE 9.15AM.txt", time.time())
    pl._pull_back_from_copy(src, dest, log)
    assert (src / "Late Filing.docx").exists()


def test_the_stale_local_stamp_goes(tmp_path):
    # Two run stamps in one folder say two different things about one run.
    src, dest = _pair(tmp_path)
    now = time.time()
    _marker(src, "DONE 8.00AM.txt", now - _HOUR)
    _marker(dest, "DONE 9.15AM.txt", now)
    pl._pull_back_from_copy(src, dest, log)
    assert [p.name for p in src.glob("DONE *.txt")] == ["DONE 9.15AM.txt"]


# ── the two-machine sequence, end to end ─────────────────────────────────────

def _config(tmp_path, monkeypatch, text):
    path = tmp_path / "pdf_linker.config"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(pl, "_config_path", lambda: path)
    return path


def _run_main(folder, monkeypatch, *extra):
    monkeypatch.setattr(sys, "argv",
                        ["pdf_linker.py", str(folder), "--no-pseudonymize",
                         *extra])
    try:
        pl.main()
    except SystemExit as e:
        return e.code
    return 0


def test_deferred_here_run_there_comes_home(tmp_path, monkeypatch):
    """Machine 1 defers; machine 2 runs the copy; machine 1 wants the files."""
    onedrive = tmp_path / "OneDrive" / "Cases"
    _config(tmp_path, monkeypatch, f"defer_run = on\ncopy_to = {onedrive}\n")
    folder = tmp_path / "src" / "Smith v Jones"
    folder.mkdir(parents=True)
    _docx(folder / "Filing.docx", "Body")

    _run_main(folder, monkeypatch)                       # machine 1: defer
    copy = onedrive / folder.name
    assert not (folder / "Text Files").exists()

    _run_main(copy, monkeypatch, "--no-defer")           # machine 2: full run
    assert list((copy / "Text Files").glob("*.txt"))
    # Machine 2's run finished later than anything here; make that unambiguous
    # against the margin the clock tolerance costs.
    for m in copy.glob("DONE *.txt"):
        _stamp(m, time.time() + 600)

    _run_main(folder, monkeypatch)                       # machine 1: again
    # The exports are HERE now, and this folder was never processed to get them.
    assert list((folder / "Text Files").glob("*.txt"))
    assert list(folder.glob("DONE *.txt"))


def test_a_full_run_after_the_sync_back_reuses_the_key_that_came_with_it(
        tmp_path, monkeypatch):
    onedrive = tmp_path / "OneDrive" / "Cases"
    _config(tmp_path, monkeypatch, f"copy_to = {onedrive}\n")
    folder = tmp_path / "src" / "Smith v Jones"
    folder.mkdir(parents=True)
    copy = onedrive / folder.name
    (copy / "Text Files").mkdir(parents=True)
    _docx(folder / "Filing.docx", "Body")
    _docx(copy / "Filing.docx", "Body")
    (copy / "Text Files" / "Filing.txt").write_text("from the other machine")
    _marker(copy, "DONE 9.15AM.txt", time.time() + 600)

    _run_main(folder, monkeypatch)
    # The run proceeded here (it re-exported), on top of the files it took.
    assert (folder / "Text Files" / "Filing.txt").exists()
    # ...and pushed the result back, so the two folders agree again.
    assert (copy / "Text Files" / "Filing.txt").read_text() != \
        "from the other machine"


def test_nothing_is_taken_when_this_folder_is_the_current_one(tmp_path,
                                                              monkeypatch):
    onedrive = tmp_path / "OneDrive" / "Cases"
    _config(tmp_path, monkeypatch, f"copy_to = {onedrive}\n")
    folder = tmp_path / "src" / "Smith v Jones"
    folder.mkdir(parents=True)
    _docx(folder / "Filing.docx", "Body")
    _run_main(folder, monkeypatch)                 # run, and push the copy
    exports = sorted(p.name for p in (folder / "Text Files").iterdir())
    _run_main(folder, monkeypatch)                 # again: nothing to take back
    assert sorted(p.name for p in (folder / "Text Files").iterdir()) == exports
    assert not (folder / folder.name).exists()


def test_a_synced_back_folder_is_not_pushed_straight_out_again(tmp_path,
                                                               monkeypatch):
    # We took those files a moment ago and processed nothing since: pushing
    # them back would copy a whole case over itself for no change.
    onedrive = tmp_path / "OneDrive" / "Cases"
    _config(tmp_path, monkeypatch, f"defer_run = on\ncopy_to = {onedrive}\n")
    folder = tmp_path / "src" / "Smith v Jones"
    folder.mkdir(parents=True)
    copy = onedrive / folder.name
    copy.mkdir(parents=True)
    _docx(folder / "Filing.docx", "Body")
    _docx(copy / "Filing.docx", "Body")
    (copy / "Text Files").mkdir()
    (copy / "Text Files" / "Filing.txt").write_text("from the other machine")
    _marker(copy, "DONE 9.15AM.txt", time.time() + 600)
    pushed = []
    real = pl._copy_folder_out
    monkeypatch.setattr(pl, "_copy_folder_out",
                        lambda *a, **k: pushed.append(a) or real(*a, **k))
    _run_main(folder, monkeypatch)
    assert pushed == []
    # ...and the files still came home.
    assert (folder / "Text Files" / "Filing.txt").exists()
