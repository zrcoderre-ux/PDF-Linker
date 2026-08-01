"""
D5 — what a DOCUMENT harvest has to clear before it becomes a term.

Every entry in this table became a live term in the fee-motion corpus:

    AL      2   read off "JUAN LOPEZ, ET AL. V. GENERAL MOTORS"
                -> every "et al." became "et aldrin."
    RS      2   an OCR fragment of "MOTORS"          -> "General Motocairnwood"
    NA      2   a short-name                          -> "CASE NA.ME" -> "CASE GG.ME"
    Tue     3   a "declarant"                         -> every "Tue Dec 17, 2024"
    aoasas  6   an OCR fragment of "Calabasas"        -> "Caiaoasas" -> "Caicolfax"

`_PN_SHORT_TOKEN_STOP` is a 24-word list and none of the two-letter ones was on
it. The screens here are scoped to a harvest: the operator's own party template
is never second-guessed, because refusing a real name is the failure the whole
method exists to prevent.

Run:  cd PDF-Linker && python3 -m pytest tests/test_harvest_screens.py -v
"""

import pytest

import pdf_linker as P


def _pz(names=(), casenos=()):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), list(casenos), [], registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    return P.Pseudonymizer(terms, det, registry=reg)


def _harvest(raw, source="document"):
    reg = P._PnFakeRegistry()
    terms = []
    P._pn_append_name_terms(terms, raw, source, reg)
    return [(t.category, t.real) for t in terms]


# ─────────────────────────── "et al." ───────────────────────────────────────

def test_et_al_is_stripped_before_tokenizing():
    # No comma: the cell splitter never sees a separate "et al." piece, so
    # `_PN_SKIP_PARTY_RE` (which only matches a WHOLE cell) never fires and the
    # tail is tokenized as part of the name.
    got = _harvest("JUAN LOPEZ ET AL.")
    assert not any(r.upper() in ("AL", "ET") for _c, r in got), got
    assert ("person-token", "LOPEZ") in got, got
    assert ("person", "JUAN LOPEZ") in got, got


@pytest.mark.parametrize("raw", ["Juan Lopez, et al.", "JUAN LOPEZ ET AL",
                                 "Juan Lopez et. al.", "Juan Lopez, et al"])
def test_et_al_spellings(raw):
    assert P._pn_strip_et_al(raw).lower().rstrip(".") == "juan lopez"


def test_et_al_survives_where_it_is_not_the_marker():
    # A party whose name genuinely contains the letters must not be trimmed.
    assert P._pn_strip_et_al("Etna Metals, LLC") == "Etna Metals, LLC"


# ────────────────────────── the length floor ────────────────────────────────

@pytest.mark.parametrize("raw", ["RS, LLC", "NA", "AL"])
def test_a_two_letter_harvest_is_refused(raw):
    assert _harvest(raw) == [], f"{raw!r} became a term from a document harvest"


@pytest.mark.parametrize("raw", ["Yu", "Ng, LLC"])
def test_the_same_value_from_the_party_template_is_kept(raw):
    assert _harvest(raw, source="spreadsheet"), (
        f"{raw!r} is the operator's own party and must still be scrubbed")


def test_a_three_letter_harvest_is_still_kept():
    assert _harvest("Kim"), "the floor must not swallow an ordinary short name"


# ────────────────────────── the calendar screen ─────────────────────────────

def test_a_weekday_is_never_a_harvested_declarant():
    z = _pz()
    z.register_declarant_refs("Returned Tue Dec 17, 2024 per the repair order.")
    assert [t.real for t in z.terms] == [], [t.real for t in z.terms]


def test_a_timestamp_survives_the_run():
    z = _pz()
    doc = "Agreed Vatue of Property; vehicle returned Tue Dec 17, 2024."
    z.register_declarant_refs(doc)
    assert z.apply(doc) == doc, z.apply(doc)


def test_a_two_letter_declarant_reference_is_still_scrubbed():
    # The structured "<Name> Decl." shape IS the corroboration a loose harvest
    # lacks, so the length floor does not apply there — refusing it would leave
    # a real declarant standing in the export.
    z = _pz()
    doc = "(Yu Dec.) Later Yu signed the declaration."
    z.register_declarant_refs(doc)
    assert "Yu" not in z.apply(doc), z.apply(doc)


# ───────────────────────── the OCR-fragment screen ──────────────────────────

def test_a_term_that_only_lives_inside_a_longer_word_is_dropped():
    z = _pz()
    fake = z.registry.token("aoasas", P._PN_NAME_WORDS, "nametok")
    z._add_terms([P._PnTerm("person-token", "aoasas", fake, whole_word=True,
                            case_sensitive=False, priority=1,
                            source="document")])
    corpus = "The dealership in Caiaoasas serviced the vehicle in Caiaoasas."
    assert "aoasas" in z.prune_fragment_terms(corpus)
    assert ("person-token", "aoasas") not in z.records


def test_a_term_that_stands_alone_somewhere_is_kept():
    z = _pz()
    fake = z.registry.token("amezcua", P._PN_NAME_WORDS, "nametok")
    z._add_terms([P._PnTerm("person-token", "Amezcua", fake, whole_word=True,
                            case_sensitive=False, priority=1,
                            source="document")])
    corpus = "AMEZCUA001234 was produced. Amezcua testified at length."
    assert z.prune_fragment_terms(corpus) == []


