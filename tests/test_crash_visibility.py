"""A run that dies must say so, and a second run must not fight the first.

The tool's normal launch is `pythonw.exe`, which has NO console — `sys.stderr`
is None, so an uncaught exception's traceback goes precisely nowhere. The
process vanishes, `pdf_linker.log` stops wherever it had got to, and Task
Manager shows nothing running. That is indistinguishable from a hang, and it is
what sent an operator back to double-click the launcher two more times on a
folder whose first run had already died — leaving three detached runs (or, as it
turned out, three dead ones) on the same 34 files.

Both halves of that are covered here: the death is made visible, and a second
launch on a folder already being worked exits instead of competing.

Run:  cd PDF-Linker && python3 -m pytest tests/test_crash_visibility.py -v
"""
import importlib.util
import logging
import subprocess
import sys
import textwrap
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pdf_linker", _ROOT / "pdf_linker.py")
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)

log = logging.getLogger("test")

_LOAD = f"""
import sys, importlib.util, logging
spec = importlib.util.spec_from_file_location("pl", {str(_ROOT / 'pdf_linker.py')!r})
pl = importlib.util.module_from_spec(spec); spec.loader.exec_module(pl)
"""


def _child(body, tmp_path, **kw):
    # `body` is dedented on its own: _LOAD already sits at column 0, so
    # dedenting the concatenation would find a common prefix of "" and leave the
    # body indented.
    src = _LOAD + textwrap.dedent(body)
    return subprocess.run([sys.executable, "-c", src],
                          capture_output=True, text=True, timeout=120,
                          cwd=str(tmp_path), **kw)


# ── the folder lock ─────────────────────────────────────────────────────────

def test_a_second_run_on_the_same_folder_is_refused(tmp_path):
    assert pl._acquire_folder_lock(tmp_path, log) is True
    try:
        done = _child(f"""
            import pathlib, logging
            got = pl._acquire_folder_lock(pathlib.Path({str(tmp_path)!r}),
                                          logging.getLogger('x'))
            print("GOT", got)
        """, tmp_path)
        assert "GOT False" in done.stdout, (done.stdout, done.stderr)
    finally:
        pl._release_folder_lock(pl._folder_lock_file(tmp_path))


def test_the_lock_is_released_and_its_file_removed(tmp_path):
    assert pl._acquire_folder_lock(tmp_path, log) is True
    assert pl._folder_lock_file(tmp_path).exists()
    pl._release_folder_lock(pl._folder_lock_file(tmp_path))
    assert not pl._folder_lock_file(tmp_path).exists()
    # ...and the folder is free again for the next run.
    assert pl._acquire_folder_lock(tmp_path, log) is True
    pl._release_folder_lock(pl._folder_lock_file(tmp_path))


def test_a_dead_run_leaves_no_stale_lock(tmp_path):
    # The reason this is an OS lock and not a pid file: the tool CAN die without
    # cleaning up (a MuPDF fatal error calls abort()). A lock the dying process
    # had to tidy would then block the folder forever.
    done = _child(f"""
        import pathlib, logging, os
        pl._acquire_folder_lock(pathlib.Path({str(tmp_path)!r}),
                                logging.getLogger('x'))
        os._exit(1)                      # die hard: no atexit, no cleanup
    """, tmp_path)
    assert done.returncode == 1
    assert pl._acquire_folder_lock(tmp_path, log) is True
    pl._release_folder_lock(pl._folder_lock_file(tmp_path))


def test_the_lock_fails_open_when_disabled(tmp_path):
    # A lock that cannot be acquired must never stop legitimate work.
    import os
    os.environ["PDF_LINKER_NO_LOCK"] = "1"
    try:
        assert pl._acquire_folder_lock(tmp_path, log) is True
        assert pl._acquire_folder_lock(tmp_path, log) is True   # never refuses
        assert not pl._folder_lock_file(tmp_path).exists()
    finally:
        del os.environ["PDF_LINKER_NO_LOCK"]


# ── crash visibility ────────────────────────────────────────────────────────

