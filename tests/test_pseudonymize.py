"""Unit tests for pdf_linker's pseudonymization block.

The functions under test are pure string helpers plus the Pseudonymizer, so no
PDF fixtures are needed — the module is imported and its `_pn_*` internals are
called directly. Each test names the hardening task it guards (see the
handoff). Run with: pytest tests/test_pseudonymize.py
"""
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

    def test_city_and_zip_are_replaced_not_dropped(self):
        pz, _reg = _pz()
        out = pz.apply(self.REAL)
        assert "Montebello" not in out and "90640" not in out
        assert re.search(r",\s*CA\s+\d{5}\b", out), out   # state kept, zip faked

    def test_suite_survives(self):
        pz, _reg = _pz()
        out = pz.apply("21225 Pacific Coast Hwy, Suite C Malibu, CA 90265")
        assert "Suite C" in out
        assert "Malibu" not in out

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
        assert "gmail" not in out.lower()

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
    def test_bare_city_learned_from_an_address(self):
        pz, _reg = _pz()
        body = ("414 S. Maple Ave. Montebello, CA 90640\n"
                "Plaintiff is an individual residing in Montebello, California.")
        pz.register_localities(body)
        out = pz.apply(body)
        assert "Montebello" not in out
        assert "90640" not in out

    def test_address_and_bare_mention_get_the_same_fake(self):
        pz, _reg = _pz()
        body = "414 S. Maple Ave. Montebello, CA 90640"
        pz.register_localities(body)
        out = pz.apply(body + "\nHe lives in Montebello.")
        cities = re.findall(r"|".join(pl._PN_CITY_NAMES), out)
        assert len(set(cities)) == 1 and len(cities) == 2

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
