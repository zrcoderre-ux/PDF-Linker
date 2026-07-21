"""
Term/record patterns are compiled once and reused, not recompiled on every page.
Python's own regex cache holds only 512 entries, so a case with more terms than
that recompiled every pattern on every page — regex compilation was ~75% of the
pseudonymize + leak-scan runtime. A per-Pseudonymizer compiled-pattern cache
removes it, with no change to what gets scrubbed.

Run:  cd PDF-Linker && python3 -m pytest tests/test_regex_cache.py -v
"""
import re

import pdf_linker as P


def _pz(names):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(names, [], [], registry=reg)
    return P.Pseudonymizer(terms, [], registry=reg)


def test_compiled_is_cached_and_returns_same_object():
    z = _pz(["Jane Smith"])
    a = z._compiled(r"\bfoo\b", re.IGNORECASE)
    b = z._compiled(r"\bfoo\b", re.IGNORECASE)
    assert a is b                                   # cached, not recompiled
    assert z._compiled(r"\bfoo\b", 0) is not a       # flags are part of the key


def test_apply_still_scrubs_with_the_cache():
    z = _pz(["Jane Smith", "Acme Widgets, Inc."])
    out = z.apply("Jane Smith sued Acme Widgets, Inc.")
    assert "Jane Smith" not in out
    assert "Acme Widgets" not in out
    assert z._rx_cache                               # cache got populated


def test_cache_holds_more_than_pythons_512_limit():
    # The whole point: a case with >512 distinct term patterns must keep them all
    # compiled, which Python's 512-entry re cache cannot.
    names = [f"Firstname{i} Lastname{i}" for i in range(700)]
    z = _pz(names)
    body = " ".join(names)
    out = z.apply(body)
    z.surviving_reals(out)
    assert len(z._rx_cache) > 512                    # all patterns cached at once
    # and nothing real is left behind
    assert z.surviving_reals(out) == []
