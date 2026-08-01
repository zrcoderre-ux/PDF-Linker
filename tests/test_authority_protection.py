"""
D1 — a cited authority must never be renamed, even when nothing parses it.

The seven-document Song-Beverly fee-motion corpus shipped six citations naming
decisions that do not exist: *Ewald v. Nationstar Mortgage, LLC* went out as
*Ewald v. Sandpiper Monarch, LLC*. Every rewritten cite WRAPPED across a
pleading line, so a gutter line number sat between the volume and the reporter;
`find_all_citations` then read no citation at all, `_protected_citation_spans`
returned no span, and the entity term rewrote the cited party.

Two fixes, tested here in both directions:
  * the parser is taught the gutter (a second detection pass with line numbers
    blanked, merged into the first), and
  * `_substitute` refuses a name-shaped candidate standing in a citation-SHAPED
    context whether or not a citation parsed there — so the protection no longer
    depends on a parser succeeding.

Run:  cd PDF-Linker && python3 -m pytest tests/test_authority_protection.py -v
"""

import pytest

import pdf_linker as P


def _pz(names, casenos=("25STCV14710",)):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), list(casenos), [], registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    return P.Pseudonymizer(terms, det, registry=reg)


def _lines(*bodies, first=17):
    """`bodies` as a pleading page's numbered lines, exactly as the text export
    writes them (`f"{num:>2}  "` + body)."""
    return "\n".join(f"{first + i:>2}  {b}" for i, b in enumerate(bodies))


# ─────────────────────────── the parser half ────────────────────────────────

# Each of these is a citation the corpus shipped renamed. The line number lands
# between the volume and the reporter in the first three and BEFORE the volume
# in the fourth — both shapes blinded the parser.
WRAPPED_CITES = [
    (["Ewald v. Nationstar Mortgage, LLC (2017) 13", "Cal.App.5th 947, 950"],
     "Nationstar Mortgage, LLC"),
    (["Jensen v. BMW of North America, Inc. (1995) 35", "Cal.App.4th 112, 138"],
     "BMW of North America, Inc."),
    (["Krotin v. Porsche Cars North America, Inc. (1995)",
      "38 Cal.App.4th 294, 299"],
     "Porsche Cars North America, Inc."),
    (["Zive v. Aston Martin Lagonda of North America, Inc. (2022) 82",
      "Cal.App.5th 951, 960"],
     "Aston Martin Lagonda of North America, Inc."),
]


@pytest.mark.parametrize("bodies,authority", WRAPPED_CITES)
def test_wrapped_cite_parses_across_a_gutter_line_number(bodies, authority):
    text = _lines(*bodies)
    cites = P.find_all_citations(text)
    assert cites, f"no citation parsed across the gutter in:\n{text}"
    s, e = cites[0]["span"]
    assert authority in text[s:e], (
        f"the parsed span {text[s:e]!r} does not cover the cited party name")


@pytest.mark.parametrize("bodies,authority", WRAPPED_CITES)
def test_wrapped_authority_survives_apply_byte_for_byte(bodies, authority):
    # Every party word of the authority is also a tracked term for this case —
    # which is the whole hazard: without protection the term rewrites the cite.
    z = _pz(["Helen Rasho", "Nationstar Mortgage, LLC",
             "North America Holdings, Inc.", "Aston Martin Lagonda, LLC",
             "Porsche Cars, Inc."])
    text = _lines(*bodies)
    out = z.apply(text)
    assert authority in out, (
        f"cited authority renamed:\n  in : {text}\n  out: {out}")


def test_single_line_cite_still_protected():
    # The pre-existing path must not regress: a cite that reads straight through
    # was always protected and still is.
    z = _pz(["Helen Rasho", "Nationstar Mortgage, LLC"])
    cite = "Ewald v. Nationstar Mortgage, LLC (2017) 13 Cal.App.5th 947, 950"
    assert cite in z.apply(f"See {cite}.")


def test_gutter_blanking_is_length_preserving():
    # Spans from the second detection pass index into the ORIGINAL text, so the
    # blanking must not move a single character.
    text = _lines("Ewald v. Nationstar Mortgage, LLC (2017) 13",
                  "Cal.App.5th 947, 950.")
    assert len(P._blank_gutter_line_numbers(text)) == len(text)


