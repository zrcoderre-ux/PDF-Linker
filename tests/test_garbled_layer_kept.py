"""
A REBUILT page says so, and its old text layer is kept where it is free to keep.

`_reocr_garbled_pages` redacts a page's text and overlays 300-dpi guesses. Two
things were missing afterwards:

  * the export never said which page that was. The rebuilt text sat in the
    middle of an accurately-extracted document reading exactly like the rest of
    it — which is how a reporter volume shipped as "A Cal. App. 4th 857" with
    nothing flagging it. Same reasoning as the low-dpi banner and the ink-form
    one: an inferred reading is never presented as equal to a read one.
  * the OLD layer was thrown away. A broken ToUnicode is usually a substitution
    cipher — glyphs in the right order, so word lengths, spacing, digits and
    punctuation are the document's own and only the letters come out wrong — so
    it can settle an argument about what the rebuilt page says. Unmapped glyphs
    ("(cid:3)(cid:15)") can settle nothing and are not kept.

Where it goes is the whole safety question. Garbled text is precisely the shape
the whole-word patterns cannot match, so a copy in the shared export would be
real party names nothing can scrub. It goes into the unscrubbed do-not-share
copy — which carries the real names in plain text already — and nowhere else.

Run:  cd PDF-Linker && python3 -m pytest tests/test_garbled_layer_kept.py -v
"""
import logging
import sys
import types

import pytest

fitz = pytest.importorskip("fitz")

import pdf_linker as P

log = logging.getLogger("test")

PROSE = ("The plaintiff filed this motion to compel further responses to "
         "requests for production served on the defendant corporation and "
         "argues that the objections are without merit under the act. ") * 4
# A substitution cipher: real word lengths and punctuation, wrong letters.
CIPHER = ("Bpm xtiqvbqnn nqtml bpqa uwbqwv bw kwuxmt nczbpmz zmaxwvama bw "
          "zmycmaba nwz xzwlckbqwv amzeml wv bpm lmnmvlivb kwzxwzibqwv. ") * 3
CIDS = "(cid:3)(cid:15)(cid:11)(cid:7) " * 40


def _install(monkeypatch, overlay_text):
    """Stub the OCR stack so the rebuild produces exactly `overlay_text`."""
    d = fitz.open()
    pg = d.new_page(width=612, height=792)
    y = 60
    for chunk in [overlay_text[i:i + 90] for i in range(0, len(overlay_text), 90)]:
        pg.insert_text((50, y), chunk, fontsize=9)
        y += 12
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


# ─── what is worth keeping ───────────────────────────────────────────────────

def test_a_ciphered_layer_is_worth_keeping():
    assert P._garbled_keepable(CIPHER) == CIPHER


def test_unmapped_glyphs_are_not():
    # "(cid:3)(cid:15)" has no word length, no spacing, no digits — nothing a
    # reader could tie-break with, and a page of it is pure noise.
    assert P._garbled_keepable(CIDS) == ""


def test_symbol_soup_is_not():
    assert P._garbled_keepable("#$%^&*<>{}[]|~ " * 40) == ""


def test_a_cid_page_with_real_text_beside_it_is_kept():
    assert P._garbled_keepable(CIDS + CIPHER) != ""


# ─── the pass records the rebuild, and only when it happened ─────────────────

def test_a_rebuilt_page_is_recorded_with_its_old_text(monkeypatch):
    monkeypatch.setattr(P, "_text_looks_garbled", lambda t: "RECOVERED" not in t)
    _install(monkeypatch, "RECOVERED " + PROSE)
    d = _one_page(CIPHER)
    assert P._reocr_garbled_pages(d, log) == 1
    kept = getattr(d, P._REOCR_ATTR)
    assert set(kept) == {0}
    assert "Bpm xtiqvbqnn" in kept[0]        # the pre-rebuild layer, verbatim
    assert "RECOVERED" in d[0].get_text()    # …and the page really was replaced
    d.close()


def test_a_refused_rebuild_records_nothing(monkeypatch):
    # The page keeps its own text, so there is nothing to carry forward — and
    # the banner must not claim the page was rebuilt.
    monkeypatch.setattr(P, "_text_looks_garbled", lambda t: True)
    _install(monkeypatch, "%%%% ^^^^ &&&&")
    d = _one_page(PROSE)
    assert P._reocr_garbled_pages(d, log) == 0
    assert getattr(d, P._REOCR_ATTR, {}) == {}
    d.close()


