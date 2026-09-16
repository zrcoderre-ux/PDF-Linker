"""A SCANNED form carries its boxes as ink in the picture and its typed
values as visible text under an OCR layer — the two things a delivered
complaint showed: no boxes drawn at all, and every value written twice."""
import fitz
import pytest

import pdf_linker as P


def _scanned_form(width=1.0, dpi=200, ocr=None):
    """A PLD-PI-001-shaped page whose line art exists only in a page image:
    a caption box with a divider and a section rule, four checkboxes (the
    first marked), rendered to a picture, then typed labels and values as
    real text over it, plus `ocr` — [(x0, y0, x1, y1, text)] words to lay
    invisibly, the way an OCR pass does."""
    src = fitz.open()
    v = src.new_page(width=612, height=792)
    sh = v.new_shape()
    sh.draw_rect(fitz.Rect(36, 47, 576, 245))
    sh.draw_line(fitz.Point(396, 47), fitz.Point(396, 245))
    sh.draw_line(fitz.Point(36, 143), fitz.Point(396, 143))
    for k in range(4):
        sh.draw_rect(fitz.Rect(40, 262 + 20 * k, 50, 272 + 20 * k))
    sh.finish(width=width)
    sh.commit()
    v.insert_text((44, 270), "X", fontsize=9)
    pix = v.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    pg.insert_image(pg.rect, pixmap=pix)
    for k, cap in enumerate(("MOTOR VEHICLE", "OTHER", "Property Damage", "Wrongful Death")):
        pg.insert_text((56, 271 + 20 * k), cap, fontsize=9)
    pg.insert_text((41, 163), "STREET ADDRESS:", fontsize=7)
    pg.insert_text((99, 163), "111 North Hill Street", fontsize=9)
    pg.insert_text((400, 60), "FOR COURT USE ONLY", fontsize=7)
    pg.insert_text((40, 760), "PLD-PI-001 [Rev. January 1, 2024]", fontsize=6)
    for x0, y0, x1, y1, text in ocr or ():
        pg.insert_text((x0, y1 - 2), text, fontsize=9, render_mode=3)
    return pg


def _scanned_prose(dpi=200):
    src = fitz.open()
    v = src.new_page(width=612, height=792)
    y = 80
    for _ in range(12):
        v.insert_text((72, y), "The quick brown fox jumps over the lazy dog and keeps running.", fontsize=11)
        y += 14
    v.insert_text((72, y + 10), "UNDERLINED HEADING ABOVE A PARAGRAPH OF BOLD CAPS", fontsize=11)
    pix = v.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    pg.insert_image(pg.rect, pixmap=pix)
    return pg


def _near(rules, pos, tol=1.5):
    return any(abs(p - pos) <= tol for p, _a, _b in rules)


class TestRulesReadOffTheRaster:
    def test_a_scanned_page_draws_no_vector_rules(self):
        pg = _scanned_form()
        assert P._page_rules(pg, P._FORM_RULE_MIN) == ([], [])
        assert P._page_scan_image(pg)

    def test_the_boxes_edges_and_dividers_are_read_from_the_picture(self):
        vert, horiz = P._raster_rules(_scanned_form(), P._FORM_RULE_MIN)
        for x in (36, 396, 576):
            assert _near(vert, x), (x, vert)
        for y in (47, 143, 245):
            assert _near(horiz, y), (y, horiz)
        # the checkboxes are 10 pt: under the floor, so none is a rule
        assert not any(b - a < 15 for _p, a, b in vert + horiz), (vert, horiz)

    def test_a_scanned_page_of_prose_yields_no_rule(self):
        # A word's baseline is a thin dark band too; the letters standing on
        # it are what says it is not a rule.
        vert, horiz = P._raster_rules(_scanned_prose(), P._FORM_RULE_MIN)
        assert vert == [] and horiz == [], (vert, horiz)

    def test_a_page_that_draws_any_line_art_keeps_its_vector_rules(self):
        pg = _scanned_form()
        sh = pg.new_shape()
        sh.draw_line(fitz.Point(36, 500), fitz.Point(576, 500))
        sh.finish(width=0.6)
        sh.commit()
        vert, horiz = P._page_art_rules(pg, P._FORM_RULE_MIN)
        assert vert == [] and len(horiz) == 1 and abs(horiz[0][0] - 500) < 0.5

    def test_a_born_digital_page_never_pays_for_a_render(self, monkeypatch):
        doc = fitz.open()
        pg = doc.new_page(width=612, height=792)
        pg.insert_text((72, 100), "No picture here.", fontsize=11)
        monkeypatch.setattr(P, "_raster_rules", lambda *a, **k: pytest.fail("rendered"))
        assert P._page_art_rules(pg, P._FORM_RULE_MIN) == ([], [])

    def test_the_form_export_draws_the_scanned_box_and_reads_the_marks(self):
        txt = P._form_page_text(_scanned_form())
        assert txt is not None
        lines = txt.splitlines()
        assert any(ln.lstrip().startswith(P._RULE_GLYPHS[2]) for ln in lines), txt   # ┌
        assert any(P._FORM_VRULE in ln and "111 North Hill Street" in ln for ln in lines), txt
        assert "[X] MOTOR VEHICLE" in txt and "[ ] OTHER" in txt, txt

    def test_the_exhibit_renderer_draws_a_scanned_rule_too(self):
        src = fitz.open()
        v = src.new_page(width=612, height=792)
        v.insert_text((72, 100), "MEMORANDUM", fontsize=12)
        sh = v.new_shape()
        sh.draw_line(fitz.Point(72, 110), fitz.Point(540, 110))
        sh.finish(width=1.0)
        sh.commit()
        pix = v.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
        doc = fitz.open()
        pg = doc.new_page(width=612, height=792)
        pg.insert_image(pg.rect, pixmap=pix)
        pg.insert_text((72, 100), "MEMORANDUM", fontsize=12)
        pg.insert_text((72, 140), "To: the file", fontsize=11)
        txt = P._page_visual_text(pg)
        assert txt and P._FORM_HRULE * 10 in txt, txt


