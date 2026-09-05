"""Three matching gaps from the delivered-batch handoff (§7).

A street wrapped around an OCR stray line ("2000" / "lf" / "Riverside
Drive, …") stood in three proofs of service, matched by nothing and reported
by nothing. A caption's "of" glued to the plaintiff ("ofQUILLMARK BUILDERS
LLC") was cured token-wise and shipped half-scrubbed. And an address whose
local part a bound name token had already faked kept its real domain.

Run:  cd PDF-Linker && python3 -m pytest tests/test_handoff_matching_gaps.py -v
"""
import logging

import pdf_linker as P

log = logging.getLogger("test")


def _run(parties, text):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(parties, [], [], registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    z = P.Pseudonymizer(terms, det, registry=reg)
    z.register_addresses(text)
    out = z.apply(text)
    out = z.scrub_emails(z.scrub_welded(z.scrub_survivors(out), spliced=False))
    return z, out


def test_a_street_wrapped_around_a_stray_line_is_faked():
    text = ("My business address is 2000\nlf\nRiverside Drive, Los Angeles CA "
            "90039.\nOffice: 2000 Riverside Drive, Los Angeles CA 90039")
    z, out = _run(["Helen Rasho"], text)
    assert "Riverside" not in out, out
    fake = [t.fake for t in z.terms if t.category == "address_street"]
    assert fake and fake[0].endswith(" Drive") and fake[0] in out
    assert z.surviving_reals(out) == []


def test_the_street_alone_takes_the_addresss_own_fake():
    text = "Serve at 2000 Riverside Drive, Los Angeles CA 90039."
    z, out = _run([], text)
    street = {t.real: t.fake for t in z.terms if t.category == "address_street"}
    assert street == {"Riverside Drive": street["Riverside Drive"]}
    assert "2000 " + street["Riverside Drive"] in out


def test_a_name_glued_behind_a_lower_case_word_is_scrubbed_whole():
    text = ("ofQUILLMARK BUILDERS LLC\nof QUILLMARK BUILDERS LLC\n"
            "byManuel Vazquez signed")
    z, out = _run(["Quillmark Builders LLC", "Manuel Vazquez"], text)
    assert "BUILDERS" not in out and "Vazquez" not in out, out
    assert out.startswith("of") and "\nof " in out and "\nby" in out
    assert z.surviving_reals(out) == []


def test_the_left_glue_never_opens_inside_a_word_without_a_case_flip():
    z, out = _run(["Quillmark Builders LLC"], "ofquillmark builders llc stands")
    assert out == "ofquillmark builders llc stands"


def test_a_short_name_is_never_matched_inside_a_longer_word():
    z, out = _run(["Tue Nguyen"], "The Vatue of the property; Tue Nguyen agreed.")
    assert out.startswith("The Vatue of the property;")
    assert "Tue Nguyen" not in out


def test_a_faked_local_part_never_keeps_a_real_domain():
    text = ("Signed by Manuel Vazquez <manuel.vazquez@example-firm.com>\n"
            "Viewed: manuel.vazquez@example-firm.com")
    z, out = _run(["Manuel Vazquez"], text)
    fake_addr = [str(r["fake"]) for (c, _k), r in z.records.items() if c == "email"][0]
    fake_dom = fake_addr.split("@", 1)[1]
    # a half-faked address the detector never saw still loses its domain
    half = "herriot.ingleby@example-firm.com"
    faked_local = fake_addr.split("@", 1)[0]
    stray = f"Sent from {faked_local}@example-firm.com today"
    assert z.scrub_emails(stray) == f"Sent from {faked_local}@{fake_dom} today"
    assert "example-firm.com" not in out
