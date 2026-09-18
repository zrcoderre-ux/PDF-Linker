"""
A HANDWRITTEN SIGNATURE is described, not read.

A signature that leaves no text layer exported as an EMPTY LINE, which is
indistinguishable from an unsigned one — and whether a declaration was signed
is frequently the whole question about it. The other outcome is worse: where a
recogniser did try, its letter-soup landed in the export as words the document
does not contain, was harvested as a name, drew a pool word and earned a key
row.

So a signature LINE the text layer says nothing about is described instead:
"[signed, but not OCR readable]" or "[no signature detected]", with the middle
of the measurement reported as possible rather than rounded, the way a
checkbox's is. A TYPED signature is untouched — an area carrying any word at
all yields no note, so OCR works as usual wherever OCR worked.

Run:  cd PDF-Linker && python3 -m pytest tests/test_signature_line.py -v
"""
import importlib.util
import logging
import math
import random
import re
from pathlib import Path

import fitz

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pdf_linker", _ROOT / "pdf_linker.py")
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)

log = logging.getLogger("test")

_LINE_Y = 420.0
_LINE_X0, _LINE_X1 = 200.0, 430.0


def _scrawl(page, y=_LINE_Y, width=200, pen=1.0, x0=210.0):
    """A cursive-looking mark sitting on the line at `y`."""
    pts = [fitz.Point(x0 + i, y - 8 - 9 * math.sin(i / 7.0) - 3 * math.cos(i / 2.3))
           for i in range(int(width))]
    for a, b in zip(pts, pts[1:]):
        page.draw_line(a, b, width=pen)


def _page(label="(SIGNATURE OF DECLARANT)", signed=False, typed=None,
          rule=True, prose="I declare under penalty of perjury.", draw=None):
    doc = fitz.open()
    pg = doc.new_page()
    if prose:
        pg.insert_text((72, 300), prose, fontsize=11)
    if rule:
        pg.draw_line(fitz.Point(_LINE_X0, _LINE_Y), fitz.Point(_LINE_X1, _LINE_Y),
                     width=0.8)
    if label:
        pg.insert_text((_LINE_X0, _LINE_Y + 11), label, fontsize=9)
    if typed:
        pg.insert_text((_LINE_X0 + 5, _LINE_Y - 3), typed, fontsize=11)
    if signed:
        _scrawl(pg)
    if draw:
        draw(pg)
    # Round-trip so the page is read exactly as a filed PDF is.
    return fitz.open("pdf", doc.tobytes())


def _notes(doc):
    pg = doc[0]
    return [sp["text"] for sp in
            pl._signature_note_spans(pl._page_text_spans(pg), pg)]


def _export(doc):
    return pl._page_visual_text(doc[0]) or ""


# ── 1. The verdicts ─────────────────────────────────────────────────────────

def test_a_signed_line_says_it_is_signed_and_not_readable():
    assert _notes(_page(signed=True)) == [pl._SIG_NOTE_SIGNED]
    assert pl._SIG_NOTE_SIGNED in _export(_page(signed=True))


def test_an_empty_signature_line_says_so():
    # The failure this exists for: a blank line reads as a complete document.
    assert _notes(_page()) == [pl._SIG_NOTE_NONE]
    assert pl._SIG_NOTE_NONE in _export(_page())


def test_a_typed_signature_is_left_to_OCR():
    # "/s/ Jane Doe" is text; the text layer has read it and the note is for
    # the line nothing read.
    assert _notes(_page(typed="/s/ Jane Doe")) == []
    out = _export(_page(typed="/s/ Jane Doe"))
    assert "/s/ Jane Doe" in out
    assert not any(n in out for n in pl._SIG_NOTES)


def test_a_typed_name_beside_a_scrawl_is_still_left_alone():
    assert _notes(_page(typed="JANE DOE", signed=True)) == []


# ── 2. The anchor is the page's own word ────────────────────────────────────

def test_a_rule_with_no_label_is_not_a_signature_line():
    # Every heading underline and table edge in a batch is a rule.
    assert _notes(_page(label=None)) == []
    assert _notes(_page(label="Dated: January 5, 2026")) == []


def test_prose_that_merely_mentions_a_signature_is_not_a_label():
    for line in ("The signature of the parties was forged in 2019.",
                 "his signature appears on the third page of the exhibit",
                 "Defendant signed by mistake and now seeks relief."):
        assert _notes(_page(label=line)) == [], line


def test_a_label_needs_a_line_of_its_own():
    assert _notes(_page(rule=False)) == []


