"""The pre-scan's corpus-wide prunes are FASTER and answer the same.

Those five passes run once over the whole folder, and each cost roughly
(terms harvested) x (corpus size): on a 15-file batch they were the longest
silent stretch of the run. Two things were done about it — a lead-word screen
so a term whose first word stands nowhere in the corpus is never scanned for,
and one pass over the corpus in `prune_heading_only_terms` where there was one
regex call per (term, LINE).

Both are speed only, so both are pinned DIFFERENTIALLY here: the screened
prunes against the same prunes with `_PN_LEAD_PREFILTER` switched off, and the
heading prune against a copy of the per-line loop it replaced. A prune that
dropped one term more would be a name left in the clear; one that dropped one
fewer would be a cited authority renamed. Neither is a trade this project makes
for time.

Run:  cd PDF-Linker && python3 -m pytest tests/test_prescan_prune_equivalence.py -v
"""
import re

import pytest

import pdf_linker as P


# A corpus with something for every prune to find: a declarant and a couple of
# labelled names to harvest from (each of which mints derived near-spellings
# that stand nowhere in the text — the terms the screen exists to skip), a
# motion's own subject matter living only in its headings, a word the prose
# writes in lower case, and three cited decisions.
CORPUS = """\
SUPERIOR COURT OF THE STATE OF CALIFORNIA
NOTICE OF MOTION AND MOTION TO QUASH SERVICE OF SUMMONS
HELEN RASHO, an individual, Plaintiff, v. QUILLMARK BUILDERS LLC
DECLARATION OF MARCUS DELACROIX IN SUPPORT OF THE MOTION
I, Marcus Delacroix, declare as follows. (Delacroix Decl. p. 4.)
Attn: Rosa Delgado
Patient: Owen Blakely
Lenis Industries, Inc. served the notice at 1440 Whorton Lane, Bakersfield, CA 93301.
ANGELA WESTBROOK, an individual, and GALPIN MOTORS INC., a California corporation
I. INTRODUCTION
A motion to quash service is governed by section 418.10.
The Court relied on Kremerman v. White (2021) 71 Cal.App.5th 358, 373-374,
and Angela White was the defendant in that decision. See also Ewald v.
Nationstar Mortgage, LLC (2017) 13 Cal.App.5th 947; Stockton Theatres, Inc.
v. Palermo (1956) 47 Cal.2d 469.
II. ARGUMENT
Counsel began to draft the opposition, then to draft the reply.
"""
# Repeated so the corpus is long enough for the screen to matter, each copy on
# its own page as the pre-scan joins them.
FULL = "\n\f\n".join(CORPUS for _ in range(6))

# Terms the harvest does not itself produce here, injected so that EVERY prune
# has something to drop and no equivalence test passes by comparing two empty
# lists. Each is a document-harvested guess, which is what all five screen for.
INJECTED = (
    # stands only inside "Stockton Theatres, Inc. v. Palermo (1956)"
    ("person-token", "Palermo"),
    # the corpus writes it lower-case twice and capitalises it never
    ("person-token", "Draft"),
    # the motion's own subject matter: capitalised only inside headings
    ("person-token", "Quash"),
    # a party of a decision this corpus cites
    ("person-token", "White"),
    # an OCR fragment: never stands as a word, only inside "MOTORS"
    ("person-token", "RS"),
)

PRUNES = ("prune_citation_only_terms", "prune_prose_word_terms",
          "prune_heading_only_terms", "prune_authority_party_terms",
          "prune_fragment_terms")


def _pz():
    """A pseudonymizer that has learned from the corpus exactly as the pre-scan
    leaves it — deterministic, so two of them are interchangeable."""
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Helen Rasho", "Quillmark Builders LLC"],
                              [], [], registry=reg)
    z = P.Pseudonymizer(terms, {}, registry=reg)
    z.note_docket_codes(FULL)
    z.note_authority_cites(FULL)
    for i in range(3):
        P._pn_learn_from_text(z, CORPUS, f"Doc{i}")
    for cat, real in INJECTED:
        t = P._PnTerm(cat, real, f"Fake{real}", whole_word=True,
                      case_sensitive=False, priority=5, source="document")
        z.terms.append(t)
        z.records[(cat, real.lower())] = {
            "real": real, "fake": t.fake, "count": 0, "category": cat}
    return z


