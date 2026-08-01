"""
Website / e-mail scrubbing policy.

  * a website is FAKED (`www.acmecorp.com` -> a neutral fake host);
  * an e-mail — anything carrying an `@` — is FAKED, local part AND host;
  * a GOVERNMENT website (`*.gov`, `*.mil`) is never faked and never flagged:
    it names an agency, not a party, so faking it protects no one and burying
    the real findings under it costs a review pass; but
  * a government host inside an E-MAIL is faked anyway — `jane.roe@courts.ca.gov`
    identifies a person, not an agency, and the `@` is what settles it.

Run:  cd PDF-Linker && python3 -m pytest tests/test_url_email_policy.py -v
"""
import pytest

import pdf_linker as P

DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}


def _apply(text):
    reg = P._PnFakeRegistry()
    return P.Pseudonymizer([], DET, registry=reg).apply(text)


# ── websites ending in .com are faked ───────────────────────────────────────

@pytest.mark.parametrize("url", [
    "www.acmecorp.com",
    "acmecorp.com",
    "https://www.acmecorp.com",
    "https://acmecorp.com/attorneys/bio.html",
    "http://mail.acmecorp.com/login",
])
def test_a_dot_com_website_is_faked(url):
    out = _apply(f"Visit {url} for details.")
    assert "acmecorp" not in out.lower()


# ── an @ makes it an e-mail, and an e-mail is always faked ──────────────────

@pytest.mark.parametrize("addr", [
    "jane.roe@acmecorp.com",
    "jroe@acmecorp.net",
    "jane.roe@acmecorp.org",
])
def test_an_email_is_faked_local_part_and_host(addr):
    out = _apply(f"Write to {addr} today.")
    assert "acmecorp" not in out.lower()
    assert "jane.roe" not in out.lower() and "jroe" not in out.lower()
    assert "@" in out                          # still reads as an address


# ── government websites are left verbatim ───────────────────────────────────

@pytest.mark.parametrize("url", [
    "www.courts.ca.gov",
    "https://www.courts.ca.gov/forms.htm",
    "oag.ca.gov",
    "https://www.cdcr.ca.gov/facilities",
    "usdoj.gov",
    "army.mil",
    "https://www.navy.mil/local",
])
def test_a_government_website_is_never_faked(url):
    text = f"See {url} now."
    assert _apply(text) == text


def test_a_bare_wrapped_gov_tail_is_kept_too():
    # A line-wrapped court URL leaves a bare "ca.gov" on its own line; the
    # child-only whitelist missed it and every kept courts.ca.gov link then
    # reported a leak.
    text = "File at appellate.courts.ca.gov; forms wrapped to\nca.gov today."
    assert _apply(text) == text


def test_a_government_website_is_not_flagged_for_review():
    findings = P._pn_review_findings("visit selfhelp.courts.ca.gov and ca.gov")
    assert not [f for f in findings if "gov" in str(f[1]).lower()]


# ── ...except inside an e-mail, where the @ wins ────────────────────────────

@pytest.mark.parametrize("addr", [
    "jane.roe@courts.ca.gov",
    "officer@usdoj.gov",
    "clerk@lacourt.gov",
    "sgt@army.mil",
])
def test_a_government_host_inside_an_email_is_faked(addr):
    local, host = addr.split("@")
    out = _apply(f"Write to {addr} today.")
    assert addr not in out
    assert local not in out                    # the person is scrubbed
    assert host not in out                     # and so is the agency host
    # The stand-in must not itself pose as a government address.
    fake = next(w.strip(".,;:") for w in out.split() if "@" in w)
    assert not fake.lower().endswith((".gov", ".mil"))


def test_gov_website_and_gov_email_on_the_same_line():
    out = _apply("Forms at www.courts.ca.gov; write clerk@courts.ca.gov.")
    assert "www.courts.ca.gov" in out          # the website survives
    assert "clerk@courts.ca.gov" not in out    # the address does not


# ── an e-mail is never a triage row: always faked, so never a decision ──────

