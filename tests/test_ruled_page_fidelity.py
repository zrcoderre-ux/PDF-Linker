"""Every renderer draws the page's RULES and its EMPTY LINES, so the export
reads beside the PDF whatever kind of page it is (`_lay_rules`, shared by the
form, exhibit and pleading renderers; `_pleading_layout` / `_pleading_lines`
for pleading paper; `_page_visual_text` for an exhibit).

Run:  cd PDF-Linker && python3 -m pytest tests/test_ruled_page_fidelity.py -v
"""
import inspect
import logging

import pytest

fitz = pytest.importorskip("fitz")

import pdf_linker as P


def _rule_line(l):
    """A line that is nothing but line art: a rule run with its junctions."""
    t = l.strip()
    return bool(t) and P._FORM_HRULE in t and set(t) <= set(P._RULE_GLYPHS)
from test_ruled_table_rows import _separate_statement


def _pleading(tmp_path, margin_rules=True):
    """A pleading page: 28 gutter numbers, a ruled caption box with a
    divider, the paper's own margin rules, empty numbered lines between the
    caption and the body, and a body that stops at line 19."""
    doc = fitz.open()
    pg = doc.new_page()
    for i in range(1, 29):
        pg.insert_text((40, 90 + (i - 1) * 20), f"{i:>2}", fontsize=10)
    sh = pg.new_shape()
    if margin_rules:
        for x in (60, 63, 590):
            sh.draw_line(fitz.Point(x, 40), fitz.Point(x, 760))
    sh.draw_rect(fitz.Rect(75, 75, 570, 175))
    sh.draw_line(fitz.Point(370, 75), fitz.Point(370, 175))
    sh.finish(width=0.6)
    sh.commit()
    pg.insert_text((80, 90), "ROXANE ESTRADA, an individual,", fontsize=10)
    pg.insert_text((380, 90), "Case No.: 25STCV37838", fontsize=10)
    pg.insert_text((80, 110), "Plaintiff,", fontsize=10)
    pg.insert_text((380, 110), "Dept.: 55", fontsize=10)
    pg.insert_text((80, 130), "vs.", fontsize=10)
    pg.insert_text((380, 130), "Hearing Date: 9/9/2026", fontsize=10)
    pg.insert_text((80, 150), "ACME WIDGETS, INC.,", fontsize=10)
    pg.insert_text((80, 170), "Defendant.", fontsize=10)
    pg.insert_text((250, 230), "NOTICE OF MOTION", fontsize=10)
    for i in range(10, 20):
        pg.insert_text((80, 90 + (i - 1) * 20),
                       f"Body line {i} of the memorandum.", fontsize=10)
    path = tmp_path / "pleading.pdf"
    doc.save(path)
    doc.close()
    doc = fitz.open(path)
    assert P._write_text_version(path, doc, logging.getLogger("t"))
    return (tmp_path / "Text Files" / "pleading.txt").read_text("utf-8")


@pytest.fixture
def txt(tmp_path):
    return _pleading(tmp_path)


