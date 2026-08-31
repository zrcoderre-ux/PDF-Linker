"""
The leaks one delivered default-judgment batch actually shipped, each pinned.

A fax-generation Personal Guarantee and a set of Judicial Council forms
(CIV-100, JUD-100) put five distinct holes on display at once:

  * the declarant's name typed onto the form's FILL-IN RULE, interleaved with
    the rule's own underscores ("I, ___ l_ria_Ra_m_o_s _____ ~ the
    undersigned declare") — matched by nothing, reported by nothing;
  * the CIV-100 item-6 mailing declarant standing above a "(TYPE OR PRINT
    NAME)" label with no other anchor — shipped in the clear in three exports;
  * a customer SURNAME-FIRST in an exhibit table ("BOND SELBORNE") whose
    surname is withheld from a bare token for being a generic word;
  * degraded-scan debris the letters-only fuzzy candidate could not see
    ("Va-iq11ez", "Pre1tlge"), and labelled contact values the detectors
    could not read ("(228) 424-3-575", "l440S Whorto1t I..n");
  * the bare-domain detector matching soup and writing a FAKE DOMAIN into the
    middle of the word "covenants" ("cuve!postbay.org and agreem~ts").

Run:  cd PDF-Linker && python3 -m pytest tests/test_form_and_degraded_leaks.py -v
"""

import pdf_linker as P

DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}

# One paragraph as a fax generation renders it (transcribed from the real
# exhibit), enough of it to clear the degradation floor.
FAX = (
    "Guarantor agree& to pay all ot\"Wcstlalce's oott5, '°'PMse& and r~asonable\n"
    "atto.-neya' fees Incurred in enfo1cing the obl.lgatiallS, cuve!nants.org and\n"
    "agreem~ts of Dcidcr in I.he Det.lcr Agrcemenl 11nd other agreement,\n"
    "bctwcc11 Wcrtlake and Dee.ler or incurred by Wllstlake ia eriforcing this\n"
    "Gua:-antcc. Guarmtorwaives na'.ice Qfthe acceptance of this Gua:-antec,\n"
    "pn:M!ltmcnt, pmtast, notice o{pro~, and 11ny and ul domands for any\n"
    "and alt notices ofnon-pelfonn11nce that might olherwae bo a condition\n"
    "pn:cedent to the liability of Guarantor under the Deafer Agrcement d~boor.\n"
)


def _pz(*names):
    reg = P._PnFakeRegistry()
    return P.Pseudonymizer(P._pn_build_terms(list(names), [], [], registry=reg),
                           DET, registry=reg)


# ── a fake domain written into garbled text ─────────────────────────────────

def test_a_bare_domain_in_a_degraded_region_is_not_faked():
    """The middle of "covenants" must not become one of our stand-ins."""
    z = _pz()
    out = z.apply(FAX * 3)
    assert "cuve!nants.org" in out
    assert not any(cat == "url" for cat, _rl in z.records)


def test_the_kept_soup_still_earns_a_review_row():
    z = _pz()
    out = z.apply(FAX * 3)
    assert ("url/domain", "nants.org") in z.review_scan(out)


def test_a_clean_page_s_bare_domain_is_still_faked():
    z = _pz()
    out = z.apply("The firm maintains its site at smithlawfirm.com today.\n" * 20)
    assert "smithlawfirm.com" not in out


def test_a_scheme_carries_its_own_corroboration_even_on_a_degraded_page():
    z = _pz()
    body = FAX + "See https://smithlawfirm.com/bio for detail.\n" + FAX + FAX
    assert P._pn_degraded_spans(P._NFKC(body)), "fixture must read degraded"
    out = z.apply(body)
    assert "smithlawfirm.com" not in out


# ── a name typed onto a fill-in rule ────────────────────────────────────────

RULE_LINE = ("24        I, ___ l_ria_Ra_m_o_s _____ ~ the undersigned declare "
             "and certify as follows:\n")


def test_a_name_on_a_fill_in_rule_is_reported_raw():
    z = _pz()
    assert z.form_rule_name_scan(RULE_LINE) == [
        ("name on a form rule?", "l_ria_Ra_m_o_s")]


