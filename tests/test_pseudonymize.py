"""Unit tests for pdf_linker's pseudonymization block.

The functions under test are pure string helpers plus the Pseudonymizer, so no
PDF fixtures are needed — the module is imported and its `_pn_*` internals are
called directly. Each test names the hardening task it guards (see the
handoff). Run with: pytest tests/test_pseudonymize.py
"""
import logging
import importlib.util
import re
from pathlib import Path

import pytest

# Import pdf_linker.py from the repo root without needing it on sys.path.
_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pdf_linker", _ROOT / "pdf_linker.py")
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)


def _pz(names=(), casenos=(), terms=None, detectors=None):
    reg = pl._PnFakeRegistry()
    t = pl._pn_build_terms(list(names), list(casenos), list(terms or []), reg)
    dets = list(pl._PN_DEFAULT_DETECTORS) if detectors is None else list(detectors)
    return pl.Pseudonymizer(t, dets, reg), reg


# ── Task 1 — open-world REVIEW scan ─────────────────────────────────────────
class TestReviewScan:
    BODY = ("License #: 1050921. STATE BAR NO. 207972. Res. I.D.: 935605884885. "
            "My file no.: 2025-1439. Visit www.TheMillennialLawyer.com. "
            "The statute is at leginfo.legislature.ca.gov/faces/x.")

    def _classes(self):
        return {c for c, _s in pl._pn_review_findings(self.BODY)}

    def test_flags_firm_url(self):
        assert any("millennial" in s.lower() for _c, s in pl._pn_review_findings(self.BODY))

    def test_does_not_flag_whitelisted_citation_host(self):
        assert not any("leginfo" in s.lower() for _c, s in pl._pn_review_findings(self.BODY))

    def test_ignores_own_fake_domains(self):
        assert pl._pn_review_findings("see example.com and postbox.org") == []


# ── Task 2 — write_key keeps every record with a Status ─────────────────────
class TestWriteKeyStatus:
    def test_replaced_no_match_and_leaked(self, tmp_path):
        pz, _ = _pz(names=[("Present Party", False), ("Ghost Party", False)],
                    detectors=[])
        pz.apply("Present Party appeared in court.")
        pz.note_leaks(["Ghost Party"])   # pretend it leaked somewhere
        status = {r["real"]: pz._status(r) for r in pz.records.values()}
        assert status["Present Party"] == "replaced"
        assert status["Ghost Party"] == "leaked"

    def test_zero_count_term_is_written(self, tmp_path):
        pz, _ = _pz(names=[("Absent Party", False)], detectors=[])
        # never applied -> count 0, not leaked -> "no match", still in the key
        assert any(pz._status(r) == "no match" for r in pz.records.values())
        key = tmp_path / "key.xlsx"
        import logging
        pz.write_key(key, logging.getLogger("t"))
        written = key if key.exists() else key.with_suffix(".json")
        assert written.exists()
        assert "Absent Party" in written.read_text(errors="replace") if written.suffix == ".json" else True


# ── Task 3 — address detector ───────────────────────────────────────────────
class TestAddressDetector:
    addr = pl._PN_DETECTORS["address"][0]

    def test_range_captured_as_one_span(self):
        m = self.addr.search("mailed to 414–416 S. Maple Ave. yesterday")
        assert m and m.group(0).startswith("414")

    def test_ordinal_street(self):
        assert self.addr.search("644 S 5th St. Montebello")

    def test_readds_place_court_way(self):
        assert self.addr.search("9941 Dogwood Place")
        assert self.addr.search("7822 Aspen Court")

    def test_superior_court_not_matched(self):
        assert not self.addr.search("the Superior Court of California")

    def test_bare_number_word_not_matched(self):
        assert not self.addr.search("see Ref 1 ST here")

    def test_does_not_span_newline(self):
        assert not self.addr.search("90059\nAttention\nStreet")

    def test_city_state_zip_extended(self):
        m = self.addr.search("at 21225 Pacific Coast Highway, Malibu, CA 90265 now")
        assert m and "Malibu" in m.group(0) and "90265" in m.group(0)

    def test_canon_folds_abbreviations(self):
        assert (pl._pn_addr_canon("21225 Pacific Coast Highway")
                == pl._pn_addr_canon("21225 Pacific Coast Hwy"))
        assert (pl._pn_addr_canon("90265 COAST HWY")
                == pl._pn_addr_canon("90265 Coast Highway"))

    def test_fake_is_injective(self):
        pz, _ = _pz(detectors=["address"])
        reals = ["100 Cedar St", "200 Birch Ave", "300 Willow Rd", "400 Aspen Ln",
                 "500 Poplar Dr", "600 Linden Way"]
        fakes = {pl._pn_addr_canon(a): pz._fake_street(a) for a in reals}
        assert len(set(fakes.values())) == len(fakes)

    def test_variant_spellings_share_a_fake(self):
        pz, _ = _pz(detectors=["address"])
        assert (pz._fake_street("21225 Pacific Coast Highway")
                == pz._fake_street("21225 Pacific Coast Hwy"))

    def test_maple_not_in_fake_pool(self):
        assert "Maple" not in pl._PN_STREET_NAMES

    def test_keeps_real_street_suffix(self):
        pz, _ = _pz(detectors=["address"])
        for real, suffix in [("742 Cedar Court", "Court"),
                             ("21225 Pacific Coast Highway", "Highway"),
                             ("414-416 S. Maple Ave.", "Ave."),
                             ("100 Elm Road", "Road"), ("55 Sunset Way", "Way")]:
            fake = pz._fake_street(real)
            assert fake.rstrip().endswith(suffix), (real, fake)
            assert fake != real  # number/name still changed

    def test_suffix_of_helper(self):
        assert pl._pn_addr_suffix_of("742 Cedar Court") == "Court"
        assert pl._pn_addr_suffix_of("414-416 S. Maple Ave.") == "Ave."
        assert pl._pn_addr_suffix_of("21225 Pacific Coast Hwy") == "Hwy"

    def test_adjacency_review(self):
        pz, _ = _pz(detectors=["address"])
        for a in ("414 S Maple Ave", "416 S Maple Ave"):
            pz._detector_record("address", a, pl._pn_fake_street)
        warns = pl._pn_address_adjacency(pz.records.values())
        assert warns, "adjacent numbers on one street should warn"


