"""
`copy_to`: the case folder — the folder itself and everything in it — is copied
into a destination folder, as <destination>/<folder name>.

WHEN it is copied follows `defer_run`, and the pairing is what keeps the case
from being processed twice on one machine:
  deferred  the copy is made FIRST and the one-click launcher (plus the party
            spreadsheet the run there will need) goes into the COPY, so the
            work happens at the destination and the source is left untouched;
  otherwise the copy is made LAST, and is HELD BACK while an export is
            quarantined so the destination never receives a *.LEAK —
            `--fix-leaks` makes it once the last leak is released.

Run:  cd PDF-Linker && python3 -m pytest tests/test_copy_to.py -v
"""
import importlib.util
import logging
import sys
import types
import zipfile
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pdf_linker", _ROOT / "pdf_linker.py")
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)

log = logging.getLogger("test")
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _docx(path, text):
    body = f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'
    doc = (f'<?xml version="1.0" encoding="UTF-8"?>'
           f'<w:document xmlns:w="{_W}"><w:body>{body}</w:body></w:document>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", doc)
    return path


def _args(**kw):
    """A stand-in for the parsed CLI namespace, with the defaults main() has."""
    ns = types.SimpleNamespace(copy_to=None, no_copy=False, key=None,
                               pseudonymize=True)
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


def _case(tmp_path, name="Smith v Jones"):
    folder = tmp_path / "src" / name
    (folder / "Text Files").mkdir(parents=True)
    (folder / "Motion.pdf").write_bytes(b"%PDF-1.4 stub")
    (folder / "Text Files" / "Motion.txt").write_text("scrubbed body")
    return folder


# ── resolving the destination ────────────────────────────────────────────────

def test_off_by_default():
    assert pl._copy_dest_root({}, _args(), log) is None
    assert pl._copy_dest_root({"copy_to": "   "}, _args(), log) is None


def test_config_value_is_used_and_expanded(tmp_path, monkeypatch):
    monkeypatch.setenv("CASEROOT", str(tmp_path))
    got = pl._copy_dest_root({"copy_to": '"$CASEROOT/Cases"'}, _args(), log)
    assert got == tmp_path / "Cases"        # quotes stripped, env expanded


def test_command_line_overrides_the_config(tmp_path):
    got = pl._copy_dest_root({"copy_to": "/from/config"},
                             _args(copy_to=str(tmp_path)), log)
    assert got == tmp_path


def test_no_copy_beats_everything(tmp_path):
    assert pl._copy_dest_root({"copy_to": str(tmp_path)},
                              _args(no_copy=True), log) is None


# ── the copy itself ──────────────────────────────────────────────────────────

def test_the_folder_and_everything_in_it_is_copied(tmp_path):
    folder = _case(tmp_path)
    dest = pl._copy_folder_out(folder, tmp_path / "dest", log)
    # The FOLDER is copied, not merely its contents.
    assert dest == (tmp_path / "dest" / folder.name).resolve()
    assert (dest / "Motion.pdf").read_bytes() == b"%PDF-1.4 stub"
    assert (dest / "Text Files" / "Motion.txt").read_text() == "scrubbed body"


def test_a_rerun_replaces_what_is_there(tmp_path):
    folder = _case(tmp_path)
    pl._copy_folder_out(folder, tmp_path / "dest", log)
    (folder / "Text Files" / "Motion.txt").write_text("fixed body")
    dest = pl._copy_folder_out(folder, tmp_path / "dest", log)
    assert (dest / "Text Files" / "Motion.txt").read_text() == "fixed body"


def test_nothing_in_the_destination_is_deleted(tmp_path):
    # The destination is a place the operator works: a draft written beside the
    # copy is not this tool's to remove.
    folder = _case(tmp_path)
    dest = pl._copy_folder_out(folder, tmp_path / "dest", log)
    (dest / "my draft.docx").write_text("work in progress")
    pl._copy_folder_out(folder, tmp_path / "dest", log)
    assert (dest / "my draft.docx").read_text() == "work in progress"


def test_a_folder_is_never_copied_onto_itself(tmp_path):
    # This is a re-run started INSIDE the copy — the launcher travelled with
    # the folder, and it has to keep working.
    folder = _case(tmp_path)
    dest = pl._copy_folder_out(folder, folder.parent, log)
    assert dest == folder.resolve()
    assert not (folder / folder.name).exists()


def test_a_destination_inside_the_folder_is_refused(tmp_path):
    # Copying a folder into itself never terminates: the walk keeps finding
    # what it has just written.
    folder = _case(tmp_path)
    assert pl._copy_folder_out(folder, folder / "backup", log) is None
    assert not (folder / "backup" / folder.name).exists()


def test_one_unreadable_file_does_not_lose_the_rest(tmp_path, monkeypatch):
    # The usual cause is a workbook open in Excel; losing the other 40 files
    # to it would be absurd.
    folder = _case(tmp_path)
    import shutil as _sh
    orig = _sh.copy2

    def flaky(src, dst, *a, **k):
        if Path(src).name == "Motion.pdf":
            raise OSError("in use by another process")
        return orig(src, dst, *a, **k)
    monkeypatch.setattr(_sh, "copy2", flaky)
    dest = pl._copy_folder_out(folder, tmp_path / "dest", log)
    assert dest is not None
    assert (dest / "Text Files" / "Motion.txt").exists()
    assert not (dest / "Motion.pdf").exists()


# ── holding the copy back ────────────────────────────────────────────────────

def test_a_held_folder_is_not_copied(tmp_path):
    folder = _case(tmp_path)
    got = pl._copy_folder_after_run(folder, tmp_path / "dest", log,
                                    hold="1 export is quarantined")
    assert got is None
    assert not (tmp_path / "dest").exists()


def test_an_unheld_folder_is_copied(tmp_path):
    folder = _case(tmp_path)
    assert pl._copy_folder_after_run(folder, tmp_path / "dest", log) is not None


def test_no_destination_means_no_copy(tmp_path):
    assert pl._copy_folder_after_run(_case(tmp_path), None, log) is None


# ── the party spreadsheet travels with a deferred copy ───────────────────────

def test_the_order_spreadsheet_is_copied_in_from_downloads(tmp_path,
                                                           monkeypatch):
    # The launcher in the copy names no spreadsheet, so the run there resolves
    # its own — and "newest Order*.xlsx in Downloads" is right only until the
    # next case is downloaded, which is exactly the window a deferred folder
    # sits in.
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "Order_Template_Input.xlsx").write_bytes(b"PK stub")
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    folder = _case(tmp_path)
    dest = tmp_path / "dest" / folder.name
    dest.mkdir(parents=True)
    got = pl._copy_party_template(folder, dest, _args(), log)
    assert got == dest / "Order_Template_Input.xlsx"
    assert got.read_bytes() == b"PK stub"


