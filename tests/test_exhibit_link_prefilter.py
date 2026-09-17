"""The exhibit-reference linker screens each page ONCE before it searches.

`_link_exhibit_references` used to run `page.search_for` for every exhibit
identifier under every prefix in every quote spelling on EVERY page — some
900 full-page glyph searches a page, 1.8 million on a 2,043-page evidence
compendium. A delivered folder spent 83 minutes there on that file and 93
on a 254-page declaration, in every run that reached them, and two runs
were killed while sitting in it because a stall that long reads as a hang.

The screen is one `get_text` per page, case-folded with its whitespace
removed, and a phrase is searched only where that string contains the
phrase reduced the same way. It must be EXACT — a page the screen skips is
a link never made — so this test runs the linker with the screen on and
off over one document carrying every spelling the loop can meet (casings,
quote forms, OCR digit spellings, a wrap, a glued word, a fragment of a
longer identifier) and pins that the two produce the SAME links, and that
the screened run spent far fewer searches getting them.

Run:  cd PDF-Linker && python3 -m pytest tests/test_exhibit_link_prefilter.py -v
"""
import logging

import pytest

fitz = pytest.importorskip("fitz")

import pdf_linker as P

LOG = logging.getLogger("test_exhibit_link_prefilter")


BODY_LINES = [
    # every casing of every prefix, some quoted, some not
    "A true copy is attached as Exhibit 1 and as EXHIBIT 2 hereto.",
    'See Ex. 3, EX. 4, Exh. "5", EXH. 6; the rest follows.',
    # the fragment rule: "Exhibit 1" must not latch onto "Exhibit 12"
    "Compare Exhibit 12 with Exhibit 1 and exhibit 2 (lower case is prose).",
    # OCR spellings of a numeric identifier, admitted in an all-numeric set
    "The scan reads it as Exhibit I and Exhibit l and Exhibit 1O sometimes.",
    # a no-break space and a run of spaces between prefix and number
    "Attached as Exhibit 7 and as Exhibit   8 with wide spacing.",
    # a glued word is not a reference, a hyphenated wrap is not either
    "Exhibit9 glued stays unlinked, as does Exhi-",
    "bit 10 wrapped over a hyphen.",
    # the OCR apostrophe-pair quote
    "The lease is Exhibit ''11'' in the set.",
    # a reference that wraps between the prefix and the number
    "and the guaranty is attached hereto as Exhibit",
    "3 which the Court may read.",
]


def _doc(n_body_pages=6, idents=range(1, 13)):
    """Twelve numbered exhibit covers behind a run of body pages that carry
    every spelling the linker meets. Each body page carries the whole
    battery, and a few pages carry nothing at all."""
    doc = fitz.open()
    for i in range(n_body_pages):
        pg = doc.new_page(width=612, height=792)
        if i % 3 == 2:
            pg.insert_text((90, 200), "Nothing of note on this page.")
            continue
        y = 120
        for line in BODY_LINES:
            pg.insert_text((72, y), line, fontsize=12)
            y += 18
    for ident in idents:
        cover = doc.new_page(width=612, height=792)
        cover.insert_text((250, 396), f"EXHIBIT {ident}", fontsize=20)
        content = doc.new_page(width=612, height=792)
        content.insert_text((90, 200), "Contents of the exhibit.")
    return doc


def _links(doc):
    out = []
    for i, page in enumerate(doc):
        for el in page.get_links():
            r = el.get("from")
            out.append((i, el.get("page"),
                        tuple(round(v, 2) for v in (r.x0, r.y0, r.x1, r.y1))))
    return sorted(out)


def _run(monkeypatch, screened):
    monkeypatch.setattr(P, "_EXHIBIT_LINK_PREFILTER", screened)
    calls = {"n": 0}
    orig = fitz.Page.search_for

    def counted(self, *a, **kw):
        calls["n"] += 1
        return orig(self, *a, **kw)
    monkeypatch.setattr(fitz.Page, "search_for", counted)
    doc = _doc()
    linked, covers = P._link_exhibit_references(doc, LOG)
    return linked, covers, _links(doc), calls["n"]


def test_the_screen_changes_no_link_and_spares_most_searches(monkeypatch):
    linked_off, covers_off, links_off, n_off = _run(monkeypatch, False)
    linked_on, covers_on, links_on, n_on = _run(monkeypatch, True)
    assert covers_on == covers_off and len(covers_on) == 12
    # The battery really exercises the loop: references were linked, the
    # glued and hyphenated spellings were not, the fragment rule held.
    assert linked_off > 0
    assert links_on == links_off
    assert linked_on == linked_off
    # Four body pages carry the battery, two carry nothing, and the twelve
    # exhibits' own pages are label pages. The screen skips the blank
    # pages outright and, on the others, every phrase whose text is not
    # on the page — the unscreened loop paid for all of them.
    assert n_on < n_off / 5, (n_on, n_off)


def test_what_the_battery_links_and_refuses(monkeypatch):
    """The reference set the differential test compares is not empty of
    the cases that matter: pin a few of them by name so a regression in
    the loop itself (not the screen) is caught here too."""
    monkeypatch.setattr(P, "_EXHIBIT_LINK_PREFILTER", True)
    doc = _doc()
    P._link_exhibit_references(doc, LOG)
    page = doc[0]
    linked_text = sorted(
        page.get_text("text", clip=el["from"]).strip()
        for el in page.get_links())
    # Every casing, the quoted forms and the OCR digit spellings link (the
    # no-break-space reference extracts with a plain space)…
    for want in ("Exhibit 1", "EXHIBIT 2", "Ex. 3", "EX. 4", 'Exh. "5"',
                 "EXH. 6", "Exhibit 12", "Exhibit I", "Exhibit l",
                 "Exhibit 1O", "Exhibit 7", "Exhibit ''11''"):
        assert want in linked_text, (want, linked_text)
    # …the glued word, the hyphenated wrap and lower-case prose do not.
    joined = " | ".join(linked_text)
    assert "Exhibit9" not in joined
    assert "bit 10" not in joined
    assert "exhibit 2" not in joined


def test_screen_key_is_the_whitespace_free_fold():
    assert P._exhibit_screen_key("Exhibit  7") == "exhibit7"
    assert P._exhibit_screen_key('EXH. "5"') == 'exh."5"'
