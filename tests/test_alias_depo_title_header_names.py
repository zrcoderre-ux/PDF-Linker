"""Four name anchors nothing read, found by probing the whole pipeline.

Each shape below was run through every harvest pass and every review scan as
they stood, and came back with nothing.

1. AN ALIAS IN BODY TEXT. `_PN_AKA_ALTS` existed only to split a template CELL,
   so "Defendant John Smith, also known as Johnny Smythe" reached no pass:
   the legal name was bound and faked and the alias shipped verbatim in the
   SAME SENTENCE — "Defendant Wemyss Paget, also known as Johnny Smythe" —
   with every scan silent. The fuzzy sweep cannot reach it (two edits at a
   length where the fold allows one) and `half_scrubbed_scan` does not fire,
   because the alias is a whole name rather than a token beside a fake.

2. THE DEPOSITION FAMILY. "Declaration of X" and "X Decl." are both harvested;
   "DEPOSITION OF X" and "X Depo. 45:12" yielded nothing at all, though a
   summary-judgment motion cites deposition testimony constantly and the
   deponent is routinely on no party template.

3. A TITLE IN FRONT OF A WORD. "Mr. Spellman", "Ms. Delacroix" — the shortest
   corroborated anchor there is, and invisible to the role-anchored tier and to
   the verb-anchored one alike.

4. AN E-MAIL HEADER LINE. The display-name path needs a `Name <addr>` pair, so
   an exhibit e-mail printed with "From:" / "To:" on their own lines named
   people nothing read.

1 and 2 harvest (the corroboration is a dba's / a Decl.'s); 3 and 4 REPORT.

Run:  cd PDF-Linker && python3 -m pytest tests/test_alias_depo_title_header_names.py -v
"""
import pytest

import pdf_linker as P


def _pz(names=(), detectors=False):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), [], [], registry=reg)
    return P.Pseudonymizer(
        terms, list(P._PN_DEFAULT_DETECTORS) if detectors else [], registry=reg)


# ── 1. an alias stated in body text ─────────────────────────────────────────

def test_the_alias_shipped_beside_its_own_party_s_fake():
    """The reported failure, end to end: bound name faked, alias left standing
    in the same sentence, nothing flagged."""
    pz = _pz(["John Smith"])
    text = ("Defendant John Smith, also known as Johnny Smythe, opened the "
            "account as Johnny Smythe.")
    P._pn_learn_from_text(pz, text)
    out = pz.apply(text)
    assert "Johnny Smythe" not in out
    assert "John Smith" not in out
    assert pz.surviving_reals(out) == []


@pytest.mark.parametrize("text,pair", [
    ('Defendant John Smith, also known as Johnny Smythe, sued.',
     ("John Smith", "Johnny Smythe")),
    ('Plaintiff Susan Spellman, a/k/a Susan Delacroix, testified.',
     ("Susan Spellman", "Susan Delacroix")),
    ('Defendant Marcus Delacroix, erroneously sued as Mark Delacroix, demurs.',
     ("Marcus Delacroix", "Mark Delacroix")),
])
def test_the_marker_forms_a_complaint_actually_uses(text, pair):
    assert P._pn_alias_pairs(text) == [pair]


def test_a_leading_role_word_is_trimmed_off_the_head():
    """"Defendant John Smith, aka ..." is how the sentence is written; the same
    trim `_pn_label_names` applies to a caption is what keeps the pair usable."""
    head, _tail = P._pn_alias_pairs(
        "Cross-Defendant John Smith, aka Johnny Smythe, answered.")[0]
    assert head == "John Smith"


@pytest.mark.parametrize("text", [
    "This is known as the American rule, and it applies here.",
    "The doctrine is also known as equitable tolling in this District.",
    "The motion is denied as to the second cause of action.",
])
def test_prose_that_merely_carries_the_words_is_not_a_pair(text):
    assert P._pn_alias_pairs(text) == []


def test_a_role_word_INSIDE_a_side_means_the_phrase_ran_past_the_name():
    assert P._pn_alias_pairs(
        "John Smith, aka Defendant Two, appeared.") == []


def test_the_alias_inherits_the_head_s_kind():
    """A dba is always a business; an alias is the same kind of thing as its
    head — which is what `_pn_append_name_terms` already does with the joined
    value, so an entity alias takes the entity path."""
    pz = _pz()
    P._pn_learn_from_text(
        pz, "ACME HOLDINGS, INC., formerly known as Acme Ventures LLC, answered.")
    cats = {t.category for t in pz.terms if "acme" in t.real.lower()}
    assert cats and cats <= {"entity", "entity-token"}


# ── 2. the deposition family ────────────────────────────────────────────────

@pytest.mark.parametrize("text,found", [
    ("DEPOSITION OF SUSAN SPELLMAN, taken on May 5, 2024.", "SUSAN SPELLMAN"),
    ("Excerpts of the Deposition of Susan Spellman are attached.",
     "Susan Spellman"),
    ("Videotaped Deposition of Marcus Delacroix, Volume II.", "Marcus Delacroix"),
])
def test_a_deposition_title_names_its_deponent(text, found):
    assert P._pn_declarant_names(text) == [found]


@pytest.mark.parametrize("text,found", [
    ("(Spellman Depo. 45:12-16.)", ["Spellman"]),
    ("(Delacroix Dep. 88:2.)", ["Delacroix"]),
    ("See Spellman Deposition, Vol. II.", ["Spellman"]),
])
def test_a_deposition_short_cite_names_its_deponent(text, found):
    assert P._pn_declarant_ref_names(text) == found


