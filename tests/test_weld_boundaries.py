"""
D3 / D4 — a replacement must not reach across a printed word boundary.

Two mechanisms, one symptom: text between real words was deleted.

D3, the REDUCED pass. `_reduce_with_index` folds text to bare lower-case
alphanumerics, dropping all whitespace and punctuation; `scrub_welded` then
hunts a record's core in that reduction. The only boundary test inspected the
characters OUTSIDE the match, never inside it — so "Further, a substantial"
(whose reduction contains "hera", a four-letter party) was replaced whole and
shipped as "Furtthorpe substantial". The worst of them ate two entire lines.

D4, the TERM patterns. `person` and `entity` terms were built with
`whole_word=False`, so an OCR fragment "RS, LLC" fired inside "General Motors,
LLC" eleven times and a declarant "Tue" fired inside "Vatue".

Run:  cd PDF-Linker && python3 -m pytest tests/test_weld_boundaries.py -v
"""

import re

import pytest

import pdf_linker as P


def _pz(names, casenos=("25STCV14710",)):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), list(casenos), [], registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    return P.Pseudonymizer(terms, det, registry=reg)


# ───────────────── D3: the reduced pass eats a boundary ─────────────────────

# Every row shipped in the corpus. The party whose core is found spanning two
# printed words is named beside it.
EATEN = [
    ("Hera", "Further, a substantial factor in the harm."),
    ("Hera", "the question whether a party may recover"),
    ("Hera", "neither assumes nor delegates any duty"),
    ("Hera", "conferred with other attorneys of record"),
    ("Hera", "COUNSEL CHECKED THE RADIO AND THE HORN"),
    # "the length" / "the lender" reduce to a run containing "helen" — the
    # plaintiff's given name. These two shipped as "tbrandtgth" / "tbrandtder",
    # the worst of the set: the replacement consumed two entire lines.
    ("Helen Rasho", "counsel measured the length of the delay"),
    ("Helen Rasho", "counsel contacted the lender by telephone"),
]


@pytest.mark.parametrize("party,prose", EATEN)
def test_reduced_pass_leaves_ordinary_prose_alone(party, prose):
    z = _pz([party])
    assert z.scrub_welded(prose) == prose, (
        f"{party!r} was matched across a printed word boundary")
    assert z.surviving_reals_reduced(prose) == [], (
        f"{party!r} was REPORTED across a printed word boundary — detection "
        f"must mirror replacement or the export is quarantined uncleanably")


def test_reduced_pass_leaves_prose_alone_across_a_line_break():
    # The bracket row, which consumed a newline and two lines of text. A bare
    # line break between two words is a separator like any other.
    z = _pz(["Hera"])
    prose = "conferred with other \n* \n[ ] AMER XPRESS charges"
    assert z.scrub_welded(prose) == prose


def test_a_genuine_weld_is_still_cured():
    # The pass must keep doing its job: a column splice welds the party name to
    # its neighbour with NO separator, and that is what it exists for.
    z = _pz(["Cultureedit, LLC"])
    welded = "Defendant CULTUREEDITservice of process"
    out = z.scrub_welded(welded)
    assert "CULTUREEDIT" not in out.upper(), f"welded name survived: {out}"
    assert z.surviving_reals_reduced(welded), "detection lost the weld too"


def test_a_wrap_hyphenated_weld_is_still_cured():
    # A hyphen before a line break is a break the printer inserted INSIDE a
    # word, not a boundary between two — so it stays curable.
    z = _pz(["Cultureedit, LLC"])
    out = z.scrub_welded("Defendant CULTUREE-\nDITservice of process")
    assert "CULTUREE-\nDIT" not in out.upper(), out


def test_span_interior_test_directly():
    assert P._pn_span_is_unbroken("CULTUREEDITservice", 0, 11)
    assert P._pn_span_is_unbroken("O'Brienservice", 0, 8)
    assert not P._pn_span_is_unbroken("Further, a substantial", 4, 10)
    assert not P._pn_span_is_unbroken("the length", 1, 6)
    assert not P._pn_span_is_unbroken("the\nlength", 1, 6)


# ──────────── D4: person / entity terms without word boundaries ─────────────