def test_gutter_blanking_leaves_a_line_leading_volume_alone():
    # "13 Cal.App.5th" opening a line is a VOLUME, not a gutter number: one
    # space, not two. Blanking it would be harmless (pass two only ever adds a
    # span) but the heuristic should still tell them apart.
    assert P._blank_gutter_line_numbers("x\n13 Cal.App.5th 947") \
        == "x\n13 Cal.App.5th 947"


# ────────────────────── the fail-closed guard half ──────────────────────────

def test_authority_protected_with_the_parser_forcibly_blinded(monkeypatch):
    # The structural fix: protection must not depend on a parser succeeding.
    # With citation detection returning nothing at all, the cited party name is
    # still refused because of the SHAPE of its context.
    z = _pz(["Helen Rasho", "Nationstar Mortgage, LLC"])
    monkeypatch.setattr(P, "find_all_citations", lambda text: [])
    out = z.apply("See Ewald v. Nationstar Mortgage, LLC (2017) 13 "
                  "Cal.App.5th 947, 950.")
    assert "Nationstar Mortgage, LLC" in out, (
        f"authority renamed once the parser was blinded: {out}")


def test_blinded_guard_needs_both_anchors(monkeypatch):
    # The guard fires only between a " v. " and a year/reporter. A party name
    # with no authority shape around it is still faked — the guard must not
    # become a blanket amnesty for anything following a "v.".
    z = _pz(["Helen Rasho", "Nationstar Mortgage, LLC"])
    monkeypatch.setattr(P, "find_all_citations", lambda text: [])
    out = z.apply("Rasho v. Nationstar Mortgage, LLC, Case No. 25STCV14710, "
                  "is the operative action.")
    assert "Nationstar Mortgage, LLC" not in out, (
        f"the case's own caption was left in the clear: {out}")


def test_guard_does_not_block_this_cases_own_caption(monkeypatch):
    # An inline recital of this case's caption DOES carry a year, so both
    # anchors are present — the caption exemption (both sides trusted) is what
    # keeps the real parties from riding out.
    z = _pz(["Helen Rasho", "General Motors, LLC"])
    monkeypatch.setattr(P, "find_all_citations", lambda text: [])
    out = z.apply("This action, Helen Rasho v. General Motors, LLC (2025), "
                  "is before the Court.")
    assert "Rasho" not in out and "General Motors" not in out, (
        f"the case's own parties survived: {out}")


def test_guard_leaves_a_detector_hit_alone(monkeypatch):
    # An SSN or a phone number inside a citation is not a thing; refusing one
    # would be pure leak, so the guard is scoped to name-shaped candidates.
    z = _pz(["Helen Rasho"])
    monkeypatch.setattr(P, "find_all_citations", lambda text: [])
    out = z.apply("Rasho v. Doe (2017) 13 Cal.App.5th 947 (818) 953-0150.")
    assert "953-0150" not in out, f"phone number left in the clear: {out}"


# ────────────────────────── _side_is_trusted ────────────────────────────────

def test_one_shared_word_does_not_make_a_side_this_cases_caption():
    # A case with a party named "North" cleared BOTH sides of
    # *Jensen v. BMW of North America* on one word each, which strips the
    # citation protection off the authority outright.
    z = _pz(["Jensen Contracting, Inc.", "North Ridge Auto Group, LLC"])
    assert z._side_is_trusted("Jensen"), "plaintiff side is genuinely ours"
    assert not z._side_is_trusted("BMW of North America"), (
        "one shared word ('North') reported a cited authority as our caption")


def test_a_real_caption_side_is_still_trusted():
    z = _pz(["Helen Rasho", "Valencia Holding Co., LLC"])
    assert z._side_is_trusted("Valencia Holding Co., LLC"), (
        "corporate furniture must not dilute a side that IS ours")
    assert z._side_is_trusted("Helen Rasho")


# ───── the scan must not report what the write side deliberately protects ────

