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
