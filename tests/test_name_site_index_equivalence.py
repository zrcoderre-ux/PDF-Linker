"""The shared word-site index yields EXACTLY what the per-word scan yielded.

`_pn_full_name_intro` and `_pn_has_name_companion` each compiled a pattern for
their candidate word and ran `finditer` over the whole export, and the fuzzy
sweep asks both of every near-miss it finds — so the cost was (candidate
words) x (length of the document). Profiled at four times the body,
`_pn_full_name_intro` alone was 2.44 s of a 5.94 s sweep and the sweep grew
x2.5 per doubling; one delivered folder paid 20 minutes of leak scans on a
218-page declaration where the 84-page one beside it paid 52 seconds.

The index is only worth having if it is EXACT. A site it misses is a name
reported as a party's misspelling when the document says it is a different
person — which the alias pre-fill then answers with `~Party`, merging a
stranger into the party on the next pass. A site it invents is the reverse: a
real leak going quiet. So this test pins the new path against a verbatim copy
of the regex it replaced, over randomized text.

Run:  cd PDF-Linker && python3 -m pytest tests/test_name_site_index_equivalence.py -v
"""
import random
import re

import pdf_linker as P


def reference(text, word):
    """The exact scan `_pn_word_occurrences` replaced, kept verbatim."""
    rx = re.compile(r"(?<![\w'’])" + re.escape(word) + r"(?![\w'’])",
                    re.IGNORECASE)
    return [(m.start(), m.end()) for m in rx.finditer(text)]


WORDS = ["Smith", "Smith-Jones", "O'Brien", "O’Brien", "Vazquez", "Davis",
         "MIDLAND", "midland", "Ardeshirpour-Zartoshti", "A", "Ph", "Doe",
         "Rasho's", "Rasho’s", "co-op", "St.", "3M", "naïve", "Zürich"]


class TestItYieldsTheSameSites:
    def test_the_worked_shapes_agree(self):
        text = ("Smith-Jones served O'Brien and O’Brien. smith wrote to "
                "SMITH-JONES; Smith. Midland States Bank, midland, MIDLAND\n"
                "13  Davis Smith testified. Rasho's motive. Rasho’s co-op.\n"
                "naïve Zürich 3M St. Doe v. Doe A. Ph.D. AB-Smith Smithy")
        for w in WORDS:
            assert list(P._pn_word_occurrences(text, w)) == reference(text, w), w

    def test_randomized_bodies_agree(self):
        rng = random.Random(20260910)
        alphabet = "abcdefgHIJKLM'’-. ,\n\t;:()0123"
        for trial in range(200):
            text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 400)))
            for _ in range(6):
                i = rng.randrange(max(1, len(text)))
                word = text[i:i + rng.randint(1, 9)]
                assert (list(P._pn_word_occurrences(text, word))
                        == reference(text, word)), (trial, repr(text), repr(word))

    def test_a_word_the_text_does_not_carry_yields_nothing(self):
        assert list(P._pn_word_occurrences("alpha beta", "gamma")) == []

    def test_even_the_degenerate_word_agrees(self):
        """No caller passes an empty word, and the index still reproduces what
        the scan did with one — an exception would need a reason, and the
        equivalence is the whole safety argument."""
        for text in ("alpha beta", ""):
            for w in ("", "   ", "\n"):
                assert (list(P._pn_word_occurrences(text, w))
                        == reference(text, w)), (repr(text), repr(w))

    def test_a_hyphenated_candidate_is_still_asked_about(self):
        """The index keys on the LEADING run, so the rest is verified against
        the text — without that a hyphenated candidate goes silently unasked,
        which is a name left standing."""
        text = "Smith-Jones and Smith-Brown and Smith"
        assert list(P._pn_word_occurrences(text, "Smith-Jones")) == [(0, 11)]
        # …and a bare "Smith" still matches inside each of them, because the
        # lookarounds do not treat a hyphen as inside a word. That is the
        # scan's own behaviour and the index must not quietly change it.
        assert (list(P._pn_word_occurrences(text, "Smith"))
                == reference(text, "Smith"))

    def test_a_word_not_opening_on_a_word_character_still_answers(self):
        """The index holds word RUNS, so a word opening on punctuation is not
        in it — and its occurrences are still real. Narrowing the function on
        "no caller does that" is the stacked guess; it falls back instead."""
        text = "the (x)foo bar and )foo baz"
        for w in (")foo", "(x)foo", "-lead"):
            assert list(P._pn_word_occurrences(text, w)) == reference(text, w), w

    def test_the_right_lookahead_still_holds(self):
        assert list(P._pn_word_occurrences("Smithy", "Smith")) == []
        assert list(P._pn_word_occurrences("Smith's", "Smith")) == []
        assert list(P._pn_word_occurrences("Smith’s", "Smith")) == []


class TestTheMemoIsAPair:
    def test_it_caps_at_the_alternating_pair(self):
        P._pn_word_sites.memo.clear()
        for body in ("alpha beta", "gamma delta", "epsilon zeta"):
            P._pn_word_sites(body)
        assert len(P._pn_word_sites.memo) <= 2

    def test_the_same_body_is_not_rebuilt(self):
        P._pn_word_sites.memo.clear()
        body = "alpha beta gamma"
        assert P._pn_word_sites(body) is P._pn_word_sites(body)


class TestTheCallersAgreeToo:
    """The index is exact, so the two helpers reading it must be unmoved."""

    def _args(self):
        return (frozenset({"rodgers"}), frozenset({"keswick"}),
                frozenset({"served", "wrote"}))

    def test_full_name_intro_finds_the_follower(self):
        tracked, known, lower = self._args()
        text = "The witness Davis Smith testified at the hearing."
        assert P._pn_full_name_intro(text, "Davis", tracked, known, lower) == "Smith"

    def test_full_name_intro_is_silent_without_one(self):
        tracked, known, lower = self._args()
        text = "The witness Davis testified at the hearing."
        assert P._pn_full_name_intro(text, "Davis", tracked, known, lower) == ""

    def test_name_companion_reads_both_sides(self):
        tracked, known, lower = self._args()
        assert P._pn_has_name_companion(
            "Robert Vatqual signed", "Vatqual", tracked, known, lower)
        assert not P._pn_has_name_companion(
            "the Vatqual was served", "Vatqual", tracked, known, lower)
