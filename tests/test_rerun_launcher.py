"""
One-click re-run launcher: after a run the tool drops a double-clickable file
in the folder that re-invokes it on that same folder (the fast path for
applying Fix? decisions). It targets its own directory so it survives a move,
and points --key at the folder's own key so the re-run reproduces the fakes.

Run:  cd PDF-Linker && python3 -m pytest tests/test_rerun_launcher.py -v
"""
import logging
import os
from pathlib import Path

import pytest

import pdf_linker as P

log = logging.getLogger("test")


def test_windows_bat_targets_own_folder_with_key():
    name, content, make_exec = P._rerun_launcher_spec(
        r"C:\Py\python.exe", r"C:\Tools\pdf_linker.py", "lexis",
        want_key=True, windows=True)
    assert name == "Re-run PDF-Linker.bat" and make_exec is False
    # %~dp0. — the "." avoids the trailing-backslash-before-quote cmd bug
    assert '"%~dp0."' in content
    assert "--provider lexis" in content
    assert '--key "%~dp0pseudonym_key.xlsx"' in content
    assert content.endswith("pause\r\n")          # window stays to show result
    assert "\r\n" in content                       # CRLF for cmd
    # A visible banner so the window is never blank, even under a windowless
    # interpreter that prints nothing of its own.
    assert "echo Re-running PDF-Linker" in content
    # Non-frozen: the interpreter needs the script path.
    assert r'"C:\Tools\pdf_linker.py"' in content


def test_windows_bat_frozen_omits_script_path():
    # A packaged .exe IS the entry point; passing the (bundled, ephemeral)
    # script path is what opened an empty console.
    _n, content, _e = P._rerun_launcher_spec(
        r"C:\App\pdf_linker.exe", r"C:\App\_MEI\pdf_linker.py", "lexis",
        want_key=True, windows=True, frozen=True)
    assert r'"C:\App\pdf_linker.exe" "%~dp0."' in content
    assert "pdf_linker.py" not in content          # no script arg when frozen
    assert "--provider lexis" in content


def test_windows_bat_without_key_when_not_pseudonymizing():
    _n, content, _e = P._rerun_launcher_spec(
        r"C:\Py\python.exe", r"C:\Tools\pdf_linker.py", "westlaw",
        want_key=False, windows=True)
    assert "--key" not in content and "--provider westlaw" in content


def test_posix_command_is_executable_and_self_locating():
    name, content, make_exec = P._rerun_launcher_spec(
        "/usr/bin/python3", "/tools/pdf_linker.py", "lexis",
        want_key=True, windows=False)
    assert name == "Re-run PDF-Linker.command" and make_exec is True
    assert content.startswith("#!/bin/sh")
    assert '"$(dirname "$0")"' in content
    assert '--key "$(dirname "$0")/pseudonym_key.xlsx"' in content
    # No `exec`, so the trailing status line still runs after the tool exits.
    assert "Re-running PDF-Linker" in content and "Finished" in content


def test_writer_creates_launcher_without_clobbering_other_markers(tmp_path):
    P._write_rerun_launcher(tmp_path, "lexis", want_key=True, log=log)
    launchers = [p for p in tmp_path.iterdir()
                 if p.name.startswith("Re-run PDF-Linker")]
    assert len(launchers) == 1
    f = launchers[0]
    assert "pdf_linker.py" in f.read_text()
    if os.name != "nt":
        assert os.access(f, os.X_OK)
    # doesn't create an ETA marker or leaks file
    assert not list(tmp_path.glob("ETA *.txt"))
    assert not list(tmp_path.glob("pdf_linker_leaks.*"))