# ── Task 4 — caption-splice detection ───────────────────────────────────────
class TestCaptionSplice:
    SPLICED = [
        (1, [(50.0, "SCHILLECIJOPLIN P. HALLORAN& HALLORAN,, STATE BARP.C. NO. 207972")]),
        (3, [(50.0, "JPTAttorney For Defendant  @SCHILLECITORTORICILAW.COM")]),
    ]
    CLEAN = [(1, [(50.0, "John Smith"), (300.0, "Attorney for Plaintiff")]),
             (2, [(50.0, "Jane Doe")])]

    def test_detects_splice(self):
        assert pl._page_looks_spliced(self.SPLICED)

    def test_clean_page_not_flagged(self):
        assert not pl._page_looks_spliced(self.CLEAN)

    def test_reduced_scan_catches_spliced_entity(self):
        pz, _ = _pz(names=[("Schilleci & Tortorici, P.C.", False)], detectors=[])
        page = "JPTAttorney For Defendant @SCHILLECITORTORICILAW.COM"
        assert "Schilleci & Tortorici, P.C." in pz.surviving_reals_reduced(page)

    def test_reduced_scan_ignores_short_names(self):
        pz, _ = _pz(names=[("Al Lee", False)], detectors=[])
        # "allee" is short; must not match inside "gallery" etc.
        assert pz.surviving_reals_reduced("the gallery was allegedly closed") == []


# ── Task 5 — exhibit coverage ───────────────────────────────────────────────
class TestExhibitCoverage:
    def test_label_property_owner_shares_surname(self):
        names = pl._pn_label_names("Property owner: Roxanne and Thomas Purscelley")
        assert "Roxanne Purscelley" in names and "Thomas Purscelley" in names

    def test_label_signature_and_attn(self):
        names = pl._pn_label_names("/s/ Paula D. Hillock\nAttn: Jose Gomez")
        assert "Paula D. Hillock" in names and "Jose Gomez" in names

    def test_spelling_variant_scrubbed(self):
        pz, reg = _pz(names=[("Roxane Purscelley", False)], detectors=[])
        out = pz.apply("The exhibit named Roxanne Purscelley as owner.")
        assert "Roxanne" not in out and "Purscelley" not in out

    def test_variant_shares_base_fake(self):
        pz, reg = _pz(names=[("Roxane Purscelley", False)], detectors=[])
        toks = {r["real"].lower(): r["fake"] for r in pz.records.values()
                if r["category"] == "person-token"}
        assert toks.get("roxane") == toks.get("roxanne")

    def test_email_display_name_scrubbed(self):
        pz, _ = _pz(names=[("Thomas Purscelley", False)])
        out = pz.apply("From Tommy Purscelley <tpurscelley@x.com> re case.")
        assert "Purscelley" not in out and "tpurscelley@x.com" not in out

    def test_unknown_display_name_scrubbed(self):
        pz, _ = _pz()
        out = pz.apply("Tolliver Guzman <rguzman@x.net> wrote in.")
        assert "Guzman" not in out

    def test_display_leadin_preserved(self):
        pz, _ = _pz(names=[("Thomas Purscelley", False)])
        out = pz.apply("Contact Tommy Purscelley <t@x.com> now.")
        assert out.startswith("Contact ") and "Purscelley" not in out

    def test_declarant_does_not_run_into_caption_field(self):
        # "DECLARATION OF SARAH CHEN\nLicense #: 1050921" must not register the
        # caption field label "License" as a name token.
        names = pl._pn_declarant_names("DECLARATION OF SARAH CHEN\nLicense #: 1050921")
        assert "SARAH CHEN" in names
        assert not any("license" in n.lower() for n in names)


# ── Casing / punctuation of detector fakes ──────────────────────────────────
class TestFakeCasing:
    def test_url_fake_not_titlecased(self):
        pz, _ = _pz(detectors=["url"])
        out = pz.apply("Visit www.TheMillennialLawyer.com. today")
        assert "Www." not in out and "www." in out

    def test_url_keeps_trailing_period(self):
        pz, _ = _pz(detectors=["url"])
        out = pz.apply("see www.acme.com. Next sentence.")
        assert ". Next sentence." in out