def test_entity_term_does_not_fire_inside_a_longer_word():
    z = _pz(["RS, LLC"])
    out = z.apply("Plaintiff purchased the vehicle from General Motors, LLC.")
    assert "General Motors, LLC" in out, f"substring collision: {out}"


def test_person_term_does_not_fire_inside_a_longer_word():
    z = _pz(["Tue"])
    out = z.apply("Agreed Vatue of Property")
    assert out == "Agreed Vatue of Property", f"substring collision: {out}"


def test_entity_term_still_matches_a_possessive():
    # The reason `whole_word=False` was there in the first place — and it does
    # not survive inspection: `(?!\w)` is satisfied by an apostrophe.
    z = _pz(["Nationstar Mortgage, LLC"])
    out = z.apply("Defendant Nationstar Mortgage, LLC's answer is due.")
    assert "Nationstar" not in out, out
    assert out.endswith("'s answer is due."), out


def test_entity_term_still_matches_across_a_line_wrap():
    z = _pz(["Nationstar Mortgage, LLC"])
    out = z.apply("as against Nationstar\nMortgage, LLC in this action")
    assert "Nationstar" not in out, out


def test_person_term_still_matches_a_possessive():
    z = _pz(["Helen Rasho"])
    out = z.apply("Helen Rasho's declaration is attached.")
    assert "Rasho" not in out, out


# ───────── D7: a whole printed token that IS the party's name ───────────────

def test_a_whole_token_weld_is_cured_off_a_flagged_page():
    # "HELENRASHO" — the plaintiff's full name with its space gone — shipped in
    # a complaint's export while the leak scan called the file clean: the page
    # carried no other splice evidence, so it was never flagged, and the long
    # tier only ran on flagged pages. A whole printed token that reduces to
    # exactly a tracked party's name is not a coincidence.
    z = _pz(["Helen Rasho"])
    assert z.scrub_welded("HELENRASHO", spliced=False) != "HELENRASHO"
    assert z.surviving_reals_reduced("HELENRASHO", spliced=False), (
        "detection must mirror the cure or the export is uncleanable")


def test_the_whole_token_rule_does_not_fire_inside_a_longer_word():
    z = _pz(["Helen Rasho"])
    assert z.scrub_welded("HELENRASHOWITZ", spliced=False) == "HELENRASHOWITZ"


def test_the_whole_token_rule_does_not_cross_a_printed_boundary():
    # The properly-spaced form belongs to the boundary-anchored pass, which
    # yields to keeps and citations this one cannot see.
    z = _pz(["Helen Rasho"])
    text = "the helen rasho matter"
    assert z.scrub_welded(text, spliced=False) == text


def test_a_short_core_still_needs_a_hard_seam():
    # The relaxation is for the LONG tier only; a 5-char person token standing
    # as its own token is ordinary text ("Helen" in prose), not a weld.
    z = _pz(["Helen Rasho"])
    text = "Helen"
    assert z.scrub_welded(text, spliced=False) == text


# ───── an entity written without its internal punctuation still scrubs ──────

def test_a_comma_less_corporate_name_still_scrubs():
    # A filing writes it both ways. The reduced pass used to cover this by
    # accident (it drops all punctuation); now that a span holding a printed
    # boundary is refused, the variant is registered explicitly instead.
    z = _pz(["General Motors, LLC"])
    out = z.apply("Attorneys for GENERAL MOTORS LLC")
    assert "GENERAL MOTORS" not in out, out


def test_both_spellings_share_one_identity():
    z = _pz(["General Motors, LLC"])
    a = z.apply("General Motors, LLC answered.")
    b = z.apply("GENERAL MOTORS LLC answered.")
    assert a.split()[0].lower() == b.split()[0].lower(), (a, b)


def test_a_comma_inverted_person_name_invents_no_spelling():
    # A comma in a PERSON's name is structural, not decoration: "Burt, Steven
    # Wayne" is surname-first, and "Burt Steven Wayne" is a name the tool would
    # be inventing.
    reg = P._PnFakeRegistry()
    terms = []
    P._pn_append_person_terms(terms, "Burt, Steven Wayne", "spreadsheet", reg)
    people = [t.real for t in terms if t.category == "person"]
    assert people == ["Burt, Steven Wayne"], people