def test_an_explicit_key_travels_instead(tmp_path):
    key = tmp_path / "elsewhere" / "Order Smith.xlsx"
    key.parent.mkdir()
    key.write_bytes(b"PK stub")
    folder = _case(tmp_path)
    dest = tmp_path / "dest" / folder.name
    dest.mkdir(parents=True)
    got = pl._copy_party_template(folder, dest, _args(key=key), log)
    assert got == dest / "Order Smith.xlsx"


def test_a_folder_that_carries_its_own_inputs_needs_nothing(tmp_path):
    folder = _case(tmp_path)
    dest = tmp_path / "dest" / folder.name
    dest.mkdir(parents=True)
    (dest / "pseudonym_key.xlsx").write_bytes(b"PK stub")   # came with it
    assert pl._copy_party_template(folder, dest, _args(), log) is None


def test_nothing_travels_when_pseudonymization_is_off(tmp_path):
    folder = _case(tmp_path)
    dest = tmp_path / "dest" / folder.name
    dest.mkdir(parents=True)
    assert pl._copy_party_template(folder, dest, _args(pseudonymize=False),
                                   log) is None


def test_an_all_word_folder_never_inherits_the_downloads_guess(tmp_path,
                                                               monkeypatch):
    # There the guess would not merely be a guess: a folder-local template
    # WINS, so a stranger's party list would become authoritative.
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "Order_Other_Case.xlsx").write_bytes(b"PK stub")
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    folder = tmp_path / "src" / "Word Case"
    folder.mkdir(parents=True)
    _docx(folder / "Filing.docx", "Body")
    dest = tmp_path / "dest" / folder.name
    dest.mkdir(parents=True)
    assert pl._copy_party_template(folder, dest, _args(), log) is None
    assert not list(dest.glob("*.xlsx"))


