"""
Deferred start (config `defer_run`): starting the tool on a folder writes a
one-click "Run PDF-Linker" launcher into it and does nothing else, so the
folder can be MOVED before the work begins — the launcher targets its own
directory, so it survives the move. The first real run replaces it with the
ordinary "Re-run PDF-Linker" launcher, so a folder never carries both.

The load-bearing rule is `--no-defer` on BOTH launchers: a double-click means
"run this folder NOW", so it must override defer_run in the config. Without it
that setting would make every double-click rewrite the launcher and exit, and
nothing the operator has would ever process the folder.

Run:  cd PDF-Linker && python3 -m pytest tests/test_deferred_run.py -v
"""
import importlib.util
import logging
import os
import sys
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
    """A minimal one-paragraph .docx, so a folder can hold a real document
    without needing fitz to read it."""
    body = f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'
    doc = (f'<?xml version="1.0" encoding="UTF-8"?>'
           f'<w:document xmlns:w="{_W}"><w:body>{body}</w:body></w:document>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", doc)
    return path


def _launchers(folder):
    return {p.name for p in folder.iterdir()
            if p.suffix in (".bat", ".command")}


def _config(tmp_path, monkeypatch, text):
    """Point the tool's config at a file we control for this test."""
    path = tmp_path / "pdf_linker.config"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(pl, "_config_path", lambda: path)
    return path


def _run_main(folder, monkeypatch, *extra):
    """main() on `folder`, returning its exit code. A full run returns
    normally (0); the short paths — a deferred start among them — sys.exit."""
    monkeypatch.setattr(sys, "argv",
                        ["pdf_linker.py", str(folder), "--no-pseudonymize",
                         *extra])
    try:
        pl.main()
    except SystemExit as e:
        return e.code
    return 0


# ── the launcher a deferred start writes ─────────────────────────────────────

def test_deferred_bat_is_named_run_not_rerun():
    # "Re-run" would say the opposite of what is true: nothing in this folder
    # has been processed yet.
    name, content, make_exec = pl._rerun_launcher_spec(
        r"C:\Py\python.exe", r"C:\Tools\pdf_linker.py", "lexis",
        want_key=False, windows=True, deferred=True)
    assert name == "Run PDF-Linker.bat" and make_exec is False
    assert '"%~dp0."' in content and "--provider lexis" in content
    assert "\r\n" in content


def test_deferred_launcher_runs_now_rather_than_deferring_again():
    # Without --no-defer, a double-click under `defer_run = on` would only
    # rewrite this same file and exit: the deferral could never end.
    _n, content, _e = pl._rerun_launcher_spec(
        r"C:\Py\python.exe", r"C:\Tools\pdf_linker.py", "lexis",
        want_key=False, windows=True, deferred=True)
    assert "--no-defer" in content


def test_the_rerun_launcher_also_runs_now():
    # Same reasoning, and it is the launcher a deferred folder ends up with:
    # a double-click is the operator asking to run, whatever the config says.
    _n, content, _e = pl._rerun_launcher_spec(
        r"C:\Py\python.exe", r"C:\Tools\pdf_linker.py", "lexis",
        want_key=True, windows=True)
    assert "--no-defer" in content


def test_deferred_launcher_says_what_it_is_and_what_replaces_it():
    _n, content, _e = pl._rerun_launcher_spec(
        r"C:\Py\python.exe", r"C:\Tools\pdf_linker.py", "lexis",
        want_key=False, windows=True, deferred=True)
    assert "deferred" in content.lower()
    assert "Re-run" in content            # names its successor
    assert "pdf_linker.log" in content and "DONE" in content
    # Detached and silent, exactly like the re-run launcher.
    assert "pause" not in content and "timeout" not in content


def test_deferred_launcher_pins_the_key_when_the_folder_has_one():
    _n, content, _e = pl._rerun_launcher_spec(
        r"C:\Py\python.exe", r"C:\Tools\pdf_linker.py", "lexis",
        want_key=True, windows=True, deferred=True)
    assert '--key "%~dp0pseudonym_key.xlsx"' in content


def test_deferred_posix_command_is_executable_and_self_locating():
    name, content, make_exec = pl._rerun_launcher_spec(
        "/usr/bin/python3", "/tools/pdf_linker.py", "lexis",
        want_key=False, windows=False, deferred=True)
    assert name == "Run PDF-Linker.command" and make_exec is True
    # Self-locating is what makes the move safe: it runs the folder it sits in.
    assert '"$(dirname "$0")"' in content
    assert "--no-defer" in content and "nohup " in content


def test_deferred_frozen_build_omits_the_script_path():
    _n, content, _e = pl._rerun_launcher_spec(
        r"C:\App\pdf_linker.exe", r"C:\App\_MEI\pdf_linker.py", "lexis",
        want_key=False, windows=True, frozen=True, deferred=True)
    assert r'"C:\App\pdf_linker.exe" "%~dp0."' in content
    assert "pdf_linker.py" not in content


# ── writing and superseding ──────────────────────────────────────────────────

def test_writer_creates_the_deferred_launcher(tmp_path):
    assert pl._write_deferred_launcher(tmp_path, "lexis", False, log) is True
    launchers = _launchers(tmp_path)
    assert len(launchers) == 1
    name = launchers.pop()
    assert name.startswith("Run PDF-Linker")
    if os.name != "nt":
        assert os.access(tmp_path / name, os.X_OK)


def test_a_failed_write_is_reported_not_swallowed(tmp_path, monkeypatch):
    # It is the ONLY output of a deferred run: if it cannot be written the
    # folder is left with nothing processed and nothing to process it with,
    # which the caller turns into a non-zero exit.
    def boom(*a, **k):
        raise OSError("read-only")
    monkeypatch.setattr(pl, "_write_launcher_file", boom)
    assert pl._write_deferred_launcher(tmp_path, "lexis", False, log) is False


def test_the_real_run_replaces_the_deferred_launcher(tmp_path):
    pl._write_deferred_launcher(tmp_path, "lexis", False, log)
    pl._write_rerun_launcher(tmp_path, "lexis", want_key=False, log=log)
    names = _launchers(tmp_path)
    assert any(n.startswith("Re-run PDF-Linker") for n in names)
    assert not any(n.startswith("Run PDF-Linker") for n in names)


def test_the_deferred_launcher_survives_a_failed_replacement(tmp_path,
                                                             monkeypatch):
    # Removed only AFTER the replacement is on disk, so a folder is never left
    # with neither launcher.
    pl._write_deferred_launcher(tmp_path, "lexis", False, log)

    def boom(*a, **k):
        raise OSError("read-only")
    monkeypatch.setattr(pl, "_write_launcher_file", boom)
    assert pl._write_rerun_launcher(tmp_path, "lexis", False, log) is False
    assert any(n.startswith("Run PDF-Linker") for n in _launchers(tmp_path))


# ── end to end ───────────────────────────────────────────────────────────────

def test_defer_writes_the_launcher_and_processes_nothing(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch, "defer_run = on\n")
    folder = tmp_path / "case"
    folder.mkdir()
    _docx(folder / "Filing.docx", "Body")
    assert _run_main(folder, monkeypatch) == 0
    assert any(n.startswith("Run PDF-Linker") for n in _launchers(folder))
    # Nothing was processed: no exports, no key, no finish stamp.
    assert not (folder / "Text Files").exists()
    assert not (folder / "pseudonym_key.xlsx").exists()
    assert not list(folder.glob("DONE *.txt"))
    assert not list(folder.glob("ETA *.txt"))


def test_the_deferred_launcher_runs_the_folder_it_is_moved_to(tmp_path,
                                                              monkeypatch):
    # The command names no absolute case folder — only the launcher's own
    # directory — which is the whole point: the folder is about to move.
    _config(tmp_path, monkeypatch, "defer_run = on\n")
    folder = tmp_path / "case"
    folder.mkdir()
    _docx(folder / "Filing.docx", "Body")
    _run_main(folder, monkeypatch)
    launcher = next(p for p in folder.iterdir()
                    if p.name.startswith("Run PDF-Linker"))
    body = launcher.read_text()
    assert str(folder) not in body
    assert ('"%~dp0."' in body) or ('"$(dirname "$0")"' in body)


def test_no_defer_overrides_the_config_so_a_double_click_runs(tmp_path,
                                                              monkeypatch):
    _config(tmp_path, monkeypatch, "defer_run = on\n")
    folder = tmp_path / "case"
    folder.mkdir()
    _docx(folder / "Filing.docx", "Body")
    _run_main(folder, monkeypatch, "--no-defer")
    assert list((folder / "Text Files").glob("*.txt"))
    assert any(n.startswith("Re-run PDF-Linker") for n in _launchers(folder))


def test_the_second_run_supersedes_the_deferred_launcher(tmp_path, monkeypatch):
    """The operator's whole sequence: defer, (move), double-click, done."""
    _config(tmp_path, monkeypatch, "defer_run = on\n")
    folder = tmp_path / "case"
    folder.mkdir()
    _docx(folder / "Filing.docx", "Body")
    _run_main(folder, monkeypatch)
    assert any(n.startswith("Run PDF-Linker") for n in _launchers(folder))
    _run_main(folder, monkeypatch, "--no-defer")     # what the launcher does
    names = _launchers(folder)
    assert any(n.startswith("Re-run PDF-Linker") for n in names)
    assert not any(n.startswith("Run PDF-Linker") for n in names)
    assert list((folder / "Text Files").glob("*.txt"))


def test_defer_is_off_by_default(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch, "# nothing set here\n")
    folder = tmp_path / "case"
    folder.mkdir()
    _docx(folder / "Filing.docx", "Body")
    _run_main(folder, monkeypatch)
    assert list((folder / "Text Files").glob("*.txt"))
    assert not any(n.startswith("Run PDF-Linker") for n in _launchers(folder))


def test_fix_leaks_is_never_deferred(tmp_path, monkeypatch):
    # --fix-leaks is the operator asking for that pass NOW. (It exits 1 here
    # for want of a key; what matters is that it never became a launcher.)
    _config(tmp_path, monkeypatch, "defer_run = on\n")
    folder = tmp_path / "case"
    folder.mkdir()
    _docx(folder / "Filing.docx", "Body")
    _run_main(folder, monkeypatch, "--fix-leaks")
    assert not any(n.startswith("Run PDF-Linker") for n in _launchers(folder))


def test_an_already_processed_folder_keeps_one_launcher(tmp_path, monkeypatch):
    # Deferring a folder that has already been run refreshes its re-run
    # launcher rather than adding a second file claiming nothing here has been
    # processed — the two would say opposite things about the same folder.
    _config(tmp_path, monkeypatch, "defer_run = on\n")
    folder = tmp_path / "case"
    folder.mkdir()
    _docx(folder / "Filing.docx", "Body")
    _run_main(folder, monkeypatch, "--no-defer")
    _run_main(folder, monkeypatch)
    names = _launchers(folder)
    assert any(n.startswith("Re-run PDF-Linker") for n in names)
    assert not any(n.startswith("Run PDF-Linker") for n in names)


def test_a_stale_launcher_is_rearmed_rather_than_looping(tmp_path, monkeypatch):
    # A re-run launcher written before --no-defer existed would defer on every
    # double-click. The refresh above is what re-arms it.
    _config(tmp_path, monkeypatch, "defer_run = on\n")
    folder = tmp_path / "case"
    folder.mkdir()
    _docx(folder / "Filing.docx", "Body")
    for suffix in (".bat", ".command"):
        (folder / f"Re-run PDF-Linker{suffix}").write_text("old launcher\n")
    _run_main(folder, monkeypatch)
    refreshed = [p for p in folder.iterdir()
                 if p.name.startswith("Re-run PDF-Linker")
                 and "--no-defer" in p.read_text()]
    assert refreshed


def test_an_empty_folder_still_gets_its_launcher(tmp_path, monkeypatch):
    # Deferring is FOR the folder that is not ready yet, so one still being
    # filled is the expected case, not an error.
    _config(tmp_path, monkeypatch, "defer_run = on\n")
    folder = tmp_path / "case"
    folder.mkdir()
    assert _run_main(folder, monkeypatch) == 0
    assert any(n.startswith("Run PDF-Linker") for n in _launchers(folder))


# ── the shipped config template documents it ─────────────────────────────────

def test_config_template_documents_defer_run():
    tpl = pl._CONFIG_TEMPLATE
    assert "defer_run = off" in tpl              # documented, and off by default
    assert "Run PDF-Linker" in tpl
