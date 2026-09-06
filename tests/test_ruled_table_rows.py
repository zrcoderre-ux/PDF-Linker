"""
A ruled TABLE on pleading paper — a separate statement's three columns — is
read by the rules the page draws (`_page_rules`), split at every vertical rule
(`_split_row_columns(rules=…)`), and folded row by row into CELLS
(`_fold_ruled_rows`, from `_page_lined_rows`): each cell's wrapped lines
joined into its paragraph, the cells behind pipes, the header followed by a
rule row, the row keeping the gutter number of the line it starts on.

Read line by line, the export interleaved the three columns one printed line
each per numbered line, and where two cells' lines sat closer than the column
gap they were welded outright: "(Caira v. historical fact stated."

Run:  cd PDF-Linker && python3 -m pytest tests/test_ruled_table_rows.py -v
"""
import logging
import re
import warnings

import fitz

import pdf_linker as P

warnings.filterwarnings("ignore", category=DeprecationWarning)
log = logging.getLogger("test")
DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}

HDR = ["MOVING PARTY'S UNDISPUTED MATERIAL FACTS AND SUPPORTING EVIDENCE",
       "OPPOSING PARTY'S RESPONSE AND SUPPORTING EVIDENCE",
       "MOVING PARTY'S REPLY AND SUPPORTING EVIDENCE"]
ROWS = [
    ["15. Plaintiff Helen Rasho took possession of the Property on or about "
     "December 28, 2025. Evidence: Kamenetsky Dec. passim, Exs. 1-3 thereto.",
     "15. This fact is undisputed. Defendants admit that Plaintiff took "
     "possession on or about December 28, 2025. Their disagreement concerns "
     "the legal consequence of possession, not the historical fact stated.",
     "(Caira v. Offner (2005) 126 Cal.App.4th 12, 21.) Because Plaintiff's "
     "superior ownership and right to possession are disputed, the fact of "
     "his prior physical possession does not establish entitlement to "
     "judgment as a matter of law."],
    ["16. Defendant Quillmark Builders LLC entered the Property on January 3, "
     "2026 without notice. Evidence: Rasho Dec. para. 4.",
     "16. Disputed. Quillmark gave written notice on December 30, 2025. "
     "Evidence: Melbury Dec. para. 2, Ex. A.",
     "The purported notice was never received and is not authenticated. "
     "Evidence: Rasho Reply Dec. para. 3."],
]
XS = (90, 262, 432, 586)
YS = (100, 160, 420, 700)


def _separate_statement(boxes=False, gutter=True):
    """A pleading page: gutter numbers, a title, and a three-column ruled
    table whose cells wrap their own paragraphs. `boxes` draws the grid as
    cell RECTANGLES instead of lines, the other way a table is drawn."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    if gutter:
        for i in range(1, 29):
            page.insert_text((45, 90 + i * 23.0), str(i), fontsize=11)
    page.insert_text((200, 70), "REPLY SEPARATE STATEMENT", fontsize=11)
    sh = page.new_shape()
    if boxes:
        for r in range(len(YS) - 1):
            for c in range(len(XS) - 1):
                sh.draw_rect(fitz.Rect(XS[c], YS[r], XS[c + 1], YS[r + 1]))
    else:
        for x in XS:
            sh.draw_line((x, YS[0]), (x, YS[-1]))
        for y in YS:
            sh.draw_line((XS[0], y), (XS[-1], y))
    sh.finish(width=0.7, color=(0, 0, 0))
    sh.commit()
    for r, texts in enumerate([HDR] + ROWS):
        for c, t in enumerate(texts):
            rect = fitz.Rect(XS[c] + 4, YS[r] + 4, XS[c + 1] - 4, YS[r + 1] - 2)
            page.insert_textbox(rect, t, fontsize=9, fontname="helv")
    return doc


def _caption_box():
    """A pleading page whose CAPTION is drawn as a lined box with a divider —
    two columns, one box, role rows — and no table."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for i in range(1, 29):
        page.insert_text((45, 90 + i * 23.0), str(i), fontsize=11)
    sh = page.new_shape()
    for x in (90, 340, 586):
        sh.draw_line((x, 100), (x, 300))
    for y in (100, 200, 300):
        sh.draw_line((90, y), (586, y))
    sh.finish(width=0.7, color=(0, 0, 0))
    sh.commit()
    for k, t in enumerate(["HELEN RASHO, an individual,", "Plaintiff,", "vs.",
                           "QUILLMARK BUILDERS LLC,", "Defendants."]):
        page.insert_text((95, 113 + 23 * k), t, fontsize=11)
    page.insert_text((345, 113), "Case No. 25STCV37838", fontsize=11)
    page.insert_text((345, 136), "NOTICE OF MOTION", fontsize=11)
    return doc


def _display(rows):
    left = P._rows_body_left(rows)
    return [((f"{num:>2}  " if num is not None else "    ")
             + P._visual_row_text(segs, left)).rstrip() for num, segs in rows]


# ── the rules ────────────────────────────────────────────────────────────────