# ── end to end ───────────────────────────────────────────────────────────────

def _config(tmp_path, monkeypatch, text):
    path = tmp_path / "pdf_linker.config"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(pl, "_config_path", lambda: path)
    return path


def _run_main(folder, monkeypatch, *extra):
    monkeypatch.setattr(sys, "argv", ["pdf_linker.py", str(folder), *extra])
    try:
        pl.main()
    except SystemExit as e:
        return e.code
    return 0


def _launchers(folder):
    return {p.name for p in folder.iterdir()
            if p.suffix in (".bat", ".command")}


def test_deferred_run_copies_first_and_arms_both_folders(tmp_path, monkeypatch):
    # The destination is a local folder that syncs to the operator's other
    # machine, so the case has to be startable from either one: BOTH folders
    # get a launcher, and each runs the folder it sits in.
    _config(tmp_path, monkeypatch,
            f"defer_run = on\ncopy_to = {tmp_path / 'dest'}\n")
    folder = tmp_path / "Smith v Jones"
    folder.mkdir()
    _docx(folder / "Filing.docx", "Body")
    assert _run_main(folder, monkeypatch, "--no-pseudonymize") == 0
    copy = tmp_path / "dest" / folder.name
    assert (copy / "Filing.docx").exists()
    assert any(n.startswith("Run PDF-Linker") for n in _launchers(copy))
    assert any(n.startswith("Run PDF-Linker") for n in _launchers(folder))
    # Neither folder has been PROCESSED, which is what deferring means.
    assert not (folder / "Text Files").exists()
    assert not (copy / "Text Files").exists()


def test_each_deferred_launcher_runs_its_own_folder(tmp_path, monkeypatch):
    # Two launchers are only safe because neither names an absolute case
    # folder: whichever is clicked processes the folder it is in.
    _config(tmp_path, monkeypatch,
            f"defer_run = on\ncopy_to = {tmp_path / 'dest'}\n")
    folder = tmp_path / "Smith v Jones"
    folder.mkdir()
    _docx(folder / "Filing.docx", "Body")
    _run_main(folder, monkeypatch, "--no-pseudonymize")
    copy = tmp_path / "dest" / folder.name
    bodies = []
    for f in (folder, copy):
        launcher = next(p for p in f.iterdir()
                        if p.name.startswith("Run PDF-Linker"))
        bodies.append(launcher.read_text())
    assert str(folder) not in bodies[1] and str(copy) not in bodies[0]
    assert bodies[0] == bodies[1]          # identical, because self-locating


def test_the_order_spreadsheet_travels_with_a_deferred_copy(tmp_path,
                                                            monkeypatch):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "Order_Template_Input.xlsx").write_bytes(b"PK stub")
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    _config(tmp_path, monkeypatch,
            f"defer_run = on\ncopy_to = {tmp_path / 'dest'}\n")
    folder = tmp_path / "Smith v Jones"
    folder.mkdir()
    (folder / "Motion.pdf").write_bytes(b"%PDF-1.4 stub")
    _run_main(folder, monkeypatch)          # pseudonymization on: needs a list
    copy = tmp_path / "dest" / folder.name
    assert (copy / "Order_Template_Input.xlsx").exists()
    # ...and it was COPIED, not moved out of the source's reach.
    assert (downloads / "Order_Template_Input.xlsx").exists()


def test_a_failed_copy_falls_back_to_a_plain_deferred_run(tmp_path,
                                                          monkeypatch):
    # A copy that could not be made is simply a run with no destination: the
    # deferral itself still has to work, and this folder still has to be
    # runnable. (A destination inside the case folder is refused — that walk
    # never terminates — which is a copy failure like any other.)
    _config(tmp_path, monkeypatch, "defer_run = on\n")
    folder = tmp_path / "Smith v Jones"
    folder.mkdir()
    _docx(folder / "Filing.docx", "Body")
    code = _run_main(folder, monkeypatch, "--no-pseudonymize",
                     "--copy-to", str(folder / "inside"))
    assert code == 0
    assert any(n.startswith("Run PDF-Linker") for n in _launchers(folder))
    assert not (folder / "inside").exists()


