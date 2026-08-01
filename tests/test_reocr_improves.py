"""A destructive rebuild must PROVE it improved the page.

`_reocr_garbled_pages` redacts a page's real text and overlays 300-dpi guesses.
Until this gate it did so on a heuristic alone: `_text_looks_garbled` said the
old text was bad, and the new text was adopted sight unseen. Two ways that ends
badly, both real — the heuristic misjudges a page that was fine (a table of
authorities, a damages table; the ratio has been retuned three times for
exactly this), or the rebuild is itself junk (a page ground down to 72 dpi, an
image Tesseract cannot read). In both the run threw away the true text layer
and kept a worse one, with nothing downstream able to tell: the export reads as
prose and the source is gone.

Run:  cd PDF-Linker && python3 -m pytest tests/test_reocr_improves.py -v
"""
import logging
import sys
import types

import fitz
import pytest

import pdf_linker as P

log = logging.getLogger("test")

PROSE = ("The plaintiff filed this motion to compel further responses to "
         "requests for production served on the defendant corporation and "
         "argues that the objections are without merit under the act. ") * 4
SOUP = "#$%^&*<>{}[]|~ " * 80


def test_a_rebuild_that_is_still_garbled_is_refused():
    """It bought nothing, and the ORIGINAL is at least what the page says."""
    assert P._reocr_improves(SOUP, SOUP) is False


def test_a_good_rebuild_is_adopted():
    assert P._reocr_improves(SOUP, PROSE) is True


def test_a_rebuild_that_recovered_almost_nothing_is_refused():
    """A render or recognition that mostly failed — the page keeps its own
    text rather than a dozen words standing in for four hundred."""
    assert P._reocr_improves(PROSE, "Plaintiff filed") is False


def test_an_empty_rebuild_is_refused():
    assert P._reocr_improves(PROSE, "") is False
    assert P._reocr_improves(PROSE, "   \n  ") is False


def test_the_yield_floor_is_a_share_not_a_count():
    """A short page whose rebuild is short too is fine; the test is relative."""
    old, new = "alpha beta gamma delta", "alpha beta"
    assert P._reocr_improves(old, new) is True          # 2 of 4 == the floor
    assert P._reocr_improves(old, "alpha") is False     # 1 of 4


def test_a_page_that_had_no_words_at_all_can_only_gain():
    assert P._reocr_improves("", PROSE) is True
    assert P._reocr_improves("....", PROSE) is True


# ── end to end: the pass keeps the page's own text ──────────────────────────
def _install(monkeypatch, overlay_text):
    """Stub the OCR stack so the rebuild produces exactly `overlay_text`."""
    d = fitz.open()
    d.new_page(width=612, height=792).insert_text((72, 100), overlay_text)
    payload = d.tobytes()
    d.close()

    fake = types.ModuleType("pytesseract")
    fake.pytesseract = types.SimpleNamespace(tesseract_cmd=None)
    fake.image_to_pdf_or_hocr = lambda img, **k: payload
    monkeypatch.setitem(sys.modules, "pytesseract", fake)
    fake_pil = types.ModuleType("PIL")
    fake_image = types.ModuleType("PIL.Image")
    fake_image.open = lambda *a, **k: object()
    fake_pil.Image = fake_image
    monkeypatch.setitem(sys.modules, "PIL", fake_pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", fake_image)
    monkeypatch.setattr(P, "_find_tesseract", lambda: "tesseract")
    monkeypatch.setattr(P, "_tesseract_usable", lambda *a, **k: True)
    monkeypatch.setattr(P, "_OCR_WORKERS", 1)
    # Stand the SOUNDNESS precondition down. It spares a page carrying a real
    # font and thirty readable words — which a prose fixture is — so without
    # this the pass returns before the improvement gate is ever consulted and
    # every assertion below passes for the wrong reason.
    monkeypatch.setattr(P, "_page_text_layer_is_sound", lambda pg: False)


def _one_page(text):
    d = fitz.open()
    pg = d.new_page(width=612, height=792)
    y = 60
    for chunk in [text[i:i + 90] for i in range(0, len(text), 90)]:
        pg.insert_text((50, y), chunk, fontsize=9)
        y += 12
        if y > 760:
            break
    return d


def test_the_page_keeps_its_own_text_when_the_rebuild_is_junk(monkeypatch):
    """The whole point: a misjudged page is not destroyed."""
    monkeypatch.setattr(P, "_text_looks_garbled", lambda t: True)
    _install(monkeypatch, "%%%% ^^^^ &&&&")
    d = _one_page(PROSE)
    n = P._reocr_garbled_pages(d, log)
    assert n == 0                                   # nothing was rebuilt
    assert "plaintiff" in d[0].get_text().lower()   # the real text survived
    d.close()


def test_a_genuinely_better_rebuild_still_replaces_the_page(monkeypatch):
    """The gate must not turn the pass off — a broken page still gets fixed."""
    monkeypatch.setattr(P, "_text_looks_garbled",
                        lambda t: "RECOVERED" not in t)
    _install(monkeypatch, "RECOVERED PLAINTIFF MOTION TEXT")
    d = _one_page(SOUP)
    n = P._reocr_garbled_pages(d, log)
    assert n == 1
    assert "RECOVERED" in d[0].get_text()
    d.close()


def test_the_refusal_is_logged(monkeypatch):
    """A page kept against the heuristic's verdict is a decision, and a
    destructive pass that leaves no trace of its decisions is not diagnosable."""
    lines = []

    class _Log:
        def info(self, m):
            lines.append(str(m))
        warning = error = info

    monkeypatch.setattr(P, "_text_looks_garbled", lambda t: True)
    _install(monkeypatch, "%%%% ^^^^")
    d = _one_page(PROSE)
    P._reocr_garbled_pages(d, _Log())
    d.close()
    assert any("no better than the text already there" in ln for ln in lines)