class TestPleadingPage:
    def test_an_empty_numbered_line_prints_as_its_bare_number(self, txt):
        lines = txt.splitlines()
        for n in (6, 7, 9, 20, 28):
            assert f"{n:>2}" in lines, (n, lines)
        # …in page order, between the rows that surround it
        assert lines.index(" 6") < lines.index(" 7") < lines.index(" 9")
        assert lines.index(" 9") < next(i for i, l in enumerate(lines)
                                        if "Body line 10" in l)

    def test_the_caption_divider_is_a_bar_at_one_column(self, txt):
        lines = [l for l in txt.splitlines()
                 if "ROXANE" in l or "Plaintiff," in l or "vs." in l
                 or "ACME" in l or "Defendant." in l]
        assert len(lines) == 5
        cols = {l.index(P._FORM_VRULE) for l in lines}
        assert len(cols) == 1, lines
        a = next(l for l in lines if "ROXANE" in l)
        assert a.index("ROXANE") < a.index(P._FORM_VRULE) < a.index("Case No.")

    def test_the_box_edges_are_rule_lines_with_no_number(self, txt):
        lines = txt.splitlines()
        rules = [i for i, l in enumerate(lines) if P._FORM_HRULE in l]
        assert len(rules) == 2, rules
        for i in rules:
            assert lines[i].startswith("    "), lines[i]   # unnumbered
            assert _rule_line(lines[i])
        assert rules[0] < next(i for i, l in enumerate(lines) if "ROXANE" in l)
        assert rules[1] > next(i for i, l in enumerate(lines) if "Defendant." in l)

    def test_the_papers_own_margin_rules_are_not_drawn(self, txt):
        # the body does not move, and no bar stands left of the party column
        assert "\n10  Body line 10 of the memorandum." in txt
        for l in txt.splitlines():
            if "Body line" in l:
                assert P._FORM_VRULE not in l, l
        a = next(l for l in txt.splitlines() if "ROXANE" in l)
        assert P._FORM_VRULE not in a[:a.index("ROXANE")]

    def test_a_page_without_line_art_draws_nothing(self, tmp_path):
        doc = fitz.open()
        pg = doc.new_page()
        for i in range(1, 29):
            pg.insert_text((40, 90 + (i - 1) * 20), f"{i:>2}", fontsize=10)
        for i in range(1, 10):
            pg.insert_text((80, 90 + (i - 1) * 20), f"Body line {i}.", fontsize=10)
        path = tmp_path / "plain.pdf"
        doc.save(path)
        doc.close()
        assert P._write_text_version(path, fitz.open(path), logging.getLogger("t"))
        out = (tmp_path / "Text Files" / "plain.txt").read_text("utf-8")
        assert P._FORM_HRULE not in out and P._FORM_VRULE not in out
        assert "\n 1  Body line 1." in out and "\n10\n11\n" in out

    def test_a_bare_number_is_a_location_and_never_prose(self, txt):
        parsed = P._pn_body_lines(txt)
        assert any(g == "7" and t == " 7" for _p, g, t in parsed)
        _lines, _low, joined, _ends, locs = P._pn_context_prep(parsed)
        assert " 6 7 " not in joined and "6 7 8" not in joined
        assert P._FORM_HRULE not in joined and P._FORM_VRULE not in joined
        # the quote still knows where the heading stood
        assert ("1", "8", parsed.index(next(
            r for r in parsed if "NOTICE OF MOTION" in r[2])) + 1) in locs

    def test_a_ruled_tables_rules_are_left_to_the_pipes(self, tmp_path):
        doc = _separate_statement()
        path = tmp_path / "ss.pdf"
        doc.save(path)
        doc.close()
        assert P._write_text_version(path, fitz.open(path), logging.getLogger("t"))
        out = (tmp_path / "Text Files" / "ss.txt").read_text("utf-8")
        assert "| --- |" in out
        assert P._FORM_HRULE not in out and P._FORM_VRULE not in out


class TestExhibitPage:
    def _page(self, rotate=0):
        doc = fitz.open()
        pg = doc.new_page()
        sh = pg.new_shape()
        sh.draw_rect(fitz.Rect(72, 72, 540, 160))
        sh.draw_line(fitz.Point(300, 72), fitz.Point(300, 160))
        sh.finish(width=0.6)
        sh.commit()
        pg.insert_text((80, 100), "Invoice No. 4471", fontsize=11)
        pg.insert_text((310, 100), "Date: 03/14/2024", fontsize=11)
        pg.insert_text((80, 130), "Bill to: Rosa Delgado", fontsize=11)
        pg.insert_text((310, 130), "Terms: Net 30", fontsize=11)
        pg.insert_text((72, 240), "Thank you for your business.", fontsize=11)
        if rotate:
            pg.set_rotation(rotate)
        pg._doc_ref = doc
        return pg

    def test_the_box_is_drawn_around_its_cells(self):
        lines = P._page_visual_text(self._page()).splitlines()
        rules = [i for i, l in enumerate(lines) if _rule_line(l)]
        assert len(rules) == 2, lines
        inside = lines[rules[0] + 1:rules[1]]
        assert len(inside) == 2 and all(l.count(P._FORM_VRULE) == 3 for l in inside), inside
        a, b = inside
        assert a.index("Invoice") < a.index("Date:")
        # the divider stands at one column on both lines, between the cells
        div = {l.rindex(P._FORM_VRULE, 0, l.rindex(P._FORM_VRULE)) for l in inside}
        assert len(div) == 1 and a.index("Invoice") < div.pop() < a.index("Date:")
        assert lines[-1].strip() == "Thank you for your business."

    def test_a_re_framed_page_draws_no_rules(self):
        text = P._page_visual_text(self._page(rotate=90))
        assert text and "Invoice No. 4471" in text
        assert P._FORM_HRULE not in text and P._FORM_VRULE not in text

    def test_a_page_without_line_art_is_unchanged(self):
        doc = fitz.open()
        pg = doc.new_page()
        pg.insert_text((72, 100), "Dear Sir,", fontsize=11)
        pg.insert_text((72, 130), "We write to confirm the terms.", fontsize=11)
        pg._doc_ref = doc
        text = P._page_visual_text(pg)
        assert text.splitlines() == ["Dear Sir,", "We write to confirm the terms."]


