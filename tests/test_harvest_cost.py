"""The HARVEST's two speed-ups are exact, and its shape is pinned.

`_pn_learn_from_text` runs every register_* pass over each document, and the
pre-scan runs it over the whole folder before a single export is written. Two
passes in it were priced by the TERM LIST, which the harvest itself keeps
growing — so on a 15-file batch of scanned exhibits the block took 54 minutes
between the last file read and the "added N term(s)" line, with nothing to say
which pass was in it:

  * `register_short_names` ran one regex scan of the WHOLE document per
    person/entity term, most of them near-miss spellings this tool minted that
    stand in no document at all;
  * `_pn_align_initials`, called from `_add_terms` every time the term set
    grows, sorted the whole person list INSIDE a per-term loop and re-split
    every sibling's words per comparison.

Both are speed only, so both are pinned differentially: the short-name screen
against the same pass with the screen bypassed, and the aligner against a
verbatim copy of the loop it replaced, over randomized term sets. An aligner
that changed one answer would move a stand-in a delivered key has already
pinned; a screen that refused one term would drop a party's own short form.

Run:  cd PDF-Linker && python3 -m pytest tests/test_harvest_cost.py -v
"""
import random
import re

import pytest

import pdf_linker as P


# ── the short-name screen ───────────────────────────────────────────────────

DEFS = """\
Defendant Glenwood Group ("Glenwood") answered the complaint.
Plaintiff Tom of Finland Foundation, a public benefit corporation ("ToFF"),
moved to compel. MIDLAND STATES BANK ("Midland") is the lender of record.
Mr. Kool's Collision, LLC ("Kool's") repaired the vehicle.
Quillmark Builders LLC ("Quillmark") was served on the same day.
"""

PARENT_NAMES = ["Glenwood Group", "Tom of Finland Foundation",
                "Midland States Bank", "Mr. Kool's Collision, LLC",
                "Quillmark Builders LLC", "Helen Rasho", "Marcus Delacroix",
                "Sunbelt Rentals LLC", "Galpin Motors Inc.", "Owen Blakely"]


class _Everything:
    """A word set that holds every word — the screen bypassed, so the pass
    scans for every term exactly as it did before."""

    def __contains__(self, _w):
        return True


def _short_names(text, bypass):
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(list(PARENT_NAMES), [], [],
                                          registry=reg), {}, registry=reg)
    if bypass:
        z._lead_words = lambda _t: _Everything()
    z.register_short_names(text)
    return sorted((t.real, t.fake) for t in z.terms
                  if t.category == "short-name")


def test_the_short_name_screen_registers_what_the_full_scan_did():
    fast = _short_names(DEFS, bypass=False)
    slow = _short_names(DEFS, bypass=True)
    assert fast == slow and fast, fast


def test_the_short_name_screen_really_refuses_most_terms():
    """The point of it: a document defines a handful of short forms, and the
    term list is mostly names that stand nowhere in THIS document."""
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(list(PARENT_NAMES), [], [],
                                          registry=reg), {}, registry=reg)
    ws = z._lead_words(DEFS)
    named = [t for t in z.terms if t.category in ("entity", "person")]
    kept = [t for t in named
            if t.lead is None or all(w.lower() in ws for w in
                                     P._PN_LEAD_WORD_RE.findall(str(t.real)))]
    assert len(kept) < len(named) / 2, (len(kept), len(named))


def test_a_document_with_no_parenthetical_defines_nothing():
    assert _short_names("Glenwood Group answered the complaint.\n", False) == []


def test_every_word_must_stand_in_the_page_not_only_the_first():
    """The screen is on the WHOLE name: a document naming "Glenwood" but never
    "Group" cannot carry a definition of "Glenwood Group", and the lead word
    alone would not have said so."""
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(["Glenwood Group"], [], [],
                                          registry=reg), {}, registry=reg)
    ws = z._lead_words('The Glenwood entity ("Glenwood") appeared.\n')
    parent = next(t for t in z.terms if t.real == "Glenwood Group")
    assert parent.lead in ws                        # the lead alone is there
    assert not all(w.lower() in ws for w in
                   P._PN_LEAD_WORD_RE.findall(parent.real))


# ── the aligner ─────────────────────────────────────────────────────────────

