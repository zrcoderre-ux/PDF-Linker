"""
A re-run skips the (expensive) link/re-save pass on a PDF it already linked
(metadata stamp), regenerating only the .txt. --relink forces the full pass.

Run:  cd PDF-Linker && python3 -m pytest tests/test_relink_skip.py -v
"""
import logging
import time
from pathlib import Path

import fitz
import pytest

import pdf_linker as P

log = logging.getLogger("test")


def test_stamp_helpers_preserve_keywords_and_are_idempotent():
    d = fitz.open()
    d.new_page().insert_text((72, 100), "hi")
    assert P._pdf_is_stamped(d) is False
    d.set_metadata({"keywords": "lemon law"})
    P._pdf_stamp_linked(d)
    assert P._pdf_is_stamped(d) is True
    assert "lemon law" in d.metadata["keywords"]      # user keyword preserved
    before = d.metadata["keywords"]
    P._pdf_stamp_linked(d)                             # idempotent
    assert d.metadata["keywords"] == before
    d.close()


def _make_pdf(path):
    d = fitz.open()
    d.new_page().insert_text(
        (72, 100), "See Smith v. Jones (2017) 13 Cal.App.5th 1152.")
    d.save(str(path))
    d.close()


def test_rerun_skips_resave_but_relink_forces_it(tmp_path):
    pdf = tmp_path / "Brief.pdf"
    _make_pdf(pdf)

    assert P.process_pdf(pdf, log) is True             # run 1: link + stamp
    d = fitz.open(str(pdf))
    assert P._pdf_is_stamped(d)
    assert sum(len(p.get_links()) for p in d) >= 1     # a link was added
    d.close()
    m1 = pdf.stat().st_mtime

    time.sleep(0.05)
    assert P.process_pdf(pdf, log) is True             # run 2: default -> skip
    assert pdf.stat().st_mtime == m1                   # PDF NOT re-saved

    assert P.process_pdf(pdf, log, relink=True) is True  # run 3: forced
    assert pdf.stat().st_mtime != m1                   # PDF re-saved


def test_skip_run_still_regenerates_the_txt(tmp_path):
    pdf = tmp_path / "Brief.pdf"
    _make_pdf(pdf)
    P.process_pdf(pdf, log)                             # link + stamp
    txt = tmp_path / "Text Files" / "Brief.txt"
    assert txt.exists()
    txt.unlink()                                       # delete the export
    P.process_pdf(pdf, log)                            # skip run
    assert txt.exists()                                # .txt regenerated anyway
