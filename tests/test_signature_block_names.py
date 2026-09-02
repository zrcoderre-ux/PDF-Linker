"""A signature block says "Name:", and a scan lower-cases the name beside it.

One delivered batch shipped its own defendant's surname four times, in four
documents, with every leak scan silent:

    Complaint, Ex. 2, Guaranty No. 2      Name: <fake> vazqvez
                                          Prnt Name: <fake> v~zquei
    Tunstall Decl., Ex. 6, Guaranty No. 2 Name: <fake> vauiuez
    Woodbridge Decl. para 10              "..., vizquez executed a written
                                          Personal Guaranty agreement"

One shape underneath all four: every name tier asks for a CAPITAL first and
asks about the name second, and this exhibit's OCR lower-cases the surname it
mangles. The given name was bound and faked on the same line, so each block
shipped as a half-scrubbed pair reading like a finished scrub.

Two answers, at their own ends.

1. HARVEST. "Name:" / "Print Name:" is the document declaring that what
   follows is a name, so after it the value's own shape stops being the
   evidence: the lead word still carries the ordinary form, the words after it
   may be lower-case or carry the scanner's debris. The block is then SCRUBBED,
   not merely reported.

2. REPORT. `fuzzy_survivor_scan` admits a lower-case candidate where the SITE
   corroborates it — a name label, one of our own person fakes in the run, or
   the subject position of a narrative verb. That reaches the declaration's
   prose, which no label anchors.

Run:  cd PDF-Linker && python3 -m pytest tests/test_signature_block_names.py -v
"""
import logging

import pytest

import pdf_linker as P

log = logging.getLogger("test")


def _pz(names=("Eduardo Vazquez",)):
    reg = P._PnFakeRegistry()
    return P.Pseudonymizer(
        P._pn_build_terms(list(names), [], [], registry=reg), [], reg)


def _fake_of(pz, real):
    return str(next(t.fake for t in pz.terms if t.real == real))


# ── 1. the harvest ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("line,found", [
    ("Name: Eduardo vazqvez", "Eduardo vazqvez"),
    ("Prnt Name: Eduardo v~zquei", "Eduardo v~zquei"),
    ("Name: Eduardo vauiuez", "Eduardo vauiuez"),
    ("Print Name: Eduardo Vazquez", "Eduardo Vazquez"),
    ("PRINT NAME: Michael Rodgers", "Michael Rodgers"),
    ("a. Name: Michael Rodgers", "Michael Rodgers"),
])
def test_a_name_label_yields_the_name_whatever_its_case(line, found):
    """The label is the corroboration, so the words after the lead need not be
    Title-case — which is the entire reason the block reached no pass."""
    assert P._pn_label_names(line) == [found]


@pytest.mark.parametrize("line", [
    # Form furniture: the worry a bare "Name:" raises is a LABEL standing in
    # front of it, and the line discipline answers it — the label must OPEN
    # its line, so a qualified one never anchors.
    "BRANCH NAME: Stanley Mosk Courthouse",
    "COURT NAME: Superior Court of California",
    "FIRM NAME: Alder Law, P.C.",
    # An unfilled slot has no capitalised lead and yields nothing.
    "Name: ______________",
    "Name:",
    # The screens `_pn_label_names` already applies still apply.
    "Name: Plaintiff",
    "Name: Los Angeles County",
])
def test_what_the_label_still_refuses(line):
    assert P._pn_label_names(line) == []


def test_the_block_is_scrubbed_and_stays_one_person():
    """End to end: the harvested spelling is faked, and a spelling near enough
    to fold takes a misspelling of the party's OWN stand-in, so the export
    still reads as one person and every fake reverses one-to-one."""
    pz = _pz()
    src = ("GUARANTOR:\n"
           "Name: Eduardo vazqvez\n"
           "Name: Eduardo Vazquez\n")
    pz.register_label_names(src)
    out = pz.apply(src)
    assert "vazqvez" not in out and "Vazquez" not in out
    surname = _fake_of(pz, "Vazquez")
    # the mangled spelling folded onto a typo of the surname's own fake
    mangled = [w for w in out.split() if w.lower() != surname.lower()
               and P._pn_osa_distance(w.lower(), surname.lower()) == 1]
    assert mangled, out


