"""The tool must never take its OWN output as a real value to scrub.

A delivered key carried two rows that between them corrupted a folder:

    person       | II                   | EE                         | 2281
    display-name | Lowther Rolleston EE | Winchcombe Penrose VENTRIS |   60

The first is an E-Court template that split "Gregory Wayne Walton, II" across
cells and offered "II" as its own party row. A template is authoritative, so it
bypassed every harvest screen, became a case-insensitive person term, and faked
2,281 occurrences — "II. ARGUMENT" to "EE. ARGUMENT", "(ii) the date" to "(ee)
the date". The second is what that made possible: the export then read "Lowther
Rolleston EE", a later pass read it as a fresh person, and the key ended up with
this tool's own stand-in in its Real Value column.

Both are refused at `_pn_build_terms`, the one gate every source passes through
— the party template, `--term`, a worksheet `yes`, a key row read back — rather
than patched pass by pass.

Run:  cd PDF-Linker && python3 -m pytest tests/test_never_refake_our_own.py -v
"""
import logging

import pytest

import pdf_linker as P

log = logging.getLogger("test")


# ── a bare Roman numeral / generational suffix is never a party ─────────────

@pytest.mark.parametrize("value", ["II", "ii", "(ii)", "III", "IV", "V",
                                   "Jr.", "jr", "Sr", "I", "X"])
def test_a_bare_suffix_is_never_faked(value):
    assert P._pn_is_never_fake(value), value


@pytest.mark.parametrize("value", ["Do", "Walton", "Rasho", "Ives", "Xu",
                                   "Ivy", "Vic", "Ida"])
def test_a_real_surname_is_not_caught_by_it(value):
    # Deliberately narrow: the professional suffixes (md, rn, pa, do) are NOT
    # refused — they do not collide with enumeration, and "Do" is a real
    # surname. Refusing one would leave a party unscrubbed.
    assert not P._pn_is_never_fake(value), value


@pytest.mark.parametrize("value", ["Vi", "Ix"])
def test_the_accepted_cost_of_the_numeral_list(value):
    """Roman VI-X shadow a few real short given names, and that is accepted.

    The trade is lopsided: "VI. CONCLUSION" and "(vi)" run through every brief,
    while a party template lists FULL names, so a row of exactly "Vi" is not a
    shape it produces. Only the whole VALUE is refused — "Vi Nguyen" is built
    normally, and so is the bare token inside it.
    """
    assert P._pn_is_never_fake(value), value
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms([f"{value} Nguyen"], [], [], registry=reg)
    assert [t for t in terms if str(t.real) == f"{value} Nguyen"]


def test_a_template_row_of_just_the_suffix_builds_no_term():
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Gregory Wayne Walton", "II"], [], [],
                              registry=reg)
    assert not [t for t in terms if str(t.real).strip() == "II"]


def test_enumeration_survives_while_the_party_is_still_scrubbed():
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Gregory Wayne Walton", "II"], [], [],
                              registry=reg)
    z = P.Pseudonymizer(terms, list(P._PN_DEFAULT_DETECTORS), registry=reg)
    out = z.apply("II. ARGUMENT — (ii) the date; Part II of Exhibit III. "
                  "Gregory Wayne Walton, II signed.")
    assert "II. ARGUMENT" in out, out
    assert "(ii) the date" in out, out
    assert "Part II of Exhibit III" in out, out
    assert "Gregory" not in out and "Walton" not in out, out
    # ...and the suffix is still carried on the party's own fake.
    assert out.rstrip().endswith("II signed."), out


# ── our own stand-in is never re-faked ─────────────────────────────────────

def _first_generation():
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Gregory Wayne Walton"], [], [], registry=reg)
    fake = next(t.fake for t in terms if t.real == "Gregory Wayne Walton")
    return reg, fake


def test_our_own_fake_is_refused_as_a_party_row():
    reg, fake = _first_generation()
    terms = P._pn_build_terms([fake], [], [], registry=reg)
    assert not [t for t in terms if str(t.real) == fake], fake


def test_our_own_fake_is_refused_as_a_term():
    # `--term`, and the auto-terms a worksheet `yes` mints, arrive this way.
    reg, fake = _first_generation()
    terms = P._pn_build_terms([], [], [fake], registry=reg)
    assert not [t for t in terms if str(t.real) == fake], fake


def test_a_half_scrubbed_phrase_is_still_built():
    # Only a value that is ENTIRELY ours is refused. A pair with one real word
    # left ("Melissa Rolleston") is `_pn_strip_prior_fakes`'s case — its real
    # remainder must still be fakeable.
    reg, _fake = _first_generation()
    terms = P._pn_build_terms(["Melissa Rolleston"], [], [], registry=reg)
    assert [t for t in terms if str(t.real) == "Melissa Rolleston"]


