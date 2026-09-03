"""A plaintiff standing in the classic citation pattern is a cited
decision's party, not a leak — whatever the parser managed.

The leak scans masked what the citation PARSER read, and the shape guard
under them (`_in_authority_context`, `_pn_in_case_name`) looked for a " v. "
to the LEFT of a candidate: the defendant's half of a case name. So a cite
the parser could not read — wrapped over a page banner, an OCR'd reporter,
a `supra` whose full cite sits in another document — had its DEFENDANT
protected and its PLAINTIFF standing for every name-shaped review tier, and
on the write side its plaintiff renamed while its defendant was kept.

Three things close it. `_pn_cite_shape_spans` matches the classic pattern
on SHAPE alone — "X v. Y (2021) 71 Cal.App.5th 358", "X, supra, …", "In re
Marriage of X (2008) …" — and the mask every review tier reads through
blanks those names beside the parser's. `_in_authority_context` gains the
plaintiff's half, mirrored in the leak tier as the defendant's already was.
And `_pn_in_case_name` gains it too, for the tiers that ask about a span.

Run:  cd PDF-Linker && python3 -m pytest tests/test_cited_plaintiff_not_a_leak.py -v
"""
import pytest

import pdf_linker as P


def _pz(names=()):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), [], [], registry=reg)
    return P.Pseudonymizer(terms, [], registry=reg)


def _blind(pz):
    """A Pseudonymizer whose citation parser reads nothing — the cite the
    scans have to survive without it."""
    pz._protected_citation_spans = lambda t: []
    return pz


def _spans(text):
    return [text[s:e] for s, e in P._pn_cite_shape_spans(text)]


# ── the shape matcher ──────────────────────────────────────────────────────

@pytest.mark.parametrize("text,names", [
    ("Plaintiff relies on Kremerman v. White (2021) 71 Cal.App.5th 358, 362.",
     ["Kremerman v. White"]),
    ("See Lukather v. General Motors LLC (2010) 181 Cal.App.4th 1041.",
     ["Lukather v. General Motors LLC"]),
    ("See Market Lofts Community Assn. v. 9th Street Market Lofts, LLC (2014) "
     "222 Cal.App.4th 924.", ["Market Lofts Community Assn. v. 9th Street Market Lofts, LLC"]),
    ("Smith v. Jones, 123 F.3d 456 (9th Cir. 1999).", ["Smith v. Jones"]),
    ("Kremerman v. White (Cal. Ct. App. 2021) 71 Cal.App.5th 358.", ["Kremerman v. White"]),
    ("the rule. Kremerman, supra, 71 Cal.App.5th at p. 362.", ["Kremerman"]),
    ("(See In re Marriage of Kelley Hartwell (2008) 167 Cal.App.4th 562.)",
     ["In re Marriage of Kelley Hartwell"]),
    ("The Legislature intended it. Sotelo v. Medianews Group, Inc. (2012) 207 "
     "Cal.App.4th 639.", ["Sotelo v. Medianews Group, Inc."]),
])
def test_the_classic_pattern_is_read_on_shape_alone(text, names):
    assert _spans(text) == names


@pytest.mark.parametrize("text", [
    "HELEN RASHO, Plaintiff, v. QUILLMARK, LLC, Defendant. Case No. 25STCV37838",
    "Rasho v. Quillmark, LLC, Case No. 25STCV37838 (filed 2025).",
    "Krikorian Inv. Servs., Inc. v. Radmanesh, No. BC543295, 2015 WL 12751760",
    "Rasho emailed the branch manager in 2021.",
    "The parties executed a Master Services Agreement (2019).",
])
def test_a_caption_a_docket_and_prose_are_not_the_pattern(text):
    assert _spans(text) == []


def test_the_name_does_not_walk_back_into_the_sentence_before_the_cite():
    # The word that closes the previous sentence is not the plaintiff, and a
    # citation signal is not either; an abbreviation inside the name is.
    assert _spans("Rasho sued Quillmark. See Smith v. Jones (2020) 1 Cal.5th 1.") == ["Smith v. Jones"]
    assert _spans("Cf. Aguilar v. Atlantic Richfield Co. (2001) 25 Cal.4th 826.") == ["Aguilar v. Atlantic Richfield Co."]


