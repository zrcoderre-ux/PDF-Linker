"""The party template is filtered to THIS folder's docket.

An E-Court export is a calendar: a sheet listing several matters, or last
week's export for another matter still in Downloads. Read whole, it handed a
delivered key twenty-five real values from a stranger's case, pinned `no
match` on every re-run, and one of them faked a city in a letterhead. Where
the sheet names more than one matter, only the rows naming the docket this
folder's documents carry are taken; a multi-matter sheet naming none of them
is refused whole.

Run:  cd PDF-Linker && python3 -m pytest tests/test_template_filtered_by_docket.py -v
"""
import logging

import fitz
import openpyxl

import pdf_linker as P

log = logging.getLogger("test")
HEAD = ["Case Number", "Title Plaintiff", "Title Defendant", "Other Names"]
ROWS = [
    ["25STCV37838", "Helen Rasho", "Quillmark Builders LLC", "Marcus Delacroix"],
    ["24SMCV00456", "Westlake Flooring Company LLC", "Lemon Motors USA", "Dana Perez"],
]


def _book(tmp_path, rows=ROWS, name="Order export.xlsx"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEAD)
    for r in rows:
        ws.append(r)
    path = tmp_path / name
    wb.save(path)
    return path


def _pdf(folder, text, name="Complaint.pdf"):
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), text)
    doc.save(folder / name)
    doc.close()


def test_only_the_matching_matters_rows_are_taken(tmp_path):
    names, casenos = P._pn_terms_from_xlsx(_book(tmp_path), [], log,
                                           folder_casenos={"25STCV37838"})
    assert [n for n, _s in names] == ["Helen Rasho", "Quillmark Builders LLC",
                                      "Marcus Delacroix"]
    assert casenos == ["25STCV37838"]


def test_a_spaced_docket_still_matches(tmp_path):
    names, _c = P._pn_terms_from_xlsx(_book(tmp_path), [], log,
                                      folder_casenos={"25 STCV 37838"})
    assert "Westlake Flooring Company LLC" not in [n for n, _s in names]
    assert "Helen Rasho" in [n for n, _s in names]


def test_a_multi_matter_sheet_naming_none_of_ours_is_refused(tmp_path):
    names, casenos = P._pn_terms_from_xlsx(_book(tmp_path), [], log,
                                           folder_casenos={"23STLC00412"})
    assert names == [] and casenos == []


def test_a_single_matter_sheet_is_read_as_before(tmp_path):
    names, _c = P._pn_terms_from_xlsx(_book(tmp_path, rows=ROWS[:1]), [], log,
                                      folder_casenos={"23STLC00412"})
    assert "Helen Rasho" in [n for n, _s in names]


def test_with_no_docket_read_every_row_is_taken_and_warned(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        names, _c = P._pn_terms_from_xlsx(_book(tmp_path), [], log,
                                          folder_casenos=set())
    assert len(names) == 6
    assert "lists 2 matters" in caplog.text


def test_the_folders_docket_is_read_off_its_first_pages(tmp_path):
    _pdf(tmp_path, "SUPERIOR COURT OF CALIFORNIA\nCase No. 25STCV37838\n"
                   "HELEN RASHO, Plaintiff, v. QUILLMARK BUILDERS LLC")
    assert P._pn_folder_casenos(tmp_path, log) == {"25STCV37838"}


def test_a_foreign_entitys_token_never_touches_a_city(tmp_path):
    _pdf(tmp_path, "Case No. 25STCV37838\nHELEN RASHO, Plaintiff")
    names, casenos = P._pn_terms_from_xlsx(
        _book(tmp_path), [], log, folder_casenos=P._pn_folder_casenos(tmp_path, log))
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(names, casenos, [], registry=reg), {},
                        registry=reg)
    text = "Counsel's office is at 100 Westlake Village Blvd, Westlake Village, CA."
    assert z.apply(text) == text
