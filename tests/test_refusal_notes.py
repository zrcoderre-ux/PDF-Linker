"""A refused decision says WHY on its own worksheet row.

`--fix-leaks` refuses to mint a `yes` whose value the documents write in lower
case (vocabulary, not a name) or that is a lone all-caps token of four letters
or fewer, and it refuses a typed replacement identical to the value. The reason
was a log line and nothing else, so the operator — who reads `LEAKS.xlsx` and
not `pdf_linker.log` — marked three rows yes, clicked Apply Leak Fixes, and got
the same three rows back with nothing on them saying why.

Run:  cd PDF-Linker && python3 -m pytest tests/test_refusal_notes.py -v
"""
import logging

import openpyxl

import pdf_linker as P

log = logging.getLogger("test")

ENTRY = {"file": "Decl.txt", "type": "narrative name?", "value": "NAN",
         "where": "p.1:3", "context": "the Agreement as NAN alleged supra."}
SCREEN = "it is a lone all-caps token of four letters or fewer"
WHY = P._PN_REFUSED_VOCAB.format(why=SCREEN)


def _rows(folder):
    wb = openpyxl.load_workbook(folder / "LEAKS.xlsx")
    ws = wb[P._PN_LEAK_SHEET]
    head = [str(h).strip()
            for h in next(ws.iter_rows(max_row=1, values_only=True))]
    v = head.index("Value")
    return {r[v]: dict(zip(head, r))
            for r in ws.iter_rows(min_row=2, values_only=True)}


def _write(folder, decisions=None, refusals=None):
    P._pn_write_leak_report(folder, [dict(ENTRY)], log, decisions=decisions,
                            refusals=refusals)
    return _rows(folder)


def _decision(value, **kw):
    d = {"value": value, "fix": "yes", "fixcell": "yes", "notes": ""}
    d.update(kw)
    return {value.lower(): d}


class TestTheReasonReachesTheRow:
    def test_the_notes_cell_says_why_and_what_to_type(self, tmp_path):
        rows = _write(tmp_path, _decision("NAN"), {"nan": WHY})
        notes = str(rows["NAN"]["Notes"])
        assert notes.startswith(P._PN_REFUSED_NOTE_LEAD)
        assert SCREEN in notes                # why
        assert "~CANONICAL" in notes          # ...and what to type instead

    def test_a_row_with_no_refusal_gains_nothing(self, tmp_path):
        rows = _write(tmp_path, _decision("NAN"), {})
        assert not str(rows["NAN"]["Notes"] or "").strip()

    def test_the_operators_own_note_survives(self, tmp_path):
        rows = _write(tmp_path, _decision("NAN", notes="ask Zach"),
                      {"nan": WHY})
        notes = str(rows["NAN"]["Notes"])
        assert notes.startswith("ask Zach")
        assert P._PN_REFUSED_NOTE_LEAD in notes


class TestAStaleRefusalIsReplacedNeverStacked:
    def test_a_second_refusal_does_not_duplicate(self, tmp_path):
        carried = P._PN_REFUSED_NOTE.format(why=WHY)
        rows = _write(tmp_path, _decision("NAN", notes=carried), {"nan": WHY})
        assert str(rows["NAN"]["Notes"]).count(P._PN_REFUSED_NOTE_LEAD) == 1

    def test_a_pass_that_refuses_nothing_clears_it(self, tmp_path):
        # The note describes what the LAST pass did. A full run screens no
        # `yes` at all, so leaving it would be one pass's verdict standing
        # beside a folder that has been re-run since.
        carried = "ask Zach | " + P._PN_REFUSED_NOTE.format(why=WHY)
        rows = _write(tmp_path, _decision("NAN", notes=carried), None)
        notes = str(rows["NAN"]["Notes"])
        assert notes == "ask Zach"

    def test_the_reason_can_change(self, tmp_path):
        carried = P._PN_REFUSED_NOTE.format(why=WHY)
        rows = _write(tmp_path, _decision("NAN", notes=carried),
                      {"nan": P._PN_REFUSED_SELF_MAP})
        notes = str(rows["NAN"]["Notes"])
        assert notes.count(P._PN_REFUSED_NOTE_LEAD) == 1
        assert "equals the value itself" in notes
        assert "four letters" not in notes


class TestTheSegmentSplitter:
    def test_it_drops_only_the_refusal(self):
        n = "ask Zach | not applied: because | cited authority: X v. Y (2020)"
        assert P._pn_notes_drop_refusal(n) == (
            "ask Zach | cited authority: X v. Y (2020)")

    def test_an_empty_or_clean_note_is_unchanged(self):
        assert P._pn_notes_drop_refusal("") == ""
        assert P._pn_notes_drop_refusal(None) == ""
        assert P._pn_notes_drop_refusal("ask Zach") == "ask Zach"


