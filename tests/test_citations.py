"""Unit tests for pdf_linker's case-citation detection across line wraps.

These need no geometry — they exercise the pure text path
(_normalize_for_detection -> REPORTER_PATTERN -> *_TAIL -> find_all_citations),
so each case is just a string. The wrapped strings reproduce what PyMuPDF
actually emits for a reporter split across two printed lines: a trailing space
before the newline ("Cal. App. \n4th"), which normalization turns into a
DOUBLE space inside the reporter. That double space is what the wild bug
(Caliber Bodyworks missed in an Opposition's authorities appendix) tripped on.

Run with: pytest tests/test_citations.py
"""
import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pdf_linker", _ROOT / "pdf_linker.py")
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)


def _keys(text):
    return {c["key"] for c in pl.find_all_citations(text)}


class TestReporterLineWraps:
    """A reporter split across a line wrap must still be detected. The wrap
    can fall at any internal position; PyMuPDF's trailing-space-then-newline
    means the reporter arrives with an embedded double space after
    normalization."""

    CITE = "Caliber Bodyworks, Inc. v. Superior Court (2005) 134 Cal.App.4th 365"

    def test_same_line_baseline(self):
        t = "See Caliber Bodyworks, Inc. v. Superior Court, 134 Cal. App. 4th 365 (2005)."
        assert self.CITE in _keys(t)

    def test_wrap_inside_reporter(self):
        # The reporter itself is broken: "134 Cal. App. \n4th 365". This is the
        # exact shape that was silently dropped from the appendix.
        t = "See Caliber Bodyworks, Inc. v. Superior Court, 134 Cal. App. \n4th 365 (2005)."
        assert self.CITE in _keys(t)

    def test_wrap_after_series(self):
        t = "See Caliber Bodyworks, Inc. v. Superior Court, 134 Cal. App. 4th \n365 (2005)."
        assert self.CITE in _keys(t)

    def test_wrap_between_volume_and_reporter(self):
        t = "See Caliber Bodyworks, Inc. v. Superior Court, 134 \nCal. App. 4th 365 (2005)."
        assert self.CITE in _keys(t)

    def test_compact_reporter_unaffected(self):
        t = "See LiMandri v. Judkins 52 Cal.App.4th 326 (1997)."
        assert "LiMandri v. Judkins (1997) 52 Cal.App.4th 326" in _keys(t)

    def test_three_token_reporter_wraps(self):
        # Cal. Rptr. 3d split mid-reporter.
        t = "See People v. Smith, 12 Cal. Rptr. \n3d 99 (2003)."
        assert any("Cal.Rptr.3d" in k for k in _keys(t))


class TestNonVCaseNames:
    """Probate, conservatorship, and family-law cases carry no "v." anchor —
    "Conservatorship of Whitley (2010) 50 Cal.4th 1206" is reachable only
    through the _NONV_PREFIX alternation in INRE_RE. The key must be rebuilt
    with the prefix that actually matched (a Conservatorship-of case relabelled
    "In re" is the wrong authority), and _short_name must strip NESTED
    prefixes so every Marriage-of case doesn't collapse onto "Marriage"."""

    CASES = [
        ("Conservatorship of Whitley (2010) 50 Cal.4th 1206.",
         "Conservatorship of Whitley (2010) 50 Cal.4th 1206", "Whitley"),
        ("Estate of Bowles (2008) 169 Cal.App.4th 684.",
         "Estate of Bowles (2008) 169 Cal.App.4th 684", "Bowles"),
        ("Guardianship of Ann S. (2009) 45 Cal.4th 1110.",
         "Guardianship of Ann S. (2009) 45 Cal.4th 1110", "Ann"),
        ("Adoption of Kelsey S. (1992) 1 Cal.4th 816.",
         "Adoption of Kelsey S. (1992) 1 Cal.4th 816", "Kelsey"),
        ("In re Marriage of Bonds (2000) 24 Cal.4th 1.",
         "In re Marriage of Bonds (2000) 24 Cal.4th 1", "Bonds"),
        ("In re Doe (2009) 555 F.3d 100.",
         "In re Doe (2009) 555 F.3d 100", "Doe"),
    ]

    def _only_case(self, text):
        cites = [c for c in pl.find_all_citations(text) if c["kind"] == "case"]
        assert len(cites) == 1, cites
        return cites[0]

    @pytest.mark.parametrize("text,key,short", CASES)
    def test_detected_with_its_own_prefix(self, text, key, short):
        c = self._only_case(text)
        assert c["key"] == key
        assert c["short"] == short

    def test_pinpoint_page_is_outside_the_span(self):
        t = ("The court in Conservatorship of Whitley (2010) 50 Cal.4th 1206, "
             "1214 held otherwise.")
        c = self._only_case(t)
        assert c["match_text"] == "Conservatorship of Whitley (2010) 50 Cal.4th 1206"
        assert t[c["span"][0]:c["span"][1]] == c["match_text"]

    def test_bluebook_form(self):
        c = self._only_case("Conservatorship of Whitley, 50 Cal.4th 1206 (2010).")
        assert c["key"] == "Conservatorship of Whitley (2010) 50 Cal.4th 1206"

    def test_supra_resolves_to_the_full_cite(self):
        t = ("Conservatorship of Whitley (2010) 50 Cal.4th 1206, 1214. Later: "
             "Conservatorship of Whitley, supra, 50 Cal.4th at p. 1214.")
        supras = [c for c in pl.find_all_citations(t) if c.get("is_supra")]
        assert [c["key"] for c in supras] == [
            "Conservatorship of Whitley (2010) 50 Cal.4th 1206"]

    def test_nested_prefixes_do_not_collide_on_marriage(self):
        t = ("In re Marriage of Bonds (2000) 24 Cal.4th 1, 25. "
             "In re Marriage of Davis (2015) 61 Cal.4th 846, 850. "
             "See In re Marriage of Davis, supra, 61 Cal.4th at p. 850.")
        supras = [c for c in pl.find_all_citations(t) if c.get("is_supra")]
        assert [c["key"] for c in supras] == [
            "In re Marriage of Davis (2015) 61 Cal.4th 846"]

    def test_citation_party_is_never_pseudonymized(self):
        """The cardinal invariant: a case-name word that is ALSO this case's
        party ("Whitley") is faked in the body and left byte-for-byte intact
        inside the published cite — full form and supra alike."""
        reg = pl._PnFakeRegistry()
        terms = pl._pn_build_terms([("Alan Whitley", False)], [], [], reg)
        pz = pl.Pseudonymizer(terms, list(pl._PN_DEFAULT_DETECTORS), reg)
        out = pz.apply(
            "Alan Whitley opposes. Moving party relies on Conservatorship of "
            "Whitley (2010) 50 Cal.4th 1206, 1214, and on Conservatorship of "
            "Whitley, supra, 50 Cal.4th at p. 1214.")
        assert "Alan Whitley" not in out
        assert out.count("Conservatorship of Whitley") == 2
        # And the intact citation must not come back as a leak to triage.
        assert pl._pn_review_findings(out) == []


