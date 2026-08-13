"""
Business entities borrow common words far more than people do, so a single-word
partial token harvested from a business name must be tighter than the full name:
a common/ordinal word ("Eighth" of "Eighth & Broadway Investments") is dropped
outright, and any other bare word requires CAPITALIZATION, so a lower-case
occurrence in prose is never faked.

Regression for: "Eighth & Broadway Investments, LLC" faked every "eighth cause
of action" in the document.

The capitalisation rule used to be scoped to a single-word BUSINESS short form,
on the reasoning that a person's surname is distinctive and OCR can lower-case
it. It now covers every bare token (`_pn_term_is_cap_only`) — see
`test_generic_business_words.py` for why, and for what that costs.

Run:  cd PDF-Linker && python3 -m pytest tests/test_business_common_word_token.py -v
"""
import logging

import pdf_linker as P

log = logging.getLogger("test")


def _pz(names):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(names, [], [], registry=reg)
    return P.Pseudonymizer(terms, [], registry=reg)


def test_ordinal_word_is_a_common_word_now():
    assert P._pn_is_generic_token("eighth")
    assert P._pn_is_generic_token("twentieth")


def test_business_common_word_is_not_faked_in_prose():
    z = _pz(["Eighth & Broadway Investments, LLC"])
    # A parenthetical elsewhere used to attach and register bare "Eighth".
    z.register_short_names(
        "See Eighth & Broadway Investments, LLC. Property at 800 S. Broadway "
        "(Eighth & Broadway).")
    assert not [r for (c, r) in z.records if c == "short-name"]   # nothing registered
    out = z.apply("The eighth cause of action against "
                  "Eighth & Broadway Investments, LLC fails.")
    assert "eighth cause of action" in out                         # ordinal untouched
    assert "Eighth & Broadway Investments" not in out              # entity still faked


def test_distinctive_business_word_requires_capitalization():
    z = _pz(["Glenwood Group"])
    z.register_short_names('Defendant Glenwood Group ("Glenwood") acted.')
    out = z.apply("Glenwood breached; the glenwood forest is unrelated.")
    assert "Glenwood breached" not in out            # capitalised form IS faked
    assert "glenwood forest" in out                   # lower-case prose left alone


def test_initialism_stays_case_insensitive():
    # An initialism is distinctive and legitimately written TOFF / Toff / ToFF.
    z = _pz(["Tom of Finland Foundation"])
    z.register_short_names('Tom of Finland Foundation ("ToFF") promotes art.')
    out = z.apply("ToFF acted. See TOFF and Toff too.")
    assert "ToFF" not in out and "TOFF" not in out and "Toff" not in out


def test_a_persons_bare_surname_is_capitalized_too():
    """The one behaviour this file used to assert the other way.

    A person's bare token was left case-insensitive because a surname is
    distinctive and a scan can lower-case one. That exception did not survive
    contact with a folder where the harvest had classified companies as people:
    `Contractors` was a PERSON token there, applied 204 times, so scoping the
    rule by category inherited the misclassification.

    The justification is the same for both kinds of name — a party is
    capitalised wherever it stands — and the FULL name still matches in any
    casing, which is what keeps the party covered. The cost is stated plainly:
    a lower-cased bare surname is no longer scrubbed by its token.
    """
    z = _pz(["Gregory Yu"])
    assert "Yu was heard" not in z.apply("Testimony of Yu was heard.")
    assert "YU was heard" not in z.apply("Testimony of YU was heard.")
    assert "yu was heard" in z.apply("Testimony of yu was heard.")
    # …and the full name is untouched by the rule, in any casing.
    assert "gregory yu" not in z.apply("Testimony of gregory yu was heard.")
