"""Two defects off one delivered PLD-PI-001 (`_widget_is_on`, `_form_text_x`).

A checkbox is ON where the page DRAWS it on: its appearance state (/AS) is
the answer where the widget carries one, and the value is consulted only
where it does not — item 12.b of the delivered form had V=1 against an
on-state of 2 with /AS /Off, the viewer drew it empty, and "not Off, so on"
printed [X] on a blank box. And a form positions a trailing label by
PADDING its span with spaces, so "(describe):" opened at the caption's own
x and the layout sorted it AHEAD of the caption; the visible text starts
where the padding ends.

Run:  cd PDF-Linker && python3 -m pytest tests/test_form_widget_state_and_padding.py -v
"""
import pytest

fitz = pytest.importorskip("fitz")

import pdf_linker as P


def _checkbox_doc(value, on_state="2", appearance=None):
    """A page with one checkbox whose on-state is `on_state`, its /V set to
    `value` and its /AS to `appearance` (None removes the key)."""
    doc = fitz.open()
    pg = doc.new_page()
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    w.field_name = "box"
    w.rect = fitz.Rect(72, 72, 84, 84)
    w.field_value = True
    pg.add_widget(w)
    w = next(pg.widgets())
    # Rename the on-state appearance, then set V and AS independently, which
    # is the shape a filled form can arrive in.
    ap = doc.xref_get_key(w.xref, "AP/N")[1]
    on_ref = ap.split()[1:3]           # "<</Yes 12 0 R>>" -> ["12", "0"]
    doc.xref_set_key(w.xref, "AP/N", f"<</{on_state} {on_ref[0]} {on_ref[1]} R>>")
    doc.xref_set_key(w.xref, "V", f"/{value}")
    doc.xref_set_key(w.xref, "AS", f"/{appearance}" if appearance else "null")
    return doc


def _widget(doc):
    """The page's one widget, with the PAGE kept alive beside it: PyMuPDF holds
    a widget's page by weak reference, and a temporary `doc[0]` dies under it."""
    pg = doc[0]
    w = next(pg.widgets())
    w._keep_page = pg
    return w


class TestWidgetIsOn:
    def test_the_appearance_state_decides_where_present(self):
        off = _checkbox_doc(value="1", on_state="2", appearance="Off")
        assert P._widget_is_on(_widget(off)) is False
        on = _checkbox_doc(value="2", on_state="2", appearance="2")
        assert P._widget_is_on(_widget(on)) is True
        # …even against a value that says otherwise: the page draws /AS.
        drawn = _checkbox_doc(value="Off", on_state="2", appearance="2")
        assert P._widget_is_on(_widget(drawn)) is True

    def test_without_an_appearance_state_the_value_must_name_the_on_state(self):
        w = _widget(_checkbox_doc(value="1", on_state="2", appearance=None))
        assert P._widget_is_on(w) is False
        w = _widget(_checkbox_doc(value="2", on_state="2", appearance=None))
        assert P._widget_is_on(w) is True
        w = _widget(_checkbox_doc(value="Off", on_state="2", appearance=None))
        assert P._widget_is_on(w) is False


class TestPaddedLabel:
    def test_a_space_padded_label_follows_its_caption(self):
        doc = fitz.open()
        pg = doc.new_page()
        w = fitz.Widget()
        w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
        w.field_name = "b"
        w.rect = fitz.Rect(90, 186, 99, 195)
        w.field_value = False
        pg.add_widget(w)
        pg.insert_text((109.7, 196), "an unincorporated entity", fontsize=9, fontname="helv")
        pg.insert_text((109.7, 196), " " * 40 + "(describe):", fontsize=9, fontname="helv")
        text = P._form_page_text(pg)
        line = next(l for l in text.splitlines() if "entity" in l)
        assert line.index("an unincorporated entity") < line.index("(describe):"), line

    def test_the_padding_width_is_the_font_space(self):
        # Forty 9 pt spaces at 0.278 em: the delivered span opened at 109.7
        # and its "(" stood at 209.8.
        assert P._form_text_x(109.7, " " * 40 + "(describe):", 9.0) == pytest.approx(209.8, abs=1.0)
        assert P._form_text_x(50.0, "plain", 9.0) == 50.0
