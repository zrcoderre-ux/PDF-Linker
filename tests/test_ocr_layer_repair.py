"""A FILER's OCR layer is measured against this run's own reading, word by
word, and corrected where ours is confidently better.

A scanned exhibit routinely arrives with an OCR layer the filer's software
wrote, drawn invisibly over the page image. `_ocr_image_regions` rendered and
read every such page and then threw the reading away as "already covered" —
588 s of one run — while the layer it kept read `Chadwick-Cas tel lano` for the
Bates stamp on 52 pages and `PARry` for PARTY on every header, and this run's
own Tesseract read every one of them right off the same image.

No shape measure can pick between two readings, so this asks a different
question at each WORD: what did our engine read at that place, and how sure
was it? Validated against the page image on 102 disagreements, then on a
sample of the 1,094 replacements the rule makes over the whole exhibit. The
screens each close a case that was seen:

* our confidence at `_LAYER_FIX_CONF` — below it the engines were genuinely at
  odds (`XXIII` read as `Xxill` at 81, the LAYER right);
* the `I`/`l`/`|`/`1` fold — the one class our engine confuses (`ARTICLE I`
  read as `|` at 90);
* a fragment is joined only where the JOINED word is one the document uses
  whole — where our engine welded ("If the" -> "Ifthe") the join is nobody's
  word; and measured the other way ("every piece is vocabulary") a stamp's own
  pieces stand on fifty pages and the stamp was refused;
* matching is MUTUAL — one stamp piece paired with our whole word would have
  written `Chadwick-Cas tel Chadwick-Castellano`;
* ours never replaces a layer word it is a strict substring of —
  "policy.Participation" -> "policy." deletes a word the layer had.

Run:  cd PDF-Linker && python3 -m pytest tests/test_ocr_layer_repair.py -v
"""
import io
import logging
import sys
import types

import pytest

import pdf_linker as P

fitz = pytest.importorskip("fitz")
log = logging.getLogger("test")

IMG = fitz.Rect(36, 36, 576, 756)

# (y, [(x, text)]) — the filer's layer, one invisible span per word.
LAYER = [
    (100, [(100, "PARry"), (160, "PROPRIETARY")]),
    (140, [(100, "Chadwick-Cas"), (190, "tel"), (215, "lano"), (260, "000249")]),
    (180, [(100, "If"), (115, "the"), (140, "Employer")]),
    (220, [(100, "XXIII")]),
    (260, [(100, "ARTICLE"), (160, "I")]),
    (300, [(100, "modiff,"), (150, "amend")]),
    (340, [(100, "shallrecei")]),
    # the document's own vocabulary: the stamp whole, and "If the" as words
    (500, [(100, "Chadwick-Castellano"), (240, "000250")]),
    (520, [(100, "Chadwick-Castellano"), (240, "000251")]),
    (540, [(100, "Chadwick-Castellano"), (240, "000252")]),
    (560, [(100, "If"), (115, "the"), (140, "Employer")]),
    (580, [(100, "If"), (115, "the"), (140, "Employer")]),
    (600, [(100, "If"), (115, "the"), (140, "Employer")]),
]

# What THIS RUN reads at each place: (layer words it covers, text, conf).
OURS = [
    (["PARry"], "PARTY", 96), (["PROPRIETARY"], "PROPRIETARY", 96),
    (["Chadwick-Cas", "tel", "lano"], "Chadwick-Castellano", 91),
    (["000249"], "000249", 95),
    (["If", "the"], "Ifthe", 95), (["Employer"], "Employer", 96),
    (["XXIII"], "Xxill", 81),
    (["ARTICLE"], "ARTICLE", 96), (["I"], "|", 90),
    (["modiff,"], "modify,", 96), (["amend"], "amend", 96),
    (["shallrecei"], "shall", 96),
]


def _doc():
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 540, 720))
    pix.clear_with(255)
    pg.insert_image(IMG, pixmap=pix)
    for y, words in LAYER:
        for x, t in words:
            pg.insert_text((x, y), t, fontsize=12, fontname="helv",
                           render_mode=3)
    return doc


def _boxes(page):
    """{text: [bbox, ...]} of the layer's words, in the order they were laid."""
    out = {}
    for w in page.get_text("words"):
        out.setdefault(w[4], []).append(fitz.Rect(w[:4]))
    return out