def test_a_term_absent_from_the_corpus_is_left_alone():
    # A real party can simply be missing from the files scanned; absence is not
    # evidence of a fragment.
    z = _pz()
    fake = z.registry.token("penuela", P._PN_NAME_WORDS, "nametok")
    z._add_terms([P._PnTerm("person-token", "Penuela", fake, whole_word=True,
                            case_sensitive=False, priority=1,
                            source="document")])
    assert z.prune_fragment_terms("nothing relevant here") == []


# ───────── a party of a CITED authority is not a party of this case ─────────

def test_a_cited_decisions_party_is_not_harvested_as_ours():
    """`prune_citation_only_terms` catches a name that never appears outside a
    citation. It cannot catch the shape that actually bites: a brief DISCUSSES
    the facts of the case it cites, so the cited party is named in prose too.

    A motion to quash argued *Kremerman v. White* (2021) 71 Cal.App.5th 358 at
    length and named Angela White — the defendant IN THAT DECISION — throughout.
    The pre-scan read her as a party of this case, her bare token "White" was
    applied 210 times, and the argument heading shipped as "Kremerman v.
    Yardley". She is a party of a published opinion: public record, and not this
    case's information to protect."""
    z = _pz(names=("Weishi Yang", "Ashley Liu"), casenos=("26STCV08967",))
    fake = P._pn_fake_person("Angela White", z.registry)[0]
    z._add_terms([P._PnTerm("person", "Angela White", fake, whole_word=True,
                            case_sensitive=False, priority=2,
                            source="document")])
    motion = ("Defendant relies on Kremerman v. White (2021) 71 Cal.App.5th "
              "358. In that case Angela White had closed her mailbox.")
    assert "Angela White" in z.prune_authority_party_terms(motion)
    out = z.apply(motion)
    assert "Kremerman v. White (2021) 71 Cal.App.5th 358" in out, out
    assert "Angela White" in out, "a published decision's party is public record"


def test_the_party_templates_own_name_survives_the_authority_screen():
    # Only a GUESS is refused. A real party who happens to share a cited
    # decision's surname keeps their term.
    z = _pz(names=("Angela White",), casenos=("26STCV08967",))
    motion = ("See Kremerman v. White (2021) 71 Cal.App.5th 358. "
              "Plaintiff Angela White testified.")
    assert z.prune_authority_party_terms(motion) == []
    out = z.apply(motion)
    assert "Angela White" not in out, "our own party must still be scrubbed"
    assert "Kremerman v. White (2021)" in out, "the authority must survive"


# ───────────── a transposed spelling of a party is still a party ────────────

def test_an_adjacent_transposition_is_a_known_variant():
    # A complaint wrote its own defendant's given name "Ashely", and the export
    # shipped it beside the faked surname — a half-scrubbed pair naming the
    # party. The registry's OCR fold already counts a transposition as ONE slip.
    assert "Ashely" in P._pn_name_variants("Ashley")


def test_a_transposed_spelling_is_scrubbed():
    z = _pz(names=("Ashley Liu",), casenos=("26STCV08967",))
    out = z.apply('Defendant Ashely Liu ("Liu") is a resident.')
    assert "Ashely" not in out and "Liu" not in out, out


def test_an_invented_variant_that_spells_a_word_is_pruned():
    # "Silver" transposes to "Sliver". A DERIVED spelling is screened whatever
    # its source — the corpus writing it in lower-case is the proof.
    z = _pz(names=("Marcus Silver",))
    corpus = ("Marcus Silver testified. A sliver of doubt remains; only a "
              "sliver of evidence supports it.")
    assert "Sliver" in z.prune_prose_word_terms(corpus)
    out = z.apply(corpus)
    assert "sliver of doubt" in out and "Silver" not in out, out


# ─────── "none of the key values matched" must stay believable ──────────────

def _hits(names, text):
    z = _pz(names=names, casenos=("26STCV08967",))
    z.apply(text)
    return z.spreadsheet_hits(), z.spreadsheet_token_hits()


def test_a_key_that_matched_only_by_token_is_not_called_stale():
    """The template says "Ashley Liu"; the complaint writes "Ashely Liu". The
    full-name term matches nothing while the surname matches throughout, so the
    run scrubbed correctly and then announced that the exports "may name real
    parties because none of the key values matched any document" — a false alarm
    on the one warning that must stay believable."""
    primary, tokens = _hits(("Weishi Yang", "Ashley Liu"),
                            "Defendant Ashely Liu appeared. Liu answered. "
                            "Liu testified at the hearing.")
    assert primary == 0, "fixture must defeat the full-name term"
    assert tokens >= 2, "the key's own tokens corroborate it"


def test_a_genuinely_stale_sheet_still_scores_zero():
    primary, tokens = _hits(("Bartholomew Quillfeather", "Peregrine Vandermolen"),
                            "Defendant Wilhelmina Ashgrove is a resident. "
                            "Ashgrove appeared and answered the complaint.")
    assert primary == 0 and tokens < 2, (primary, tokens)


def test_an_ordinary_word_token_does_not_corroborate():
    # The reason the primary-only rule existed: a party named Green or Long must
    # not be cleared by prose that happens to use the word.
    z = _pz(names=("Marcus Green", "Sandra Long"), casenos=("26STCV08967",))
    z.apply("The green light was long overdue; a green car and a long delay.")
    assert z.spreadsheet_token_hits() < 2, "prose must not corroborate a key"
