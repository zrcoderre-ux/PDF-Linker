"""An OCR'd exhibit IDENTIFIER is read against the document's series.

OCR reads a 1 as a capital I or a lower-case l and a 0 as a capital O, so
a scanned slip sheet arrives as EXHIBIT "I", EXHIBIT l or EXHIBIT lO. The
first of those is a perfectly good cover in a LETTERED set and exhibit 1
in a NUMBERED one, and nothing about the line itself can say which. The
series decides: the document's unambiguous covers first ("2" and "3"
beside it, or "A" and "B"), the body's own references where those tie
("attached hereto as Exhibit 1"), and the letter where nothing decides —
which is what an EXHIBIT I cover always meant before.

Run:  cd PDF-Linker && python3 -m pytest tests/test_exhibit_ocr_identifier.py -v
"""
import pytest

import pdf_linker as P


# ── readings: what an identifier may be ────────────────────────────────────

@pytest.mark.parametrize("raw,number,letters", [
    ("1", "1", None),          # a digit is only a number
    ("12", "12", None),
    ("A", None, "A"),          # a capital is only a letter…
    ("I", "1", "I"),           # …unless OCR could have made it of a 1
    ("II", "11", "II"),        # or of an 11 (II is a valid doubled letter)
    ("l", "1", None),          # lower-case l is never an exhibit letter
    ("O", None, "O"),          # a lone O cannot be exhibit 0
    ("OO", None, "OO"),
    ("IO", "10", "IO"),        # both readings stand; the number takes it (below)
    ("lO", "10", None),
    ("I2", "12", None),
    ("2O", "20", None),
    ("III", "111", None),
    ("AB", None, "AB"),        # the AA/AB convention is still a letter
    ("OOO", None, None),
])
def test_an_identifier_has_the_readings_ocr_could_have_made(raw, number, letters):
    assert P._exhibit_ident_readings(raw) == (number, letters)


@pytest.mark.parametrize("raw,ambiguous", [
    ("I", True), ("II", True),
    ("IO", False), ("O", False), ("OO", False), ("l", False), ("1", False),
    ("A", False), ("AB", False),
])
def test_only_i_and_ii_are_for_the_series_to_decide(raw, ambiguous):
    assert P._exhibit_ident_ambiguous(raw) is ambiguous


# ── the cover regex admits the OCR-digit shapes, strictly ──────────────────

@pytest.mark.parametrize("line,raw", [
    ("EXHIBIT ''I''", "I"),
    ("EXHIBIT l", "l"),
    ("EXHIBIT ''l''", "l"),
    ("EXHIBIT ' ' lO ''", "lO"),
    ("EXHIBIT I2", "I2"),
    ("EXHIBIT ''II''", "II"),
    ("EXHIBIT l - Lease", "l"),
])
def test_the_cover_regex_carries_the_raw_ocr_identifier(line, raw):
    m = P._exhibit_cover_match(line)
    assert m is not None, line
    assert P._exhibit_match_raw(m) == raw


@pytest.mark.parametrize("line", [
    "EXHIBIT l hereby declare",     # the OCR-digit branch is strict, like a letter
    "EXHIBIT lO is attached",
    "EXHIBIT llll",                 # four characters is no exhibit number
])
def test_the_ocr_digit_branch_admits_no_trailing_prose(line):
    assert P._exhibit_cover_match(line) is None


def test_an_unambiguous_letter_still_takes_the_letter_branch():
    m = P._exhibit_cover_match('EXHIBIT "A"')
    assert m.group("letter") == "A" and m.group("mixed") is None


# ── the series decides an ambiguous reading ────────────────────────────────

def test_a_numbered_set_reads_i_as_one():
    assert P._exhibit_series_numeric(["I", "2", "3"]) is True
    assert P._exhibit_resolve_ident("I", True) == "1"


def test_a_lettered_set_reads_i_as_the_letter():
    assert P._exhibit_series_numeric(["I", "A", "B"]) is False
    assert P._exhibit_resolve_ident("I", False) == "I"


def test_an_ocr_only_shape_needs_no_series():
    assert P._exhibit_resolve_ident("l", False) == "1"
    assert P._exhibit_resolve_ident("lO", False) == "10"
    assert P._exhibit_resolve_ident("IO", False) == "10"
    assert P._exhibit_resolve_ident("AB", True) == "AB"
    assert P._exhibit_resolve_ident("O", True) == "O"
    assert P._exhibit_resolve_ident("OOO", True) is None


def test_with_nothing_to_decide_the_letter_wins():
    assert P._exhibit_series_numeric(["I"]) is False
    assert P._exhibit_series_numeric(["I", "2", "A"]) is False