class TestConnectorJoinedPartyNames:
    """A party can be named with a lowercase word inside it — "Service by
    Medallion, Inc.", "Committee for Green Foothills". The walk-back from
    "v." stopped on the connector and captured only the tail, so the link
    and the blue underline started mid-name. Legal style italicizes the
    case name, so the visible result was an underline that began partway
    through the italics."""

    def _cite(self, text):
        cites = [c for c in pl.find_all_citations(text) if c["kind"] == "case"]
        assert len(cites) == 1, cites
        return cites[0]

    def test_by_is_kept_inside_the_party_name(self):
        t = ("See Service by Medallion, Inc. v. Clorox Co. (1996) 44 "
             "Cal.App.4th 1807, 1818-1819.")
        c = self._cite(t)
        assert c["plaintiff"] == "Service by Medallion, Inc."
        # The whole italicized case name is inside the span that gets the
        # link and the underline — not just "Medallion, Inc. v. Clorox Co."
        assert c["match_text"].startswith("Service by Medallion, Inc. v.")

    def test_for_is_kept_inside_the_party_name(self):
        t = ("Committee for Green Foothills v. Santa Clara County (2010) "
             "48 Cal.4th 32, 40.")
        assert self._cite(t)["plaintiff"] == "Committee for Green Foothills"

    def test_leading_preposition_in_prose_is_still_stripped(self):
        """The connector is admitted only when a capitalized word precedes
        it. In prose the word to its left is lowercase, so the walk-back
        stops there and the signal-prefix strip removes the connector."""
        for lead in ("The test articulated by", "The standard for",
                     "relied on by", "as adopted by"):
            t = f"{lead} Smith v. Jones (2001) 90 Cal.App.4th 1, 5."
            assert self._cite(t)["plaintiff"] == "Smith"

    def test_supra_still_resolves_for_a_connector_joined_party(self):
        """SUPRA_RE captures one capitalized token, so "Service by
        Medallion, supra" comes back as "Medallion" while the registered
        short name is now "Service". The alias keeps the supra cite
        resolvable."""
        t = ("Service by Medallion, Inc. v. Clorox Co. (1996) 44 "
             "Cal.App.4th 1807, 1818. Later, Service by Medallion, supra, "
             "44 Cal.App.4th at p. 1818.")
        supras = [c for c in pl.find_all_citations(t) if c.get("is_supra")]
        assert [c["key"] for c in supras] == [
            "Service by Medallion, Inc. v. Clorox Co. (1996) 44 Cal.App.4th 1807"]

    def test_supra_alias_also_covers_of_joined_parties(self):
        t = ("Bank of America, N.A. v. Smith (2019) 30 Cal.App.5th 1, 5. "
             "See Bank of America, supra, 30 Cal.App.5th at p. 5.")
        supras = [c for c in pl.find_all_citations(t) if c.get("is_supra")]
        assert [c["key"] for c in supras] == [
            "Bank of America, N.A. v. Smith (2019) 30 Cal.App.5th 1"]

    def test_short_name_aliases_needs_a_capitalized_follower(self):
        assert pl._short_name_aliases("Service by Medallion, Inc.") == ["Medallion"]
        assert pl._short_name_aliases("Smith") == []
        assert pl._short_name_aliases("Jones and") == []
