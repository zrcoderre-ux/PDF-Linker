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
