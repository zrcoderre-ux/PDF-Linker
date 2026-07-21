"""
Regression tests for the holistic-review fixes: citation core (Westlaw NM
splice, short-form registry, chained sections, supra flags, Marriage short
name, JCCP, Supp.), layout/export (marker strip on the rows path, garbled
tables, user-.txt guard, stale temp, splice particles), and fix-leaks
(welded cure, filename scrub, newer-file preservation, suppression parity).

Run:  cd PDF-Linker && python3 -m pytest tests/test_holistic_fixes.py -v
"""
import logging
import re
import time
from pathlib import Path

import fitz
import openpyxl
import pytest

import pdf_linker as P

log = logging.getLogger("test")


# ── Citation core ────────────────────────────────────────────────────────────

def _pdf(folder, *lines):
    d = fitz.open()
    pg = d.new_page()
    for i, t in enumerate(lines):
        pg.insert_text((72, 100 + 40 * i), t)
    p = folder / "brief.pdf"
    d.save(str(p))
    d.close()
    return p


def test_westlaw_urls_have_no_nm_splice(tmp_path):
    p = _pdf(tmp_path, "Santana v. FCA US, LLC, 56 Cal.App.5th 334, 345 (2020).")
    P.process_pdf(p, log, provider="westlaw", extract_text=False)
    d = fitz.open(str(p))
    uris = [ln.get("uri") for pg in d for ln in pg.get_links()]
    d.close()
    assert uris and all("/NM(fitz" not in u for u in uris), uris


def test_short_form_links_reporter_cited_case(tmp_path):
    p = _pdf(tmp_path,
             "Santana v. FCA US, LLC, 56 Cal.App.5th 334, 345 (2020) held X.",
             "As explained in Santana v. FCA US, LLC, the burden shifts.")
    P.process_pdf(p, log, provider="westlaw", extract_text=False)
    d = fitz.open(str(p))
    n = sum(len(pg.get_links()) for pg in d)
    d.close()
    assert n >= 2                       # full cite AND the bare second mention


def test_chained_sections_do_not_link_prose_numbers():
    def keys(t):
        return [c["key"] for c in P.find_statute_citations(t)]
    assert keys("Code of Civil Procedure section 1005 and 16 court days"
                ) == ["CCP § 1005"]
    assert keys("Code of Civil Procedure section 998 and 1998 amendments"
                ) == ["CCP § 998"]
    # real chains still work
    assert keys("Code of Civil Procedure section 128.5 and 128.7 permit"
                ) == ["CCP § 128.5", "CCP § 128.7"]
    assert keys("Code of Civil Procedure sections 1005, 1013, and 1015 govern"
                ) == ["CCP § 1005", "CCP § 1013", "CCP § 1015"]


def test_supra_inherits_provider_flags():
    cites = P.find_all_citations(
        "Chillon v. Ford Motor Co., 2023 WL 3035369, at *4 (C.D. Cal. 2023) "
        "held X. As Chillon, supra, explained, Y.")
    supra = [c for c in cites if c.get("is_supra")]
    assert supra and supra[0]["wl_only"] is True
    assert "westlaw" in P.resolve_url(supra[0], "lexis")


def test_marriage_of_short_name_and_supra():
    assert P._short_name("In re Marriage of Smith") == "Smith"
    cs = P.find_all_citations(
        "In re Marriage of Smith (2000) 20 Cal.App.4th 100 held so. "
        "Later, Marriage of Smith, supra, the court said.")
    assert any(c.get("is_supra") for c in cs)


def test_jccp_is_not_a_ccp_statute():
    assert P.find_statute_citations(
        "Judicial Council Coordination Proceeding (J.C.C.P. 5237)") == []
    assert [c["key"] for c in P.find_statute_citations("C.C.P. 1005 applies")
            ] == ["CCP § 1005"]


def test_supp_reporter_keeps_its_space():
    cs = P.find_case_citations(
        "Orozco v. Casimiro (2004) 121 Cal.App.4th Supp. 7 applies.")
    assert cs and "Cal.App.4th Supp. 7" in cs[0]["key"]


def test_anchor_scan_is_linear():
    t0 = time.monotonic()
    P.find_case_citations("Aa v. Bb " * 4000)
    assert time.monotonic() - t0 < 1.0     # was ~4s before the window fix


# ── Layout / export ──────────────────────────────────────────────────────────

def test_garbled_heuristic_spares_numeric_tables():
    rows = "\n".join(f"{i:02d}  01/{i:02d}/2024   $1,000.50   $2,000.75   0"
                     for i in range(1, 31))
    assert P._text_looks_garbled(rows) is False