@pytest.mark.parametrize("value,is_email", [
    ("jane.roe@acmecorp.com", True),
    ("clerk@courts.ca.gov", True),
    ("a@b.co", True),
    ("courts.ca.gov", False),                  # a website, not an address
    ("www.acmecorp.com", False),
    ("Robert Smith", False),
    ("@acmecorp.com", False),                  # no local part
    ("jane@localhost", False),                 # no dotted host
    ("a@b.com c@d.com", False),                # two addresses: not one value
])
def test_email_value_shape(value, is_email):
    assert P._pn_is_email_value(value) is is_email


def test_an_email_host_is_not_reported_as_a_stray_domain():
    # The url regex matches "acmecorp.com" inside the address, and OCR that
    # spaced the address out leaves that fragment standing.
    for text in ("write to jane@acmecorp.com today",
                 "write to jane @ acmecorp.com today"):
        assert not [f for f in P._pn_review_findings(text)
                    if f[0] == "url/domain"], text


def test_a_bare_website_is_still_reported():
    # The suppression above must not swallow an ordinary stray domain.
    found = P._pn_review_findings("the firm site is acmecorp.com today")
    assert ("url/domain", "acmecorp.com") in found


def test_scrub_emails_cures_an_address_the_pattern_pass_left_behind():
    reg = P._PnFakeRegistry()
    pz = P.Pseudonymizer([], DET, registry=reg)
    pz.apply("Contact rsmith@smithassoc.com for service.")   # mints the record
    fake = next(r["fake"] for (c, _), r in pz.records.items() if c == "email")

    # A second rendering still carrying the real address (a wrap or a protected
    # span the substituter could not claim) is cured with the SAME fake.
    out = pz.scrub_emails("Served on RSMITH@SMITHASSOC.COM by e-mail.")
    assert "smithassoc.com" not in out.lower()
    assert fake in out
    assert not pz.surviving_reals(out)


def test_scrub_emails_is_idempotent_and_leaves_other_text_alone():
    reg = P._PnFakeRegistry()
    pz = P.Pseudonymizer([], DET, registry=reg)
    body = pz.apply("Contact rsmith@smithassoc.com; see www.courts.ca.gov.")
    assert pz.scrub_emails(pz.scrub_emails(body)) == pz.scrub_emails(body)
    assert "www.courts.ca.gov" in pz.scrub_emails(body)


# ── a whitelisted URL is protected from TOKEN passes too ────────────────────
# The url detector always skipped whitelisted hosts, but a bare token term
# sees no URL context: a batch that harvested "Google" as an entity rewrote
# every appendix verification link ("https://scholar.denholm.com/…"). The
# whole whitelisted span now joins the protected set, exactly like a citation.

def _pz_with_names(*names):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), [], [], registry=reg)
    return P.Pseudonymizer(terms, DET, registry=reg)


def test_google_never_binds_a_bare_token_at_all():
    # First line of defence is the gazetteer: "google"/"scholar" are ordinary
    # vocabulary now, so no harvest can mint the token that rewrote the links.
    z = _pz_with_names("Google Scholar Institute")
    assert not any(t.real.lower() in ("google", "scholar") for t in z.terms)


def test_a_whitelisted_link_survives_a_name_shaped_token():
    # Second line: even when a real party's own token appears inside a
    # whitelisted host (a declarant named "Justia" / law.justia.com), the span
    # is protected like a citation, so the verification link stays
    # byte-for-byte. Without the protection this exact text shipped as
    # "law.aldous.com" — the bare person-token fired inside the host.
    z = _pz_with_names("Justia Ramirez")
    assert any(t.real.lower() == "justia" for t in z.terms)  # token really binds
    url = "https://law.justia.com/cases/california/court-of-appeal/"
    out = z.apply(f"Declarant Justia Ramirez cites {url} in support.")
    assert url in out, "a whitelisted verification link must never be rewritten"
    assert "Justia Ramirez" not in out  # the declarant is still faked


def test_a_protected_url_survivor_is_not_reported_as_a_leak():
    # The scan must stay mirrored with the substitution side: a value standing
    # inside a span _substitute refuses to touch must not be reported, or the
    # export is quarantined by a leak nothing can ever clear.
    z = _pz_with_names("Justia Ramirez")
    out = z.apply("See https://law.justia.com/cases/california/ for the cite.")
    survivors = {s.lower() for s in z.surviving_reals(out)}
    assert not any("justia" in s for s in survivors), survivors
