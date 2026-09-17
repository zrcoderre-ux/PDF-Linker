"""A REPEATED citation is searched only on the pages that can carry it.

A citation occurring once in the document was already searched on its own
page. One occurring twice was searched on EVERY page with a glyph search
apiece, and a 2,043-page evidence compendium with 415 citations spent 21
minutes there linking nothing. Each page's text is reduced once the way the
exhibit linker reduces it (`_exhibit_screen_key`), and a repeated citation
is searched where the reduced page carries the reduced needle, or one of
the safe fragments the wrapped-citation fallback would use. The screen is
switched off through `_PN_CITE_PAGE_SCREEN` to obtain the reference.

Run:  cd PDF-Linker && python3 -m pytest tests/test_citation_link_page_screen.py -v
"""
import logging
import shutil

import pytest

fitz = pytest.importorskip("fitz")

import pdf_linker as P

LOG = logging.getLogger("test_citation_link_page_screen")

CITE = "Kremerman v. White (2021) 71 Cal.App.5th 358"
CITE2 = "Sanchez v. Valencia Holding Co. (2015) 61 Cal.4th 899"


def _doc(pages=24):
    doc = fitz.open()
    for i in range(pages):
        pg = doc.new_page(width=612, height=792)
        y = 100
        lines = ["The parties agreed that the work would proceed on schedule."] * 4
        if i in (3, 17):
            lines[1] = f"See {CITE}, which controls."       # repeated: twice
        if i == 9:
            lines[2] = f"See also {CITE2}."                  # once
        if i == 20:
            # the repeated cite again, wrapped across two lines
            lines[1] = "Compare Kremerman v. White (2021) 71"
            lines[2] = "Cal.App.5th 358 at 373."
        for ln in lines:
            pg.insert_text((72, y), ln, fontsize=11)
            y += 18
    return doc


def _links(doc):
    return sorted((i, el.get("uri"), tuple(round(v, 1) for v in el["from"]))
                  for i, pg in enumerate(doc) for el in pg.get_links())


def _run(tmp_path, monkeypatch, screened):
    monkeypatch.setattr(P, "_PN_CITE_PAGE_SCREEN", screened)
    calls = {"n": 0}
    orig = fitz.Page.search_for

    def counted(self, *a, **kw):
        calls["n"] += 1
        return orig(self, *a, **kw)
    monkeypatch.setattr(fitz.Page, "search_for", counted)
    src = tmp_path / f"brief_{int(screened)}.pdf"
    _doc().save(str(src))
    ok = P.process_pdf(src, LOG, provider="lexis", extract_text=False)
    assert ok
    with fitz.open(str(src)) as out:
        return _links(out), calls["n"]


def test_the_screen_links_the_same_and_searches_far_fewer_pages(tmp_path,
                                                                monkeypatch):
    links_off, n_off = _run(tmp_path, monkeypatch, False)
    links_on, n_on = _run(tmp_path, monkeypatch, True)
    assert links_on == links_off
    # Both occurrences of the repeated cite and the single one are linked.
    pages = {i for i, _u, _r in links_on}
    assert {3, 17, 9} <= pages, pages
    assert n_on < n_off / 3, (n_on, n_off)


def test_a_page_the_wrapped_fragment_fallback_would_use_is_kept():
    """The screen must admit a page on any SAFE fragment of a wrapped
    citation, since `_safe_search_for_citation` may link from one."""
    needle = "Kremerman v. White (2021) 71\nCal.App.5th 358"
    keys = [P._exhibit_screen_key(needle)] + [
        P._exhibit_screen_key(f.strip()) for f in needle.splitlines()
        if f.strip() and P._is_safe_fragment(f.strip())]
    # "Cal.App.5th 358" alone is not a safe fragment (reporter furniture), so
    # a page carrying only that is rightly refused; the plaintiff's half is.
    assert not any(k in P._exhibit_screen_key("blah Cal.App.5th 358 blah")
                   for k in keys)
    page = P._exhibit_screen_key("see Kremerman v. White (2021) 71 blah")
    assert any(k in page for k in keys)
