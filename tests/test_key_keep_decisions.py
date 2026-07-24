"""
KEEP / KEEP-PART edits typed into the pseudonym key's Replacement column.

Sometimes the pseudonym_key.xlsx itself carries a mistake that never surfaced as
a leak, so there is no LEAKS row to correct it on. The operator can fix it in
place, in the key's Replacement column, with the same vocabulary the LEAKS Fix?
column accepts:
  * 'no'          -> leave this Real Value verbatim (do not fake it), and
  * '[bracketed]' -> keep the bracketed part verbatim, auto-fake the rest.
Both build no faking term; the decision is applied (keep-protection / fragment
faking), persisted to LEAKS.xlsx, and recorded in the master leak log.

Run:  cd PDF-Linker && python3 -m pytest tests/test_key_keep_decisions.py -v
"""
import importlib.util
import logging
from pathlib import Path

import openpyxl
import pytest

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pdf_linker", _ROOT / "pdf_linker.py")
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)

log = logging.getLogger("test")
DET = {k: pl._PN_DETECTORS[k] for k in pl._PN_DEFAULT_DETECTORS}
_HDR = ["Category", "Real Value", "Replacement", "Status", "Source", "Occurrences"]


def _write_key(path, rows):
    """rows: list of (category, real, replacement)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(_HDR)
    for cat, real, repl in rows:
        ws.append([cat, real, repl, "replaced", "spreadsheet", 1])
    wb.save(path)
    return path


# ── _pn_load_key parses the control words ────────────────────────────────────

def test_load_key_parses_no(tmp_path):
    kp = _write_key(tmp_path / "pseudonym_key.xlsx",
                    [("person", "Acme Holdings", "no")])
    reg = pl._PnFakeRegistry()
    terms, decisions = pl._pn_load_key(kp, reg, log)
    assert terms == []                                   # no faking term built
    d = decisions["acme holdings"]
    assert d["fix"] == "no" and d["type"] == "KEEP"


def test_load_key_parses_bracket(tmp_path):
    kp = _write_key(tmp_path / "pseudonym_key.xlsx",
                    [("entity", "Raytheon Human Resources", "[Human Resources]")])
    reg = pl._PnFakeRegistry()
    terms, decisions = pl._pn_load_key(kp, reg, log)
    d = decisions["raytheon human resources"]
    assert d["type"] == "KEEP-PART" and d["fix"] == "yes"
    assert d["fake_values"] == ["Raytheon"]              # the non-kept fragment


def test_load_key_normal_replacement_unchanged(tmp_path):
    kp = _write_key(tmp_path / "pseudonym_key.xlsx",
                    [("person", "Jane Doe", "Keswick Bexley")])
    reg = pl._PnFakeRegistry()
    terms, decisions = pl._pn_load_key(kp, reg, log)
    assert decisions == {}                               # not a control word
    assert any(t.real == "Jane Doe" and t.fake == "Keswick Bexley" for t in terms)


# ── keep_values actually prevents faking ─────────────────────────────────────

def test_keep_values_blocks_a_term(tmp_path):
    reg = pl._PnFakeRegistry()
    terms = pl._pn_build_terms(["Acme Holdings"], [], [], registry=reg)
    pz = pl.Pseudonymizer(terms, DET, registry=reg)
    # Without protection the term fakes it.
    assert "Acme Holdings" not in pz.apply("We sued Acme Holdings today.")
    # With protection the exact value is left verbatim.
    pz2 = pl.Pseudonymizer(terms, DET, registry=pl._PnFakeRegistry())
    pz2.keep_values = {"Acme Holdings"}
    assert "Acme Holdings" in pz2.apply("We sued Acme Holdings today.")


def test_keep_values_blocks_a_detector(tmp_path):
    reg = pl._PnFakeRegistry()
    pz = pl.Pseudonymizer([], DET, registry=reg)
    pz.keep_values = {"info@acme.com"}
    out = pz.apply("Contact info@acme.com for details.")
    assert "info@acme.com" in out


# ── end-to-end through the reuse path (main) with a real PDF ─────────────────

def _make_pdf(path, lines):
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    y = 100
    for ln in lines:
        page.insert_text((72, y), ln, fontsize=11)
        y += 24
    doc.save(path)
    doc.close()


def _run(folder, monkeypatch, key):
    import sys
    monkeypatch.setattr(sys, "argv",
                        ["pdf_linker.py", str(folder), "--key", str(key)])
    pl.main()


def test_key_no_keeps_value_in_export(tmp_path, monkeypatch):
    _make_pdf(tmp_path / "Motion.pdf",
              ["Plaintiff Acme Holdings and Jane Roe appear.",
               "Acme Holdings is a party."])
    key = _write_key(tmp_path / "pseudonym_key.xlsx",
                     [("entity", "Acme Holdings", "no"),
                      ("person", "Jane Roe", "Keswick Bexley")])
    _run(tmp_path, monkeypatch, key)

    txt = "\n".join(p.read_text() for p in (tmp_path / "Text Files").glob("*.txt"))
    assert "Acme Holdings" in txt          # marked 'no' — kept verbatim
    assert "Jane Roe" not in txt           # normal binding still fakes


def test_key_no_is_written_to_leaks_and_master(tmp_path, monkeypatch):
    _make_pdf(tmp_path / "Motion.pdf", ["Acme Holdings appears here."])
    key = _write_key(tmp_path / "pseudonym_key.xlsx",
                     [("entity", "Acme Holdings", "no")])
    # Point the master log at a file inside tmp so the test is self-contained.
    master = tmp_path / "master_leaks.xlsx"
    monkeypatch.setattr(pl, "_pn_master_leaks_path", lambda cfg: master)
    _run(tmp_path, monkeypatch, key)

    # LEAKS.xlsx carries the decision (Fix? = no) so it round-trips.
    leaks = tmp_path / "LEAKS.xlsx"
    assert leaks.is_file()
    rows = list(openpyxl.load_workbook(leaks).active.iter_rows(values_only=True))
    hdr = [str(h).lower() if h else "" for h in rows[0]]
    vi, fi = hdr.index("value"), next(i for i, h in enumerate(hdr)
                                      if h.startswith("fix?"))
    kept = [r for r in rows[1:] if str(r[vi]) == "Acme Holdings"]
    assert kept and str(kept[0][fi]).strip().lower() == "no"

    # Master log recorded it as a KEEP.
    assert master.is_file()
    mrows = list(openpyxl.load_workbook(master).active.iter_rows(values_only=True))
    assert any(str(r[0]) == "Acme Holdings" and str(r[1]) == "KEEP"
               for r in mrows[1:])


def test_key_bracket_keeps_part_fakes_rest(tmp_path, monkeypatch):
    _make_pdf(tmp_path / "Motion.pdf",
              ["In this action the Raytheon Human Resources department "
               "responded to",
               "the plaintiff's written discovery requests within the time "
               "allowed,",
               "and produced the documents that the parties had agreed were "
               "relevant."])
    key = _write_key(tmp_path / "pseudonym_key.xlsx",
                     [("entity", "Raytheon Human Resources", "[Human Resources]")])
    _run(tmp_path, monkeypatch, key)

    txt = "\n".join(p.read_text() for p in (tmp_path / "Text Files").glob("*.txt"))
    assert "Human Resources" in txt        # bracketed part kept
    assert "Raytheon" not in txt           # the rest is faked
