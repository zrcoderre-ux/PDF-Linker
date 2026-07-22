"""
--fix-leaks applies the worksheet Fix?=yes decisions to the .txt/.LEAK exports
directly (no PDFs), un-quarantines files that are now clean, and preserves +
extends the key. A companion 'Apply Leak Fixes' launcher runs it on the folder.

Run:  cd PDF-Linker && python3 -m pytest tests/test_fix_leaks.py -v
"""
import logging
from pathlib import Path

import openpyxl
import pytest

import pdf_linker as P

log = logging.getLogger("test")


def _setup(folder):
    tdir = folder / "Text Files"
    tdir.mkdir()
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Ford Motor Company"], ["24STCV24253"], [],
                              registry=reg)
    pz = P.Pseudonymizer(terms, {}, registry=reg)
    pz.apply("Ford Motor Company")
    pz.write_key(folder / "pseudonym_key.xlsx", log)
    (tdir / "Opposition.txt.LEAK").write_text(
        "====== Page 1 ======\n(Yu Decl.) Gregory Yu testified.\n",
        encoding="utf-8")
    (tdir / "Motion.txt").write_text(
        "====== Page 1 ======\nGregory Yu appeared.\n", encoding="utf-8")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["File", "Type", "Value", "Where", "Fix? (yes/no)", "Notes"])
    ws.append(["Opposition.txt.LEAK", "LEAK", "Gregory Yu", "p.1:2", "yes", ""])
    wb.save(folder / "LEAKS.xlsx")
    return tdir


class _Args:
    key = None
    term = None


def test_fix_leaks_scrubs_unquarantines_and_extends_key(tmp_path):
    tdir = _setup(tmp_path)
    args = _Args()
    args.key = str(tmp_path / "pseudonym_key.xlsx")
    code = P._fix_leaks_mode(tmp_path, args, {}, log)
    assert code == 0                                   # no primary leaks left

    # .LEAK un-quarantined; the flagged name scrubbed in BOTH files
    assert (tdir / "Opposition.txt").exists()
    assert not (tdir / "Opposition.txt.LEAK").exists()
    opp = (tdir / "Opposition.txt").read_text()
    assert "Gregory Yu" not in opp and "Yu Decl." not in opp
    assert "Yu" not in (tdir / "Motion.txt").read_text()

    # key preserved the party AND added the fixed name
    reals = [r[1] for r in openpyxl.load_workbook(
        tmp_path / "pseudonym_key.xlsx")["Pseudonym Key"].iter_rows(
        min_row=2, values_only=True)]
    assert "Ford Motor Company" in reals and "Gregory Yu" in reals


def test_fix_leaks_needs_a_real_key(tmp_path):
    (tmp_path / "Text Files").mkdir()
    args = _Args()
    assert P._fix_leaks_mode(tmp_path, args, {}, log) == 1   # no key -> refuse


def test_fix_leaks_noop_without_yes_decisions(tmp_path):
    tdir = _setup(tmp_path)
    # flip the only decision to "no"
    wb = openpyxl.load_workbook(tmp_path / "LEAKS.xlsx")
    wb.active["E2"] = "no"
    wb.save(tmp_path / "LEAKS.xlsx")
    args = _Args()
    args.key = str(tmp_path / "pseudonym_key.xlsx")
    assert P._fix_leaks_mode(tmp_path, args, {}, log) == 0
    assert (tdir / "Opposition.txt.LEAK").exists()          # untouched


def test_fix_launcher_spec_windows_and_frozen():
    n, c, _ = P._fix_launcher_spec(r"C:\Py\python.exe", r"C:\T\pdf_linker.py", True)
    assert n == "Apply Leak Fixes.bat"
    assert "--fix-leaks" in c and '"%~dp0."' in c and c.endswith("pause\r\n")
    _n, cf, _e = P._fix_launcher_spec(r"C:\App\app.exe", r"C:\x.py", True, frozen=True)
    assert "x.py" not in cf and "--fix-leaks" in cf       # no script arg when frozen


# ─── Bug fixes: tool artifacts in fallback layout; NFKC-only no-op ────────────

