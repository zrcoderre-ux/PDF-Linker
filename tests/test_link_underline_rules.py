"""This tool's own hyperlink underline is not one of the page's RULES.

A citation link is drawn with a blue underline (`LINK_COLOUR`, at
`rect.y1 - 0.5` across the link's own rect), and the tool replaces the source
PDF — so on every run after the first, the page's line art carries one thin
horizontal stroke per linked citation. `_page_rules` read them as the page's
own rules and `_lay_rules` drew each as a `─` run on a line of its own, so a
brief came back with a rule line under every cite: lines the document does not
have, in text this tool put there itself.

Run:  cd PDF-Linker && python3 -m pytest tests/test_link_underline_rules.py -v
"""
import pytest

fitz = pytest.importorskip("fitz")

import pdf_linker as P


def _committed(doc):
    """Reopen through a save. PyMuPDF caches a page's link list, so
    `get_links()` is empty until the file round-trips — which is exactly the
    real case: the export is written before any linking, from a document
    opened off disk, so only a RE-RUN ever meets these underlines."""
    return fitz.open("pdf", doc.tobytes())


def _linked_page(uri="https://example.test/cite"):
    """A page with one linked citation, underlined the way the tool does it,
    and one rule of the document's own."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 200), "See Code Civ. Proc., section 372.", fontsize=11)
    rect = fitz.Rect(100, 190, 300, 203)
    page.insert_link({"kind": fitz.LINK_URI, "from": rect, "uri": uri})
    y = rect.y1 - 0.5
    page.draw_line(fitz.Point(rect.x0, y), fitz.Point(rect.x1, y),
                   color=P.LINK_COLOUR, width=1.0)
    # ...and a rule the DOCUMENT draws, which must survive.
    page.draw_line(fitz.Point(36, 400), fitz.Point(576, 400), width=0.8)
    out = _committed(doc)
    doc.close()
    return out, out[0], rect


def test_the_tools_own_link_underline_is_not_a_rule():
    doc, page, rect = _linked_page()
    try:
        vert, horiz = P._page_rules(page, min_len=P._FORM_RULE_MIN)
        assert not vert
        ys = [round(y, 1) for y, _a, _b in horiz]
        assert 400.0 in ys                      # the document's own rule
        assert round(rect.y1 - 0.5, 1) not in ys
        assert len(horiz) == 1
    finally:
        doc.close()


def test_it_is_not_drawn_into_the_export():
    """The reported symptom: a rule line under every hyperlinked citation."""
    doc, page, _rect = _linked_page()
    try:
        text = P._page_visual_text(page)
        assert text.count("─") > 0         # the document's rule is drawn
        rules = [ln for ln in text.splitlines() if set(ln.strip()) == {"─"}]
        assert len(rules) == 1                  # ...and only that one
    finally:
        doc.close()


def test_a_rule_the_page_draws_in_another_colour_under_a_link_survives():
    """Both conditions are load-bearing: a form's own rule may run under a
    link (a caption box's edge, a footer rule beneath a linked cite)."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    rect = fitz.Rect(100, 190, 300, 203)
    page.insert_link({"kind": fitz.LINK_URI, "from": rect,
                      "uri": "https://example.test/x"})
    y = rect.y1 - 0.5
    page.draw_line(fitz.Point(rect.x0, y), fitz.Point(rect.x1, y), width=0.8)
    doc, page = _committed(doc), None
    page = doc[0]
    try:
        _v, horiz = P._page_rules(page, min_len=P._FORM_RULE_MIN)
        assert [round(q, 1) for q, _a, _b in horiz] == [round(y, 1)]
    finally:
        doc.close()


def test_a_blue_rule_that_is_not_under_a_link_survives():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.draw_line(fitz.Point(36, 400), fitz.Point(576, 400),
                   color=P.LINK_COLOUR, width=1.0)
    try:
        _v, horiz = P._page_rules(page, min_len=P._FORM_RULE_MIN)
        assert [round(q, 1) for q, _a, _b in horiz] == [400.0]
    finally:
        doc.close()


def test_a_page_of_linked_cites_is_not_read_as_a_form_or_a_table():
    """A run of them reads as the section dividers a caption box is made of."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for i in range(8):
        top = 120 + i * 40
        rect = fitz.Rect(100, top, 400, top + 13)
        page.insert_text((72, top + 11), f"Smith v. Jones ({1990 + i}) 1 Cal.5th 1",
                         fontsize=11)
        page.insert_link({"kind": fitz.LINK_URI, "from": rect,
                          "uri": f"https://example.test/{i}"})
        y = rect.y1 - 0.5
        page.draw_line(fitz.Point(rect.x0, y), fitz.Point(rect.x1, y),
                       color=P.LINK_COLOUR, width=1.0)
    doc = _committed(doc)
    page = doc[0]
    try:
        assert P._page_rules(page, min_len=P._FORM_RULE_MIN) == ([], [])
        assert "─" not in P._page_visual_text(page)
    finally:
        doc.close()


def test_it_is_not_a_heading_cue_either():
    """The same underline reaches `_page_underline_strokes`, where underline
    counts like bold: a body row ending in a linked citation would read as a
    heading and mint a bookmark off a line the tool drew itself."""
    doc, page, rect = _linked_page()
    try:
        strokes = P._page_underline_strokes(page)
        ys = [round(y, 1) for _a, _b, y in strokes]
        assert 400.0 in ys                      # the document's own rule
        assert round(rect.y1 - 0.5, 1) not in ys
        assert not P._row_is_underlined(
            (100.0, 190.0, 300.0, 203.0), strokes)
    finally:
        doc.close()
