"""The leak scan must not be quadratic in the document, and must not go quiet.

A 130-page motion in a real folder spent 82 minutes inside one file's scrub and
scan block, writing nothing to `pdf_linker.log` the whole time, and the run then
stopped there — indistinguishable from a hang. Profiling the shape of that
folder (a few hundred terms, 220 master-KEEP values, most of them ordinary
vocabulary) put 19 of every 24 seconds in ONE line: `_in_name_run` searched
`text[:s]` for a `$`-anchored match, so every occurrence of a soft keep copied
and re-scanned the whole export. The master sheet keeps words like "and", "the"
and "court", a long filing carries thousands of them, and the product is
quadratic.

Three things are pinned here, and correctness comes first: the two rewritten
primitives must answer exactly what the code they replaced answered, the memos
must not outlive the state they were computed against, and the cost must scale
with the document rather than with its square.

Run:  cd PDF-Linker && python3 -m pytest tests/test_scan_cost.py -v
"""
import random
import re
import time

import pdf_linker as P


# ── _PnSpanIndex: the same answers as the walk it replaced ──────────────────

def _naive_overlaps(spans, s, e):
    return any(s < pe and ps < e for ps, pe in spans)


def _naive_overlaps_wider(spans, s, e):
    return any(s < pe and ps < e and not (s <= ps and pe <= e)
               for ps, pe in spans)


def test_span_index_agrees_with_the_walk_it_replaced():
    rng = random.Random(11)
    for trial in range(200):
        spans = []
        for _ in range(rng.randrange(0, 12)):
            a = rng.randrange(0, 40)
            spans.append((a, a + rng.randrange(0, 8)))
        idx = P._PnSpanIndex(spans)
        assert bool(idx) == bool(spans)
        assert len(idx) == len(spans)
        for _ in range(60):
            s = rng.randrange(0, 45)
            e = s + rng.randrange(0, 10)
            assert idx.overlaps(s, e) == _naive_overlaps(spans, s, e), (
                trial, spans, s, e)
            assert idx.overlaps_wider(s, e) == _naive_overlaps_wider(
                spans, s, e), (trial, spans, s, e)


def test_span_index_handles_nesting_and_zero_width():
    # A party term nested inside a longer one, which is the shape
    # `party_wider_only` exists to tell apart: a match the kept span COVERS
    # releases nothing, one reaching past it still does.
    idx = P._PnSpanIndex([(10, 20), (12, 15), (25, 30)])
    assert idx.overlaps(12, 15)
    assert not idx.overlaps_wider(9, 21)    # both inner spans are covered
    assert idx.overlaps_wider(11, 21)       # (10,20) starts back past 11
    assert idx.overlaps_wider(12, 16)       # (10,20) reaches back past 12
    assert not idx.overlaps(20, 25)         # half-open: neither touches
    assert not idx.overlaps(5, 5)
    assert P._PnSpanIndex([]).overlaps(0, 100) is False


# ── _in_name_run: the same answers as the slicing regex ─────────────────────

def _old_in_name_run(text, s, e):
    """Verbatim copy of the implementation this replaced — the oracle."""
    r = re.match(r"[ \t]+([A-Za-z][A-Za-z.'’&\-]*)", text[e:])
    if r and P._pn_is_name_word(r.group(1)):
        return True
    l = re.search(r"([A-Za-z][A-Za-z.'’&\-]*)[ \t]+$", text[:s])
    return bool(l and P._pn_is_name_word(l.group(1)))


_NEIGHBOURS = ["", " ", "  ", "\t", "\n", " \n", "\n ", ", ", ". ", " .", "-",
               " O'Brien ", " Equipment ", " the ", " .Smith ", " A ", " &",
               " Cal ", "Cal", " 123 ", " ,", " St. ", "'’", "   \n"]


