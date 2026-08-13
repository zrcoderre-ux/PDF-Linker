"""The folder gets a list of what the PARTIES cited.

It lives in the CASE FOLDER, not in `Text Files`: that folder is the
deliverable, measured against an upload cap, and one more file there would cost
a document. This is a work product for whoever reads the papers, so it belongs
beside the PDFs and the key.

Real citation text, deliberately — published authorities are public record, and
the pipeline preserves them byte-for-byte precisely so a cite is never renamed.
A list that scrubbed the very names it exists to report would be useless.

Run:  cd PDF-Linker && python3 -m pytest tests/test_authorities_list.py -v
"""
import logging

import pdf_linker as P

log = logging.getLogger("test")

MOTION = ("Plaintiff relies on Donlen v. Ford Motor Co. (2013) 217 Cal.App.4th "
          "138, 145, and on Civil Code section 1750. See also Cal. Rules of "
          "Court, rule 3.1350. Donlen, supra, 217 Cal.App.4th at 146.")
OPPO = ("Defendant answers that Donlen v. Ford Motor Co. (2013) 217 "
        "Cal.App.4th 138 is distinguishable, and cites Kremerman v. White "
        "(2021) 71 Cal.App.5th 358.")


def _collect(*docs):
    got = {}
    for name, text in docs:
        for c in P.find_all_citations(text):
            P._note_authority(got, c, name)
    return got


def test_a_short_form_folds_onto_the_authority_it_repeats():
    # "Donlen, supra" is the same authority, not a second one. A list that
    # counted mentions would not be a list of authorities. The full cite and
    # the supra therefore leave ONE entry between them.
    got = _collect(("Motion.pdf", MOTION))
    cases = [k for k, v in got.items() if v["kind"] == "case"]
    assert cases == ["Donlen v. Ford Motor Co. (2013) 217 Cal.App.4th 138"]


def test_one_entry_per_authority_across_documents():
    got = _collect(("Motion.pdf", MOTION), ("Opposition.pdf", OPPO))
    donlen = got["Donlen v. Ford Motor Co. (2013) 217 Cal.App.4th 138"]
    # The documents are kept for the header's "across N document(s)".
    assert donlen["docs"] == ["Motion.pdf", "Opposition.pdf"]
    assert "Kremerman v. White (2021) 71 Cal.App.5th 358" in got


def test_no_mention_count_is_tracked():
    # The file no longer prints one, and a tally nothing reads is a number the
    # next reader would take on trust.
    got = _collect(("Motion.pdf", MOTION), ("Opposition.pdf", OPPO))
    assert all("count" not in rec for rec in got.values())


def test_the_file_lands_in_the_case_folder_not_the_exports(tmp_path):
    (tmp_path / "Text Files").mkdir()
    got = _collect(("Motion.pdf", MOTION), ("Opposition.pdf", OPPO))
    out = P._write_authorities_list(tmp_path, got, log)
    assert out == tmp_path / P._AUTHORITIES_FILE
    assert out.is_file()
    assert not (tmp_path / "Text Files" / P._AUTHORITIES_FILE).exists()
    assert not list((tmp_path / "Text Files").glob("*.txt"))


def test_it_groups_by_kind(tmp_path):
    got = _collect(("Motion.pdf", MOTION), ("Opposition.pdf", OPPO))
    body = P._write_authorities_list(tmp_path, got, log).read_text()
    assert "CASES (2)" in body, body
    assert "STATUTES AND CODES (1)" in body, body
    assert "RULES (1)" in body, body
    assert "Donlen v. Ford Motor Co. (2013) 217 Cal.App.4th 138" in body
    # It says plainly what it is NOT.
    assert "NOT a check" in body


def test_an_entry_is_the_citation_and_nothing_else(tmp_path):
    """No mention count and no citing documents under the entry.

    Both were dropped at the owner's direction: the file answers "what did the
    parties cite", and a count reads as a claim about how heavily an authority
    is relied on that the number does not support.
    """
    got = _collect(("Motion.pdf", MOTION), ("Opposition.pdf", OPPO))
    body = P._write_authorities_list(tmp_path, got, log).read_text()
    assert "cited" not in body.split("RULES")[0].split("CASES")[1], body
    assert "Motion.pdf" not in body, body
    assert "Opposition.pdf" not in body, body
    cases = [ln for ln in body.split("CASES (2)")[1].split("STATUTES")[0]
             .splitlines() if ln.strip()]
    assert cases == ["  Kremerman v. White (2021) 71 Cal.App.5th 358",
                     "  Donlen v. Ford Motor Co. (2013) 217 Cal.App.4th 138"], cases


