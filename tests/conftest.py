"""Shared pytest fixtures.

Isolate the cross-folder master workbook (the KEEP + Master-Leaks store) to a
per-test temp file via the PDF_LINKER_MASTER env var, so tests that run main()
or --fix-leaks never read or pollute a real master_leaks.xlsx next to the
script (and never leak state between tests). Tests that pass an explicit
`master_leaks_path` cfg still win — that config override takes precedence over
the env var.
"""
import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_master(tmp_path, monkeypatch):
    monkeypatch.setenv("PDF_LINKER_MASTER", str(tmp_path / "master_leaks.xlsx"))
    yield
