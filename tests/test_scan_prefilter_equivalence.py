"""The speed-ups are EXACT: every fast path answers precisely what the pass
it replaced answered.

Four of them, each a differential test against the slow form it stands in
for: the lead-word prefilter before a term's pattern runs (`_leads_present`,
switched off through `_PN_LEAD_PREFILTER` to obtain the reference), the
per-distinct-case-name citation pass, the letter-set floor on the OCR
distance, and the joined-body Context search. A speed-up that changed one
answer would be a scrub that faked less or a scan that reported less, which
is the one trade this project never makes for time.

Run:  cd PDF-Linker && python3 -m pytest tests/test_scan_prefilter_equivalence.py -v
"""
import logging
import random
import re

import pytest

import pdf_linker as P

log = logging.getLogger("test")

NAMES = ["Vadim Sarkisyan", "Helen Rasho", "Sara Ardeshirpour-Zartoshti",
         "Midland States Bank", "Mr. Kool's Collision, LLC", "Sean O'Brien",
         "Rachel Green's Trust", "Manuel Vazquez", "Ken Cranston"]
TEXT = ("V ADIM SARKISY AN and SARKISYA.N signed. M idland States Bank sued. "
        "Helen Rasho's motion; RASHO'S reply. Sara Ardeshirpour- Zartoshti and "
        "Dr. Ardeshirpour examined the plaintiff. Sean O’Brien and MR. KOOLS "
        "COLLISION, LLC appeared; RACHEL GREEN’S TRUST intervened. Vazquez Manuel "
        "signed the table row, and Ken left. SmithDecl. ¶ 4 states otherwise.\n"
        "The Court relied on Kremerman v. White (2021) 71 Cal.App.5th 358, 373 "
        "and Kremerman v. White, supra; see also Ewald v. Nationstar Mortgage, "
        "LLC (2017) 13 Cal.App.5th 947; Kremerman v. White again.\n")


def _pz(names=NAMES):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), [], [], registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    z = P.Pseudonymizer(terms, det, registry=reg)
    z.keep_soft = {"and", "the", "court", "motion"}
    return z


def _with_prefilter(flag):
    class _Ctx:
        def __enter__(self):
            self.old = P._PN_LEAD_PREFILTER
            P._PN_LEAD_PREFILTER = flag
        def __exit__(self, *a):
            P._PN_LEAD_PREFILTER = self.old
    return _Ctx()


def _cands(z, text):
    return [(p, s, e, r["real"]) for p, s, e, r in z._term_cands(text)]


def test_the_lead_prefilter_changes_no_candidate():
    """Broken spellings ("V ADIM", "SARKISYA.N", "M idland"), wrap-split
    hyphens, possessives in both marks, all-caps, surname-first, a nickname
    and a weld-follow declarant all match exactly as they did."""
    z = _pz()
    z.register_declarant_refs(TEXT)          # adds a follow (weld) term
    with _with_prefilter(False):
        slow = _cands(z, TEXT)
    z._lead_memo = []
    with _with_prefilter(True):
        fast = _cands(z, TEXT)
    assert fast == slow and slow, len(slow)
    assert any(r.lower().startswith("vadim") for _p, _s, _e, r in fast)


def test_the_prefilter_skips_most_terms_on_an_ordinary_page():
    z = _pz()
    kept = z._leads_present(TEXT, z.terms, lambda t: t.lead)
    assert len(kept) < len(z.terms) // 2, (len(kept), len(z.terms))


def test_keep_spans_and_survivors_agree_with_the_full_scan():
    z = _pz()
    out = "Helen Rasho was left standing here. " + z.apply(TEXT)
    with _with_prefilter(False):
        slow_keep = z._keep_spans(out)
        z._survivor_memo = {}
        slow_surv = z._surviving_records(out)
    z._keep_span_memo = {}
    z._survivor_memo = {}
    z._lead_memo = []
    with _with_prefilter(True):
        fast_keep = z._keep_spans(out)
        fast_surv = z._surviving_records(out)
    assert fast_keep == slow_keep
    assert fast_surv == slow_surv
    assert any("rasho" in v.lower() for v in z.surviving_reals(out))


def test_a_weld_follow_term_is_never_prefiltered():
    z = _pz()
    z.register_declarant_refs("Smith Decl. ¶ 2; SmithDecl. ¶ 4")
    follows = [t for t in z.terms if t.lead is None
               and t.category in P._PN_LEAD_CATS]
    assert follows, "the declarant weld term should carry no lead"
    assert all(t in z._leads_present("nothing here", z.terms, lambda t: t.lead)
               for t in follows)