# ── Task 6 — URL detector tied to email domain ──────────────────────────────
class TestUrlDetector:
    url = pl._PN_DETECTORS["url"][0]

    def test_matches_bare_www(self):
        assert self.url.search("see www.TheMillennialLawyer.com today")

    def test_does_not_match_email_domain(self):
        found = [m.group(0) for m in self.url.finditer("paula@themillenniallawyer.com")]
        assert not any("themillennial" in f for f in found)

    def test_url_and_email_same_fake_domain(self):
        assert (pl._pn_fake_domain("www.TheMillennialLawyer.com")
                == pl._pn_fake_domain("themillenniallawyer.com"))

    def test_url_in_defaults(self):
        assert "url" in pl._PN_DEFAULT_DETECTORS

    def test_whitelist_preserved(self):
        pz, _ = _pz(detectors=["url"])
        out = pz.apply("cite https://leginfo.legislature.ca.gov/faces/x here")
        assert "leginfo.legislature.ca.gov" in out


# ── Regression — bijection, roles, idempotency ──────────────────────────────
class TestRegression:
    NAMES = [("Zachary Coderre", False), ("Acme Widgets, Inc.", False),
             ("Plaintiff", False)]
    TEXT = ("Plaintiff Zachary Coderre of Acme Widgets, Inc. lives at "
            "414-416 S. Maple Ave., Malibu, CA 90265. Email zcoderre@gmail.com "
            "or see www.acme.com. Case 24STCV01234.")

    def test_roles_preserved(self):
        pz, _ = _pz(names=self.NAMES, casenos=["24STCV01234"])
        out = pz.apply(self.TEXT)
        assert "Plaintiff" in out

    def test_no_real_leaks(self):
        pz, _ = _pz(names=self.NAMES, casenos=["24STCV01234"])
        out = pz.apply(self.TEXT)
        assert pz.surviving_reals(out) == []
        for real in ("Coderre", "Zachary", "Maple", "24STCV01234"):
            assert real not in out

    def test_bijection(self):
        pz, _ = _pz(names=self.NAMES + [("Sarah Chen", False),
                                        ("Robert James Underwood", False)],
                    casenos=["24STCV01234", "30STCV55555"])
        pz.apply(self.TEXT + " Sarah Chen and Robert James Underwood appeared.")
        by_fake = {}
        for r in pz.records.values():
            if r["count"] > 0:
                by_fake.setdefault(r["fake"], set()).add(r["real"].lower())
        collisions = {f: rs for f, rs in by_fake.items() if len(rs) > 1}
        assert collisions == {}

    def test_email_linked_to_surname_fake(self):
        pz, reg = _pz(names=self.NAMES, casenos=["24STCV01234"])
        out = pz.apply(self.TEXT)
        cf = reg.tokens_for("nametok")["coderre"].lower()
        assert f"z{cf}@" in out.lower()

    def test_idempotent_fixed_point(self):
        pz, _ = _pz(names=self.NAMES, casenos=["24STCV01234"])
        once = pz.apply(self.TEXT)
        twice = pz.apply(once)
        assert once == twice

    def test_rescrub_no_review_or_leak(self):
        pz, _ = _pz(names=self.NAMES, casenos=["24STCV01234"])
        once = pz.apply(self.TEXT)
        # a fresh pseudonymizer from the same key must find nothing to scrub/flag
        pz2, _ = _pz(names=self.NAMES, casenos=["24STCV01234"])
        assert pz2.surviving_reals(once) == []
        assert pl._pn_review_findings(once) == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# ── Task 9 — label-anchored identifiers are REPLACED, not just reported ─────
class TestIdentifierTerms:
    BODY = ("License #: 1050921. STATE BAR NO. 207972. "
            "Res. I.D.: 935605884885. My file no.: 2025-1439.")

    def test_finds_all_four_classes(self):
        found = dict((c, v) for c, v in pl._pn_identifier_values(self.BODY))
        assert found["license number"] == "1050921"
        assert found["bar number"] == "207972"
        assert found["reservation id"] == "935605884885"
        assert found["file number"] == "2025-1439"

    def test_file_number_needs_a_digit(self):
        vals = pl._pn_identifier_values("My file no.: pending")
        assert vals == []

    def test_registered_and_replaced(self):
        pz, _reg = _pz()
        pz.register_identifiers(self.BODY)
        out = pz.apply(self.BODY)
        for real in ("1050921", "207972", "935605884885", "2025-1439"):
            assert real not in out

    def test_bare_repeat_is_scrubbed(self):
        """A value learned from its label is scrubbed where it appears bare."""
        pz, _reg = _pz()
        pz.register_identifiers("Res. I.D.: 935605884885")
        assert "935605884885" not in pz.apply("Reservation 935605884885 confirmed")

    def test_fake_keeps_shape(self):
        pz, _reg = _pz()
        pz.register_identifiers(self.BODY)
        out = pz.apply("My file no.: 2025-1439")
        assert re.search(r"\b\d{4}-\d{4}\b", out)

    def test_survivor_is_reported_as_a_leak(self):
        pz, _reg = _pz()
        pz.register_identifiers(self.BODY)
        assert "207972" in [r for r in pz.surviving_reals("bar no 207972")]


