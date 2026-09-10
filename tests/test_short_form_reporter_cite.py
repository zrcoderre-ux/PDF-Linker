"""A short-form cite written WITHOUT "supra" is a citation.

"(Greenspan, 191 Cal.App.4th at 511.)" is how a California brief cites a
decision it has already spelled out, and nothing read it: the full-cite
parser is anchored on " v. " and the supra resolver on the word "supra", so
the cite parsed as nothing, was linked nowhere, earned no protected span,
and the name in it was offered up to every name-shaped review tier as a
value this case had failed to scrub — a row an operator can only answer
wrong, since a `yes` mints the cited decision's party as an authoritative
term and renames the authority in every export.

Two halves, the way this file's other authority rules are built. The PARSER
resolves the short cite against the full cite the same text spells out, so
it links and earns a span; and the SHAPE guard protects the name whether or
not any parse succeeded (`_PN_SHORT_CITE_TAIL`, `_pn_short_cite_follows`),
because protection must never depend on a parser succeeding.

Run:  cd PDF-Linker && python3 -m pytest tests/test_short_form_reporter_cite.py -v
"""
import pytest

import pdf_linker as P


FULL = "Greenspan v. LADT, LLC (2010) 191 Cal.App.4th 486, 511."
SHORT = "(Greenspan, 191 Cal.App.4th at 511.)"


def _pz(names=()):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), [], [], registry=reg)
    return P.Pseudonymizer(terms, [], registry=reg)


def _blind(pz):
    """A Pseudonymizer whose citation parser reads nothing — the cite the
    guards have to survive without."""
    pz._protected_citation_spans = lambda t: []
    return pz


def _spans(text):
    return [text[s:e] for s, e in P._pn_cite_shape_spans(text)]


# ── the parser ─────────────────────────────────────────────────────────────

def test_the_short_cite_resolves_to_the_full_cite_it_shortens():
    cites = P.find_all_citations(f"{FULL} The court so held. {SHORT}")
    shorts = [c for c in cites if c.get("is_short_cite")]
    assert [c["match_text"] for c in shorts] == ["Greenspan, 191 Cal.App.4th at 511"]
    assert shorts[0]["key"] == "Greenspan v. LADT, LLC (2010) 191 Cal.App.4th 486"


@pytest.mark.parametrize("short,text", [
    ("Greenspan, 191 Cal.App.4th at p. 511", "Greenspan, 191 Cal.App.4th at p. 511."),
    ("Greenspan, 191 Cal.App.4th at pp. 511-512",
     "See Greenspan, 191 Cal.App.4th at pp. 511-512."),
    ("Greenspan, 191 Cal.App.4th at 511", "(Accord, Greenspan, 191 Cal.App.4th at 511.)"),
])
def test_the_pinpoint_forms_a_brief_actually_writes(short, text):
    cites = P.find_all_citations(f"{FULL} {text}")
    assert short in [c["match_text"] for c in cites if c.get("is_short_cite")]


def test_the_name_may_carry_its_own_v():
    text = ("Kremerman v. White (2021) 71 Cal.App.5th 358, 362. "
            "Kremerman v. White, 71 Cal.App.5th at 364.")
    shorts = [c for c in P.find_all_citations(text) if c.get("is_short_cite")]
    assert [c["match_text"] for c in shorts] == ["Kremerman v. White, 71 Cal.App.5th at 364"]


def test_the_reporter_run_says_WHICH_decision_it_is():
    """Two cases share a first word, and the volume and reporter of the short
    cite are what tell them apart. Linking a reader to the wrong decision is
    worse than not linking at all, so a run that agrees with neither full
    cite resolves to nothing."""
    text = ("Smith v. Jones (1990) 5 Cal.3d 1. Smith v. Doe (2001) 88 "
            "Cal.App.4th 20. Smith, 88 Cal.App.4th at 25. "
            "Smith, 12 Cal.App.4th at 30.")
    shorts = [c for c in P.find_all_citations(text) if c.get("is_short_cite")]
    assert [c["match_text"] for c in shorts] == ["Smith, 88 Cal.App.4th at 25"]
    assert shorts[0]["key"].startswith("Smith v. Doe")


def test_a_short_cite_with_no_full_cite_in_reach_resolves_to_nothing():
    assert [c for c in P.find_all_citations(SHORT) if c.get("is_short_cite")] == []


def test_a_bluebook_full_cite_is_not_read_as_a_short_one():
    """The pinpoint "at" is the corroboration: a full cite states its year
    where a short cite states a page, and the branches that read the full
    form must keep it."""
    text = "Smith v. Jones, 123 F.3d 456 (9th Cir. 1999)."
    assert [c for c in P.find_all_citations(text) if c.get("is_short_cite")] == []
    assert [c["match_text"] for c in P.find_all_citations(text)] == [text.rstrip(".")]


