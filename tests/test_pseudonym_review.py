"""
Regression suite from the pseudonym-replacement review (2026-07-10).

Each test encodes ONE acceptance criterion for a defect found by comparing the
delivered pseudonymized .txt exports against the originals for
`25STCV37838 Estrada v. Azul Concreto`. Every test in the REVIEW section is
expected to FAIL against the pre-fix code and PASS once the corresponding fix
in HANDOFF.md lands. The GUARD section pins behavior that is already correct
and must not regress while the fixes are made.

Run:  cd PDF-Linker && python3 -m pytest tests/test_pseudonym_review.py -v
"""

import logging
import re
import openpyxl
import pytest

import pdf_linker as P

log = logging.getLogger("test")


def _pz(names=("Roxane Estrada", "Azul Concreto, Inc."),
        casenos=("25STCV37838",)):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), list(casenos), [], registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    return P.Pseudonymizer(terms, det, registry=reg)


# ─────────────────────────── REVIEW (red now) ───────────────────────────────

# P0-1  Defendant identity must not split into two unrelated fakes.
#   Delivered set called the same corporation both "Beacon Torchlight, Inc."
#   (entity pool) and "Nolan Isley, Inc." / "(Nolan)" (person pool), because a
#   word maps to a DIFFERENT fake depending on which pool asks for it.
#   Fix: a token already bound in the entity pool must reuse that fake when the
#   person path later meets the same word (cross-pool reconciliation), and a
#   suffix-less corporate name must not take the person path.
def test_token_fake_is_stable_across_person_and_entity_pools():
    reg = P._PnFakeRegistry()
    ent = reg.token("azul", P._PN_ENTITY_WORDS, "enttok")
    nam = reg.token("azul", P._PN_NAME_WORDS, "nametok")
    assert ent == nam, (
        f"'azul' got {ent!r} as an entity but {nam!r} as a person; the "
        "defendant renders under two identities in the same document set")


def test_defendant_bare_form_reuses_entity_fake():
    # "Azul Concreto, Inc." is the entity (from the spreadsheet). When a
    # document pass later meets the name WITHOUT its suffix and takes the person
    # path, it must reuse the entity's per-word fakes — never mint an unrelated
    # person ("Nolan Isley"). Every faked word of the bare person form must
    # therefore appear in the entity fake.
    reg = P._PnFakeRegistry()
    ent_fake, _map = P._pn_fake_entity_parts("Azul Concreto, Inc.", reg)
    person_fake, _bare = P._pn_fake_person("Azul Concreto", reg)
    for w in person_fake.split():
        assert w in ent_fake, (
            f"bare person form {person_fake!r} diverges from entity {ent_fake!r}"
            "; the defendant would appear under two identities")


# P0-2  A spelled-out state must never be corrupted.
#   "…, Montebello, California 90640" was emitted as "…, Clearwater, ia 30070":
#   the two-letter state group ate the tail of "California", leaving "ia".
def test_spelled_out_state_survives_addressing():
    z = _pz()
    out = z._fake_street("414 S. Maple Ave., Montebello, California 90640")
    assert "California" in out and " ia " not in f" {out} "
    out2 = z._fake_street("100 Centerview Drive, Suite 205, Birmingham, Alabama 35216")
    assert "Alabama" in out2 and " ma " not in f" {out2} "


# P1  House standard (and the repo owner): do NOT fake city, state, or ZIP.
#   Only the street number, street name, and unit change. Keeping the locality
#   also removes every state-corruption and city-drift failure at the source.
def test_city_state_zip_preserved_verbatim():
    z = _pz()
    for real, city, state, zipc in [
        ("414 S. Maple Ave., Montebello, California 90640", "Montebello", "California", "90640"),
        ("414 S. Maple Ave. Montebello, CA 90640", "Montebello", "CA", "90640"),
        ("100 Centerview Drive, Suite 205, Birmingham, Alabama 35216", "Birmingham", "Alabama", "35216"),
    ]:
        out = z._fake_street(real)
        assert city in out, f"city {city!r} was altered in {out!r}"
        assert re.search(rf"\b{state}\b", out), f"state {state!r} was altered in {out!r}"
        assert zipc in out, f"ZIP {zipc!r} was altered in {out!r}"


# P1  One parcel, however spelled, gets exactly one fake street.
#   Delivered key mapped 414 S. Maple to Cypress, Birch, Linden AND Tamarack.
def test_one_parcel_one_street_fake():
    z = _pz()
    spellings = [
        "414 S. Maple Ave.",
        "414 S. Maple Ave. Montebello, CA 90640",
        "414 S. Maple Ave., Montebello, California 90640",
    ]
    def street_of(s):
        # leading "<number> <name>" of the faked street, ignoring any tail
        m = re.match(r"\s*(\d[\d\-\u2013\u2014]*\s+[A-Za-z]+)", z._fake_street(s))
        return m.group(1) if m else z._fake_street(s)
    fakes = {street_of(s) for s in spellings}
    assert len(fakes) == 1, f"one parcel produced multiple street fakes: {fakes}"