def test_the_header_still_says_how_wide_the_batch_is(tmp_path):
    # Context for the list, not a claim about any authority in it.
    got = _collect(("Motion.pdf", MOTION), ("Opposition.pdf", OPPO))
    body = P._write_authorities_list(tmp_path, got, log).read_text()
    assert "4 authority(ies) cited across 2 document(s)" in body, body


# ── cases run in year order ─────────────────────────────────────────────────

YEARS = ("The court relied on Zeta v. Alpha (2019) 40 Cal.App.5th 1, on "
         "Alpha v. Zeta (1974) 11 Cal.3d 1, and on Mid v. Range (2003) 30 "
         "Cal.4th 1.")


def _case_lines(tmp_path, text):
    body = P._write_authorities_list(
        tmp_path, _collect(("Brief.pdf", text)), log).read_text()
    return [ln.strip() for ln in
            body.split("CASES")[1].splitlines()[2:] if ln.strip()]


def test_cases_are_sorted_by_year_most_recent_first(tmp_path):
    # Alphabetically this would be Alpha, Mid, Zeta — which says nothing, since
    # the first word of a case name is one party's surname.
    assert _case_lines(tmp_path, YEARS) == [
        "Zeta v. Alpha (2019) 40 Cal.App.5th 1",
        "Mid v. Range (2003) 30 Cal.4th 1",
        "Alpha v. Zeta (1974) 11 Cal.3d 1"]


def test_statutes_and_rules_keep_their_alphabetical_order(tmp_path):
    # They carry no year, and a code section IS read by its number.
    got = _collect(("Brief.pdf", "See Civil Code section 1750, Code of Civil "
                                 "Procedure section 128.7, and Civil Code "
                                 "section 51."))
    body = P._write_authorities_list(tmp_path, got, log).read_text()
    codes = [ln.strip() for ln in
             body.split("STATUTES AND CODES")[1].splitlines()[2:] if ln.strip()]
    assert codes == sorted(codes, key=str.lower), codes


def test_a_cite_with_no_year_sorts_last_not_as_year_zero(tmp_path):
    """Under a DESCENDING sort a year of zero is the newest, so an undated cite
    would head the list. The missing-year flag is what keeps it at the foot."""
    assert P._authority_year("Alpha v. Zeta (1974) 11 Cal.3d 1") == 1974
    assert P._authority_year("Alpha v. Zeta, 11 Cal.3d 1") is None
    got = _collect(("Brief.pdf", YEARS))
    got["Undated v. Nobody, 1 Cal.5th 1"] = {"kind": "case", "docs": [],
                                             "order": 9}
    lines = [ln.strip() for ln in
             P._write_authorities_list(tmp_path, got, log)
             .read_text().split("CASES")[1].splitlines()[2:] if ln.strip()]
    assert lines[-1] == "Undated v. Nobody, 1 Cal.5th 1", lines
    assert lines[0] == "Zeta v. Alpha (2019) 40 Cal.App.5th 1", lines


def test_the_citation_text_is_never_scrubbed(tmp_path):
    # The whole method preserves a cited authority byte-for-byte; this list
    # reports those names, so pseudonymizing it would defeat its purpose.
    got = _collect(("Motion.pdf", MOTION))
    body = P._write_authorities_list(tmp_path, got, log).read_text()
    assert "Ford Motor Co." in body
    assert "Cal. Rules of Court, rule 3.1350" in body


def test_a_folder_that_cites_nothing_gets_no_file(tmp_path):
    stale = tmp_path / P._AUTHORITIES_FILE
    stale.write_text("from a previous run", encoding="utf-8")
    assert P._write_authorities_list(tmp_path, {}, log) is None
    # Removed, not left describing a batch that has moved on.
    assert not stale.exists()


def test_it_is_rewritten_whole_on_every_run(tmp_path):
    first = _collect(("Motion.pdf", MOTION))
    P._write_authorities_list(tmp_path, first, log)
    second = _collect(("Opposition.pdf", OPPO))
    body = P._write_authorities_list(tmp_path, second, log).read_text()
    assert "Kremerman" in body
    assert "rule 3.1350" not in body, "a stale entry survived the rewrite"


def test_an_unchanged_folder_reproduces_the_file(tmp_path):
    got = _collect(("Motion.pdf", MOTION), ("Opposition.pdf", OPPO))
    one = P._write_authorities_list(tmp_path, got, log).read_text()
    two = P._write_authorities_list(
        tmp_path, _collect(("Motion.pdf", MOTION),
                           ("Opposition.pdf", OPPO)), log).read_text()
    assert one == two, "nothing volatile belongs in this file"