# ── end to end ─────────────────────────────────────────────────────────────

def _doc(cover_lines, body="A true and correct copy is attached as"):
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    first = doc.new_page(width=612, height=792)
    first.insert_text((90, 200), body)
    for line in cover_lines:
        pg = doc.new_page(width=612, height=792)
        pg.insert_text((220, 396), line, fontsize=20)
        content = doc.new_page(width=612, height=792)
        content.insert_text((90, 200), "Contents of the exhibit.")
    return doc


def test_an_ocr_read_first_cover_joins_its_numbered_set():
    doc = _doc(["EXHIBIT ''I''", "EXHIBIT ''2''", "EXHIBIT ''3''"])
    covers, label_pages = P._find_exhibit_cover_pages(doc)
    assert set(covers) == {"1", "2", "3"}
    assert covers["1"] == [1]
    assert label_pages == {1, 3, 5}


def test_the_same_cover_stays_a_letter_in_a_lettered_set():
    doc = _doc(['EXHIBIT "I"', 'EXHIBIT "J"', 'EXHIBIT "K"'])
    covers, _ = P._find_exhibit_cover_pages(doc)
    assert set(covers) == {"I", "J", "K"}


def test_a_lower_case_l_and_a_capital_o_read_as_digits_whatever_the_set():
    doc = _doc(["EXHIBIT l", "EXHIBIT 2", "EXHIBIT lO"])
    covers, _ = P._find_exhibit_cover_pages(doc)
    assert set(covers) == {"1", "2", "10"}


def test_the_body_breaks_a_tie_toward_numbers():
    doc = _doc(["EXHIBIT ''I''"],
               body="A true copy of the lease is attached as Exhibit 1.")
    covers, _ = P._find_exhibit_cover_pages(doc)
    assert set(covers) == {"1"}


def test_the_body_breaks_a_tie_toward_letters():
    doc = _doc(["EXHIBIT ''I''"],
               body="A true copy of the lease is attached as Exhibit I.")
    covers, _ = P._find_exhibit_cover_pages(doc)
    assert set(covers) == {"I"}


def test_a_lone_ambiguous_cover_with_no_context_is_the_letter():
    doc = _doc(["EXHIBIT ''I''"])
    covers, _ = P._find_exhibit_cover_pages(doc)
    assert set(covers) == {"I"}


def test_the_bookmark_reads_the_resolved_number():
    doc = _doc(["EXHIBIT ''I''", "EXHIBIT ''2''"])
    covers, _ = P._find_exhibit_cover_pages(doc)
    tree = P._build_bookmark_tree(doc, [], covers, [])
    titles = [title for _lvl, title, _pg in tree]
    assert "Exhibit 1" in titles and "Exhibit 2" in titles
    assert "Exhibit I" not in titles


# ── body references and footer labels follow the resolved number ───────────

def test_ocr_spellings_of_a_number():
    assert set(P._exhibit_ocr_spellings("1")) == {"I", "l"}
    assert set(P._exhibit_ocr_spellings("10")) == {"IO", "lO", "1O", "I0", "l0"}
    assert P._exhibit_ocr_spellings("2") == ()
    assert P._exhibit_ocr_spellings("A") == ()


def test_a_body_reference_spelled_by_ocr_links_to_the_numbered_exhibit():
    import logging
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    body = doc.new_page(width=612, height=792)
    body.insert_text((90, 200), "A true copy is attached as Exhibit I hereto.")
    body.insert_text((90, 230), "A second copy is attached as Exhibit 2 hereto.")
    for line in ("EXHIBIT ''I''", "EXHIBIT ''2''"):
        pg = doc.new_page(width=612, height=792)
        pg.insert_text((220, 396), line, fontsize=20)
    linked, covers = P._link_exhibit_references(doc, logging.getLogger("t"))
    assert set(covers) == {"1", "2"}
    targets = sorted(l["page"] for l in doc[0].get_links() if l.get("page") is not None)
    assert targets == [1, 2]


@pytest.mark.parametrize("label,ident,expected", [
    ("EXHIBIT I", "1", True),
    ("EXHIBIT lO", "10", True),
    ("EXHIBIT ''l''", "1", True),
    ("EXHIBIT I", "I", True),
    ("EXHIBIT I", "2", False),
    ("EXHIBIT O", "0", False),
])
def test_a_footer_label_spelled_by_ocr_is_still_its_exhibits_id(label, ident, expected):
    assert P._label_is_just_exhibit_id(label, ident) is expected
