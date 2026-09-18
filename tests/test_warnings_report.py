"""
`PDF-Linker Warnings.txt`: the run's own warnings, beside the log.

`pdf_linker.log` is the run narrating its own work — hundreds of INFO lines on
a real folder — and everything that wants the operator's attention is a WARNING
somewhere among them. The report is written from the records the run emitted,
describes the LAST run only, and is REMOVED by a run that warns about nothing,
so the file's existence is itself the answer to "did anything want looking at?".

Run:  cd PDF-Linker && python3 -m pytest tests/test_warnings_report.py -v
"""
import importlib.util
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pdf_linker", _ROOT / "pdf_linker.py")
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)

NAME = pl._WARNINGS_REPORT_FILE
W, E = logging.WARNING, logging.ERROR


def _report(folder):
    return (folder / NAME).read_text(encoding="utf-8")


def _entries(folder):
    """The message texts the report carries, read back the way the next run
    reads them."""
    return pl._read_warnings_report(folder / NAME)


# ── the file ─────────────────────────────────────────────────────────────────

def test_the_name_has_spaces_and_no_underscores():
    assert NAME == "PDF-Linker Warnings.txt"


def test_it_is_never_an_export(tmp_path):
    # Under the older single-folder layout the case folder's .txt files are
    # read as exports. This one is the tool's own and must never be scrubbed,
    # tracked or folded into a combined file.
    assert pl._is_tool_txt_artifact(tmp_path / NAME)
    assert not pl._is_tool_txt_artifact(tmp_path / "Brief.txt")


# ── what it says ─────────────────────────────────────────────────────────────

def test_a_run_that_warns_gets_a_report(tmp_path):
    pl._write_warnings_report(tmp_path, [
        (W, "REVIEW: Brief.pdf page 4 appears column-spliced"),
        (E, "Could not quarantine leaked export Brief.txt: denied"),
    ])
    text = _report(tmp_path)
    assert text.lstrip().startswith(pl._WARNINGS_REPORT_MARK)
    assert "column-spliced" in text and "Could not quarantine" in text
    # The severities are separated: an error is not one more warning.
    assert text.index("ERRORS") < text.index("WARNINGS")
    assert "1 error, 1 warning" in text


def test_a_repeat_is_one_entry_with_its_count(tmp_path):
    # One REVIEW banner per page of a 200-page exhibit set is ONE thing to look
    # at, not two hundred.
    pl._write_warnings_report(tmp_path, [(W, "REVIEW: low-confidence page")] * 3)
    text = _report(tmp_path)
    assert text.count("REVIEW: low-confidence page") == 1
    assert "(x3)" in text
    assert "3 warnings (1 distinct)" in text


def test_a_message_that_wrapped_is_one_line(tmp_path):
    # One entry is one line, so the file can be read back to answer "which of
    # these are new?" without a second machine-readable copy of itself.
    pl._write_warnings_report(tmp_path, [(W, "first part\n   second part")])
    assert _entries(tmp_path) == {"first part second part"}


def test_a_clean_run_removes_the_report(tmp_path):
    pl._write_warnings_report(tmp_path, [(W, "something")])
    assert (tmp_path / NAME).exists()
    assert pl._write_warnings_report(tmp_path, []) is None
    assert not (tmp_path / NAME).exists()


def test_a_later_run_marks_what_is_new_and_counts_what_is_gone(tmp_path):
    pl._write_warnings_report(tmp_path, [(W, "still here"), (W, "fixed since")])
    pl._write_warnings_report(tmp_path, [(W, "still here"), (W, "brand new")])
    text = _report(tmp_path)
    assert "fixed since" not in text                  # the last run only
    assert "1 line(s) from the previous report no longer occur" in text
    lines = {line.split("]")[-1].strip(): line for line in text.splitlines()
             if "still here" in line or "brand new" in line}
    assert "[NEW]" in lines["brand new"]
    assert "[NEW]" not in lines["still here"]         # carried over, not new


def test_a_first_report_marks_nothing_new(tmp_path):
    # With no previous report there is nothing to be new AGAINST, and marking
    # every line would say only that the file did not exist a moment ago.
    pl._write_warnings_report(tmp_path, [(W, "one"), (W, "two")])
    marked = [line for line in _report(tmp_path).splitlines()
              if pl._WARN_ENTRY_RE.match(line) and "[NEW]" in line]
    assert not marked


