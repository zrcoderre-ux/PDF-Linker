"""A double-struck exhibit label still yields its 'Exhibit A' bookmark.

An exhibit slip sheet whose big label is set as a faux-bold double strike
LOOKS like 'Exhibit A' on the page, but the text layer carries every glyph
twice and extraction returns the copies of each character adjacent, so the
label copies out as

    EEXXHHIIBBIITT ""AA""

(native to the PDF, not an OCR artifact — Tesseract does not emit doubled
characters). _EXHIBIT_COVER_RE never matches that, so the exhibit got no
cover page, no bookmark, and no body links. A delivered batch carried its
whole exhibit set A-E this way. _undouble_strike collapses the interleaved
form and _exhibit_cover_match also tolerates the run-repeated form the row
merger produces when the two copies extract as separate runs on one
baseline ('EXHIBIT "A" EXHIBIT "A"').

Run:  cd PDF-Linker && python3 -m pytest tests/test_double_strike_exhibit.py -v
"""
import pytest

import pdf_linker as P

fitz = pytest.importorskip("fitz")


def _double(text: str) -> str:
    """Double every non-space character, the way the strike extracts."""
    return "".join(ch if ch.isspace() else ch * 2 for ch in text)


# ── _undouble_strike: what halves and what must not ─────────────────────────

def test_the_reported_label_halves_to_its_visual_reading():
    assert P._undouble_strike('EEXXHHIIBBIITT ""AA""') == 'EXHIBIT "A"'


@pytest.mark.parametrize("letter", ["B", "C", "D", "E"])
def test_the_whole_delivered_set_halves(letter):
    assert (P._undouble_strike(_double(f'EXHIBIT "{letter}"'))
            == f'EXHIBIT "{letter}"')


def test_a_stray_unpaired_glyph_does_not_break_the_halving():
    # The operator's own transcription of exhibit B carried three quotes —
    # one lost its twin. One single among nine pairs still reads as struck.
    assert P._undouble_strike('EEXXHHIIBBIITT ""BB"') == 'EXHIBIT "B"'


def test_curly_quotes_halve_too():
    assert (P._undouble_strike("EEXXHHIIBBIITT ““AA””")
            == "EXHIBIT “A”")


def test_a_genuinely_doubled_exhibit_letter_survives_the_halving():
    # Exhibit AA struck twice extracts as AAAA and must come back as AA,
    # not A.
    assert P._undouble_strike("EEXXHHIIBBIITT AAAA") == "EXHIBIT AA"


@pytest.mark.parametrize("text", [
    "EXHIBIT AA",             # single-struck double letter: EXHIBIT pairs nowhere
    "BOOKKEEPER RECORDS",     # genuine doubled letters are a minority of the line
    "EXHIBIT A",              # nothing doubled at all
    "",                       # empty line
    "see Aanenson v. Baker",  # ordinary prose
])
def test_single_struck_text_is_never_halved(text):
    assert P._undouble_strike(text) is None


# ── _exhibit_cover_match: the fallback chain ────────────────────────────────

@pytest.mark.parametrize("line,ident", [
    ('EXHIBIT "A"', "A"),                      # plain match still first
    ('EEXXHHIIBBIITT ""AA""', "A"),            # interleaved double strike
    ('EEXXHHIIBBIITT ""EE""', "E"),
    (_double("EXHIBIT 5"), "5"),               # numeric labels strike too
    ('EXHIBIT "A" EXHIBIT "A"', "A"),          # two copies as separate runs
    ("EXHIBIT C EXHIBIT C", "C"),
])
def test_a_twice_drawn_label_matches_and_names_the_right_exhibit(line, ident):
    m = P._exhibit_cover_match(line)
    assert m is not None, line
    assert (m.group("num") or m.group("letter")) == ident


@pytest.mark.parametrize("line", [
    "EXHIBIT Apple",                # never matched before, still not
    "Exhibit a",                    # lowercase letter refs stay unlinked
    "The contract, EXHIBIT A, was", # not a standalone label row
    "SEE SEE",                      # a repeated word that is no label
])
def test_the_fallbacks_admit_nothing_the_regex_refused_for_cause(line):
    assert P._exhibit_cover_match(line) is None


# ── end to end: covers found, bookmarks labelled 'Exhibit A' ────────────────

def _doc_with_struck_slip_sheets(letters=("A", "B", "C", "D", "E")):
    doc = fitz.open()
    body = doc.new_page(width=612, height=792)
    body.insert_text((90, 200), "A true and correct copy is attached as")
    for letter in letters:
        pg = doc.new_page(width=612, height=792)
        pg.insert_text((220, 396), _double(f'EXHIBIT "{letter}"'), fontsize=20)
        content = doc.new_page(width=612, height=792)
        content.insert_text((90, 200), f"Contents of exhibit {letter}.")
    return doc


def test_struck_covers_are_found_under_their_visual_identifiers():
    doc = _doc_with_struck_slip_sheets()
    covers, label_pages = P._find_exhibit_cover_pages(doc)
    assert set(covers) == {"A", "B", "C", "D", "E"}
    # Slip sheets sit at pages 1, 3, 5, 7, 9 of the fixture.
    assert covers["A"] == [1]
    assert covers["E"] == [9]
    assert label_pages == {1, 3, 5, 7, 9}


def test_the_bookmarks_read_exhibit_a_not_the_struck_text():
    doc = _doc_with_struck_slip_sheets()
    covers, _ = P._find_exhibit_cover_pages(doc)
    tree = P._build_bookmark_tree(doc, [], covers, [])
    titles = [title for _lvl, title, _pg in tree]
    for letter in "ABCDE":
        assert f"Exhibit {letter}" in titles
    assert not any("EEXX" in t or '""' in t for t in titles)
