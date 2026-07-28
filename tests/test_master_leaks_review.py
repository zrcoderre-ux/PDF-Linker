"""
Regressions distilled from a real cross-folder `Master Leaks` / `KEEP` review.

Every test here reproduces a row class the master workbook accumulated —
either a genuine leak the scrubber should have prevented, or triage noise the
operator had to clear with a KEEP `no` over and over:

  * wrapped-URL LEAD FRAGMENTS ("http://www", "http://]") minted as records,
    which then "survived" inside every deliberately-kept court URL;
  * a curly quote swallowed into a URL match, forking the dedup;
  * e-filing infrastructure hosts (One Legal, usLegalPro) flagged per folder;
  * this run's own fake domain, welded to a neighbour by a column splice,
    re-reported as an unknown identifier;
  * "Attorneys for Defendant HEALTH NET" reported WITH the role word — so a
    plain `yes` faked the word "Defendant" document-wide;
  * welded role boilerplate ("DefendantAttorneys") flagged as a name;
  * form labels ("Fax Number", "Telephone Number", "RESERVATION NO") flagged;
  * "…, an unincorporated interindemnity arrangement" harvested into the
    entity name, its ordinary words becoming bare pseudonym tokens;
  * a document TITLE in a name cell ("DEMURRER TO RESCORE HOLLYWOOD, LLC")
    registering pleading vocabulary as a party;
  * a HYPHENATED surname whose halves ("Dr. Ardeshirpour", a line-wrap's
    "Ardeshirpour- Zartoshti") leaked beside the faked given name.

Run:  cd PDF-Linker && python3 -m pytest tests/test_master_leaks_review.py -v
"""
import pytest

import pdf_linker as P

DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}


def _pz(values=(), text=""):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(values), [], [], registry=reg)
    return P.Pseudonymizer(terms, DET, registry=reg)


# ── wrapped-URL lead fragments ──────────────────────────────────────────────

@pytest.mark.parametrize("frag", [
    "http://www", "https://www", "http://", "https://", "http://]", "www.",
])
def test_url_lead_fragment_is_fragmentary(frag):
    assert P._pn_url_fragmentary(frag)


@pytest.mark.parametrize("value", [
    "www.wildmere.com", "law.com", "https://acme.com/path", "sub.firm.net",
])
def test_real_domain_is_not_fragmentary(value):
    assert not P._pn_url_fragmentary(value)


def test_wrapped_url_fragment_is_not_minted_as_a_record():
    # A line wrap split the URL: the detector sees only "http://www." — faking
    # it corrupts the visible text, and the minted record then re-matched the
    # head of every intact kept URL as a phantom folder-wide leak.
    z = _pz()
    out = z.apply("See http://www.\nexamplesite.com/page for details.")
    assert "http://www.\n" in out                   # lead fragment untouched
    reals = [r["real"] for r in z.records.values()]
    assert not any(r.startswith("http") for r in reals)
    # ... while the tail half (a bare domain on its own line) is still faked.
    assert "examplesite.com" not in out


def test_fragment_never_survives_as_leak_row_over_kept_court_urls():
    z = _pz()
    text = ("Filed via http://www.\nexamplesite.com. Forms at "
            "https://www.courts.ca.gov/forms.htm.")
    out = z.apply(text)
    assert "https://www.courts.ca.gov/forms.htm" in out   # kept deliberately
    assert not [v for v in z.surviving_reals(out) if v.startswith("http")]


def test_fragment_is_not_a_review_finding():
    assert not [s for c, s in P._pn_review_findings("go to http://www now")
                if c == "url/domain"]


# ── curly-quote tails ───────────────────────────────────────────────────────

def test_curly_quote_not_swallowed_into_url_match():
    rx = P._PN_DETECTORS["url"][0]
    m = [m.group(0) for m in
         rx.finditer("at “https://status.example.com/.” today")]
    assert m == ["https://status.example.com/"]


# ── e-filing infrastructure hosts ───────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "https://status.onelegal.com/",
    "platform.onelegal.com/JtiOrderCaseSearch",
    "https://uslegalpro.com/californiaefile/login",
    "www.lawhelpcalifornia.org",
])
def test_efiling_infrastructure_is_whitelisted(url):
    assert P._pn_url_whitelisted(url)
    out = _pz().apply(f"Track your filing at {url} anytime.")
    assert url in out                               # never faked
    assert not [s for c, s in P._pn_review_findings(f"see {url} now")
                if c == "url/domain"]               # never flagged


def test_efiling_email_is_still_faked():
    # The @ settles it: an address names a mailbox, not the filing channel.
    out = _pz().apply("From: noreply@onelegal.com")
    assert "noreply@onelegal.com" not in out


# ── own fake domain welded by a column splice ───────────────────────────────

def test_welded_own_fake_domain_not_reported():
    known = {"wadsworth.com", "vance", "postbox2.org"}
    noise = "See www.wadsworth.com.mallory and drvance.com and postbox2.orgpany."
    assert not [s for c, s in P._pn_review_findings(noise, known)
                if c == "url/domain"]


def test_real_domain_beside_fakes_still_reported():
    found = P._pn_review_findings("See www.CAPphysicians.com today.",
                                  {"wadsworth.com"})
    assert ("url/domain", "www.CAPphysicians.com") in found