def _crash_child(tmp_path, body):
    return _child(f"""
        import logging, sys
        sys.stderr = None                       # what pythonw.exe gives you
        logging.basicConfig(filename="pdf_linker.log", level=logging.INFO,
                            format="%(asctime)s [%(levelname)s] %(message)s")
        _log = logging.getLogger("pdf_linker")
        pl._install_crash_logging(_log)
        _log.info("  Pre-scan 17/34: Big Scanned Exhibit.pdf")
        for h in logging.getLogger().handlers: h.flush()
        {body}
    """, tmp_path)


def test_an_uncaught_exception_reaches_the_log_without_a_console(tmp_path):
    # The failure that differs between two machines running the same folder: a
    # dependency imported lazily mid-run. With no stderr this wrote nowhere.
    done = _crash_child(tmp_path, "import a_module_that_is_not_installed")
    assert done.returncode != 0
    text = (tmp_path / "pdf_linker.log").read_text()
    assert "Run ended on an unhandled error" in text
    assert "ModuleNotFoundError" in text
    assert "a_module_that_is_not_installed" in text


def test_a_hard_abort_still_leaves_a_trace(tmp_path):
    # The other way it dies: MuPDF calls abort() on a fatal error, which raises
    # nothing and so cannot be hooked. faulthandler is the only thing that can
    # record it.
    done = _crash_child(tmp_path, "import ctypes; ctypes.string_at(0)")
    assert done.returncode != 0
    text = (tmp_path / "pdf_linker.log").read_text()
    assert "Fatal Python error" in text


def test_the_last_log_line_names_the_file_being_read(tmp_path):
    # Whatever killed it, the line before the crash says which file was open —
    # which is the difference between a diagnosable crash and "it just stops".
    done = _crash_child(tmp_path, "import ctypes; ctypes.string_at(0)")
    assert done.returncode != 0
    lines = [ln for ln in (tmp_path / "pdf_linker.log").read_text().splitlines()
             if ln.strip()]
    named = [i for i, ln in enumerate(lines) if "Big Scanned Exhibit.pdf" in ln]
    assert named, lines
    assert any("Fatal Python error" in ln for ln in lines[named[0]:])


def test_running_out_of_memory_still_says_so(tmp_path):
    # The one death the hook could not report, and the one a big folder is most
    # likely to hit. Formatting a traceback ALLOCATES — logging re-reads the
    # source lines to print them — so the rich report raised a second
    # MemoryError inside the hook, `except Exception: pass` swallowed it, and
    # the process exited having written nothing at all. A log ending mid-file
    # with no python left in Task Manager is exactly the silence this exists to
    # break, so the fixed line goes down first, pre-encoded and written straight
    # at the descriptor.
    done = _crash_child(tmp_path, "raise MemoryError()")
    assert done.returncode != 0
    text = (tmp_path / "pdf_linker.log").read_text()
    assert "OUT OF MEMORY" in text
    assert "Big Scanned Exhibit.pdf" in text   # ...still after the file it named


def test_the_bare_line_lands_even_when_the_rich_report_cannot(tmp_path):
    # Simulate the second failure directly: the traceback path is dead, and the
    # operator must STILL be told the run ended rather than left reading a log
    # that simply stops.
    done = _crash_child(tmp_path, """
        class _Dead:
            def critical(self, *a, **k):
                raise MemoryError()
        pl._install_crash_logging(_Dead())
        raise ValueError("boom")
    """)
    assert done.returncode != 0
    text = (tmp_path / "pdf_linker.log").read_text()
    assert "Run ended on an unhandled error" in text


def test_installing_the_hooks_never_itself_fails():
    # A diagnostic that raises would end the very run it exists to explain.
    pl._install_crash_logging(logging.getLogger("no-handlers-at-all"))


# ── the dependency check ────────────────────────────────────────────────────

def test_pymupdf_is_present_here():
    assert pl._require_pymupdf(log) is True


