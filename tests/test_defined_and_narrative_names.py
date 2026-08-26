"""Two anchors that were missing, and the leak they let through.

A complaint referencing `Susan Spellman ("Spellman")` shipped unscrubbed AND
unflagged. Three passes already read a defined-term parenthetical and every one
of them needs the parent name to be KNOWN first — `_pn_split_cell` reads it out
of the E-Court template cell, `register_short_names` iterates `self.terms`, and
`review_definition_survivors` is scoped to initialisms of a tracked party — so
a party no template named and no role anchor reached met no pass at all.

1. THE DOCUMENT NAMES ITS OWN PARTIES. `X ("Y")` is the filing declaring that
   the run in front of it is a name. `defined_name_scan` reports it, and does
   not rewrite it: the same shape defines an agreement, a statute and a
   published decision, so minting a term off it would rename a cited authority.

2. A NAME IS THE THING THAT DOES SOMETHING. "Spellman confirmed", "Rasho
   emailed" — a capitalised run in the subject position of an active reporting
   verb is a person or a company, and nothing else in a pleading stands there.
   That anchor needs no role prefix, no label and no parenthetical, which is
   what makes it reach a fact-section witness.

Both are REVIEW tier: reported for triage in LEAKS.xlsx, never repaired.

Run:  cd PDF-Linker && python3 -m pytest tests/test_defined_and_narrative_names.py -v
"""
import pytest

import pdf_linker as P


def _pz(names=()):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), [], [], registry=reg)
    return P.Pseudonymizer(terms, [], registry=reg)


def _defined(text, pz=None):
    pz = pz or _pz()
    return sorted(s for _c, s in pz.defined_name_scan(text, text))


def _narrative(text, pz=None):
    pz = pz or _pz()
    return sorted(s for _c, s in pz.narrative_name_scan(text))


# ── 1. the defined-term parenthetical ───────────────────────────────────────

def test_the_reported_leak_is_flagged():
    """The complaint that started this: a party defined in the body, named on
    no template, reaching no other anchor."""
    text = 'Plaintiff Susan Spellman ("Spellman") was employed by the company.'
    assert _defined(text) == ["Spellman", "Susan Spellman"]


def test_the_finding_carries_its_class():
    pz = _pz()
    text = 'Susan Spellman ("Spellman") signed the lease.'
    assert pz.defined_name_scan(text, text) == [("defined name?",
                                                 "Susan Spellman"),
                                                ("defined name?", "Spellman")]
    # ...and accumulates into the folder review list the worksheet is built from
    assert ("defined name?", "Susan Spellman") in pz.review
    assert ("defined name?", "Spellman") in pz.review


@pytest.mark.parametrize("text,found", [
    ('Defendant ACME CORPORATION, INC. ("Acme") answered.',
     ["ACME CORPORATION, INC.", "Acme"]),
    ('Sunlight Financial LLC ("Sunlight") funded the loan.',
     ["Sunlight", "Sunlight Financial LLC"]),
    ('Cross-Defendant Mr. Kool\'s Collision, LLC ("Kool\'s") demurs.',
     ["Kool's", "Mr. Kool's Collision, LLC"]),
    ('MARIA CRUZ DE AMEZCUA ("Amezcua") was served on May 5.',
     ["Amezcua", "MARIA CRUZ DE AMEZCUA"]),
])
def test_shapes_a_california_complaint_actually_uses(text, found):
    assert _defined(text) == found


def test_a_leading_role_word_is_trimmed_not_fatal():
    """"Plaintiff HELEN RASHO, an individual" is the commonest caption form
    there is; a screen that refused any run carrying a role word would yield
    nothing at all."""
    text = 'Plaintiff HELEN RASHO ("Rasho") filed suit.'
    assert _defined(text) == ["HELEN RASHO", "Rasho"]


@pytest.mark.parametrize("text", [
    'The parties executed the Retail Installment Contract ("Contract").',
    'Plaintiff signed a lease. The Subject Property ("Property") is here.',
    'The parties entered a Master Services Agreement ("Agreement").',
    'This action arises under the Fair Employment and Housing Act ("FEHA").',
    'Plaintiff filed a Request for Judicial Notice ("RJN").',
    'Defendants Are Entitled To An Order ("Order") granting relief.',
])
def test_a_defined_THING_is_not_a_party(text):
    """The article carries the dominant false-positive family, because no word
    list can: "Property", "Lease", "Policy" and "Note" are all real surnames,
    so widening a gazetteer to cover them would cost the names this exists to
    surface. An INITIALISM is refused for its own reason — against an unknown
    parent, ("FEHA")/("RJN")/("UCL") are defined legal vocabulary far more
    often than a party's initials."""
    assert _defined(text) == []


