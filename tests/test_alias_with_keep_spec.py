"""`*CANONICAL` and a `{braced}`/`[bracketed]` keep-spec compose in one cell.

The two answer different halves of one finding and neither alone is enough. A
clipped OCR lead welded to the next word — "avidsaid", which is "David said"
with the D lost and the space gone — needs the WORD kept and the NAME folded:

  * `{said}` alone keeps the word and leaves the remainder "avid" to an
    ordinary pool draw, because the typo fold cannot reach it (`avid` is four
    letters, `_PN_NAME_FOLD_MIN` is 5) — the exact gap the alias exists to
    close. The party comes back under a second unrelated stand-in and reads as
    two people.
  * `*David` alone folds correctly and swallows "said" into the surname.

They never met because both decision readers are if/elif chains that test the
alias FIRST, and `{}` is not one of `_PN_ALIAS_FORMULA_CHARS` — so the whole
cell was taken as the canonical, the tool went looking for a Real Value named
"David {said}", found none, warned, and faked the value the ordinary way.

Keep-spec is read FIRST, which is also the order the two operate in: the spec
CUTS the value, and the alias derives the stand-in for what the cut leaves.

Run:  cd PDF-Linker && python3 -m pytest tests/test_alias_with_keep_spec.py -v
"""
import logging

import pytest

import pdf_linker as P

log = logging.getLogger("test")
VALUE = "avidsaid"


def _decide(cell, value=VALUE):
    rows = [["Value", "Fix? (yes/no)", "Type", "Notes"],
            [value, cell, "LEAK", ""]]
    return P._pn_parse_decision_rows(rows)[value.lower()]


# ── the parse ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("cell", ["*David {said}", "*David [said]",
                                  "=David {said}"])
def test_both_controls_in_one_cell_are_read_as_both(cell):
    d = _decide(cell)
    assert d["fix"] == "yes"
    assert d["alias"] == "David"          # the name to mirror
    assert d["fake_values"] == ["avid"]   # what the keep-spec left to fake
    assert d["replacement"] is None       # never a literal replacement
    assert d["fixcell"] == cell           # the operator's text, echoed back


@pytest.mark.parametrize("cell,alias,frags", [
    ("*David", "David", None),            # alias alone: the whole value
    ("{said}", None, ["avid"]),           # keep-spec alone: an ordinary draw
    ("no", None, None),
    ("yes", None, None),
])
def test_a_single_control_is_untouched(cell, alias, frags):
    d = _decide(cell)
    assert d["alias"] == alias and d["fake_values"] == frags


@pytest.mark.parametrize("cell", [
    "{notinthisvalue}",        # names text outside the value
    "*() {said}",              # not a value after the star
    "David {said}",            # no star: an ordinary keep-spec
])
def test_a_cell_that_is_not_both_falls_back(cell):
    """Every half-formed shape drops to the single-control branches, which
    report their own failures — the composition never swallows one."""
    d = _decide(cell)
    assert d["alias"] is None


def test_a_spec_covering_the_whole_value_is_a_KEEP_and_never_an_alias():
    """`*David {avidsaid}` leaves the alias nothing to mirror, so the keep is
    the decision. It must not fall to the plain alias branch, which would read
    the braces as part of the canonical's name and FAKE a value the operator
    had just said to keep entire."""
    d = _decide("*David {avidsaid}")
    assert d["fix"] == "no" and d["alias"] is None
    assert d["replacement"] is None


def test_the_alias_mirrors_the_FRAGMENT_and_not_the_whole_value():
    """The kept text is the document's own word and is part of nobody's name,
    so what the alias mirrors is what the cut left."""
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["David Thomas"], [], [], registry=reg)
    d = {VALUE: _decide("*David {said}")}
    _terms, values = P._pn_apply_aliases(d, terms, reg, log)
    assert values == ["avid"]             # not "avidsaid"


def test_the_fragment_takes_the_same_slip_as_the_real_value():
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["David Thomas"], [], [], registry=reg)
    david = next(str(t.fake) for t in terms if str(t.real) == "David")
    P._pn_apply_aliases({VALUE: _decide("*David {said}")}, terms, reg, log)
    avid = reg.tokens_for("nametok")["avid"]
    # "avid" is "David" one slip out; so is its stand-in from David's — one
    # person spelled two ways, and two DISTINCT rows for the macro to reverse
    # (a shared Replacement is what `DeAnonymize.bas` calls ambiguous).
    assert avid != david
    assert P._pn_osa_distance(avid.lower(), david.lower()) == 1


def test_the_weld_follow_still_fires_through_a_star():
    """The fragment butts straight against the kept text, so its whole-word
    term could not otherwise land — `_pn_bracket_welds` reads the pair off the
    cell and must not be confused by the alias mark."""
    assert P._pn_bracket_welds(VALUE, "*David {said}") == {"avid": "said"}


def test_it_is_still_a_KEEP_so_the_braced_word_reaches_the_master_sheet():
    assert P._pn_decision_is_keep(_decide("*David {said}")) is True
    assert P._pn_decision_nuclear_parts(_decide("*David {said}")) == ["said"]


def test_the_key_reads_the_cell_the_same_way_the_worksheet_does(tmp_path):
    """Both ends must answer one question identically — a Replacement cell and
    a Fix? cell carrying the same text mean the same thing."""
    import openpyxl
    reg = P._PnFakeRegistry()
    pz = P.Pseudonymizer(P._pn_build_terms(["David Thomas"], [], [],
                                           registry=reg), [], registry=reg)
    pz.apply("David Thomas signed.")
    kp = tmp_path / "pseudonym_key.xlsx"
    pz.write_key(kp, log)

    wb = openpyxl.load_workbook(kp)
    ws = wb[P._PN_KEY_MAIN_SHEET]
    hdr = [str(c.value or "").strip().lower() for c in ws[1]]
    row = [None] * len(hdr)
    row[hdr.index("category")] = "person"
    row[hdr.index("real value")] = VALUE
    row[hdr.index("replacement")] = "*David {said}"
    ws.append(row)
    wb.save(kp)

    _terms, key_decisions = P._pn_load_key(kp, P._PnFakeRegistry(), log)
    d = key_decisions[VALUE]
    assert d["alias"] == "David" and d["fake_values"] == ["avid"]