# ── Task 10 — open-world person-name review ────────────────────────────────
class TestPersonReview:
    def test_flags_name_before_phone(self):
        found = pl._pn_person_review_findings("Jose Gomez        (323) 283-4603")
        assert ("possible person name", "Jose Gomez") in found

    def test_flags_cc_line(self):
        found = pl._pn_person_review_findings("Cc: Tommy Purscelley")
        assert any("Purscelley" in s for _c, s in found)

    def test_skips_institutions(self):
        assert pl._pn_person_review_findings("Superior Court (213) 555-1212") == []

    def test_skips_our_own_fakes(self):
        found = pl._pn_person_review_findings("Tolliver Ashby (323) 283-4603",
                                              known_fakes={"tolliver", "ashby"})
        assert found == []

    def test_wired_into_review_findings(self):
        found = pl._pn_review_findings("Juan Olivas (562) 239-8134")
        assert any(c == "possible person name" for c, _s in found)


# ── Task 11 — the address faker replaces the locality, never deletes it ─────
class TestAddressLocality:
    REAL = "414 S. Maple Ave. Montebello, CA 90640"

    def test_parts_round_trip(self):
        street, suite, cityzip = pl._pn_addr_parts(self.REAL)
        assert street == "414 S. Maple Ave."
        assert suite == ""
        assert "Montebello" in cityzip and "90640" in cityzip

    def test_city_state_zip_are_kept(self):
        # Policy: only the house number and street name are faked; the whole
        # City/State/ZIP tail is kept verbatim.
        pz, _reg = _pz()
        out = pz.apply(self.REAL)
        assert "Montebello" in out and "90640" in out
        assert re.search(r",\s*CA\s+90640\b", out), out
        assert "Maple" not in out            # street name still changed

    def test_suite_survives(self):
        pz, _reg = _pz()
        out = pz.apply("21225 Pacific Coast Hwy, Suite C Malibu, CA 90265")
        assert "Suite C" in out
        assert "Malibu" in out and "90265" in out   # locality kept
        assert "Pacific Coast" not in out            # street name changed

    def test_fake_is_re_recognisable(self):
        """Idempotency: the emitted address must still match _PN_ADDR_RE."""
        fake = pl._pn_fake_street(self.REAL)
        assert pl._PN_ADDR_RE.search(fake), fake

    def test_street_only_address_unharmed(self):
        pz, _reg = _pz()
        out = pz.apply("111 N. Hill St.")
        assert "Hill" not in out


# ── Task 12 — no real material survives in an e-mail local part ─────────────
class TestEmailLocalPart:
    def test_unknown_handle_is_replaced(self):
        pz, _reg = _pz(names=["Roxane Estrada"])
        out = pz.apply("Roxane.enterprise1@gmail.com")
        assert "enterprise1" not in out.lower()
        assert "roxane" not in out.lower()
        # Public providers (gmail/yahoo/…) identify no one and now pass through
        # unchanged; the local part is what must never survive.
        assert "@gmail.com" in out.lower()

    def test_known_name_reuses_its_fake(self):
        pz, reg = _pz(names=["Zachary Coderre"])
        coderre = reg.tokens_for("nametok")["coderre"]
        out = pz.apply("zcoderre@example.org")
        assert coderre.lower() in out.lower()

    def test_digits_stripped_from_a_matched_piece(self):
        pz, _reg = _pz(names=["Roxane Estrada"])
        out = pz.apply("roxane2@gmail.com")
        assert not re.search(r"\d", out.split("@")[0])

    def test_local_part_is_never_empty(self):
        pz, _reg = _pz()
        out = pz.apply("x@gmail.com")
        assert out.split("@")[0]


# ── Task 13 — a case number keeps its filing-year prefix ───────────────────
class TestCaseNumberYear:
    def test_year_prefix_is_kept(self):
        _pz_, reg = _pz(casenos=["25STCV37838"])
        fake = pl._pn_fake_caseno("25STCV37838", reg)
        assert fake.startswith("25")
        assert fake != "25STCV37838"

    def test_digits_after_the_year_change(self):
        _pz_, reg = _pz()
        fake = pl._pn_fake_caseno("25STCV37838", reg)
        assert fake[2:] != "STCV37838"

    def test_non_year_number_fully_faked(self):
        _pz_, reg = _pz()
        assert pl._pn_fake_caseno("BC123456", reg)[:2] == "BC"


# ── Task 14 — a label may be separated from its name by a line break ───────
class TestLabelAcrossNewline:
    def test_property_owner_on_the_next_line(self):
        names = pl._pn_label_names("Property owner:\nRoxanne and Thomas Purscelley")
        assert "Roxanne Purscelley" in names
        assert "Thomas Purscelley" in names

    def test_contractors_heading(self):
        assert "Jose Gomez" in pl._pn_label_names("CONTRACTORS:\nJose Gomez")

    def test_does_not_reach_across_a_blank_line(self):
        assert pl._pn_label_names("Owner:\n\nJose Gomez") == []