def test_a_full_run_copies_at_the_end(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch, f"copy_to = {tmp_path / 'dest'}\n")
    folder = tmp_path / "Smith v Jones"
    folder.mkdir()
    _docx(folder / "Filing.docx", "Body")
    _run_main(folder, monkeypatch, "--no-pseudonymize")
    copy = tmp_path / "dest" / folder.name
    # The finished folder, as the operator would find it: exports, launcher,
    # finish stamp.
    assert list((copy / "Text Files").glob("*.txt"))
    assert list(copy.glob("DONE *.txt"))
    # BOTH folders end up with a re-run launcher, so the case can be re-run
    # from either machine.
    assert any(n.startswith("Re-run PDF-Linker") for n in _launchers(copy))
    assert any(n.startswith("Re-run PDF-Linker") for n in _launchers(folder))


def test_a_rerun_replaces_the_destination_copy(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch, f"copy_to = {tmp_path / 'dest'}\n")
    folder = tmp_path / "Smith v Jones"
    folder.mkdir()
    _docx(folder / "Filing.docx", "Body")
    _run_main(folder, monkeypatch, "--no-pseudonymize")
    _docx(folder / "Second.docx", "More")          # the forgotten filing
    _run_main(folder, monkeypatch, "--no-pseudonymize")
    copy = tmp_path / "dest" / folder.name
    assert len(list((copy / "Text Files").glob("*.txt"))) == 2


def test_no_copy_flag_stops_it(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch, f"copy_to = {tmp_path / 'dest'}\n")
    folder = tmp_path / "Smith v Jones"
    folder.mkdir()
    _docx(folder / "Filing.docx", "Body")
    _run_main(folder, monkeypatch, "--no-pseudonymize", "--no-copy")
    assert not (tmp_path / "dest").exists()


# ── the copy the full run held back for triage ───────────────────────────────
# A run that quarantines an export has decided the folder is not deliverable,
# so the copy waits; Apply Leak Fixes makes it when the last leak is released.

def _held_folder(tmp_path, fix):
    """A folder with one quarantined export, a key, and a worksheet answering
    the leak with `fix`."""
    import openpyxl
    td = tmp_path / "Text Files"
    td.mkdir()
    (td / "Brief.txt.LEAK").write_text(
        "====== Page 1 ======\nRaytheon Technologies opposed.\n",
        encoding="utf-8")
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Pseudonym Key"
    ws.append(["Category", "Real Value", "Replacement", "Status",
               "Source", "Occurrences"])
    ws.append(["person", "Filler Party", "Fake Party", "replaced", "--term", "1"])
    wb.save(tmp_path / "pseudonym_key.xlsx")
    wb2 = openpyxl.Workbook(); w2 = wb2.active; w2.title = "Potential Leaks"
    w2.append(["File", "Type", "Value", "Where (page:line)", "Fix? (yes/no)",
               "Notes"])
    w2.append(["Brief.txt.LEAK", "LEAK", "Raytheon Technologies", "p.1", fix, ""])
    wb2.save(tmp_path / "LEAKS.xlsx")
    return types.SimpleNamespace(term=[],
                                 key=str(tmp_path / "pseudonym_key.xlsx"))


def test_fix_leaks_makes_the_copy_once_the_last_leak_is_released(tmp_path):
    args = _held_folder(tmp_path, "yes")
    dest = tmp_path.parent / "dest"
    rc = pl._fix_leaks_mode(tmp_path, args, {"copy_to": str(dest)}, log)
    assert rc == 0
    copy = dest / tmp_path.name
    assert (copy / "Text Files" / "Brief.txt").exists()   # released, then copied
    assert not list((copy / "Text Files").glob("*.LEAK"))


