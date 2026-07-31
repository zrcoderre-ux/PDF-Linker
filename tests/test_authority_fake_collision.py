"""
D6 — a stand-in must never be the name of an authority the corpus cites.

"Stockton" is in `_PN_NAME_WORDS`. The fee-motion corpus cites *Stockton
Theatres, Inc. v. Palermo* (1956) 47 Cal.2d 469, and the run minted "stockton"
as a fake. The citation survived the FORWARD pass — that is what citation-span
protection is for — but `DeAnonymizeTentative` searches for FAKES
case-insensitively, so the first reversal would have rewritten the authority. A
loaded gun, not a fired one.

`_pn_guard_distinct_fake` only checks that a fake differs from its own real
value; nothing checked a fake against the document's authorities.

Run:  cd PDF-Linker && python3 -m pytest tests/test_authority_fake_collision.py -v
"""

import pytest

import pdf_linker as P


def _pz(names, casenos=("25STCV14710",)):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), list(casenos), [], registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    return P.Pseudonymizer(terms, det, registry=reg)


def _fakes(z):
    return {str(r["fake"]) for r in z.records.values()}


# ─────────────────────── harvesting the authorities ─────────────────────────

def test_authority_tokens_come_from_a_year_bearing_cite():
    got = P._pn_authority_tokens(
        "See Stockton Theatres, Inc. v. Palermo (1956) 47 Cal.2d 469, 476.")
    assert {"stockton", "palermo", "theatres"} <= got, got


def test_a_bare_v_run_is_not_harvested():
    # Harvesting from every "X v. Y" scoops up the document's OWN caption, and
    # then no party could be replaced at all.
    assert P._pn_authority_tokens(
        "HELEN RASHO v. GENERAL MOTORS, LLC\n     Defendant.") == set()


def test_corporate_furniture_is_not_an_authority_token():
    got = P._pn_authority_tokens(
        "Sanchez v. Valencia Holding Co., LLC (2015) 61 Cal.4th 899.")
    assert "llc" not in got and "co" not in got, got
    assert "valencia" in got and "sanchez" in got, got


# ──────────────────────────── the mint screen ───────────────────────────────

def test_a_reserved_word_is_never_drawn():
    reg = P._PnFakeRegistry()
    reg.avoid_words = {w.lower() for w in P._PN_NAME_WORDS[:40]}
    for i in range(20):
        fake = reg.token(f"party{i}", P._PN_NAME_WORDS, "nametok")
        assert fake.lower() not in reg.avoid_words, fake


def test_an_already_minted_collision_is_re_minted():
    # The parties are bound from the operator's template before a single
    # document has been read, so the run's most-used fakes are already drawn by
    # the time the corpus says which authorities it cites. Nothing has been
    # substituted yet, so the binding can still move for free.
    z = _pz(["Woodruff DRC, LLC", "Helen Rasho"])
    victim = sorted(_fakes(z), key=len)[-1].split()[0]
    corpus = (f"Plaintiff relies on {victim} Theatres, Inc. v. Palermo (1956) "
              f"47 Cal.2d 469, 476.")
    swaps = z.reserve_authority_names(corpus)
    assert swaps, f"{victim!r} is both a minted fake and a cited authority"
    assert not any(victim.lower() == w.lower()
                   for f in _fakes(z) for w in str(f).split()), (
        f"{victim!r} still stands as a fake after the re-mint: {_fakes(z)}")


def test_a_re_mint_keeps_the_composed_name_consistent():
    # A person's full fake is its token fakes joined; moving one word must move
    # it everywhere, or the full name and the bare surname become two people.
    z = _pz(["Helen Rasho"])
    full = z.records[("person", "helen rasho")]["fake"]
    surname = full.split()[-1]
    z.reserve_authority_names(
        f"See {surname} v. Superior Court (1998) 20 Cal.4th 1, 5.")
    new_full = z.records[("person", "helen rasho")]["fake"]
    new_surname = z.records[("person-token", "rasho")]["fake"]
    assert new_full.split()[-1] == new_surname, (full, new_full, new_surname)
    assert surname not in new_full, (full, new_full)


def test_a_reused_key_is_never_re_minted():
    # A re-run's whole job is to reproduce the delivered exports byte for byte.
    # A fake already in circulation is a worse problem to create than the one
    # being avoided, so a loaded binding only ever gets the PROSPECTIVE screen.
    z = _pz(["Helen Rasho"])
    z._loaded_reals = {"helen rasho"}
    full = z.records[("person", "helen rasho")]["fake"]
    surname = full.split()[-1]
    assert z.reserve_authority_names(
        f"See {surname} v. Superior Court (1998) 20 Cal.4th 1, 5.") == []
    assert z.records[("person", "helen rasho")]["fake"] == full
    assert surname.lower() in z.registry.avoid_words


def test_the_stockton_case_directly():
    reg = P._PnFakeRegistry()
    reg.avoid(P._pn_authority_tokens(
        "Stockton Theatres, Inc. v. Palermo (1956) 47 Cal.2d 469."))
    drawn = {reg.token(f"party{i}", P._PN_NAME_WORDS, "nametok").lower()
             for i in range(60)}
    assert "stockton" not in drawn and "palermo" not in drawn