def test_citation_spans_are_distinct_and_cover_every_repeat():
    z = _pz()
    text = TEXT * 3
    spans = z._protected_citation_spans(text)
    assert len(spans) == len(set(spans))
    # every "Kremerman v. White" — full, supra, bare repeat — sits in a span
    for m in re.finditer(r"Kremerman v\. White", text):
        assert any(s <= m.start() and m.end() <= e for s, e in spans), m.start()
    # and the memo hands back the same answer
    assert z._protected_citation_spans(text) == spans


@pytest.mark.parametrize("seed", range(3))
def test_the_letter_set_floor_never_refuses_a_pair_within_reach(seed):
    """`_pn_ocr_distance_within` may only say False where the full distance
    says False: the floor is a bound on the distance, never an estimate."""
    rnd = random.Random(seed)
    letters = "abcdefghijklmnopqrstuvwxyz"
    for _ in range(4000):
        a = "".join(rnd.choice(letters[:9]) for _ in range(rnd.randint(5, 10)))
        b = list(a)
        for _ in range(rnd.randint(0, 4)):
            op = rnd.choice("sidt")
            i = rnd.randrange(len(b))
            if op == "s":
                b[i] = rnd.choice(letters[:9])
            elif op == "i":
                b.insert(i, rnd.choice(letters[:9]))
            elif op == "d" and len(b) > 5:
                del b[i]
            elif op == "t" and i + 1 < len(b):
                b[i], b[i + 1] = b[i + 1], b[i]
        b = "".join(b)
        for k in (1, 1.5, 2, 3):
            for ends in (True, False):
                full = (a == b or (min(len(a), len(b)) >= 5
                        and P._pn_ocr_distance(b, a, ends) <= k))
                assert P._pn_ocr_distance_within(b, a, k, min_len=5, ends=ends) == full, (a, b, k)


def _old_scan(lines, lowers, nl, lo_want, hi_want, bounded):
    first = None
    rx = re.compile(r"(?<!\w)" + re.escape(nl) + r"(?!\w)") if bounded else None
    for k, low in enumerate(lowers):
        if lo_want is not None and not (lo_want <= k <= hi_want):
            continue
        if rx is not None:
            m = rx.search(low)
            j = m.start() if m else -1
        else:
            j = low.find(nl)
        if j < 0:
            continue
        at = lines[k][0] + j
        if first is None:
            first = at
        if lines[k][2]:
            return at
    return first


def test_the_joined_context_search_matches_the_per_line_one():
    body = ("====== Page 1 ======\n 1  MOTION OF HELEN RASHO\n 2  Helen Rasho "
            "moved to compel. Rasho's counsel, Sara Ardeshirpour-\n 3  Zartoshti, "
            "signed it. The Rasho\n 4  motion was denied; rasho appealed.\n"
            " 5  Charge of discrimination.\n 6  CHARGE OF DISCRIMINATION\n")
    parsed = P._pn_body_lines(body)
    lines, lowers, text, ends, _locs = P._pn_context_prep(parsed)
    for needle in ("Helen Rasho", "Rasho", "rasho", "Charge", "Zartoshti",
                   "Ardeshirpour-Zartoshti", "counsel, sara", "absent", ""):
        nl = needle.lower()
        for within in (None, (0, 1, 0, 0), (2, 3, 0, 0), (1, 5, 1, 0)):
            lo, hi = within[:2] if within else (None, None)
            for bounded in (True, False):
                want = _old_scan(lines, lowers, nl, lo, hi, bounded)
                quote, site = P._pn_context_hit(parsed, needle, within=within,
                                                bounded_only=bounded)
                # the same first-hit rule: a hit iff the old scan found one
                assert bool(quote) == (want is not None and needle != ""), (
                    needle, within, bounded, want, quote)


# ── the screen asks about EVERY word, not the first ─────────────────────────
# A case has a hundred parties sharing twenty given names, each with its
# near-miss spellings minted beside it, so on a page that says "Maria" once
# the lead screen let every person term opening on Maria — and every variant
# of one — run its whole pattern over the whole page. Every letter run of the
# real has to stand on the page for the pattern to match (`_pn_term_words`),
# and a KEEP value's plainer pattern needs the same, so both are screened on
# all their words now. Exact, and pinned as such: the reference is the
# unscreened pass, through the same switch.

