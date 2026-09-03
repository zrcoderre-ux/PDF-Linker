"""A bare ENTITY word is scrubbed, by the first run and the re-run alike — and
a multi-word nuclear keep is a PHRASE, not a licence for its words.

The suffix-stripped short form (`_pn_entity_bare`) skipped a single leftover
word on purpose, while `write_key` harvested a row per word of the composed
name and `_pn_load_key` read each back as a term — so a re-run scrubbed a bare
"Midland" the first run had left standing. At the owner's direction the two
ends now agree on the WIDER answer: each distinctive word of a party is its
own token (`_pn_append_entity_terms`), behind the screens every bare business
token takes.

What that costs is a word like "States" off "Midland States Bank" faked
wherever the corpus never writes it lower-case — and the operator's answer is
a phrase keep. `{United States}` keeps "United States" as a unit; it used to
put "States" itself on the keep list, so the bank shipped as "THORNFIELD
STATES BANK", half-scrubbed by a keep nobody typed.

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


def _decision(value, cell):
    return {value.lower(): {"value": value, "fixcell": cell, "fix": "no",
                            "fake_values": None, "alias": None,
                            "replacement": None, "type": "", "notes": ""}}


def _first(tmp_path, decisions=None):
    reg = P._PnFakeRegistry()
    if decisions:
        P._pn_set_keep_words(reg, decisions, log)
    z = P.Pseudonymizer(P._pn_build_terms(PARTIES, [], [], registry=reg),
                        {}, registry=reg)
    if decisions:
        z.keep_strict, z.keep_soft, z.keep_nuclear = P._pn_keep_values(decisions)
    out = z.apply(TEXT)
    z.write_key(tmp_path / "pseudonym_key.xlsx", log)
    return z, out


def _rerun(tmp_path, decisions=None):
    reg = P._PnFakeRegistry()
    if decisions:
        P._pn_set_keep_words(reg, decisions, log)
    terms, *_ = P._pn_load_key(tmp_path / "pseudonym_key.xlsx", reg, log)
    z = P.Pseudonymizer(terms, {}, registry=reg)
    if decisions:
        z.keep_strict, z.keep_soft, z.keep_nuclear = P._pn_keep_values(decisions)
    return z


# ── the bare word ───────────────────────────────────────────────────────────

def test_a_bare_entity_word_is_scrubbed_by_the_first_run():
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(PARTIES, [], [], registry=reg),
                        {}, registry=reg)
    out = z.apply(TEXT)
    assert "Midland" not in out, out
    tok = next(t for t in z.terms
               if t.category == "entity-token" and t.real == "Midland")
    full = next(t for t in z.terms if t.category == "entity")
    assert tok.fake == str(full.fake).split()[0]     # the composed word itself


def test_the_first_run_and_the_rerun_scrub_alike(tmp_path):
    _z, first = _first(tmp_path)
    assert _rerun(tmp_path).apply(TEXT) == first


def test_a_generic_or_suffix_word_is_never_a_token():
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(["General Motors, LLC", "Lenis Industries, Inc."],
                                          [], [], registry=reg), {}, registry=reg)
    bare = {t.real.lower() for t in z.terms if t.category == "entity-token"
            and len(t.real.split()) == 1}
    assert "general" not in bare and "motors" not in bare      # generic words
    assert "llc" not in bare and "inc" not in bare              # suffixes
    assert "lenis" in bare


def test_a_bare_token_is_cap_only():
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(PARTIES, [], [], registry=reg),
                        {}, registry=reg)
    assert z.apply("the midland of the county") == "the midland of the county"


# ── the phrase keep ─────────────────────────────────────────────────────────

def test_a_braced_phrase_keeps_the_phrase_and_nothing_else(tmp_path):
    keep = _decision("United States", "never")
    z, out = _first(tmp_path, keep)
    assert "United States Bankruptcy Court" in out
    assert "Midland States Bank" not in out and "Midland" not in out, out
    assert "States Bank sued" not in out, out       # the bank is faked WHOLE
    assert _rerun(tmp_path, keep).apply(TEXT) == out


def test_the_phrase_is_verbatim_inside_a_party_name():
    keep = _decision("Medical Center", "{Medical Center}")
    reg = P._PnFakeRegistry()
    P._pn_set_keep_words(reg, keep, log)
    z = P.Pseudonymizer(P._pn_build_terms(["Mulliken Medical Center",
                                           "Center Street Holdings LLC"],
                                          [], [], registry=reg), {}, registry=reg)
    z.keep_strict, z.keep_soft, z.keep_nuclear = P._pn_keep_values(keep)
    out = z.apply("Mulliken Medical Center sued Center Street Holdings LLC.")
    assert "Medical Center" in out and "Mulliken" not in out
    # "Center" standing OUTSIDE the phrase is an ordinary word of a party and
    # is faked with it.
    assert "Center Street" not in out, out


def test_a_phrase_kept_binding_is_repaired_on_load(tmp_path):
    key = tmp_path / "pseudonym_key.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Category", "Real Value", "Replacement", "Status", "Source",
               "Occurrences"])
    ws.append(["person", "Mulliken Medical Center", "Wildmere Ashcroft Center",
               "replaced", "spreadsheet", 4])
    wb.save(key)
    reg = P._PnFakeRegistry()
    P._pn_set_keep_words(reg, _decision("Medical Center", "{Medical Center}"))
    terms, _dec = P._pn_load_key(key, reg, log)
    full = next(t for t in terms if t.category == "person")
    assert full.fake == "Wildmere Medical Center"


def test_a_finding_made_of_a_kept_phrase_is_dropped_whole():
    keep = _decision("United States", "never")
    reg = P._PnFakeRegistry()
    P._pn_set_keep_words(reg, keep)
    z = P.Pseudonymizer(P._pn_build_terms(PARTIES, [], [], registry=reg),
                        {}, registry=reg)
    assert z._all_words_kept("United States")
    assert not z._all_words_kept("States")
    assert not z._all_words_kept("United States Steel")