def test_in_name_run_agrees_with_the_regex_it_replaced():
    z = P.Pseudonymizer([], [])
    rng = random.Random(5)
    for _ in range(4000):
        left = "".join(rng.choice(_NEIGHBOURS) for _ in range(rng.randrange(0, 3)))
        right = "".join(rng.choice(_NEIGHBOURS) for _ in range(rng.randrange(0, 3)))
        word = rng.choice(["Cal", "Doe", "and", "Law", "Green"])
        text = left + word + right
        s, e = len(left), len(left) + len(word)
        assert z._in_name_run(text, s, e) == _old_in_name_run(text, s, e), (
            repr(text), s, e)


def test_in_name_run_reads_only_the_neighbouring_words():
    # The point of the rewrite: cost is proportional to one word, not to the
    # distance from the start of the export. Both calls answer the same thing;
    # only the second used to copy 400 KB to do it.
    z = P.Pseudonymizer([], [])
    near = "Equipment Cal Ranch"
    far = ("x " * 200_000) + near
    s = far.index("Cal")
    assert z._in_name_run(far, s, s + 3) is True
    assert z._in_name_run(near, 10, 13) is True


# ── the memos must not outlive the state they were computed against ─────────

def _pz(names, keeps=()):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), [], [], registry=reg)
    z = P.Pseudonymizer(terms, list(P._PN_DEFAULT_DETECTORS), registry=reg)
    z.keep_soft = set(keeps)
    return z


def test_a_keep_typed_after_the_first_scan_still_takes_effect():
    # The memo keys on `_scan_state_key`, not on the text alone. `--fix-leaks`
    # and the tests both set the keep sets on a live Pseudonymizer and ask the
    # same question again, and every COUNT can stay where it was — so a memo
    # keyed on sizes would answer from before the operator's decision.
    text = "Filed through filevineapp.com today."
    z = _pz(["Michael Patrick Carroll"])
    z.apply(text)
    assert "filevineapp.com" in z.surviving_reals(text)
    z.keep_soft = {"filevineapp.com"}
    assert z.surviving_reals(text) == []
    z.keep_soft = set()                      # ...and back again
    assert "filevineapp.com" in z.surviving_reals(text)


def test_swapping_one_keep_for_another_invalidates_the_memo():
    # Same sizes, different values — the case a length-only key would miss.
    text = "Filed through filevineapp.com today."
    z = _pz(["Michael Patrick Carroll"], keeps={"filevineapp.com"})
    z.apply(text)
    assert z.surviving_reals(text) == []
    z.keep_soft = {"somethingelse.com"}
    assert "filevineapp.com" in z.surviving_reals(text)


def test_the_cure_and_the_scan_still_agree_through_the_memo():
    # `_surviving_records` is the SINGLE eligibility rule `scrub_survivors` and
    # `surviving_reals` share; memoizing it must not let the two drift.
    text = "Contact Michael Patrick Carroll about the matter."
    z = _pz(["Michael Patrick Carroll"])
    z.apply("seed")
    before = set(z.surviving_reals(text))
    cured = z.scrub_survivors(text)
    assert before                              # the value really was standing
    assert not set(z.surviving_reals(cured)) & before


# ── and the cost scales with the document, not with its square ──────────────

def _timed_scan(pages, keeps):
    line = ("Plaintiff Helen Rasho alleges that the audit and authentication "
            "of business records in this court is disputed, and counsel of "
            "record denies each allegation.\n")
    body = line * (28 * pages)
    z = _pz(["Helen Rasho", "Justin Beimforde"], keeps=keeps)
    t = time.time()
    z._keep_spans(body)
    return time.time() - t


def test_the_keep_pass_is_not_quadratic_in_the_document():
    """Quadrupling the export must not multiply the keep pass by ~16.

    The keeps here are the shape a real master sheet holds — ordinary
    vocabulary, standing thousands of times in a long filing — which is what
    made the old `text[:s]` search a product of two numbers that both grow with
    the document. The bound is deliberately loose (a linear pass would be ~4x,
    the quadratic one measured ~16x and worse); this asserts the SHAPE, so it
    stays meaningful on a slow or loaded machine.
    """
    keeps = {"and", "the", "of", "court", "audit", "business", "counsel"}
    small = _timed_scan(6, keeps)
    large = _timed_scan(24, keeps)
    assert large < max(small, 0.02) * 10, (small, large)
