"""The form export mirrors the PAGE, so a person can read the two side by
side: the page's vertical gaps are blank lines, its ruled boxes are drawn
(`─` runs and `│` bars), the footer's small lines are their own rows, and the
grid unit is the page's own type (`_form_layout`, `_form_page_geometry`,
`_form_raw_spans`).

Run:  cd PDF-Linker && python3 -m pytest tests/test_form_render_fidelity.py -v
"""
import pytest

fitz = pytest.importorskip("fitz")

import pdf_linker as P


def _rule_line(l):
    """A line that is nothing but line art: a rule run with its junctions."""
    t = l.strip()
    return bool(t) and P._FORM_HRULE in t and set(t) <= set(P._RULE_GLYPHS)


def _boxed_form():
    """A page shaped like a Judicial Council caption: a ruled box with a
    column divider, a checkbox, a caption set hard against the box edge, a
    wide gap before the next item, and a three-line 6 pt footer beside a
    two-line 10 pt title."""
    doc = fitz.open()
    pg = doc.new_page()
    sh = pg.new_shape()
    sh.draw_rect(fitz.Rect(36, 47, 576, 120))          # the caption box
    sh.draw_line(fitz.Point(396, 47), fitz.Point(396, 120))  # its divider
    sh.draw_line(fitz.Point(200, 47), fitz.Point(200, 80))   # a two-line box's edge, 33 pt
    sh.finish(width=0.6)
    sh.commit()
    pg.insert_text((38, 58), "ATTORNEY OR PARTY WITHOUT ATTORNEY", fontsize=6, fontname="helv")
    pg.insert_text((400, 58), "FOR COURT USE ONLY", fontsize=6, fontname="helv")
    pg.insert_text((38, 75), "NAME: Rosa Delgado", fontsize=9, fontname="helv")
    pg.insert_text((38, 110), "PLAINTIFF: Rosa Delgado", fontsize=9, fontname="helv")
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    w.field_name = "cb"
    w.rect = fitz.Rect(36, 140, 45, 149)
    w.field_value = True
    pg.add_widget(w)
    pg.insert_text((50, 148), "MOTOR VEHICLE", fontsize=9, fontname="helv")
    pg.insert_text((36, 210), "1. Plaintiff (name):", fontsize=9, fontname="helv")   # a wide gap
    for i, t in enumerate(("Form Approved for Optional Use", "Judicial Council of California",
                           "PLD-PI-001 [Rev. January 1, 2024]")):
        pg.insert_text((36, 735 + 7 * i), t, fontsize=6, fontname="helv")
    pg.insert_text((250, 737), "COMPLAINT—Personal Injury, Property", fontsize=10, fontname="helv")
    pg.insert_text((250, 749), "Damage, Wrongful Death", fontsize=10, fontname="helv")
    pg._doc_ref = doc
    return pg


def _lines(text):
    return text.splitlines()[1:]          # past the banner


def test_rules_are_drawn_and_the_box_reads_as_a_box():
    lines = _lines(P._form_page_text(_boxed_form()))
    top = next(i for i, l in enumerate(lines) if _rule_line(l))
    bottom = next(i for i, l in enumerate(lines) if i > top and _rule_line(l))
    inside = lines[top + 1:bottom]
    assert inside, lines
    # every line inside the box carries its left edge, the divider and its right edge
    for l in inside:
        assert l.count(P._FORM_VRULE) >= 3, l
    # …and the divider stands at ONE column all the way down
    cols = {l.rindex(P._FORM_VRULE, 0, l.rindex(P._FORM_VRULE)) for l in inside}
    assert len(cols) == 1, cols
    # the short (33 pt) edge is drawn on the lines it crosses and no others
    short = [l for l in inside if l.count(P._FORM_VRULE) == 4]
    assert short and len(short) < len(inside), inside
    # the caption set against the edge follows it, never overprints it
    l = next(l for l in inside if "ATTORNEY OR PARTY" in l)
    assert l.index("ATTORNEY") > l.index(P._FORM_VRULE)
    assert "FOR COURT USE ONLY" in l and l.index("FOR COURT") > l.index("ATTORNEY")


def test_a_vertical_gap_is_a_blank_line_and_the_box_edges_do_not_shift_the_page():
    lines = _lines(P._form_page_text(_boxed_form()))
    i = next(i for i, l in enumerate(lines) if "MOTOR VEHICLE" in l)
    j = next(i for i, l in enumerate(lines) if "1. Plaintiff" in l)
    assert any(l.strip() == "" for l in lines[i + 1:j]), lines[i:j + 1]
    # the page's left edge is the box's edge: nothing is indented by a phantom margin
    assert lines[j].startswith("1. Plaintiff")
    assert " ".join(lines[i].split()).startswith("[X] MOTOR VEHICLE")


def test_the_footer_keeps_its_lines():
    lines = _lines(P._form_page_text(_boxed_form()))
    foot = [l for l in lines if any(k in l for k in ("Form Approved", "Judicial Council", "PLD-PI-001 [Rev"))]
    assert len(foot) == 3, foot
    assert "COMPLAINT" in foot[0] and "Damage, Wrongful Death" not in foot[0]


def test_the_grid_unit_is_measured_off_the_page():
    pg = _boxed_form()
    cw, (vr, hr), page_w = P._form_page_geometry(pg)
    assert cw != P._FORM_CHAR_W and page_w == pytest.approx(pg.rect.width)
    # the drawing floor admits the two-line box's short edges the row
    # splitter's floor refuses
    assert any(y1 - y0 < P._RULE_MIN_LEN for _x, y0, y1 in vr)


def test_a_cell_at_its_own_stop_never_pushes_the_stop():
    # the box edge and the caption set 2 pt inside it share one stop; the
    # row's own guard separates them and the stop stays at column 0
    rows = [[(36.0, "│"), (38.0, "ATTORNEY OR PARTY WITHOUT ATTORNEY")],
            [(36.0, "│"), (38.0, "NAME: Rosa Delgado")]]
    stops = P._column_stops(rows, 36.0, 4.0)
    assert stops[36.0] == 0 and stops[38.0] == 0
    a, b = P._visual_rows_text(rows, 36.0, 4.0)
    assert a.startswith("│ ATTORNEY") and b.startswith("│ NAME")


def test_padded_label_x_is_read_off_the_characters():
    doc = fitz.open()
    pg = doc.new_page()
    pg.insert_text((100, 100), " " * 30 + "(describe):", fontsize=9, fontname="helv")
    sp = next(sp for blk in P._form_raw_spans(pg) for ln in blk.get("lines", [])
              for sp in ln.get("spans", []) if "(describe)" in sp["text"])
    assert sp["_vis_x0"] == pytest.approx(100 + 30 * 0.278 * 9, abs=1.5)
    assert P._form_text_x(100.0, sp["text"], 9.0, sp["_vis_x0"]) == sp["_vis_x0"]