# ── unknown-name scan: role words trimmed off the reported value ────────────

def test_role_words_trimmed_from_unscrubbed_name_finding():
    text = ("Attorneys for Defendant HEALTH NET, INC. appeared. "
            "Counsel for Defendants BHC ALHAMBRA HOSPITAL joined.")
    names = [s for _, s in P._pn_unknown_name_findings(text, set())]
    assert "HEALTH NET" in names
    assert "BHC ALHAMBRA HOSPITAL" in names
    assert not any(s.startswith("Defendant") for s in names)


def test_plain_anchor_still_reports_the_party():
    names = [s for _, s in
             P._pn_unknown_name_findings("Defendant Travelers moved.", set())]
    assert names == ["Travelers"]


def test_welded_role_boilerplate_not_a_name():
    text = "Defendants DefendantAttorneys for DefendantAttorney served."
    assert not P._pn_unknown_name_findings(text, set())


# ── form labels are boilerplate, not people ─────────────────────────────────

def test_fax_and_telephone_labels_not_person_names():
    text = ("Fax Number\n(310) 555-1212 and Telephone Number "
            "(213) 555-0000 are on file.")
    assert not P._pn_person_review_findings(text)


def test_reservation_label_not_an_unscrubbed_name():
    text = "Defendant RESERVATION NO 439871 and the Trial Date stand."
    assert not P._pn_unknown_name_findings(text, set())


def test_real_person_before_phone_still_reported_without_trailing_quote():
    found = P._pn_person_review_findings("Sheila Bird'\n(213) 555-9999")
    assert found == [("possible person name", "Sheila Bird")]


# ── interindemnity descriptor ───────────────────────────────────────────────

def test_interindemnity_arrangement_descriptor_stripped():
    head, had = P._pn_strip_entity_descriptor(
        "MUTUAL PROTECTION TRUST, an unincorporated interindemnity arrangement")
    assert had and head == "MUTUAL PROTECTION TRUST"


def test_bare_interindemnity_descriptor_is_no_party():
    assert P._PN_ONLY_DESCRIPTOR_RE.match(
        "an unincorporated interindemnity arrangement")


def test_descriptor_words_never_become_bare_tokens():
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(
        ["MUTUAL PROTECTION TRUST, an unincorporated interindemnity arrangement"],
        [], [], registry=reg)
    reals = {t.real.lower() for t in terms}
    for w in ("unincorporated", "interindemnity", "arrangement", "an"):
        assert w not in reals
    out = P.Pseudonymizer(terms, [], registry=reg).apply(
        "MUTUAL PROTECTION TRUST, an unincorporated interindemnity arrangement")
    assert out.endswith(", an unincorporated interindemnity arrangement")
    assert "MUTUAL PROTECTION TRUST" not in out       # the name itself faked


# ── document titles in a name cell ──────────────────────────────────────────

def test_pleading_title_prefix_stripped_from_name_cell():
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["DEMURRER TO RESCORE HOLLYWOOD, LLC"],
                              [], [], registry=reg)
    reals = {t.real.lower() for t in terms}
    assert not any("demurrer" in r for r in reals)
    z = P.Pseudonymizer(terms, [], registry=reg)
    out = z.apply("The DEMURRER TO RESCORE HOLLYWOOD, LLC is sustained. "
                  "RESCORE HOLLYWOOD, LLC may amend.")
    assert out.count("DEMURRER TO ") == 1              # the pleading word stays
    assert "RESCORE HOLLYWOOD" not in out              # the party is faked


def test_pure_title_cell_registers_nothing():
    terms = P._pn_build_terms(["MOTION TO STRIKE"], [], [],
                              registry=P._PnFakeRegistry())
    assert not any(t.category in ("person", "entity") for t in terms)


def test_entity_starting_with_a_pleading_word_is_untouched():
    assert (P._pn_strip_pleading_title_prefix(
        "Motion Picture Industry Pension Plan")
        == "Motion Picture Industry Pension Plan")


# ── hyphenated surnames ─────────────────────────────────────────────────────

def test_hyphenated_surname_halves_are_scrubbed():
    z = _pz(["Farhad Ardeshirpour-Zartoshti, M.D."])
    out = z.apply("Dr. Ardeshirpour saw the patient; Zartoshti signed. "
                  "Farhad Ardeshirpour-Zartoshti, M.D. concurred.")
    assert "Ardeshirpour" not in out and "Zartoshti" not in out


def test_line_wrap_split_hyphen_matches_the_whole_token_fake():
    z = _pz(["Farhad Ardeshirpour-Zartoshti, M.D."])
    whole = z.apply("Ardeshirpour-Zartoshti")
    wrapped = z.apply("Ardeshirpour-\nZartoshti")
    assert whole == wrapped.strip()                    # same fake either way
    assert "Ardeshirpour" not in wrapped


def test_short_hyphen_halves_not_expanded():
    # "Al-Amin": a 2-letter half would rewrite the article "Al" everywhere.
    z = _pz(["Yusuf Al-Amin"])
    reals = {t.real for t in z.terms}
    assert "Al" not in reals and "Amin" not in reals
