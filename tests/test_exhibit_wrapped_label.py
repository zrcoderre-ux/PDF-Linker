"""A slip sheet may put its quotation marks around the WHOLE label.

"EXHIBIT K" is as common a cover as EXHIBIT "K" — the typist quoted the
label they were naming, not the identifier inside it — and the cover
regex's ^EXHIBIT anchor refused every one of them: no cover page, no
bookmark, no body links, while the exhibits spelled the other way in the
same set earned all three. The quote RUN is now optional in front of the
prefix word as well as after it.

Run:  cd PDF-Linker && python3 -m pytest tests/test_exhibit_wrapped_label.py -v
"""
import pytest

import pdf_linker as P


# ── the wrap names its exhibit, in every spelling of the quote ─────────────

@pytest.mark.parametrize("line,ident", [
    ('"EXHIBIT K"', "K"),                 # the reported spelling
    ("“Exhibit K”", "K"),       # curly, title case
    ("''EXHIBIT K''", "K"),               # OCR's apostrophe pair
    ("' ' EXHIBIT K ' '", "K"),           # ...with its spaces
    ('"EXHIBIT AA"', "AA"),               # two-capital id
    ('"Exhibit 5"', "5"),                 # a numbered set wraps the same way
    ('"EXHIBIT 12"', "12"),
    ('"Ex. K"', "K"),                     # short prefix
    ("“EXHIBIT K — Lease”", "K"),   # closer after the descriptor
    ('"EXHIBIT K - Lease"', "K"),
    ('"EXHIBIT 3 - Lease"', "3"),
    ('"EXHIBIT "K""', "K"),               # both wraps at once
])
def test_a_wrapped_label_names_its_exhibit(line, ident):
    m = P._exhibit_cover_match(line)
    assert m is not None, line
    assert P._exhibit_match_raw(m) == ident


# ── and admits nothing the regex refused for cause ─────────────────────────

@pytest.mark.parametrize("line", [
    '"EXHIBIT Apple"',                    # never matched, still not
    '"Exhibit a"',                        # a lower-case id is not an exhibit
    '"EXHIBIT A, the contract was"',      # a comma is not a separator
    '"EXHIBIT ABC"',                      # three capitals is not an id
    '"EXHIBIT 1234"',                     # four digits is not a number
    '"The contract, EXHIBIT A, was"',     # the prefix must open the line
    '""K"',                               # a quote run with no prefix word
    '"EXHIBIT"',                          # a quote run with no identifier
])
def test_the_wrap_admits_nothing_refused_for_cause(line):
    assert P._exhibit_cover_match(line) is None


# ── the lone-cover strictness gate still decides on the label alone ────────
# _EXHIBIT_QUOTE_LEAD_RE strips the wrap's closing half off the numeric
# branch's remainder, so a wrapped bare label reads STRICT and earns its
# bookmark alone, while a wrapped body sentence stays loose and does not.

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


@pytest.mark.parametrize("line", ['"EXHIBIT 3"', '"EXHIBIT 3 - Lease"',
                                  "''EXHIBIT 3''"])
def test_a_lone_wrapped_numeric_cover_is_strict(line):
    covers, label_pages = P._find_exhibit_cover_pages(_doc([line]))
    assert len(covers) == 1
    assert label_pages == {1}


def test_a_wrapped_body_sentence_is_still_refused():
    covers, label_pages = P._find_exhibit_cover_pages(
        _doc(['"Exhibit 3 hereto is a true copy"']))
    assert covers == {} and label_pages == set()


# ── end to end: the set is found and bookmarked under its letters ─────────

def test_a_wrapped_set_is_found_and_bookmarked():
    # Straight quotes in the fixture: the base-14 font a synthesized page
    # is written with has no curly pair, and encodes one as a middle dot.
    # The curly spelling is pinned against the regex above.
    doc = _doc(['"EXHIBIT J"', '"EXHIBIT K"', "''EXHIBIT L''"])
    covers, label_pages = P._find_exhibit_cover_pages(doc)
    assert set(covers) == {"J", "K", "L"}
    assert covers["J"] == [1] and covers["K"] == [3] and covers["L"] == [5]
    assert label_pages == {1, 3, 5}
    titles = [t for _lvl, t, _pg in P._build_bookmark_tree(doc, [], covers, [])]
    assert "Exhibit K" in titles
    assert not any('"' in t or "'" in t for t in titles)


def test_a_wrapped_and_a_bare_label_are_one_exhibit():
    doc = _doc(['"EXHIBIT K"', "EXHIBIT K"])
    covers, _ = P._find_exhibit_cover_pages(doc)
    assert set(covers) == {"K"}
    assert covers["K"] == [1, 3]


# ── the footer-label matcher takes the same wrap ───────────────────────────

@pytest.mark.parametrize("label,ident", [
    ('"EXHIBIT K"', "K"),
    ("“Exhibit 5”", "5"),
    ("''EXHIBIT K''", "K"),
])
def test_a_wrapped_footer_label_is_just_the_exhibit_id(label, ident):
    assert P._label_is_just_exhibit_id(label, ident)


@pytest.mark.parametrize("label,ident", [
    ('"EXHIBIT K"', "B"),            # wrong exhibit
    ('"EXHIBIT K - Lease"', "K"),    # a descriptor makes it more than the id
])
def test_a_wrapped_label_that_is_more_or_another_id_is_refused(label, ident):
    assert not P._label_is_just_exhibit_id(label, ident)
