"""
The run streams progress to the console (not only the log file), so the re-run
launcher's window shows live output instead of reading as an empty terminal.

Run:  cd PDF-Linker && python3 -m pytest tests/test_console_output.py -v
"""
import subprocess
import sys
from pathlib import Path

PDF_LINKER = str(Path(__file__).resolve().parent.parent / "pdf_linker.py")


def test_run_prints_progress_to_stdout(tmp_path):
    # An empty case folder still produces the run banner + summary on stdout.
    r = subprocess.run(
        [sys.executable, PDF_LINKER, str(tmp_path), "--no-pseudonymize"],
        capture_output=True, text=True, timeout=120)
    assert "Run started for folder" in r.stdout
    assert "Found 0 PDF(s)" in r.stdout
    assert "Done:" in r.stdout
