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


def key_body_rows(path):
    """Every BINDING row of a pseudonym key, from both of its sheets.

    A binding no export has ever carried lives on `_PN_KEY_PINNED_SHEET` so the
    reversal macro — which reads the active sheet — cannot apply it backwards
    onto a Real Value that was never in the document. It is still authoritative
    going forward and `_pn_load_key` reads it, so a test asking "is this
    binding in the key?" has to look at both. Ask `wb.active` directly when the
    question is specifically about what the MACRO will see."""
    import openpyxl

    wb = openpyxl.load_workbook(path)
    rows = []
    for ws in wb.worksheets:
        rows += list(ws.iter_rows(min_row=2, values_only=True))
    return [r for r in rows if any(c is not None for c in r)]
