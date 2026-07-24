"""
A cross-case MASTER leak log: every flagged value accumulates into one
spreadsheet across all runs and case folders, sorted alphabetically, so a value
that keeps leaking over time is easy to spot. Opt-in (`master_leaks = on`),
relocatable (`master_leaks_path`), off by default.

Run:  cd PDF-Linker && python3 -m pytest tests/test_master_leaks.py -v
"""
import logging

import openpyxl
import pytest

import pdf_linker as P

log = logging.getLogger("test")


def _read(path):
    ws = openpyxl.load_workbook(path).active
    return [list(r) for r in ws.iter_rows(values_only=True)]


def test_disabled_by_default_but_opt_in_and_relocatable():
    assert P._pn_master_leaks_path({}) is None
    assert P._pn_master_leaks_path({"master_leaks": "off"}) is None
    assert P._pn_master_leaks_path({"master_leaks": "on"}) is not None
    p = P._pn_master_leaks_path({"master_leaks_path": r"/tmp/Master Leaks.xlsx"})
    assert str(p).endswith("Master Leaks.xlsx")   # override works even w/o on


def test_accumulates_sorted_with_times_seen(tmp_path):
    mp = tmp_path / "master.xlsx"
    P._pn_update_master_leaks(
        mp, [("Zeta Corp", "LEAK"), ("Acme LLC", "LEAK")],
        "Case Alpha", "2026-01-01", log)
    P._pn_update_master_leaks(
        mp, [("Acme LLC", "LEAK"), ("Middle Co", "unknown name?")],
        "Case Beta", "2026-02-02", log)
    rows = _read(mp)
    assert rows[0] == list(P._PN_MASTER_HEADERS)
    values = [r[0] for r in rows[1:]]
    assert values == sorted(values, key=str.lower)          # alphabetical
    acme = next(r for r in rows[1:] if r[0] == "Acme LLC")
    assert acme[2] == 2                                       # Times Seen
    assert "Case Alpha" in acme[3] and "Case Beta" in acme[3]  # both cases
    assert acme[4] == "2026-01-01" and acme[5] == "2026-02-02"  # first/last


def test_same_value_same_case_not_double_counted_across_reruns(tmp_path):
    mp = tmp_path / "master.xlsx"
    P._pn_update_master_leaks(mp, [("Acme LLC", "LEAK")], "Case A", "2026-01-01", log)
    P._pn_update_master_leaks(mp, [("Acme LLC", "LEAK")], "Case A", "2026-01-05", log)
    acme = next(r for r in _read(mp)[1:] if r[0] == "Acme LLC")
    assert acme[2] == 2                     # times-seen counts runs
    assert acme[3] == "Case A"              # but the case is listed once
    assert acme[5] == "2026-01-05"          # last-seen advanced


def test_write_leak_report_updates_master_when_enabled(tmp_path):
    folder = tmp_path / "Case Gamma"
    folder.mkdir()
    entries = [{"file": "Brief.pdf", "type": "LEAK", "value": "Zeta Corp",
                "where": "p.1:1"},
               {"file": "Brief.pdf", "type": "LEAK", "value": "Acme LLC",
                "where": "p.1:2"}]
    mp = tmp_path / "Master Leaks.xlsx"
    cfg = {"master_leaks_path": str(mp)}
    P._pn_write_leak_report(folder, entries, log, cfg=cfg)
    rows = _read(mp)
    assert [r[0] for r in rows[1:]] == ["Acme LLC", "Zeta Corp"]   # sorted


def test_no_master_written_when_disabled(tmp_path):
    folder = tmp_path / "Case Delta"
    folder.mkdir()
    entries = [{"file": "B.pdf", "type": "LEAK", "value": "Zeta Corp",
                "where": "p.1"}]
    P._pn_write_leak_report(folder, entries, log, cfg={})     # disabled
    assert not list(tmp_path.glob("*.xlsx")) or \
        all("master" not in p.name.lower() for p in tmp_path.glob("*.xlsx"))