def test_a_file_we_did_not_write_is_neither_read_nor_deleted(tmp_path):
    (tmp_path / NAME).write_text("my own notes about this case\n", encoding="utf-8")
    assert _entries(tmp_path) is None
    pl._write_warnings_report(tmp_path, [])            # a clean run
    assert (tmp_path / NAME).exists()                  # not ours, not deleted


# ── the wiring ───────────────────────────────────────────────────────────────

def test_the_collector_takes_warnings_and_leaves_info(tmp_path):
    pl._WARNINGS.install(tmp_path)
    log = logging.getLogger("pdf_linker")
    try:
        log.info("ordinary progress")
        log.warning("something to look at")
        log.error("something worse")
        pl._WARNINGS.write()
    finally:
        logging.getLogger().removeHandler(pl._WARNINGS)
    text = _report(tmp_path)
    assert "something to look at" in text and "something worse" in text
    assert "ordinary progress" not in text


def test_install_resets_rather_than_accumulating(tmp_path):
    # `main` can be called more than once in one process (these tests do), and
    # the previous folder's warnings are not this folder's.
    pl._WARNINGS.install(tmp_path)
    log = logging.getLogger("pdf_linker")
    try:
        log.warning("from the first run")
        pl._WARNINGS.install(tmp_path)
        log.warning("from the second run")
        pl._WARNINGS.write()
    finally:
        logging.getLogger().removeHandler(pl._WARNINGS)
    text = _report(tmp_path)
    assert "from the second run" in text and "from the first run" not in text


def test_a_run_that_exits_through_a_gate_still_writes_its_report(
        tmp_path, monkeypatch):
    # THE reason the write is in a `finally`: the leak gate and the
    # key-completeness gate both exit non-zero from the middle of the run, and
    # a report only a clean run produced would be a report of the runs that had
    # nothing to say.
    def _stub():
        pl._WARNINGS.install(tmp_path)
        logging.getLogger("pdf_linker").warning("!! Pseudonymize FAILED")
        sys.exit(2)

    monkeypatch.setattr(pl, "_main", _stub)
    try:
        pl.main()
    except SystemExit as e:
        assert e.code == 2
    finally:
        logging.getLogger().removeHandler(pl._WARNINGS)
    assert "!! Pseudonymize FAILED" in _report(tmp_path)


def test_a_run_that_dies_says_so_in_the_report(tmp_path, monkeypatch):
    # `sys.excepthook` logs the traceback, but it runs after the run unwinds,
    # so the collector would never see that line.
    def _stub():
        pl._WARNINGS.install(tmp_path)
        raise RuntimeError("boom")

    monkeypatch.setattr(pl, "_main", _stub)
    try:
        pl.main()
    except RuntimeError:
        pass
    finally:
        logging.getLogger().removeHandler(pl._WARNINGS)
    text = _report(tmp_path)
    assert "unhandled error" in text and "boom" in text
    assert "pdf_linker.log" in text                    # where the traceback is


def test_new_means_new_since_the_last_RUN_not_the_last_write(tmp_path):
    # The report is written twice in a run — once before the folder copy, so
    # the copy carries it, and once in `main`'s `finally`. A second write that
    # read the first one back would compare the run against ITSELF: every line
    # carried over, nothing ever marked, and a "no longer occur" count taken
    # against a snapshot of the same run.
    pl._write_warnings_report(tmp_path, [(W, "from the previous run")])
    pl._WARNINGS.install(tmp_path)
    log = logging.getLogger("pdf_linker")
    try:
        log.warning("a fresh one")
        pl._WARNINGS.write()          # the mid-run write (before the copy)
        log.warning("a later one")
        pl._WARNINGS.write()          # the end-of-run write
    finally:
        logging.getLogger().removeHandler(pl._WARNINGS)
    text = _report(tmp_path)
    marked = {line.split("]")[-1].strip() for line in text.splitlines()
              if pl._WARN_ENTRY_RE.match(line) and "[NEW]" in line}
    assert marked == {"a fresh one", "a later one"}
    assert "1 line(s) from the previous report no longer occur" in text