def test_a_public_entity_is_not_reported():
    text = 'Defendant Los Angeles Unified School District ("LAUSD") answered.'
    assert _defined(text) == []


def test_the_run_stops_at_the_sentence_before_it():
    """The `_PN_DECL_NAME_WORD` lesson: a harvest that walks past a full stop
    walks out of the structure that corroborated it. "Provision. Carpenter
    Smith" is not a party named Provision."""
    text = 'The court must enforce the Provision. Carpenter Smith ("Smith") so testified.'
    assert _defined(text) == ["Carpenter Smith", "Smith"]


def test_the_article_test_reads_the_NAME_not_the_raw_run():
    """The definite article the raw run backs onto belongs to "the Provision",
    a sentence away — so the offset `_pn_defined_name_run` returns is what the
    lookbehind must be taken from."""
    words, at = P._pn_defined_name_run("Provision. Carpenter Smith")
    assert words == ["Carpenter", "Smith"]
    assert "Provision. Carpenter Smith"[at:] == "Carpenter Smith"


def test_a_published_authority_is_never_a_finding():
    """Renaming a cited decision is the failure the whole method refuses, and
    a short-cite parenthetical has exactly this shape."""
    text = ('The rule is settled. (See Kremerman v. White (2021) '
            '71 Cal.App.5th 358 ("Kremerman").)')
    assert "Kremerman v. White" not in _defined(text)


def test_the_citation_guard_is_load_bearing():
    """Not belt-and-braces: a brief that defines a short form INSIDE the cite
    offers the cited party up as this case's own, and the span check is the
    only thing that refuses it."""
    text = ('(See Ewald v. Nationstar Mortgage, LLC ("Nationstar") '
            '(2017) 13 Cal.App.5th 947.)')
    assert _defined(text) == []
    off = _pz()
    off._protected_citation_spans = lambda t: []
    assert _defined(text, off) == ["Nationstar", "Nationstar Mortgage, LLC"]


def test_the_citation_parse_is_paid_only_where_there_is_a_candidate():
    """It is the expensive thing on the leak path (~0.8 s on a 214 KB brief)
    and this is the one scan asking about a third body, so a file offering no
    defined-term candidate must not pay for it at all."""
    pz = _pz()
    asked = []
    real = pz._protected_citation_spans
    pz._protected_citation_spans = lambda t: (asked.append(t), real(t))[1]
    pz.defined_name_scan("The motion was filed on May 5. It is unopposed.",
                         "The motion was filed on May 5. It is unopposed.")
    assert asked == []
    text = 'Plaintiff Susan Spellman ("Spellman") sued.'
    assert _defined(text, pz) == ["Spellman", "Susan Spellman"]
    assert len(asked) == 1          # once, not once per candidate


def test_a_value_already_faked_is_not_reported():
    """Read from the SOURCE, reported only when it SURVIVED: a party correctly
    bound has nothing left standing to flag."""
    pz = _pz(["Susan Spellman"])
    src = 'Plaintiff Susan Spellman ("Spellman") was employed here.'
    out = pz.apply(src)
    assert "Spellman" not in out
    assert pz.defined_name_scan(src, out) == []


def test_a_tracked_value_is_the_leak_tier_s_row_not_this_one():
    """A value the run tracks is `surviving_reals`' finding if it survived and
    nobody's if it did not — either way not a second row here."""
    pz = _pz(["Susan Spellman"])
    src = 'Plaintiff Susan Spellman ("Spellman") was employed here.'
    assert pz.defined_name_scan(src, src) == []


# ── 1a. a STATUTE is not a party ────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    # The definite article screens most statutes out incidentally...
    'Plaintiff brings a claim under the Consumer Legal Remedies Act ("CLRA").',
    # ...and stops the moment the article is anything else. Every one of these
    # was reported as a possible party before the rule.
    'Plaintiff sues under California\'s Unruh Civil Rights Act ("Unruh Act").',
    'Plaintiff pleads violations of Song-Beverly Consumer Warranty Act '
    '("Song-Beverly Act").',
    'This case arises under Rosenthal Fair Debt Collection Practices Act '
    '("Rosenthal Act").',
    'Defendant violated Tom Bane Civil Rights Act ("Bane Act") that day.',
    'This implicates Jones Act ("Jones Act") seaman status for plaintiff.',
    'Plaintiff cites Costa-Hawkins Rental Housing Act ("Costa-Hawkins").',
    # ...and the siblings of "Act", which fail identically.
    'Plaintiff cites Beverly Hills Rent Stabilization Ordinance '
    '("Rent Ordinance").',
    'Violations of California Labor Code ("Labor Code") are alleged.',
])
def test_a_defined_STATUTE_is_not_a_party(text):
    """A California statute is named after the LEGISLATOR who carried it, so
    Unruh, Song-Beverly, Rosenthal, Bane, Jones and Costa-Hawkins are all
    surnames standing at the head of the run — which is exactly what the
    name-shape test is looking for. Refused whole: neither the full name nor
    the short form earns a row."""
    assert _defined(text) == []


