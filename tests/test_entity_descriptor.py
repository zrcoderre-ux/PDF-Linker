"""
A state-of-organization descriptor — "a Delaware corporation", "a California
limited liability company", "an Illinois limited partnership" — is stock
boilerplate that names the incorporation state and legal form. It identifies no
one and reads identically for thousands of companies, so it must stay verbatim
and never be faked, EVEN when it sits inside a party's name. Only the
distinctive name in front of it becomes a term.

Run:  cd PDF-Linker && python3 -m pytest tests/test_entity_descriptor.py -v
"""
import pytest

import pdf_linker as P


def _fake(value, text=None):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms([value], [], [], registry=reg)
    z = P.Pseudonymizer(terms, [], registry=reg)
    return z.apply(text if text is not None else value)


@pytest.mark.parametrize("value,tail", [
    ("Riverside Ford, a California corporation", ", a California corporation"),
    ("Acme Widgets, Inc., a Delaware corporation", ", a Delaware corporation"),
    ("Sunrise Motors, LLC, a California limited liability company",
     ", a California limited liability company"),
    ("Doe Holdings, an Illinois limited partnership",
     ", an Illinois limited partnership"),
    ("Bay Cities Auto, a California general partnership",
     ", a California general partnership"),
    ("Helios Foundation, a California nonprofit public benefit corporation",
     ", a California nonprofit public benefit corporation"),
    ("Vance Capital, a Nevada LLC", ", a Nevada LLC"),
])
def test_descriptor_survives_verbatim_but_name_is_faked(value, tail):
    out = _fake(value)
    assert out.endswith(tail), out                 # descriptor untouched
    lead = value[:value.index(tail)]
    assert lead not in out                          # the name itself was faked


def test_descriptor_survives_when_only_the_name_is_a_term():
    # The clean key value (no descriptor) still leaves the descriptor in the
    # document verbatim while faking the name — the common path.
    out = _fake("Acme Widgets, Inc.",
                "Acme Widgets, Inc., a California corporation, answered.")
    assert ", a California corporation," in out
    assert "Acme Widgets" not in out


@pytest.mark.parametrize("value", [
    "California Pizza Kitchen, Inc.",     # 'California' is part of the name
    "Delaware Widgets Limited",            # no article -> not a descriptor
    "Texas Roadhouse, Inc.",
])
def test_state_inside_a_real_name_still_fakes(value):
    # No leading article, so it is the company's real name, not a descriptor —
    # it must fake fully (the state word included).
    out = _fake(value)
    assert out != value
    assert value.split(",")[0] not in out


@pytest.mark.parametrize("value", [
    "a California corporation",
    "an Illinois limited partnership",
    "a corporation",
])
def test_bare_descriptor_is_never_a_term(value):
    # A value that is nothing but a descriptor names no party; it must not become
    # a term and must be left verbatim.
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms([value], [], [], registry=reg)
    assert terms == []
    assert P.Pseudonymizer(terms, [], registry=reg).apply(value) == value


def test_strip_helper_contract():
    assert P._pn_strip_entity_descriptor(
        "Riverside Ford, a California corporation") == ("Riverside Ford", True)
    assert P._pn_strip_entity_descriptor("Acme, a corporation") == ("Acme", True)
    # not a descriptor: no article, or the whole thing is the descriptor
    assert P._pn_strip_entity_descriptor(
        "California Pizza Kitchen, Inc.") == ("California Pizza Kitchen, Inc.", False)
    assert P._pn_strip_entity_descriptor(
        "Bank of America, N.A.") == ("Bank of America, N.A.", False)
