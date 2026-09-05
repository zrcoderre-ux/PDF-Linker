"""A party of THIS case is scrubbed even when a cited decision shares it.

General Motors was the defendant of a Song-Beverly fee batch AND the defendant
of *Lukather v. General Motors LLC* (2010) 181 Cal.App.4th 1041, which the fee
motion cited. Every harvested spelling of the party was dropped by
`prune_authority_party_terms` on the strength of that citation, so the name
shipped in the caption, the attorney line and every billing entry of four
exports — with no LEAK reported, since a term never built is invisible to the
survivor scan too. (The short form the brief defined, "GM", HAD been bound off
the parent before the prune ran, so the exports read "counsel to General
Motors LLC ("HQ")" — half of one party.)

The prune is right about Angela White, who is named in the prose of a motion
DISCUSSING *Kremerman v. White*. What separates the two is POSITION: a filing
states its own parties in the attorney line, the Doe-closed caption roster, the
caption descriptor and the possessive filing title, and a cited decision's
party never stands in any of them (`_PN_CASE_PARTY_SITES`). The citation keeps
its span protection either way; the spare buys the name faked everywhere else.

Run:  cd PDF-Linker && python3 -m pytest tests/test_case_party_authority_spare.py -v
"""
import logging

import pytest

import pdf_linker as P

log = logging.getLogger("test")

CITE = "Lukather v. General Motors LLC (2010) 181 Cal.App.4th 1041, 1049"


def _pz(names=()):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), [], [], registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    return P.Pseudonymizer(terms, det, registry=reg)


def _learn(z, text):
    P._pn_learn_from_text(z, text, "Motion")
    return z


BATCH = (
    "Attorneys for Defendant,\n"
    "    GENERAL MOTORS LLC\n"
    "HAVERFORD AYLESWORTH,                   Case No: 24STCV32649\n"
    "               Plaintiff,\n"
    "      vs.\n"
    "GENERAL MOTORS LLC; and DOES 1          Complaint Filed: December 11, 2024\n"
    "through 10, inclusive,\n"
    "               Defendants.              GENERAL MOTORS LLC’S\n"
    "                                        OPPOSITION TO PLAINTIFF’S MOTION\n"
    "Defendant General Motors, LLC made an oral motion to dismiss. "
    f"The failure to act in good faith is sanctionable. {CITE}; "
    "Kirzhner v. Mercedes-Benz USA, LLC (2020) 9 Cal.5th 966, 972. "
    "In Lukather, General Motors LLC did not act in good faith for two "
    "months. Attorney for General Motors LLC\n"
)


def test_the_reported_batch_scrubs_its_defendant_and_keeps_the_cite():
    z = _learn(_pz(["Haverford Aylesworth"]), BATCH)
    z.prune_citation_only_terms(BATCH)
    dropped = z.prune_authority_party_terms(BATCH, log)
    assert not any("general motors" in d.lower() for d in dropped), dropped
    out = z.apply(BATCH)
    assert CITE in out, out
    body = out.replace(CITE, "")
    assert "General Motors" not in body and "GENERAL MOTORS" not in body, out
    # …and the survivor scan agrees the caption is clean.
    assert not any("general motors" in s.lower()
                   for s in z.surviving_reals(out))


def test_the_spared_name_is_named_in_the_log(caplog):
    z = _learn(_pz(["Haverford Aylesworth"]), BATCH)
    with caplog.at_level(logging.INFO):
        z.prune_authority_party_terms(BATCH, log)
    # Case-insensitive: the spelling the log names is whichever the harvest
    # registered first, and the comma-less caps form of the attorney line
    # ("GENERAL MOTORS LLC") is a harvest of its own now.
    assert any("party of THIS case" in r.message
               and "general motors" in r.message.lower()
               for r in caplog.records), [r.message for r in caplog.records]


def test_a_cited_decisions_party_named_only_in_prose_is_still_dropped():
    """The Angela White case: named throughout the DISCUSSION of the decision,
    in no party position of this case. Unchanged."""
    z = _pz(["Weishi Yang", "Ashley Liu"])
    fake = P._pn_fake_person("Angela White", z.registry)[0]
    z._add_terms([P._PnTerm("person", "Angela White", fake, whole_word=True,
                            case_sensitive=False, priority=2,
                            source="document")])
    motion = ("Defendant relies on Kremerman v. White (2021) 71 Cal.App.5th "
              "358. In that case Defendant White had closed her mailbox, and "
              "Angela White never received the summons.")
    assert "Angela White" in z.prune_authority_party_terms(motion, log)


