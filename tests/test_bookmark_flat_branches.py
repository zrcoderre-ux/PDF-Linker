"""A branch header that separates nothing is not written.

Two shapes, both of them one click of pure nesting over a list the reader
was already looking at:

  * "Documents" over a SINGLE sub-document. The file IS that document, so
    the header names nothing the entry under it does not. Two or more
    still earn it — that header is what says the file is a combined
    filing.
  * "Exhibits" where the exhibits are the tree's ONLY category. There is
    nothing to separate them from, so each exhibit becomes a top-level
    bookmark. With a Contents, a Causes of Action or a Documents entry
    beside them the header does real work and stays.

In both cases the entries' own children rise a level with them, so the
tree keeps its shape below the header that went.

Run:  cd PDF-Linker && python3 -m pytest tests/test_bookmark_flat_branches.py -v
"""
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pdf_linker as P  # noqa: E402

fitz = pytest.importorskip("fitz")
LOG = logging.getLogger("test")


def _doc(n_pages):
    doc = fitz.open()
    for _ in range(n_pages):
        doc.new_page(width=612, height=792)
    return doc


def _levels(tree):
    return {title: lvl for lvl, title, _pg in tree}


# ── Documents ───────────────────────────────────────────────────────────────

def test_a_single_document_is_written_without_the_documents_header():
    doc = _doc(6)
    tree = P._build_bookmark_tree(
        doc, [], {}, [(0, 1), (2, 4)],
        document_entries=[("DECLARATION OF SMITH", 0)])
    titles = [t for _lvl, t, _pg in tree]
    assert "Documents" not in titles
    lv = _levels(tree)
    assert lv["DECLARATION OF SMITH"] == 1
    # Its paragraphs rise with it.
    assert lv["¶ 1"] == 2 and lv["¶ 4"] == 2


def test_two_documents_still_earn_the_header():
    doc = _doc(6)
    tree = P._build_bookmark_tree(
        doc, [], {}, [(0, 1), (3, 1)],
        document_entries=[("NOTICE OF MOTION", 0),
                          ("DECLARATION OF SMITH", 3)])
    lv = _levels(tree)
    assert lv["Documents"] == 1
    assert lv["NOTICE OF MOTION"] == 2 and lv["DECLARATION OF SMITH"] == 2
    assert lv["¶ 1"] == 3


def test_a_single_documents_sections_rise_with_it():
    doc = _doc(8)
    tree = P._build_bookmark_tree(
        doc, [], {}, [(4, 7)],
        document_entries=[("MEMORANDUM OF POINTS AND AUTHORITIES", 0)],
        section_entries=[("I. INTRODUCTION", 2), ("II. ARGUMENT", 4)])
    lv = _levels(tree)
    assert "Documents" not in lv
    assert lv["MEMORANDUM OF POINTS AND AUTHORITIES"] == 1
    assert lv["I. INTRODUCTION"] == 2 and lv["II. ARGUMENT"] == 2
    assert lv["¶ 7"] == 3


# ── Exhibits ────────────────────────────────────────────────────────────────

def test_exhibits_alone_are_the_top_level():
    doc = _doc(6)
    tree = P._build_bookmark_tree(doc, [], {"A": [0], "B": [3]}, [])
    titles = [t for _lvl, t, _pg in tree]
    assert "Exhibits" not in titles
    lv = _levels(tree)
    assert lv["Exhibit A"] == 1 and lv["Exhibit B"] == 1


def test_an_exhibits_paragraphs_rise_with_it():
    doc = _doc(6)
    tree = P._build_bookmark_tree(doc, [], {"A": [0]}, [(1, 2)])
    lv = _levels(tree)
    assert lv["Exhibit A"] == 1 and lv["¶ 2"] == 2


def test_a_contents_branch_keeps_the_exhibits_header():
    doc = _doc(6)
    tree = P._build_bookmark_tree(
        doc, [("I. INTRODUCTION", 1)], {"A": [3]}, [])
    lv = _levels(tree)
    assert lv["Contents"] == 1 and lv["Exhibits"] == 1
    assert lv["Exhibit A"] == 2