def _stub(monkeypatch, page, ours=OURS):
    """Tesseract's `image_to_data` for `page`'s image: each of our words boxed
    over the layer words it covers, in the render's own pixels."""
    boxes = _boxes(page)
    used = {}
    dpi = P._ocr_base_dpi(page)
    sc = dpi / 72.0
    clip = fitz.Rect(IMG * page.rotation_matrix)
    d = {k: [] for k in ("text", "conf", "left", "top", "width", "height")}
    for covers, text, conf in ours:
        r = None
        for t in covers:
            i = used.get(t, 0)
            used[t] = i + 1
            b = boxes[t][i]
            r = b if r is None else r | b
        d["text"].append(text)
        d["conf"].append(conf)
        d["left"].append(int((r.x0 - clip.x0) * sc))
        d["top"].append(int((r.y0 - clip.y0) * sc))
        d["width"].append(int(r.width * sc))
        d["height"].append(int(r.height * sc))
    calls = {"data": 0, "pdf": 0}

    def _to_data(img, config=None, timeout=None, output_type=None):
        calls["data"] += 1
        assert config == P._OCR_CONFIG
        return d

    def _to_pdf(*a, **k):
        calls["pdf"] += 1
        raise AssertionError("a filer-OCR'd page is repaired, never overlaid")

    fake = types.ModuleType("pytesseract")
    fake.pytesseract = types.SimpleNamespace(tesseract_cmd=None)
    fake.Output = types.SimpleNamespace(DICT="dict")
    fake.image_to_data = _to_data
    fake.image_to_pdf_or_hocr = _to_pdf
    monkeypatch.setitem(sys.modules, "pytesseract", fake)
    pil = types.ModuleType("PIL")
    pil.Image = types.SimpleNamespace(open=lambda b: b)
    monkeypatch.setitem(sys.modules, "PIL", pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", pil.Image)
    monkeypatch.setattr(P, "_find_tesseract", lambda: "/usr/bin/tesseract")
    monkeypatch.setattr(P, "_tesseract_usable", lambda t, l: True)
    return calls


# ── the population ──────────────────────────────────────────────────────────

def test_an_invisible_layer_in_an_ordinary_font_is_a_filer_layer():
    """Read off the render mode, not the font name: this exhibit's layer is
    Helvetica, and `_page_text_is_ocr`'s GlyphLessFont test never saw it."""
    doc = _doc()
    assert P._page_layer_is_filer_ocr(doc[0])


def test_a_marginal_stamp_does_not_exclude_the_page():
    """A filed scan carries a visible e-filing stamp; requiring no visible
    type at all excluded every such page silently."""
    doc = _doc()
    doc[0].insert_text((100, 780), "Electronically Received 1/2/2026", fontsize=7)
    assert P._page_layer_is_filer_ocr(doc[0])


def test_a_page_of_typed_values_over_the_image_is_not():
    doc = _doc()
    for y in range(400, 700, 14):
        doc[0].insert_text((300, y), "typed value typed value typed value", fontsize=12)
    assert not P._page_layer_is_filer_ocr(doc[0])


def test_visible_type_over_the_layer_refuses_the_rewrite(monkeypatch):
    doc = _doc()
    doc[0].insert_text((100, 104), "over the layer", fontsize=12)   # on PARry's line
    _stub(monkeypatch, doc[0])
    P._ocr_image_regions(doc, log)
    assert "PARry" in doc[0].get_text("text")
    assert not getattr(doc, P._LAYER_FIX_ATTR, {})


def test_a_page_this_run_read_itself_is_not():
    """Same engine, same dpi: a second reading can add nothing."""
    doc = _doc()
    P._note_ocr_read_page(doc[0])
    assert not P._page_layer_is_filer_ocr(doc[0])


# ── the repair, end to end through the image pass ───────────────────────────

def test_the_layer_is_corrected_where_ours_is_confidently_better(monkeypatch):
    doc = _doc()
    calls = _stub(monkeypatch, doc[0])
    P._ocr_image_regions(doc, log)
    text = doc[0].get_text("text")
    assert calls["data"] == 1 and calls["pdf"] == 0
    assert "PARTY" in text and "PARry" not in text
    assert "modify," in text and "modiff" not in text


def test_a_fragmented_stamp_is_joined_to_the_word_the_document_uses(monkeypatch):
    doc = _doc()
    _stub(monkeypatch, doc[0])
    P._ocr_image_regions(doc, log)
    text = doc[0].get_text("text")
    assert "Chadwick-Castellano 000249" in " ".join(text.split())
    assert "Cas tel lano" not in text
    assert "tel" not in text.split()


def test_a_weld_of_ours_is_refused(monkeypatch):
    """"Ifthe" is nobody's word; the layer's "If the" stands."""
    doc = _doc()
    _stub(monkeypatch, doc[0])
    P._ocr_image_regions(doc, log)
    text = doc[0].get_text("text")
    assert "Ifthe" not in text
    assert text.count("If") >= 4


def test_an_unsure_reading_leaves_the_layer(monkeypatch):
    doc = _doc()
    _stub(monkeypatch, doc[0])
    P._ocr_image_regions(doc, log)
    assert "XXIII" in doc[0].get_text("text")


def test_the_I_l_bar_class_leaves_the_layer(monkeypatch):
    doc = _doc()
    _stub(monkeypatch, doc[0])
    P._ocr_image_regions(doc, log)
    text = doc[0].get_text("text")
    assert "ARTICLE I" in " ".join(text.split()) and "|" not in text


def test_ours_never_deletes_letters_the_layer_had(monkeypatch):
    doc = _doc()
    _stub(monkeypatch, doc[0])
    P._ocr_image_regions(doc, log)
    assert "shallrecei" in doc[0].get_text("text")


def test_nothing_else_moves_and_the_page_is_banner_marked(monkeypatch):
    doc = _doc()
    _stub(monkeypatch, doc[0])
    before = doc[0].get_text("words")
    P._ocr_image_regions(doc, log)
    after = doc[0].get_text("words")
    assert getattr(doc, P._LAYER_FIX_ATTR, {}).get(0) == 3
    assert getattr(doc, P._IMG_OCR_ATTR, {}).get(0) is None   # not an overlay
    # three words changed, two pieces folded away, every other word as it was
    assert len(after) == len(before) - 2
    for w in ("PROPRIETARY", "Employer", "amend", "000250", "000251"):
        assert w in {x[4] for x in after}


def test_a_stub_that_agrees_everywhere_changes_nothing(monkeypatch):
    doc = _doc()
    agree = [([t], t, 96) for _y, ws in LAYER for _x, t in ws]
    _stub(monkeypatch, doc[0], ours=agree)
    before = doc[0].get_text("text")
    P._ocr_image_regions(doc, log)
    assert doc[0].get_text("text") == before
    assert not getattr(doc, P._LAYER_FIX_ATTR, {})


# ── the rule on its own ─────────────────────────────────────────────────────

def _box(x, w=30, y=100):
    return (x, y, x + w, y + 10)


def test_one_piece_never_pairs_with_our_whole_word():
    """Mutual matching: our stamp covers three pieces, so no single piece is
    a one-to-one disagreement with it."""
    layer = [(_box(100, 40), "Cas"), (_box(145, 20), "tel"), (_box(170, 30), "lano")]
    ours = [((100, 100, 200, 110), "Castellano", 91)]
    repl, done = P._layer_fix_decisions(layer, ours, {"castellano": 5})
    assert repl == {0: "Castellano", 1: "", 2: ""}, repl
    repl, _d = P._layer_fix_decisions(layer, ours, {"castellano": 1})
    assert repl == {}                      # the joined word is nobody's


def test_a_fragment_joins_under_the_I_l_fold_where_the_word_is_the_documents():
    """"Cas teI lano" is the stamp with its l read as I; the joined word's own
    sixty-six pages settle the spelling. Without them, nothing."""
    layer = [(_box(100, 40), "Cas"), (_box(145, 20), "teI"), (_box(170, 30), "lano")]
    ours = [((100, 100, 200, 110), "Castellano", 91)]
    assert P._layer_fix_decisions(layer, ours, {"castellano": 5})[0] == \
        {0: "Castellano", 1: "", 2: ""}
    assert P._layer_fix_decisions(layer, ours, {})[0] == {}


def test_a_bang_is_a_scans_l_inside_a_fragment():
    """"Ca! tel lano" — the tall l read as "!" — joins where the word stands
    whole elsewhere; without that, nothing."""
    layer = [(_box(100, 40), "Ca!"), (_box(145, 20), "tel"), (_box(170, 30), "lano")]
    ours = [((100, 100, 200, 110), "Castellano", 91)]
    assert P._layer_fix_decisions(layer, ours, {"castellano": 5})[0] == \
        {0: "Castellano", 1: "", 2: ""}
    assert P._layer_fix_decisions(layer, ours, {})[0] == {}


def test_furniture_never_becomes_a_letter():
    """A dash in the layer, read as "e" at 96: the layer word has no letters
    to be wrong about."""
    layer = [(_box(100, 8), "-")]
    ours = [(_box(100, 8), "e", 96)]
    assert P._layer_fix_decisions(layer, ours, {"e": 9})[0] == {}


def test_an_alignment_artifact_is_left_alone():
    """A word of ours spanning two layer words that do NOT join to it."""
    layer = [(_box(100, 40), "Disciplinary"), (_box(145, 20), "or")]
    ours = [((100, 100, 165, 110), "Disciplinary or", 94)]
    assert P._layer_fix_decisions(layer, ours, {})[0] == {}


def test_a_welded_layer_word_is_split_where_our_pieces_are_words():
    layer = [(_box(100, 80), "MileageIncrements")]
    ours = [(_box(100, 35), "Mileage", 96), (_box(140, 40), "Increments", 95)]
    v = {"mileage": 4, "increments": 4}
    assert P._layer_fix_decisions(layer, ours, v)[0] == {0: "Mileage Increments"}
    v["mileageincrements"] = 3              # the layer's word IS a word here
    assert P._layer_fix_decisions(layer, ours, v)[0] == {}
