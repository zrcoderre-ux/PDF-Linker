"""A citation with NO TAIL in reach may not cross a page boundary.

Every other branch of `_PN_CITE_SHAPE_RE` is bounded by a tail — a year or a
volume+reporter run that says where the cite ends. The `strung` branch has
none by construction: it exists for the cite whose year sits on the next page
behind the firm's letterhead, and it is bounded only by a word count. So on a
page break it ran on into whatever the export printed next.

What it printed, in a delivered folder, was the attorney roster at the top of
the following page. "<plaintiff> v. Coastal Gas & Electric Co." closing page
15 swallowed "<attorney>, Esq." off the top of page 16 and read the attorney
as the cited defendant. Both sides of the mirror then failed, in opposite
directions and for the same reason:

* `_in_authority_context` refused to fake the name — it had a " v. " to its
  left, no year to its right, and a string-cite seam behind the " v. ";
* the citation MASK blanks exactly that run, so `_surviving_records`, which
  reads the masked body, could not see the name at all.

A real attorney's name shipped in the clear on every page of two exports, and
where the mask span came from the parser instead of the shape pattern the
value was reported as a leak that no `--fix-leaks` pass could ever clear —
every pass runs the same `_substitute`, refuses it again and re-reports it.

Three things close it, and the third is what lets the first two agree:
the furniture hop belongs to the TAIL and not to the name run; a tail-less
run is held to one page (`_PN_CITE_NAME_RUN_SAMEPAGE`, `_PN_PAGE_SEAM_RE`);
and `set_page_context` writes the export's own page header at the seam, so
the write guard can see a page boundary the read side has always seen.

Run:  cd PDF-Linker && python3 -m pytest tests/test_cite_run_stops_at_the_page.py -v
"""
import pdf_linker as P
import pytest


def _pz(names):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), [], [], registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    return P.Pseudonymizer(terms, det, registry=reg)


# Page 15 closes a string cite; its year opens page 16 behind the letterhead.
PAGE15 = ("26  the duty is owed to every invitee.  (Sanderling v. Whitcombe\n"
          "27  (2004) 121 Cal.App.4th 358, 373-374; Ferrers v. Coastal Gas & "
          "Electric Co.\n")
PAGE16 = ("Marisol Ellsworth, Esq.\n"
          "Jason Petherbridge, Esq.\n"
          "Dennis Houghton, Esq.\n"
          "\n"
          "           CALIFORNIA ACCIDENT FIRM\n"
          " 1  (1992) 7 Cal.App.4th 387, 393.)\n")
EXPORT = PAGE15 + "====== Page 16 ======\n" + PAGE16


class TestTheRunStopsAtThePage:
    def test_the_case_name_does_not_swallow_the_next_page(self):
        runs = [EXPORT[a:b] for a, b in P._pn_cite_shape_spans(EXPORT)]
        assert "Ferrers v. Coastal Gas & Electric Co." in runs
        assert not any("Ellsworth" in r for r in runs), (
            f"the attorney was read as a cited party: {runs}")

    def test_the_write_guard_and_the_leak_scan_agree(self):
        """The mirror. A value one side refuses and the other reports is a
        leak nothing can ever clear."""
        z = _pz(["Marisol Ellsworth"])
        s = EXPORT.index("Marisol Ellsworth")
        e = s + len("Marisol Ellsworth")
        write = z._in_authority_context(EXPORT, s, e)
        read = z._in_authority_context(z._mask_protected_citations(EXPORT), s, e)
        assert write == read is False

    def test_the_attorney_is_faked_and_nothing_leaks(self):
        z = _pz(["Marisol Ellsworth"])
        z.set_page_context(PAGE15, "")
        out = z.apply(PAGE16)
        assert "Marisol Ellsworth" not in out
        assert z.surviving_reals(PAGE15 + "\n" + out) == []