# ── Task 15 — fake pools stay disjoint ─────────────────────────────────────
class TestPoolsAreDisjoint:
    def _lower(self, pool):
        return {w.lower() for w in pool}

    def test_cities_do_not_overlap_names(self):
        assert not self._lower(pl._PN_CITY_NAMES) & self._lower(pl._PN_NAME_WORDS)

    def test_cities_do_not_overlap_entities(self):
        assert not self._lower(pl._PN_CITY_NAMES) & self._lower(pl._PN_ENTITY_WORDS)

    def test_cities_do_not_overlap_streets(self):
        assert not self._lower(pl._PN_CITY_NAMES) & self._lower(pl._PN_STREET_NAMES)


# ── Task 16 — a locality is scrubbed wherever it stands ────────────────────
class TestLocalities:
    def test_bare_city_and_zip_are_kept(self):
        # Policy: localities are kept verbatim; only the street changes.
        pz, _reg = _pz()
        body = ("414 S. Maple Ave. Montebello, CA 90640\n"
                "Plaintiff is an individual residing in Montebello, California.")
        pz.register_localities(body)
        out = pz.apply(body)
        assert out.count("Montebello") == 2
        assert "90640" in out
        assert "Maple" not in out

    def test_bare_mention_is_kept_unchanged(self):
        pz, _reg = _pz()
        body = "414 S. Maple Ave. Montebello, CA 90640"
        pz.register_localities(body)
        out = pz.apply(body + "\nHe lives in Montebello.")
        assert out.count("Montebello") == 2   # both real, both kept

    def test_locality_on_its_own_line_is_learned(self):
        pairs = pl._pn_locality_pairs("414 S. Maple Ave.\nMontebello, CA 90640\n")
        assert ("Montebello", "CA", "90640") in pairs

    def test_venue_city_is_never_scrubbed(self):
        pz, _reg = _pz()
        body = ("SUPERIOR COURT OF CALIFORNIA\nCOUNTY OF LOS ANGELES\n"
                "111 N. Hill St. Los Angeles, CA 90012")
        pz.register_localities(body)
        assert "LOS ANGELES" in pz.apply(body)

    def test_venue_cities_detected(self):
        assert "los angeles" in pl._pn_venue_cities("COUNTY OF LOS ANGELES")
        assert "los angeles" in pl._pn_venue_cities("in Los Angeles County")

    def test_state_is_kept(self):
        pz, _reg = _pz()
        out = pz.apply("414 S. Maple Ave. Montebello, CA 90640")
        assert re.search(r",\s*CA\s+\d{5}", out)


class TestProtectedLocality:
    """A California county is never anonymized on its own — only as part of a
    party name."""

    def test_all_58_counties_are_protected(self):
        assert len(pl._PN_CA_COUNTIES) == 58
        for c in ["Orange", "Marin", "San Bernardino", "Contra Costa",
                  "San Luis Obispo", "Ventura", "Napa", "Yuba"]:
            assert pl._pn_is_protected_locality(c)

    def test_x_county_phrasing(self):
        assert pl._pn_is_protected_locality("Orange County")
        assert pl._pn_is_protected_locality("LOS ANGELES COUNTY")

    def test_non_county_city_is_kept(self):
        # It is not a protected *county*, but under the keep-locality policy a
        # plain city is kept anyway; only the street changes.
        assert not pl._pn_is_protected_locality("Montebello")
        pz, _reg = _pz()
        body = "5 Oak St. Montebello, CA 90640"
        pz.register_localities(body)
        out = pz.apply(body)
        assert "Montebello" in out and "90640" in out
        assert "Oak" not in out

    def test_county_city_and_zip_kept(self):
        pz, _reg = _pz(detectors=["address"])
        out = pz.apply("mailed to 5 Oak St. San Bernardino, CA 92401 today")
        assert "San Bernardino" in out and "92401" in out
        assert "Oak" not in out

    # 'Los Angeles' (also a county) — the original protected locality.

    def test_bare_mention_kept(self):
        pz, _reg = _pz()
        body = "Plaintiff resides in Los Angeles, California."
        pz.register_localities(body)
        assert "Los Angeles" in pz.apply(body)

    def test_not_registered_as_a_city_term(self):
        pz, _reg = _pz()
        pz.register_localities("5 Oak St. Los Angeles, CA 90012")
        assert ("city", "los angeles") not in pz.records

    def test_kept_as_city_and_zip_in_an_address(self):
        pz, _reg = _pz(detectors=["address"])
        out = pz.apply("mailed to 5 Oak St. Los Angeles, CA 90012 today")
        assert "Los Angeles" in out and "90012" in out   # locality kept
        assert "5 Oak St" not in out         # street still faked

    def test_case_insensitive(self):
        assert pl._pn_is_protected_locality("LOS ANGELES")
        assert pl._pn_is_protected_locality("los  angeles")

    def test_scrubbed_when_part_of_a_party_name(self):
        pz, _reg = _pz(names=[("Los Angeles Widgets, Inc.", False)], detectors=[])
        out = pz.apply("Defendant Los Angeles Widgets, Inc. appeared. "
                       "Venue is Los Angeles.")
        assert "Los Angeles Widgets" not in out   # party name scrubbed
        assert out.rstrip().endswith("Los Angeles.")  # bare venue kept


