"""
A case-number stand-in is issued ONCE, across every case and every machine.

Uniqueness inside one run is the registry's job, but every folder starts a
FRESH registry, so a random draw could only ever promise uniqueness within one
case — and the space for a filing year is exactly 100,000 ("YY" + the
courthouse/division letters + five digits). That is the birthday problem with a
small denominator: 16,000 cases minted in separate runs produced 327 stand-ins
claimed by two real cases each, and one chambers-year of 300 cases carries a
36% chance of at least one. Two unrelated matters then arrive under one
case number, and a reader with both drafts cannot tell they are two cases.

So the stand-ins are handed out SEQUENTIALLY, and the counter lives on the
master workbook — the file the cross-case state already lives in, and the one
that travels between machines. What is stored is the COUNT and nothing else:
no real case number, no stand-in, no mapping.

Run:  cd PDF-Linker && python3 -m pytest tests/test_caseno_sequence.py -v
"""
import logging

import openpyxl
import pytest

import pdf_linker as P

log = logging.getLogger("test")
DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}


@pytest.fixture
def cfg(tmp_path):
    return {"master_leaks_path": str(tmp_path / "master_leaks.xlsx")}


def _run_a_case(cfg, casenos, folder):
    """One folder's run: a fresh registry seeded from the shared master."""
    reg = P._PnFakeRegistry()
    reg.caseno_seq = P._pn_read_master_caseno_seq(cfg)
    terms = P._pn_build_terms([], list(casenos), [], registry=reg)
    pz = P.Pseudonymizer(terms, DET, registry=reg)
    P._pn_note_caseno_seq(cfg, reg, folder, log)
    return pz, [t.fake for t in pz.terms if t.category == "case_number"]


# ── the property the whole thing exists for ─────────────────────────────────

def test_separate_cases_never_share_a_stand_in(cfg):
    reals = [f"{y}STCV{s:05d}" for y in (24, 25) for s in range(0, 400, 7)]
    seen = {}
    for i, real in enumerate(reals):
        _pz, fakes = _run_a_case(cfg, [real], f"Case {i}")
        assert fakes[0] not in seen, (
            f"{fakes[0]} stands for {seen.get(fakes[0])} AND {real}")
        seen[fakes[0]] = real
    assert len(seen) == len(reals)


def test_the_counter_is_what_carries_it_across_folders(cfg):
    _run_a_case(cfg, ["24STCV24253"], "A")
    assert P._pn_read_master_caseno_seq(cfg) == 1
    _run_a_case(cfg, ["24STCV31247", "25STCV14710"], "B")
    assert P._pn_read_master_caseno_seq(cfg) == 3


def test_a_run_with_no_case_number_writes_nothing(cfg, tmp_path):
    _run_a_case(cfg, [], "A")
    assert not (tmp_path / "master_leaks.xlsx").exists()


# ── what the master learns, and what it must not ───────────────────────────

def test_the_master_stores_the_count_and_no_case_number(cfg):
    _run_a_case(cfg, ["24STCV24253"], "Rasho v. Quillmark")
    wb = openpyxl.load_workbook(cfg["master_leaks_path"])
    cells = [str(c) for ws in wb.worksheets
             for r in ws.iter_rows(values_only=True)
             for c in r if c is not None]
    assert "24STCV24253" not in cells          # the real value never travels
    assert not any(c.startswith("24STCV") for c in cells)   # nor the stand-in
    assert "1" in cells or 1 in [c for c in cells]


def test_the_counter_never_moves_down(cfg):
    _run_a_case(cfg, ["24STCV24253", "24STCV31247", "25STCV14710"], "A")
    # A machine whose copy of the workbook had not synced yet.
    P._pn_write_master_caseno_seq(cfg, 1, "stale", "2026-08-27", log)
    assert P._pn_read_master_caseno_seq(cfg) == 3
    # …and the audit line still describes the run that issued that count.
    rows = P._pn_master_sheet_rows(
        P._pn_master_load(P._pn_master_path(cfg)), P._PN_MASTER_CASENO_SHEET)
    assert rows[1][2] == "A"


def test_the_keep_and_leak_sheets_are_not_disturbed(cfg):
    keep = {"labor": {"fix": "no", "fixcell": "never", "value": "Labor"}}
    P._pn_update_master_keep(cfg, keep, "A", "2026-08-27", log)
    _run_a_case(cfg, ["24STCV24253"], "A")
    assert P._pn_read_master_keep(cfg).get("labor")
    assert P._pn_read_master_caseno_seq(cfg) == 1