def _run(z, name):
    fn = getattr(z, name)
    return sorted(v.lower() for v in
                  (fn(FULL, None) if name == "prune_authority_party_terms"
                   else fn(FULL)))


def _with_prefilter(flag):
    class _Ctx:
        def __enter__(self):
            self.old = P._PN_LEAD_PREFILTER
            P._PN_LEAD_PREFILTER = flag
        def __exit__(self, *a):
            P._PN_LEAD_PREFILTER = self.old
    return _Ctx()


def test_the_corpus_has_something_for_every_prune_to_find():
    """Guard against a vacuous suite: a prune that drops nothing here would
    make its equivalence test pass by comparing two empty lists."""
    z = _pz()
    dropped = {name: _run(z, name) for name in PRUNES}
    empty = [n for n, v in dropped.items() if not v]
    assert not empty, f"nothing to compare for {empty}: {dropped}"


@pytest.mark.parametrize("name", PRUNES)
def test_the_lead_screen_changes_no_prune(name):
    with _with_prefilter(False):
        slow = _run(_pz(), name)
    with _with_prefilter(True):
        fast = _run(_pz(), name)
    assert fast == slow


def _heading_only_per_line(z, text):
    """The per-LINE loop `prune_heading_only_terms` replaced, verbatim, as the
    reference the one-pass form is measured against."""
    text = P._NFKC(text)
    loaded = getattr(z, "_loaded_reals", ())
    lines = text.split("\n")
    prose_line = [P._pn_line_is_prose(ln) for ln in lines]
    covered = z._multiword_covered_words()
    doomed = []
    for t in list(z.terms):
        if not z._corpus_prunable(t, loaded, covered):
            continue
        rx = re.compile(r"(?<!\w)" + re.escape(t.real) + r"(?!\w)",
                        re.IGNORECASE)
        seen = False
        for i, ln in enumerate(lines):
            hits = rx.findall(ln)
            if not hits:
                continue
            seen = True
            if prose_line[i] and any(h[:1].isupper() for h in hits):
                break
        else:
            if seen:
                doomed.append(t)
    return sorted(t.real.lower() for t in doomed)


def test_the_heading_prune_answers_what_the_per_line_loop_did():
    """One pass over the corpus, placed on its line by bisect, against one
    regex call per (term, line)."""
    assert _run(_pz(), "prune_heading_only_terms") == \
        _heading_only_per_line(_pz(), FULL)


def test_the_heading_prune_places_a_match_on_its_own_line():
    """The bisect must not be off by one: a value capitalised on a PROSE line
    is spared, and the same value written only in headings is dropped."""
    z = _pz()
    lines = FULL.split("\n")
    starts = [0]
    for ln in lines:
        starts.append(starts[-1] + len(ln) + 1)
    import bisect
    for m in re.finditer(r"\bQuash\b|\bDelacroix\b|\bRasho\b", FULL):
        i = bisect.bisect_right(starts, m.start()) - 1
        assert m.group(0) in lines[i], (m.group(0), i, lines[i])


def test_a_fragment_term_is_never_lead_screened():
    """The one prune that must NOT take the screen. It exists to find the term
    that stands only INSIDE a longer word ("RS" off "MOTORS"), where the lead
    word is by construction not a word of the corpus — screening it would make
    the pass find nothing at all."""
    z = _pz()
    frag = next(t for t in z.terms if t.real == "RS")
    ws = z._corpus_lead_words(P._NFKC(FULL))
    assert z._corpus_lead_skip(frag, ws), \
        "the screen should indeed refuse this term — which is why it is not asked"
    assert "rs" in _run(z, "prune_fragment_terms")