def test_the_statute_rule_is_STRUCTURAL_not_a_word_list():
    """`_PN_COMMON_WORDS` already carries this lesson: "Act" was once swallowed
    into that gazetteer and took the surnames Bane and Fair with it. The rule
    reads the LAST word of the name instead, so the words stay as reportable
    as they ever were."""
    assert "act" not in P._PN_COMMON_WORDS
    text = 'Defendant Marcus Bane ("Bane") was served at his residence.'
    assert _defined(text) == ["Bane", "Marcus Bane"]


@pytest.mark.parametrize("text,found", [
    ('Plaintiff retained Sedgwick Law ("Sedgwick") as counsel.',
     ["Sedgwick", "Sedgwick Law"]),
    ('Defendant retained Linford Law Group ("Linford") to defend.',
     ["Linford", "Linford Law Group"]),
])
def test_law_and_rule_are_deliberately_not_statute_words(text, found):
    """A law FIRM is defined in exactly this shape, and Rule is a surname. The
    cost of a wrong entry is a name neither faked nor flagged — the "Spellman"
    leak this tier exists to catch — so the set stays at words no person and no
    firm is ever called."""
    assert not {"law", "rule"} & set(P._PN_STATUTE_TAIL_WORDS)
    assert _defined(text) == found


# ── 1b. a definition names TWO values ───────────────────────────────────────

def test_both_the_full_name_and_the_short_form_are_reported():
    """The export usually carries the SHORT form on every page after the
    definition, so a worksheet naming only the parent asks about the spelling
    that appears once and says nothing about the one that appears eighty
    times."""
    text = 'This is about Zachary Coderre ("Coderre") and his employment.'
    assert _defined(text) == ["Coderre", "Zachary Coderre"]


def test_each_value_is_asked_SEPARATELY_whether_it_survived():
    """One of the two is routinely bound while the other is not. That
    asymmetry IS the finding: an entity's bare token is deliberately withheld
    (`_corpus_prunable`), so the export ships the full name faked and the
    short form standing on every page after it — reported by `surviving_reals`
    never (it is not a tracked value) and by `half_scrubbed_scan` never (it
    wants a person fake beside a real token)."""
    pz = _pz(["Sunrise Motors Group, LLC"])
    src = ('Defendant Sunrise Motors Group, LLC ("Sunrise") sold the vehicle. '
           'Sunrise then refused a refund.')
    out = pz.apply(src)
    assert "Sunrise Motors Group" not in out      # the parent was bound...
    assert "Sunrise" in out                       # ...and the short form was not
    assert pz.surviving_reals(out) == []          # nothing else reports it
    assert _defined(src, pz) == ["Sunrise"], "the standing short form"


def test_a_short_form_that_is_pure_vocabulary_still_earns_no_row():
    """`Master Services Agreement ("Agreement")` says nothing about a party,
    and reporting the short form does not relax the screen that says so."""
    assert _defined('The parties entered a Master Services Agreement '
                    '("Agreement").') == []


def test_the_short_form_row_is_not_a_duplicate_of_the_parent():
    """A one-word parent defining itself carries no name evidence at all and
    is refused before any of this — so the two rows are never the same value
    written twice."""
    text = 'The court construed the Lease ("Lease") narrowly.'
    assert _defined(text) == []


# ── 2. the verb anchor ──────────────────────────────────────────────────────

@pytest.mark.parametrize("text,found", [
    ("Spellman confirmed the transfer on May 5, 2024.", "Spellman"),
    ("Susan Spellman testified at her deposition.", "Susan Spellman"),
    ("Defendant Sarkisyan resigned in March.", "Sarkisyan"),
    ("On May 5 Ms. Rasho emailed the branch manager.", "Rasho"),
    ("Dr. Ardeshirpour explained the procedure.", "Ardeshirpour"),
])
def test_a_name_is_the_thing_that_does_something(text, found):
    assert _narrative(text) == [found]


def test_the_finding_carries_its_own_class():
    pz = _pz()
    assert pz.narrative_name_scan("Spellman confirmed it.") == [
        ("narrative name?", "Spellman")]


def test_an_honorific_is_a_title_and_not_the_name():
    """"Ms. Rasho emailed" is a row about Rasho: keeping the title would mint a
    term narrower than the surname the rest of the document uses."""
    assert _narrative("Ms. Rasho emailed counsel.") == ["Rasho"]


