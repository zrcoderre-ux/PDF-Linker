"""
A broken Tesseract install (starts then dies — Windows 0xc0000142) used to be
discovered one page at a time: every OCR page spawned a tesseract.exe that
failed with a system error popup. The install is now probed ONCE per run and
OCR disabled with a single log line; child error dialogs are suppressed.

Run:  cd PDF-Linker && python3 -m pytest tests/test_tesseract_probe.py -v
"""
import logging
import os

import pytest

import pdf_linker as P

log = logging.getLogger("test")


def _script(tmp_path, name, body):
    p = tmp_path / name
    p.write_text("#!/bin/sh\n" + body)
    os.chmod(p, 0o755)
    return str(p)


def test_broken_tesseract_probes_false_and_caches(tmp_path):
    broken = _script(tmp_path, "tess-broken", "exit 127\n")
    P._TESS_PROBE.pop(broken, None)
    assert P._tesseract_usable(broken, log) is False
    assert P._TESS_PROBE[broken] is False          # cached: probed once per run


def test_working_tesseract_probes_true(tmp_path):
    ok = _script(tmp_path, "tess-ok", "echo tesseract 5.3.0\nexit 0\n")
    P._TESS_PROBE.pop(ok, None)
    assert P._tesseract_usable(ok, log) is True


def test_missing_tesseract_probes_false(tmp_path):
    missing = str(tmp_path / "no-such-tesseract")
    assert P._tesseract_usable(missing, log) is False


def test_dialog_suppression_is_posix_safe():
    P._suppress_child_error_dialogs()              # must not raise off-Windows