def _align_reference(terms, log=None):
    """`_pn_align_initials` as it stood before the index: the whole person list
    sorted inside the per-term loop, every sibling re-split per comparison."""
    def split(t):
        rw, fw = (P._PN_WORD_RE.findall(str(t.real)),
                  P._PN_WORD_RE.findall(str(t.fake)))
        return (rw, fw) if rw and len(rw) == len(fw) else (None, None)

    people = [t for t in terms
              if t.category == "person" and not getattr(t, "loaded", False)]
    if not people:
        return []
    faked = {}
    for t in people:
        rw, fw = split(t)
        if rw is None:
            continue
        faked[id(t)] = frozenset(f.lower() for r, f in zip(rw, fw) if r != f)
    changed = []
    for t in people:
        rw, fw = split(t)
        if rw is None:
            continue
        slots = [i for i, r in enumerate(rw) if len(r) == 1 and r == fw[i]]
        mine = faked.get(id(t))
        if not slots or not mine or len(mine) < 2:
            continue
        letters = {}
        for u in sorted(people, key=lambda u: (str(u.real).lower(), id(u))):
            if u is t or not (mine < faked.get(id(u), frozenset())):
                continue
            ru, fu = split(u)
            if ru is None:
                continue
            for r, f in zip(ru, fu):
                if len(r) > 1 and r != f and f:
                    letters.setdefault(r[0].lower(), f[0])
        if not letters:
            continue
        out, hit = list(fw), False
        for i in slots:
            letter = letters.get(rw[i][0].lower())
            if letter and letter.lower() != rw[i].lower():
                out[i] = letter.upper() if rw[i].isupper() else letter.lower()
                hit = True
        if not hit:
            continue
        old = t.fake
        t.fake = P._pn_rejoin_words(str(t.fake), fw, out)
        changed.append((t, old))
    return changed


GIVEN = ["Steven", "Amberly", "Helen", "Marcus", "Rosa", "Owen", "Vahe"]
MIDDLE = ["Wayne", "Ondine", "Marie", "Cole", "Ann", "Rae"]
SUR = ["Burt", "Yeardley", "Rasho", "Delacroix", "Delgado", "Blakely"]
FAKE_G = ["Cranston", "Melbury", "Strangeways", "Keswick", "Sable", "Redwood"]
FAKE_M = ["Ondine", "Thornfield", "Larkspur", "Marlowe", "Fenmore", "Darrow"]
FAKE_S = ["Yeardley", "Whitlock", "Bancroft", "Merrick", "Sedgwick", "Linford"]


def _random_terms(rnd, n):
    """Person terms of the shape the aligner exists for: a spelled-out name and
    the same name written with an initial, faked word for word."""
    out = []
    for _ in range(n):
        gi, mi, si = (rnd.randrange(len(GIVEN)), rnd.randrange(len(MIDDLE)),
                      rnd.randrange(len(SUR)))
        g, m, s = GIVEN[gi], MIDDLE[mi], SUR[si]
        fg, fm, fs = FAKE_G[gi % 6], FAKE_M[mi % 6], FAKE_S[si % 6]
        shape = rnd.random()
        if shape < 0.45:                       # the initialled form
            real, fake = f"{g} {m[0]}. {s}", f"{fg} {m[0]}. {fs}"
        elif shape < 0.9:                      # the spelled-out form
            real, fake = f"{g} {m} {s}", f"{fg} {fm} {fs}"
        else:                                  # a bare two-word name
            real, fake = f"{g} {s}", f"{fg} {fs}"
        t = P._PnTerm("person", real, fake, whole_word=True,
                      case_sensitive=False, priority=1, source="document")
        out.append(t)
    return out


@pytest.mark.parametrize("seed", range(12))
def test_the_aligner_answers_what_the_scan_it_replaced_did(seed):
    n = random.Random(seed).randint(2, 40)
    # The SAME list twice — one for each implementation, since both mutate the
    # terms they are given.
    fast = _random_terms(random.Random(seed + 1000), n)
    slow = _random_terms(random.Random(seed + 1000), n)
    assert [(t.real, t.fake) for t in fast] == [(t.real, t.fake) for t in slow]

    a = P._pn_align_initials(fast)
    b = _align_reference(slow)
    assert [(t.real, old) for t, old in a] == [(t.real, old) for t, old in b]
    assert [(t.real, t.fake) for t in fast] == [(t.real, t.fake) for t in slow]


def test_the_aligner_still_aligns_the_worked_example():
    """"STEVEN W. BURT" takes the first letter of the fake "Wayne" got."""
    terms = [
        P._PnTerm("person", "Steven Wayne Burt", "Amberly Ondine Yeardley",
                  whole_word=True, case_sensitive=False, priority=1,
                  source="spreadsheet"),
        P._PnTerm("person", "STEVEN W. BURT", "AMBERLY W. YEARDLEY",
                  whole_word=True, case_sensitive=False, priority=1,
                  source="document"),
    ]
    P._pn_align_initials(terms)
    assert terms[1].fake == "AMBERLY O. YEARDLEY", terms[1].fake


def test_the_aligner_is_idempotent():
    terms = _random_terms(random.Random(3), 30)
    P._pn_align_initials(terms)
    once = [(t.real, t.fake) for t in terms]
    assert P._pn_align_initials(terms) == []
    assert [(t.real, t.fake) for t in terms] == once