@pytest.mark.parametrize("text", [
    "Plaintiff alleges that the contract was breached.",
    "The Court found that the demurrer was well taken.",
    "This Court held otherwise.",
    "Counsel stated that no response was received.",
    "The Complaint alleges four causes of action.",
    "The Agreement provided for arbitration.",
    "AL asked for more time.",
])
def test_ordinary_pleading_vocabulary_is_not_a_name(text):
    assert _narrative(text) == []


def test_a_heading_is_not_prose():
    """The verb must be written in LOWER CASE. A section title capitalises
    every word of itself, which is what separates the two."""
    assert _narrative("Doe Failed To Mitigate Her Damages") == []
    assert _narrative("SPELLMAN CONFIRMED THE TRANSFER") == []


def test_our_own_stand_in_is_never_reported():
    """A fake this run minted is not a leak, however it is standing."""
    pz = _pz(["Susan Spellman"])
    out = pz.apply("Susan Spellman confirmed the transfer.")
    assert pz.narrative_name_scan(out) == []


def test_the_original_is_evidence():
    """A word absent from the source cannot have survived from it — the rule
    `note_original` states, applied to this tier too."""
    pz = _pz()
    pz.note_original("The parties disputed the amount.")
    assert pz.narrative_name_scan("Spellman confirmed it.") == []
    pz2 = _pz()
    pz2.note_original("Spellman confirmed it in writing.")
    assert _narrative("Spellman confirmed it.", pz2) == ["Spellman"]


def test_an_authority_is_masked_out_of_the_verb_scan_too():
    text = "In Kremerman v. White (2021) 71 Cal.App.5th 358 the court agreed."
    assert "Kremerman" not in _narrative(text)


# ── 3. noise ────────────────────────────────────────────────────────────────

_PLEADING_PROSE = """
The motion was filed on May 5 and served the same day. The Complaint alleges
four causes of action. Plaintiff alleges that the contract was breached, and
Defendant contends that the claim is time-barred. This Court held otherwise in
a prior ruling. Counsel stated that no response was received. The Agreement
provided for arbitration of any dispute arising out of the Retail Installment
Contract, and the Subject Property is described in Exhibit A. The Notice of
Motion and Motion to Quash Service of Summons was heard and argued. The parties
executed a Master Services Agreement, and the Request for Judicial Notice was
granted. The Legislature intended a broad remedy. Exhibit B shows the
signature. The Separate Statement of Undisputed Material Facts is unopposed.
Nothing in the Declaration of Custodian of Records supports the opposition.
"""


def test_neither_tier_reads_ordinary_pleading_prose_as_a_name():
    """The whole vocabulary the four hand-kept gazetteers were each written
    after a motion type shipped with its subject matter renamed. Neither tier
    may add to that history."""
    pz = _pz()
    assert pz.defined_name_scan(_PLEADING_PROSE, _PLEADING_PROSE) == []
    assert pz.narrative_name_scan(_PLEADING_PROSE) == []


# The fictional names this repo's own notes are written in. A finding made
# entirely of these is the document's worked example being read correctly, not
# a misread — the distinction the bound below is actually about.
_WORKED_EXAMPLE_WORDS = {
    "acme", "corporation", "inc", "amezcua", "ashely", "coderre", "cruz",
    "de", "group", "kool", "langley", "law", "linford", "llc", "maria",
    "marlowe", "marcus", "bane", "helen", "motors", "mortgage", "nationstar",
    "rasho", "sarkisyan", "sedgwick", "spellman", "sunlight", "sunrise",
    "susan", "financial", "zachary",
}


def test_both_tiers_stay_quiet_on_dense_technical_prose():
    """This repo's own notes are 200 KB of capitalised technical vocabulary in
    running sentences — the shape both scans are most likely to misread. What
    they DO report there is the document's own worked examples ("Susan
    Spellman", "Spellman confirmed", "Ashely Langley"), which is the scans
    working; the bound is on everything else.

    Measured on EVERYTHING ELSE, and not on the blended total, because the
    total is dominated by the examples: every rule that earns a worked example
    in the notes adds findings the scans are RIGHT about, so a blended cap
    drifts upward for good reasons and stops saying anything about misreads.
    Today the residue is "PDF", "MuPDF" and "EXPORT" — three pieces of this
    project's own vocabulary, none of them a name."""
    import pathlib
    root = pathlib.Path(P.__file__).resolve().parent
    text = (root / "CLAUDE.md").read_text(encoding="utf-8")
    pz = _pz()
    found = {s for _c, s in pz.defined_name_scan(text, text)}
    found |= {s for _c, s in pz.narrative_name_scan(text)}
    residue = sorted(v for v in found
                     if not all(P._pn_word_base(w) in _WORKED_EXAMPLE_WORDS
                                for w in v.split()))
    assert len(residue) <= 4, residue
