"""
A value typed into the leak worksheet's Fix? column (anything other than
yes/no) is an explicit operator-provided replacement: it is applied verbatim,
bypassing the auto-faker. The fix persists into the reversal key and survives a
re-run, so --fix-leaks converges instead of re-deriving a different fake.

Run:  cd PDF-Linker && python3 -m pytest tests/test_typed_leak_fix.py -v
"""
import logging
import types
from pathlib import Path

import openpyxl
import pytest

import pdf_linker as P

log = logging.getLogger("test")


def _key_with_self_map(folder):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Pseudonym Key"
    ws.append(["Category", "Real Value", "Replacement", "Status",
               "Source", "Occurrences"])
    ws.append(["person", "M & M", "M & M", "leaked", "--term", "21"])
    wb.save(folder / "pseudonym_key.xlsx")


def _worksheet(folder, fix_cell):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Potential Leaks"
    ws.append(["File", "Type", "Value", "Where (page:line)",
               "Fix? (yes/no)", "Notes"])
    ws.append(["Motion.txt.LEAK", "LEAK", "M & M", "p.1", fix_cell, ""])
    wb.save(folder / "pdf_linker_leaks.xlsx")


def _setup(folder, fix_cell):
    tdir = folder / "Text Files"
    tdir.mkdir()
    (tdir / "Motion.txt.LEAK").write_text(
        "====== Page 1 ======\nPlaintiff sues M & M; M & M denies it.\n",
        encoding="utf-8")
    _key_with_self_map(folder)
    _worksheet(folder, fix_cell)
    return tdir


def _key_rows(folder):
    ws = openpyxl.load_workbook(folder / "pseudonym_key.xlsx",
                                data_only=True).active
    return [r for r in ws.iter_rows(values_only=True)
            if r and str(r[1]).strip() == "M & M"]


def _fix_cell(folder):
    ws = openpyxl.load_workbook(folder / "pdf_linker_leaks.xlsx",
                                data_only=True).active
    for r in ws.iter_rows(values_only=True):
        if r and str(r[2]).strip() == "M & M":
            return str(r[4] or "")
    return None


def _args(folder):
    return types.SimpleNamespace(term=[], key=str(folder / "pseudonym_key.xlsx"))


def test_typed_replacement_scrubs_and_unquarantines(tmp_path):
    tdir = _setup(tmp_path, "FOXGLEN & FOXGLEN")
    rc = P._fix_leaks_mode(tmp_path, _args(tmp_path), {}, log)
    assert rc == 0                                   # loop cleared
    assert not (tdir / "Motion.txt.LEAK").exists()   # un-quarantined
    body = (tdir / "Motion.txt").read_text()
    assert "M & M" not in body
    assert "FOXGLEN & FOXGLEN" in body


def test_typed_replacement_persists_in_key(tmp_path):
    _setup(tmp_path, "FOXGLEN & FOXGLEN")
    P._fix_leaks_mode(tmp_path, _args(tmp_path), {}, log)
    rows = _key_rows(tmp_path)
    assert rows and rows[0][2] == "FOXGLEN & FOXGLEN"   # not the self-map


def test_typed_replacement_is_idempotent(tmp_path):
    _setup(tmp_path, "FOXGLEN & FOXGLEN")
    assert P._fix_leaks_mode(tmp_path, _args(tmp_path), {}, log) == 0
    # The typed value must be carried back into the worksheet, not collapsed
    # to "yes" (which would re-derive a different fake and drop the binding).
    assert _fix_cell(tmp_path) == "FOXGLEN & FOXGLEN"
    assert P._fix_leaks_mode(tmp_path, _args(tmp_path), {}, log) == 0
    rows = _key_rows(tmp_path)
    assert rows and rows[0][2] == "FOXGLEN & FOXGLEN"   # binding still present


def test_self_identical_typed_value_is_rejected(tmp_path, caplog):
    # Typing the value back in as its own replacement can never scrub it: it is
    # ignored (with a warning), leaving nothing to apply — the file stays
    # quarantined rather than shipping with the leak.
    tdir = _setup(tmp_path, "M & M")
    with caplog.at_level(logging.WARNING):
        rc = P._fix_leaks_mode(tmp_path, _args(tmp_path), {}, log)
    assert rc == 0                                   # nothing actionable
    assert (tdir / "Motion.txt.LEAK").exists()       # stays quarantined
    assert not (tdir / "Motion.txt").exists()
    assert any("equals the value itself" in m for m in caplog.messages)


def test_plain_yes_still_auto_fakes(tmp_path):
    # A normal name the faker CAN handle still works via "yes".
    folder = tmp_path
    td = folder / "Text Files"
    td.mkdir()
    (td / "Opp.txt.LEAK").write_text(
        "====== Page 1 ======\nGregory Yu appeared.\n", encoding="utf-8")
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Gregory Yu"], [], [], registry=reg)
    pz = P.Pseudonymizer(terms, {}, registry=reg)
    pz.apply("Gregory Yu")
    pz.write_key(folder / "pseudonym_key.xlsx", log)
    _worksheet2 = openpyxl.Workbook()
    ws = _worksheet2.active
    ws.append(["File", "Type", "Value", "Where", "Fix? (yes/no)", "Notes"])
    ws.append(["Opp.txt.LEAK", "LEAK", "Gregory Yu", "p.1", "yes", ""])
    _worksheet2.save(folder / "pdf_linker_leaks.xlsx")
    rc = P._fix_leaks_mode(folder, _args(folder), {}, log)
    assert rc == 0
    body = (td / "Opp.txt").read_text()
    assert "Gregory Yu" not in body


def test_no_leaves_nothing_to_apply(tmp_path):
    # "no" = leave it: with no yes/typed row, --fix-leaks has nothing to apply
    # and returns cleanly without delivering the still-leaking export.
    tdir = _setup(tmp_path, "no")
    rc = P._fix_leaks_mode(tmp_path, _args(tmp_path), {}, log)
    assert rc == 0
    assert (tdir / "Motion.txt.LEAK").exists()       # not delivered
    assert "M & M" in (tdir / "Motion.txt.LEAK").read_text()


def test_decisions_parse_typed_value(tmp_path):
    # Unit-level: the parser classifies a typed value as an explicit fix.
    folder = tmp_path
    _worksheet(folder, "FOXGLEN & FOXGLEN")
    d = P._pn_read_leak_decisions(folder)["m & m"]
    assert d["fix"] == "yes"
    assert d["replacement"] == "FOXGLEN & FOXGLEN"
    _worksheet(folder, "yes")
    assert P._pn_read_leak_decisions(folder)["m & m"]["replacement"] is None
    _worksheet(folder, "no")
    assert P._pn_read_leak_decisions(folder)["m & m"]["fix"] == "no"
