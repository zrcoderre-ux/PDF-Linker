"""
--dump-terms prints the protected vocabulary from the live constants, so the
inventory can't drift from the source of truth.

Run:  cd PDF-Linker && python3 -m pytest tests/test_dump_terms.py -v
"""
import io

import pdf_linker as P


def test_dump_covers_every_protected_set():
    text = P._dump_protected_terms(out=io.StringIO())
    # every set is fully enumerated, with its constant name for grep-ability
    for const in ("_PN_PLEADING_WORDS", "_PN_DECL_DESCRIPTOR",
                  "_PN_SHORT_TOKEN_STOP"):
        assert const in text
    for w in P._PN_PLEADING_WORDS | P._PN_DECL_DESCRIPTOR | P._PN_SHORT_TOKEN_STOP:
        assert w in text, f"{w} missing from dump"
    # the never-fake reference words and the citation shapes are listed
    for token in ("declaration", "decl", "dec",
                  "_PN_INRE_LITIG_RE", "_PN_CASES_RUN_RE", "_PN_WL_RUN_RE"):
        assert token in text
    # court-form boilerplate that is never faked
    for token in ("_PN_NEVER_FAKE", "CIV-100", "CASE NUMBER", "Default Only"):
        assert token in text


def test_dump_writes_to_the_given_stream():
    buf = io.StringIO()
    returned = P._dump_protected_terms(out=buf)
    assert buf.getvalue() == returned and returned.strip()