# ── the shape guard ────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,names", [
    ("The court so held. (Greenspan, 191 Cal.App.4th at 511.)", ["Greenspan"]),
    ("See Greenspan, 191 Cal.App.4th at p. 511.", ["Greenspan"]),
    ("(RGC Gaslamp, 56 Cal.App.5th at 420.)", ["RGC Gaslamp"]),
    ("Ford Motor Warranty, 17 Cal.5th at 1133.", ["Ford Motor Warranty"]),
])
def test_the_short_form_is_read_on_shape_alone(text, names):
    assert _spans(text) == names


@pytest.mark.parametrize("text", [
    "HELEN RASHO, Plaintiff, v. QUILLMARK, LLC. Case No. 25STCV37838.",
    "Rasho met Quillmark at 511 Main Street, 5 miles from the site.",
    "The deposition began at 10 a.m. and ran to 5 p.m.",
    "Quillmark, 191 units at 511 Main Street.",
])
def test_prose_a_caption_and_an_address_are_not_the_pattern(text):
    assert _spans(text) == []


def test_the_name_does_not_walk_back_into_the_sentence_before_the_cite():
    assert (_spans("Rasho sued Quillmark. See Greenspan, 191 Cal.App.4th at 511.")
            == ["Greenspan"])


# ── the write side, and its mirror ─────────────────────────────────────────

def test_the_authority_is_not_renamed_and_the_leak_tier_agrees():
    pz = _blind(_pz(["Greenspan", "Helen Rasho"]))
    text = f"Rasho signed the note. The court so held. {SHORT}"
    out = pz.apply(text)
    assert "Greenspan, 191 Cal.App.4th at 511" in out    # the authority stands
    assert "Rasho" not in out                            # the party does not
    assert pz.surviving_reals(out) == []                 # …and no leak is reported


def test_the_guard_runs_on_a_page_that_carries_no_v_at_all():
    """The guard's own gate read a " v. " alone, so a page whose only cites
    are short forms ran no guard: the cheap early-out, not the guard, was
    what renamed the decision."""
    pz = _blind(_pz(["Greenspan"]))
    text = "The rule is settled. (Greenspan, 191 Cal.App.4th at 511.)"
    assert "v." not in text
    assert pz.apply(text) == text


def test_the_cite_survives_the_pleading_wrap_the_export_prints():
    """The export keeps the gutter number of the line a cite wraps onto, so
    the gap between the name and its reporter run is "\n 7  " — the shape
    every other branch is built to read across, and the one that has blinded
    this guard before."""
    pz = _blind(_pz(["Greenspan"]))
    body = (" 6  The court disagreed. (Greenspan,\n"
            " 7  191 Cal.App.4th at 511.) The motion is denied.\n")
    assert _spans(body) == ["Greenspan"]
    assert pz.apply(body) == body
    assert pz.surviving_reals(body) == []


def test_the_case_name_screen_covers_it_when_given_the_span():
    text = "Greenspan, 191 Cal.App.4th at 511"
    assert P._pn_in_case_name(text, 0, len("Greenspan")) is True
    assert P._pn_in_case_name(text, 0) is False          # the left-only ask


def test_the_review_tiers_refuse_a_cited_short_form():
    pz = _pz()
    assert pz.unknown_name_scan(
        "Respondent Greenspan, 191 Cal.App.4th at 511, is inapposite.") == []


def test_the_fuzzy_sweep_does_not_read_a_cited_short_form_as_a_slip():
    pz = _blind(_pz(["Steven Greenspann"]))
    out = pz.apply(f"Steven Greenspann signed. {SHORT}")
    assert "Greenspann" not in out
    assert not any("Greenspan" in s for _c, s in pz.fuzzy_survivor_scan(out))


def test_the_mask_blanks_the_name_and_leaves_the_rest():
    pz = _blind(_pz())
    masked = pz._mask_protected_citations(
        "The court so held. (Greenspan, 191 Cal.App.4th at 511.) Rasho agreed.")
    assert "Greenspan" not in masked
    assert "191 Cal.App.4th at 511" in masked and "Rasho agreed" in masked


def test_a_real_party_beside_a_short_cite_is_still_reported():
    pz = _pz()
    text = f"Spellman confirmed the transfer. {SHORT}"
    assert [s for _c, s in pz.narrative_name_scan(text)] == ["Spellman"]


def test_the_bare_short_name_is_masked_wherever_the_brief_uses_it():
    """A short cite DECLARES the name the brief then uses bare — "Greenspan
    is distinguishable", two lines under it — exactly as ", supra" does, and
    the review tiers read through the mask that blanks it."""
    pz = _blind(_pz())
    masked = pz._mask_protected_citations(
        f"{SHORT} Greenspan is distinguishable, and Rasho agreed.")
    assert "Greenspan" not in masked
    assert "Rasho agreed" in masked


def test_a_tracked_party_that_shares_the_name_is_still_scrubbed_elsewhere():
    """`_tracked_real_words` is the exception the mask has always carried: a
    party of THIS case who shares a cited decision's name keeps being faked
    everywhere but inside the cite."""
    pz = _pz(["Greenspan"])
    out = pz.apply(f"{SHORT} Greenspan signed the note on Tuesday.")
    assert "Greenspan, 191 Cal.App.4th at 511" in out
    assert "Greenspan signed" not in out