# P1  A hyphenated unit range is the same parcel as its base number.
def test_unit_range_matches_base_parcel():
    z = _pz()
    base = re.split(r",", z._fake_street("414 S. Maple Ave."))[0]
    rng = re.split(r",", z._fake_street("414-416 S. Maple Ave."))[0]
    # same faked street NAME (the range may keep a range in the number)
    name = lambda s: re.sub(r"^[\d\-\u2013\u2014 ]+", "", s).strip()
    assert name(base) == name(rng), f"{base!r} vs {rng!r} disagree on street name"


# P2  Distinct real e-mail domains must map to distinct fakes (injective).
#   Delivered key collapsed gmail.com, yahoo.com and the firm domain all onto
#   letterbox.co, implying opposing parties shared an e-mail domain.
def test_email_domains_injective():
    hosts = ["gmail.com", "yahoo.com", "schillecitortoricilaw.com",
             "themillenniallawyer.com", "outlook.com"]
    fakes = [P._pn_fake_domain(h) for h in hosts]
    assert len(set(fakes)) == len(hosts), (
        f"domain map is not injective: {dict(zip(hosts, fakes))}")


# P2  Public consumer providers carry no identity and should pass through.
#   (Recommendation — delete this test if the firm prefers to fake them, but
#   then test_email_domains_injective still governs uniqueness.)
def test_public_email_providers_preserved():
    for h in ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"]:
        assert P._pn_fake_domain(h) == h, f"public provider {h} was faked"


# P2  The macro-reversible key must not carry rows that matched nothing.
#   ReAnonymize runs the key in reverse and will replace a Real Value that was
#   never in the documents. Build terms, apply to text that hits ONLY some of
#   them, write the key, and assert no surviving "no match" rows.
def test_reversal_key_has_no_zero_occurrence_rows(tmp_path):
    z = _pz(names=["Roxane Estrada", "Azul Concreto, Inc.", "Someone Neverpresent"])
    z.apply("Plaintiff Roxane Estrada sued Azul Concreto, Inc. in 25STCV37838.")
    out = tmp_path / "pseudonym_key.xlsx"
    z.write_key(out, log)
    wb = openpyxl.load_workbook(out)
    ws = wb.active
    header = [c.value for c in next(ws.iter_rows(max_row=1))]
    occ_i = header.index("Occurrences")
    zero = [r for r in ws.iter_rows(min_row=2, values_only=True)
            if r[occ_i] in (0, None)]
    assert not zero, f"{len(zero)} zero-occurrence row(s) in the reversal key"
    # The full report is a separate "pseudonym audit.xlsx" (trailing "key"
    # dropped), kept out of anything that circulates with the document.
    assert (tmp_path / "pseudonym audit.xlsx").exists()
    assert not (tmp_path / "pseudonym_key audit.xlsx").exists()


# P1  Every name in a phone-roster block must be harvested, not just the first.
#   Delivered FAC leaked `Juan Olivas` and `Viviana Gomez` (only `Jose Gomez`
#   was caught by the CONTRACTORS: label).
def test_contractor_roster_all_names_harvested():
    block = ("CONTRACTORS:\n"
             "Jose Gomez (323) 283-4603\n"
             "Juan Olivas (562) 239-8134\n"
             "Viviana Gomez (562) 456-6420 office\n")
    got = P._pn_label_names(block)
    for n in ("Jose Gomez", "Juan Olivas", "Viviana Gomez"):
        assert n in got, f"{n!r} not harvested from the roster: {got}"


# P1  Same-person aliases faked with unrelated surnames are surfaced (not
#   silently merged) so a reviewer can link them. Delivered set faked Roxane's
#   Estrada/Guzman/Purscelley names as three unrelated surnames.
def test_alias_candidates_surfaced():
    z = _pz(names=["Roxane Estrada", "Roxane Guzman", "Jason Tortorici"])
    flat = {n for grp in z.alias_candidates() for n in grp}
    assert {"Roxane Estrada", "Roxane Guzman"} <= flat
    assert "Jason Tortorici" not in flat   # unique given name — never flagged


# ─────────────────────────── GUARD (green now) ──────────────────────────────
# Behavior that is already correct; these must stay green through the fixes.

def test_guard_venue_city_not_scrubbed():
    # "Los Angeles" as a county/venue is locality, never a party.
    assert P._pn_is_protected_locality("Los Angeles")
    assert P._pn_is_protected_locality("Los Angeles County")


def test_guard_caseno_filing_year_kept():
    reg = P._PnFakeRegistry()
    fake = reg.digits("25STCV37838", "case_number", keep_prefix=2)
    assert fake.startswith("25") and fake != "25STCV37838"


def test_guard_reservation_id_is_faked_digitwise():
    reg = P._PnFakeRegistry()
    fake = reg.digits("935605884885", "reservation_id")
    assert fake != "935605884885" and fake.isdigit() and len(fake) == 12
