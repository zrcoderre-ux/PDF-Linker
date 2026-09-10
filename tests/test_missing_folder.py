"""A folder that is not there says so, somewhere the operator can find it.

`main` checks the folder argument before anything else, and until now it said
so with a bare `print`. The normal launch is `pythonw.exe`, which has no
stdout, and `pdf_linker.log` lives INSIDE the folder that is missing — so the
process started, printed into the void and exited 1. From the outside that is
identical to Python never starting, and it also defeats "is there a log?" as a
diagnostic, since there is no log either way. That is the failure
`_install_crash_logging` exists to prevent, arriving one step ahead of it.

The commonest CAUSE is invisible too: a shortcut records an absolute path and
Windows moves the folder underneath it, redirecting Desktop and Documents into
OneDrive. So where the twin can be FOUND it is named, rather than left to be
guessed at.

Run:  cd PDF-Linker && python3 -m pytest tests/test_missing_folder.py -v
"""
import subprocess
import sys
from pathlib import Path

import pdf_linker as P


def _profile(tmp_path, monkeypatch):
    """A user profile with the Desktop redirected into OneDrive: the stale
    local Desktop still there, the folder living in the OneDrive twin."""
    home = tmp_path / "ZCoderre"
    (home / "Desktop").mkdir(parents=True)
    (home / "OneDrive" / "Desktop" / "Convert").mkdir(parents=True)
    monkeypatch.setattr(P.Path, "home", staticmethod(lambda: home))
    return home


def test_the_message_names_where_the_folder_went(tmp_path, monkeypatch):
    home = _profile(tmp_path, monkeypatch)
    msg = P._missing_folder_message(home / "Desktop" / "Convert")
    assert "Not a folder" in msg
    assert str(home / "OneDrive" / "Desktop" / "Convert") in msg
    assert "MOVED" in msg


def test_a_work_tenant_onedrive_is_found_too(tmp_path, monkeypatch):
    """A work or school account is "OneDrive - <Organisation>", not
    "OneDrive"."""
    home = tmp_path / "ZCoderre"
    (home / "Desktop").mkdir(parents=True)
    (home / "OneDrive - Superior Court" / "Desktop" / "Convert").mkdir(parents=True)
    monkeypatch.setattr(P.Path, "home", staticmethod(lambda: home))
    msg = P._missing_folder_message(home / "Desktop" / "Convert")
    assert str(home / "OneDrive - Superior Court" / "Desktop" / "Convert") in msg


def test_the_twin_is_found_in_the_other_direction(tmp_path, monkeypatch):
    """A shortcut made AFTER the redirect, kept when the folder moved back
    out: the path names OneDrive and the folder is in the plain profile."""
    home = tmp_path / "ZCoderre"
    (home / "OneDrive" / "Desktop").mkdir(parents=True)
    (home / "Desktop" / "Convert").mkdir(parents=True)
    monkeypatch.setattr(P.Path, "home", staticmethod(lambda: home))
    msg = P._missing_folder_message(home / "OneDrive" / "Desktop" / "Convert")
    assert str(home / "Desktop" / "Convert") in msg


def test_no_twin_claims_no_move(tmp_path, monkeypatch):
    """It must never say the folder moved when it cannot show where to."""
    home = tmp_path / "ZCoderre"
    (home / "Desktop").mkdir(parents=True)
    monkeypatch.setattr(P.Path, "home", staticmethod(lambda: home))
    msg = P._missing_folder_message(home / "Desktop" / "Gone")
    assert "MOVED" not in msg and "It exists here" not in msg
    assert "OneDrive" in msg              # still worth naming as a cause


def test_the_message_is_logged_where_the_folder_should_have_been(tmp_path,
                                                                monkeypatch):
    home = _profile(tmp_path, monkeypatch)
    missing = home / "Desktop" / "Convert"
    where = P._missing_folder_log(missing)
    assert where == home / "Desktop" / P._MISSING_FOLDER_LOG
    body = where.read_text(encoding="utf-8")
    assert "Not a folder" in body and "[ERROR]" in body
    assert str(home / "OneDrive" / "Desktop" / "Convert") in body


def test_the_log_falls_back_when_the_parent_is_gone_too(tmp_path, monkeypatch):
    """A path several levels of nothing deep still gets its message written —
    beside the tool, or in TEMP."""
    monkeypatch.setattr(P.Path, "home", staticmethod(lambda: tmp_path))
    where = P._missing_folder_log(tmp_path / "no" / "such" / "place")
    assert where is not None and where.is_file()
    assert "Not a folder" in where.read_text(encoding="utf-8")


def test_the_run_exits_one_and_leaves_the_message_on_disk(tmp_path):
    """End to end, as the launcher runs it: a real process, a real exit code,
    and a log to find afterwards. Asserted from a SUBPROCESS because that is
    the only thing that sees the exit status the shortcut sees."""
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    missing = desktop / "Convert"
    out = subprocess.run(
        [sys.executable, str(Path(P.__file__).resolve()), str(missing)],
        capture_output=True, text=True)
    assert out.returncode == 1, out.stderr
    assert "Not a folder" in out.stdout
    log = desktop / P._MISSING_FOLDER_LOG
    assert log.is_file(), sorted(p.name for p in desktop.iterdir())
    assert "Not a folder" in log.read_text(encoding="utf-8")
