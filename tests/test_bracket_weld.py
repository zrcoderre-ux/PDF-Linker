"""A [bracketed] keep-spec works on a WELDED value.

"John Doeis" — a lost space gluing the party to the next word — answered with
`[is]` always parsed correctly (fake "John Doe", keep "is") and then cured
nothing: the remainder becomes an ordinary WHOLE-WORD term, and a whole-word
pattern cannot land where the printed boundary is missing, so the export
shipped half-scrubbed ("Wemyss Doeis") while the worksheet said the bracket
was honoured.

`_pn_bracket_welds` reads the weld out of the (value, cell) pair — the
fragment's last character hard against the kept text's first, both word
characters — and `_pn_apply_weld_follows` rebuilds the fragment term with
`_pn_build_pattern(follow=…)`, the same one-run-only relaxation the declarant
harvester uses for "SmithDecl.": the term may butt against exactly that kept
text and nothing else. Applied to the FULL-name term only, never its bare
tokens, and assigned in place so replacement and the leak scans stay mirrored.

Run:  cd PDF-Linker && python3 -m pytest tests/test_bracket_weld.py -v
"""
import logging

import pytest

import pdf_linker as P

log = logging.getLogger("test")


def _pz_with_weld(fragment="Marcus Delacroix", kept="is"):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms([], [], [fragment], registry=reg)
    P._pn_apply_weld_follows(terms, {fragment.lower(): kept}, log)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    return P.Pseudonymizer(terms, det, registry=reg)


class TestWeldMap:
    def test_a_right_weld_is_read_out_of_the_pair(self):
        assert P._pn_bracket_welds("John Doeis", "[is]") == {"john doe": "is"}

    def test_a_printed_separator_is_not_a_weld(self):
        # The ordinary whole-word term matches across a space; no relaxation.
        assert P._pn_bracket_welds("Raytheon's Human Resources",
                                   "[Human Resources]") == {}

    def test_kept_text_outside_the_value_yields_nothing(self):
        assert P._pn_bracket_welds("John Doeis", "[absent]") == {}

    def test_a_left_weld_is_deliberately_not_repaired(self):
        # _pn_build_pattern has no left relaxation — the left boundary is the
        # one that stops a short name firing inside a longer word.
        assert P._pn_bracket_welds("ReJohn Doe", "[Re]") == {}

    def test_two_keeps_map_each_welded_fragment(self):
        got = P._pn_bracket_welds("John Doeis, Jane Roewas", "[is] {was}")
        assert got == {"john doe": "is", "jane roe": "was"}


class TestWeldedScrub:
    def test_the_welded_pair_is_cured_and_the_kept_text_stands(self):
        pz = _pz_with_weld()
        fake = pz.apply("Marcus Delacroix")
        out = pz.apply("Marcus Delacroixis entitled to relief. "
                       "Marcus Delacroix was served.")
        assert "Delacroix" not in out
        assert f"{fake}is entitled" in out          # the fake, the weld, the "is"
        assert f"{fake} was served" in out          # the clean occurrence too

    def test_ordinary_prose_is_untouched(self):
        pz = _pz_with_weld()
        text = "This basis is analysis of the crisis."
        assert pz.apply(text) == text

    def test_a_bare_token_never_borrows_the_relaxation(self):
        # Only the full name is left-anchored by its own first word; the bare
        # surname token must not fire inside the welded token on its own.
        pz = _pz_with_weld()
        out = pz.apply("Delacroixis alone on this line.")
        assert "Delacroixis" in out

    def test_detection_stays_mirrored(self):
        # The scan reads the same widened pattern, so a weld the substitution
        # cures is never left gating the export.
        pz = _pz_with_weld()
        out = pz.apply("Marcus Delacroixis entitled to relief.")
        assert "Marcus Delacroix" not in pz.surviving_reals(out)

    def test_only_full_name_categories_are_widened(self):
        reg = P._PnFakeRegistry()
        terms = P._pn_build_terms([], [], ["Marcus Delacroix"], registry=reg)
        before = {id(t): t.pattern for t in terms
                  if t.category not in P._PN_WELD_FOLLOW_CATS}
        P._pn_apply_weld_follows(terms, {"marcus delacroix": "is",
                                         "marcus": "is", "delacroix": "is"}, log)
        for t in terms:
            if t.category not in P._PN_WELD_FOLLOW_CATS:
                assert t.pattern == before[id(t)], t.category