# ─── the appendix, and where it may appear ───────────────────────────────────

def test_the_appendix_explains_itself_and_quotes_each_page():
    out = P._garbled_appendix({0: CIPHER, 4: "second " + CIPHER})
    assert "Original text layer of rebuilt page(s) 1, 5" in out
    assert "TIE-BREAKER" in out and "substitution cipher" in out
    assert "--- Page 1, as extracted before the rebuild ---" in out
    assert "--- Page 5, as extracted before the rebuild ---" in out
    assert "Bpm xtiqvbqnn" in out


def test_a_page_with_nothing_keepable_yields_no_appendix():
    assert P._garbled_appendix({0: ""}) == ""
    assert P._garbled_appendix({}) == ""


def _written(tmp_path, monkeypatch, doc, pz):
    src = tmp_path / "Motion.pdf"
    doc.save(src)
    with fitz.open(src) as reopened:
        # carry the run's record onto the doc the writer sees
        setattr(reopened, P._REOCR_ATTR, getattr(doc, P._REOCR_ATTR, {}))
        P._write_text_version(src, reopened, log, pseudonymizer=pz,
                              original_subdir="Original Text")
    return src


def test_the_banner_says_the_page_was_rebuilt(tmp_path):
    d = _one_page("Body of the motion, recognised from the page image.")
    setattr(d, P._REOCR_ATTR, {0: CIPHER})
    _written(tmp_path, None, d, None)
    body = (tmp_path / "Text Files" / "Motion.txt").read_text()
    assert "REBUILT by OCR" in body.split("\n", 1)[0]
    assert "GUESSES" in body.split("\n", 1)[0]
    d.close()


def test_an_ordinary_page_gets_no_banner(tmp_path):
    d = _one_page("Body of the motion, extracted from a sound text layer.")
    _written(tmp_path, None, d, None)
    body = (tmp_path / "Text Files" / "Motion.txt").read_text()
    assert "REBUILT" not in body
    d.close()


def test_the_old_layer_reaches_the_do_not_share_copy_only(tmp_path):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Ford Motor Company"], [], [], registry=reg)
    pz = P.Pseudonymizer(terms, {}, registry=reg)
    d = _one_page("Ford Motor Company opposes the motion to compel.")
    setattr(d, P._REOCR_ATTR, {0: CIPHER})
    _written(tmp_path, None, d, pz)

    export = (tmp_path / "Text Files" / next(
        p.name for p in (tmp_path / "Text Files").glob("*.txt"))).read_text()
    original = (tmp_path / "Original Text"
                / "Motion (Original).txt").read_text()

    # The shared export gets the WARNING and none of the garbled text: it is
    # unscrubbable by construction, so a copy there is real names nothing can
    # touch. The do-not-share copy — which carries the real names anyway — gets
    # the tie-breaker.
    assert "REBUILT by OCR" in export
    assert "Bpm xtiqvbqnn" not in export
    assert "Original text layer" not in export
    assert "Bpm xtiqvbqnn" in original
    assert original.rstrip().endswith(CIPHER.strip())    # at the end, as asked
    d.close()


def test_the_evidence_the_fix_pass_reads_carries_it_too(tmp_path):
    # `--fix-leaks` reads the in-folder copy when there is one and the TEMP
    # cache otherwise, so the two must say the same thing. As evidence the
    # appendix can only ADD words, and `_real_remainder` only removes a word
    # absent from the original — so it can keep a finding, never drop one.
    reg = P._PnFakeRegistry()
    pz = P.Pseudonymizer(P._pn_build_terms(["Ford Motor Company"], [], [],
                                           registry=reg), {}, registry=reg)
    d = _one_page("Ford Motor Company opposes the motion.")
    setattr(d, P._REOCR_ATTR, {0: CIPHER})
    src = _written(tmp_path, None, d, pz)
    # `note_original` keeps a reduced form, so ask it the question it answers
    assert pz._finding_is_in_original("xtiqvbqnn")
    cached = P._originals_cache_dir(tmp_path)
    if cached is not None and cached.is_dir():
        assert any("Bpm xtiqvbqnn" in p.read_text(encoding="utf-8",
                                                  errors="ignore")
                   for p in cached.glob("*.txt"))
    P._clear_originals_cache(tmp_path)
    d.close()
