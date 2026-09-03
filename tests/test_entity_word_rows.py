"""A re-run off the key scrubs a bare ENTITY word exactly as the first run did.

`_pn_entity_bare` registers an entity's suffix-stripped short form only as a
MULTI-word phrase; a single leftover word is skipped on purpose, to keep
unrelated prose intact. `write_key` still harvests a row per word of the
composed name, and `_pn_load_key` read every such row back as a live term — so
a re-run scrubbed a bare "Midland" the first run left standing, and would have
faked "States" inside "United States" wherever a page capitalised it (the
corpus prunes that screen a bare business token never reach a value a key
pinned). The two ends now ask the builder's question, the rule the generic
`*-token` row already follows. The row stays for the reversal macro.

Run:  cd PDF-Linker && python3 -m pytest tests/test_entity_word_rows.py -v
"""
import logging

import openpyxl

import pdf_linker as P

log = logging.getLogger("test")
PARTIES = ["Midland States Bank", "Marcus Delacroix"]
TEXT = ("Midland States Bank sued. The Midland loan closed. Midland States "
        "moved. The United States Bankruptcy Court stayed the action. "
        "Marcus Delacroix signed.")


def _first(tmp_path):
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(PARTIES, [], [], registry=reg),
                        {}, registry=reg)
    out = z.apply(TEXT)
    z.write_key(tmp_path / "pseudonym_key.xlsx", log)
    return z, out


def _rerun(tmp_path):
    reg = P._PnFakeRegistry()
    terms, *_ = P._pn_load_key(tmp_path / "pseudonym_key.xlsx", reg, log)
    return P.Pseudonymizer(terms, {}, registry=reg)


def test_the_first_run_and_the_rerun_scrub_alike(tmp_path):
    _z, first = _first(tmp_path)
    assert _rerun(tmp_path).apply(TEXT) == first


def test_a_bare_entity_word_is_left_alone_by_both_runs(tmp_path):
    _z, first = _first(tmp_path)
    assert "The Midland loan" in first
    assert "United States Bankruptcy Court" in first
    again = _rerun(tmp_path).apply(TEXT)
    assert "The Midland loan" in again
    assert "United States Bankruptcy Court" in again


def test_the_multi_word_bare_form_is_scrubbed_by_both_runs(tmp_path):
    _z, first = _first(tmp_path)
    assert "Midland States moved" not in first
    assert "Midland States moved" not in _rerun(tmp_path).apply(TEXT)


def test_the_word_rows_stay_in_the_key_for_the_reversal(tmp_path):
    z, _first_out = _first(tmp_path)
    rp = P._PN_KEY_HEADERS.index("Replacement")
    rows = {(str(r[0]), str(r[1])): str(r[rp]) for ws in
            openpyxl.load_workbook(tmp_path / "pseudonym_key.xlsx").worksheets
            for r in ws.iter_rows(min_row=2, values_only=True) if r[1]}
    assert ("entity-token", "Midland") in rows
    fake_full = next(str(r["fake"]) for (c, _rl), r in z.records.items()
                     if c == "entity")
    assert rows[("entity-token", "Midland")] in fake_full.split()


def test_a_defined_short_form_is_scrubbed_by_both_runs(tmp_path):
    """The short form the document itself defines is a `short-name` row of
    its own, built by `register_short_names` on the first run and read back
    as a term on the re-run — unaffected by the per-word rule."""
    defined = 'Midland States Bank ("Midland") sued. Midland moved to dismiss.'
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(PARTIES, [], [], registry=reg),
                        {}, registry=reg)
    z.register_short_names(defined)
    first = z.apply(defined)
    assert "Midland moved" not in first and "Midland" not in first
    z.write_key(tmp_path / "pseudonym_key.xlsx", log)
    assert _rerun(tmp_path).apply(defined) == first
