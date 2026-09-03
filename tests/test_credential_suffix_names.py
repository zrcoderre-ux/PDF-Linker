"""A CREDENTIAL trails a person and nothing else.

    Joe Smith, M.D.        Mary Sue, ED/UCC        Jane Cole, RN, BSN

A medical record, an expert report and a signature line name their people
this way — no role, no label, no "Declaration of" — and the composing faker
has always KEPT a degree verbatim ("<fake> <fake>, M.D."), so the shape was
understood on the way out and read by nothing on the way in. The comma plus
the credential is the corroboration, exactly as a caption's "X, an individual"
is. A KNOWN degree corroborates on its own; an UNKNOWN credential (a unit code,
a specialty no list is complete for) must be a compound, be dotted, be one of
two, or close its line — the signature shape, never prose.

Run:  cd PDF-Linker && python3 -m pytest tests/test_credential_suffix_names.py -v
"""
import pytest

import pdf_linker as P

DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}


# ── the name is read ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("line,expected", [
    ("Joe Smith, M.D., testified that the patient", ["Joe Smith"]),
    ("Mary Sue, ED/UCC", ["Mary Sue"]),
    ("Signed by Mary Sue, ED/UCC on the date shown", ["Mary Sue"]),
    ("Jane Cole, RN, BSN", ["Jane Cole"]),
    ("Robert Lee, Ph.D.", ["Robert Lee"]),
    ("Carla Ruiz, D.O.", ["Carla Ruiz"]),
    ("Ana Perez, FNP-C", ["Ana Perez"]),
    ("Priya Raman, CPA", ["Priya Raman"]),
    ("Anh Do, Esq.", ["Anh Do"]),
    # A lone unknown credential counts where it CLOSES the line.
    ("John Vance, LCSW\nThe next line.", ["John Vance"]),
    # Two people on one line: the tail is a lookahead, so the first match
    # does not consume the second name.
    ("Joe Smith, M.D., Mary Sue, ED/UCC", ["Joe Smith", "Mary Sue"]),
])
def test_a_credentialed_person_is_harvested(line, expected):
    assert P._pn_label_names(line) == expected


def test_the_lead_is_trimmed_to_the_name():
    # The run reaches back over capitalised prose and an honorific; neither
    # is part of the name the document goes on to use.
    assert P._pn_label_names("Signed By Mary Sue, ED/UCC") == ["Mary Sue"]
    assert P._pn_label_names("Dr. Joe Smith, M.D.") == ["Joe Smith"]
    # A known degree corroborates a longer name; a generic one does not.
    assert P._pn_label_names("Mary Ann Smith Jones, M.D.") == [
        "Mary Ann Smith Jones"]


# ── and what is not a credential ─────────────────────────────────────────────

@pytest.mark.parametrize("line", [
    "Silver Spring, MD 20910",              # a state, and MD is one too
    "Los Angeles, CA 90012",
    "Alder Law, P.C.",                      # a corporate suffix
    "Bank of America, N.A.",
    "Smith & Jones, LLP",
    "JUAN LOPEZ, ET AL.",
    "Article II, IV",                       # a Roman numeral is not a degree
    "Uniform Commercial Code, UCC",         # a lone acronym mid-line is prose
    "John Vance, LCSW is a therapist",
    "Housing Act, FEHA and the ADA",
    "HELEN RASHO, Plaintiff",
    "Rasho v. Quillmark, BC543295",
    "Filed January 5, 2024, AM",
    "Bob Jones, md",                        # a bare degree must be shouted
])
def test_other_things_after_a_comma_are_not(line):
    got = [n for n in P._pn_label_names(line)
           if n not in ("HELEN RASHO",)]     # the caption anchor's own
    assert got == [], got


def test_a_bare_md_after_a_comma_is_left_to_the_other_anchors():
    # "Bob Jones, MD" is a degree to a reader and Maryland to a service list,
    # and a two-word city before the comma is exactly this shape. Residual,
    # and stated: the dotted form is what this anchor reads.
    assert P._pn_label_names("Bob Jones, MD") == []
    assert P._pn_label_names("Bob Jones, M.D.") == ["Bob Jones"]


# ── end to end: bound, scrubbed, the credential left standing ────────────────

def test_the_credential_stays_and_the_person_goes():
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms([], [], [], registry=reg), DET,
                        registry=reg)
    text = ("Progress note signed by Joe Smith, M.D., and reviewed by "
            "Mary Sue, ED/UCC\nDr. Smith ordered imaging. Sue concurred.")
    z.register_label_names(text)
    out = z.apply(text)
    for real in ("Joe Smith", "Mary Sue", "Smith", "Sue"):
        assert real not in out, (real, out)
    assert "M.D." in out and "ED/UCC" in out
    reals = {str(r["real"]).lower() for r in z.records.values()}
    assert "joe smith" in reals and "mary sue" in reals


def test_a_template_party_costs_nothing_extra():
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(["Joe Smith"], [], [], registry=reg),
                        [], registry=reg)
    before = z.records[("person", "joe smith")]["fake"]
    z.register_label_names("Joe Smith, M.D.")
    assert z.records[("person", "joe smith")]["fake"] == before


# ── the declarant anchor takes the same suffixes ─────────────────────────────

@pytest.mark.parametrize("line,name", [
    ("DECLARATION OF CARLA RUIZ, D.O.", "CARLA RUIZ, D.O"),
    ("Declaration of Ravi Nair, Psy.D. in support", "Ravi Nair, Psy.D"),
    ("Declaration of Ruiz, D.O.", "Ruiz, D.O"),
])
def test_a_declarant_may_carry_any_known_suffix(line, name):
    assert name in P._pn_declarant_names(line), P._pn_declarant_names(line)