def test_the_rules_are_read_off_lines_and_off_boxes():
    for boxes in (False, True):
        vr, hr = P._page_rules(_separate_statement(boxes=boxes)[0])
        assert [round(x) for x, _a, _b in vr] == list(XS), boxes
        assert [round(y) for y, _a, _b in hr] == list(YS), boxes
        # Each merged to one rule with the full extent of the strokes.
        assert all(round(b - a) == YS[-1] - YS[0] for _x, a, b in vr)


def test_a_plain_pleading_page_has_no_rules():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((95, 113), "Plaintiff alleges negligence.", fontsize=11)
    assert P._page_rules(page) == ([], [])


def test_a_rule_splits_a_row_whatever_the_gap():
    spans = [{"bbox": (94.0, 100.0, 258.0, 110.0), "text": "(Caira v."},
             {"bbox": (266.0, 100.0, 420.0, 110.0), "text": "historical fact stated."}]
    # 8 pt apart: under the column gap, so one segment without a rule…
    assert len(P._split_row_columns(spans)) == 1
    # …and two with the rule the page draws between them.
    assert [t for _x, t in P._split_row_columns(spans, rules=[262.0])] == \
        ["(Caira v.", "historical fact stated."]


# ── the fold ─────────────────────────────────────────────────────────────────

def test_a_separate_statement_folds_into_cells():
    for boxes in (False, True):
        rows = P._page_lined_rows(_separate_statement(boxes=boxes)[0])
        lines = _display(rows)
        assert lines[0].strip() == "REPLY SEPARATE STATEMENT"
        assert lines[1].startswith(" 1  | MOVING PARTY'S UNDISPUTED")
        assert lines[1].rstrip().endswith("REPLY AND SUPPORTING EVIDENCE |")
        assert lines[2].strip() == "| --- | --- | --- |"
        # Each cell whole, in order, behind pipes — and the cite contiguous.
        fact = lines[3]
        # The row keeps the gutter number of the line it STARTS on.
        assert re.match(r"^ ?\d+  \| 15\. Plaintiff Helen Rasho took possession", fact)
        assert "| (Caira v. Offner (2005) 126 Cal.App.4th 12, 21.) Because" in fact
        assert "historical fact stated. |" in fact
        assert fact.count("|") == 4
        assert re.match(r"^\d+  \| 16\. Defendant Quillmark Builders LLC", lines[4])
        assert len(lines) == 5


def test_the_cells_are_separate_segments_for_the_scrub():
    rows = P._page_lined_rows(_separate_statement()[0])
    num, fact = next((num, segs) for num, segs in rows
                     if segs[0][1].startswith("| 15."))
    assert num is not None
    assert len(fact) == 3
    assert [t[:6] for _x, t in fact] == ["| 15. ", "| 15. ", "| (Cai"]
    # …each at its own column, so the column streams keep them apart.
    bands = P._page_column_bands(rows)
    i = next(i for i, (_n, segs) in enumerate(rows)
             if segs[0][1].startswith("| 15."))
    assert len(set(bands[i])) == 3


def test_a_plain_pleading_page_is_returned_as_it_came():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for i in range(1, 29):
        page.insert_text((45, 90 + i * 23.0), str(i), fontsize=11)
        page.insert_text((95, 90 + i * 23.0), f"Body line {i} of the brief.",
                         fontsize=11)
    anchors = P._detect_line_anchors(page)
    assert P._fold_ruled_rows(anchors, page) is anchors


def test_a_lined_caption_box_is_not_a_table():
    rows = P._page_lined_rows(_caption_box()[0])
    texts = [t for _n, segs in rows for _x, t in segs]
    assert "Plaintiff," in texts and "vs." in texts
    assert not any(t.startswith("|") for t in texts)


def test_the_linker_still_sees_the_page_line_by_line():
    """`_detect_line_anchors` is the linker's — its rows are split at the
    rules and never folded, so a citation's rect is still its own line's."""
    anchors = P._detect_line_anchors(_separate_statement()[0])
    assert not any(t.startswith("|") for a in anchors for _x, t in a["segments"])
    caira = [a for a in anchors if any("(Caira v." in t for _x, t in a["segments"])]
    assert caira and all(len(a["segments"]) >= 2 for a in caira)


def test_the_export_scrubs_the_cells_and_reads_them_whole(tmp_path):
    pdf = tmp_path / "Reply Separate Statement.pdf"
    _separate_statement().save(pdf)
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Helen Rasho", "Quillmark Builders LLC"], [], [],
                              registry=reg)
    pz = P.Pseudonymizer(terms, DET, registry=reg)
    assert P.process_pdf(pdf, log, pseudonymizer=pz)
    export = next((tmp_path / "Text Files").glob("*.txt")).read_text(
        encoding="utf-8")
    fake = next(t for t in terms if t.real == "Helen Rasho").fake
    assert "Helen Rasho" not in export and "Rasho" not in export
    assert f"| 15. Plaintiff {fake} took possession" in export
    assert "(Caira v. Offner (2005) 126 Cal.App.4th 12, 21.)" in export
    assert "| --- | --- | --- |" in export
    assert not pz.surviving_reals(export)
    # Detection reads whole cells too.
    detect = P._page_detect_text(fitz.open(pdf)[0])
    assert "Because Plaintiff's superior ownership" in detect