def test_a_term_whose_later_word_is_absent_is_skipped():
    z = _pz(["Helen Rasho", "Helen Tavquen", "Helen Quillmark-Tavquen"])
    page = "Helen Rasho signed. Helen said so. Tavquen else did."
    kept = {t.real for t in z._words_present(page, z.terms, lambda t: t.words)}
    assert "Helen Rasho" in kept
    assert "Helen Quillmark-Tavquen" not in kept    # "quillmark" is not there
    # "Helen Tavquen" has both runs on the page (apart), so it is scanned —
    # the screen only ever refuses, the pattern still decides.
    assert "Helen Tavquen" in kept
    assert P._pn_term_words("Sean O'Brien", "person") == ("sean", "o", "brien")
    assert P._pn_term_words("25STCV37838", "case_number") is None


def test_the_all_words_screen_changes_no_answer_on_random_pages():
    """Randomized differential over the three passes that read the screen:
    pages built from the fixture's own spellings (broken, wrapped, possessive,
    glued, all-caps), with keeps that are sometimes on the page and sometimes
    not, and a term list carrying names that share a given name with a real
    party but never appear."""
    rnd = random.Random(23)
    pieces = [s.strip() for s in re.split(r"[.;]\s*", TEXT) if s.strip()]
    absent = ["Vadim Nobody", "Helen Elsewhere", "Sara Nowhere", "Manuel Absent"]
    for trial in range(12):
        z = _pz(NAMES + absent)
        z.keep_soft = {"and", "the", "court", "motion", "signed", "unseen"}
        z.keep_nuclear = {"reply", "trust", "neverhere"}
        page = " ".join(rnd.choice(pieces) for _ in range(rnd.randint(2, 6)))
        if rnd.random() < 0.5:
            page = "Helen Rasho was left standing. " + page
        with _with_prefilter(False):
            z._lead_memo = []; z._keep_span_memo = {}; z._survivor_memo = {}
            slow = (_cands(z, page), z._keep_spans(page),
                    [r["real"] for r in z._surviving_records(page)])
        with _with_prefilter(True):
            z._lead_memo = []; z._keep_span_memo = {}; z._survivor_memo = {}
            fast = (_cands(z, page), z._keep_spans(page),
                    [r["real"] for r in z._surviving_records(page)])
        assert fast == slow, (trial, page)
        skipped = [t for t in z.terms
                   if t.words and not P._pn_words_in(t.words, z._lead_words(page))]
        assert skipped, "the screen should refuse the absent names"


def test_a_keep_absent_from_the_page_is_not_scanned(monkeypatch):
    z = _pz()
    z.keep_soft = {"court", "unseenword"}
    page = "The court took the motion under submission."
    seen = []
    orig = z._compiled

    def spy(pattern, flags):
        seen.append(pattern)
        return orig(pattern, flags)
    monkeypatch.setattr(z, "_compiled", spy)
    z._keep_span_memo = {}
    spans = z._keep_spans(page)
    assert spans, "the present keep is still found"
    assert not any("unseenword" in p for p in seen)
    assert any("court" in p for p in seen)


# ── a whole-text scan is run chunk by chunk, and yields the same matches ────
# The constants are SHRUNK so a page of text is dozens of chunks and every
# boundary case is met: a name wrapped across a chunk cut, a gutter seam at
# one, a match that would reach a window's end, a long run of whitespace
# that makes a window unsafe, a glued first word behind a boundary, and
# matches abutting one another. The invariant the shrunken constants must
# keep is the one the production ones keep: a match longer than the overlap
# holds a whitespace run at least as long as the unsafe threshold.

def _with_chunking(flag, chunk=120, overlap=200, max_real=60, max_words=6,
                   long_ws=12):
    assert (overlap - max_real - max_words * 6) / max_words > long_ws

    class _Ctx:
        def __enter__(self):
            self.old = (P._PN_CHUNK_SCAN, P._PN_SCAN_CHUNK, P._PN_SCAN_OVERLAP,
                        P._PN_SCAN_MAX_REAL, P._PN_SCAN_MAX_WORDS,
                        P._PN_SCAN_LONG_WS_RE)
            P._PN_CHUNK_SCAN = flag
            P._PN_SCAN_CHUNK, P._PN_SCAN_OVERLAP = chunk, overlap
            P._PN_SCAN_MAX_REAL, P._PN_SCAN_MAX_WORDS = max_real, max_words
            P._PN_SCAN_LONG_WS_RE = re.compile(r"\s{%d,}" % long_ws)

        def __exit__(self, *a):
            (P._PN_CHUNK_SCAN, P._PN_SCAN_CHUNK, P._PN_SCAN_OVERLAP,
             P._PN_SCAN_MAX_REAL, P._PN_SCAN_MAX_WORDS,
             P._PN_SCAN_LONG_WS_RE) = self.old
    return _Ctx()


