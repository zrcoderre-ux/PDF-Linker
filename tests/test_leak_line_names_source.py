"""
The LEAK warning names each value's category and source, so a leak with no
key row behind it can be traced to the pass that built its term.

Run:  cd PDF-Linker && python3 -m pytest tests/test_leak_line_names_source.py -v
"""
import inspect

import pdf_linker as P


def test_describe_reals_names_category_and_source():
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Mercedes Benz USA LLC"], [], [], registry=reg)
    pz = P.Pseudonymizer(terms, {}, registry=reg)
    out = pz.describe_reals({"Benz", "Nobody Tracked"})
    assert out[0].startswith("Benz (entity-token, from ")
    assert out[1] == "Nobody Tracked"          # an untracked value stands as is


def test_both_export_writers_use_it():
    for fn in (P._write_text_version, P._write_word_text_version):
        src = inspect.getsource(fn)
        assert "describe_reals(survivors)" in src