def test_a_protected_authority_is_not_reported_as_a_leak():
    """The mirroring rule, and the reason it is not optional.

    `_substitute` refuses a name-shaped candidate in a citation-SHAPED context
    whether or not a citation parsed there. `_surviving_records` masks only what
    the PARSER read — so for a cite the parser cannot read, the write side
    protected the value and the read side reported it. A party-name leak
    quarantines the export, and NO number of Apply-Leak-Fixes passes can ever
    clear it: every pass refuses to scrub, every pass re-reports."""
    z = _pz(["Helen Rasho", "General Motors, LLC"])
    cite = "Accord, Silvio v. General Motors, LLC (2019) 33 Wn.App.2d 114, 120."
    assert P.find_all_citations(cite) == [], "fixture must defeat the parser"
    assert z.apply(cite) == cite, "the authority must survive byte-for-byte"
    assert z.surviving_reals(cite) == [], (
        "the scan reported a value the scrubber is required to leave alone")


def test_the_same_value_standing_elsewhere_is_still_a_leak():
    # The mirror must not become a blanket amnesty: one protected occurrence
    # cannot excuse an unprotected one on the same page.
    z = _pz(["Helen Rasho", "General Motors, LLC"])
    cite = "Accord, Silvio v. General Motors, LLC (2019) 33 Wn.App.2d 114, 120."
    assert z.surviving_reals(cite + " Defendant General Motors, LLC answered.") \
        == ["General Motors, LLC"]


def test_an_ordinary_survivor_is_unaffected():
    z = _pz(["Helen Rasho"])
    assert z.surviving_reals("Plaintiff Helen Rasho testified.")


# ── the guard's window must not straddle two different citations ─────────────

# Taken verbatim from a quarantined export. "Liu" is the DEFENDANT's real name;
# *Kremerman v. White* is a genuine authority the brief cites in full on the
# next line and names again in the argument heading above.
_BRIEF = ("E. Kremerman v. White Is Inapposite - and Actually Supports "
          "Plaintiff.\n"
          "Liu leans heavily on Kremerman v. White (2021) 71 Cal.App.5th 358, "
          "but\nthat decision cuts against her. Angela White testified.")


def _brief_pz():
    return _pz(["Angela White", "White", "Ashley Liu"], casenos=("26STCV08967",))


def test_a_party_name_between_two_citations_is_still_scrubbed():
    """Both windows are 80 characters wide, so they straddled two different
    cites: "Liu" had a " v. " to its left (from the heading) and a "(2021)" to
    its right (from the cite that follows), and the guard read it as a cited
    party. The export shipped the defendant's real name, the leak scan reported
    it, and Apply Leak Fixes could never clear it — every pass refused to scrub
    and every pass re-reported."""
    out = _brief_pz().apply(_BRIEF)
    assert "Liu" not in out, f"the defendant's real name rode out: {out}"


def test_the_cited_party_in_that_same_sentence_is_still_protected():
    out = _brief_pz().apply(_BRIEF)
    assert "Kremerman v. White (2021) 71 Cal.App.5th 358" in out, out


def test_a_short_form_case_name_is_protected_from_its_own_full_cite():
    """A brief names an authority again in an argument heading, with no
    reporter — nothing for the parser to read and no anchor for the guard. One
    opposition shipped a heading reading "Kremerman v. Yardley" while the full
    cite two lines below kept the real name."""
    out = _brief_pz().apply(_BRIEF)
    assert "Kremerman v. White Is Inapposite" in out, (
        f"a cited decision was renamed in the argument heading: {out}")


def test_the_same_surname_elsewhere_is_still_a_party():
    # The pair is protected, not the word: a real person who happens to share a
    # surname with a cited decision is still scrubbed.
    out = _brief_pz().apply(_BRIEF)
    assert "Angela White" not in out, out


def test_a_short_form_repeat_of_our_own_caption_is_not_protected():
    # The caption exemption applies here too: both sides ours means it is this
    # case's own caption, which must still be replaced.
    z = _pz(["Helen Rasho", "General Motors, LLC"])
    page = ("Helen Rasho v. General Motors, LLC (2025) 1 Cal.5th 1.\n"
            "As set out above, Helen Rasho v. General Motors, LLC is this "
            "action.")
    out = z.apply(page)
    assert "Rasho" not in out and "General Motors" not in out, out
