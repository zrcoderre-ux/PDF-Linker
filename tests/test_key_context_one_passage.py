"""Both halves of a key row's Context cell come from ONE run, or neither does.

`note_key_context` mints the original quote, the export quote and the location
in a single statement, so the three can only describe one passage of one
document. `write_key` then took them apart again: each half asked its OWN
emptiness whether to fall back to the key already on disk, and the export half
is empty in a case the design calls honest — the row's fake does not stand in
the passage the original was quoted from (its occurrence there sat inside a
protected citation, or a cap-only token was met in lower case). So the cell
stacked THIS run's sentence over a sentence a PREVIOUS run had found the fake
in, in whatever document happened to carry it, with nothing saying the two were
not the same passage.

Run:  cd PDF-Linker && python3 -m pytest tests/test_key_context_one_passage.py -v
"""
import logging

import openpyxl
import pytest

import pdf_linker as P

log = logging.getLogger("test")


def _pz(names=("Roxane Estrada",)):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), [], [], registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    return P.Pseudonymizer(terms, det, registry=reg)


def _cells(path):
    """{real_lower: (Context, File, Where)} across both sheets."""
    wb = openpyxl.load_workbook(path)
    out = {}
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        hdr = [P._pn_norm_header(h) for h in rows[0]]
        rv = hdr.index("real value")
        cx = hdr.index("context")
        fx = hdr.index("file")
        wx = hdr.index(P._pn_norm_header(P._PN_KEY_WHERE_HEADER))
        for row in rows[1:]:
            if row[rv]:
                out[str(row[rv]).lower()] = (str(row[cx] or ""),
                                             str(row[fx] or ""),
                                             str(row[wx] or ""))
    wb.close()
    return out


def _halves(cell):
    return P._pn_context_split(cell)


# The first run: the party stands in a sentence, and the export carries the
# fake in that same sentence. Both halves, one passage.
RUN_ONE = ("====== Page 1 ======\n"
           " 1  The process server handed the summons to Roxane Estrada at\n"
           " 2  her residence in Van Nuys on the fourth of July.\n")


def _first_run(tmp_path):
    z = _pz()
    z.note_key_context(RUN_ONE, z.apply(RUN_ONE), "Proof of Service.pdf")
    key = tmp_path / "pseudonym_key.xlsx"
    z.write_key(key, log)
    return z, key


class TestTheCarryForwardIsAPair:
    def test_a_first_run_pairs_both_halves_from_one_passage(self, tmp_path):
        _z, key = _first_run(tmp_path)
        orig, export = _halves(_cells(key)["roxane estrada"][0])
        assert "process server handed the summons" in orig
        # Same sentence, with the stand-in in the party's place.
        assert "process server handed the summons" in export
        assert "Roxane Estrada" not in export

    def test_a_fresh_quote_with_no_export_half_shows_the_original_alone(
            self, tmp_path):
        """The reported failure, from the run that produces it.

        The second run quotes the value from a DIFFERENT document, and there
        the fake does not stand in that passage. The export half is empty and
        must stay empty: the key on disk holds a perfectly good export
        sentence, and it is a sentence of another document."""
        _z1, key = _first_run(tmp_path)
        before = _halves(_cells(key)["roxane estrada"][0])[1]
        assert before, "the first run must leave an export half to be stolen"

        z2 = _pz()
        # A fax exhibit: the party's name stands in a garbled line, and its
        # occurrence there was never replaced (a protected span, a cap-only
        # token met in lower case), so the fake stands nowhere in the passage.
        other = ("====== Page 1 ======\n"
                 " 1  Effective: T6022 1201AM Roxane Estrada 88hitieveiiaedd\n")
        # The export of that page is handed in unscrubbed — the shape the
        # design calls honest: the fake stands nowhere in this passage.
        z2.note_key_context(other, other, "Fax Cover.pdf")
        z2.write_key(key, log)

        cell, fname, where = _cells(key)["roxane estrada"]
        orig, export = _halves(cell)
        assert "T6022" in orig, "this run's own quote must win"
        assert export == "", (
            "the export half must not be carried forward under a quote from "
            f"another document; got {export!r}")
        assert fname == "Fax Cover.pdf"
        assert where

    def test_a_value_this_run_never_quoted_carries_all_three_forward(
            self, tmp_path):
        """The carry-forward still does its job: the key outlives the folder's
        contents, so a value no document in THIS run mentions keeps the
        sentence, the export sentence and the location the last run learned —
        together."""
        _z1, key = _first_run(tmp_path)
        was = _cells(key)["roxane estrada"]
        assert was[0] and was[1] and was[2]

        z2 = _pz()
        z2.note_key_context("====== Page 1 ======\n 1  Nothing relevant.\n",
                            "====== Page 1 ======\n 1  Nothing relevant.\n",
                            "Other.pdf")
        z2.write_key(key, log)
        assert _cells(key)["roxane estrada"] == was

    def test_the_three_cells_are_chosen_by_one_expression(self):
        """Pinned on the SOURCE, because the failure was three fallbacks that
        could disagree and a test of the output alone cannot see that a fourth
        would be added the same way."""
        import inspect
        body = inspect.getsource(P.Pseudonymizer.write_key)
        assert "def row_evidence(" in body
        for gone in ("def row_context(", "def row_context_scrubbed(",
                     "def row_where("):
            assert gone not in body, f"{gone} splits the pair again"
