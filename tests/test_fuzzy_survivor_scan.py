"""
An OCR slip is what a survivor sweep is worst at, and worst at exactly where
it matters.

A fax-generation scan mangles precisely the values that count. The process
server's name was bound and scrubbed everywhere the page spelled it correctly,
and still shipped as "Michale Rodgers" and "Miachael Rodgers" — the exact
sweep answers "is this value still here?", and it is only as good as the
spelling it was handed. `_pn_name_variants` already registers the near
spellings the tool is CONFIDENT about (a doubled consonant, an adjacent
transposition); this is the net under them, and it REPORTS rather than
repairs, because a fuzzy substitution would rename a cited authority the
moment the OCR mangled one.

Run:  cd PDF-Linker && python3 -m pytest tests/test_fuzzy_survivor_scan.py -v
"""

import pytest

import pdf_linker as P

DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}


def _pz(*names):
    reg = P._PnFakeRegistry()
    return P.Pseudonymizer(P._pn_build_terms(list(names), [], [], registry=reg),
                           DET, registry=reg)


def _scan(z, text):
    return [s for _c, s in z.fuzzy_survivor_scan(text)]


def test_an_ocr_mangled_survivor_is_reported():
    z = _pz("Michael Rodgers")
    out = z.apply("Michael Rodgers served it. Miachael Rodgers tried again.")
    assert _scan(z, out) == ["Miachael"]


def test_the_class_says_what_the_row_is():
    z = _pz("Michael Rodgers")
    out = z.apply("Miachael Rodgers attempted service.")
    assert z.fuzzy_survivor_scan(out)[0][0] == "misspelled name?"


def test_a_correctly_spelled_name_is_scrubbed_not_reported():
    z = _pz("Michael Rodgers")
    out = z.apply("Michael Rodgers served the summons.")
    assert _scan(z, out) == []
    assert "Rodgers" not in out


def test_our_own_fake_is_never_reported():
    # A stand-in is by construction close to nothing real, but the guard is
    # explicit: reporting our own output is how a `yes` mints a fake as a real
    # value and grows a second generation of the map.
    z = _pz("Michael Rodgers")
    out = z.apply("Michael Rodgers served the summons.")
    fakes = z.known_fake_words()
    assert not {s.lower() for s in _scan(z, out)} & fakes


def test_ordinary_vocabulary_is_not_a_near_miss():
    z = _pz("Michael Rodgers")
    out = z.apply("The Motion To Quash Service of Summons was filed. "
                  "Proof of Service and Declaration attached.")
    assert _scan(z, out) == []


def test_a_cited_authority_is_masked_out():
    # A cited decision's party is preserved on purpose; reporting it as a
    # near-miss would put a row in front of the operator that a `yes` answers
    # by renaming the authority.
    z = _pz("Sumner McClanahan")
    out = z.apply("See Summers v. McClanahan (2006) 140 Cal.App.4th 403.")
    assert _scan(z, out) == []


def test_a_short_token_stays_strict():
    # Fold distance scales with length: two genuinely different short
    # surnames must never be linked.
    z = _pz("Anna Chen")
    out = z.apply("Anna Chen testified. Shen and Wren also appeared.")
    assert _scan(z, out) == []


@pytest.mark.parametrize("a,b,near", [
    ("michael", "miachael", True),      # one insertion
    ("michael", "michale", True),       # adjacent transposition
    ("ardeshirpour", "ardeshlrpour", True),   # one substitution, long token
    ("rodgers", "rodgers", True),
    ("rodgers", "bridges", False),
])
def test_the_fold_distance_matches_the_registrys(a, b, near):
    got = P._pn_edit_distance_within(a, b, P._pn_name_fold_dist(a, b),
                                     min_len=P._PN_NAME_FOLD_MIN)
    assert got is near


def test_the_index_is_rebuilt_when_terms_are_added():
    z = _pz("Helen Rasho")
    z._tracked_name_token_index()                    # warm the cache
    z.register_label_names("Michael Rodgers, a registered process server, served.")
    assert "rodgers" in z._tracked_name_token_index()[1]