class TestPatchingTheSheetInPlace:
    """When NOTHING applied, the pass leaves the folder untouched and returns
    before the report exists — which is exactly when every row the operator
    answered was refused and the sheet comes back byte-identical."""

    def test_it_writes_the_note_without_touching_anything_else(self, tmp_path):
        _write(tmp_path, _decision("NAN"), None)
        before = _rows(tmp_path)["NAN"]
        assert P._pn_note_refusals(tmp_path, {"nan": WHY}, log) is True
        after = _rows(tmp_path)["NAN"]
        assert SCREEN in str(after["Notes"])
        for col, was in before.items():
            if col != "Notes":
                assert after[col] == was, col

    def test_it_is_idempotent(self, tmp_path):
        _write(tmp_path, _decision("NAN"), None)
        P._pn_note_refusals(tmp_path, {"nan": WHY}, log)
        # Nothing left to change, so nothing is rewritten.
        assert P._pn_note_refusals(tmp_path, {"nan": WHY}, log) is False
        assert str(_rows(tmp_path)["NAN"]["Notes"]).count(
            P._PN_REFUSED_NOTE_LEAD) == 1

    def test_no_worksheet_and_no_refusals_are_both_no_ops(self, tmp_path):
        assert P._pn_note_refusals(tmp_path, {"nan": WHY}, log) is False
        _write(tmp_path, _decision("NAN"), None)
        assert P._pn_note_refusals(tmp_path, {}, log) is False

    def test_the_next_pass_still_reads_the_decision(self, tmp_path):
        _write(tmp_path, _decision("NAN"), None)
        P._pn_note_refusals(tmp_path, {"nan": WHY}, log)
        d = P._pn_read_leak_decisions(tmp_path)["nan"]
        assert d["fix"] == "yes"
        assert SCREEN in str(d["notes"])


# ── end to end through --fix-leaks ──────────────────────────────────────────

import types

_KEY_HDR = ["Category", "Real Value", "Replacement", "Status", "Source",
            "Occurrences"]


def _setup(folder, body, leak_rows):
    tdir = folder / "Text Files"
    tdir.mkdir()
    (tdir / "Motion.txt.LEAK").write_text(f"====== Page 1 ======\n{body}\n",
                                          encoding="utf-8")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Pseudonym Key"
    ws.append(_KEY_HDR)
    ws.append(["person-token", "Penuela", "Sable", "replaced", "regex", 3])
    wb.save(folder / "pseudonym_key.xlsx")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "LEAKS"
    ws.append(["File", "Type", "Value", "Where (page:line)", "Fix? (yes/no)",
               "Notes"])
    for val, fix in leak_rows:
        ws.append(["Motion.txt.LEAK", "LEAK", val, "p.1", fix, ""])
    wb.save(folder / "LEAKS.xlsx")
    return tdir


def _args(folder):
    return types.SimpleNamespace(term=[],
                                 key=str(folder / "pseudonym_key.xlsx"))


class TestThroughTheRealPass:
    def test_the_row_the_operator_marked_yes_comes_back_saying_why(
            self, tmp_path):
        # Every `yes` refused, so nothing applies and the pass returns leaving
        # the folder held — the case where the sheet is otherwise identical to
        # the one just filled in.
        _setup(tmp_path, "the Agreement as NAN alleged supra.", [("NAN", "yes")])
        assert P._fix_leaks_mode(tmp_path, _args(tmp_path), {}, log) == 0
        notes = str(_rows(tmp_path)["NAN"]["Notes"])
        assert P._PN_REFUSED_NOTE_LEAD in notes
        assert "four letters or fewer" in notes
        assert "~CANONICAL" in notes

    def test_and_the_decision_the_operator_typed_is_untouched(self, tmp_path):
        _setup(tmp_path, "the Agreement as NAN alleged supra.", [("NAN", "yes")])
        P._fix_leaks_mode(tmp_path, _args(tmp_path), {}, log)
        assert P._pn_read_leak_decisions(tmp_path)["nan"]["fix"] == "yes"

    def test_a_row_that_applies_leaves_no_note_on_its_neighbour(self, tmp_path):
        # One row applies, so the pass runs through and REWRITES the sheet;
        # the refused row still carries its reason there.
        _setup(tmp_path, "NAN says Melissa Sable signed for Ardmore Quarry.",
               [("NAN", "yes"), ("Ardmore Quarry", "yes")])
        P._fix_leaks_mode(tmp_path, _args(tmp_path), {}, log)
        rows = _rows(tmp_path)
        assert P._PN_REFUSED_NOTE_LEAD in str(rows["NAN"]["Notes"])
        assert "Ardmore Quarry" not in rows      # it applied, so its row goes
