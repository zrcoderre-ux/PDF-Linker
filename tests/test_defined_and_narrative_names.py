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
    assert _defined(text) == ["Susan Spellman"]


def test_the_finding_carries_its_class():
    pz = _pz()
    text = 'Susan Spellman ("Spellman") signed the lease.'
    assert pz.defined_name_scan(text, text) == [("defined name?",
                                                 "Susan Spellman")]
    # ...and accumulates into the folder review list the worksheet is built from
    assert ("defined name?", "Susan Spellman") in pz.review


@pytest.mark.parametrize("text,found", [
    ('Defendant ACME CORPORATION, INC. ("Acme") answered.',
     "ACME CORPORATION, INC."),
    ('Sunlight Financial LLC ("Sunlight") funded the loan.',
     "Sunlight Financial LLC"),
    ('Cross-Defendant Mr. Kool\'s Collision, LLC ("Kool\'s") demurs.',
     "Mr. Kool's Collision, LLC"),
    ('MARIA CRUZ DE AMEZCUA ("Amezcua") was served on May 5.',
     "MARIA CRUZ DE AMEZCUA"),
])
def test_shapes_a_california_complaint_actually_uses(text, found):
    assert _defined(text) == [found]


def test_a_leading_role_word_is_trimmed_not_fatal():
    """"Plaintiff HELEN RASHO, an individual" is the commonest caption form
    there is; a screen that refused any run carrying a role word would yield
    nothing at all."""
    text = 'Plaintiff HELEN RASHO ("Rasho") filed suit.'
    assert _defined(text) == ["HELEN RASHO"]


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
    assert _defined(text) == ["Carpenter Smith"]


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
    """A brief that defines a short form INSIDE a cite offers the cited party
    up as this case's own, and a `yes` on that row would mint it as an
    AUTHORITATIVE term and rename the decision in every export."""
    text = ('(See Ewald v. Nationstar Mortgage, LLC ("Nationstar") '
            '(2017) 13 Cal.App.5th 947.)')
    assert _defined(text) == []


def test_the_guard_does_not_depend_on_the_parser_succeeding():
    """The span check asks what the parser could READ, and a parse that fails
    hands back nothing at all — a short cite, or one whose reporter run the
    scan mangled. So the SHAPE is checked too: a run standing after a " v. "
    with nothing but more party name between is a cited decision's party
    whatever the parser managed. The doctrine `_in_authority_context` states
    for the rewrite path, applied to the report."""
    blind = _pz()
    blind._protected_citation_spans = lambda t: []
    assert _defined('(See Ewald v. Nationstar Mortgage, LLC ("Nationstar") '
                    '(2017) 13 Cal.App.5th 947.)', blind) == []
    # The shape that has no year or reporter left beside it at all, which is
    # what the span check cannot see even unblinded.
    assert _defined('See Market Lofts Community Assn. v. 9th Street Market '
                    'Lofts, LLC ("Market Lofts"), which held otherwise.') == []
    # …and the other way a case names itself, with no " v. " in it at all.
    assert _defined('(See In re Marriage of Kelley Hartwell ("Hartwell") '
                    '(2008) 167 Cal.App.4th 562.)') == []


def test_a_case_short_name_is_not_a_party():
    """`… (hereinafter "Mkt Lofts v 9th St")` is the document saying what it
    will call an AUTHORITY. No party of any matter is named "X v. Y", so the
    versus token settles it on the parenthetical's own text — which is what
    makes it hold where the shape of the surrounding cite does not."""
    assert _defined(
        'Market Lofts Community Assn. v. 9th Street Market Lofts, LLC (2014) '
        '222 Cal.App.4th 924, 932 (hereinafter "Mkt Lofts v 9th St") is '
        'controlling.') == []


def test_the_real_party_is_still_reported():
    """The screens above are shaped on the CITE, so a party defined in ordinary
    prose — the whole reason this tier exists — is untouched by them."""
    assert _defined('Plaintiff Susan Spellman ("Spellman") signed the lease.') \
        == ["Susan Spellman"]
    assert _defined('Defendant Sunrise Motors Group ("Sunrise") sold it.') \
        == ["Sunrise Motors Group"]


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
    assert _defined(text, pz) == ["Susan Spellman"]
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


def test_both_tiers_stay_quiet_on_dense_technical_prose():
    """This repo's own notes are 200 KB of capitalised technical vocabulary in
    running sentences — the shape both scans are most likely to misread. What
    they DO report there is the document's own worked examples ("Susan
    Spellman", "Spellman confirmed", "Ashely Langley"), which is the scans
    working; the bound is on everything else."""
    import pathlib
    root = pathlib.Path(P.__file__).resolve().parent
    text = (root / "CLAUDE.md").read_text(encoding="utf-8")
    pz = _pz()
    found = {s for _c, s in pz.defined_name_scan(text, text)}
    found |= {s for _c, s in pz.narrative_name_scan(text)}
    # The notes' own worked examples: each is a name the scans are MEANT to
    # report, quoted in the prose as the shape they exist for. The bound is
    # on what is left once those are set aside, so growing the notes with
    # another example never moves it.
    examples = {
        "Susan Spellman", "Spellman", "ACME CORPORATION, INC.", "Rasho",
        "Sarkisyan", "Ashely Langley", "David", "Sunbelt Rentals LLC",
        "Sunbelt Rentals", "Providence Holy Cross Medical",
    }
    noise = found - examples
    assert len(noise) <= 5, sorted(noise)
