"""A petition with one webpage exhibit gets TWO clean bookmarks, not four
junk ones.

A delivered petition-to-compel-arbitration produced Document bookmarks of

    ____________________ PETITION TO COMPEL ARBITRATION AND TO STAY ...
    [url] grant us a worldwide, non-exclusive, perpetual, royalty-free ...
    and our policies with respect to changing or cancelling a Subscription...

— while the one clean 'EXHIBIT "A"' slip sheet earned no bookmark at all,
and the petition's own I./II./III. headings earned no section bookmarks.
Three distinct causes:

  * The footer detector reads the bottom band of every page. A printed
    WEBPAGE (the Terms-of-Service exhibit) flows body prose into that band,
    and every page's sentence fragment is distinct, so each page minted its
    own "document" labelled with the fragment plus the browser's URL/page
    footer. The petition's own label kept the title block's horizontal rule
    (extracted as underscores).
  * _link_exhibit_references returned an EMPTY cover map below 2 covers —
    right for body-reference linking, but it starved the bookmark tree.
  * The section scan read rows WITHOUT dropping gutter line-numbers (the
    merged row "5  I. INTRODUCTION" fails the label regex and stretches the
    bbox so the centering test fails too), and the commonest court heading
    style — body-size, not bold, centered/UNDERLINED — had no qualifying
    visual cue because underline was never read from the page's line art.

Run:  cd PDF-Linker && python3 -m pytest tests/test_document_bookmarks.py -v
"""
import logging

import pytest

import pdf_linker as P

fitz = pytest.importorskip("fitz")

LOG = logging.getLogger("test_document_bookmarks")

PETITION_FOOTER = ("PETITION TO COMPEL ARBITRATION AND TO STAY "
                   "JUDICIAL PROCEEDINGS")
WEB_PROSE = [
    "grant us a worldwide, non-exclusive, perpetual, royalty-free, fully "
    "paid, sublicensable and transferable license to use, edit, modify, "
    "truncate, aggregate, reproduce, distribute, prepare",
    "and our policies with respect to changing or cancelling a "
    "Subscription. Before submitting your order for a Subscription, you "
    "must create your assortment of products and select the quantity",
    "you may not use the Services for any unlawful purpose or in any "
    "manner that could damage, disable, overburden or impair the site",
]


# ── footer furniture: rules, URLs, browser page counters ────────────────────

def test_the_underscore_rule_is_not_part_of_the_title():
    raw = "_" * 80 + " " + PETITION_FOOTER
    assert P._clean_footer_label(raw) == PETITION_FOOTER
    # …and the key agrees, so a page with the rule and a page without it
    # group as one document.
    assert (P._normalize_footer_for_key(raw)
            == P._normalize_footer_for_key(PETITION_FOOTER))


def test_a_browser_print_footer_is_stripped_from_the_label():
    raw = "TERMS OF SERVICE https://www.acme.com/store/terms 3/17"
    assert P._clean_footer_label(raw) == "TERMS OF SERVICE"


def test_a_date_survives_the_page_fraction_strip():
    assert "8/20/2026" in P._clean_footer_label("FILED 8/20/2026 NUNC PRO TUNC")


# ── a body-prose band is not a footer ───────────────────────────────────────

@pytest.mark.parametrize("band", WEB_PROSE + [
    "https://www.acme.com/store/help/terms-of-service",  # URL-only band
])
def test_webpage_body_text_in_the_band_reads_as_prose(band):
    assert P._footer_reads_as_prose(band)


@pytest.mark.parametrize("band", [
    PETITION_FOOTER,
    "Declaration of John Smith in Support of Petitioner's Motion",
    "MEMORANDUM OF POINTS AND AUTHORITIES",
    "Petition to Compel Arbitration - Case No. 24STCV12345",
    "",
])
def test_a_real_running_footer_never_reads_as_prose(band):
    assert not P._footer_reads_as_prose(band)


# ── the fixture: petition + one printed-webpage exhibit ─────────────────────

def _petition_doc():
    doc = fitz.open()
    for i in range(3):
        pg = doc.new_page(width=612, height=792)
        for n in range(1, 8):
            pg.insert_text((50, 90 + n * 24), str(n), fontsize=10)
        pg.insert_text((110, 114),
                       "The parties entered into a written agreement.")
        pg.insert_text((110, 770), "_" * 60, fontsize=8)
        pg.insert_text((130, 780), PETITION_FOOTER, fontsize=8)
    cover = doc.new_page(width=612, height=792)
    cover.insert_text((250, 396), 'EXHIBIT "A"', fontsize=20)
    for prose in WEB_PROSE:
        pg = doc.new_page(width=612, height=792)
        pg.insert_text((72, 200), "TERMS OF SERVICE CONTENT PAGE")
        # The printed webpage's last lines land inside the footer band…
        pg.insert_text((72, 758), prose[:90], fontsize=9)
        # …with the browser's own print footer under them.
        pg.insert_text((72, 782), "https://www.acme.com/store/terms 3/17",
                       fontsize=8)
    return doc


def test_the_webpage_pages_mint_no_documents():
    doc = _petition_doc()
    entries = P._detect_document_footers(doc, LOG, have_exhibits=True)
    assert entries == [(PETITION_FOOTER, 0)]