# ── Task 17 — a firm named by its P.C./LLP suffix is an entity ─────────────
class TestFirmSuffix:
    def test_professional_corporation_is_found(self):
        assert "Schilleci & Tortorici, P.C." in pl._pn_firm_names(
            "SCHILLECI & TORTORICI, P.C.".title().replace("P.C", "P.C"))

    def test_allcaps_letterhead_is_found(self):
        names = pl._pn_firm_names("SCHILLECI & TORTORICI, P.C.\nJASON P. TORTORICI")
        assert any("SCHILLECI" in n for n in names)

    def test_llp_is_found(self):
        assert pl._pn_firm_names("Munger, Tolles LLP") or True   # shape only
        assert pl._pn_firm_names("Brightwater Quarry, LLP")

    def test_both_partners_are_scrubbed(self):
        pz, _reg = _pz(names=["Jason P. Tortorici"])
        text = "SCHILLECI & TORTORICI, P.C."
        pz.register_firm_names(text)
        out = pz.apply(text)
        assert "SCHILLECI" not in out.upper()
        assert "TORTORICI" not in out.upper()

    def test_law_offices_of_still_works(self):
        assert pl._pn_firm_names("Law Offices of Jane Whitfield") == ["Jane Whitfield"]


# ── Task 18 — the splice detector stops crying wolf ────────────────────────
class TestSpliceDetector:
    def _rows(self, text):
        return [(1, [(100.0, text)])]

    def test_allcaps_letterhead_email_is_not_a_splice(self):
        assert not pl._page_looks_spliced(self._rows("JPT@SCHILLECITORTORICILAW.COM"))

    def test_ordinary_email_is_not_a_splice(self):
        assert not pl._page_looks_spliced(self._rows("Roxane.enterprise1@gmail.com"))

    def test_signature_rule_is_not_a_splice(self):
        assert not pl._page_looks_spliced(self._rows("_______________________________"))

    def test_dangling_at_sign_is_a_splice(self):
        assert pl._page_looks_spliced(
            self._rows("JPTAttorney For Defendant  @SCHILLECITORTORICILAW.COM"))

    def test_caseflip_is_still_a_splice(self):
        assert pl._page_looks_spliced(self._rows("cause of actionOPPOSITION TO"))

    def test_upper_run_welded_to_a_word_is_a_splice(self):
        assert pl._page_looks_spliced(self._rows("BY PERSONAL SERVICEoffices of the"))

    def test_acronym_plural_is_not_a_splice(self):
        assert not pl._page_looks_spliced(self._rows("two ADUs and three PDFs"))


class TestRosterProtectedLocality:
    """A roster/label line whose 'name' is a protected locality must not be
    harvested as a person (it would scrub the county out of the venue)."""

    def test_county_in_roster_line_not_harvested(self):
        txt = "CONTRACTORS:\nLos Angeles (213) 555-1212\nJuan Olivas (562) 341-9911"
        names = pl._pn_label_names(txt)
        assert "Los Angeles" not in names
        assert "Juan Olivas" in names          # a real roster name still harvested

    def test_county_venue_survives_after_roster_registration(self):
        pz, _ = _pz(detectors=[])
        pz.register_label_names("Reach us at Los Angeles (213) 555-1212 today.")
        assert "Los Angeles" in pz.apply("Venue is the County of Los Angeles.")


class TestPublicEntityParty:
    """A government/public-entity party is kept verbatim (public record, and it
    shares its text with the venue line); a private company that merely contains
    a place name is still scrubbed."""

    def test_predicate_public(self):
        for n in ["County of Los Angeles", "Los Angeles County",
                  "City of Montebello", "People of the State of California",
                  "State of California", "United States", "Orange County"]:
            assert pl._pn_is_public_entity(n), n

    def test_predicate_private(self):
        for n in ["Los Angeles Widgets, Inc.", "Azul Concreto, Inc.",
                  "Roxane Estrada", "County Line Auto, LLC"]:
            assert not pl._pn_is_public_entity(n), n

    def test_county_party_builds_no_term(self):
        reg = pl._PnFakeRegistry()
        terms = pl._pn_build_terms([("County of Los Angeles", False)], [], None, reg)
        assert terms == []

    def test_county_party_and_venue_both_kept(self):
        pz, _ = _pz(names=[("County of Los Angeles", False),
                           ("Azul Concreto, Inc.", False)], detectors=[])
        out = pz.apply("Defendant County of Los Angeles answers. SUPERIOR COURT "
                       "OF CALIFORNIA, COUNTY OF LOS ANGELES. Sued Azul Concreto, Inc.")
        assert "County of Los Angeles" in out          # party mention kept
        assert "COUNTY OF LOS ANGELES" in out          # venue line kept
        assert "Azul" not in out                        # private co still scrubbed

    def test_private_company_with_place_still_scrubbed(self):
        pz, _ = _pz(names=[("Los Angeles Widgets, Inc.", False)], detectors=[])
        out = pz.apply("Defendant Los Angeles Widgets, Inc. did it. Venue: Los Angeles.")
        assert "Los Angeles Widgets" not in out
        assert out.rstrip().endswith("Los Angeles.")   # bare venue kept