def test_the_label_forms_a_filing_actually_prints():
    for label in ("(SIGNATURE OF DECLARANT)", "Signature:",
                  "SIGNATURE OF ATTORNEY OR PARTY WITHOUT ATTORNEY",
                  "(Signature of Plaintiff)", "Signature"):
        assert _notes(_page(label=label, signed=True)) == [pl._SIG_NOTE_SIGNED], label


def test_a_signed_by_stamp_is_read_under_its_label():
    # A "Signed by" stamp writes UNDER its label and rules no line of the
    # page's own, so the cell being nothing BUT the label is its whole
    # corroboration — prose always gives the phrase its agent.
    def stamp(pg):
        _scrawl(pg, y=_LINE_Y + 34, width=120, pen=1.2, x0=205.0)

    signed = _page(label="Signed by:", rule=False, draw=stamp)
    assert _notes(signed) == [pl._SIG_NOTE_SIGNED]
    assert _notes(_page(label="Signed by:", rule=False)) == [pl._SIG_NOTE_NONE]
    assert _notes(_page(label="Signed by Jane Doe", rule=False)) == []


# ── 3. Dirt is not a signature ──────────────────────────────────────────────

def _speckle(density, radius, seed=11):
    rnd = random.Random(seed)
    def draw(pg):
        for _ in range(int(230 * 24 * density)):
            pg.draw_circle(fitz.Point(_LINE_X0 + rnd.random() * 230,
                                      _LINE_Y - 24 + rnd.random() * 23),
                           radius, color=(0, 0, 0), fill=(0, 0, 0), width=0)
    return draw


def test_a_dirty_blank_line_is_never_reported_as_signed():
    # Measured, a blank line under heavy scanner dirt carries as much INK as a
    # signed one — which is why the measure is STROKES. Asserting that a
    # filing was signed is not a guess this tool makes.
    for density, radius in ((0.05, 0.35), (0.05, 0.6), (0.10, 0.6),
                            (0.10, 1.0), (0.20, 0.6)):
        got = _notes(_page(draw=_speckle(density, radius)))
        assert got and got[0] != pl._SIG_NOTE_SIGNED, (density, radius, got)


def test_a_thin_pen_and_a_short_initial_still_read_as_signed():
    assert _notes(_page(signed=True)) == [pl._SIG_NOTE_SIGNED]
    for width, pen in ((200, 0.8), (200, 1.2), (40, 1.0), (25, 0.8)):
        doc = _page(label="(SIGNATURE OF DECLARANT)",
                    draw=lambda pg, w=width, p=pen: _scrawl(pg, width=w, pen=p))
        assert _notes(doc) == [pl._SIG_NOTE_SIGNED], (width, pen)


# ── 4. One line, one note, one rendering ────────────────────────────────────

def test_two_labels_for_one_rule_earn_one_note():
    doc = _page(signed=True)
    pg = doc[0]
    pg.insert_text((_LINE_X0 + 150, _LINE_Y + 11), "Signature", fontsize=9)
    doc = fitz.open("pdf", doc.tobytes())
    assert _notes(doc) == [pl._SIG_NOTE_SIGNED]


def test_the_note_is_laid_at_the_seam_every_rendering_reads():
    # Two definitions of what a page says about its signature line is how one
    # page comes to be described two ways. The pass is called once, from
    # `_drop_overdrawn_spans`, and every renderer takes its spans through it.
    src = (_ROOT / "pdf_linker.py").read_text(encoding="utf-8")
    calls = re.findall(r"^(?!def )[^\n#]*_signature_note_spans\(", src, re.M)
    assert len(calls) == 1, calls
    assert "def _signature_note_spans" in src


def test_the_note_never_reaches_the_flowing_text():
    # That rendering is the citation parse's and the unscrubbed copy's, and it
    # is returned byte-for-byte where the page carries no re-draw.
    doc = _page(signed=True)
    pg = doc[0]
    flowing = pl._page_flowing_text(pg)
    assert not any(n in flowing for n in pl._SIG_NOTES)
    assert flowing == pl._undouble_strike_lines(pg.get_text("text"))


def test_the_note_is_never_read_back_as_a_real_value():
    # It stands in the export as ordinary text, so a worksheet `yes` could
    # otherwise mint this tool's own sentence as a party.
    for note in pl._SIG_NOTES:
        assert pl._pn_is_never_fake(note), note


