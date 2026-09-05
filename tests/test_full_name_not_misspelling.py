"""A near-miss standing where a FULL NAME is introduced is a different person.

"Davis Smith" is one edit from a tracked "David", and the fuzzy sweep reported
it as a misspelling of David Thomas — and the alias pre-fill would then have
answered the row with `~David`, merging a different person into the party on
the next pass. A name in a filing is written given name first, so the surname
beside the slip is the evidence: a capitalised name word that nothing tracks,
across whitespace alone, says this is somebody else. A comma between them is a
list and says nothing; a tracked surname beside it is the ordinary misspelling;
one of our own stand-ins beside it is the half-scrubbed pair the scans exist
for. Follower only, so a misspelled surname behind a nickname is still caught.

Run:  cd PDF-Linker && python3 -m pytest tests/test_full_name_not_misspelling.py -v
"""
import pytest

import pdf_linker as P

DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}


def _pz(*names):
    reg = P._PnFakeRegistry()
    return P.Pseudonymizer(P._pn_build_terms(list(names), [], [], registry=reg),
                           DET, registry=reg)


def _scan(z, text):
    return [s for _c, s in z.fuzzy_survivor_scan(z.apply(text))]


# ── a different person is not a misspelling ──────────────────────────────────

@pytest.mark.parametrize("text", [
    "David Thomas sued. Davis Smith attended the meeting.",
    # Evidence anywhere settles it: the bare later occurrence is the same
    # person the introduction named.
    "David Thomas sued. Davis Smith attended. Later Davis left.",
    # A pleading wrap keeps the gutter number between the two words.
    "David Thomas sued. Davis\n12  Smith attended.",
    "DAVID THOMAS SUED. DAVIS SMITH ATTENDED, an individual.",
])
def test_a_full_name_introduction_is_not_flagged(text):
    assert _scan(_pz("David Thomas"), text) == []


# ── and what is still a misspelling ──────────────────────────────────────────

@pytest.mark.parametrize("text,flagged", [
    # A comma between them is a LIST, not a surname.
    ("David Thomas sued. Davis, Smith and Jones attended.", "Davis"),
    # Nothing follows.
    ("David Thomas sued. Davis testified.", "Davis"),
    # The capital after it opens a new sentence.
    ("David Thomas sued. We met Davis. Wilson said no.", "Davis"),
    # The follower is vocabulary, not a name.
    ("David Thomas sued. Davis Street was closed.", "Davis"),
    ("David Thomas sued. Davis Declaration was filed.", "Davis"),
    # The follower is written lower-case elsewhere: a caps caption's word.
    ("DAVID THOMAS SUED. DAVIS TESTIFIED that he testified.", "DAVIS"),
    # The follower IS a tracked value: the ordinary misspelling.
    ("David Thomas sued. Davis Thomas attended.", "Davis"),
])
def test_without_the_marker_the_near_miss_is_still_reported(text, flagged):
    assert _scan(_pz("David Thomas"), text) == [flagged]


def test_a_tracked_surname_beside_the_slip_is_the_ordinary_misspelling():
    z = _pz("Michael Rodgers")
    got = _scan(z, "Michael Rodgers served it. Miachael Rodgers tried again.")
    assert got == ["Miachael"]


def test_follower_only_so_a_misspelled_surname_behind_a_nickname_is_caught():
    z = _pz("Michael Rodgers")
    assert _scan(z, "Michael Rodgers served it. Mike Rodgerz signed.") == [
        "Rodgerz"]


def test_our_own_stand_in_beside_it_is_the_half_scrubbed_pair():
    z = _pz("David Thomas")
    fake_surname = z.apply("David Thomas sued.").split()[1]
    assert _scan(z, f"David Thomas sued. Davis {fake_surname} attended.") == [
        "Davis"]


def test_the_rule_is_about_individuals_not_companies():
    z = _pz("Westlake Financial Services, LLC")
    got = _scan(z, "Westlake Financial Services, LLC sued. Wcstlake Village "
                   "attended.")
    assert got == ["Wcstlake"]


# ── the helper on its own ────────────────────────────────────────────────────

def test_the_marker_is_read_across_whitespace_alone():
    known, tracked, lower = set(), {"david", "thomas"}, set()
    f = P._pn_full_name_intro
    assert f("Davis Smith went", "Davis", tracked, known, lower) == "Smith"
    assert f("Davis\n12  Smith went", "Davis", tracked, known, lower) == "Smith"
    assert f("Davis, Smith went", "Davis", tracked, known, lower) == ""
    assert f("Davis. Smith went", "Davis", tracked, known, lower) == ""
    assert f("Davis; Smith went", "Davis", tracked, known, lower) == ""
    assert f("Davis Thomas went", "Davis", tracked, known, lower) == ""
    assert f("Davis smith went", "Davis", tracked, known, lower) == ""
