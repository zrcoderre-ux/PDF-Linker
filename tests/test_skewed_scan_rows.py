"""
A SKEWED scan's OCR layer is sheared straight before its rows are clustered
(`_page_skew_slope`, `_deskew_spans`, in `_reading_frame_spans`).

A letter scanned a degree off square came out with every line in three pieces
on three rows, the END of each line ABOVE its beginning: the recogniser laid
each word on the baseline it measured, the extractor joined words into pieces
while the drift stayed inside its own tolerance, and `_cluster_rows` compared
each piece to the row's FIRST baseline — so the tail of a 500 pt line, 9 pt
higher than its head, was a different row, sorted above it.

Run:  cd PDF-Linker && python3 -m pytest tests/test_skewed_scan_rows.py -v
"""
import inspect
import math
import warnings

import fitz

import pdf_linker as P

warnings.filterwarnings("ignore", category=DeprecationWarning)

LINES = [
    "We have attempted to contact you by both first class mail and, on at "
    "least three occasions, by phone in an effort to discuss your",
    "financial situation and help you avoid foreclosure. Despite these "
    "attempts, we have been unable to reach you as of this letter date.",
    "Please contact us immediately so we can help you avoid a potentially "
    "serious situation.",
    "As a homeowner, you have the right to know which solutions are "
    "available to help you avoid foreclosure, including solutions that",
    "may help you keep your home. These could include:",
    "    Bringing your loan current through a repayment plan or reinstatement",
    "    Temporarily reducing or pausing your payments with a forbearance",
]


def _scan(skew_deg, rotate=0, stamp=False):
    """An OCR'd page: one invisible text object per WORD, each on the
    baseline a scan `skew_deg` off square would give it, with the word
    sizes varied a little so the extractor breaks each line into pieces
    the way a real OCR layer's does."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    if rotate:
        page.set_rotation(rotate)
    slope = math.tan(math.radians(skew_deg))
    for i, line in enumerate(LINES):
        x, y0 = 50.0, 100 + 14 * i
        for k, w in enumerate(line.split(" ")):
            if not w:
                x += 4
                continue
            fs = 8.0 + (0.6 if k % 3 == 0 else -0.4 if k % 3 == 1 else 0.0)
            y = y0 - slope * (x - 50)
            page.insert_text((x, y), w, fontsize=fs, fontname="helv",
                             render_mode=3)
            x += fitz.get_text_length(w + " ", fontname="helv", fontsize=fs)
    if stamp:
        # A slanted received-stamp: a few spans at a steep angle of their own.
        for j, w in enumerate(["RECEIVED", "SEP", "06", "2026"]):
            page.insert_text((400, 300 + 30 * j), w, fontsize=9,
                             fontname="helv", render_mode=3, rotate=0,
                             morph=(fitz.Point(400, 300 + 30 * j),
                                    fitz.Matrix(-25)))
    return doc


def _rows(page):
    return [ln for ln in (P._page_visual_text(page) or "").splitlines()
            if ln.strip()]


def _whole(rows):
    """Every printed line came out as ONE row carrying its whole text."""
    # Compared with the spaces out: the synthetic layer's word gaps are a
    # little tight for the glue rule here and there ("attemptedto"), which
    # is the fixture's doing and not the rows'.
    want = ["".join(l.split()) for l in LINES]
    got = ["".join(r.split()) for r in rows]
    return got == want


# ── the failure, and the fix ────────────────────────────────────────────────

def test_a_straight_scan_renders_line_by_line():
    assert _whole(_rows(_scan(0.0)[0]))


def test_a_skewed_scan_split_every_line_and_is_whole_now():
    for deg in (0.5, 1.0, -1.0, 1.8):
        rows = _rows(_scan(deg)[0])
        assert _whole(rows), (deg, rows)


def test_the_unsheared_page_really_does_split(monkeypatch):
    """The regression the fix answers: with the shear switched off the same
    page splits its lines, the tail of each ABOVE its head."""
    monkeypatch.setattr(P, "_deskew_spans", lambda spans: spans)
    rows = _rows(_scan(1.0)[0])
    assert not _whole(rows)
    assert len(rows) > len(LINES)
    # The tail of line one ("...discuss your") sorts above its head.
    tail = next(i for i, r in enumerate(rows) if r.rstrip().endswith("your"))
    head = next(i for i, r in enumerate(rows) if r.startswith("We have"))
    assert tail < head


def test_the_slope_is_measured_and_a_straight_page_reads_zero():
    straight = P._page_text_spans(_scan(0.0)[0])
    assert P._page_skew_slope(straight) == 0.0
    tilted = P._page_text_spans(_scan(1.0)[0])
    est = P._page_skew_slope(tilted)
    assert abs(est - (-math.tan(math.radians(1.0)))) < 0.002


def test_a_straight_page_is_returned_untouched():
    """The same list object back — the ordinary export does not move."""
    spans = P._page_text_spans(_scan(0.0)[0])
    assert P._deskew_spans(spans) is spans


def test_a_slanted_stamp_does_not_tilt_a_straight_page():
    doc = _scan(0.0, stamp=True)
    spans = P._page_text_spans(doc[0])
    assert P._page_skew_slope(spans) == 0.0
    body = [r for r in _rows(doc[0]) if not any(
        w in r for w in ("RECEIVED", "SEP", "2026", "06"))]
    assert _whole(body)


def test_the_shear_moves_y_alone():
    """A shear, not a rotation: every x is what the page prints, so the
    indent of the bullet lines survives."""
    spans = P._page_text_spans(_scan(1.0)[0])
    out = P._deskew_spans(spans)
    assert [s["bbox"][0] for s in out] == [s["bbox"][0] for s in spans]
    assert [s["bbox"][2] for s in out] == [s["bbox"][2] for s in spans]
    rows = _rows(_scan(1.0)[0])
    assert rows[5].startswith("   Bringing") and rows[6].startswith("   Temporarily")


def test_a_rotated_and_skewed_scan_composes_both_frames():
    """The /Rotate reading frame (#292) and the shear stack: a landscape
    scan displayed through /Rotate whose OCR layer is also a degree off."""
    rows = _rows(_scan(1.0, rotate=90)[0])
    assert _whole(rows), rows


def test_both_renderers_share_the_frame():
    src = inspect.getsource(P._reading_frame_spans)
    assert src.count("_deskew_spans(") == 2
    assert "_reading_frame_spans(" in inspect.getsource(P._page_flowing_text)
    assert "_reading_frame_spans(" in inspect.getsource(P._page_visual_text)