def test_fallback_layout_ignores_tool_artifacts(tmp_path):
    # Old single-folder layout: the worksheet's .txt companion legitimately
    # CONTAINS real leaked values and must not be scanned as an export (it made
    # the run report a phantom leak and exit 2); run markers stay untouched.
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Ford Motor Company"], ["24STCV24253"], [],
                              registry=reg)
    pz = P.Pseudonymizer(terms, {}, registry=reg)
    pz.apply("Ford Motor Company")
    pz.write_key(tmp_path / "pseudonym_key.xlsx", log)
    (tmp_path / "Brief.txt").write_text("Gregory Yu appeared.", encoding="utf-8")
    (tmp_path / "LEAKS.txt").write_text(
        "LEAK  Ford Motor Company  p.1:2", encoding="utf-8")
    (tmp_path / "DONE 4.25PM.txt").write_text("", encoding="utf-8")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["File", "Type", "Value", "Where", "Fix? (yes/no)", "Notes"])
    ws.append(["Brief.txt", "LEAK", "Gregory Yu", "p.1:1", "yes", ""])
    wb.save(tmp_path / "LEAKS.xlsx")
    args = _Args()
    args.key = str(tmp_path / "pseudonym_key.xlsx")
    assert P._fix_leaks_mode(tmp_path, args, {}, log) == 0   # no phantom leak
    assert "Yu" not in (tmp_path / "Brief.txt").read_text()
    marker = tmp_path / "DONE 4.25PM.txt"
    assert marker.exists() and marker.stat().st_size == 0


def test_nfkc_only_difference_is_not_rewritten(tmp_path):
    tdir = _setup(tmp_path)
    lig = tdir / "Clean.txt"
    lig.write_text("The ﬁnding was aﬃrmed.", encoding="utf-8")  # ligatures only
    args = _Args()
    args.key = str(tmp_path / "pseudonym_key.xlsx")
    P._fix_leaks_mode(tmp_path, args, {}, log)
    assert lig.read_text() == "The ﬁnding was aﬃrmed."          # untouched


# ── Auto-cleanup: once every LEAK file is fixed, remove the workflow files ────
def _fixable_folder(tmp_path):
    """A folder with one quarantined export and a key+worksheet that resolve it,
    plus a stand-in Apply-Leak-Fixes launcher."""
    td = tmp_path / "Text Files"
    td.mkdir()
    (td / "Brief.txt.LEAK").write_text(
        "====== Page 1 ======\nRaytheon Technologies opposed.\n", encoding="utf-8")
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Pseudonym Key"
    ws.append(["Category", "Real Value", "Replacement", "Status",
               "Source", "Occurrences"])
    ws.append(["person", "Filler Party", "Fake Party", "replaced", "--term", "1"])
    wb.save(tmp_path / "pseudonym_key.xlsx")
    wb2 = openpyxl.Workbook(); w2 = wb2.active; w2.title = "Potential Leaks"
    w2.append(["File", "Type", "Value", "Where (page:line)", "Fix? (yes/no)", "Notes"])
    w2.append(["Brief.txt.LEAK", "LEAK", "Raytheon Technologies", "p.1", "yes", ""])
    wb2.save(tmp_path / "LEAKS.xlsx")
    (tmp_path / "Apply Leak Fixes.command").write_text("#!/bin/sh\n", encoding="utf-8")
    return td


def _fl_args(folder):
    import types
    return types.SimpleNamespace(term=[], key=str(folder / "pseudonym_key.xlsx"))


def test_resolved_run_deletes_worksheet_and_launcher(tmp_path):
    td = _fixable_folder(tmp_path)
    rc = P._fix_leaks_mode(tmp_path, _fl_args(tmp_path), {}, log)
    assert rc == 0
    assert not (td / "Brief.txt.LEAK").exists()          # un-quarantined
    assert not (tmp_path / "LEAKS.xlsx").exists()         # worksheet removed
    assert not (tmp_path / "Apply Leak Fixes.command").exists()   # launcher removed


def test_unresolved_run_keeps_worksheet_and_launcher(tmp_path):
    # A leak the key can't resolve (no matching term) keeps the file
    # quarantined, so the worksheet and launcher must stay.
    td = tmp_path / "Text Files"; td.mkdir()
    (td / "Brief.txt.LEAK").write_text(
        "====== Page 1 ======\nOmega Dynamics opposed.\n", encoding="utf-8")
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Pseudonym Key"
    ws.append(["Category", "Real Value", "Replacement", "Status",
               "Source", "Occurrences"])
    ws.append(["person", "Filler Party", "Fake Party", "replaced", "--term", "1"])
    wb.save(tmp_path / "pseudonym_key.xlsx")
    wb2 = openpyxl.Workbook(); w2 = wb2.active; w2.title = "Potential Leaks"
    w2.append(["File", "Type", "Value", "Where (page:line)", "Fix? (yes/no)", "Notes"])
    # A typed replacement equal to the value is rejected — nothing gets fixed.
    w2.append(["Brief.txt.LEAK", "LEAK", "Omega Dynamics", "p.1",
               "Omega Dynamics", ""])
    wb2.save(tmp_path / "LEAKS.xlsx")
    (tmp_path / "Apply Leak Fixes.command").write_text("#!/bin/sh\n", encoding="utf-8")
    P._fix_leaks_mode(tmp_path, _fl_args(tmp_path), {}, log)
    assert (td / "Brief.txt.LEAK").exists()               # still quarantined
    assert (tmp_path / "LEAKS.xlsx").exists()             # worksheet kept
    assert (tmp_path / "Apply Leak Fixes.command").exists()