def test_a_missing_or_unreadable_master_starts_at_zero(cfg, tmp_path):
    assert P._pn_read_master_caseno_seq(cfg) == 0
    (tmp_path / "master_leaks.xlsx").write_bytes(b"not a workbook")
    assert P._pn_read_master_caseno_seq(cfg) == 0


# ── the shape of a sequential stand-in ─────────────────────────────────────

@pytest.mark.parametrize("real, want", [
    # The sequence run is replaced; the filing year and the courthouse and
    # division codes printed beside it are court structure, and stay.
    ("24STCV24253", "24STCV00047"),
    ("22STCP01234", "22STCP00047"),
    ("BC543295", "BC000047"),
    ("2:24-cv-01234", "2:24-cv-00047"),
    ("30-2024-01234567-CU-BC-CJC", "30-2024-00000047-CU-BC-CJC"),
])
def test_the_sequence_run_is_the_part_that_moves(real, want):
    reg = P._PnFakeRegistry()
    reg.caseno_seq = 46
    assert P._pn_fake_caseno(real, reg) == want


def test_one_number_met_twice_costs_one_tick():
    reg = P._PnFakeRegistry()
    first = P._pn_fake_caseno("24STCV24253", reg)
    assert P._pn_fake_caseno("24STCV24253", reg) == first
    assert reg.caseno_seq == 1


def test_a_stand_in_never_equals_its_own_real_value():
    """A sequence that walks the whole space steps onto some case's own number
    sooner or later, and a fake equal to its real value scrubs nothing: it
    ships the number in a "clean" export and re-flags it on every --fix-leaks
    pass. The tick is SKIPPED, not issued."""
    reg = P._PnFakeRegistry()
    reg.caseno_seq = 24252                       # the tick before the real one
    fake = P._pn_fake_caseno("24STCV24253", reg)
    assert fake != "24STCV24253"
    assert fake == "24STCV24254" and reg.caseno_seq == 24254


def test_an_outgrown_counter_falls_back_rather_than_wrapping():
    """Wrapping would re-issue numbers already out — the one thing this is for.
    100,000 cases for the five-digit LASC sequence, so it is a promise about
    centuries of filings rather than a branch anyone will meet."""
    reg = P._PnFakeRegistry()
    reg.caseno_seq = 99999
    fake = P._pn_fake_caseno("24STCV24253", reg)
    assert fake != "24STCV24253"
    assert len(fake) == len("24STCV24253")       # still the right shape


# ── the invariant a re-run depends on ──────────────────────────────────────

def test_a_reused_key_reproduces_and_spends_no_tick(cfg, tmp_path):
    """The documents already sent must come back byte for byte, so the key
    outranks the counter — and a pinned value must not burn a tick either, or
    every re-run would leak numbers out of the series."""
    pz, [fake] = _run_a_case(cfg, ["24STCV24253"], "A")
    text = "CASE NUMBER: 24STCV24253"
    first = pz.apply(text)
    key = tmp_path / "pseudonym_key.xlsx"
    pz.write_key(key, log)
    at_rest = P._pn_read_master_caseno_seq(cfg)

    reg2 = P._PnFakeRegistry()
    reg2.caseno_seq = P._pn_read_master_caseno_seq(cfg)
    terms, *_ = P._pn_load_key(key, reg2, log)
    pz2 = P.Pseudonymizer(terms, DET, registry=reg2)
    P._pn_note_caseno_seq(cfg, reg2, "A re-run", log)
    assert pz2.apply(text) == first
    reloaded = [t for t in pz2.terms if t.category == "case_number"]
    assert reloaded[0].fake == fake
    assert P._pn_read_master_caseno_seq(cfg) == at_rest


def test_a_document_harvested_number_draws_from_the_same_series(cfg):
    """The template path and the form harvest are one slot, so a folder that
    learns its case number off a CIV-100 consumes a tick like any other."""
    reg = P._PnFakeRegistry()
    reg.caseno_seq = P._pn_read_master_caseno_seq(cfg)
    pz = P.Pseudonymizer(P._pn_build_terms([], [], [], registry=reg),
                         DET, registry=reg)
    pz.register_identifiers("CASE NUMBER: 24STCV24253")
    assert reg.caseno_seq == 1
    assert next(t.fake for t in pz.terms
                if t.category == "case_number") == "24STCV00001"
