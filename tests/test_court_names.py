"""
Court personnel scrubbing, all DISCOVERED from the document (no hard-coded name):
the presiding judge (full name everywhere; bare surname only behind a title),
court staff (by role label), and the department number (consistent digit fake).

Run:  cd PDF-Linker && python3 -m pytest tests/test_court_names.py -v
"""
import re

import pytest

import pdf_linker as P


def _pz():
    return P.Pseudonymizer([], {}, registry=P._PnFakeRegistry())


def test_judge_full_name_everywhere_but_surname_only_behind_title():
    z = _pz()
    doc = ("Hon. Dana Whitaker presiding. Dana Whitaker signed it. "
           "Judge Whitaker ruled; before Whitaker the parties argued.")
    z.register_court_names(doc)
    out = z.apply(doc)
    assert "Dana Whitaker" not in out          # full name faked
    assert "Judge Whitaker" not in out           # titled surname faked
    assert "before Whitaker" in out              # BARE surname kept (no title)


def test_titled_surname_fake_matches_the_full_name_surname():
    z = _pz()
    doc = "Hon. Dana Whitaker. Later, Judge Whitaker issued a ruling."
    z.register_court_names(doc)
    out = z.apply(doc)
    m = re.search(r"Hon\. \w+ (\w+)\.", out)        # faked "First Last"
    assert m, out
    assert f"Judge {m.group(1)}" in out              # same surname behind title


def test_discovery_is_name_agnostic():
    z = _pz()
    doc = "Assigned to the Honorable Ruben Delacruz-Ortiz for all purposes."
    z.register_court_names(doc)
    assert "Ruben Delacruz-Ortiz" not in z.apply(doc)


def test_generic_captures_are_not_names():
    for doc in ["before the Honorable Court", "Judge Presiding entered an order",
                "Judge of the Superior Court"]:
        z = _pz()
        z.register_court_names(doc)
        assert z.apply(doc) == doc, doc


def test_department_number_faked_consistently_bare_number_kept():
    z = _pz()
    doc = "Dept. 515 and Department 515 and Department No. 515. Page 515 of 900."
    z.register_court_names(doc)
    out = z.apply(doc)
    nums = re.findall(r"(?:Dept\.?|Department)\s*(?:No\.?\s*)?(\d+)", out)
    assert nums and len(set(nums)) == 1 and "515" not in set(nums)
    assert "Page 515" in out                      # bare number untouched


def test_court_staff_by_role_label():
    z = _pz()
    doc = ("Judicial Assistant: Maria Sandoval\nCourt Reporter: Robert Ng\n"
           "Courtroom Clerk: David Whitfield")
    z.register_court_names(doc)
    out = z.apply(doc)
    for name in ("Maria Sandoval", "Robert Ng", "David Whitfield"):
        assert name not in out


# ─── Bug fixes: verb-swallowing, key-reuse surname rule, possessive ───────────

def test_allcaps_ruling_verb_is_not_part_of_the_name():
    # "JUDGE SMITH ORDERED THE PARTIES…" must register NO person ("SMITH
    # ORDERED" was being faked in ordinary prose); the titled surname still
    # scrubs inside the heading.
    for heading in ("JUDGE SMITH ORDERED THE PARTIES TO MEET",
                    "JUDGE SMITH OVERRULED THE OBJECTION",
                    "The Judge Whitaker Ruled Yesterday"):
        z = _pz()
        z.register_court_names(heading)
        assert not [r for (c, _k), r in z.records.items() if c == "person"], heading
        out = z.apply(heading)
        assert "SMITH" not in out and "Whitaker" not in out, out
        prose = z.apply("Smith ordered lunch. Smith overruled it.")
        assert "Smith ordered lunch" in prose and "Smith overruled it" in prose


def test_bare_surname_stays_bare_after_key_reuse(tmp_path):
    # The derived person-token key row must NOT become an unconditional term on
    # key reuse — first run and re-run must treat the bare surname identically.
    import logging
    log = logging.getLogger("test")
    z = _pz()
    doc = ("Hon. Dana Whitaker presiding. Judge Whitaker ruled. "
           "Before Whitaker, counsel argued.")
    z.register_court_names(doc)
    first = z.apply(doc)
    assert "Before Whitaker" in first
    z.write_key(tmp_path / "pseudonym_key.xlsx", log)
    reg2 = P._PnFakeRegistry()
    terms2 = P._pn_load_key(tmp_path / "pseudonym_key.xlsx", reg2, log)
    z2 = P.Pseudonymizer(terms2, {}, registry=reg2)
    reused = z2.apply(doc)
    assert reused == first                      # identical, incl. bare surname
    assert "Before Whitaker" in reused


def test_possessive_titled_form_keeps_apostrophe_and_shares_fake():
    z = _pz()
    doc = "Judge Whitaker’s ruling. Hon. Dana Whitaker."
    z.register_court_names(doc)
    out = z.apply(doc)
    m = re.search(r"Judge (\w+)’s ruling\. Hon\. \w+ (\w+)\.", out)
    assert m, out
    assert m.group(1) == m.group(2)             # same surname fake both places
    assert "Whitaker" not in out


def test_court_staff_name_before_role():
    # An LASC-generated notice signs "By: N. Lachikian, Deputy Clerk" — the
    # name BEFORE the role. The clerk is court personnel and must scrub like
    # the label-first shapes instead of riding into the review sheet as a
    # "possible person name" on every notice of appeal.
    z = _pz()
    doc = "By: N. Lachikian, Deputy Clerk\nBy: A. Latchinian, Deputy Clerk"
    z.register_court_names(doc)
    out = z.apply(doc)
    assert "Lachikian" not in out and "Latchinian" not in out
    assert "Deputy Clerk" in out                 # the role label is kept


def test_name_first_staff_shape_never_harvests_an_institution():
    z = _pz()
    doc = "Superior Court, Deputy Clerk of the County of Los Angeles"
    z.register_court_names(doc)
    assert z.apply(doc) == doc