def test_without_exhibits_a_single_footer_still_yields_no_branch():
    doc = fitz.open()
    for i in range(4):
        pg = doc.new_page(width=612, height=792)
        pg.insert_text((130, 780), PETITION_FOOTER, fontsize=8)
    assert P._detect_document_footers(doc, LOG, have_exhibits=False) == []


# ── a single clean exhibit cover reaches the bookmark tree ──────────────────

def test_a_single_strict_cover_is_kept():
    covers, label_pages = P._find_exhibit_cover_pages(_petition_doc())
    assert covers == {"A": [3]}
    assert label_pages == {3}


def test_link_pass_returns_the_single_cover_without_linking():
    linked, cover_map = P._link_exhibit_references(_petition_doc(), LOG)
    assert linked == 0
    assert cover_map == {"A": [3]}


def test_a_lone_loose_numeric_match_is_not_an_exhibit():
    # A wrapped body sentence that happens to start the line matches the
    # numeric branch's free descriptor; alone, it must not become a
    # phantom Exhibits branch that annexes the rest of the document.
    doc = fitz.open()
    for i in range(4):
        pg = doc.new_page(width=612, height=792)
        pg.insert_text((90, 300), "The agreement is attached hereto.")
    doc[2].insert_text((90, 340), "Exhibit 3 hereto is a true copy of it")
    covers, _ = P._find_exhibit_cover_pages(doc)
    assert covers == {}


def test_two_covers_still_corroborate_each_other():
    doc = fitz.open()
    for label in ("EXHIBIT 1 Purchase Agreement", "EXHIBIT 2 Warranty"):
        doc.new_page(width=612, height=792)
        pg = doc.new_page(width=612, height=792)
        pg.insert_text((250, 396), label, fontsize=20)
    covers, _ = P._find_exhibit_cover_pages(doc)
    assert set(covers) == {"1", "2"}


# ── the tree the user asked for: two clean bookmarks ────────────────────────

def test_the_tree_is_the_petition_and_exhibit_a_and_nothing_else():
    doc = _petition_doc()
    covers, _ = P._find_exhibit_cover_pages(doc)
    entries = P._detect_document_footers(doc, LOG,
                                         have_exhibits=bool(covers))
    tree = P._build_bookmark_tree(doc, [], covers, [],
                                  document_entries=entries)
    titles = [t for _lvl, t, _pg in tree]
    assert PETITION_FOOTER in titles
    assert "Exhibit A" in titles
    for t in titles:
        assert "grant us" not in t and "http" not in t and "__" not in t


# ── section headings: gutter numbers, centering, underlines ─────────────────

def _petition_with_headings():
    doc = fitz.open()
    for _ in range(2):   # caption pages the scan skips
        doc.new_page(width=612, height=792)
    pg = doc.new_page(width=612, height=792)
    # Pleading gutter numbers sharing baselines with the content.
    y = 114
    body = ("Petitioner respectfully submits this memorandum in support "
            "of its petition.")
    rows = [("I. INTRODUCTION", True), (body, False),
            ("II. PARTIES", True), (body, False),
            ("III. JURISDICTION AND VENUE", True), (body, False)]
    n = 1
    for text, heading in rows:
        pg.insert_text((50, y), str(n), fontsize=11)
        if heading:
            width = fitz.get_text_length(text, fontsize=11)
            x0 = (612 - width) / 2
            pg.insert_text((x0, y), text, fontsize=11)   # body size, not bold
            pg.draw_line((x0, y + 2), (x0 + width, y + 2))  # underlined
        else:
            pg.insert_text((110, y), text, fontsize=11)
        y += 24
        n += 1
    doc.new_page(width=612, height=792)
    return doc


def test_centered_underlined_body_size_headings_are_detected():
    entries = P._detect_section_headings(_petition_with_headings(), LOG)
    labels = [lbl for lbl, _pg in entries]
    assert labels == ["I. INTRODUCTION", "II. PARTIES",
                      "III. JURISDICTION AND VENUE"]


def test_an_underlined_left_aligned_subsection_is_detected():
    doc = fitz.open()
    for _ in range(2):
        doc.new_page(width=612, height=792)
    pg = doc.new_page(width=612, height=792)
    text = "A. The Agreement Delegates Arbitrability"
    pg.insert_text((126, 200), text, fontsize=11)
    width = fitz.get_text_length(text, fontsize=11)
    pg.draw_line((126, 202), (126 + width, 202))
    pg.insert_text((110, 240),
                   "The parties clearly and unmistakably delegated it.",
                   fontsize=11)
    entries = P._detect_section_headings(doc, LOG)
    assert [lbl for lbl, _pg in entries] == [text]


def test_a_bare_centered_label_is_not_a_heading():
    # The caption's "V." between the parties is a centered outline label
    # with no text; centering alone must not make it a bookmark.
    assert not P._is_heading_row("V.", 11.0, False, True, 11.0)
    assert P._is_heading_row("I. INTRODUCTION", 11.0, False, True, 11.0)


def test_plain_body_text_is_still_no_heading():
    assert not P._is_heading_row(
        "Petitioner respectfully submits this memorandum.",
        11.0, False, False, 11.0, is_underlined=False)
