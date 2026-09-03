"""The misspelling sweep reads HOW MANY spellings the document offers, and
WHERE an edit fell.

A lone near-miss of a tracked word — however often it recurs — is as likely a
different name as a slip, so it must be a CLOSE match: the plain scan reach,
none of the degraded or named-party bumps. Several distinct near-misses of one
word are the signature of a scan that keeps mangling that name, and that is
where the real name becomes obvious: there the full reach applies, and one
degree further — a spelling within the fold of an identified variant is a
variant too.

The distance is weighted by position. A wrong letter in the MIDDLE is what OCR
does; a wrong FIRST or LAST letter is more often a different name and costs
1.5. A letter clipped off the front or the back is what a scan does to a word's
edges and costs 0.5, where a letter lost from the middle costs 1. So "thanisl"
is Nathaniel (2.0) and not Daniel (3.0), where a plain count calls them equal.
And a slash or a bar with letters hard against it is a corrupted l, on any
page.

Run:  cd PDF-Linker && python3 -m pytest tests/test_variant_reach.py -v
"""
import pytest

import pdf_linker as P

DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
WESTLAKE = ["Westlake Financial Services, LLC"]


def _pz(*names):
    reg = P._PnFakeRegistry()
    return P.Pseudonymizer(P._pn_build_terms(list(names), [], [], registry=reg),
                           DET, registry=reg)


def _scan(names, text):
    z = _pz(*names)
    return [s for _c, s in z.fuzzy_survivor_scan(z.apply(text))]


# ── the weighted distance ────────────────────────────────────────────────────

def test_the_edges_are_cheap_to_lose_and_dear_to_get_wrong():
    d = P._pn_ocr_distance
    assert d("micheal", "michael") == 1.0          # a middle transposition
    assert d("nichael", "michael") == 1.5          # a wrong first letter
    assert d("michaal", "michael") == 1.0          # a wrong middle letter
    assert d("michae", "michael") == 0.5           # the tail clipped
    assert d("ichael", "michael") == 0.5           # the lead clipped
    assert d("micael", "michael") == 1.0           # a middle letter lost


def test_thanisl_is_nathaniel_and_not_daniel():
    assert P._pn_ocr_distance("thanisl", "nathaniel") == 2.0
    assert P._pn_ocr_distance("thanisl", "daniel") == 3.0
    # …where the plain count cannot tell them apart.
    assert P._pn_osa_distance("thanisl", "nathaniel") == P._pn_osa_distance(
        "thanisl", "daniel")
    got = _scan(["Nathaniel Brooks"],
                "Nathaniel Brooks signed. Later thanisl Brooks called.")
    assert got == ["thanisl"]
    assert _scan(["Daniel Brooks"],
                 "Daniel Brooks signed. Later Thanisl Brooks called.") == []


def test_the_end_penalty_is_dropped_where_the_scan_is_known_to_mangle():
    assert P._pn_ocr_distance("nichael", "michael", ends=False) == 1.0


# ── one variant, or several ──────────────────────────────────────────────────

def test_a_lone_far_variant_beside_a_name_word_is_not_reported():
    # "Wcstlalce" is three slips from the party's own token, which the wide
    # net reaches; alone it is not a close match, repetition is not a second
    # spelling, and standing behind a given name nothing tracks it is
    # somebody else.
    assert _scan(WESTLAKE, "Westlake Financial sued. Robert Wcstlalce paid. "
                           "Robert Wcstlalce again. Wcstlalce signed.") == []


def test_a_lone_far_variant_that_is_always_bare_is_reported():
    # …while one that never shows a given name or a surname beside it is
    # what a mangled party name looks like, and the wide reach applies.
    assert _scan(WESTLAKE, "Westlake Financial sued. Wcstlalce Financial paid. "
                           "Wcstlalce again. Wcstlalce signed.") == ["Wcstlalce"]


def test_a_tracked_given_name_beside_it_is_not_a_companion():
    # "Manuel Vatqual" is the defendant, not somebody else.
    assert _scan(["Manuel Vazquez"],
                 "Manuel Vazquez signed. Print Name: Manuel Vatqual, loan.") == [
        "Vatqual"]
    assert _scan(["Manuel Vazquez"],
                 "Manuel Vazquez signed. Vatqual Ortega, loan officer.") == []