def test_the_three_renderers_read_one_rule_layout():
    """Pinned on the SOURCE: a renderer that stopped calling `_lay_rules`
    would be the start of two definitions of how a rule is drawn."""
    for fn in (P._form_layout, P._page_visual_text, P._pleading_lines):
        assert "_lay_rules(" in inspect.getsource(fn), fn.__name__


class TestJunctions:
    def test_a_box_meets_its_divider_with_corners_and_tees(self):
        lines = P._page_visual_text(TestExhibitPage()._page()).splitlines()
        top, bottom = [l for l in lines if _rule_line(l)]
        assert top.startswith("\u250c") and top.rstrip().endswith("\u2510")   # ┌ … ┐
        assert "\u252c" in top and "\u2534" in bottom                         # ┬ … ┴
        assert bottom.startswith("\u2514") and bottom.rstrip().endswith("\u2518")
        # the tee stands at the very column the bar takes on the text lines
        inside = [l for l in lines if l.count(P._FORM_VRULE) == 3]
        div = {l.rindex(P._FORM_VRULE, 0, l.rindex(P._FORM_VRULE)) for l in inside}
        assert div == {top.index("\u252c")} == {bottom.index("\u2534")}

    def test_a_rule_ending_at_a_divider_is_a_tee_not_a_gap(self, txt):
        lines = txt.splitlines()
        top, bottom = [l for l in lines if _rule_line(l)]
        a = next(l for l in lines if "ROXANE" in l)
        col = a.index(P._FORM_VRULE)
        assert top[col] == "\u252c" and bottom[col] == "\u2534"
        assert P._FORM_VRULE not in top and P._FORM_VRULE not in bottom

    def test_the_form_caption_box_is_drawn_whole(self):
        from test_form_render_fidelity import _boxed_form
        lines = P._form_page_text(_boxed_form()).splitlines()[1:]
        top = next(l for l in lines if _rule_line(l))
        assert top.strip()[0] == "\u250c" and top.strip()[-1] == "\u2510"
        assert top.count("\u252c") == 2, top          # the divider and the short edge