def test_splice_detector_spares_particle_names():
    rows = [(1, [(72.0, "SEAN McDONALD, ESQ. FOR DiGIORNO FOODS COMPANY")])]
    assert P._page_looks_spliced(rows) is False


def test_user_txt_beside_pdf_is_not_deleted(tmp_path):
    p = _pdf(tmp_path, "hello world prose for the export")
    notes = tmp_path / "brief.txt"
    notes.write_text("my own notes", encoding="utf-8")
    P.process_pdf(p, log)
    assert notes.read_text() == "my own notes"


def test_stale_temp_is_cleaned_and_file_processed(tmp_path):
    # Text-rich enough that _pdf_has_text_layer accepts it for export.
    lines = ["This is a full line of ordinary prose to satisfy the native "
             "text layer heuristic used by the export decision."] * 6
    p = _pdf(tmp_path, *lines)
    (tmp_path / "brief_temp.pdf").write_text("junk", encoding="utf-8")
    assert P.process_pdf(p, log) is True
    assert not (tmp_path / "brief_temp.pdf").exists()
    assert (tmp_path / "Text Files" / "brief.txt").exists()


def test_export_name_collision_gets_disambiguated(tmp_path):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["John Smith"], [], [], registry=reg)
    z = P.Pseudonymizer(terms, {}, registry=reg)
    a = P._pseudonymized_txt_path(tmp_path, Path("Smith Decl.pdf"), z, log)
    b = P._pseudonymized_txt_path(tmp_path, Path("Smith_Decl.pdf"), z, log)
    assert a != b                          # no silent overwrite
    assert P._pseudonymized_txt_path(
        tmp_path, Path("Smith Decl.pdf"), z, log) == a   # stable per source


# ── fix-leaks hardening ──────────────────────────────────────────────────────

def _mk_case(folder):
    td = folder / "Text Files"
    td.mkdir()
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Ford Motor Company"], ["24STCV24253"], [],
                              registry=reg)
    pz = P.Pseudonymizer(terms, {}, registry=reg)
    pz.apply("Ford Motor Company")
    pz.write_key(folder / "pseudonym_key.xlsx", log)
    return td


def _sheet(folder, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["File", "Type", "Value", "Where", "Fix? (yes/no)", "Notes"])
    for r in rows:
        ws.append(r)
    wb.save(folder / "LEAKS.xlsx")


class _Args:
    key = None
    term = None


def test_fix_leaks_cures_welded_leak(tmp_path):
    td = _mk_case(tmp_path)
    (td / "Motion.txt.LEAK").write_text(
        "caption FORDMOTORCOMPANYDEFENDANT welded. Gregory Yu.",
        encoding="utf-8")
    _sheet(tmp_path, [["Motion.txt.LEAK", "LEAK", "Gregory Yu", "p.1:1", "yes", ""]])
    args = _Args()
    args.key = str(tmp_path / "pseudonym_key.xlsx")
    P._fix_leaks_mode(tmp_path, args, {}, log)
    out = next(td.glob("Motion.txt*")).read_text()
    assert "FORDMOTORCOMPANY" not in out     # welded name cured, not shipped


def test_fix_leaks_scrubs_the_delivered_filename(tmp_path):
    td = _mk_case(tmp_path)
    (td / "Yu Decl ISO Opp.txt.LEAK").write_text("Gregory Yu testified.",
                                                 encoding="utf-8")
    _sheet(tmp_path, [["x", "LEAK", "Gregory Yu", "p.1:1", "yes", ""]])
    args = _Args()
    args.key = str(tmp_path / "pseudonym_key.xlsx")
    P._fix_leaks_mode(tmp_path, args, {}, log)
    names = [p.name for p in td.iterdir()]
    assert not any("Yu " in n for n in names), names   # name scrubbed too


def test_fix_leaks_keeps_newer_export_over_stale_leak(tmp_path):
    td = _mk_case(tmp_path)
    (td / "Opposition.txt.LEAK").write_text("Gregory Yu old copy.",
                                            encoding="utf-8")
    (td / "Opposition.txt").write_text("NEWER clean copy", encoding="utf-8")
    _sheet(tmp_path, [["x", "LEAK", "Gregory Yu", "p.1:1", "yes", ""]])
    args = _Args()
    args.key = str(tmp_path / "pseudonym_key.xlsx")
    P._fix_leaks_mode(tmp_path, args, {}, log)
    assert (td / "Opposition.txt").read_text() == "NEWER clean copy"
    assert not (td / "Opposition.txt.LEAK").exists()
