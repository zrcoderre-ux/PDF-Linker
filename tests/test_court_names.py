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
    doc = ("Hon. Alison Mackenzie presiding. Alison Mackenzie signed it. "
           "Judge Mackenzie ruled; before Mackenzie the parties argued.")
    z.register_court_names(doc)
    out = z.apply(doc)
    assert "Alison Mackenzie" not in out          # full name faked
    assert "Judge Mackenzie" not in out           # titled surname faked
    assert "before Mackenzie" in out              # BARE surname kept (no title)


def test_titled_surname_fake_matches_the_full_name_surname():
    z = _pz()
    doc = "Hon. Alison Mackenzie. Later, Judge Mackenzie issued a ruling."
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