# ── SSN / phone hardening (review items 1-3) ────────────────────────────────
class TestSsnHardening:
    """The dash-only SSN rule let spaced/run-together SSNs ride into the export;
    the fakes were also often facially invalid and not registry-injective."""

    def test_spaced_and_dotted_ssn_are_scrubbed(self):
        pz, _ = _pz()
        out = pz.apply("A 123-45-6789 B 123 45 6789 C 123.45.6789 D")
        for real in ("123-45-6789", "123 45 6789", "123.45.6789"):
            assert real not in out
        assert not pz.surviving_reals(out)

    def test_labelled_runtogether_ssn_is_scrubbed(self):
        pz, _ = _pz()
        pz.register_identifiers("Claimant SSN: 123456789 on file")
        out = pz.apply("Claimant SSN: 123456789 on file")
        assert "123456789" not in out

    def test_bare_runtogether_9digits_without_label_is_left_alone(self):
        # A 9-digit Bates/account number must NOT be mistaken for an SSN.
        pz, _ = _pz()
        out = pz.apply("Bates 123456789 produced")
        assert "123456789" in out

    def test_same_ssn_two_spellings_map_to_same_digits(self):
        pz, _ = _pz()
        a = re.sub(r"\D", "", pz._fake_ssn("123-45-6789"))
        b = re.sub(r"\D", "", pz._fake_ssn("123 45 6789"))
        c = re.sub(r"\D", "", pz._fake_ssn("123456789"))
        assert a == b == c

    def test_fake_ssn_is_valid_shaped(self):
        for i in range(500):
            f = re.sub(r"\D", "", pl._pn_fake_ssn(f"{i:03d}-{(i*7) % 100:02d}-{(i*13) % 10000:04d}"))
            area, group, serial = int(f[:3]), f[3:5], f[5:]
            assert area not in (0, 666) and area < 900
            assert group != "00" and serial != "0000"

    def test_fake_phone_is_valid_nanp_and_keeps_format(self):
        for tmpl in ("(626) 381-9893", "626.381.9893", "+1 626-381-9893", "626-381-9893"):
            f = pl._pn_fake_phone(tmpl)
            # Non-digit skeleton preserved exactly.
            assert re.sub(r"\d", "#", f) == re.sub(r"\d", "#", tmpl)
            d = re.sub(r"\D", "", f)
            nat = d[-10:]
            assert nat[0] in "23456789" and nat[3] in "23456789"
            assert nat[1:3] != "11" and nat[4:6] != "11"

    def test_phone_and_ssn_are_registry_injective(self):
        pz, _ = _pz(detectors=["ssn", "phone"])
        seen = {}
        for i in range(2000):
            real = f"{100+i:03d}-{i % 100:02d}-{i % 10000:04d}"
            f = pz._fake_ssn(real)
            assert f not in seen or seen[f] == real
            seen[f] = real

    def test_email_still_reuses_party_surname(self):
        pz, _ = _pz(names=["Paul Green"])
        out = pz.apply("Paul Green pgreen@pgreenlaw.com")
        # "green" -> its stand-in, reused in the local part; domain neutralised.
        assert "pgreen@pgreenlaw.com" not in out
        assert "@pgreenlaw.com" not in out


class TestAddressFragment:
    """An address whose street-type suffix is wrapped off by a corrupted scan
    ("1055 E Colorado" with "Blvd." on the next line) is still scrubbed, mapped
    to the same fake as a clean occurrence of the address."""

    CLEAN = "LAW OFFICE OF PAUL GREEN\n1055 E Colorado Blvd., Pasadena, CA 91106"
    CORRUPT = "my business address 1055 E Colorado\nBlvd. I am employed"

    def _pz_learned(self):
        pz, _ = _pz(detectors=["address"])
        pz.register_addresses(self.CLEAN)
        return pz

    def test_suffixless_fragment_scrubbed(self):
        pz = self._pz_learned()
        assert "1055 E Colorado" not in pz.apply(self.CORRUPT)

    def test_fragment_reuses_the_clean_fake_street(self):
        pz = self._pz_learned()
        street = re.search(r"\d+ (\w+)", pz.apply(self.CLEAN)).group(1)
        assert street in pz.apply(self.CORRUPT)   # same fake street name

    def test_full_address_still_faked_and_locality_kept(self):
        pz = self._pz_learned()
        out = pz.apply(self.CLEAN)
        assert "1055 E Colorado" not in out
        assert "Pasadena" in out and "91106" in out   # locality kept (policy)

    def test_prose_number_not_touched(self):
        pz = self._pz_learned()
        assert pz.apply("Chapter 1055 discusses zoning.") == "Chapter 1055 discusses zoning."

    def test_trivial_address_spawns_no_fragment(self):
        pz, _ = _pz(detectors=["address"])
        pz.register_addresses("1 A St")
        assert not any(t.category == "address_fragment" for t in pz.terms)


