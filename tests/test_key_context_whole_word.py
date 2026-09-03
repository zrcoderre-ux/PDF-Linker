"""A key row is quoted only where its value stands as a whole word.

A `--term` "Ken" was quoted out of "DECLARATION OF KENNETH W. BOSWORTH": the
row had matched nothing, and the Context cell read as the tool having taken
"Ken" from that sentence while the full name's own row was faked beside it.
The substring fallback exists for the worksheet's welded findings and has no
business on a key row.

Run:  cd PDF-Linker && python3 -m pytest tests/test_key_context_whole_word.py -v
"""
import pdf_linker as P

DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
ORIG = ("====== Page 1 ======\n"
        " 1  KENNETH W. BOSWORTH, an individual; and DOES 1 through 50, inclusive,\n"
        " 2  MEMORANDUM OF POINTS & AUTHORITIES; DECLARATION OF KENNETH W. BOSWORTH\n"
        " 3  The declarant states as follows. Kenneth signed the lease in March.\n")


def _pz(names, terms):
    reg = P._PnFakeRegistry()
    return P.Pseudonymizer(P._pn_build_terms(names, [], terms, registry=reg),
                           DET, registry=reg)


def test_a_term_that_matched_nowhere_is_not_quoted_out_of_a_longer_word():
    z = _pz(["Kenneth W. Bosworth"], ["Ken"])
    out = z.apply(ORIG)
    z.note_key_context(ORIG, out, source="Brief.pdf")
    assert "ken" not in z._key_context             # no whole-word "Ken" anywhere
    assert "KENNETH" in z._key_context["kenneth w. bosworth"]
    assert z._key_context["kenneth"]


def test_the_same_term_is_quoted_where_it_stands_whole():
    z = _pz(["Kenneth W. Bosworth"], ["Ken"])
    body = ORIG + " 4  Ken initialed each page.\n"
    out = z.apply(body)
    z.note_key_context(body, out, source="Brief.pdf")
    assert "Ken initialed" in z._key_context["ken"]


def test_the_worksheet_keeps_the_substring_fallback_for_a_welded_finding():
    parsed = P._pn_body_lines("====== Page 1 ======\n 1  Served on HELENRASHO at home.\n")
    assert "HELENRASHO" in P._pn_context(parsed, "Rasho")
    assert P._pn_context_hit(parsed, "Rasho", bounded_only=True) == ("", None)
