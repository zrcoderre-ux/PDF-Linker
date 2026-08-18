"""
Detector spellings the corpus actually produces, previously left in clear text.

Every value here is one the corresponding detector already scrubbed in its
plainest spelling — what changes is only the SPELLING a real filing gives it:
an all-caps letterhead URL, a street name with a typographic apostrophe or an
accented letter, an ordinal street in a shouting caption, a phone number whose
extraction padded the separators, an SSN Word re-punctuated with en dashes.
A detector that recognises one spelling of a value and not another is a leak
in exactly the documents (scans, captions, letterheads) that matter most.

Also pinned here: the street IDENTITY of an ordinal street. A bare character
class ate the digits of "5th" along with the house number, so "100 5th Street"
and "200 9th Street" both keyed as "th street" and drew ONE fake — the
many-reals-onto-one-fake collapse the registry exists to prevent, and one the
reversal macro answers by restoring neither. And the `www.` prefix strip in
`_pn_load_key`, which used `str.lstrip` (a character SET, not a prefix) and so
mangled a host with its own leading w's.

Run:  cd PDF-Linker && python3 -m pytest tests/test_detector_gaps.py -v
"""
import logging

import openpyxl
import pytest

import pdf_linker as P

log = logging.getLogger("test")

DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}


def _pz():
    return P.Pseudonymizer([], DET, registry=P._PnFakeRegistry())


def _apply(text):
    return _pz().apply(text)


# ── an ALL-CAPS website is the same website ─────────────────────────────────

@pytest.mark.parametrize("url", [
    "WWW.SMITHLAWFIRM.COM",
    "HTTPS://WWW.SMITHLAWFIRM.COM/BIO",
    "SMITHLAWFIRM.COM",
])
def test_an_all_caps_website_is_faked(url):
    out = _apply(f"VISIT OUR WEBSITE AT {url} FOR MORE.")
    assert "smithlawfirm" not in out.lower()


def test_caps_and_lowercase_spellings_seed_one_fake_host():
    pz = _pz()
    out = pz.apply("See www.smithlawfirm.com and WWW.SMITHLAWFIRM.COM today.")
    hosts = {rec["fake"].lower().replace("www.", "").rstrip("/")
             for rec in pz.records.values() if rec["category"] == "url"}
    assert len(hosts) == 1                 # one firm, one fake domain


# ── an address keeps its identity through Word's punctuation and accents ────

@pytest.mark.parametrize("street", [
    "123 O’Farrell Street",       # typographic apostrophe
    "123 O'Farrell Street",       # straight apostrophe
    "1234 La Cañada Boulevard",   # accented letter (the CITY tail is kept —
    "4321 Peñasquitos Drive",     # localities are never faked by design)
    "1234 5TH STREET",            # shouting caption
])
def test_an_address_is_scrubbed_in_every_spelling(street):
    out = _apply(f"Service was made at {street}, Los Angeles, CA 90013 "
                 f"on the manager.")
    assert street not in out


def test_both_apostrophe_spellings_are_one_street():
    pz = _pz()
    out = pz.apply("Offices at 123 O’Farrell Street, San Francisco, CA 94102 "
                   "and at 123 O'Farrell Street, San Francisco, CA 94102.")
    fakes = {rec["fake"] for rec in pz.records.values()
             if rec["category"] == "address"}
    assert len(fakes) == 1                 # one parcel, one fake


# ── an ordinal street keeps its own identity ────────────────────────────────

def test_two_ordinal_streets_are_two_streets():
    a = P._pn_addr_street_key("100 5th Street")
    b = P._pn_addr_street_key("200 9th Street")
    assert a[0] != b[0]
    assert a[0] == "5th street" and b[0] == "9th street"
    # …and the composed fakes differ too (injectivity survives end to end).
    pz = _pz()
    pz.apply("He lives at 100 5th Street, Montebello, CA 90640. Her office "
             "is at 200 9th Street, Pasadena, CA 91101.")
    fakes = [rec["fake"] for rec in pz.records.values()
             if rec["category"] == "address"]
    assert len(fakes) == 2 and fakes[0] != fakes[1]


def test_the_ordinal_survives_the_house_number_strip():
    assert P._pn_addr_name_of("100 5th Street") == "5th"
    assert P._pn_addr_name_of("7227 Hickory Blvd") == "Hickory"
    assert P._pn_addr_name_of("414-416 S. Maple Ave.") == "S. Maple"


# ── separators the scan and the extraction really produce ───────────────────

@pytest.mark.parametrize("phone", [
    "(818)  953-0150",        # preserve_interword_spaces double space
    "(818) 953 - 0150",       # padded hyphen off a fax scan
    "(818) 953-0150",         # …and the plain form still works
])
def test_a_padded_phone_number_is_faked(phone):
    out = _apply(f"Call {phone} to reach counsel.")
    assert "953" not in out


@pytest.mark.parametrize("ssn", [
    "552–81–9081",            # en dash (Word autoformat)
    "552—81—9081",            # em dash
    "552-81-9081",
])
def test_a_dashed_ssn_is_faked_whatever_the_dash(ssn):
    out = _apply(f"SSN: {ssn} appears on the form.")
    assert "9081" not in out


# ── the www. strip is a PREFIX strip ────────────────────────────────────────

def test_a_host_with_its_own_leading_ws_keeps_them_through_the_key(tmp_path):
    key = tmp_path / "pseudonym_key.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Pseudonym Key"
    ws.append(["Category", "Real Value", "Replacement", "Status", "Source",
               "Occurrences"])
    ws.append(["email", "info@wwlaw.com", "grosvenor@postcairn.co",
               "replaced", "regex", 3])
    wb.save(key)
    reg = P._PnFakeRegistry()
    P._pn_load_key(key, reg, log)
    # The memo is seeded under the REAL host, not a w-stripped mangling of it —
    # so a later www spelling of the same firm's site folds onto the key's fake
    # instead of drawing a second one, and no unrelated host is bound.
    assert reg._memo.get(("domain", "wwlaw.com")) == "postcairn.co"
    assert ("domain", "law.com") not in reg._memo
    assert P._pn_fake_domain("www.wwlaw.com", reg) == "postcairn.co"