def test_a_party_position_inside_the_citation_itself_proves_nothing():
    """The evidence is read off the CITATION-MASKED corpus, so a decision
    whose case name happens to carry a party shape cannot corroborate its
    own party."""
    z = _pz(["Weishi Yang"])
    fake = P._pn_fake_entity("Acme Widgets, Inc.", z.registry)
    z._add_terms([P._PnTerm("entity", "Acme Widgets, Inc.", fake,
                            whole_word=True, case_sensitive=False,
                            priority=2, source="document")])
    motion = ("See Doe v. Acme Widgets, Inc., a Delaware corporation (2019) "
              "40 Cal.App.5th 200. The Acme Widgets, Inc. decision controls.")
    assert "Acme Widgets, Inc." in z.prune_authority_party_terms(motion, log)


@pytest.mark.parametrize("site", [
    "Attorneys for Defendant Acme Widgets, Inc.",
    "Attorney of record for\nAcme Widgets, Inc.",
    "ACME WIDGETS, INC.; and DOES 1 through 20, inclusive,",
    "Acme Widgets, Inc., a Delaware corporation,",
    "Acme Widgets, Inc., an individual,",
    "ACME WIDGETS, INC.’S REPLY IN SUPPORT OF ITS MOTION",
])
def test_each_party_position_spares_the_name(site):
    z = _pz(["Weishi Yang"])
    fake = P._pn_fake_entity("Acme Widgets, Inc.", z.registry)
    z._add_terms([P._PnTerm("entity", "Acme Widgets, Inc.", fake,
                            whole_word=True, case_sensitive=False,
                            priority=2, source="document")])
    # A sentence between the site and the cite, because the citation parser
    # walks BACK over a case name and would otherwise take the site's own
    # line into the protected span — which the mask then blanks.
    motion = (f"{site}\nThe court has ruled on this before. See Doe v. Acme "
              "Widgets, Inc. (2019) 40 Cal.App.5th 200, 210.")
    assert z.prune_authority_party_terms(motion, log) == []


def test_a_bare_role_prefix_is_not_a_party_position():
    """"Defendant White" is exactly how a brief discusses the facts of the
    case it cites, so a role prefix alone spares nothing."""
    z = _pz(["Weishi Yang"])
    fake = P._pn_fake_entity("Acme Widgets, Inc.", z.registry)
    z._add_terms([P._PnTerm("entity", "Acme Widgets, Inc.", fake,
                            whole_word=True, case_sensitive=False,
                            priority=2, source="document")])
    motion = ("Defendant Acme Widgets, Inc. moved to dismiss in Doe v. Acme "
              "Widgets, Inc. (2019) 40 Cal.App.5th 200.")
    assert "Acme Widgets, Inc." in z.prune_authority_party_terms(motion, log)


def test_every_spelling_of_a_spared_name_is_spared_with_it():
    """Decided on the full name and inherited by everything composed from its
    words: the comma-less spelling `_pn_depunct_spelling` registers, and any
    bare token (none here — "General" and "Motors" are both generic words,
    so the party has no bare token to begin with)."""
    z = _learn(_pz(["Haverford Aylesworth"]), BATCH)
    z.prune_authority_party_terms(BATCH, log)
    reals = {t.real.lower() for t in z.terms}
    assert {"general motors llc", "general motors, llc"} <= reals, sorted(reals)


def test_a_spared_names_tokens_ride_with_it():
    z = _pz(["Weishi Yang"])
    terms = []
    P._pn_append_name_terms(terms, "Lukather Widgets, Inc.", "document",
                            z.registry)
    z._add_terms(terms)
    assert any(t.category == "entity-token" and t.real == "Lukather Widgets"
               for t in z.terms), [(t.category, t.real) for t in z.terms]
    motion = ("LUKATHER WIDGETS, INC.; and DOES 1 through 10, inclusive,\n"
              "The court has ruled on this before. See Doe v. Lukather "
              "Widgets, Inc. (2019) 40 Cal.App.5th 200, 210.")
    assert z.prune_authority_party_terms(motion, log) == []
    assert any(t.category == "entity-token" and t.real == "Lukather Widgets"
               for t in z.terms)