def test_a_missing_pymupdf_names_this_interpreter(tmp_path):
    # The failure that produced the traceback this file exists for: `fitz` is
    # imported lazily at each use site, so its absence surfaced 34 files into a
    # run's setup rather than at startup. The message has to name the
    # interpreter by full path — a bare `pip install pymupdf` can land in a
    # different Python on the same machine and leave this failing identically.
    done = _child("""
        import sys, builtins, logging
        _real = builtins.__import__
        def _no_fitz(name, *a, **k):
            if name == "fitz":
                raise ImportError("No module named 'fitz'")
            return _real(name, *a, **k)
        builtins.__import__ = _no_fitz
        logging.basicConfig(filename="dep.log", level=logging.INFO,
                            format="%(message)s")
        print("OK", pl._require_pymupdf(logging.getLogger("d")))
    """, tmp_path)
    assert "OK False" in done.stdout, (done.stdout, done.stderr)
    text = (tmp_path / "dep.log").read_text()
    assert "-m pip install pymupdf" in text
    assert sys.executable.replace("pythonw", "python") in text


def test_the_store_python_gets_its_own_note(tmp_path):
    # The Microsoft Store build looks identical to a plain missing install from
    # here, but it is a different problem: it sandboxes site-packages, so a
    # pure-Python wheel (openpyxl) imports on the very interpreter a compiled
    # one (PyMuPDF) cannot load. The install command can succeed and the import
    # still fail, so the note has to be explicit.
    done = _child("""
        import sys, builtins, logging
        sys.executable = ("C:\\\\Users\\\\Z\\\\AppData\\\\Local\\\\Microsoft\\\\WindowsApps"
                          "\\\\PythonSoftwareFoundation.Python.3.13_qbz5n2\\\\pythonw.exe")
        _real = builtins.__import__
        def _no_fitz(name, *a, **k):
            if name == "fitz":
                raise ImportError("No module named 'fitz'")
            return _real(name, *a, **k)
        builtins.__import__ = _no_fitz
        logging.basicConfig(filename="store.log", level=logging.INFO,
                            format="%(message)s")
        pl._require_pymupdf(logging.getLogger("d"))
    """, tmp_path)
    text = (tmp_path / "store.log").read_text()
    assert "Microsoft Store build" in text, (text, done.stderr)
    assert "python.org" in text


def test_an_ordinary_interpreter_gets_no_store_note(tmp_path):
    done = _child("""
        import sys, builtins, logging
        sys.executable = "C:\\\\Python313\\\\pythonw.exe"
        _real = builtins.__import__
        def _no_fitz(name, *a, **k):
            if name == "fitz":
                raise ImportError("No module named 'fitz'")
            return _real(name, *a, **k)
        builtins.__import__ = _no_fitz
        logging.basicConfig(filename="plain.log", level=logging.INFO,
                            format="%(message)s")
        pl._require_pymupdf(logging.getLogger("d"))
    """, tmp_path)
    text = (tmp_path / "plain.log").read_text()
    assert "-m pip install pymupdf" in text, (text, done.stderr)
    assert "Microsoft Store" not in text


def test_the_lock_never_litters_the_case_folder(tmp_path):
    # The whole point of moving it to temp: the operator's folder stays clean,
    # and it stays clean even while a run holds the lock.
    assert pl._acquire_folder_lock(tmp_path, log) is True
    try:
        assert list(tmp_path.iterdir()) == []
        assert str(pl._folder_lock_file(tmp_path)).startswith(
            __import__("tempfile").gettempdir())
    finally:
        pl._release_folder_lock(pl._folder_lock_file(tmp_path))


def test_two_folders_get_two_different_locks(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    assert pl._folder_lock_file(a) != pl._folder_lock_file(b)
    # ...and one folder always maps to the same lock, however it is spelled.
    assert pl._folder_lock_file(a) == pl._folder_lock_file(tmp_path / "." / "a")


def test_a_lock_left_in_the_case_folder_by_an_older_build_is_swept_up(tmp_path):
    stale = tmp_path / pl._LOCK_NAME
    stale.write_bytes(b"")
    assert pl._acquire_folder_lock(tmp_path, log) is True
    try:
        assert not stale.exists()
    finally:
        pl._release_folder_lock(pl._folder_lock_file(tmp_path))