def test_the_harvest_reaches_the_terms_the_scrub_applies():
    """`register_label_names` is the seam — a value read off the label has to
    become a live TERM or the block is read and left standing.

    The FULL name is what registers. No bare token falls out of the mangled
    word, and that is right rather than a gap: a bare token is cap-only
    (`_pn_term_is_cap_only`), so a token built from a lower-case real could
    never match its own spelling. Residual, and stated: the mangled surname
    standing ALONE, away from the given name, is not scrubbed by this — it is
    what the lower-case leak tier below reports."""
    pz = _pz()
    before = {t.real for t in pz.terms}
    pz.register_label_names("Name: Eduardo vazqvez\n")
    assert {t.real for t in pz.terms} - before == {"Eduardo vazqvez"}


# ── 2. the lower-case leak tier ─────────────────────────────────────────────

def test_the_lower_case_misspellings_are_reported():
    """All three lower-case spellings, each at a site that says "name" without
    reference to the word's own shape."""
    pz = _pz()
    given = _fake_of(pz, "Eduardo")
    out = (f" 3  Name: {given} vazqvez\n"
           f" 4  Name: {given} vauiuez\n"
           " 6  Concurrently with the execution of Loan Agreement No. 2, vizquez\n"
           " 7  executed a written Personal Guaranty agreement.\n")
    found = {v for _c, v in pz.fuzzy_survivor_scan(out)}
    assert {"vazqvez", "vauiuez", "vizquez"} <= found


def test_the_verb_may_sit_on_the_next_printed_line():
    """Legal prose wraps mid-sentence and the export keeps the gutter number,
    so the subject and its verb are routinely on different lines — which is how
    the declaration's own occurrence is printed."""
    pz = _pz()
    wrapped = (" 6  Concurrently with the execution of Loan Agreement No. 2, vizquez\n"
               " 7  executed a written Personal Guaranty agreement.\n")
    assert ("misspelled name?", "vizquez") in pz.fuzzy_survivor_scan(wrapped)


@pytest.mark.parametrize("site,text", [
    ("on a name label's own line", "Name: Buckminster vazqvez"),
    ("in a name run with one of our own stand-ins", "the guarantor Buckminster vazqvez signed"),
    ("the subject of a narrative verb", "On May 5, vazqvez executed the note."),
])
def test_each_corroboration_stands_on_its_own(site, text):
    assert P._pn_lower_name_site(
        text, text.index("vazqvez"), text.index("vazqvez") + 7,
        {"buckminster"}) == site


def test_an_uncorroborated_lower_case_word_is_not_a_finding():
    """The capital was standing in for evidence, and where there is none the
    tier must stay shut: admitting every lower-case word within the fold
    distance measured 38 rows of ordinary vocabulary on this repo's own notes.
    A word mid-clause in front of a narrative verb is prose, not a subject."""
    for text in ("the parties merely restate the record",
                 "which the macro writes into the row",
                 "a spelling nothing in the corpus carries"):
        for w in text.split():
            assert not P._pn_lower_name_site(
                text, text.index(w), text.index(w) + len(w), {"buckminster"})


def test_the_capital_tier_is_unchanged():
    """The widening adds a tier; it must not move the one that was there."""
    pz = _pz()
    out = "The guarantor Vazqvez signed the note."
    assert ("misspelled name?", "Vazqvez") in pz.fuzzy_survivor_scan(out)


def test_ordinary_prose_reports_no_lower_case_row():
    """Measured on this repo's own notes — 249 KB of capitalised technical
    vocabulary in running sentences, against a deliberately over-large tracked
    set. The corroboration is what makes the tier affordable: without it this
    same corpus turns up 38 rows, every one of them vocabulary
    ("squash"~"suasn", "readers"~"rogders", "merely"~"kelely").

    "Vazquez" is deliberately NOT tracked here. The notes now carry the
    doctrine this tier was written for, quoting its four spellings verbatim, so
    a run tracking that name reports them off the prose — correctly, which is
    the opposite of what this test measures."""
    import pathlib
    notes = pathlib.Path(__file__).resolve().parent.parent / "CLAUDE.md"
    pz = _pz(("Helen Rasho", "Marcus Delacroix", "Susan Spellman",
              "Michael Rodgers", "Westlake Financial", "Wharton Holdings",
              "Angela White", "Gregory Walton"))
    rows = pz.fuzzy_survivor_scan(notes.read_text(encoding="utf-8"))
    assert [v for _c, v in rows if v[:1].islower()] == []
