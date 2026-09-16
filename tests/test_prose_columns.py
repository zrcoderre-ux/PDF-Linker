"""Two-column PROSE reads COLUMN BY COLUMN in the export.

The positional layout mirrors the page's geometry, and for a contract or a
terms page printed in two columns geometry and reading order disagree: each
export line carried one printed line of EACH column, so a reader met "1. TERM.
This Agreement begins on the 2. PAYMENT. Lessee shall pay the monthly" as one
sentence. A band that reads as multi-column prose (`_prose_column_bands`,
`_band_is_prose`) is rendered every line of the first column, then every line
of the next, each at its own indent. A caption, a ledger and a label/value
block are NOT prose and stay side by side.

Run:  cd PDF-Linker && python3 -m pytest tests/test_prose_columns.py -v
"""
import pytest

fitz = pytest.importorskip("fitz")

import pdf_linker as P

LEFT = ["1. TERM. This Agreement begins on the", "Effective Date and continues for twelve",
        "months unless terminated earlier as", "provided herein.",
        "", "3. NOTICES. Any notice under this", "Agreement shall be in writing and"]
RIGHT = ["2. PAYMENT. Lessee shall pay the monthly", "rent on the first day of each month",
         "without demand, deduction or setoff of", "any kind whatsoever.",
         "4. DEFAULT. Failure to pay within ten", "days of the due date is a default", ""]


def _page(draw):
    doc = fitz.open()
    pg = doc.new_page()
    draw(pg)
    pg._doc_ref = doc
    return pg


def _two_column(extra=None):
    def draw(p):
        p.insert_text((72, 80), "COMMERCIAL LEASE AGREEMENT", fontsize=12, fontname="helv")
        y = 120
        for l, r in zip(LEFT, RIGHT):
            if l:
                p.insert_text((72, y), l, fontsize=10, fontname="helv")
            if r:
                p.insert_text((320, y), r, fontsize=10, fontname="helv")
            y += 13
        if extra:
            extra(p, y)
    return _page(draw)


def _nonblank(text):
    return [l for l in text.splitlines() if l.strip()]


def test_a_two_column_contract_reads_column_by_column():
    lines = _nonblank(P._page_visual_text(_two_column()))
    body = [l.strip() for l in lines[1:]]
    left = [l for l in LEFT if l]
    right = [r for r in RIGHT if r]
    assert body == left + right, lines
    # …each column at its own indent: the right column sits to the right.
    r_lines = [l for l in lines if l.strip() in right]
    assert all(l.startswith(" " * 30) for l in r_lines)
    assert all(not l.startswith(" ") for l in lines if l.strip() in left)


def test_a_paragraph_gap_inside_one_column_is_a_blank_line_in_that_column():
    out = P._page_visual_text(_two_column())
    text_left = out.split("2. PAYMENT")[0]
    assert "provided herein.\n\n3. NOTICES" in text_left


def test_a_full_width_line_ends_the_band():
    def extra(p, y):
        p.insert_text((72, y + 20), "IN WITNESS WHEREOF the parties have executed this "
                      "Agreement on the date first written above.", fontsize=10, fontname="helv")
    lines = _nonblank(P._page_visual_text(_two_column(extra)))
    assert lines[-1].startswith("IN WITNESS WHEREOF")
    assert lines[-2].strip() == "days of the due date is a default"


def test_a_caption_stays_side_by_side():
    cap = [("HELEN RASHO, an individual,", "Case No. 25STCV37838"),
           ("Plaintiff,", "OPPOSITION TO MOTION TO"), ("v.", "COMPEL ARBITRATION"),
           ("QUILLMARK BUILDERS LLC, a California", "Date: Oct 1, 2026"),
           ("limited liability company,", "Dept: 55")]

    def draw(p):
        for i, (l, r) in enumerate(cap):
            p.insert_text((72, 100 + 14 * i), l, fontsize=11, fontname="helv")
            p.insert_text((380, 100 + 14 * i), r, fontsize=11, fontname="helv")
    lines = _nonblank(P._page_visual_text(_page(draw)))
    assert len(lines) == 5
    assert "Case No." in lines[0] and "HELEN RASHO" in lines[0]


def test_a_ledger_stays_a_table():
    cols = [72, 300, 360, 420]
    rows = [("Telephone conference with client regarding the responses", "0.8", "450", "360.00"),
            ("Draft and revise the opposition to the motion to compel", "4.5", "450", "2,025.00"),
            ("Review and analyse the file for the upcoming hearing", "0.2", "450", "90.00"),
            ("Email to opposing counsel regarding the discovery cutoff", "0.1", "450", "45.00")]

    def draw(p):
        for i, r in enumerate(rows):
            for x, t in zip(cols, r):
                p.insert_text((x, 80 + 11 * i), t, fontsize=8, fontname="helv")
    lines = _nonblank(P._page_visual_text(_page(draw)))
    assert len(lines) == 4 and all("450" in l for l in lines)


def test_single_column_prose_is_untouched():
    def draw(p):
        for i in range(6):
            p.insert_text((72, 80 + 13 * i), "The court orders the parties to meet and confer "
                          "before the hearing.", fontsize=10, fontname="helv")
    out = P._page_visual_text(_page(draw))
    assert P._prose_column_bands([]) == []
    assert len(_nonblank(out)) == 6 and all(not l.startswith(" ") for l in out.splitlines())


def test_band_screens():
    # Numbers and short cells are never prose; wide lower-case cells are.
    g = {72.0: 72.0, 320.0: 320.0}
    prose = [[(72.0, 300.0, "lessee shall pay the monthly rent"),
              (320.0, 540.0, "any notice under this agreement")]] * 4
    assert P._band_is_prose(prose, [72.0, 320.0], g)
    short = [[(72.0, 80.0, "v."), (320.0, 400.0, "Case No. 25STCV37838")]] * 4
    assert not P._band_is_prose(short, [72.0, 320.0], g)
    unfilled = [[(72.0, 150.0, "lessee shall pay rent"),
                 (320.0, 540.0, "any notice under this agreement")]] * 4
    assert not P._band_is_prose(unfilled, [72.0, 320.0], g)