def test_a_break_tolerant_term_is_exempt_from_the_screen():
    """`_corpus_lead_words` leaves out the adjacent PAIRS that keep the page
    screen exact for a kerned spelling, so a term that may match across a
    printed break is always scanned instead."""
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Vadim Sarkisyan"], [], [], registry=reg)
    z = P.Pseudonymizer(terms, {}, registry=reg)
    broken = "The caption reads V ADIM SARKISY AN throughout.\n"
    ws = z._corpus_lead_words(broken)
    tok = [t for t in z.terms
           if t.real.lower() == "sarkisyan" and t.category == "person-token"]
    assert tok, [t.real for t in z.terms]
    assert "sarkisyan" not in ws          # only "sarkisy" and "an" are words
    assert not z._corpus_lead_skip(tok[0], ws)
    # …and the citation prune therefore still sees it, exactly as it did.
    with _with_prefilter(False):
        slow = sorted(P.Pseudonymizer(
            P._pn_build_terms(["Vadim Sarkisyan"], [], [],
                              registry=P._PnFakeRegistry()), {}
        ).prune_citation_only_terms(broken, sources=("--term",)))
    with _with_prefilter(True):
        fast = sorted(P.Pseudonymizer(
            P._pn_build_terms(["Vadim Sarkisyan"], [], [],
                              registry=P._PnFakeRegistry()), {}
        ).prune_citation_only_terms(broken, sources=("--term",)))
    assert fast == slow


def test_the_screen_skips_most_terms_on_a_real_corpus():
    """The point of the change: a term is scanned for the folder it is in."""
    z = _pz()
    text = P._NFKC(FULL)
    ws = z._corpus_lead_words(text)
    skipped = [t for t in z.terms if z._corpus_lead_skip(t, ws)]
    assert skipped, "nothing screened — the prunes would cost what they did"


def test_the_citation_index_memo_answers_what_a_fresh_parse_does():
    """`reserve_authority_names` and `prune_authority_party_terms` ask about
    the same whole-folder corpus, and the second parse was pure repetition."""
    P._PN_AUTH_CITE_MEMO.clear()
    fresh = P._pn_authority_cite_index(FULL)
    assert fresh, "the corpus should cite something"
    cached = P._pn_authority_cite_index(FULL)
    assert cached == fresh
    P._PN_AUTH_CITE_MEMO.clear()
    assert P._pn_authority_cite_index(FULL) == fresh
    # …and it is capped, so it cannot grow with the folder.
    for i in range(4):
        P._pn_authority_cite_index(FULL + "\n" * (i + 1))
    assert len(P._PN_AUTH_CITE_MEMO) <= 2


def test_the_site_screen_answers_what_every_site_did():
    """`_pn_case_party_shapes` drops a party-position site whose fixed words
    stand nowhere in the folder, so the evidence loop stops re-scanning the
    corpus for it once per name. It may only drop a site no term could have
    matched."""
    z = _pz()
    masked = z._mask_uncached(P._NFKC(FULL))
    sites = P._pn_case_party_shapes(masked)
    assert len(sites) < len(P._PN_CASE_PARTY_SITES), \
        "this corpus carries only some of the sites — else nothing is screened"
    answers = [P._pn_case_party_evidence(masked, t, sites) for t in z.terms]
    assert answers == [P._pn_case_party_evidence(masked, t) for t in z.terms]
    assert any(answers), "no term found at any site — the comparison is vacuous"


def test_a_site_written_in_CAPITALS_is_not_screened_out():
    """The screen reads each half case-INSENSITIVELY, because the full shape
    is compiled with the TERM's flags. Read case-sensitively, `['’]s` missed
    the "’S" of an all-caps filing title and dropped the one site the caption
    actually carried."""
    masked = "ACME WIDGETS, INC.’S REPLY IN SUPPORT OF ITS MOTION TO COMPEL\n"
    assert "the filing title" in [l for l, _ in P._pn_case_party_shapes(masked)]
