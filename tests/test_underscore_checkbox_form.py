"""A printed checkbox is not always a SQUARE, and a form id is not always the
Judicial Council's.

A local LASC order form rules its boxes as a run of UNDERSCORES and prints the
check on top of them:

    __ with prejudice as to        ✔ without prejudice as to
    ✔ entire action                __ complaint only

Nothing in that page's line art is square, and its footer carries "LACIV 140" —
a LASC LOCAL form number, which `_JC_FORM_NO_RE` does not match. So both arms of
the ink gate declined, the page fell through to plain extraction, and an Order of
Dismissal exported with every box reading "__".

On that form the checkbox IS the ruling. The export could not say whether the
dismissal was with or without prejudice, or whether it reached the entire action
— while reading like a complete document. The filled values landed in an
unanchored heap at the end for the same reason.

The marks were readable the whole time: three ZapfDingbats glyphs, each sitting
ON the underscores of the caption it checks. What was missing was a gate that let
the page in, and a slot the mark could be matched to — the ordinary probe window
looks LEFT of a caption, and this mark sits a point or two INSIDE it.

Run:  cd PDF-Linker && python3 -m pytest tests/test_underscore_checkbox_form.py -v
"""
import pytest

import pdf_linker as P

fitz = pytest.importorskip("fitz")

CAPTIONS = [
    ("__ pursuant to the provisions of section ____________", True),
    ("__ pursuant to Local Policy and / or Local Rules,", False),
    ("__ with prejudice as to", False),
    ("__ entire action", True),
    ("__ complaint only", False),
    ("__ other _____________________________________", False),
]
CHECK = "\x14"          # the ZapfDingbats check a flattened form keeps


def _page(marks=True, footer="LACIV 140 (Rev. XX/XX)"):
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    y = 200
    for text, checked in CAPTIONS:
        pg.insert_text((42, y), text, fontsize=12)
        if checked and marks:
            pg.insert_text((45, y), CHECK, fontsize=12, fontname="zadb")
        y += 21
    # The signature rule: a long underscore run that also OPENS its span.
    pg.insert_text((295, y + 40), "_" * 39, fontsize=12)
    pg.insert_text((403, y + 60), "Judicial Officer", fontsize=12)
    pg.insert_text((60, 740), footer, fontsize=8)
    return doc[0]


def _text(page):
    return P._form_page_text(page) or ""


# ── the page is admitted, and the ruling is readable ────────────────────────

def test_the_page_reaches_the_form_path_at_all():
    assert P._form_page_text(_page()) is not None


def test_every_box_reports_its_state():
    body = _text(_page())
    assert "[X] pursuant to the provisions of section" in body, body
    assert "[ ] pursuant to Local Policy" in body, body
    assert "[ ] with prejudice as to" in body, body
    assert "[X] entire action" in body, body
    assert "[ ] complaint only" in body, body


def test_the_underscores_are_replaced_not_repeated():
    """The leading underscores ARE the box; leaving them would read
    "[X] __ entire action"."""
    body = _text(_page())
    assert "__ entire action" not in body, body
    assert "[X] __" not in body, body


def test_an_unmarked_form_reports_every_box_empty():
    body = _text(_page(marks=False))
    assert "[X]" not in body, body
    assert body.count("[ ]") == len(CAPTIONS), body


def test_the_banner_tallies_the_boxes():
    banner = _text(_page()).split("\n", 1)[0]
    assert "6 box(es)" in banner, banner
    assert "2 marked" in banner, banner


# ── and nothing else is mistaken for a checkbox ─────────────────────────────

def test_a_signature_rule_is_not_a_checkbox():
    """A long underscore run opens its span too, and reading one as a box put a
    phantom "[ ]" beside the date. A printed checkbox is two or three
    underscores wide; a blank ruled for a human to write on is not."""
    body = _text(_page())
    assert "_" * 39 in body, body
    assert body.count("[ ]") + body.count("[X]") == len(CAPTIONS), body


@pytest.mark.parametrize("run,is_box", [
    ("__ entire action", True),
    ("___ entire action", True),
    ("____ entire action", True),
    ("_____ entire action", False),      # five is a rule, not a box
    ("_ entire action", False),          # one is not a box
    ("__entire action", False),          # must be followed by a space
    ("the __ entire action", False),     # must OPEN the span
    ("of section _______", False),       # a trailing fill-in rule
])
def test_only_a_short_leading_run_is_a_checkbox(run, is_box):
    sp = {"text": run, "bbox": (42.0, 200.0, 300.0, 214.0)}
    assert (P._ink_underscore_slot(sp) is not None) is is_box


def test_an_ordinary_filing_is_not_read_as_a_form():
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    y = 100
    for line in ["MEMORANDUM OF POINTS AND AUTHORITIES",
                 "Plaintiff moves to compel further responses.",
                 "The motion is timely under Code of Civil Procedure section",
                 "2030.300, and no further meet and confer is required."]:
        pg.insert_text((72, y), line, fontsize=12)
        y += 20
    assert P._ink_underscore_count(doc[0]) == 0
    assert P._form_page_text(doc[0]) is None
