"""A business name is often just a combination of generic words.

"All Premium Contractors, Inc.", "Sunlight Financial LLC", "Cross River Bank" —
and specifically the words the case's own documents are full of. The FULL name
is distinctive and is registered as its own term. Its bare WORDS are not, and
matching them case-insensitively rewrote the vocabulary of the case: one
delivered folder replaced `Contractors` 204 times and `Sunlight` 356, so "the
contractors were unlicensed" and "converts sunlight into electricity" came back
carrying surnames.

Three screens now stand between a party name and its own vocabulary, and only
the last of them is a word list:

1. CASE (`_pn_term_is_cap_only`). A party is capitalised wherever it stands, in
   prose and caption alike; the ordinary noun is not. A bare token matches
   "Contractors" and "CONTRACTORS" and leaves "contractors" alone.
2. THE CORPUS (`_corpus_prunable`, asked by `prune_prose_word_terms` and
   `prune_heading_only_terms`). A bare BUSINESS token qualifies for those prunes
   whatever its source — the operator's template names a PARTY, not the party's
   individual words — but only while a longer term still covers the party. A
   PERSON's bare token does not: a surname is not a borrowed word, and a
   construction case can have a declarant named Carpenter while its prose is
   full of carpenters.
3. A WORD LIST (`_PN_TRADE_GENERIC_WORDS`). The belt, for a word the corpus
   evidence is too thin to condemn.

What none of them touch is the full name, which is why the cost of all three is
a missed BARE occurrence and never a party in the clear.

Run:  cd PDF-Linker && python3 -m pytest tests/test_generic_business_words.py -v
"""
import logging

import pytest

import pdf_linker as P

log = logging.getLogger("test")


def _pz(names, **kw):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), [], [], registry=reg)
    return P.Pseudonymizer(terms, [], registry=reg, **kw)


# ── 1. a bare token is the party only where the document capitalises it ─────

def test_the_vocabulary_of_the_case_is_left_alone():
    z = _pz(["All Premium Contractors, Inc."])
    out = z.apply("The contractors were unlicensed, so the contractors' work "
                  "on the roof failed.")
    assert out.count("contractors") == 2, out


def test_the_full_name_is_still_scrubbed_in_any_casing():
    z = _pz(["All Premium Contractors, Inc."])
    for spelling in ("All Premium Contractors, Inc.",
                     "ALL PREMIUM CONTRACTORS, INC.",
                     "all premium contractors, inc."):
        assert "ontractors" not in z.apply(spelling), spelling


@pytest.mark.parametrize("spelling", ["Meadowbank", "MEADOWBANK"])
def test_a_capitalised_bare_occurrence_is_still_scrubbed(spelling):
    """A caption SHOUTS its parties, so the all-caps form has to match — the
    rule this replaced was fully case-sensitive and missed it."""
    z = _pz(["Meadowbank Holdings, LLC"])
    z.register_short_names('Defendant Meadowbank Holdings, LLC ("Meadowbank").')
    assert spelling not in z.apply(f"Defendant {spelling} answered.")


def test_the_same_word_in_lower_case_prose_is_left_alone():
    z = _pz(["Meadowbank Holdings, LLC"])
    z.register_short_names('Defendant Meadowbank Holdings, LLC ("Meadowbank").')
    assert "the meadowbank path" in z.apply("Walk the meadowbank path.")


def test_the_detection_mirror_moves_with_it():
    """`_surviving_records` must not report a value `_term_cands` is required to
    leave alone, or the export is quarantined by a leak nothing can clear."""
    z = _pz(["All Premium Contractors, Inc."])
    body = z.apply("The contractors were unlicensed.")
    assert "contractors" in body
    assert [v for _c, v in z.surviving_reals(body)] == []


# ── 2. the corpus prunes reach a word split out of a TEMPLATE name ──────────

CORPUS = ("The meadowbank was flooded. Cattle crossed the meadowbank at dawn. "
          "A meadowbank is not a party. Meadowbank Holdings, LLC is the "
          "defendant.")


def _entity_pz():
    z = _pz(["Meadowbank Holdings, LLC"])
    z.register_short_names('Defendant Meadowbank Holdings, LLC ("Meadowbank").')
    return z


def test_a_token_of_a_template_name_is_pruned_on_corpus_evidence():
    z = _entity_pz()
    assert "Meadowbank" in [t.real for t in z.terms]
    dropped = z.prune_prose_word_terms(CORPUS)
    assert "Meadowbank" in dropped, dropped
    # …and the party is still covered, which is the whole safety argument.
    assert "Meadowbank Holdings, LLC" in [t.real for t in z.terms]
    assert "Meadowbank" not in z.apply("Meadowbank Holdings, LLC answered.")


