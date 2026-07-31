"""
A value the operator marked KEEP is present on purpose, so it is not a leak.

`surviving_reals` reported every tracked real still standing in the export,
including one a KEEP decision had deliberately left verbatim. That put a row in
LEAKS.xlsx no answer could clear: `no` is what produced it, and the durable
decision lives on the cross-folder master KEEP sheet, so consuming the local
worksheet never retired the row either — it came back every run, forever.

The suppression is scoped so the safety rule survives: a keep is RELEASED inside
a full party match (`_keep_spans`), so a person/entity/case_number real that is
still standing was faked nowhere and IS a genuine leak.

Run:  cd PDF-Linker && python3 -m pytest tests/test_kept_value_not_a_leak.py -v
"""
import logging

import pdf_linker as P

log = logging.getLogger("test")


def _pz(names):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), [], [], registry=reg)
    return P.Pseudonymizer(terms, list(P._PN_DEFAULT_DETECTORS), registry=reg)


def test_kept_domain_is_not_reported_as_a_leak():
    z = _pz(["Michael Patrick Carroll"])
    body = z.apply("Filed through filevineapp.com today.")
    assert "filevineapp.com" in z.surviving_reals("Filed through filevineapp.com")
    z.keep_soft = {"filevineapp.com"}
    assert z.surviving_reals("Filed through filevineapp.com") == []


def test_keep_strict_fragment_is_not_reported_either():
    z = _pz(["Michael Patrick Carroll"])
    z.apply("Reach us at www.LAWBROTHERS.com for details.")
    z.keep_strict = {"www.LAWBROTHERS.com"}
    assert z.surviving_reals("See www.LAWBROTHERS.com") == []


def test_a_kept_PARTY_name_is_still_a_leak():
    # The override that stops a keep leaving a real party in the clear must not
    # be undone here: a person/entity real still standing was faked nowhere.
    z = _pz(["Michael Patrick Carroll"])
    z.keep_soft = {"Michael Patrick Carroll"}
    assert "Michael Patrick Carroll" in z.surviving_reals(
        "Defendant Michael Patrick Carroll answered.")


def test_no_keeps_means_no_change_in_behaviour():
    z = _pz(["Michael Patrick Carroll"])
    assert "Michael Patrick Carroll" in z.surviving_reals(
        "Defendant Michael Patrick Carroll answered.")


# ── a keep that WINS must not be reported either (the quarantine loop) ───────

def test_a_local_bracket_keep_that_beats_a_party_match_is_not_reported():
    """`--fix-leaks: applied 3 fix(es) to 0 file(s) ... 2 file(s) still carry a
    party-name leak`, forever.

    A LOCAL bracketed keep-spec beats even a full party match — that is what
    `party_wins=False` means, and it is deliberate: the bracket already says how
    to split the name. But `_surviving_records` only skipped a kept value for
    NON-party categories, so a kept value whose record is a `person` was
    refused by the scrubber and reported by the scan. The export is quarantined,
    the operator marks the row `yes`, the fix pass changes nothing and
    re-reports it, and the folder never resolves."""
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Weishi Yang", "White"], ["26STCV08967"], [],
                              registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    z = P.Pseudonymizer(terms, det, registry=reg)
    z.keep_strict = {"White"}
    z.keep_strict_local = {"White"}
    text = "Declaration of White in support of the motion to quash."
    out = z.apply(text)
    assert out == text, "fixture must exercise a keep that WINS"
    assert z.surviving_reals(out) == [], (
        "the scan reported a value the scrubber is required to leave alone")


def test_a_keep_released_by_a_party_match_is_still_reported():
    """The safety rule is untouched: a keep YIELDS inside a full party match, so
    a party still standing there was faked nowhere and IS a leak."""
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Weishi Yang"], ["26STCV08967"], [],
                              registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    z = P.Pseudonymizer(terms, det, registry=reg)
    z.keep_soft = {"Weishi"}          # a soft keep, released in a name run
    assert z.surviving_reals("Plaintiff Weishi Yang appeared.")
