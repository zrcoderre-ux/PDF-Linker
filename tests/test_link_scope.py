"""
Citation linking must not search all N pages for every citation — that
O(citations x pages) scan made a 448-page OCR'd exhibit crawl for an hour. A
citation whose exact text occurs once in the document is provably on ONE page
and is linked there directly; repeated text keeps the full scan so every
occurrence is still linked.

Run:  cd PDF-Linker && python3 -m pytest tests/test_link_scope.py -v
"""
import logging

import fitz
import pytest

import pdf_linker as P

log = logging.getLogger("test")
_CITE = "See Santana v. FCA US, LLC, 56 Cal.App.5th 334, 345 (2020)."


def _pdf(folder, n, cite_pages):
    d = fitz.open()
    for i in range(n):
        pg = d.new_page()
        pg.insert_text((72, 100), _CITE if i in cite_pages else f"Filler page {i}.")
    p = folder / "brief.pdf"
    d.save(str(p))
    d.close()
    return p


def _linked_pages(p):
    d = fitz.open(str(p))
    pages = sorted({pg.number for pg in d for ln in pg.get_links()})
    d.close()
    return pages


def test_unique_citation_links_on_its_own_page_only(tmp_path):
    p = _pdf(tmp_path, 50, {40})
    P.process_pdf(p, log, provider="westlaw", extract_text=False)
    assert _linked_pages(p) == [40]


def test_repeated_citation_still_links_on_every_page(tmp_path):
    # The fast path only applies to once-only text; a citation on two pages must
    # still be linked on both (the full-scan fallback).
    p = _pdf(tmp_path, 30, {5, 20})
    P.process_pdf(p, log, provider="westlaw", extract_text=False)
    assert _linked_pages(p) == [5, 20]


def test_citation_on_first_and_last_page(tmp_path):
    # Boundary: span-to-page mapping must be right at the ends of the document.
    p = _pdf(tmp_path, 12, {0, 11})
    P.process_pdf(p, log, provider="westlaw", extract_text=False)
    assert _linked_pages(p) == [0, 11]
