"""
A party name welded to a paragraph NUMBER, on a page no splice signal flags.

"MICHAEL14. While LAPD", "MARIA46. As stated" — a caps run glued to a numbered
pleading paragraph. `_page_looks_spliced` never fires on it, so the weld cure
never ran and the defendant's given name rode into the export.

The obvious repair — teach `_page_looks_spliced` that `[A-Z]{3,}\\d{2,}` is
corruption — is unusable: measured over this repo's own corpus that rule is ~90%
false positives, and they are the shapes the tool handles most (a California
case number "26STCV00400", a federal docket, a VIN, a Bates stamp "RAM000013",
a court reservation code). A false page flag is not free either — it switches on
the >=8-char reduced pass document-wide, and that tier has no boundary check.

So the SEAM is classified instead of the page. `_pn_span_has_hard_seam` asks
whether the matched span meets its neighbour across a letter<->digit transition
or a case flip, and it only ever runs where a trusted party token already
matched — so "COVID19" and "RAM000013" are untouched unless the case has a party
named Covid or Ram.

Run:  cd PDF-Linker && python3 -m pytest tests/test_hard_seam_weld.py -v
"""
import logging

import pdf_linker as P

log = logging.getLogger("test")

PARTIES = ["Maria Antonia Cruz De Amezcua", "Juan Carlos Amezcua",
           "Michael Patrick Carroll"]


def _pz(names=PARTIES):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), [], [], registry=reg)
    return P.Pseudonymizer(terms, list(P._PN_DEFAULT_DETECTORS), registry=reg)


def _rows(text):
    return [(1, [(50.0, text)])]


def test_the_page_carries_no_splice_signal():
    # The premise: this is the shape _page_looks_spliced cannot see.
    assert not P._page_looks_spliced(_rows("MARIA46. As stated in the motion."))
    assert not P._page_looks_spliced(_rows("MICHAEL14. While LAPD responded."))


def test_name_welded_to_a_paragraph_number_is_cured_unflagged():
    z = _pz()
    out = z.scrub_welded(z.apply("MARIA46. As stated. MICHAEL14. While LAPD."),
                         spliced=False)
    assert "MARIA" not in out.upper()
    assert "MICHAEL" not in out.upper()
    assert "46." in out and "14." in out       # the paragraph numbers survive


def test_case_number_bates_and_covid_are_untouched():
    z = _pz()
    text = ("Case 26STCV00400. See RAM000013 and CONFIDENTIAL0001. "
            "COVID19 protocols applied. Form CIV100 filed.")
    assert z.scrub_welded(text, spliced=False) == text
    assert z.surviving_reals_reduced(text, spliced=False) == []


def test_a_party_token_inside_an_ordinary_word_is_untouched():
    # No hard seam: "Juan|ita" and "Carroll|ton" are letter-to-letter, same
    # case. Only a lost boundary shows up as a transition.
    z = _pz()
    text = "Juanita Carrollton and Marianne testified."
    assert z.scrub_welded(text, spliced=False) == text


def test_hard_seam_helper_reads_the_boundary_not_the_page():
    assert P._pn_span_has_hard_seam("MARIA46", 0, 5)        # letter -> digit
    assert P._pn_span_has_hard_seam("JUANthe", 0, 4)        # caps -> lower
    assert not P._pn_span_has_hard_seam("Juanita", 0, 4)    # no transition
    assert not P._pn_span_has_hard_seam("Maria was", 0, 5)  # not welded at all


def test_detection_and_replacement_stay_mirrored_in_both_modes():
    for spliced in (False, True):
        z = _pz()
        welded = "MARIA46. As stated."
        assert "Maria" in z.surviving_reals_reduced(welded, spliced=spliced)
        cured = z.scrub_welded(welded, spliced=spliced)
        assert z.surviving_reals_reduced(cured, spliced=spliced) == []


def test_flagged_page_still_gets_the_full_pass():
    # The wider behaviour must be unchanged where the page IS flagged: a
    # caps-to-caps weld has no hard seam and is recoverable only there.
    z = _pz()
    assert z.scrub_welded("MICHAELCARROLL", spliced=False) == "MICHAELCARROLL"
    assert "CARROLL" not in z.scrub_welded("MICHAELCARROLL",
                                           spliced=True).upper()


def test_default_mode_is_the_full_pass():
    # scrub_welded()/surviving_reals_reduced() with no argument keep their
    # original meaning, so every existing caller is unaffected.
    z = _pz()
    assert "CARROLL" not in z.scrub_welded("MICHAELCARROLL").upper()