class TestBarRealignment:
    def test_a_longer_stand_in_takes_its_growth_from_the_padding(self):
        before = "\u2502 NAME: Rosa Delgado          \u2502 x \u2502"
        after = before.replace("Rosa Delgado", "Wilhelmina Featherstonehaugh"[:20])
        out = P._realign_rule_bars(before, after)
        assert [i for i, c in enumerate(out) if c == P._FORM_VRULE] == \
               [i for i, c in enumerate(before) if c == P._FORM_VRULE]
        assert "Wilhelmina" in out and out.count(" ") < before.count(" ")

    def test_a_shorter_stand_in_pads_back_out(self):
        before = "\u2502 NAME: Rosa Delgado   \u2502"
        after = before.replace("Rosa Delgado", "Ann Lee")
        out = P._realign_rule_bars(before, after)
        assert out.index(P._FORM_VRULE, 1) == before.index(P._FORM_VRULE, 1)

    def test_text_that_fills_the_cell_is_never_cut(self):
        before = "\u2502 EMAIL: a@b.com \u2502"
        after = before.replace("a@b.com", "averylongmailbox@postbox9.org")
        assert P._realign_rule_bars(before, after) == after

    def test_a_line_count_change_or_a_bar_count_change_is_left_alone(self):
        assert P._realign_rule_text("a\u2502b\nc", "a\u2502b") == "a\u2502b"
        assert P._realign_rule_bars("a \u2502 b", "a b") == "a b"

    def test_the_export_scrubs_a_form_and_keeps_the_bars_aligned(self, tmp_path):
        from test_form_render_fidelity import _boxed_form
        pg = _boxed_form()
        path = tmp_path / "form.pdf"
        pg._doc_ref.save(path)
        doc = fitz.open(path)
        reg = P._PnFakeRegistry()
        terms = P._pn_build_terms(["Rosa Delgado"], [], [], registry=reg)
        det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
        pz = P.Pseudonymizer(terms, det, registry=reg)
        assert P._write_text_version(path, doc, logging.getLogger("t"), pseudonymizer=pz)
        out = (tmp_path / "Text Files").glob("*.txt")
        text = next(out).read_text("utf-8")
        assert "Rosa Delgado" not in text
        inside = [l for l in text.splitlines() if l.count(P._FORM_VRULE) >= 3]
        cols = {tuple(i for i, c in enumerate(l) if c == P._FORM_VRULE)[-2:] for l in inside}
        assert len(cols) == 1, cols

    def test_a_cure_that_lands_after_the_layout_keeps_the_bars_aligned(
            self, tmp_path, monkeypatch):
        """The e-mail, weld and survivor cures rewrite the display text after
        `build_body` has laid the page out and realigned it, so a stand-in
        one of them lands pushed the bar after it — the EMAIL ADDRESS row of
        a delivered PLD-PI-001 sat five columns right of every other row.
        Realigned once more after the last cure, against the unscrubbed
        body."""
        from test_form_render_fidelity import _boxed_form
        pg = _boxed_form()
        path = tmp_path / "form.pdf"
        pg._doc_ref.save(path)
        doc = fitz.open(path)
        reg = P._PnFakeRegistry()
        terms = P._pn_build_terms(["Rosa Delgado"], [], [], registry=reg)
        det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
        pz = P.Pseudonymizer(terms, det, registry=reg)
        # A cure landing a LONGER stand-in on a caption-box row, after the
        # main pass and its realignment have both run.
        real = pz.scrub_survivors
        monkeypatch.setattr(pz, "scrub_survivors", lambda t: real(t).replace(
            "FOR COURT USE ONLY", "FOR COURT USE ONLY (CLERK STAMP HERE)"))
        assert P._write_text_version(path, doc, logging.getLogger("t"), pseudonymizer=pz)
        text = next((tmp_path / "Text Files").glob("*.txt")).read_text("utf-8")
        assert "CLERK STAMP HERE" in text                 # the cure landed
        inside = [l for l in text.splitlines() if l.count(P._FORM_VRULE) >= 3]
        cols = {tuple(i for i, c in enumerate(l) if c == P._FORM_VRULE)[-2:] for l in inside}
        assert len(cols) == 1, cols

    def test_the_realignment_follows_the_last_cure_on_both_writer_paths(self):
        """Pinned on the SOURCE: the realignment is worth nothing ahead of a
        pass that can still move the text, and the fix-leaks rewrite runs the
        same cures over an export of its own."""
        import inspect
        src = inspect.getsource(P._write_text_version)
        cure = src.index("_leak_mark(\"survivor cure\")")
        assert "_realign_rule_text(original, body)" in src[cure:]
        assert "scrub_" not in src[src.index("_realign_rule_text(original, body)"):
                                   src.index("surviving_reals(body)")]
        fix = inspect.getsource(P._fix_leaks_mode)
        i = fix.index("scrubbed = pz.scrub_survivors(scrubbed)")
        assert "_realign_rule_text(_NFKC(body), scrubbed)" in fix[i:i + 600]