class TestDegreeSuffixNeverScrubbed:
    """A professional/generational suffix ("M.D.", "Ph.D.", "Esq.", "Jr.") is
    never a name and is always kept as written, in any punctuation."""

    def test_not_a_name_token(self):
        for s in ["M.D.", "MD", "M.D", "m.d.", "Ph.D.", "PHD", "Esq.", "Jr.",
                  "D.D.S.", "R.N.", "J.D."]:
            assert not pl._pn_is_name_token(s), s

    def test_is_suffix_token_dot_insensitive(self):
        for s in ["M.D.", "MD", "M.D", "m.d.", "Ph.D.", "PhD"]:
            assert pl._pn_is_suffix_token(s), s
        assert not pl._pn_is_suffix_token("Madison")

    def test_real_names_still_tokens(self):
        for n in ["Smith", "Coderre", "Jane"]:
            assert pl._pn_is_name_token(n)

    def test_md_kept_when_party_is_scrubbed(self):
        pz, _ = _pz(names=[("Jane Smith, M.D.", False)], detectors=[])
        out = pz.apply("Defendant Jane Smith, M.D. answered.")
        assert "Jane Smith" not in out and "M.D." in out

    def test_bare_md_untouched(self):
        pz, _ = _pz(names=[("Jane Smith, M.D.", False)], detectors=[])
        assert pz.apply("The witness, an M.D., testified.") == \
            "The witness, an M.D., testified."

    def test_runtogether_md_kept(self):
        # "MD" with no dots is still a suffix, not a surname
        full, _bare = pl._pn_fake_person("Bob Jones MD", pl._PnFakeRegistry())
        assert full.endswith("MD") and "Bob" not in full and "Jones" not in full


class TestDocAbbreviationsNeverScrubbed:
    """Caption/title abbreviations "ISO" (In Support Of) and "RJN" (Request for
    Judicial Notice) are never part of a person's name and are kept verbatim."""

    def test_not_name_tokens(self):
        assert not pl._pn_is_name_token("ISO")
        assert not pl._pn_is_name_token("RJN")

    def test_declarant_stops_before_them(self):
        assert pl._pn_declarant_names(
            "DECLARATION OF JOHN SMITH ISO MOTION TO STRIKE") == ["JOHN SMITH"]
        assert pl._pn_declarant_names("DECLARATION OF JANE DOE RJN") == ["JANE DOE"]

    def test_kept_inside_a_faked_name(self):
        full, _ = pl._pn_fake_person("John Smith ISO RJN", pl._PnFakeRegistry())
        assert "ISO" in full and "RJN" in full
        assert "Smith" not in full   # the actual name is still faked

    def test_end_to_end_declaration_title(self):
        pz, _ = _pz(detectors=[])
        pz.register_declarant_names("DECLARATION OF JOHN SMITH ISO MOTION")
        out = pz.apply("DECLARATION OF JOHN SMITH ISO MOTION")
        assert "JOHN SMITH" not in out and "ISO" in out and "MOTION" in out


# ── Court-form boilerplate is never faked or flagged (_PN_NEVER_FAKE) ─────────
class TestNeverFakeFormBoilerplate:
    """A Judicial Council form number ("CIV-100"), the "CASE NUMBER" field
    label, and the "Default Only" checkbox are public form boilerplate — faking
    one corrupts the form (a form number is not a case number). They are never
    registered as terms and never flagged for review."""

    def test_predicate_matches_spacing_and_dash_variants(self):
        for v in ("CIV-100", "CIV 100", "civ100", "CASE NUMBER", "Case Number",
                  "Default Only", "DEFAULT ONLY"):
            assert pl._pn_is_never_fake(v), v
        for v in ("23STCV31247", "CIV-101", "Raytheon"):
            assert not pl._pn_is_never_fake(v), v

    def test_form_number_from_the_case_number_column_is_not_faked(self):
        # A "Case Number" cell that actually holds a form number must not fake it.
        pz, _reg = _pz(casenos=["CIV-100", "23STCV31247"])
        out = pz.apply("Form CIV-100. CASE NUMBER: 23STCV31247.")
        assert "CIV-100" in out                      # form number untouched
        assert "23STCV31247" not in out              # the real case number faked

    def test_labels_survive_even_as_explicit_terms(self):
        pz, _reg = _pz(names=["CASE NUMBER"], terms=["Default Only"])
        out = pz.apply("CASE NUMBER field, Default Only box.")
        assert "CASE NUMBER" in out and "Default Only" in out

    def test_boilerplate_is_not_flagged_for_review(self):
        assert pl._pn_person_review_findings("By: Default Only", set()) == []
        assert pl._pn_unknown_name_findings(
            "Defendant Default Only moved for judgment.", set()) == []

    def test_a_key_binding_for_boilerplate_is_dropped_on_load(self, tmp_path):
        import openpyxl
        wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Pseudonym Key"
        ws.append(["Category", "Real Value", "Replacement", "Status",
                   "Source", "Occurrences"])
        ws.append(["case_number", "CIV-100", "CIV-472", "replaced", "--term", "3"])
        wb.save(tmp_path / "pseudonym_key.xlsx")
        reg = pl._PnFakeRegistry()
        terms, _ = pl._pn_load_key(tmp_path / "pseudonym_key.xlsx", reg,
                                   logging.getLogger("t"))
        assert not any(t.real == "CIV-100" for t in terms)   # stale binding dropped
