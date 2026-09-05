"""A cited decision is never renamed through its SHORT FORMS.

A delivered batch kept every full citation of "RGC Gaslamp, LLC v. Ehmcke
Sheet Metal Co., Inc. (2020) 56 Cal.App.5th 413" byte-identical and shipped
every "RGC Gaslamp, supra", every argument heading naming the case and every
bare prose mention with the first word replaced by a pool fake — eleven
occurrences across three briefs. Three things compounded: the comma-led
corporate-suffix harvester read both sides of the cite as this case's
parties; the supra resolver admitted ONE word before ", supra" and keyed the
full cite on its first word, so "RGC Gaslamp, supra" never resolved and the
prune that asks "does this value stand outside a citation?" kept the tokens;
and the write guard protected only what the parser returned.

Run:  cd PDF-Linker && python3 -m pytest tests/test_cited_short_forms.py -v
"""
import logging

import openpyxl

import pdf_linker as P

log = logging.getLogger("test")

TEXT = ("(RGC Gaslamp, LLC v. Ehmcke Sheet Metal Co., Inc. (2020) 56 "
        "Cal.App.5th 413, 426.)\nThe privilege applies. (RGC Gaslamp, supra, "
        "56 Cal.App.5th at pp. 426-427.)\nRGC Gaslamp does not eliminate "
        "independent claims.\n(Posner v. Grunwald-Marx, Inc. (1961) 56 Cal.2d "
        "169, 186.)\n")


def _learned(text, parties=("Quillmark Builders LLC",)):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms([(pty, False) for pty in parties], [], [],
                              registry=reg)
    z = P.Pseudonymizer(terms, {}, registry=reg)
    P._pn_learn_from_text(z, text, "Motion")
    for fn in (z.prune_citation_only_terms, z.prune_prose_word_terms,
               z.prune_heading_only_terms, z.prune_fragment_terms):
        try:
            fn(text)
        except TypeError:
            fn()
    return z


def test_the_handoff_text_comes_back_byte_identical(tmp_path):
    z = _learned(TEXT)
    assert z.apply(TEXT) == TEXT
    kp = tmp_path / "pseudonym_key.xlsx"
    z.write_key(kp, log)
    if kp.exists():
        reals = " ".join(str(r[1]) for ws in openpyxl.load_workbook(kp).worksheets
                         for r in ws.iter_rows(min_row=2, values_only=True)
                         if r and r[1])
        for bad in ("RGC", "Gaslamp", "Ehmcke", "Grunwald"):
            assert bad not in reals, reals


def test_the_harvest_never_reads_a_citations_name():
    z = _learned(TEXT)
    assert not [t.real for t in z.terms if t.source == "document"], [
        (t.category, t.real) for t in z.terms if t.source == "document"]


def test_a_two_word_supra_resolves_to_its_full_cite():
    cites = P.find_all_citations(TEXT)
    full = [c for c in cites if c.get("plaintiff") == "RGC Gaslamp, LLC"]
    supra = [c for c in cites if c.get("is_supra")]
    assert full and supra, cites
    assert supra[0]["key"] == full[0]["key"]
    assert TEXT[slice(*supra[0]["span"])] == "RGC Gaslamp, supra"


def test_a_lead_in_word_before_the_short_form_is_walked_past():
    text = TEXT + "As held in RGC Gaslamp, supra, at p. 427, the claim fails.\n"
    supra = [c for c in P.find_all_citations(text) if c.get("is_supra")]
    assert len(supra) == 2
    assert text[slice(*supra[1]["span"])] == "RGC Gaslamp, supra"


def test_a_one_word_supra_still_resolves():
    text = ("(Posner v. Grunwald-Marx, Inc. (1961) 56 Cal.2d 169, 186.) "
            "Under Posner, supra, the rule holds.")
    supra = [c for c in P.find_all_citations(text) if c.get("is_supra")]
    assert supra and text[slice(*supra[0]["span"])] == "Posner, supra"


def test_a_template_party_sharing_a_cited_name_is_still_scrubbed():
    """The exception the mask already makes: a word of a value THIS case
    tracks is this case's, so "RGC Gaslamp" on the template is faked in
    prose while the full citation keeps it."""
    z = _learned(TEXT, parties=("RGC Gaslamp LLC",))
    out = z.apply(TEXT)
    assert "RGC Gaslamp, LLC v. Ehmcke" in out          # the full cite survives
    assert "RGC Gaslamp does not eliminate" not in out  # this case's party is faked


def test_a_party_standing_after_a_strung_cite_is_faked():
    """The tail-less half of the write guard protected any name within its
    window of a strung " v. ", across a lower-case word and a full stop, and
    the mask did not — so the party shipped with the leak tier silent."""
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(["Helen Rasho"], [], [], registry=reg),
                        {}, registry=reg)
    text = ("(Kremerman v. White (2021) 71 Cal.App.5th 358; Ewald v. "
            "Nationstar again. Helen Rasho then moved to compel.")
    out = z.apply(text)
    assert "Helen Rasho" not in out, out
    assert "Ewald v. Nationstar" in out


def test_a_whitelisted_verification_link_survives_the_cures():
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(["Grunwald-Marx Inc."], [], [],
                                          registry=reg), {}, registry=reg)
    link = "https://scholar.google.com/scholar?q=Posner%20v.%20Grunwald-Marx%2C%20Inc."
    text = "Grunwald-Marx Inc. answered. See " + link
    out = z.scrub_survivors(z.scrub_welded(z.apply(text), spliced=True))
    assert link in out, out
    assert not out.startswith("Grunwald-Marx")
    assert z.surviving_reals_reduced(out) == []
