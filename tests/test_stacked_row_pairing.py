"""A gutter number's stacked rows are paired by BASELINE, not by index.

A dense letterhead or caption sets several physical rows under ONE gutter
number, so `_detect_line_anchors` buckets the number's segments into page
columns and emits a line per row of the stack. It paired them by INDEX — "line
k is the k-th row of every column" — which is right only while every column
under the number has the same number of rows.

A TITLE PAGE is exactly where that fails. The e-filing FILED stamp beside the
attorney block sets its own rows at its own lead, so under one gutter number
the attorney block had ONE row where the stamp had TWO, the k-th rows belonged
to different printed lines, and a delivered export read

    3  Los Angeles, California 90048   David W. Slayton, …Clerk of Court  M. Vermilye  Deputy
       By:

— the clerk's name lifted off the line it was signed on and the "By:" left
alone underneath it.

Two rows of the SAME column are never one line, which keeps a letterhead's own
consecutive rows apart; a row within `_cluster_rows`' attachment slack of one
is a raised FRAGMENT (a superscript) and joins it; and the tolerance narrows to
half the densest column's lead, so a caption whose columns are set at different
rhythms still pairs each line with the one beside it.

Run:  cd PDF-Linker && python3 -m pytest tests/test_stacked_row_pairing.py -v
"""
import pytest

import pdf_linker as P

fitz = pytest.importorskip("fitz")

STAMP = ["Electronically FILED by", "Superior Court of California,",
         "County of Los Angeles", "12/12/2022 11:04 AM",
         "David W. Slayton, Executive Officer/Clerk of Court",
         "By:      M. Vermilye      Deputy"]


def _title_page():
    """A pleading title page: 28 gutter numbers, an attorney block at the
    body lead, and a small-type e-filing stamp beside it at its own."""
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    for i in range(28):
        pg.insert_text((40, 70 + 24 * i), str(i + 1), fontsize=10)
    for i, line in enumerate(["Vanguard Eldridge # 101812",
                              "ELDRIDGE STONEHAVEN LLP",
                              "6311 Bilberry Boulevard",
                              "Los Angeles, California 90048",
                              "T: (803) 390-8778",
                              "Attorneys for Plaintiffs"]):
        pg.insert_text((72, 70 + 24 * i), line, fontsize=11)
    for k, line in enumerate(STAMP):
        pg.insert_text((350, 58 + 11 * k), line, fontsize=7)
    return pg


def _lines(page):
    return [((f"{num:>2}  " if num is not None else "    ")
             + P._visual_row_text(segs, P._rows_body_left(rows))).rstrip()
            for rows in [P._page_lined_rows(page)] for num, segs in rows]


# ── the stamp keeps its own lines ───────────────────────────────────────────

def test_a_stamp_line_is_never_lifted_onto_another(monkeypatch):
    for line in _lines(_title_page()):
        assert not ("Clerk of Court" in line and "Vermilye" in line), line


def test_the_by_line_keeps_the_name_that_was_signed_on_it():
    line = next(l for l in _lines(_title_page()) if "By:" in l)
    assert "Vermilye" in line and "Deputy" in line


def test_the_attorney_block_keeps_its_own_line_and_its_number():
    lines = _lines(_title_page())
    assert any(l.startswith(" 4  Los Angeles, California 90048") for l in lines)


def test_the_number_goes_on_its_leftmost_columns_first_line():
    """A gutter number numbers a line of the pleading's BODY, and the body is
    the leftmost column: the stamp beside it can start above that line."""
    lines = _lines(_title_page())
    numbered = [l for l in lines if l[:2].strip().isdigit()]
    for i, want in enumerate(["Vanguard Eldridge # 101812",
                              "ELDRIDGE STONEHAVEN LLP",
                              "6311 Bilberry Boulevard"]):
        assert want in numbered[i], numbered[i]


# ── and a column's own rows never collapse ──────────────────────────────────

def test_two_rows_of_one_column_are_two_lines():
    """A tightly-set letterhead runs at ~half the numbered-body lead, so two of
    its rows fall under one gutter number and must stay apart."""
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    for i in range(28):
        pg.insert_text((40, 70 + 24 * i), str(i + 1), fontsize=10)
    pg.insert_text((72, 62), "Paul Green, Esq. (SBN 237707)", fontsize=11)
    pg.insert_text((72, 74), "LAW OFFICE OF PAUL GREEN", fontsize=11)
    bodies = [b for _n, b in
              [(a["line_num"], a["body_text"]) for a in P._detect_line_anchors(pg)]]
    assert not any("Esq." in b and "LAW OFFICE" in b for b in bodies)


def test_a_caption_whose_columns_run_at_different_leads_still_pairs():
    """The party column and the case-number column are set at their own
    rhythms; a bound of half a lead read the page as having twice its lines."""
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    for i in range(28):
        pg.insert_text((40, 70 + 24 * i), str(i + 1), fontsize=10)
    pg.insert_text((72, 300), "deceased; and GABLE RAMSEY;", fontsize=11)
    pg.insert_text((330, 315), "THIRD AMENDED COMPLAINT", fontsize=11)
    pg.insert_text((72, 324), "              Plaintiffs,", fontsize=11)
    pg.insert_text((330, 330), "FOR DAMAGES", fontsize=11)
    pairs = [a["body_text"] for a in P._detect_line_anchors(pg)]
    assert any("GABLE RAMSEY" in b and "THIRD AMENDED" in b for b in pairs), pairs
    assert any("Plaintiffs," in b and "FOR DAMAGES" in b for b in pairs), pairs


def test_the_pairing_is_asked_of_the_stacks_alone():
    """`_pair_stacked_rows` decides it, so the two callers cannot drift."""
    stacks = {0: {100.0: [72.0, "left"]},
              1: {88.0: [350.0, "stamp above"], 100.0: [350.0, "By:"]},
              2: {100.0: [430.0, "M. Vermilye"]}}
    lines = P._pair_stacked_rows(stacks, 12.0)
    assert [sorted(t for _x, _y, t in ln) for ln in lines] == [
        ["stamp above"], ["By:", "M. Vermilye", "left"]]
