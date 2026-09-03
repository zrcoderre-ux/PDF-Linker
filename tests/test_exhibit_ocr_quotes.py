"""An OCR'd exhibit label still names its exhibit.

A scanned slip sheet reaches the tool through OCR, and OCR does not read
the big straight double quote a display face prints as one character. A
delivered exhibit set came back as

    EXHIBIT ''1''
    EXHIBIT ' ' 2 ''

— two apostrophes for each quote, sometimes with a space between them —
and _EXHIBIT_COVER_RE, which allowed exactly one quote character on each
side of the identifier, matched none of it: no cover page, no bookmark,
no body links. A quote is now a RUN of quote-shaped glyphs with optional
horizontal whitespace between them and before the identifier, on both
sides, and the footer-label matcher tolerates the same run.

Run:  cd PDF-Linker && python3 -m pytest tests/test_exhibit_ocr_quotes.py -v
"""
import pytest

import pdf_linker as P


# ── the cover regex reads every OCR spelling of a quoted label ─────────────

@pytest.mark.parametrize("line,ident", [
    ("EXHIBIT ''1''", "1"),            # the reported spelling
    ("EXHIBIT ' ' 2 ''", "2"),         # the other reported spelling
    ("EXHIBIT '' 3 ''", "3"),          # spaces between the run and the id
    ("EXHIBIT ''12''", "12"),          # two-digit id keeps both digits
    ("EXHIBIT ``4''", "4"),            # backtick pair for the opener
    ("EXHIBIT ″C″", "C"),    # double prime
    ("EXHIBIT „5“", "5"),    # low-9 opener a scan makes of a quote
    ("EXHIBIT ''A''", "A"),            # letters take the same run
    ("EXHIBIT ' ' B ' '", "B"),
    ("EXHIBIT ''AA''", "AA"),
    ("Exhibit ''6''", "6"),            # title-case label
    ("Ex. ''7''", "7"),                # short prefix
    ("EXHIBIT ''8'' - Lease", "8"),    # descriptor after the closing run
    ("EXHIBIT ''D'' — Guaranty", "D"),
    ("EXHIBIT ”9“", "9"),    # opener and closer swapped: OCR keeps no direction
    ("EXHIBIT ''10", "10"),            # closing run lost entirely
    ("EXHIBIT 11''", "11"),            # opening run lost entirely
    ('EXHIBIT "A"', "A"),              # the clean spellings still match
    ("EXHIBIT “5”", "5"),
    ("EXHIBIT 5", "5"),
])
def test_an_ocr_quoted_label_names_its_exhibit(line, ident):
    m = P._exhibit_cover_match(line)
    assert m is not None, line
    assert (m.group("num") or m.group("letter")) == ident


@pytest.mark.parametrize("line", [
    "EXHIBIT Apple",                    # never matched, still not
    "Exhibit a",                        # lower-case letter refs stay unlinked
    "EXHIBIT A, the contract was",      # a comma is not a quote and not a separator
    "EXHIBIT A's terms",                # a possessive is not a closing quote
    "The contract, EXHIBIT ''A'', was", # not a standalone label row
    "EXHIBIT '' '' ''",                 # a quote run with no identifier
    "EXHIBIT ''",
    "EXHIBIT ''1234''",                 # four digits is not an exhibit number
    "EXHIBIT ''ABC''",                  # three capitals is not an exhibit letter
])
def test_the_run_admits_nothing_the_regex_refused_for_cause(line):
    assert P._exhibit_cover_match(line) is None


# ── strictness survives the OCR spelling ───────────────────────────────────
# A lone cover feeds the bookmark tree only when it is STRICT — the label
# alone or with a separator before its descriptor. The strip that decides
# that used to remove ONE closing quote character, so an OCR'd lone cover
# read as loose ("'' " left standing) and the exhibit earned nothing.

def _doc(lines):
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    body = doc.new_page(width=612, height=792)
    body.insert_text((90, 200), "A true and correct copy is attached as")
    for line in lines:
        pg = doc.new_page(width=612, height=792)
        pg.insert_text((220, 396), line, fontsize=20)
        content = doc.new_page(width=612, height=792)
        content.insert_text((90, 200), "Contents of the exhibit.")
    return doc


@pytest.mark.parametrize("line", ["EXHIBIT ''1''", "EXHIBIT ' ' 2 ''",
                                  "EXHIBIT '' 3 '' - Lease"])
def test_a_lone_ocr_quoted_numeric_cover_is_strict(line):
    covers, label_pages = P._find_exhibit_cover_pages(_doc([line]))
    assert len(covers) == 1
    assert label_pages == {1}


def test_a_lone_loose_numeric_cover_is_still_refused():
    covers, label_pages = P._find_exhibit_cover_pages(
        _doc(["Exhibit 3 hereto is a true copy"]))
    assert covers == {} and label_pages == set()


# ── end to end: the reported set is found and bookmarked ───────────────────

def test_the_reported_exhibit_set_is_found_under_its_numbers():
    doc = _doc(["EXHIBIT ''1''", "EXHIBIT ' ' 2 ''", "EXHIBIT ''3''"])
    covers, label_pages = P._find_exhibit_cover_pages(doc)
    assert set(covers) == {"1", "2", "3"}
    assert covers["1"] == [1] and covers["2"] == [3] and covers["3"] == [5]
    assert label_pages == {1, 3, 5}


def test_the_bookmarks_read_the_exhibit_number_not_the_apostrophes():
    doc = _doc(["EXHIBIT ''1''", "EXHIBIT ' ' 2 ''"])
    covers, _ = P._find_exhibit_cover_pages(doc)
    tree = P._build_bookmark_tree(doc, [], covers, [])
    titles = [title for _lvl, title, _pg in tree]
    assert "Exhibit 1" in titles and "Exhibit 2" in titles
    assert not any("'" in t for t in titles)


# ── the footer-label matcher tolerates the same run ────────────────────────

@pytest.mark.parametrize("label,ident", [
    ("EXHIBIT ''A''", "A"),
    ("EXHIBIT ' ' 2 ''", "2"),
    ('EXHIBIT "5"', "5"),
    ("Exhibit “B”", "B"),
    ("EXHIBIT 5", "5"),
])
def test_a_quoted_footer_label_is_just_the_exhibit_id(label, ident):
    assert P._label_is_just_exhibit_id(label, ident)


@pytest.mark.parametrize("label,ident", [
    ("EXHIBIT A - Lease", "A"),      # a descriptor makes it more than the id
    ("EXHIBIT ''A''", "B"),          # wrong exhibit
    ("EXHIBIT ''12''", "1"),         # 12 is not 1
])
def test_a_label_that_is_more_than_the_id_or_another_id_is_refused(label, ident):
    assert not P._label_is_just_exhibit_id(label, ident)
