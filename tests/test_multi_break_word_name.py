"""A scan does not break a printed word ONCE and stop.

`_pn_word_breaks` matches a word written with one stray break in it — the kern
gap extraction read as a space, the speck a scan dropped inside a word. One
break was the whole tolerance, and a small-type Bates stamp does not oblige:

    Chadwick-Castellano 000253   ->  Chadwick-Hepworth 000253     (faked)
    Chadwick-Castel lano 000250  ->  Chadwick-Hepworth 000250     (faked, 1 break)
    Chadwick-Cas tel lano 000249 ->  unchanged                    (2 breaks)
    Chadwick-Cas tel la no 000251 -> unchanged                    (3 breaks)

A delivered 177-page exhibit set carried exactly that. The stamp read whole on
50 pages and the plaintiff's surname was faked on every one of them; it came
apart on 52 others and the REAL NAME shipped in the clear — with every leak
tier silent, because a whole-word term cannot match the broken spelling and
`_surviving_records` scans with that same pattern, so replacement and detection
were blind together and the gate passed the file. Two pages carry both readings
of the doubled layer side by side, which is the shape that gave it away:

    Chadwick-Hepworth Chadwick-Ca! tell ano 000256

The corroboration does not weaken with the number of breaks, because it was
never the pieces: it is the CONCATENATION, and "Cas tel lano" spells the party's
own token exactly. What weakens is the word left to concatenate, so a split
into three or more pieces is offered only from `_PN_SPLIT_MULTI_MIN` letters up.

Measured over 695 surnames, 51,405 break branches and 2.8 MB of real filings
and this repo's own prose, with `cap_only` enforced as the scan enforces it:
ZERO false matches, the same count the one-break rule measured.

Residual, and deliberate: a break that also SUBSTITUTES a character
("Cas teI lano", "Ca! tel lano" — the l read as I or !) is the fuzzy scan's
business, reported for review and never repaired. Ten of that batch's 52 broken
stamps are of that kind and are NOT closed here.

Run:  cd PDF-Linker && python3 -m pytest tests/test_multi_break_word_name.py -v
"""
import pytest

import pdf_linker as P

PARTIES = ["Kerrigan Castellano"]

# The stamp as the delivered export actually carries it, verbatim.
STAMPS = (
    "                        Chadwick-Castellano 000253\n"
    "                        Chadwick-Castel lano 000250\n"
    "                        Chadwick-Castell ano 000255\n"
    "                        Chadwick-Cas tel lano 000249\n"
    "                        Chadwick-Cas tel la no 000251\n"
)


def _run(names, text):
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(names, [], [], registry=reg),
                        {}, registry=reg)
    return z, z.apply(text)


# ── the leak ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("leaked", [
    "Cas tel lano", "Cas tel la no", "Castel lano", "Castell ano", "Castellano",
])
def test_a_multiply_broken_name_does_not_reach_the_export(leaked):
    _z, out = _run(PARTIES, STAMPS)
    assert leaked not in out, out


def test_no_fragment_of_the_party_survives():
    _z, out = _run(PARTIES, STAMPS)
    low = out.lower()
    for real in ("castellano", "cas tel", "tel lano", "tel la no"):
        assert real not in low, (real, out)


def test_every_stamp_still_carries_its_own_number():
    """The break tolerance replaces the NAME. A branch that ate the digits
    beside it would be the reduced weld pass's old failure — a match spanning
    a printed boundary, deleting the text between two real words."""
    _z, out = _run(PARTIES, STAMPS)
    for n in ("000253", "000250", "000255", "000249", "000251"):
        assert n in out, (n, out)


# ── the shape of a split ────────────────────────────────────────────────────

def test_the_one_break_splits_are_still_offered_first():
    """An intact-but-once-broken spelling must be preferred over a reading
    that assumes the scan fell apart three times."""
    splits = P._pn_word_splits("Castellano")
    assert [len(p) for p, _b in splits] == sorted(len(p) for p, _b in splits)
    assert len(splits[0][0]) == 2


def test_a_split_reaches_the_observed_spellings():
    got = {"".join(f" {p}" for p in pieces).strip()
           for pieces, _b in P._pn_word_splits("Castellano")}
    assert "Cas tel lano" in got
    assert "Cas tel la no" in got


def test_a_short_word_is_never_cut_into_three():
    """Cutting a five-letter name into three leaves mostly single letters,
    which corroborate nothing."""
    for short in ("Vada", "Kimbe"):
        assert all(len(p) <= 2 for p, _b in P._pn_word_splits(short)), short


def test_the_break_count_is_bounded():
    for pieces, breaks in P._pn_word_splits("Ardeshirpour"):
        assert len(pieces) <= P._PN_WORD_BREAK_MAX + 1
        assert len(breaks) == len(pieces) - 1


def test_every_cut_falls_between_letters():
    for pieces, _b in P._pn_word_splits("Ardeshirpour-Zartoshti"):
        for a, b in zip(pieces, pieces[1:]):
            assert a[-1].isalpha() and b[0].isalpha(), pieces


def test_a_split_of_nothing_but_ordinary_words_is_refused():
    """The rule that keeps "No where" off "Nowhere", asked of every piece."""
    for pieces, _b in P._pn_word_splits("Inaction"):
        assert not all(P._pn_is_generic_token(p.lower()) for p in pieces), pieces


def test_a_trailing_single_letter_still_takes_a_mark_only():
    """"Debora H" is how a filing writes a middle initial — a SPACE there
    would rewrite Debora H. Smith as Deborah. A single letter with pieces
    still to come is not that shape and keeps its space ("Cas tel la no")."""
    for pieces, breaks in P._pn_word_splits("Castellano"):
        if len(pieces[-1]) == 1:
            assert breaks[-1] == P._PN_WORD_BREAK_MARK, pieces
    mid = next(b for p, b in P._pn_word_splits("Castellano")
               if p == ("Cas", "tell", "a", "no"))
    assert mid[2] == P._PN_WORD_BREAK


# ── the prefilter must not silently drop the term ───────────────────────────

@pytest.mark.parametrize("text", [
    "Chadwick-Cas tel lano 000249", "Chadwick-Cas tel la no 000251",
])
def test_the_lead_index_holds_every_broken_run(text):
    """`_leads_present` is EXACT by construction: a term whose lead word is
    absent is never scanned. Index pairs alone and the pattern still tolerates
    the break and is never asked — the fix becomes dead code."""
    pz = P.Pseudonymizer.__new__(P.Pseudonymizer)
    assert "castellano" in P.Pseudonymizer._lead_words(pz, text)


def test_a_harvested_name_is_still_never_broken():
    """A split spelling is a guess about how a printed word came apart, and
    stacking it on a guess about who the party is doubles the ways it can be
    wrong. The operator's own list is the one place the name is not in doubt."""
    assert not P._pn_term_is_breakable("person-token", "prescan")
    assert P._pn_term_is_breakable("person-token", "spreadsheet")