def _fresh(z):
    z._lead_memo = []; z._keep_span_memo = {}; z._survivor_memo = {}
    z._scan_plan_memo = []


def _random_body(rnd):
    """Prose with the fixture's spellings, wraps, gutter seams, a stretch of
    whitespace long enough to make a window unsafe, and names glued behind
    lower-case runs, so chunk cuts land inside every shape."""
    bits = [s.strip() for s in re.split(r"[.;]\s*", TEXT) if s.strip()]
    filler = "the parties agreed that the work would proceed on the schedule".split()
    out = []
    for _ in range(rnd.randint(30, 60)):
        r = rnd.random()
        if r < 0.25:
            out.append(rnd.choice(bits))
        elif r < 0.35:
            out.append("Helen\n" + rnd.choice(["", " 7  ", "12  "]) + "Rasho")
        elif r < 0.40:
            out.append("Midland\nStates Bank")
        elif r < 0.45:
            out.append(" " * rnd.randint(8, 40))
        elif r < 0.48:
            out.append("ofQUILLMARK")
        elif r < 0.52:
            out.append("Ken Cranston Ken")
        else:
            out.append(" ".join(rnd.choice(filler) for _ in range(rnd.randint(2, 9))))
        out.append(rnd.choice([" ", "\n", ".\n", " and "]))
    return "".join(out)


def test_the_chunked_scan_yields_exactly_the_whole_scan(seed=None):
    rnd = random.Random(31)
    for trial in range(30):
        z = _pz(NAMES + ["Quillmark Builders LLC", "Helen Nowhere"])
        z.keep_soft = {"and", "the", "court", "motion", "signed", "schedule"}
        z.keep_nuclear = {"reply", "trust", "parties"}
        body = _random_body(rnd)
        with _with_chunking(False):
            _fresh(z)
            slow = (_cands(z, body), z._keep_spans(body),
                    [r["real"] for r in z._surviving_records(body)],
                    z.apply(body, count=False))
        with _with_chunking(True):
            _fresh(z)
            bounds, _index = z._scan_plan(body)
            fast = (_cands(z, body), z._keep_spans(body),
                    [r["real"] for r in z._surviving_records(body)],
                    z.apply(body, count=False))
        assert fast == slow, (trial, body[:200])
        assert len(bounds) > 3, "the constants should cut the body into chunks"
    # …and at least one trial met an unsafe window, so the fallback ran.
    rnd = random.Random(31)
    z = _pz(NAMES)
    seen_unsafe = False
    with _with_chunking(True):
        for _ in range(30):
            _fresh(z)
            seen_unsafe |= any(u for *_r, u in z._scan_plan(_random_body(rnd))[0])
    assert seen_unsafe


def test_a_match_crossing_a_chunk_cut_is_found_once():
    """A name wrapped across the cut, with the gutter seam the export prints
    there, is matched from the chunk it starts in and never again from the
    next — `finditer` resumes at the last match's end, and so does this."""
    z = _pz(["Helen Rasho"])
    line = "x" * 100 + "\n"
    body = line + "Helen\n 7  Rasho" + "\n" + line * 3
    rx = z._compiled(z.terms[0].pattern, z.terms[0].flags)
    with _with_chunking(True, chunk=104, overlap=200):
        _fresh(z)
        bounds, _index = z._scan_plan(body)
        # The cut falls at the newline INSIDE the name: "Helen\n" closes the
        # first chunk and " 7  Rasho" opens the second.
        assert bounds[0][1] == 107, bounds[0]
        got = [m.span() for m in z._scan_matches(body, rx, z.terms[0].words,
                                                 "Helen Rasho")]
    assert got == [m.span() for m in rx.finditer(body)]
    assert len(got) == 1


def test_the_regex_facts_the_chunked_scan_rests_on():
    """A lookbehind at `pos` sees the characters before it; a lookahead at
    `endpos` does not see past it. Both are what the design assumes, and a
    Python that changed either would make the chunked scan inexact."""
    rx = re.compile(r"(?<!\w)Smith(?!\w)")
    t = "xSmith Smith Smithx"
    assert [m.span() for m in rx.finditer(t, 1)] == [(7, 12)]     # 'x' before pos
    glue = re.compile(r"(?:(?<!\w)|(?-i:(?<=[a-z])(?=[A-Z])))Smith(?!\w)", re.I)
    assert [m.span() for m in glue.finditer("ofSmith", 2)] == [(2, 7)]
    assert [m.span() for m in rx.finditer(t, 0, 18)] == [(7, 12), (13, 18)]
    assert [m.span() for m in rx.finditer(t)] == [(7, 12)]