def _sp(x0, y0, x1, y1, text, font="TimesNewRomanPSMT"):
    return {"bbox": (x0, y0, x1, y1), "text": text, "font": font, "size": 10.0}


class TestAnOcrWordOverVisibleType:
    """Measured on a delivered scan: the typed value "111 North Hill Street"
    at [99.6, 154.8, 184.3, 165.9] under OCR words whose last, "Street",
    ran to 188.1 — past the run's edge by 3.8 pt — and sat 0.3 pt higher."""

    VALUE = _sp(99.6, 154.8, 184.3, 165.9, "111 North Hill Street")

    def test_the_last_word_overshooting_the_run_is_still_a_piece_of_it(self):
        words = [_sp(100.8, 155.1, 117.8, 163.8, "111", "GlyphLessFont"),
                 _sp(117.1, 155.1, 145.1, 163.8, "North", "GlyphLessFont"),
                 _sp(143.0, 155.1, 162.2, 163.7, "Hill", "GlyphLessFont"),
                 _sp(161.7, 155.1, 188.1, 163.7, "Street", "GlyphLessFont")]
        kept = P._drop_overdrawn_spans([self.VALUE] + words)
        assert [s["text"] for s in kept] == ["111 North Hill Street"]

    def test_the_same_overshoot_in_a_second_visible_layer_collapses_too(self):
        # Two visible layers that split the row differently: the overshoot
        # is the geometry's, not the invisible font's.
        words = [_sp(161.7, 155.1, 188.1, 163.7, "Street")]
        kept = P._drop_overdrawn_spans([self.VALUE] + words)
        assert [s["text"] for s in kept] == ["111 North Hill Street"]

    def test_the_next_word_on_the_line_is_never_a_piece(self):
        nxt = _sp(186.0, 154.8, 220.0, 165.9, "Suite", "GlyphLessFont")
        kept = P._drop_overdrawn_spans([self.VALUE, nxt])
        assert len(kept) == 2

    def test_an_invisible_misreading_over_the_type_is_dropped(self):
        typed = _sp(108.1, 130.8, 194.5, 141.9, "BERRINGTON BRAMBLE")
        misread = _sp(108.2, 128.6, 166.7, 137.3, "BERRIINGTON", "GlyphLessFont")
        rest = _sp(164.1, 128.8, 202.0, 137.4, "BRAMBLE", "GlyphLessFont")
        kept = P._drop_overdrawn_spans([typed, misread, rest])
        assert [s["text"] for s in kept] == ["BERRINGTON BRAMBLE"]

    def test_visible_type_inside_an_invisible_misreading_stays(self):
        # The other way round the invisible run is the reading and the type
        # the document: a visible word is dropped only by the text rule (its
        # text really is on the page in the run), never for being under an
        # OCR word that read it wrong.
        run = _sp(90, 130, 200, 142, "ATTORNEY FOR BERRIINGTON", "GlyphLessFont")
        typed = _sp(150, 131, 199, 141, "BERRINGTON")
        kept = P._drop_overdrawn_spans([run, typed])
        assert {s["text"] for s in kept} == {"ATTORNEY FOR BERRIINGTON", "BERRINGTON"}

    def test_an_invisible_word_beside_the_type_stays(self):
        label = _sp(66.5, 155.1, 100.0, 163.8, "ADDRESS:", "GlyphLessFont")
        kept = P._drop_overdrawn_spans([self.VALUE, label])
        assert len(kept) == 2

    def test_a_tall_invisible_word_over_small_type_stays(self):
        # A stamp-sized OCR word whose box happens to cover a small typed
        # word is not a reading of it: the height gate holds here too.
        typed = _sp(100, 300, 110, 308, "X")
        big = _sp(98, 280, 140, 320, "EXHIBIT", "GlyphLessFont")
        kept = P._drop_overdrawn_spans([typed, big])
        assert len(kept) == 2

    def test_two_invisible_layers_collapse_on_text_alone(self):
        run = _sp(99.6, 154.8, 184.3, 165.9, "111 North Hill Street", "GlyphLessFont")
        misread = _sp(161.7, 155.1, 188.1, 163.7, "Streel", "GlyphLessFont")
        kept = P._drop_overdrawn_spans([run, misread])
        assert len(kept) == 2
