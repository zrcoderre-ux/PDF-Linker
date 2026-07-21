"""
The welded/reduced-substring scrub (which recovers a party name that column-
splicing welds to its neighbour) must use only NAME-type records. A structured
identifier's core is a substring of the party it belongs to — "raytheon.com"
(core "raytheoncom") nests inside "RAYTHEON COMPANY" (reduced "raytheoncompany")
and, being longer than the party core "raytheon", used to win the longest-first
pass and splice a domain fake into the party name: "RAYTHEON COMPANY" ->
"POSTBOX.ORGPANY".

Run:  cd PDF-Linker && python3 -m pytest tests/test_welded_domain_splice.py -v
"""
import logging

import pdf_linker as P

log = logging.getLogger("test")


def _pz(names):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(names, [], [], registry=reg)
    z = P.Pseudonymizer(terms, list(P._PN_DEFAULT_DETECTORS), registry=reg)
    return z


def test_domain_core_does_not_splice_into_welded_party_name():
    z = _pz(["Raytheon Company", "RTX Corporation"])
    # A bare URL in the document registers a url record for "raytheon.com".
    z.apply("See raytheon.com and www.planetdepos.com for more.")
    welded = "corporation);RAYTHEONCOMPANY(aDelawarecorporation)"
    out = z.scrub_welded(welded)
    assert "POSTBOX" not in out and ".ORG" not in out    # no domain fake spliced
    assert "RAYTHEONCOMPANY" not in out                   # the party WAS scrubbed


def test_domain_record_not_reported_as_a_reduced_survivor():
    z = _pz(["Raytheon Company"])
    z.apply("See raytheon.com for more.")
    # The url record must not be flagged as a welded survivor inside the party.
    survivors = z.surviving_reals_reduced("RAYTHEONCOMPANY")
    assert "raytheon.com" not in survivors


def test_legit_welded_firm_name_still_recovered():
    # The feature this pass exists for must keep working: a firm name welded to
    # an email local-part on a spliced caption is still found and scrubbed.
    z = _pz(["Schilleci & Tortorici, P.C."])
    welded = "AZUL@SCHILLECITORTORICILAW"
    assert "SCHILLECITORTORICI" not in z.scrub_welded(welded)
    assert z.surviving_reals_reduced(welded)              # still detected as a leak
