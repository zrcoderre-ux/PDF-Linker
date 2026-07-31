"""
One person written both ways must read as one person.

An initial is kept verbatim (faking "J." to a whole surname renders "J. Brett
Griffin" as "TOLLIVER. Forsythe Ivers"), but the spelled-out form fakes the
middle name — so "STEVEN W. BURT" came back "AMBERLY W. YEARDLEY" beside
"Steven Wayne Burt" -> "Amberly Ondine Yeardley". Two middle names for one
attorney, and the surviving "W." is the REAL middle initial.

Run:  cd PDF-Linker && python3 -m pytest tests/test_initial_agreement.py -v
"""
import logging

import pytest

import pdf_linker as P

log = logging.getLogger("test")
DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}


def _built(names):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), [], [], registry=reg)
    return reg, terms, {t.real: t.fake for t in terms if t.category == "person"}


# ── the two key rows the operator saw ───────────────────────────────────────

@pytest.mark.parametrize("order", [
    ["Steven Wayne Burt", "STEVEN W. BURT"],
    ["STEVEN W. BURT", "Steven Wayne Burt"],
])
def test_the_initial_takes_the_fake_middle_names_letter(order):
    _reg, _terms, people = _built(order)
    spelled = people["Steven Wayne Burt"]
    middle = spelled.split()[1]                      # the fake middle name
    initialled = next(v for k, v in people.items() if k.lower() != "steven wayne burt")
    assert initialled.split()[1].rstrip(".").upper() == middle[0].upper()
    # The REAL middle initial is gone from every form.
    assert not any(w.rstrip(".").upper() == "W" for v in people.values()
                   for w in v.split())


def test_both_forms_name_the_same_person():
    _reg, _terms, people = _built(["Steven Wayne Burt", "STEVEN W. BURT"])
    firsts = {v.split()[0].lower() for v in people.values()}
    lasts = {v.split()[-1].lower() for v in people.values()}
    assert len(firsts) == 1 and len(lasts) == 1


def test_a_declarant_harvested_later_is_aligned_too():
    """The signature block is read per file, long after the party template."""
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Steven Wayne Burt"], [], [], registry=reg)
    pz = P.Pseudonymizer(terms, DET, registry=reg)
    late = [t for t in P._pn_build_terms(["STEVEN W. BURT"], [], [], registry=reg)
            if t.category == "person"]
    pz._add_terms(late)
    fakes = {r["real"]: r["fake"] for r in pz.records.values()
             if r["category"] == "person"}
    assert all("W" != w.rstrip(".").upper()
               for v in fakes.values() for w in v.split())
    # the record the key is written from moved with the term
    for t in pz.terms:
        rec = pz.records.get((t.category, t.real.lower()))
        if rec is not None:
            assert rec["fake"] == t.fake


def test_a_lone_initial_with_nothing_to_learn_from_is_left_alone():
    """No spelled-out sibling — keep the old behaviour rather than invent a
    letter, since faking an initial into a whole word is the worse failure."""
    _reg, _terms, people = _built(["J. Brett Griffin"])
    assert people["J. Brett Griffin"].startswith("J. ")


def test_a_loaded_binding_is_never_realigned():
    """A reused key pins what the delivered exports already say."""
    t = P._PnTerm("person", "STEVEN W. BURT", "AMBERLY W. YEARDLEY",
                  whole_word=False, case_sensitive=False, priority=2,
                  source="declarant")
    t.loaded = True
    u = P._PnTerm("person", "Steven Wayne Burt", "Amberly Ondine Yeardley",
                  whole_word=False, case_sensitive=False, priority=2,
                  source="spreadsheet")
    u.loaded = True
    assert P._pn_align_initials([t, u]) == []
    assert t.fake == "AMBERLY W. YEARDLEY"


# ── the same disagreement in prose, from a single key row ───────────────────

def test_the_abbreviated_spelling_is_registered():
    _reg, _terms, people = _built(["Steven Wayne Burt"])
    assert people["Steven Wayne Burt"] == "Amberly Ondine Yeardley"
    assert people["Steven W. Burt"] == "Amberly O. Yeardley"
    assert people["Steven W Burt"] == "Amberly O Yeardley"


def test_every_spelling_in_the_text_agrees():
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Steven Wayne Burt"], [], [], registry=reg)
    pz = P.Pseudonymizer(terms, DET, registry=reg)
    out = pz.apply("Steven Wayne Burt signed. Steven W. Burt also signed, as "
                   "did STEVEN W BURT and Mr. Burt.")
    assert "Burt" not in out and "Steven" not in out
    assert " W. " not in out and " W " not in out
    middles = {w for w in out.replace(".", " ").split() if len(w) == 1}
    assert middles <= {"O"}


def test_the_abbreviated_spelling_is_synthetic():
    """It is a spelling this tool invented, so it earns a key row by MATCHING
    and never merely by existing (`_PnTerm.derived`)."""
    _reg, terms, people = _built(["Steven Wayne Burt"])
    byreal = {t.real: t for t in terms if t.category == "person"}
    assert byreal["Steven W. Burt"].derived is True
    assert byreal["Steven Wayne Burt"].derived is False


@pytest.mark.parametrize("name", [
    "Jane Doe",                    # no middle name
    "Burt, Steven Wayne",          # comma-inverted: the surname is not last
    "Law Offices of Scott C. Stratman",   # the middle IS an initial already
])
def test_no_spellings_invented_where_the_shape_is_wrong(name):
    _reg, _terms, people = _built([name])
    assert list(people) == [name]


def test_a_kept_middle_word_is_never_abbreviated():
    """"Law"/"of" are kept verbatim, so there is no fake letter to stand for
    them and no abbreviated spelling to invent."""
    fake, _bare = P._pn_fake_person("Law Office of Steven Burt",
                                    P._PnFakeRegistry())
    assert [r for r, _f in P._pn_initial_spellings("Law Office of Steven Burt",
                                                   fake)] == []
