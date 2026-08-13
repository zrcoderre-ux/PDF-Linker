"""A declarant name run must not cross a SENTENCE BOUNDARY.

`_PN_DECL_NAME_WORD` carried `.` inside its tail class, so a whole word could
swallow the period that ends a sentence and the reference harvester walked
backwards out of the declaration cite into the sentence before it. "…enforce
the Arbitration Provision. Carpenter Decl. ¶ 5" was read as a declarant named
"Provision. Carpenter".

That is not a mis-flag in a worksheet. The bare token is registered too, so one
delivered folder's key shows `Provision` replaced by a surname **321** times and
`System` **370** — 692 ordinary nouns rewritten as people, on the strength of a
handful of sentences that happened to end in front of a "Decl." (The same
harvest also caught `River`, `Cross` and `Sunlight`; those are real parties the
E-Court template registers independently, to the identical fakes, so dropping
the declarant rows costs no scrubbing.)

The triage worksheet was the visible symptom two steps downstream. A bogus row
is a PERSON row, so its fake joins `name_fake_words()` — which
`half_scrubbed_scan` scopes to people deliberately, because an entity's fake
word sits beside ordinary capitalised prose all the time. "System" -> Hartwell
put an entity-shaped stand-in in the person set, so "the solar system" became
"the solar hartwell" and every capitalised neighbour read as a half-scrubbed
pair: 33 of one folder's 54 rows were solar-financing vocabulary — "Solar",
"Energy", "Installation", "Dealer", "Capital", "Funds", "Improvement".

The period was only ever needed for an INITIAL, and a professional suffix has
its own group, so the run stops at a multi-letter word's period and yields the
declarant that is actually there.

Run:  cd PDF-Linker && python3 -m pytest tests/test_declarant_sentence_boundary.py -v
"""
import pytest

import pdf_linker as P


# ── the run stops at the end of a sentence ──────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("…enforce the Arbitration Provision. Carpenter Decl. ¶ 5.", "Carpenter"),
    ("…installed the System. Carpenter Decl. ¶ 12.", "Carpenter"),
    ("…financing from Cross River. Carpenter Decl. ¶ 3.", "Carpenter"),
    ("…marketed by Sunlight. Carpenter Decl. ¶ 8.", "Carpenter"),
    ("The panels were removed. Chung Declaration, ¶ 2.", "Chung"),
])
def test_a_sentence_end_is_not_part_of_the_declarants_name(text, expected):
    assert P._pn_declarant_ref_names(text) == [expected]


@pytest.mark.parametrize("noun", ["Provision", "System", "River", "Cross",
                                  "Sunlight", "Agreement", "Loan"])
def test_the_preceding_noun_is_never_harvested(noun):
    """Each of these was registered as a person token in a delivered key, and
    then applied to every occurrence of the ordinary noun in the folder."""
    got = P._pn_declarant_ref_names(f"…as set out in the {noun}. Carpenter "
                                    f"Decl. ¶ 5.")
    assert got == ["Carpenter"]
    assert not any(noun.lower() in n.lower() for n in got), got


# ── every legitimate shape still resolves ───────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    # An INITIAL is the one thing the period was ever needed for.
    ("Clark H. Cameron Decl. ¶ 1.", "Clark H. Cameron"),
    # …including an accented name behind one (the Alarcón truncation).
    ("Teresa C. Alarcón Decl. ¶ 7.", "Teresa C. Alarcón"),
    ("T. Richmond-McPherson Decl. ¶ 2.", "T. Richmond-McPherson"),
    ("See Smith Decl. ¶ 2.", "Smith"),
    ("Gregory Yu Decl. ¶ 4.", "Gregory Yu"),
    ("Alarcón Declaration, ¶ 4", "Alarcón"),
    # Extraction that lost the space still resolves — the one weld this
    # harvester is allowed to read.
    ("(YuDec.) at 3", "Yu"),
])
def test_a_real_declarant_reference_is_unchanged(text, expected):
    assert P._pn_declarant_ref_names(text) == [expected]


@pytest.mark.parametrize("text,expected", [
    ("Declaration of Teresa C. Alarcón in support of the motion",
     "Teresa C. Alarcón"),
    ("DECLARATION OF MICHAEL CHUNG IN SUPPORT", "MICHAEL CHUNG"),
    ("I, Clark H. Cameron, declare as follows", "Clark H. Cameron"),
])
def test_the_title_and_self_declaration_forms_are_unchanged(text, expected):
    assert expected in P._pn_declarant_names(text)


def test_a_title_after_a_sentence_end_still_names_its_declarant():
    # The title form is anchored on "Declaration of", so the sentence before it
    # was never at risk — this pins that the tightened word did not break it.
    got = P._pn_declarant_names(
        "…the Arbitration Provision. Declaration of Justin Carpenter ¶ 1.")
    assert "Justin Carpenter" in got
    assert not any("Provision" in n for n in got), got


# ── and the noun never becomes a term ───────────────────────────────────────

def test_the_noun_is_not_registered_as_a_person(monkeypatch):
    """The end-to-end consequence: with the noun harvested, every occurrence of
    it in the folder was replaced by a surname."""
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms([], [], [], registry=reg),
                        list(P._PN_DEFAULT_DETECTORS), registry=reg)
    z.register_declarant_refs(
        "Plaintiffs agreed to the Arbitration Provision. Carpenter Decl. ¶ 5. "
        "The System. Carpenter Decl. ¶ 12.")
    reals = {str(r["real"]).lower() for r in z.records.values()}
    assert "carpenter" in reals, reals
    for noun in ("provision", "system", "provision. carpenter",
                 "system. carpenter"):
        assert noun not in reals, reals
    # And the ordinary noun rides through the scrub untouched.
    out = z.apply("The System was installed under the Arbitration Provision.")
    assert out == "The System was installed under the Arbitration Provision."
