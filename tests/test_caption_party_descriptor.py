"""A caption states its parties with a DESCRIPTOR, and nothing was reading it.

    IRANI ROUZBAHNI, an individual; ANAHID CHAHREMANIANS, an individual,

Every other harvest anchor is a ROLE prefix ("Defendant Travelers") or a LABEL
("Attn:", "/s/"), and a caption states the role in its own column — so a party
named ONLY in a caption reached no pass at all. That is how a fee motion shipped
another matter's plaintiffs: its exhibits carry summonses and complaints from the
firm's OTHER cases, whose parties are on nobody's template. The review scans
could flag them, which is review-tier and does not gate delivery, so the export
went out carrying them.

The descriptor IS the corroboration, which is what makes an anchor this short
safe: "X, an individual" is a caption's way of saying "this is a human party",
and prose that happens to contain the words has no capitalised name in front of
the comma.

Run:  cd PDF-Linker && python3 -m pytest tests/test_caption_party_descriptor.py -v
"""
import pytest

import pdf_linker as P


# ── the caption is read ─────────────────────────────────────────────────────

@pytest.mark.parametrize("line,expected", [
    ("IRANI ROUZBAHNI, an individual; ANAHID CHAHREMANIANS, an individual,",
     ["IRANI ROUZBAHNI", "ANAHID CHAHREMANIANS"]),
    ("Helen Rasho, an individual, and DOES 1 to 50, inclusive,",
     ["Helen Rasho"]),
    # "individually" is the same statement in the other idiom.
    ("Vadim Sarkisyan, individually and as trustee, Plaintiff,",
     ["Vadim Sarkisyan"]),
])
def test_a_caption_party_is_harvested(line, expected):
    assert P._pn_label_names(line) == expected


@pytest.mark.parametrize("role", ["Plaintiff", "Defendant", "Petitioner",
                                  "Cross-Complainant"])
def test_the_role_prefix_is_trimmed_not_fatal(role):
    """The commonest caption form in California puts the role in front of the
    name. The screen that drops any piece carrying a role token refused the
    whole thing, so this shape yielded nothing at all."""
    got = P._pn_label_names(f"{role} HELEN RASHO, an individual,")
    assert got == ["HELEN RASHO"], got


def test_a_role_word_INSIDE_the_run_still_drops_it():
    """Trimming is for a LEADING role word only — a role word standing inside a
    name run is the different thing that screen exists to catch."""
    assert P._pn_label_names("HELEN Plaintiff RASHO, an individual,") == []


# ── and prose is not a caption ──────────────────────────────────────────────

@pytest.mark.parametrize("line", [
    "each plaintiff is an individual residing in the county",
    "The Plaintiff, an individual, seeks damages",
    "damages to an individual, and to the class",
    # An ENTITY descriptor is not this shape, and an entity is not a person.
    "CROSS RIVER BANK, a Delaware corporation",
    "GENERAL MOTORS LLC, a Delaware Limited Liability Company",
    # A protected locality must never become a person.
    "Los Angeles, an individual",
])
def test_prose_and_entities_are_not_harvested(line):
    assert P._pn_label_names(line) == []


def test_a_single_word_is_not_a_party():
    # A caption names a person with at least two words; one is a role or noise.
    assert P._pn_label_names("RASHO, an individual,") == []


# ── end to end: the name is bound and scrubbed, not merely flagged ──────────

def test_a_prior_matters_caption_party_is_scrubbed(caplog):
    """Before, these names were unbound: the review scans surfaced them
    review-tier, which does not gate delivery, so the export shipped them."""
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(["Vadim Sarkisyan"], [], [],
                                          registry=reg),
                        list(P._PN_DEFAULT_DETECTORS), registry=reg)
    exhibit = ("EXHIBIT 3 — SUMMONS\n"
               "IRANI ROUZBAHNI, an individual; ANAHID CHAHREMANIANS, an "
               "individual,\nPlaintiffs, v. ACME CORP.\n")
    z.register_label_names(exhibit)
    out = z.apply(exhibit + "Later, Rouzbahni objected. Chahremanians did too.")
    for real in ("ROUZBAHNI", "CHAHREMANIANS", "Rouzbahni", "Chahremanians"):
        assert real not in out, (real, out)
    # …and the binding is reversible: the key carries a row for each.
    reals = {str(r["real"]).lower() for r in z.records.values()}
    assert "irani rouzbahni" in reals and "anahid chahremanians" in reals


def test_this_cases_own_caption_costs_nothing_extra():
    """The template already names these parties, so harvesting the caption must
    reuse the SAME fake rather than mint a second one."""
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(["Vadim Sarkisyan"], [], [],
                                          registry=reg), [], registry=reg)
    before = dict(z.records[("person", "vadim sarkisyan")])
    z.register_label_names("VADIM SARKISYAN, an individual, Plaintiff,")
    assert z.records[("person", "vadim sarkisyan")]["fake"] == before["fake"]
