"""A word inside a CASE NAME is a party of a published decision, not of this
case — and three shapes of case name were reaching the review tiers anyway.

A cite STRUNG behind another ("…358, 373-374; Krongos v. Pacific Gas &
Electric Co.") had its year at the head of the next page, behind the firm's
letterhead, so neither the parser nor the shape guard saw a tail and the
plaintiff was reported. The semicolon after a citation is how a string cite
is written, and a capitalised " v. " run after it is the next authority; the
seam is the anchor the tail would have been. A `supra` short form declares a
short name ("Sanders, supra, 119 Cal.App.2d at p. 365") and the brief then
uses it BARE ("Sanders is instructive"), where nothing masked it. And the
authorities appendix this tool writes spells every cite out again in a URL
query ("scholar?q=Angle%20M.%20v.%20Superior%20Court"), where the plaintiff
blanked in the cite stood as a word between "=" and "%".

Run:  cd PDF-Linker && python3 -m pytest tests/test_string_cite_names.py -v
"""
import pdf_linker as P

DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}


def _pz(*names):
    reg = P._PnFakeRegistry()
    return P.Pseudonymizer(P._pn_build_terms(list(names), [], [], registry=reg),
                           DET, registry=reg)


def _rows(z, text):
    z.note_original(text)
    out = z.apply(text)
    return out, [r[1] for fn in ("fuzzy_survivor_scan", "half_scrubbed_scan",
                                 "unknown_name_scan", "narrative_name_scan")
                 for r in getattr(z, fn)(out)]


STRUNG = ("26  (Kremerman v. White (2021) 71 Cal.App.5th 358,\n"
          "27  373-374; Krongos v. Pacific Gas & Electric Co.\n"
          "28  \n"
          "\n"
          "====== Page 4 ======\n"
          "Steven Burt, Esq. (SBN 123456)\n"
          "LAW OFFICES OF STEVEN BURT\n"
          "1200 Main Street, Suite 400\n"
          " 1  (1992) 7 Cal.App.4th 387, 392.) The court held\n")


def test_a_strung_cite_with_its_year_on_the_next_page_is_masked():
    z = _pz("Maria Yardley", "Kronos Inc.")
    assert "Krongos" not in z._mask_protected_citations(STRUNG)
    assert "Pacific Gas" not in z._mask_protected_citations(STRUNG)
    _out, rows = _rows(z, STRUNG)
    assert "Krongos" not in rows


def test_the_seam_needs_a_cite_before_the_semicolon():
    # A semicolon in ordinary prose anchors nothing.
    text = ("12  The owner was warned; Krongos v. Pacific Gas & Electric Co.\n"
            "13  was never mentioned again.\n")
    assert not P._pn_string_cite_seam(text, text.index("Krongos"))
    assert P._pn_string_cite_seam(STRUNG, STRUNG.index("Krongos"))


def test_the_write_guard_keeps_a_strung_cites_parties():
    # A tracked party who shares a strung cite's name is left standing in
    # the cite — the invariant `_in_authority_context` states — while the
    # same name in prose is faked. One side at a time: both sides tracked
    # is the inline recital of this case's own caption, which is scrubbed.
    z = _pz("Ana Krongos")
    out = z.apply(STRUNG + "Ana Krongos signed.")
    assert "373-374; Krongos v. Pacific Gas & Electric Co." in out
    assert "Ana Krongos" not in out
    z = _pz("Pacific Gas & Electric Co.")
    out = z.apply(STRUNG + "Pacific Gas & Electric Co. paid.")
    assert "373-374; Krongos v. Pacific Gas & Electric Co." in out
    assert out.count("Pacific Gas & Electric Co.") == 1


def test_the_letterhead_hop_still_needs_the_tail():
    # The furniture hop after a page header admits nothing on its own: with
    # no year or reporter on the next page there is no cite shape, and a
    # capitalised run at the head of the next page is not joined to one.
    text = ("27  Later the owner of Pacific Gas & Electric Co.\n"
            "\n====== Page 4 ======\n"
            "Steven Burt, Esq.\n"
            " 1  Krongos filed suit.\n")
    assert P._pn_cite_shape_spans(text) == []


SUPRA = ("12  ted by the owner of the property himself, knowledge of the\n"
         "13  dangerous condition is imputed to the owner.' (Sanders, supra,\n"
         "14  119 Cal.App.2d at p. 365.) Sanders is instructive. In Sanders the\n"
         "15  owner knew of the hazard, and Sanders's owner was liable.\n")


def test_a_supra_short_name_is_masked_wherever_it_stands_bare():
    z = _pz("Paul Sander")
    masked = z._mask_protected_citations(SUPRA)
    assert "Sanders" not in masked
    assert P._pn_cite_short_names(SUPRA) == {"sanders"}
    _out, rows = _rows(z, SUPRA)
    assert "Sanders" not in rows


def test_a_space_before_the_supra_comma_is_tolerated():
    text = "13  owner.' (Sanders , supra, 119 Cal.App.2d at p. 365.)"
    assert [text[a:b] for a, b in P._pn_cite_shape_spans(text)] == ["Sanders"]


def test_a_tracked_party_sharing_the_short_name_is_not_masked():
    # `_surviving_records` reads through the mask, so a real party who shares
    # a cited decision's short name must stay visible where it survives.
    z = _pz("Paul Sanders")
    masked = z._mask_protected_citations(SUPRA)
    assert "Sanders is instructive" in masked
    assert "(Sanders, supra" not in masked      # the cite itself still is


def test_a_supra_short_name_is_an_authority_party_for_the_prune():
    idx = P._pn_authority_cite_index(SUPRA)
    assert idx.get("sanders") == {"Sanders, supra"}
    idx = P._pn_authority_cite_index(STRUNG)
    assert "krongos" in idx and "pacific" in idx


def test_a_word_inside_a_url_is_not_a_candidate():
    text = ("Stevens v. Owens (1990) 50 Cal.3d 100 -> https://scholar.google.com/"
            "scholar?q=Stevens%20v.%20Owens%2050%20Cal.3d%20100\n"
            "See also www.example.com/Stevens-brief.pdf for the brief.\n")
    z = _pz("Stevans Park")
    _out, rows = _rows(z, text)
    assert rows == []
    # …while the same word standing in prose is still a near-miss.
    z = _pz("Stevans Park")
    _out, rows = _rows(z, "Later Stevens signed the lease. Stevens paid.")
    assert "Stevens" in rows
