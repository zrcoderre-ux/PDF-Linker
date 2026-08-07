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
    # counted mentions would not be a list of authorities.
    got = _collect(("Motion.pdf", MOTION))
    cases = [k for k, v in got.items() if v["kind"] == "case"]
    assert cases == ["Donlen v. Ford Motor Co. (2013) 217 Cal.App.4th 138"]
    assert got[cases[0]]["count"] == 2          # the full cite and the supra


def test_one_entry_per_authority_across_documents():
    got = _collect(("Motion.pdf", MOTION), ("Opposition.pdf", OPPO))
    donlen = got["Donlen v. Ford Motor Co. (2013) 217 Cal.App.4th 138"]
    assert donlen["docs"] == ["Motion.pdf", "Opposition.pdf"]
    assert donlen["count"] == 3
    assert "Kremerman v. White (2021) 71 Cal.App.5th 358" in got


def test_the_file_lands_in_the_case_folder_not_the_exports(tmp_path):
    (tmp_path / "Text Files").mkdir()
    got = _collect(("Motion.pdf", MOTION), ("Opposition.pdf", OPPO))
    out = P._write_authorities_list(tmp_path, got, log)
    assert out == tmp_path / P._AUTHORITIES_FILE
    assert out.is_file()
    assert not (tmp_path / "Text Files" / P._AUTHORITIES_FILE).exists()
    assert not list((tmp_path / "Text Files").glob("*.txt"))


def test_it_groups_by_kind_and_names_the_citing_documents(tmp_path):
    got = _collect(("Motion.pdf", MOTION), ("Opposition.pdf", OPPO))
    body = P._write_authorities_list(tmp_path, got, log).read_text()
    assert "CASES (2)" in body, body
    assert "STATUTES AND CODES (1)" in body, body
    assert "RULES (1)" in body, body
    assert "Donlen v. Ford Motor Co. (2013) 217 Cal.App.4th 138" in body
    assert "cited 3 times in: Motion.pdf, Opposition.pdf" in body, body
    assert "cited 1 time in: Opposition.pdf" in body, body   # singular
    # It says plainly what it is NOT.
    assert "NOT a check" in body


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
