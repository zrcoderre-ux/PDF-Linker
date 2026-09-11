"""A Judicial Council form id is never rewritten, not even a piece of one.

`_pn_is_never_fake` has always refused to build a TERM for "MC-025"; nothing
stopped a shorter term matching INSIDE one. A term matches whole words and a
hyphen is no word character, so a two-letter entity acronym is a whole-word
match in "MC-025" — and a delivered cause-of-action attachment shipped footed
"NG-025", the form no longer saying which form it is, with the SAME occurrence
the whole of the evidence that minted the acronym.
"""
import re

import pytest

import pdf_linker as P


FORM_BODY = ("MC-025\n"
             "SHORT TITLE: CASE NUMBER.\n"
             "Mogharebi Capital, LLC et al v. HALLMARK 75 ONTARIO, LLC\n"
             "ATTACHMENT (Number): 2\n")


def _pz(names):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), [], [], registry=reg)
    return P.Pseudonymizer(terms, {}, registry=reg), reg


class TestTheSpanShape:
    def test_it_matches_the_forms_the_packet_carries(self):
        for form in ("MC-025", "CIV-100", "JUD-100", "SUM-100", "FL-150",
                     "PLD-C-001", "PLD-PI-001(2)"):
            assert _PN_SPAN(form) == [(0, len(form))], form

    def test_it_is_case_sensitive_where_the_label_regex_is_not(self):
        # `_JC_FORM_NO_RE` only LABELS a rendering, so it tolerates a scan's
        # "l" for "I"; this one decides what is protected from faking, and a
        # lower-case "mc-025" in prose is not a form id.
        assert _PN_SPAN("mc-025") == []
        assert P._JC_FORM_NO_RE.search("mc-025")

    def test_a_longer_stamp_is_never_half_claimed(self):
        # Both boundaries hold, so a production stamp is either a form-id
        # shape whole or nothing — never its first six characters.
        assert _PN_SPAN("RAM-000013") == []
        assert _PN_SPAN("MC-025A") == []
        assert _PN_SPAN("ABC-MC-025") == [(0, 10)]   # the PLD-C-001 shape


def _PN_SPAN(text):
    return [m.span() for m in P._PN_FORM_ID_SPAN_RE.finditer(text)]


class TestTheIdSurvivesTheScrub:
    def test_an_acronym_term_does_not_rewrite_the_form_id(self):
        # The acronym is genuinely used by the document here, so it binds —
        # and the form id is still intact.
        body = FORM_BODY + "MC breached the agreement, and MC then sued.\n"
        pz, _ = _pz(["Mogharebi Capital, LLC"])
        pz.register_entity_acronyms(body)
        assert any(t.category == "short-name" and t.real == "MC"
                   for t in pz.terms)
        out = pz.apply(body)
        assert "MC-025" in out
        assert "MC breached" not in out          # the real use IS faked
        assert "Mogharebi" not in out

    def test_and_the_read_side_does_not_report_it(self):
        # The mirror: a value standing where `_substitute` refuses to touch
        # must never be reported, or the export is quarantined by a leak no
        # --fix-leaks pass can clear.
        body = FORM_BODY + "MC breached the agreement, and MC then sued.\n"
        pz, _ = _pz(["Mogharebi Capital, LLC"])
        pz.register_entity_acronyms(body)
        assert pz.surviving_reals(pz.apply(body)) == []

    def test_a_bare_token_term_does_not_rewrite_one_either(self):
        # Not acronym-specific: any term whose value is the id's letter run.
        body = "MC-025 ATTACHMENT\nMC Holdings LLC signed it.\n"
        pz, _ = _pz(["MC Holdings LLC"])
        out = pz.apply(body)
        assert "MC-025" in out
        assert "MC Holdings" not in out

    def test_the_lines_path_protects_it_too(self):
        # `apply_lines` assembles its own protected set; the two must agree.
        body = FORM_BODY + "MC breached the agreement, and MC then sued.\n"
        pz, _ = _pz(["Mogharebi Capital, LLC"])
        pz.register_entity_acronyms(body)
        out = "\n".join(pz.apply_lines(body.split("\n")))
        assert "MC-025" in out
        assert "MC breached" not in out


class TestTheAcronymNeedsEvidenceThatIsNotTheFormId:
    def test_a_form_id_occurrence_alone_mints_nothing(self):
        # The footer was both the reason the acronym existed and the thing it
        # rewrote. Span protection stops the rewrite; the term would still
        # carry a key row and fire wherever else those letters stand.
        pz, _ = _pz(["Mogharebi Capital, LLC"])
        pz.register_entity_acronyms(FORM_BODY)
        assert not [t for t in pz.terms if t.category == "short-name"]

    def test_one_real_occurrence_is_enough(self):
        pz, _ = _pz(["Mogharebi Capital, LLC"])
        pz.register_entity_acronyms(FORM_BODY + "MC then sued.\n")
        assert [t.real for t in pz.terms if t.category == "short-name"] == ["MC"]


class TestTheWholeValueGuardIsUnmoved:
    def test_a_form_id_is_still_never_a_term(self):
        assert P._pn_is_never_fake("MC-025")
        assert P._pn_is_never_fake("PLD-PI-001(2)")

    def test_a_term_the_operator_names_for_it_is_still_refused(self):
        reg = P._PnFakeRegistry()
        terms = P._pn_build_terms(["MC-025"], [], [], registry=reg)
        assert [t.real for t in terms] == []
