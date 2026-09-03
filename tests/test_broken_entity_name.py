"""An ENTITY's name comes apart at a kerned pair exactly as a person's does.

A delivered folder's own plaintiff was on the template, and the born-digital
export carried it as `M idland States Bank` on every page — the same kerned
"Mi" pair, so the defined short form went out as `("M idland")` too. The break
tolerance (`_pn_word_breaks`) was scoped to a bare PERSON token, so no term
could match the bank, the survivor scan (same pattern) saw nothing, and the one
thing the run said was a half-scrub row for `idland` — which the operator read
as the tool having cut the first letter off a word.

Lifted for every authoritative NAME term, full and bare, person and entity. The
screen that refuses a branch whose halves are BOTH ordinary words already
carries the entity worry, and the measurement before lifting it — 222
business-name words, 1,555 break branches, 3 MB of real filings and this
repo's own prose — found zero false matches.

Run:  cd PDF-Linker && python3 -m pytest tests/test_broken_entity_name.py -v
"""
import logging

import pytest

import pdf_linker as P

log = logging.getLogger("test")

PARTIES = ["Midland States Bank", "Marcus Delacroix"]
BROKEN = ('Plaintiff M idland States Bank ("M idland") is a lender. '
          "M idland States Bank sued Marcus Delacroix on the guaranty.")
WHOLE = ('Plaintiff Midland States Bank ("Midland") is a lender. '
         "Midland States Bank sued Marcus Delacroix on the guaranty.")


def _run(names, text, registry=None):
    reg = registry if registry is not None else P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(names, [], [], registry=reg),
                        {}, registry=reg)
    return z, z.apply(text)


def test_the_broken_full_name_is_scrubbed():
    _z, out = _run(PARTIES, BROKEN)
    assert "M idland States Bank" not in out, out
    assert "idland States" not in out, out


def test_the_broken_and_the_whole_spelling_are_one_party():
    z, broken = _run(PARTIES, BROKEN)
    _z2, whole = _run(PARTIES, WHOLE)
    fake = next(str(r["fake"]) for (c, _rl), r in z.records.items()
                if c == "entity")
    assert fake in broken and fake in whole


def test_a_whole_spelling_is_unchanged_by_the_tolerance():
    """The intact branch comes first in the alternation, so a name that never
    broke scrubs exactly as it always did. (The bare defined short form
    `("Midland")` is `register_short_names`' business, not a term here.)"""
    _z, out = _run(PARTIES, WHOLE)
    _z2, out_ref = _run(PARTIES, WHOLE)
    assert out == out_ref
    assert "Midland States Bank" not in out


def test_the_survivor_scan_uses_the_same_pattern():
    """Detection and replacement share the pattern, so a broken spelling the
    term can now match is reported by the exact sweep if it ever survives."""
    z, _out = _run(PARTIES, BROKEN)
    # The unscrubbed text, asked about directly: the broken spelling IS the
    # tracked value to the scan.
    assert "Midland States Bank" in z.surviving_reals(BROKEN)


def test_a_harvested_entity_is_not_broken():
    reg = P._PnFakeRegistry()
    terms = []
    P._pn_append_name_terms(terms, "Midland States Bank", "document", reg)
    z = P.Pseudonymizer(terms, {}, registry=reg)
    # The broken word stays broken: no tolerance for a harvested name. (The
    # bare "States" token beside it is the entity path's ordinary business.)
    assert "M idland" in z.apply("M idland States Bank")


def test_a_multi_word_term_keeps_matching_across_a_line_wrap():
    """The per-word alternation must not cost the whitespace rule: the words
    of a term still match across ANY whitespace run."""
    _z, out = _run(PARTIES, "Midland\n   States   Bank sued.")
    assert "Midland" not in out and "States   Bank" not in out, out


def test_the_break_never_reaches_ordinary_prose():
    prose = ("The mid land was surveyed by the state's bank examiner; the "
             "Statehouse Bank of the Midlands, as he called it, is a fiction.")
    _z, out = _run(PARTIES, prose)
    assert out == prose


def test_the_key_alone_reproduces_the_delivered_export(tmp_path):
    """The tolerance is asked of the row's own category and source, so a
    re-run off the key alone scrubs the broken spelling exactly as the first
    run did — the bare `("M idland")` included, which neither run touches:
    the builder makes no one-word entity token, and the loader now declines
    the per-word row `write_key` harvests (`test_entity_word_rows.py`)."""
    text = BROKEN
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(PARTIES, [], [], registry=reg),
                        {}, registry=reg)
    first = z.apply(text)
    assert "M idland States Bank" not in first
    path = tmp_path / "pseudonym_key.xlsx"
    z.write_key(path, log)
    reg2 = P._PnFakeRegistry()
    terms, *_ = P._pn_load_key(path, reg2, log)
    z2 = P.Pseudonymizer(terms, {}, registry=reg2)
    assert z2.apply(text) == first


# ── the review row, for a name NO template carries ─────────────────────────

def test_a_fragment_beside_a_fake_is_reported_with_its_lead():
    """Where the tolerance does not reach — a HARVESTED name — the half-scrub
    tier used to report the tail alone ("idland"). It now reports the broken
    spelling whole, which is what stands in the export."""
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Marcus Delacroix"], [], [], registry=reg)
    P._pn_append_name_terms(terms, "Midland States Bank", "document", reg)
    z = P.Pseudonymizer(terms, {}, registry=reg)
    out = z.apply("Marcus Delacroix and M idland met on Tuesday.")
    found = [s for _c, s in z.half_scrubbed_scan(out)]
    assert "M idland" in found, found
    assert "idland" not in found, found


def test_an_upper_case_fragment_is_reported_with_its_lead_too():
    """"MANUEL VAZQUEZ, an individual" harvested off the caption, and the
    export carrying "MANUEL VA ZQUEZ": the fuzzy sweep reported "ZQUEZ" —
    two letters short of the defendant's surname. Now "VA ZQUEZ"."""
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Weishi Yang"], [], [], registry=reg)
    P._pn_append_name_terms(terms, "Manuel Vazquez", "document", reg)
    z = P.Pseudonymizer(terms, {}, registry=reg)
    out = z.apply("DEFENDANT MANUEL VA ZQUEZ, an individual; and DOES 1")
    found = [s for _c, s in z.fuzzy_survivor_scan(out)]
    assert "VA ZQUEZ" in found, found
    assert "ZQUEZ" not in found, found


def test_a_fragment_with_no_lead_beside_it_is_still_the_fragment():
    """The conformed-stamp clip this tier was built for ("avid" for David)
    has no lead letter standing anywhere, and is reported as before."""
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Marcus Delacroix", "David Huntingdon"],
                              [], [], registry=reg)
    z = P.Pseudonymizer(terms, {}, registry=reg)
    out = z.apply("avid Huntingdon signed. Marcus Delacroix agreed.")
    found = [s for _c, s in z.half_scrubbed_scan(out)]
    assert "avid" in found, found


@pytest.mark.parametrize("text", [
    "Deborah M idland",          # the lead is a middle INITIAL, not a break
])
def test_the_lead_must_sit_on_a_word_boundary(text):
    """`_pn_broken_lead` joins only a lead that itself begins a word."""
    assert P._pn_broken_lead("x" + text, len("x" + text) - 6, "idland",
                             ["midland"]) == "M idland"
    # ...and never reaches back INTO a preceding word.
    assert P._pn_broken_lead("xM idland", 3, "idland", ["midland"]) == ""
