"""
Leak-triage worksheet: every potential leak the run flags is collected into
pdf_linker_leaks.xlsx, each row located to the printed page and gutter line,
with a blank Fix? column for the reviewer. A clean run leaves no worksheet.

Run:  cd PDF-Linker && python3 -m pytest tests/test_leak_report.py -v
"""
import logging
from pathlib import Path

import openpyxl
import pytest

import pdf_linker as P

log = logging.getLogger("test")

BODY = """====== Page 1 ======
 1  Attorneys for Defendant Travelers appeared.
 2  vs.
====== Page 2 (printed p. 5) ======
16  Defendant Travelers joined the motion. SBN 175977.
17  continuation line about Travelers again
====== Authorities cited (public verification links) ======
Donlen v. Ford Motor Co. -> http://scholar..."""


def test_locate_reports_printed_page_and_gutter_line():
    parsed = P._pn_body_lines(BODY)
    assert P._pn_locate(parsed, "Travelers") == "p.1:1, p.5:16, p.5:17"
    assert P._pn_locate(parsed, "175977") == "p.5:16"
    assert P._pn_locate(parsed, "absent-value") == "(not located)"


def test_worksheet_has_fix_column_and_severity_order(tmp_path):
    entries = [
        {"file": "Motion.txt", "type": "unscrubbed name?",
         "value": "Sunrise Motors", "where": "p.3:4"},
        {"file": "Motion.txt", "type": "LEAK", "value": "Travelers",
         "where": "p.5:16"},
        {"file": "Motion.txt", "type": "REID bar number", "value": "175977",
         "where": "p.5:16"},
    ]
    P._pn_write_leak_report(tmp_path, entries, log)
    xp = tmp_path / "pdf_linker_leaks.xlsx"
    assert xp.exists()
    rows = list(openpyxl.load_workbook(xp).active.iter_rows(values_only=True))
    assert rows[0] == ("File", "Type", "Value", "Where (page:line)",
                       "Fix? (yes/no)", "Notes")
    # real leaks first, then map-inverting REID, then ordinary review
    assert [r[1] for r in rows[1:]] == ["LEAK", "REID bar number",
                                        "unscrubbed name?"]
    # each row is located, and the Fix? column is blank for the reviewer
    assert rows[1][3] == "p.5:16"
    assert rows[1][4] in (None, "")


def test_clean_run_removes_stale_worksheet(tmp_path):
    xp = tmp_path / "pdf_linker_leaks.xlsx"
    P._pn_write_leak_report(tmp_path, [{"file": "x", "type": "LEAK",
                                        "value": "v", "where": "p.1:1"}], log)
    assert xp.exists()
    P._pn_write_leak_report(tmp_path, [], log)      # a clean re-run
    assert not xp.exists()


def test_pseudonymizer_collects_located_findings():
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Alejandro Orellana"], ["24STCV06764"], [],
                              registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    z = P.Pseudonymizer(terms, det, registry=reg)
    assert z.leak_report == []       # starts empty, accumulates during a run