class TestTheAuthoritiesStillSurvive:
    """Whole point of the guard: a cited decision is never renamed."""

    def test_an_ordinary_cited_defendant(self):
        z = _pz(["Angela White"])
        t = "The court relied on Kremerman v. White (2021) 71 Cal.App.5th 358."
        assert z.apply(t) == t

    def test_a_TAILED_cite_still_crosses_the_page_break(self):
        """`Berryman v. Merit Prop. Mgmt., Inc.` closes one page and its
        `(2007) 152 Cal.App.4th 1544` opens the next. The tail is what says
        the name continues, so this branch keeps its page hop."""
        z = _pz(["Merit Property"])
        p3 = "27  arbitration is compelled.  (Berryman v. Merit Prop. Mgmt., Inc.\n"
        p4 = " 1  (2007) 152 Cal.App.4th 1544, 1550.)\n"
        z.set_page_context("", p4)
        assert z.apply(p3) == p3

    def test_a_strung_cite_on_one_page_keeps_its_defendant(self):
        z = _pz(["Pacific Gas"])
        t = ("27  (2004) 121 Cal.App.4th 358, 373-374; Ferrers v. Pacific Gas "
             "& Electric Co.\n28  and the rule is settled.\n")
        assert z.apply(t) == t


class TestTheSeamIsTheExportsOwn:
    def test_set_page_context_writes_a_page_header(self):
        z = _pz(["Angela White"])
        z.set_page_context("tail of the previous page", "head of the next")
        assert P._PN_PAGE_SEAM_RE.search(z._ctx_before)
        assert P._PN_PAGE_SEAM_RE.search(z._ctx_after)

    def test_the_seam_matches_the_pattern_that_reads_it(self):
        assert P._PN_PAGE_SEAM_RE.search(P._PN_PAGE_SEAM)

    def test_the_furniture_hop_is_the_tails_alone(self):
        """It was added to reach a year behind a letterhead; in the name run's
        own separator it let the NAME continue through that letterhead."""
        assert P._PN_CITE_PAGE_FURNITURE in P._PN_CITE_TAIL_WS
        assert P._PN_CITE_PAGE_FURNITURE not in P._PN_CITE_WS
        assert P._PN_CITE_PAGE_FURNITURE not in P._PN_CITE_NAME_RUN


class TestTheVItselfMayNotStraddleThePage:
    """The name runs of a tail-less cite were held to one page first and the
    " v. " between them was not, so a strung cite whose " v. " sat at the
    seam still matched across it — and the mask then blanked the page header
    itself. Nothing bounds a tail-less run but its word count, so nothing in
    it may cross a page: the pattern and both halves of the write guard now
    say so together."""
    P15 = ("27  (2004) 121 Cal.App.4th 358, 373-374; Ferrers Holdings\n")
    P16 = (" 1  v. Coastal Gas & Electric Co. supports the point.\n")
    EXPORT = P15 + "====== Page 16 ======\n" + P16

    def test_the_shape_pattern_stops_at_the_seam(self):
        runs = [self.EXPORT[a:b] for a, b in P._pn_cite_shape_spans(self.EXPORT)]
        assert not any("Page 16" in r for r in runs), runs
        assert not any("Ferrers" in r or "Coastal" in r for r in runs), runs

    def test_the_page_header_survives_the_mask(self):
        z = _pz(["Angela White"])
        assert "====== Page 16 ======" in z._mask_protected_citations(self.EXPORT)

    @pytest.mark.parametrize("party,page,before,after", [
        ("Coastal Gas", P16, P15, ""),       # the defendant's half
        ("Ferrers Holdings", P15, "", P16),  # the plaintiff's half
    ])
    def test_both_halves_of_the_write_guard_agree_with_the_mask(
            self, party, page, before, after):
        z = _pz([party])
        s = self.EXPORT.index(party)
        write = z._in_authority_context(self.EXPORT, s, s + len(party))
        read = z._in_authority_context(
            z._mask_protected_citations(self.EXPORT), s, s + len(party))
        assert write == read is False
        z.set_page_context(before, after)
        assert party not in z.apply(page)

    def test_a_strung_cite_whose_v_stays_on_its_page_keeps_both_names(self):
        z = _pz(["Coastal Gas", "Ferrers Holdings"])
        t = ("27  (2004) 121 Cal.App.4th 358, 373-374; Ferrers Holdings\n"
             "28  v. Coastal Gas & Electric Co. supports the point.\n")
        assert "Ferrers Holdings\n28  v. Coastal Gas & Electric Co." in [
            t[a:b] for a, b in P._pn_cite_shape_spans(t)]
