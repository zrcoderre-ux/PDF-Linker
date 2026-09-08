"""
A pleading page with a printed box or two is NOT a court form.

A delivered declaration's caption page — twenty-eight numbered lines, the
firm's attorney block, a two-column caption, the court's e-filing stamp —
came out of the export as a "[printed court form … 1 box(es), 0 marked]":
the gutter numbers set on lines of their own, the stamp's lines interleaved
word by word ("9/04/2026 County of 3:58 Los Angeles PM"), the caption's
columns lost. The ink gate lets a page in on checkbox-SIZED line art, which a
pleading can carry for reasons of its own, and the routing rule then handed
the page to the form layout on the strength of ONE empty box.

Now an INK rendering displaces the pleading rows only where the page is
form-shaped by a stronger measure than the gate's — a form id in its footer,
or at least `_INK_MIN_BOXES` states paired with captions — and a page below
that keeps its rows and gets the few states it has laid INTO them, so nothing
the ink pass read is lost.

Run:  cd PDF-Linker && python3 -m pytest tests/test_pleading_ink_boxes.py -v
"""
import importlib.util
import logging
from pathlib import Path

import fitz

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pdf_linker", _ROOT / "pdf_linker.py")
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)

log = logging.getLogger("test")

_STAMP = ["Electronically FILED by", "Superior Court of California,",
          "County of Los Angeles", "9/04/2026 3:58 PM",
          "David W. Slayton, Executive Officer/Clerk of Court,",
          "By M. Fulmer, Deputy Clerk"]


def _y(i):
    return 70 + i * 24


def _caption_page(doc, boxes=1, marked=False, form_no=None):
    """A pleading caption page: 28 gutter numbers, an attorney block, a
    two-column caption, a small-type e-filing stamp, and — on the notice
    line — `boxes` printed checkbox squares beside courthouse options, plus
    enough spare checkbox-sized line art that the ink gate admits the page."""
    p = doc.new_page(width=612, height=792)
    for k, ln in enumerate(_STAMP):
        p.insert_text((400, 60 + k * 8), ln, fontsize=6.5)
    for i in range(1, 29):
        p.insert_text((40, _y(i)), str(i), fontsize=10)
        if i <= 8:
            p.insert_text((80, _y(i)), f"Attorney line {i} of the block", fontsize=11)
        elif i <= 20:
            p.insert_text((80, _y(i)), f"Caption left {i},", fontsize=11)
            p.insert_text((300, _y(i)), ")", fontsize=11)
            p.insert_text((310, _y(i)), f"CASE NO. 19STCV62331 line {i}", fontsize=11)
        elif i < 28:
            p.insert_text((80, _y(i)), f"Please take notice paragraph line {i}.", fontsize=11)
    # line 28: "718 [box] Stanley Mosk …" — and more options for more boxes
    p.insert_text((80, _y(28)), "718", fontsize=11)
    x = 290
    for b in range(boxes):
        p.draw_rect(fitz.Rect(x - 18, _y(28) - 9, x - 8, _y(28) + 1), width=0.7)
        if marked and b == 0:
            p.draw_line(fitz.Point(x - 16, _y(28) - 7), fitz.Point(x - 10, _y(28) - 1),
                        width=0.8)
        p.insert_text((x, _y(28)), "Stanley Mosk", fontsize=11)
        x += 110
    # spare checkbox-sized line art beside no caption: what admits the page
    p.draw_rect(fitz.Rect(500, 700, 510, 710), width=0.7)
    p.draw_rect(fitz.Rect(520, 700, 530, 710), width=0.7)
    if form_no:
        p.insert_text((40, 760), f"{form_no} [Rev. January 1, 2023]", fontsize=6)
    return p


def _export(tmp_path, doc):
    src = tmp_path / "Declaration.pdf"
    doc.save(src)
    assert pl._write_text_version(src, fitz.open(src), log)
    return next((tmp_path / "Text Files").glob("*.txt")).read_text(encoding="utf-8")


def test_the_ink_pass_still_reads_the_one_box():
    # The gate admits the page and the pass pairs one box with its caption —
    # the state is real, and the fix below must not lose it.
    p = _caption_page(fitz.open())
    render = pl._form_page_render(p)
    assert render is not None and render["source"] == "exact"
    assert render["boxes"] == 1
    assert pl._form_has_state_boxes(render["text"])
    assert pl._page_lined_rows(p) is not None          # pleading paper