def test_a_persons_bare_surname_is_not_pruned_by_the_corpus():
    """A construction case can have a declarant named Carpenter while its prose
    is full of carpenters. The CASE rule already keeps the lower-case
    occurrences out; dropping the token would leave "Carpenter Decl." standing.
    """
    z = _pz(["Justin Carpenter"])
    corpus = ("the carpenter was late, a carpenter's lien, carpenters on site. "
              "Justin Carpenter signed it.")
    assert "Carpenter" not in z.prune_prose_word_terms(corpus)
    out = z.apply("Carpenter Decl. \u00b6 5; the carpenter was late.")
    assert "Carpenter Decl" not in out
    assert "the carpenter was late" in out


def test_the_operators_own_one_word_party_is_never_pruned():
    """A party really named Green keeps its term however the prose reads — the
    value is one the operator NAMED, not a word this tool split out."""
    z = _pz(["Green"])
    corpus = "the green roof, a green panel, green wiring. Green answered."
    assert z.prune_prose_word_terms(corpus) == []
    assert "Green" in [t.real for t in z.terms]


def _auth_token(real):
    return P._PnTerm("entity-token", real, "Kaldor", whole_word=True,
                     case_sensitive=False, priority=1, source="spreadsheet")


def test_an_authoritative_token_is_prunable_only_while_a_longer_term_covers_it():
    """The guard that makes this cost a bare occurrence and never a party: if
    no longer term still names the party, the token is all that stands between
    it and the export, so corpus evidence alone must not drop it."""
    z = _entity_pz()
    t = _auth_token("Meadowbank")
    covered = z._multiword_covered_words()
    assert "meadowbank" in covered                 # "Meadowbank Holdings, LLC"
    assert z._corpus_prunable(t, (), covered)
    assert not z._corpus_prunable(t, (), set())    # nothing else covers it
    assert not z._corpus_prunable(t, {"meadowbank"}, covered)   # key-pinned


def test_an_authoritative_full_NAME_is_never_prunable():
    """Only the bare WORDS a party name was split into are screened. The value
    the operator actually named is authoritative however the prose reads."""
    z = _entity_pz()
    named = P._PnTerm("entity", "Meadowbank", "Kaldor", whole_word=True,
                      case_sensitive=False, priority=2, source="spreadsheet")
    assert not z._corpus_prunable(named, (), z._multiword_covered_words())


def test_a_person_token_is_never_prunable_from_an_authoritative_source():
    z = _entity_pz()
    t = P._PnTerm("person-token", "Carpenter", "Meriwether", whole_word=True,
                  case_sensitive=False, priority=1, source="spreadsheet")
    covered = z._multiword_covered_words() | {"carpenter"}
    assert not z._corpus_prunable(t, (), covered)


def test_a_key_pinned_token_is_never_pruned():
    """Its row is the reversal of a fake already standing in a delivered
    export."""
    z = _entity_pz()
    z._loaded_reals = {"meadowbank"}
    assert "Meadowbank" not in z.prune_prose_word_terms(CORPUS)


# ── 3. the word list, for evidence too thin to condemn ─────────────────────

@pytest.mark.parametrize("word", [
    "contractors", "contracting", "installation", "dealer", "solar",
    "sunlight", "energy", "financial", "financing", "lender", "loan",
    "capital", "warranty", "roofing", "permit",
])
def test_trade_vocabulary_never_becomes_a_bare_token(word):
    assert P._pn_is_generic_token(word)


def test_the_trade_words_stay_reportable():
    """Withheld from becoming a token, NOT swallowed into `_PN_COMMON_WORDS` —
    a word swallowed there stops being reportable, and a party really named
    Dealer or Bright must keep surfacing for review."""
    assert not (P._PN_TRADE_GENERIC_WORDS & P._PN_COMMON_WORDS)


def test_the_trade_words_collide_with_no_fake_pool():
    pools = ({w.lower() for w in P._PN_NAME_WORDS}
             | {w.lower() for w in P._PN_ENTITY_WORDS}
             | {w.lower() for w in P._PN_STREET_NAMES})
    assert not (P._PN_TRADE_GENERIC_WORDS & pools)


def test_the_trade_block_holds_only_lower_case_words():
    # A `#` inside a triple-quoted word list is data, not a comment.
    bad = [w for w in P._PN_TRADE_GENERIC_WORDS
           if not w.isalpha() or w != w.lower()]
    assert not bad, bad
