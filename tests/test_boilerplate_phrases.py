"""
Legal-boilerplate phrases must never be treated as a real name — neither
surfaced as an unscrubbed-name finding nor captured as a judge — because they
are stock language, not people or entities ("Alleges Facts Supporting Liability
Based", "Case Assigned For All Purposes", "Delaware Limited", "Our Supreme
Court", "Unlimited Jurisdiction"). The suppression is on DETECTION only: a
genuine curated party whose name happens to contain one of these words still
scrubs from the key ("Unless a party").

Run:  cd PDF-Linker && python3 -m pytest tests/test_boilerplate_phrases.py -v
"""
import pytest

import pdf_linker as P

_BOILERPLATE = [
    "Alleges Facts Supporting Liability Based",
    "Case Assigned For All Purposes",
    "Delaware Limited",
    "Our Supreme Court",
    "Unlimited Jurisdiction",
]


@pytest.mark.parametrize("phrase", _BOILERPLATE)
def test_boilerplate_is_not_an_unscrubbed_name(phrase):
    # Even directly behind a party-role anchor (the high-recall trigger), the
    # phrase is boilerplate, so it must not be flagged for review.
    for anchor in ("Defendant", "Plaintiff"):
        text = f"{anchor} {phrase} moved for relief."
        assert P._pn_unknown_name_findings(text, set()) == [], text


@pytest.mark.parametrize("phrase", _BOILERPLATE)
def test_boilerplate_is_not_captured_as_a_judge(phrase):
    z = P.Pseudonymizer([], {}, registry=P._PnFakeRegistry())
    z.register_court_names(f"Judge {phrase} presiding over the matter.")
    assert not [k for (c, k) in z.records if c == "person"], phrase
    assert z.apply(phrase) == phrase          # left verbatim


def test_curated_party_containing_boilerplate_still_scrubs():
    # "Unless a party": the words are safe as boilerplate, but a genuine party
    # named in the key still gets faked — detection suppression never blocks a
    # curated term.
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(
        ["Delaware Widgets Limited", "Supreme Casing Company"], [], [],
        registry=reg)
    z = P.Pseudonymizer(terms, {}, registry=reg)
    for real in ("Delaware Widgets Limited", "Supreme Casing Company"):
        assert real not in z.apply(real), real