def test_a_lone_document_beside_exhibits_still_keeps_the_exhibits_header():
    # The Documents header goes (one document); the Exhibits header stays,
    # because the document is still something to separate the exhibits
    # from.
    doc = _doc(8)
    tree = P._build_bookmark_tree(
        doc, [], {"A": [4]}, [],
        document_entries=[("DECLARATION OF SMITH", 0)])
    lv = _levels(tree)
    assert "Documents" not in lv
    assert lv["DECLARATION OF SMITH"] == 1
    assert lv["Exhibits"] == 1 and lv["Exhibit A"] == 2


def test_a_nested_subdocument_rises_with_its_flattened_exhibit():
    doc = _doc(8)
    tree = P._build_bookmark_tree(
        doc, [], {"A": [0]}, [(3, 1)],
        document_entries=[("DECLARATION OF JONES", 2)])
    lv = _levels(tree)
    assert "Exhibits" not in lv and "Documents" not in lv
    assert lv["Exhibit A"] == 1
    # The sub-document sits inside Exhibit A's page range, so it is the
    # exhibit's child — one level under it, and its paragraph under that.
    assert lv["DECLARATION OF JONES"] == 2
    assert lv["¶ 1"] == 3


# ── Contents and Sections never describe the same headings twice ────────────
# A Contents branch is the document's OWN table of contents; the section scan
# is a detector reading those same headings off the page. Written together the
# reader gets one list of headings and a second, overlapping one beside it.

def test_a_contents_branch_suppresses_the_detected_sections():
    doc = _doc(8)
    tree = P._build_bookmark_tree(
        doc, [("I. INTRODUCTION", 2), ("II. ARGUMENT", 4)], {}, [],
        section_entries=[("I. INTRODUCTION", 2), ("II. ARGUMENT", 4),
                         ("SUMMARY OF ARGUMENT", 1)])
    titles = [t for _lvl, t, _pg in tree]
    assert "Sections" not in titles
    assert "SUMMARY OF ARGUMENT" not in titles
    # The Contents branch itself is untouched.
    lv = _levels(tree)
    assert lv["Contents"] == 1
    assert lv["I. INTRODUCTION"] == 2 and lv["II. ARGUMENT"] == 2


def test_with_no_contents_the_sections_are_the_branch():
    doc = _doc(8)
    tree = P._build_bookmark_tree(
        doc, [], {}, [(5, 3)],
        section_entries=[("I. INTRODUCTION", 2), ("II. ARGUMENT", 4)])
    lv = _levels(tree)
    assert lv["Sections"] == 1
    assert lv["I. INTRODUCTION"] == 2 and lv["II. ARGUMENT"] == 2
    assert lv["¶ 3"] == 3


def test_a_contents_branch_suppresses_the_sections_under_a_document():
    # Sections nest under a Document when one exists — and are dropped there
    # too, since the duplication is with Contents and not with the parent.
    doc = _doc(8)
    tree = P._build_bookmark_tree(
        doc, [("I. INTRODUCTION", 2)], {}, [(3, 4)],
        document_entries=[("MEMORANDUM OF POINTS AND AUTHORITIES", 0)],
        section_entries=[("I. INTRODUCTION", 2)])
    titles = [t for _lvl, t, _pg in tree]
    assert titles.count("I. INTRODUCTION") == 1      # the Contents child
    lv = _levels(tree)
    assert lv["Contents"] == 1
    assert lv["MEMORANDUM OF POINTS AND AUTHORITIES"] == 1
    # The paragraph that would have nested under the section rises to the
    # document it belongs to.
    assert lv["¶ 4"] == 2


def test_the_scan_is_not_even_run_for_a_toc_bearing_brief():
    # The builder is what decides; skipping the walk only saves the cost and
    # a log line claiming headings that reach no bookmark. Pinned on the
    # SOURCE, because the cost is the whole point of the call-site gate.
    import inspect
    src = inspect.getsource(P.process_pdf)
    assert "if not skip_links and not toc_entries:" in src