# ── the span screens ───────────────────────────────────────────────────────

def test_the_case_name_screen_covers_the_plaintiff_when_given_the_span():
    text = "Kremerman v. White (2021) 71 Cal.App.5th 358"
    s, e = 0, len("Kremerman")
    assert P._pn_in_case_name(text, s, e) is True
    assert P._pn_in_case_name(text, s) is False          # the old, left-only ask
    text = "Quillmark. See Smith v. Jones (2020) 1 Cal.5th 1"
    assert P._pn_in_case_name(text, 0, len("Quillmark")) is False


def test_the_write_side_guard_covers_the_plaintiff_and_mirrors_the_leak_tier():
    pz = _blind(_pz(["Helen Rasho", "Quillmark, LLC", "Kremerman"]))
    text = "Plaintiff relies on Kremerman v. White (2021) 71 Cal.App.5th 358."
    out = pz.apply(text)
    assert out == text, out                 # the authority is not renamed…
    assert pz.surviving_reals(out) == []     # …and the leak tier agrees


def test_the_guard_still_needs_both_anchors():
    pz = _blind(_pz(["Helen Rasho", "Quillmark, LLC"]))
    # The caption: a " v. " follows the plaintiff, and no year or reporter.
    out = pz.apply("HELEN RASHO, Plaintiff, v. QUILLMARK, LLC, Defendant.")
    assert "RASHO" not in out and "QUILLMARK" not in out
    # A party closing the sentence before a cite is not its plaintiff.
    out = pz.apply("Rasho sued Quillmark. See Smith v. Jones (2020) 1 Cal.5th 1.")
    assert "Rasho" not in out and "Quillmark" not in out
    assert "Smith v. Jones" in out


def test_this_case_s_own_caption_recited_inline_is_still_scrubbed():
    pz = _blind(_pz(["Helen Rasho", "Quillmark, LLC"]))
    out = pz.apply("This action, Rasho v. Quillmark, LLC (2025) 12 Cal.App.5th 1, is on remand.")
    assert "Rasho" not in out


# ── the review tiers ───────────────────────────────────────────────────────

def test_the_role_anchored_tier_refuses_a_cited_plaintiff():
    pz = _pz()
    text = "Respondent Kremerman v. White (2021) 71 Cal.App.5th 358 is inapposite."
    assert pz.unknown_name_scan(text) == []


def test_the_fuzzy_sweep_does_not_read_a_cited_plaintiff_as_a_slip():
    """A cited plaintiff one letter from this case's party, in a cite the
    parser could not read, is the shape the sweep exists to net — and the
    mask now blanks the classic pattern whether or not the parser read it."""
    pz = _blind(_pz(["Steven Kremermann"]))
    text = ("Steven Kremermann signed. See Kremerman v. White (2021) "
            "71 Cal.App.5th 358, 362.")
    out = pz.apply(text)
    assert "Kremermann" not in out
    assert not any("Kremerman" in s for _c, s in pz.fuzzy_survivor_scan(out))


def test_a_supra_short_form_is_masked_without_its_full_cite():
    pz = _blind(_pz(["Steven Kremermann"]))
    out = pz.apply("Steven Kremermann signed. Kremerman, supra, 71 Cal.App.5th at p. 362.")
    assert not any("Kremerman" in s for _c, s in pz.fuzzy_survivor_scan(out))


def test_the_mask_blanks_the_name_and_leaves_the_rest():
    pz = _blind(_pz())
    masked = pz._mask_protected_citations(
        "See Kremerman v. White (2021) 71 Cal.App.5th 358, and Rasho agreed.")
    assert "Kremerman" not in masked and "White" not in masked
    assert "(2021) 71 Cal.App.5th 358" in masked and "Rasho agreed" in masked


def test_a_real_party_beside_a_cite_is_still_reported():
    """The screens are shaped on the CITE: a witness named in ordinary prose
    next to one is exactly what the review tiers exist to surface."""
    pz = _pz()
    text = ("Spellman confirmed the transfer. See Kremerman v. White (2021) "
            "71 Cal.App.5th 358.")
    assert [s for _c, s in pz.narrative_name_scan(text)] == ["Spellman"]