def test_a_blank_rule_and_a_job_title_yield_nothing():
    z = _pz()
    body = ("The blank form reads: I, ______________, the undersigned declare.\n"
            " 8  as the __ D_e_a_le_r C_o_m--'-p_lia_n_ce_M_a_n---'ag=--e_r "
            "___ , I maintain custody of the files\n")
    assert z.form_rule_name_scan(body) == []


def test_a_clean_self_id_is_the_harvest_anchor_s_business():
    z = _pz()
    assert z.form_rule_name_scan("I, Maria Ramos, declare as follows:\n") == []


def test_the_self_id_anchor_tolerates_the_form_s_own_furniture():
    """The form prints "I, ______, the undersigned declare"; a filled copy
    loses the second comma."""
    for t in ("I, Maria Ramos, declare as follows:",
              "I, Maria Ramos the undersigned declare and certify",
              "I, Maria Ramos, the undersigned declare and certify"):
        assert P._pn_declarant_names(t) == ["Maria Ramos"], t
    assert P._pn_declarant_names("I, THE UNDERSIGNED, declare this") == []


# ── the (TYPE OR PRINT NAME) label ──────────────────────────────────────────

CIV100_SIG = ("| declare under penalty of perjury under the laws of the State "
              "of California that the foregoing items 4, 5, and 6 are true "
              "and correct.\nDate: Julv 14. 2026\n"
              "                Narine Kinatyan                           feYA\n"
              "                                                 >\n"
              "               (TYPE OR PRINT NAME)                           "
              "(SIGNATURE OF\n"
              "                                                             "
              "DECLARANT)\n")


def test_the_typed_name_above_the_label_is_harvested():
    assert P._pn_label_names(CIV100_SIG) == ["Narine Kinatyan"]


def test_the_ocr_brace_spelling_of_the_label_matches_too():
    block = ("                   Narine Kinatyan                         >\n"
             "                   {TYPE OR PRINT NAME)                     "
             "(SIGNATURE OF DECLARANT)\n")
    assert P._pn_label_names(block) == ["Narine Kinatyan"]


def test_an_unfilled_signature_block_yields_nothing():
    for block in ("Date: Julv 14. 2026\n\n"
                  "               (TYPE OR PRINT NAME)\n",
                  "   correct and these costs were necessarily incurred.\n"
                  "               (TYPE OR PRINT NAME)\n"):
        assert P._pn_label_names(block) == [], block


def test_the_civ100_mailing_declarant_is_scrubbed_end_to_end():
    z = _pz()
    P._pn_learn_from_text(z, CIV100_SIG)
    out = z.apply(CIV100_SIG)
    assert "Narine" not in out and "Kinatyan" not in out


# ── the surname-first table row ─────────────────────────────────────────────

def test_a_surname_first_table_row_is_scrubbed():
    """"Bond" is a generic word, so its bare token is deliberately withheld —
    the reversed spelling is what covers the table."""
    z = _pz("Selborne Bond")
    out = z.apply("purchased by Selborne Bond.\n"
                  "41962166       BOND SELBORNE       06/20/2023   CHGOFF\n")
    assert "BOND" not in out and "Bond" not in out


def test_the_two_orders_are_one_person_word_for_word():
    z = _pz("Selborne Bond")
    out = z.apply("Selborne Bond\nBOND SELBORNE\n")
    fwd, rev = out.strip().split("\n")
    assert fwd.lower().split() == list(reversed(rev.lower().split()))


def test_the_reversed_spelling_is_derived_and_two_word_only():
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Selborne Bond", "Steven Wayne Burt"], [], [],
                              registry=reg)
    rev = [t for t in terms if str(t.real).lower() == "bond selborne"]
    assert rev and rev[0].derived
    assert not any(str(t.real).lower().startswith("burt ") for t in terms)


def test_a_keep_retires_the_reversed_spelling_with_its_parent():
    """The derived spelling is the SAME party: a `no` on the parent must not
    leave the reversed term (or its words) faking the kept value."""
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Marcus Bellweather"], [], [], registry=reg)
    keeps = {"marcus bellweather": {
        "value": "Marcus Bellweather", "type": "KEEP", "fix": "no",
        "replacement": None, "fake_values": None, "fixcell": None,
        "notes": "t"}}
    import logging
    survivors, retired = P._pn_retire_kept_key_terms(
        terms, keeps, reg, logging.getLogger("t"))
    assert retired
    assert not any("bellweather" in str(t.real).lower() for t in survivors)