def test_fix_leaks_keeps_holding_the_copy_while_a_leak_stands(tmp_path):
    # A typed replacement equal to the value fixes nothing, so the file stays
    # quarantined — and the destination must never receive a *.LEAK.
    args = _held_folder(tmp_path, "Raytheon Technologies")
    dest = tmp_path.parent / "dest"
    pl._fix_leaks_mode(tmp_path, args, {"copy_to": str(dest)}, log)
    assert (tmp_path / "Text Files" / "Brief.txt.LEAK").exists()   # still held
    assert not (dest / tmp_path.name).exists()


def test_a_stale_run_launcher_in_the_copy_is_superseded(tmp_path, monkeypatch):
    # The destination may have been a DEFERRED target before: its old
    # "Run PDF-Linker" says nothing here has been processed, which the copy of
    # a finished folder makes false.
    _config(tmp_path, monkeypatch, f"copy_to = {tmp_path / 'dest'}\n")
    folder = tmp_path / "Smith v Jones"
    folder.mkdir()
    _docx(folder / "Filing.docx", "Body")
    copy = tmp_path / "dest" / folder.name
    copy.mkdir(parents=True)
    (copy / "Run PDF-Linker.command").write_text("#!/bin/sh\n")
    (copy / "Run PDF-Linker.bat").write_text("@echo off\r\n")
    _run_main(folder, monkeypatch, "--no-pseudonymize")
    names = _launchers(copy)
    assert any(n.startswith("Re-run PDF-Linker") for n in names)
    assert not any(n.startswith("Run PDF-Linker") for n in names)


# ── the destination can be configured AFTER the folder has been run ──────────
# The copy is decided per run, from the config as it stands when the run
# starts, so adding or editing copy_to and clicking Re-run places the copy at
# the end of that run. Pinned because it is the natural way an operator adopts
# the setting: the folder is already processed by the time they think of it.

def test_adding_copy_to_later_copies_on_the_next_run(tmp_path, monkeypatch):
    cfg = _config(tmp_path, monkeypatch, "# no destination yet\n")
    folder = tmp_path / "Smith v Jones"
    folder.mkdir()
    _docx(folder / "Filing.docx", "Body")
    _run_main(folder, monkeypatch, "--no-pseudonymize")
    assert not (tmp_path / "dest").exists()

    cfg.write_text(f"copy_to = {tmp_path / 'dest'}\n", encoding="utf-8")
    _run_main(folder, monkeypatch, "--no-pseudonymize")
    copy = tmp_path / "dest" / folder.name
    assert list((copy / "Text Files").glob("*.txt"))
    assert list(copy.glob("DONE *.txt"))


def test_editing_the_destination_copies_to_the_new_one(tmp_path, monkeypatch):
    cfg = _config(tmp_path, monkeypatch, f"copy_to = {tmp_path / 'first'}\n")
    folder = tmp_path / "Smith v Jones"
    folder.mkdir()
    _docx(folder / "Filing.docx", "Body")
    _run_main(folder, monkeypatch, "--no-pseudonymize")
    assert (tmp_path / "first" / folder.name).is_dir()

    cfg.write_text(f"copy_to = {tmp_path / 'second'}\n", encoding="utf-8")
    _run_main(folder, monkeypatch, "--no-pseudonymize")
    assert list((tmp_path / "second" / folder.name / "Text Files").glob("*.txt"))


def test_adding_copy_to_later_also_works_on_a_deferred_start(tmp_path,
                                                             monkeypatch):
    # There the copy is made at the START, and the folder it copies is the
    # finished one — the run that produced it happened before the setting did.
    cfg = _config(tmp_path, monkeypatch, "# no destination yet\n")
    folder = tmp_path / "Smith v Jones"
    folder.mkdir()
    _docx(folder / "Filing.docx", "Body")
    _run_main(folder, monkeypatch, "--no-pseudonymize")

    cfg.write_text(f"defer_run = on\ncopy_to = {tmp_path / 'dest'}\n",
                   encoding="utf-8")
    _run_main(folder, monkeypatch, "--no-pseudonymize")
    copy = tmp_path / "dest" / folder.name
    assert list((copy / "Text Files").glob("*.txt"))
    # The folder has been processed, so both launchers say so.
    assert any(n.startswith("Re-run PDF-Linker") for n in _launchers(copy))
