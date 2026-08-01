"""A motion's own subject matter is not a party name.

Four hand-kept word lists exist to stop ordinary legal vocabulary being
replaced by a surname, and each was written after a motion type shipped with
its own vocabulary renamed: "NOTICE AND MOTION TO MABRY SERVICE OF SUMMONS"
(Quash), "ELDRIDGE OF SERVICE" (Proof), "a registered California process
radley" (Server). A list of words the tool must not treat as names is a list of
every noun in every motion type it has not met yet — the standing note in
CLAUDE.md is "expect the next motion type to reveal the next missing block",
which is a promise of recurrence rather than a fix.

`prune_prose_word_terms` is the general form of the question and catches the
words the corpus writes in lower case. It cannot catch these: a motion's
subject matter lives in its CAPTION and HEADINGS, where every word is
capitalised, so "Quash" is never once written lower-case in a motion to quash.
The evidence that separates them is POSITION — a party is written into prose.

Run:  cd PDF-Linker && python3 -m pytest tests/test_heading_only_terms.py -v
"""
import pytest

import pdf_linker as P

CORPUS = """\
NOTICE OF MOTION AND MOTION TO QUASH SERVICE OF SUMMONS
MEMORANDUM OF POINTS AND AUTHORITIES
PROOF OF SERVICE

HELEN RASHO, an individual,
                Plaintiff,
        v.
YARDLEY SUPPLY COMPANY, LLC, a California corporation,
                Defendant.

     Defendant Yardley Supply Company, LLC moves to quash service of the
summons on the ground that it was never delivered to an officer. The
declaration of Michael Rodgers establishes that Rodgers attempted service
at the mailbox store and left the papers with the manager.
     Plaintiff Rasho opposes and argues that substituted service was proper.
"""


def _pz(words, source="document", derived=False):
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer([], {}, registry=reg)
    for w in words:
        z._add_terms([P._PnTerm(
            "person-token", w, reg.token(w.lower(), P._PN_NAME_WORDS, "nametok"),
            whole_word=True, case_sensitive=False, priority=1,
            source=source, derived=derived)])
    return z


# ── the line classifier ────────────────────────────────────────────────────
@pytest.mark.parametrize("line", [
    "NOTICE OF MOTION AND MOTION TO QUASH SERVICE OF SUMMONS",
    "Motion to Quash Service of Summons",
    "MEMORANDUM OF POINTS AND AUTHORITIES",
    "PROOF OF SERVICE BY MAIL",
    "Process Server Institute, Registration No. 833",
    "By: /s/ Cody Yardley, Attorney at Law",
    "DECLARATION OF MICHAEL RODGERS",
])
def test_a_heading_is_not_prose(line):
    assert P._pn_line_is_prose(line) is False


@pytest.mark.parametrize("line", [
    "served on Mabry at his residence in San Bernardino",
    "The declaration of Michael Rodgers establishes that he",
    "HELEN RASHO, an individual,",              # a caption CELL — see below
    "Defendant Yardley Supply Company, LLC moves to quash service",
])
def test_running_text_and_a_caption_cell_are_prose(line):
    assert P._pn_line_is_prose(line) is True


def test_a_title_leaves_its_function_words_lower_case():
    """The reason the test cannot simply be "does the line hold a lower-case
    word": house style keeps "to" and "of" lower inside a title."""
    assert P._pn_line_is_prose("Motion to Quash Service of Summons") is False
    assert P._pn_line_is_prose("Motion to Quash filed by counsel") is True


def test_ocr_damage_to_a_capitalised_word_is_not_prose_evidence():
    """"SERVICE" misread as "SERVlCE" is MIXED case, not lower — so one slip
    cannot certify a caption as running text."""
    assert P._pn_line_is_prose("NOTICE OF MOTION TO QUASH SERVlCE") is False


# ── the prune ──────────────────────────────────────────────────────────────
def test_the_motions_own_subject_matter_is_dropped():
    z = _pz(["Quash", "Proof", "Authorities", "Summons"])
    dropped = set(z.prune_heading_only_terms(CORPUS))
    assert {"Quash", "Proof", "Authorities"} <= dropped


def test_every_real_name_in_the_same_corpus_survives():
    z = _pz(["Rasho", "Rodgers", "Yardley", "Michael"])
    assert z.prune_heading_only_terms(CORPUS) == []
    assert {t.real for t in z.terms} == {"Rasho", "Rodgers", "Yardley", "Michael"}


def test_a_party_named_only_in_the_caption_survives():
    """The caption is where a filing states its parties — reading a caption
    cell as a heading would drop the party the caption exists to name."""
    caption = ("NOTICE OF MOTION AND MOTION TO QUASH SERVICE OF SUMMONS\n"
               "HELEN RASHO, an individual,\n"
               "YARDLEY SUPPLY COMPANY, LLC, a California corporation,\n")
    z = _pz(["Rasho", "Yardley", "Quash"])
    assert set(z.prune_heading_only_terms(caption)) == {"Quash"}


def test_a_lower_case_occurrence_never_rescues_a_word():
    """A motion writes "moves to quash service" in its argument and "MOTION TO
    QUASH" in its caption. Counting the argument's occurrence as evidence
    rescued the very word this exists to drop."""
    z = _pz(["Quash"])
    assert z.prune_heading_only_terms(
        "MOTION TO QUASH SERVICE\nDefendant moves to quash service today\n"
    ) == ["Quash"]


def test_an_authoritative_value_is_never_screened():
    """A party the operator's own template names is not a guess — a real party
    called Short or Green keeps their term however the headings read."""
    z = _pz(["Quash"], source="key")
    assert z.prune_heading_only_terms(CORPUS) == []


def test_a_value_pinned_by_a_reused_key_is_never_screened():
    """Dropping it would change what an already-delivered export says."""
    z = _pz(["Quash"])
    z._loaded_reals = {"quash"}
    assert z.prune_heading_only_terms(CORPUS) == []


def test_a_derived_spelling_is_screened_whatever_its_source():
    """A variant this tool invented is its own guess — same rule
    `prune_prose_word_terms` applies."""
    z = _pz(["Quash"], source="key", derived=True)
    assert z.prune_heading_only_terms(CORPUS) == ["Quash"]


def test_a_multi_word_term_is_left_alone():
    """The screen answers "is this WORD a name?"; a multi-word value carries
    its own corroboration and is not a vocabulary collision."""
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer([], {}, registry=reg)
    z._add_terms([P._PnTerm("entity", "Quash Service Corp", "Mabry Ltd",
                            whole_word=True, case_sensitive=False,
                            priority=2, source="document")])
    assert z.prune_heading_only_terms(CORPUS) == []


def test_a_term_the_corpus_never_mentions_is_left_alone():
    """No occurrences is no evidence either way, and a term that matches
    nothing costs nothing — dropping it on silence would unbind a party this
    batch simply has not reached yet."""
    z = _pz(["Winterbourne"])
    assert z.prune_heading_only_terms(CORPUS) == []


def test_the_prune_drops_the_record_with_the_term():
    """A term removed but left in `records` would still be reported as a leak
    and still earn a key row — the value would be un-faked AND flagged."""
    z = _pz(["Quash"])
    z.prune_heading_only_terms(CORPUS)
    assert ("person-token", "quash") not in z.records
    assert "quash" in z._pruned_reals
