"""A company named by ANY comma-led corporate suffix is harvested.

`Lenis Industries, Inc.` — the primary debtor a guaranty answer names three
times, on no template and behind no role word — reached no pass at all: the
suffix-anchored harvester knew a law firm's suffixes (LLC, LLP, P.C., APC) and
nothing else, so the commonest corporate suffix there is was not an anchor. And
a run that OPENED with a role word ("Defendant General Motors, LLC made an oral
motion") was refused whole instead of trimmed.

Run:  cd PDF-Linker && python3 -m pytest tests/test_corporate_suffix_harvest.py -v
"""
import pytest

import pdf_linker as P


@pytest.mark.parametrize("text,found", [
    ("the primary debtor, Lenis Industries, Inc., defaulted",
     "Lenis Industries, Inc."),
    ("the primary debtor (Lenis Industries, Inc.) obligations",
     "Lenis Industries, Inc."),
    ("Debtor, Lenis Industries, Inc., under the loan agreement",
     "Lenis Industries, Inc."),
    ("Defendant General Motors, LLC made an oral motion", "General Motors, LLC"),
    ("Plaintiff Acme Widgets, Corp. alleges", "Acme Widgets, Corp."),
    ("Bank of America, N.A. sued", "Bank of America, N.A."),
    ("The Boeing Company, Inc. answered", "The Boeing Company, Inc."),
    ("Sunrise Holdings, Ltd. and", "Sunrise Holdings, Ltd."),
    ("Sunrise Partners, L.P. filed", "Sunrise Partners, L.P."),
])
def test_a_comma_led_corporate_suffix_is_an_anchor(text, found):
    assert found in P._pn_firm_names(text), P._pn_firm_names(text)


@pytest.mark.parametrize("text", [
    "Denver, CO 80202",                      # a state abbreviation, not "Co."
    "Los Angeles, CA 90067",
    "John Smith, Jr., Esq.",
    "Exhibit A, Inc.",                       # nothing name-shaped in front
    "Doe Partners, L.P.",                    # a Doe is a role word, not a name
])
def test_what_is_not_a_company(text):
    names = P._pn_firm_names(text)
    assert not any(n.lower().startswith(("denver", "los angeles", "john",
                                         "exhibit", "doe")) for n in names), names


def test_the_reported_answer_scrubs_the_debtor():
    text = ("4. Plaintiff has waived its right to enforce the alleged guaranties "
            "through its conduct, including failure to timely enforce rights "
            "against the primary debtor, Lenis Industries, Inc.\n"
            "10. Debtor, Lenis Industries, Inc., under the loan agreement with "
            "the Plaintiff, defaulted. To the extent the primary debtor (Lenis "
            "Industries, Inc.) obligations were discharged, the guaranty fell.")
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(["Herriot Savennake"], [], [],
                                          registry=reg), {}, registry=reg)
    P._pn_learn_from_text(z, text, "Answer")
    for fn in (z.prune_citation_only_terms, z.prune_prose_word_terms,
               z.prune_heading_only_terms, z.prune_fragment_terms):
        fn(text)
    out = z.apply(text)
    assert "Lenis" not in out, out
    assert "Industries, Inc." not in out or "Lenis" not in out


def test_a_law_firm_suffix_still_harvests_as_before():
    names = P._pn_firm_names("SCHILLECI & TORTORICI, P.C.\nJASON P. TORTORICI")
    assert "SCHILLECI & TORTORICI, P.C." in names
