"""
Leak-triage worksheet: every potential leak the run flags is collected into
LEAKS.xlsx, each row located to the printed page and gutter line,
with a blank Fix? column for the reviewer. A clean run leaves no worksheet.

Column order is Value, Fix?, File, Type, Where, Notes — the flagged value and
its decision lead, the locating detail trails.

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
    xp = tmp_path / "LEAKS.xlsx"
    assert xp.exists()
    wb = openpyxl.load_workbook(xp)
    assert wb.active.title == "LEAKS"
    rows = list(wb.active.iter_rows(values_only=True))
    assert rows[0] == ("Value", "Fix? (yes/no)", "File", "Type",
                       "Where (page:line)", "Notes")
    # real leaks first, then map-inverting REID, then ordinary review
    assert [r[3] for r in rows[1:]] == ["LEAK", "REID bar number",
                                        "unscrubbed name?"]
    # each row is located, and the Fix? column is blank for the reviewer
    assert rows[1][4] == "p.5:16"
    assert rows[1][1] in (None, "")


def test_clean_run_removes_stale_worksheet(tmp_path):
    xp = tmp_path / "LEAKS.xlsx"
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


def test_decisions_read_back_from_annotated_worksheet(tmp_path):
    P._pn_write_leak_report(tmp_path, [
        {"file": "M.txt", "type": "LEAK", "value": "Travelers", "where": "p.5:16"},
        {"file": "M.txt", "type": "possible business (purchase)",
         "value": "Worthington Motors", "where": "p.9:2"},
    ], log)
    xp = tmp_path / "LEAKS.xlsx"
    wb = openpyxl.load_workbook(xp)
    ws = wb.active
    for row in ws.iter_rows(min_row=2):
        if row[0].value == "Travelers":
            row[1].value = "yes"
        if row[0].value == "Worthington Motors":
            row[1].value = "No"          # case/space-insensitive
    wb.save(xp)

    dec = P._pn_read_leak_decisions(tmp_path)
    assert dec["travelers"]["fix"] == "yes"
    assert dec["worthington motors"]["fix"] == "no"


def test_roundtrip_persists_yes_suppresses_no_and_surfaces_new(tmp_path):
    decisions = {
        "travelers": {"value": "Travelers", "type": "LEAK", "fix": "yes",
                      "notes": ""},
        "worthington motors": {"value": "Worthington Motors",
                               "type": "possible business (purchase)",
                               "fix": "no", "notes": ""},
    }
    # This run: Travelers was scrubbed (gone), Worthington still present, and a
    # brand-new undecided finding appears.
    entries = [
        {"file": "M.txt", "type": "possible business (purchase)",
         "value": "Worthington Motors", "where": "p.9:2"},
        {"file": "M.txt", "type": "unscrubbed name?", "value": "New Corp",
         "where": "p.2:1"},
    ]
    P._pn_write_leak_report(tmp_path, entries, log, decisions)
    rows = list(openpyxl.load_workbook(tmp_path / "LEAKS.xlsx")
                .active.iter_rows(values_only=True))
    by_val = {r[0]: r for r in rows[1:]}
    # a marked-yes value that's now gone is RETAINED so the term keeps applying
    assert by_val["Travelers"][1] == "yes"
    assert by_val["Travelers"][4] == P._PN_LEAK_ABSENT
    # a marked-no value is carried forward
    assert by_val["Worthington Motors"][1] == "no"
    # a new undecided finding is blank and sorts ABOVE the resolved rows
    assert by_val["New Corp"][1] in (None, "")
    order = [r[0] for r in rows[1:]]
    assert order.index("New Corp") < order.index("Worthington Motors")
    assert order.index("New Corp") < order.index("Travelers")


def test_legacy_worksheet_name_is_still_read(tmp_path):
    # A folder triaged under the old name keeps its decisions: the reader
    # falls back to pdf_linker_leaks.xlsx when LEAKS.xlsx is absent.
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(P._PN_LEAK_HEADERS))
    ws.append(["Travelers", "yes", "M.txt", "LEAK", "p.5:16", ""])
    wb.save(tmp_path / "pdf_linker_leaks.xlsx")
    dec = P._pn_read_leak_decisions(tmp_path)
    assert dec["travelers"]["fix"] == "yes"


def test_writing_migrates_off_the_legacy_name(tmp_path):
    # Once the report is rewritten, the stale old-named file is removed so the
    # operator's decisions don't split across two worksheets.
    (tmp_path / "pdf_linker_leaks.xlsx").write_bytes(b"stale")
    P._pn_write_leak_report(tmp_path, [{"file": "M.txt", "type": "LEAK",
                                        "value": "v", "where": "p.1:1"}], log)
    assert (tmp_path / "LEAKS.xlsx").exists()
    assert not (tmp_path / "pdf_linker_leaks.xlsx").exists()


def test_suppressed_value_excluded_from_gate():
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["AHC Acquisition, LLC"], ["24STCV06764"], [],
                              registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    z = P.Pseudonymizer(terms, det, registry=reg)
    z.note_leaks({"ahc acquisition, llc"})
    z.suppressed = {"ahc acquisition, llc"}
    # the gate's expression must exclude a suppressed value
    gating = {v for v in z.primary_leaks()
              if str(v).lower() not in z.suppressed}
    assert gating == set()
