"""
A name term must not carry the sentence it was standing in.

A leak-worksheet `yes` mints the whole flagged phrase as an authoritative
`--term`, and a flagged phrase is routinely an argument heading rather than a
party. One delivered key carried

    That Lin                     -> That Yardley            (124 hits)
    Lin Intended                 -> Yardley Intended
    Alleges That Lin Particpated -> Alleges That Yardley Fenwick

beside the correct `Lin -> Yardley` the case already had. The edge word is
never identifying, and keeping it costs three ways:

  * it NARROWS the match to that one phrasing;
  * it clutters the key with rows that say nothing; and
  * the reversal macro applies a multi-word row's stored casing when the
    matched text is mixed case, so "...on the ground that Lin was a sham
    defendant" comes back as "That Lin" — the document's own capitalization
    rewritten, mid-sentence, everywhere the phrase appeared.

Trimmed, the row is `Lin -> Yardley` and the OUTPUT TEXT IS UNCHANGED: the edge
word was being mapped to itself anyway, so dropping it removes a constraint on
matching, never a substitution.

Run:  cd PDF-Linker && python3 -m pytest tests/test_edge_vocabulary_terms.py -v
"""

import pytest

import pdf_linker as P

DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}


def _named(term):
    reg = P._PnFakeRegistry()
    ts = P._pn_build_terms([], [], [term], registry=reg)
    return {t.real for t in ts if t.category in ("person", "entity")}


# ─────────────────── the sentence is trimmed off a person ───────────────────

@pytest.mark.parametrize("raw,want", [
    ("That Lin", "Lin"),
    ("Alleges That Lin Particpated", "Lin Particpated"),
    ("Lin Intended", "Lin Intended"),          # "intended" is not gazetteer'd
    ("That David Mandel", "David Mandel"),
])
def test_edge_vocabulary_is_trimmed(raw, want):
    assert P._pn_trim_edge_vocabulary(raw) == want


def test_the_term_that_gets_built_is_the_core():
    assert _named("That Lin") == {"Lin"}


def test_a_real_name_is_never_shortened():
    for raw in ("Nicolas Lin", "David Mandel", "Lin Kuan Liang Nicolas"):
        assert P._pn_trim_edge_vocabulary(raw) == raw


def test_a_name_that_is_all_vocabulary_keeps_it():
    # Nothing distinctive would be left, so the value is passed through and
    # the ordinary screens decide it.
    for raw in ("That Which", "The Same"):
        assert P._pn_trim_edge_vocabulary(raw) == raw


def test_a_common_word_surname_is_not_trimmed():
    # Green, West, Price and Day are real surnames; the trim must not eat one.
    for raw in ("Green Mandel", "West Mandel", "Mandel Day"):
        assert P._pn_trim_edge_vocabulary(raw) == raw


# ─────────────────── an ENTITY keeps its whole name ─────────────────────────

@pytest.mark.parametrize("raw", [
    "Service by Medallion, Inc.",
    "General Motors, LLC",
    "The Green Company",
    "LAW OFFICES OF SCOTT STRATMAN",
])
def test_an_entity_name_is_never_trimmed(raw):
    # An entity's leading word is routinely part of its identity AND routinely
    # ordinary vocabulary. A person's name does not begin with a conjunction.
    assert raw in _named(raw), _named(raw)


def test_firm_furniture_survives_on_the_person_path_too():
    # "LAW OFFICES OF" is kept verbatim by the composing faker on purpose.
    assert P._pn_trim_edge_vocabulary("LAW OFFICES OF SCOTT STRATMAN") == \
        "LAW OFFICES OF SCOTT STRATMAN"


# ─────────────────── the output text does not change ────────────────────────

def test_the_export_reads_the_same_and_keeps_its_own_capitalisation():
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms([], [], ["That Lin"], registry=reg),
                        DET, registry=reg)
    src = ("on the ground that Lin was a sham defendant. The Complaint "
           "alleges that Lin made it. That Lin delivered the repudiation.")
    out = z.apply(src)
    assert "Lin" not in out                      # the name is still scrubbed
    assert "on the ground that Yardley" in out   # lowercase "that" preserved
    assert "That Yardley delivered" in out       # sentence-initial one too


def test_one_row_instead_of_a_row_per_phrasing():
    # Every phrasing the heading happened to use collapses onto one binding.
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms([], [], ["That Lin", "Alleges That Lin", "Lin"],
                              registry=reg)
    named = {t.real for t in terms if t.category == "person"}
    assert named == {"Lin"}, named