def test_one_render_answers_a_page_however_often_it_is_asked():
    # Every rendering of a page goes through the seam; without the memo each
    # would rasterise the page again.
    doc = _page(signed=True)
    pg = doc[0]
    made = []
    real = pl._InkRaster

    class Counted(real):
        def __init__(self, page, *a, **kw):
            made.append(page.number)
            super().__init__(page, *a, **kw)

    pl._InkRaster = Counted
    try:
        for _ in range(4):
            assert _notes(doc) == [pl._SIG_NOTE_SIGNED]
    finally:
        pl._InkRaster = real
    assert len(made) == 1, made


# ── 5. A pleading page keeps its numbers and still says it ──────────────────

def _pleading_page(signed):
    doc = fitz.open()
    pg = doc.new_page()
    for i in range(1, 29):
        pg.insert_text((40, 70 + (i - 1) * 24), str(i), fontsize=12)
    pg.insert_text((95, 70), "I declare under penalty of perjury that the",
                   fontsize=11)
    pg.insert_text((95, 94), "foregoing is true and correct.", fontsize=11)
    y = 70 + 11 * 24
    pg.draw_line(fitz.Point(240, y), fitz.Point(460, y), width=0.8)
    pg.insert_text((240, y + 11), "(SIGNATURE OF DECLARANT)", fontsize=9)
    if signed:
        _scrawl(pg, y=y, width=180, pen=1.2, x0=250.0)
    return fitz.open("pdf", doc.tobytes())


def test_a_pleading_page_keeps_its_gutter_numbers_and_says_it():
    doc = _pleading_page(signed=True)
    rows = pl._page_lined_rows(doc[0])
    assert rows, "the pleading path declined the page"
    text = "\n".join(t for _n, segs in rows for _x, t in segs)
    assert pl._SIG_NOTE_SIGNED in text
    # …and the note carries no line number of its own away from the page's.
    assert [n for n, _s in rows if n] == sorted(n for n, _s in rows if n)
    blank = pl._page_lined_rows(_pleading_page(signed=False)[0])
    assert pl._SIG_NOTE_NONE in "\n".join(t for _n, segs in blank
                                          for _x, t in segs)


# ── 6. The page the pass exists for: a SCAN ─────────────────────────────────

def _scanned(signed):
    """A page rendered to a picture with an invisible OCR layer over it — how
    a signed declaration actually arrives. The only thing that can say whether
    it was signed is the ink in the picture."""
    src = fitz.open()
    pg = src.new_page()
    pg.insert_text((72, 300), "I declare under penalty of perjury.", fontsize=11)
    pg.draw_line(fitz.Point(_LINE_X0, _LINE_Y), fitz.Point(_LINE_X1, _LINE_Y),
                 width=0.8)
    pg.insert_text((_LINE_X0, _LINE_Y + 11), "(SIGNATURE OF DECLARANT)", fontsize=9)
    if signed:
        _scrawl(pg, pen=1.2)
    pix = pg.get_pixmap(dpi=200)
    out = fitz.open()
    p2 = out.new_page(width=pg.rect.width, height=pg.rect.height)
    p2.insert_image(p2.rect, pixmap=pix)
    for xy, text, size in (((72, 300), "I declare under penalty of perjury.", 11),
                           ((_LINE_X0, _LINE_Y + 11), "(SIGNATURE OF DECLARANT)", 9)):
        p2.insert_text(xy, text, fontsize=size, render_mode=3)
    return fitz.open("pdf", out.tobytes())


def test_a_scanned_declaration_says_whether_it_was_signed():
    assert _notes(_scanned(True)) == [pl._SIG_NOTE_SIGNED]
    assert _notes(_scanned(False)) == [pl._SIG_NOTE_NONE]
    out = _export(_scanned(True))
    # …above the line, where it was written, and above the label that names it.
    lines = [ln for ln in out.splitlines() if ln.strip()]
    i = next(k for k, ln in enumerate(lines) if pl._SIG_NOTE_SIGNED in ln)
    assert "(SIGNATURE OF DECLARANT)" in lines[i + 2]


def test_a_form_prints_its_own_pointer_into_the_band():
    # Every Judicial Council form prints a "►" beside its signature line, as a
    # nine-point IMAGE — measured, a mark in the writing space. A blank form
    # says its line is blank, not that it may carry something.
    blanks = sorted((_ROOT / "Form Templates").glob("*.pdf"))
    assert blanks, "no committed blanks to measure against"
    seen = []
    for path in blanks:
        with fitz.open(path) as doc:
            for pg in doc:
                seen += [sp["text"] for sp in
                         pl._signature_note_spans(pl._page_text_spans(pg), pg)]
    assert seen, "no signature line found on any committed blank"
    assert set(seen) == {pl._SIG_NOTE_NONE}, sorted(set(seen))