def test_one_empty_box_does_not_displace_the_pleading_rows(tmp_path):
    body = _export(tmp_path, _doc(boxes=1))
    assert "printed court form" not in body
    # the gutter numbers stay with their lines…
    assert " 1  Attorney line 1 of the block" in body
    assert "28  718 [ ] Stanley Mosk" in body
    # …the caption keeps its two columns on one line…
    assert any("Caption left 12," in ln and "CASE NO." in ln
               for ln in body.split("\n"))
    # …and the e-filing stamp's lines are not interleaved word by word
    assert "County of Los Angeles" in body
    assert "9/04/2026 3:58 PM" in body
    assert "County of 3:58" not in body


def _doc(**kw):
    doc = fitz.open()
    _caption_page(doc, **kw)
    return doc


def test_a_marked_box_on_pleading_paper_keeps_its_state_and_its_number(tmp_path):
    body = _export(tmp_path, _doc(boxes=1, marked=True))
    assert "printed court form" not in body
    assert "28  718 [X] Stanley Mosk" in body


def test_detection_reads_the_rows_the_export_writes():
    # The leak scan must see the same rendering — with the state laid in and
    # the numbers kept — not the form layout the export declined.
    p = _caption_page(fitz.open())
    render = pl._form_page_render(p)
    assert not pl._form_displaces_rows(render)
    detect = pl._page_detect_text(p, form=None, ink=render["ink"])
    assert "printed court form" not in detect
    assert "[ ]" in detect and "Stanley Mosk" in detect


def test_enough_paired_boxes_still_make_a_form(tmp_path):
    # The gate's own count, asked of the RESULT: three states paired with
    # captions is a form even on pleading paper, and takes the form layout.
    p = _caption_page(fitz.open(), boxes=pl._INK_MIN_BOXES)
    render = pl._form_page_render(p)
    assert render["boxes"] == pl._INK_MIN_BOXES
    assert pl._form_displaces_rows(render)
    body = _export(tmp_path, _doc(boxes=pl._INK_MIN_BOXES))
    assert "printed court form" in body


def test_a_form_id_in_the_footer_still_makes_a_form():
    p = _caption_page(fitz.open(), boxes=1, form_no="MC-025")
    render = pl._form_page_render(p)
    assert render["boxes"] == 1 and render["form_no"]
    assert pl._form_displaces_rows(render)


def test_a_widget_state_is_still_enough_on_its_own():
    # A widget's state is the form's own word: the rule is unchanged there.
    render = {"text": "[fillable form MC-025: 1 checkbox(es), 1 checked]\n[X] a",
              "source": "fields", "boxes": 1, "form_no": "", "ink": None}
    assert pl._form_displaces_rows(render)
    render["text"] = "[fillable form MC-025: no checkboxes]\nvalue"
    assert not pl._form_displaces_rows(render)


def test_a_state_no_row_is_near_is_left_out():
    # A box between two lines belongs to nobody, and is never invented onto one.
    spans = [{"text": "Stanley Mosk", "bbox": (290.0, 730.0, 360.0, 745.0),
              "origin": (290.0, 742.0), "size": 11.0}]
    cells = [pl._form_cell(700.0, 5.0, 272.0, "[ ]")]
    ink = (cells, 1, 0, 0, True, [])
    assert pl._ink_state_spans(spans, ink) == spans
    cells = [pl._form_cell(738.0, 5.0, 272.0, "[ ]")]
    ink = (cells, 1, 0, 0, True, [])
    out = pl._ink_state_spans(spans, ink)
    assert [s["text"] for s in sorted(out, key=lambda s: s["bbox"][0])] == ["[ ]", "Stanley Mosk"]
    assert pl._span_baseline(out[-1]) == 742.0     # on the row's own baseline


def test_the_glyph_inside_the_box_and_an_underscore_slot_go_with_the_state():
    spans = [{"text": "3", "bbox": (273.0, 733.0, 280.0, 742.0),
              "origin": (273.0, 742.0), "size": 9.0},
             {"text": "__ entire action", "bbox": (400.0, 730.0, 480.0, 745.0),
              "origin": (400.0, 742.0), "size": 11.0}]
    cells = [pl._form_cell(738.0, 5.0, 272.0, "[X]"),
             pl._form_cell(738.0, 7.0, 400.0, "[X]")]
    ink = (cells, 2, 2, 0, True, [fitz.Rect(273.0, 733.0, 280.0, 742.0)])
    out = sorted(pl._ink_state_spans(spans, ink), key=lambda s: s["bbox"][0])
    assert [s["text"] for s in out] == ["[X]", "[X]", "entire action"]