def test_a_lone_close_variant_is_still_reported():
    assert _scan(["Michael Rodgers"],
                 "Michael Rodgers served. Miachael Rodgers again.") == [
        "Miachael"]


def test_a_second_spelling_brings_the_wide_reach_back():
    got = _scan(WESTLAKE, "Westlake Financial sued. Wcstlalce Financial paid. "
                          "Wesnuke Financial too.")
    assert got == ["Wcstlalce", "Wesnuke"]


def test_several_spellings_reach_one_degree_further():
    # "Wcstlelce" is four slips from Westlake and one from the identified
    # variant "Wcstlalce": a variant of a variant.
    got = _scan(WESTLAKE, "Westlake Financial sued. Wcstlalce Financial paid. "
                          "Wesnuke Financial too. Wcstlelce signed.")
    assert got == ["Wcstlalce", "Wesnuke", "Wcstlelce"]


def test_the_second_degree_needs_several_spellings_first():
    # With one variant there is no evidence of a mangling scan, so nothing
    # reaches out from it: "Wcstlelce" is four slips from Westlake and is
    # not a second spelling until a second one exists.
    assert _scan(WESTLAKE, "Westlake Financial sued. Wcstlalce Financial paid. "
                           "Wcstlelce signed.") == ["Wcstlalce"]


# ── two words too far to flag alone ──────────────────────────────────────────

def test_a_pair_near_a_tracked_full_name_is_reported_as_the_pair():
    # "Ionn" is under the length floor and two edits from John; "Smleh" is
    # two from Smith. Together they are one person.
    got = _scan(["John Smith"],
                "John Smith signed. Later Ionn Smleh signed the guaranty.")
    assert got == ["Ionn Smleh"]


def test_a_wrapped_pair_is_reported_on_one_line():
    got = _scan(["John Smith"],
                "John Smith signed. Later Ionn\n12  Smleh signed.")
    assert got == ["Ionn Smleh"]


def test_a_pair_needs_both_words_near():
    assert _scan(["John Smith"], "John Smith signed. Later Joan Baker signed.") == []


def test_a_pair_reaches_a_three_word_name_by_its_first_and_last():
    assert _scan(["Steven Wayne Burt"],
                 "Steven Wayne Burt signed. Stevan Burtt objected.") == [
        "Stevan Burtt"]


def test_a_pair_with_one_word_already_scrubbed_is_the_single_words_row():
    # "John" is faked in the export, so the pair standing there is our
    # stand-in beside "Smleh", and "Smleh" is the row.
    assert _scan(["John Smith"], "John Smith signed. Later John Smleh signed.") == [
        "Smleh"]


def test_the_tools_own_near_spellings_are_not_variants():
    # `_pn_name_variants` registers "Rodgerrs" beside "Rodgers"; a survivor
    # near it is still ONE spelling of one word, not two.
    assert _scan(["Michael Rodgers"],
                 "Michael Rodgers served. Rodgerz signed.") == ["Rodgerz"]


# ── the slash ────────────────────────────────────────────────────────────────

def test_a_slash_is_a_corrupted_letter_on_a_clean_page():
    got = _scan(["Thomas Wilson"],
                "Thomas Wilson signed. Mr. Wi/son left. Da|ey too. The and/or "
                "clause applies.")
    assert got == ["Wi/son"]


def test_the_prefill_reads_the_slash_the_same_way():
    assert _pz("Thomas Wilson").alias_suggestion("Wi/son") == "Wilson"
    assert P._PN_DIGIT_LETTERS["/"] == "l" and P._PN_DIGIT_LETTERS["|"] == "l"


def test_a_slash_word_is_reported_whole_not_as_its_halves():
    # Read by the clean tier, "Natha/iel" is two halves, and the front one
    # reports as a clipped spelling of the name it is really the whole of.
    got = _scan(["Nathaniel Brooks"],
                "Nathaniel Brooks signed. Natha/iel Brooks called.")
    assert got == ["Natha/iel"]


def test_a_trailing_slash_is_a_corrupted_last_letter():
    got = _scan(["Nathaniel Brooks"],
                "Nathaniel Brooks signed. Nathanie/ Brooks called.")
    assert got == ["Nathanie/"]