def test_a_genuinely_real_party_is_untouched():
    reg, _fake = _first_generation()
    terms = P._pn_build_terms(["Helen Rasho"], [], [], registry=reg)
    assert [t for t in terms if str(t.real) == "Helen Rasho"]


def test_the_chain_cannot_grow_a_second_generation():
    """The whole point: feeding an export back in must add nothing.

    This is the shape a `--fix-leaks` pass, a worksheet `yes` on a half-scrubbed
    row, and a key row read back all reduce to.
    """
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Gregory Wayne Walton"], [], [], registry=reg)
    z = P.Pseudonymizer(terms, list(P._PN_DEFAULT_DETECTORS), registry=reg)
    scrubbed = z.apply("Gregory Wayne Walton signed the declaration.")
    assert "Gregory" not in scrubbed

    # Now hand the SCRUBBED name back as though it were a real value.
    fake_name = scrubbed.split(" signed")[0]
    again = P._pn_build_terms([fake_name], [], [], registry=reg)
    assert not [t for t in again if str(t.real) == fake_name], again


# ── …and the REVIEW scans must not report it either ────────────────────────
# The same rule from the other side. A run that flags its own stand-in as an
# unscrubbed name asks the operator a question with no right answer: `no` leaves
# what was already correct, and `yes` mints the stand-in as a real value — the
# second generation the gate above exists to refuse.
#
# `known_fake_words` held the fake word as written and every consumer looks one
# up by its BASE (`_pn_word_is_own_fake` through `_pn_word_base`,
# `_pn_strip_prior_fakes` through `_pn_word_affixes`), both of which strip a
# POSSESSIVE. So "Mr. Kool's Collision, LLC" faked to "Mr. Redwood's Lightwell,
# LLC" put "redwood's" in the set, the scan asked for "redwood", and one
# delivered folder's worksheet carried `Mr. Redwood's` as an unscrubbed name.
# "Lightwell", which has no possessive, was recognised perfectly — which is why
# it survived this long.

POSSESSIVE_PARTY = "Mr. Kool's Collision, LLC"


def _known(party=POSSESSIVE_PARTY):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms([party], [], [party], registry=reg)
    z = P.Pseudonymizer(terms, {}, registry=reg)
    return z, z.known_fake_words()


def test_a_fake_carrying_a_possessive_is_recognised_as_ours():
    z, known = _known()
    fake = z.records[("entity", POSSESSIVE_PARTY.lower())]["fake"]
    possessive = next(w for w in fake.split() if "'" in w or "’" in w)
    assert P._pn_word_is_own_fake(possessive, known), (possessive, sorted(known))
    # the bare spelling of the same word, as a scan meets it
    assert P._pn_word_is_own_fake(P._pn_word_base(possessive), known)


@pytest.mark.parametrize("sentence", [
    "Plaintiff Mr. Redwood's counsel appeared.",       # the delivered row
    "Defendant Redwood's moved to strike.",
    "Attorneys for Redwood's Lightwell filed it.",
])
def test_our_own_stand_in_is_never_reported_as_an_unscrubbed_name(sentence):
    z, known = _known()
    fake = z.records[("entity", POSSESSIVE_PARTY.lower())]["fake"]
    words = {P._pn_word_base(w) for w in fake.split()}
    # The sentences above are written against the fake this build actually
    # mints; skip if a pool resize moved it rather than assert on a pool word.
    if "redwood" not in words:
        pytest.skip(f"pool moved: {fake}")
    assert P._pn_unknown_name_findings(sentence, known) == []
    assert z.review_scan(sentence) == []


def test_a_name_it_has_never_seen_is_still_reported():
    """The suppression must not widen into blindness."""
    _z, known = _known()
    assert P._pn_unknown_name_findings(
        "Defendant Sarkisyan moved to strike.", known)


def test_a_yes_on_such_a_row_could_not_have_minted_a_generation():
    """`_pn_strip_prior_fakes` missed it the same way, so the phrase would have
    been faked a second time — the chain that never reaches the real name."""
    z, known = _known()
    fake = z.records[("entity", POSSESSIVE_PARTY.lower())]["fake"]
    assert P._pn_strip_prior_fakes(fake, known) is None
    assert P._pn_strip_prior_fakes(fake.rsplit(",", 1)[0], known) is None


def test_the_two_sets_agree_on_every_fake_this_run_minted():
    """The invariant behind it: whatever `known_fake_words` holds, a consumer
    asking by base must find."""
    z, known = _known()
    for rec in z.records.values():
        for w in str(rec["fake"]).split():
            base = P._pn_word_base(w)
            if len(base) >= 3:
                assert P._pn_word_is_own_fake(w, known), (w, rec["fake"])
                assert P._pn_word_is_own_fake(base, known), (base, rec["fake"])
