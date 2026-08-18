"""
Four OCR-side gates that misfired on exactly the pages they exist for.

* `_reocr_improves` counted every `(cid:NN)` token of the OLD layer as the
  word "cid", so a page of unmapped glyphs — the first page class
  `_text_looks_garbled` flags — measured ~one phantom word per glyph and a
  PERFECT rebuild could never clear the yield bar: the export kept its cid
  soup forever while paying for the render and OCR on every run. The old
  count now runs on the cid-stripped text, exactly as `_garbled_keepable`
  measures it.

* `_span_is_redraw_fragment` had no size check, so a big stamp or watermark
  span whose box covered body text swallowed any short word its text
  happened to contain — the article "A" under an "EXHIBIT A" stamp, the "I"
  that opens a declaration. A redraw fragment is a piece of the SAME printed
  line, so comparable glyph height is now required.

* `_image_ocr_new_words` counted duplicates, so one junk token repeated
  ("QQXZW QQXZW") cleared the two-new-words floor and a junk overlay was
  written into the PDF.

* `_table_keeps_every_word` compared the grid's ESCAPED text (`\\|`) against
  the page's raw text, so any table containing a literal pipe tokenized
  differently and the grid rendering was silently unavailable for that page.

Run:  cd PDF-Linker && python3 -m pytest tests/test_ocr_gate_fixes.py -v
"""
import pytest

import pdf_linker as P

fitz = pytest.importorskip("fitz")


# ── the re-OCR yield bar ignores cid soup ───────────────────────────────────

def test_a_clean_rebuild_beats_a_page_of_unmapped_glyphs():
    old = " ".join(f"(cid:{i % 90})" for i in range(1500))
    new = "The parties stipulate that the hearing is continued. " * 40
    assert P._text_looks_garbled(old)          # the page the pass exists for
    assert P._reocr_improves(old, new)


def test_a_substitution_cipher_still_needs_the_yield():
    # A broken ToUnicode preserves token counts, so a rebuild that lost half
    # the words is still refused — the cid strip must not loosen that bar.
    old = "xqzjw kvbnp qwrtz " * 200
    assert not P._reocr_improves(old, "only these few words came back")


# ── a stamp is not a redraw of the words beneath it ─────────────────────────

def test_a_short_word_under_a_stamp_survives():
    big = {"text": "EXHIBIT A", "bbox": (100, 100, 300, 180)}
    word = {"text": "A", "bbox": (150, 150, 158, 160)}
    assert not P._span_is_redraw_fragment(word, big)
    spans = [big, word,
             {"text": "I, JANE DOE, declare:", "bbox": (100, 152, 290, 162)}]
    kept = P._drop_redrawn_fragments(list(spans))
    assert word in kept


def test_a_true_word_by_word_redraw_is_still_dropped():
    big = {"text": "EDGECOMBE N. DENHOLM, ESQ.", "bbox": (72, 100, 300, 112)}
    piece = {"text": "EDGECOMBE", "bbox": (72, 100.4, 140, 111.8)}
    assert P._span_is_redraw_fragment(piece, big)


# ── the image-OCR floor counts DISTINCT words ───────────────────────────────

def test_one_repeated_junk_token_is_one_word():
    assert len(P._image_ocr_new_words("QQXZW QQXZW", set())) == 1
    assert len(P._image_ocr_new_words("Alison Mackenzie", set())) == 2


# ── a literal pipe does not disqualify a table ──────────────────────────────

def test_a_table_with_a_pipe_can_still_prove_itself():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "Qty|Rate 150")
    grid = "| " + P._table_cell("Qty|Rate") + " | " + P._table_cell("150") + " |"
    assert P._table_keeps_every_word(page, (60, 80, 400, 120), grid)
    doc.close()