def test_a_deposition_descriptor_is_not_the_deponent():
    """The `Supporting Declaration` rule, applied to the deposition words:
    "Videotaped Deposition" must not read as a deponent named Videotaped."""
    assert P._pn_declarant_ref_names(
        "Videotaped Deposition of Marcus Delacroix.") == []
    assert P._pn_declarant_ref_names("The Certified Deposition is lodged.") == []


@pytest.mark.parametrize("text", [
    "The hearing was set for Dec. 5, 2024 in Department 55.",
    "See the Department 1 order and the Decker Group filing.",
])
def test_a_longer_D_word_still_letters_out_to_nothing(text):
    """The validator is what makes the new words safe: "Department", "December"
    and "Decker" all reduce to something the set does not hold."""
    assert P._pn_declarant_ref_names(text) == []


def test_the_date_guard_stays_on_dec_alone():
    """"Depo. 45:12" is a page:line pin and must NOT take the date guard that
    "Dec. 5, 2024" needs."""
    assert "dec" in P._PN_DECL_REF_DATE_WORDS
    assert not (P._PN_DECL_REF_DATE_WORDS & {"depo", "dep", "deposition"})


# ── 3. a title in front of a word ───────────────────────────────────────────

def _titled(text, names=()):
    pz = _pz(names, detectors=True)
    return sorted(s for _c, s in pz.honorific_name_scan(pz.apply(text)))


@pytest.mark.parametrize("text,found", [
    ("At the meeting, Mr. Spellman and Ms. Delacroix signed.",
     ["Delacroix", "Spellman"]),
    ("Dr. Ardeshirpour performed the surgery.", ["Ardeshirpour"]),
    ("Mr. Spellman's employment ended in March.", ["Spellman"]),
    ("Counsel met Mr. O'Brien at the office.", ["O'Brien"]),
])
def test_a_title_is_a_person_reference(text, found):
    assert _titled(text) == found


def test_a_bound_party_is_silent():
    """`_pn_fake_person` keeps an honorific verbatim, so a party this run bound
    comes out "Mr. <fake>" and screens as neutral."""
    assert _titled("Mr. Spellman testified at length.", ["Susan Spellman"]) == []


def test_a_street_suffix_is_not_a_doctor():
    """"Dr" is the one title that is also an ordinary word of a filing, and it
    lands in exactly this shape: "1200 Sunset Dr Los Angeles" read as a doctor
    named Los. The period is what separates them."""
    assert _titled("The property is at 1200 Sunset Dr Los Angeles, CA 90012.") == []


def test_only_a_TRAILING_possessive_is_stripped():
    """An interior possessive is the name continuing: stripping it everywhere
    turned "Mr. Kool's Collision" into "Kool Collision", a value the document
    does not contain and a `yes` would key to nothing."""
    assert _titled("Cross-Defendant Mr. Kool's Collision, LLC demurs.") == \
        ["Kool's Collision"]


def test_the_run_stops_at_ordinary_vocabulary():
    """"Ms. Delacroix Was Terminated Without Cause" is a heading; the title
    governs the name, not the sentence after it."""
    assert _titled("Ms. Delacroix Was Terminated Without Cause") == ["Delacroix"]


# ── 4. an e-mail header line ────────────────────────────────────────────────

def _header(text):
    pz = _pz()
    return sorted(s for _c, s in pz.mail_header_name_scan(text))


def test_a_printed_header_names_its_correspondents():
    text = ("From: Susan Spellman\nSent: Monday, May 5\n"
            "To: Marcus Delacroix\nSubject: invoice")
    assert _header(text) == ["Marcus Delacroix", "Susan Spellman"]


@pytest.mark.parametrize("text", [
    "To: All Employees\nFrom: Accounts Payable\nCc: Undisclosed Recipients",
    "To: Purchasing\nFrom: Facilities Management",
    "To: Counsel of Record\nFrom: The Court",
])
def test_a_header_that_addresses_no_person_is_not_a_finding(text):
    """A header line is not only ever a person, which is exactly why this tier
    REPORTS rather than harvesting."""
    assert _header(text) == []


def test_the_anchor_is_the_line_head():
    """"from" and "to" are two of the commonest words in English; only the
    header form puts one at the head of a line with a colon after it."""
    assert _header("The letter was sent from Susan to Marcus on May 5.") == []


def test_a_single_word_header_is_not_a_name():
    assert _header("To: Marcus\nFrom: Susan") == []


def test_the_backoffice_block_swallows_no_surname():
    """The one screen `_PN_COMMON_WORDS` must pass — a word that doubles as a
    real name belongs in `_PN_SERVICE_GENERIC_WORDS` instead, so a party who
    carries it stays reportable."""
    for surname in ("green", "fair", "bane", "banks", "bell", "payne", "bond"):
        assert surname not in P._PN_BACKOFFICE_WORDS


# ── noise ───────────────────────────────────────────────────────────────────

def test_the_two_review_tiers_are_quiet_on_pleading_prose():
    prose = """
    The motion was filed on May 5 and served the same day. The Complaint
    alleges four causes of action. Plaintiff alleges that the contract was
    breached, and Defendant contends the claim is time-barred. This Court held
    otherwise. Counsel stated that no response was received. The Agreement
    provided for arbitration. To: the extent the opposition argues otherwise,
    it is unpersuasive. From: the record, no such showing appears.
    """
    pz = _pz()
    assert pz.honorific_name_scan(prose) == []
    assert pz.mail_header_name_scan(prose) == []
