"""
Website / e-mail scrubbing policy.

  * a website is FAKED (`www.acmecorp.com` -> a neutral fake host) — EVERY
    website that does not end in `.gov`, at the owner's direction: no
    e-filing vendor, no public mail provider, no `.mil`; the one exemption is
    the hosts of the verification links the tool itself writes;
  * an e-mail — anything carrying an `@` — is FAKED, local part AND host;
  * a `.gov` website is never faked and never flagged: it names an agency,
    not a party, so faking it protects no one and burying the real findings
    under it costs a review pass; but
  * a government host inside an E-MAIL is faked anyway — `jane.roe@courts.ca.gov`
    identifies a person, not an agency, and the `@` is what settles it;
  * a `no` / `never` typed against an address or a non-.gov website is NOT
    honoured — the row is set aside with a warning and the value is faked.

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
])
def test_a_government_website_is_never_faked(url):
    text = f"See {url} now."
    assert _apply(text) == text


@pytest.mark.parametrize("url", [
    "army.mil",
    "https://www.navy.mil/local",
    "https://status.onelegal.com/",
    "www.gdit.com/cob",
    "mail.google.com/mail",          # not the appendix's scholar host
    "gmail.com",
])
def test_every_other_host_is_faked(url):
    # ".gov" is the rule and there is no list behind it.
    out = _apply(f"See {url} now.")
    assert url not in out, out


@pytest.mark.parametrize("url", [
    "https://scholar.google.com/scholar?q=Rasho%20v.%20Quillmark",
    "https://www.law.cornell.edu/uscode/text/42/1983",
    "https://leginfo.legislature.ca.gov/faces/codes.xhtml",
])
def test_the_tools_own_verification_links_survive(url):
    # The authorities appendix writes these into the export itself; they name
    # a legal publisher and no party, and rewriting them breaks the links.
    assert P._pn_url_whitelisted(url)
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


def test_a_firm_domain_behind_an_unread_at_sign_is_still_faked():
    # The e-mail detector needs a local part in front of the "@"; a wrap that
    # left the handle on the line above leaves "@acmecorp.com" behind. The
    # domain is a website whatever stands before its "@", so it is faked —
    # where before it shipped as the real half of `<fake-local>@<real-domain>`.
    out = _apply("e-mail:\n@acmecorp.com")
    assert "acmecorp" not in out.lower(), out


def test_a_keep_on_an_address_or_website_is_not_honoured():
    # A `no` on a website is a decision the operator no longer gets to make;
    # the master KEEP sheet of a delivered folder carried dozens, and a soft
    # keep then applied every one in every folder.
    rows = [["Type", "Value", "Fix? (yes/no)", "Notes"],
            ["url/domain", "www.mrcooper.com", "no", ""],
            ["url/domain", "www.courts.ca.gov", "no", ""],
            ["email", "jane.roe@acmecorp.com", "never", ""],
            ["name", "Rosa Delgado", "no", ""]]
    out = P._pn_parse_decision_rows(rows)
    assert "www.mrcooper.com" not in out
    assert "jane.roe@acmecorp.com" not in out
    assert out["www.courts.ca.gov"]["fix"] == "no"   # a .gov site may be kept
    assert out["rosa delgado"]["fix"] == "no"
    for kind, value in (("e-mail address", "jane.roe@acmecorp.com"),
                        ("website", "www.mrcooper.com"),
                        ("website", "mrcooper.com"),
                        (None, "www.courts.ca.gov"),
                        (None, "Rosa Delgado")):
        assert P._pn_contact_value(value) == kind, value


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
    # whitelisted host (a declarant named "Cornell" / law.cornell.edu), the
    # span is protected like a citation, so the verification link stays
    # byte-for-byte. Without the protection this exact shape shipped as
    # "law.aldous.com" — the bare person-token fired inside the host.
    z = _pz_with_names("Cornell Ramirez")
    assert any(t.real.lower() == "cornell" for t in z.terms)  # token really binds
    url = "https://www.law.cornell.edu/uscode/text/42/1983"
    out = z.apply(f"Declarant Cornell Ramirez cites {url} in support.")
    assert url in out, "a whitelisted verification link must never be rewritten"
    assert "Cornell Ramirez" not in out  # the declarant is still faked


def test_a_protected_url_survivor_is_not_reported_as_a_leak():
    # The scan must stay mirrored with the substitution side: a value standing
    # inside a span _substitute refuses to touch must not be reported, or the
    # export is quarantined by a leak nothing can ever clear.
    z = _pz_with_names("Cornell Ramirez")
    out = z.apply("See https://www.law.cornell.edu/uscode/text/42/ for the cite.")
    survivors = {s.lower() for s in z.surviving_reals(out)}
    assert not any("cornell" in s for s in survivors), survivors


# ── OCR spellings of one address are ONE address ────────────────────────────
# A fax-generation scan shipped "barrylaw7 @gmail.com" in clear text (space
# before the @ missed the detector), "BARRYLAW7@GMAIL. COM" (TLD split), and
# minted THREE different fakes for the one address across the batch. The
# at-sign tolerates a step of whitespace, the TLD tolerates one after the dot
# (known TLDs only), and every fake derivation seeds on the canonical form.

def _email_fakes(*spellings):
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer([], DET, registry=reg)
    outs = [z.apply(f"Contact {s} today.") for s in spellings]
    return z, outs


@pytest.mark.parametrize("spelling", [
    "barrylaw7 @gmail.com",
    "barrylaw7@ gmail.com",
    "BARRYLAW7@GMAIL. COM",
    "barrylaw7(a)gmail.com",
])
def test_an_ocr_spelling_of_an_address_is_still_faked(spelling):
    _z, (out,) = _email_fakes(spelling)
    assert "barrylaw7" not in out.lower(), out


def test_every_spelling_of_one_address_draws_one_fake():
    z, _outs = _email_fakes("barrylaw7@gmail.com", "barrylaw7 @gmail.com",
                            "BARRYLAW7@GMAIL. COM", "barrylaw7(a)gmail.com")
    fakes = {r["fake"].lower() for r in z.records.values()
             if r["category"] == "email"}
    assert len(fakes) == 1, f"one real address shipped under {sorted(fakes)}"


def test_a_sentence_boundary_is_not_read_as_a_spaced_tld():
    # "bob@acme. Next sentence" — "Next" must not be swallowed as a TLD.
    _z, (out,) = _email_fakes("bob@acme. Next sentence follows.")
    assert "Next sentence follows." in out