# ── the debris tier of the fuzzy sweep ──────────────────────────────────────

def test_debris_spellings_are_reported_inside_a_degraded_region():
    z = _pz("Mark Vasquez", "Prestige Auto Sales")
    body = FAX + "Print Name: Mark Va-iq11ez\nDBA: Pre1tlge Auto\n" + FAX + FAX
    out = z.apply(body)
    rows = [s for _c, s in z.fuzzy_survivor_scan(out)]
    assert "Va-iq11ez" in rows and "Pre1tlge" in rows


def test_debris_needs_a_degraded_region():
    z = _pz("Mark Vasquez")
    body = ("The parties met and conferred on the schedule as required.\n" * 30
            + "Print Name: Mark Va-iq11ez\n"
            + "They agreed the motion would be heard in Department 47.\n" * 30)
    assert not P._pn_degraded_spans(P._NFKC(body))
    out = z.apply(body)
    assert "Va-iq11ez" not in [s for _c, s in z.fuzzy_survivor_scan(out)]


def test_our_own_compound_fake_is_never_reported_as_debris():
    z = _pz("Maria Ardeshirpour-Zartoshti")
    out = z.apply(FAX * 3 + "Dr. Ardeshirpour-Zartoshti appeared.\n")
    fake = next(str(r["fake"]) for (c, _rl), r in z.records.items()
                if c == "person")
    compound = fake.split()[-1]
    assert compound.lower() not in [
        s.lower() for _c, s in z.fuzzy_survivor_scan(out)]


# ── labelled contact values the detectors could not read ────────────────────

CONTACTS = ("      ADDRESS:     l440S Whorto1t I..n           ADDRESS: ·\n"
            "      TEL: rAX:    _,.___._ (228) 424-3-575 ____________ _ TEL:\n"
            "    Dca.ler Address: 2UIHB Pass Rd\n"
            "      ADDRESS: game\n")


def test_labelled_contacts_on_a_degraded_page_are_reported():
    z = _pz()
    # The contact lines sit INSIDE the fax page, as on the real exhibit —
    # a trailing block of mostly-clean lines is not degraded.
    rows = {s for _c, s in z.degraded_contact_scan(FAX + CONTACTS + FAX * 2)}
    assert {"l440S Whorto1t I..n", "(228) 424-3-575", "2UIHB Pass Rd"} <= rows
    assert "game" not in " ".join(rows)


def test_contact_rows_need_a_degraded_region():
    z = _pz()
    assert z.degraded_contact_scan(
        "Clean prose all around here.\n" * 40 + CONTACTS) == []


def test_a_value_the_detector_already_faked_is_not_reported():
    z = _pz()
    body = FAX * 3 + "      Tel: (980) 818-5933\n"
    out = z.apply(body)
    assert "(980) 818-5933" not in out          # faked
    assert z.degraded_contact_scan(out) == []


# ── the e-filing stamp's court staff ────────────────────────────────────────

STAMP = ("Electronically FILED by\nSuperior Court of California,\n"
         "County of Los Angeles\n7/22/2026 12:41 PM\n"
         "David W. Slayton,\nExecutive Officer/Clerk of Court,\n"
         "By J. So, Deputy Clerk\n")


def test_the_executive_officer_is_scrubbed_across_the_stamp_wrap():
    z = _pz()
    P._pn_learn_from_text(z, STAMP)
    out = z.apply(STAMP)
    assert "Slayton" not in out and "David" not in out


def test_a_deputy_whose_surname_spells_a_word_is_scrubbed():
    z = _pz()
    P._pn_learn_from_text(z, STAMP)
    out = z.apply(STAMP)
    assert "J. So," not in out


def test_the_word_so_is_untouched_outside_the_name():
    z = _pz()
    P._pn_learn_from_text(z, STAMP)
    out = z.apply(STAMP + "and so the clerk So ordered, so it is done.\n")
    assert "and so the clerk" in out and "so it is done" in out


def test_a_run_on_capture_with_no_anchor_still_dies():
    z = _pz()
    P._pn_learn_from_text(z, "The Answer Has Been Filed, Deputy Clerk.\n")
    assert not z.records
