"""
The read-side keep and URL spans are computed on the UNMASKED body.

A batch's LEAKS worksheet carried "American", "Benz" and "Mercedes-Benz" as
LEAK rows with no key row behind them: every occurrence stood inside a
citation, so the scrub had rightly left them all alone. The site that
reported them was the authorities appendix's verification link. The
citation mask blanks a cited name wherever it stands, the appendix spells the
cite out again inside the link ("scholar?q=Kwan%20v.%20Mercedes-Benz…"), and
the read side ran its URL regex over the MASKED copy — where the blank inside
the link cut the URL short, so every word after it lay outside the
whitelisted span. The write side reads the same spans off the unmasked text,
so it refused the site, and no `--fix-leaks` pass could ever clear the row.

Run:  cd PDF-Linker && python3 -m pytest tests/test_url_spans_unmasked.py -v
"""
import inspect

import pdf_linker as P

BODY = (
    "====== Page 1 ======\n"
    " 1  The presumption applies to a leased vehicle as well.  (Kwan v. Mercedes-Benz of\n"
    " 2  North America, Inc. (1994) 23 Cal.App.4th 174, 184; Oregel v. American Isuzu\n"
    " 3  Motors, Inc. (2001) 90 Cal.App.4th 1094, 1103.)  Plaintiff bought the car in 2019.\n"
    " 4  The lease is no different.  (Kwan, supra, 23 Cal.App.4th at p. 184; Oregel, supra,\n"
    " 5  90 Cal.App.4th at p. 1103.)\n"
    "\n"
    "====== Authorities cited (public verification links) ======\n"
    "Kwan v. Mercedes-Benz of North America, Inc. (1994) 23 Cal.App.4th 174  ->  "
    "https://scholar.google.com/scholar?q=Kwan%20v.%20Mercedes-Benz%20of%20North%20America%2C%20Inc.%2023%20Cal.App.4th%20174\n"
    "Oregel v. American Isuzu Motors, Inc. (2001) 90 Cal.App.4th 1094  ->  "
    "https://scholar.google.com/scholar?q=Oregel%20v.%20American%20Isuzu%20Motors%2C%20Inc.%2090%20Cal.App.4th%201094\n"
)


def _pz():
    reg = P._PnFakeRegistry()
    terms = [t for t in P._pn_build_terms(
        ["Mercedes Benz USA LLC", "American Honda Motor Co."], [], [], registry=reg)
        if any(w in t.real.lower() for w in ("benz", "american"))]
    return P.Pseudonymizer(terms, {}, registry=reg)


def test_the_mask_reaches_inside_the_verification_link():
    # The premise: the mask blanks the cited plaintiff INSIDE the URL, so a
    # URL regex run over the masked copy would stop short of "Benz".
    pz = _pz()
    body = P._NFKC(BODY)
    masked = pz._mask_protected_citations(body)
    assert len(masked) == len(body)
    i = body.find("scholar?q=Kwan")
    assert masked[i:i + 14] != body[i:i + 14]          # "Kwan" blanked in the link
    d = body.find("Mercedes-Benz%20of")
    assert P._PnSpanIndex(pz._whitelisted_url_spans(body)).overlaps(d, d + 4)


def test_a_tracked_word_inside_the_link_is_not_a_leak():
    pz = _pz()
    out = pz.apply(BODY)
    assert out == P._NFKC(BODY)                       # the write side changed nothing
    assert pz.surviving_reals(out) == []
    assert pz.surviving_reals_reduced(out, spliced=True) == []
    assert pz.surviving_reals_reduced(out, spliced=False) == []
    # …and the cures leave the link exactly as written, so the mirror holds.
    assert pz.scrub_welded(out, spliced=True) == out
    assert pz.scrub_survivors(out) == out


def test_a_tracked_word_outside_any_cite_is_still_reported():
    pz = _pz()
    body = BODY + "\n====== Page 2 ======\n 1  The Benz dealer serviced the car twice.\n"
    out = pz.apply(body)
    assert "Benz dealer" not in out                    # scrubbed where it may be
    assert pz.surviving_reals(out) == []
    # A bound value the scrub was blocked from reaching still gates: put the
    # word where a keep protects nothing and no cite covers it.
    pz2 = _pz()
    raw = "====== Page 1 ======\n 1  The Benz dealer serviced the car twice.\n"
    assert pz2.surviving_reals(raw) == ["Benz"]


def test_both_tiers_read_their_spans_off_the_unmasked_body():
    src = inspect.getsource(P.Pseudonymizer._surviving_records)
    assert "self._whitelisted_url_spans(guard_body)" in src
    assert "self._whitelisted_url_spans(text)" not in src
    src = inspect.getsource(P.Pseudonymizer.surviving_reals_reduced)
    assert "self._whitelisted_url_spans(span_src)" in src
    assert "self._whitelisted_url_spans(masked)" not in src
