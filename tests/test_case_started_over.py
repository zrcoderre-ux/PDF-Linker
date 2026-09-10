"""Starting a WORKED case over: say so, once, where a failure is read.

A case's decisions live in two places and only one survives a lost key.
`no`/`never`/`phrase`/`**` go to the cross-folder master KEEP sheet and come
back everywhere. `yes`, a typed replacement, a `~` alias and a `*` OCR fix are
CASE-LOCAL — what persists each one is the binding it minted, and that binding
lives in this folder's `pseudonym_key.xlsx` and nowhere else.

So a worked folder with no key to reuse discards every case-local answer before
the run starts, and used to say so with one INFO line ("using E-Court export")
among hundreds — indistinguishable from ordinary input discovery. The operator
found out by answering the same worksheet rows a second time.

Run:  cd PDF-Linker && python3 -m pytest tests/test_case_started_over.py -v
"""
import logging

import pytest

import pdf_linker as P

log = logging.getLogger("test")
EXPORTS = "Text Files"


@pytest.fixture
def said():
    """The warnings the run would surface, in order."""
    out = []
    return out, out.append


def _worked(folder, how):
    """Give `folder` the marks of an earlier run, one way or another."""
    if how == "worksheet":
        P._pn_leak_xlsx_path(folder).write_text("", encoding="utf-8")
    elif how == "exports":
        d = folder / EXPORTS
        d.mkdir()
        (d / "Motion.txt").write_text("body", encoding="utf-8")
    elif how == "done stamp":
        (folder / f"{P._DONE_MARKER_PREFIX} 5.12PM.txt").write_text(
            "", encoding="utf-8")


@pytest.mark.parametrize("how", ["worksheet", "exports", "done stamp"])
def test_a_worked_folder_with_no_key_is_warned_about(tmp_path, said, how):
    out, warn = said
    _worked(tmp_path, how)
    assert P._pn_warn_case_started_over(
        tmp_path, EXPORTS, tmp_path / "Order_Template_Input.xlsx", warn) is True
    assert len(out) == 1
    assert "STARTING THIS CASE OVER" in out[0]


def test_a_first_run_says_nothing(tmp_path, said):
    # Nothing has been processed here, so nothing is being discarded. A warning
    # on every fresh case would be noise, and noise is what buried the old line.
    out, warn = said
    (tmp_path / "Motion.pdf").write_text("not really a pdf", encoding="utf-8")
    assert P._pn_warn_case_started_over(
        tmp_path, EXPORTS, tmp_path / "Order.xlsx", warn) is False
    assert out == []


def test_an_empty_exports_folder_is_not_a_prior_run(tmp_path, said):
    # The folder is created before anything is written into it.
    out, warn = said
    (tmp_path / EXPORTS).mkdir()
    assert P._pn_warn_case_started_over(tmp_path, EXPORTS, None, warn) is False
    assert out == []


def test_the_configured_export_folder_is_the_one_checked(tmp_path, said):
    # `text_subfolder` is configurable; looking only in "Text Files" would miss
    # a prior run on any machine that renamed it.
    out, warn = said
    d = tmp_path / "Scrubbed"
    d.mkdir()
    (d / "Motion.txt").write_text("body", encoding="utf-8")
    assert P._pn_warn_case_started_over(tmp_path, "Scrubbed", None, warn) is True
    assert P._pn_folder_was_processed(tmp_path, EXPORTS) is False


def test_the_warning_names_what_is_lost_and_what_is_not(tmp_path, said):
    out, warn = said
    _worked(tmp_path, "worksheet")
    P._pn_warn_case_started_over(
        tmp_path, EXPORTS, tmp_path / "Order_Template_Input_26STCV19298.xlsx",
        warn)
    msg = out[0]
    # The case-local four, which are the ones that just died.
    for lost in ("Fix?=yes", "'~' alias", "'*' OCR fix", "typed replacement"):
        assert lost in msg
    # ...and the durable ones, so the operator does not re-answer those too.
    assert "no/never/phrase/**" in msg and "master KEEP" in msg
    # The likeliest cause, since it is not usually a deleted key.
    assert "second folder" in msg and "copy_to" in msg
    # Named, so the operator can see it faked against the wrong input.
    assert "Order_Template_Input_26STCV19298.xlsx" in msg
    assert tmp_path.name in msg


def test_an_unreadable_folder_never_costs_the_run(tmp_path, said):
    out, warn = said
    missing = tmp_path / "no-such-folder"
    assert P._pn_folder_was_processed(missing, EXPORTS) is False
    assert P._pn_warn_case_started_over(missing, EXPORTS, None, warn) is False
