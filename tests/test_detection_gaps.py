"""The detection gaps of one delivered batch, each verified at HEAD as
"nothing: not faked, not gated, no review row".

Every fix follows the module's own rules: a HARVEST is a term routed through
`_pn_label_names`-style screens (two words, no role token, no locality,
Title case) or is REVIEW-tier only where a single word is all the anchor
gives; a new identifier is a label-anchored `_PN_ID_RES` class faked through
the registry, never a bare-number rule; and detection never out-runs
replacement (a harvest is a TERM, a review tier is a ROW). Each anchor was
measured over this repo's CLAUDE.md and the module's docstrings and
comments (1.2 MB of capitalised technical prose) at zero rows beyond the
repo's own worked examples.

Run:  cd PDF-Linker && python3 -m pytest tests/test_detection_gaps.py -v
"""
import logging
import re

import pdf_linker as P

log = logging.getLogger("test")


def _pz(parties=(), detectors=None):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms([(p, False) for p in parties], [], [],
                              registry=reg)
    det = (list(P._PN_DEFAULT_DETECTORS) if detectors is None
           else list(detectors))
    return P.Pseudonymizer(terms, det, registry=reg)


def _learn(text, parties=(), detectors=None):
    z = _pz(parties, detectors)
    P._pn_learn_from_text(z, text, "Doc")
    return z


def _reals(z, *cats):
    return {t.real for t in z.terms if not cats or t.category in cats}


def _gone(out, *values):
    for v in values:
        assert v not in out, (v, out)


# ── 1. Exhibit labels ────────────────────────────────────────────────────────

LABELS = ("Patient: Priya Venkataraman\n"
          "Insured: Brian Kowalczyk\n"
          "Treating Physician: Farhad Ardeshirpour\n"
          "Reserved By : Owen Blakely\n"
          "Salesperson : Tomas Delgado\n"
          "Prepared by: Rosa Delgado\n"
          "Claimant: Ana Delgado\n")


def test_exhibit_labels_are_harvested():
    z = _learn(LABELS)
    reals = _reals(z, "person")
    for who in ("Priya Venkataraman", "Brian Kowalczyk", "Farhad Ardeshirpour",
                "Owen Blakely", "Tomas Delgado", "Rosa Delgado", "Ana Delgado"):
        assert who in reals, reals
    out = z.apply(LABELS)
    _gone(out, "Venkataraman", "Kowalczyk", "Ardeshirpour", "Blakely", "Delgado")
    # The labels themselves are furniture and stay.
    for label in ("Patient:", "Insured:", "Treating Physician:", "Reserved By :",
                  "Salesperson :", "Prepared by:"):
        assert label in out, out


def test_the_qualifying_individual_is_harvested_and_the_heading_is_not():
    text = ("The qualifying individual Farhad Ardeshirpour certified that the "
            "work was done.\nQualifying Individual Must Be Licensed\n")
    z = _learn(text)
    assert "Farhad Ardeshirpour" in _reals(z, "person")
    assert not any("Must" in r for r in _reals(z)), _reals(z)
    assert "Qualifying Individual Must Be Licensed" in z.apply(text)


def test_a_numbered_witness_list_is_harvested_line_by_line():
    text = ("WITNESSES:\n1. Rosa Delgado\n2. Tomas Delgado, custodian of "
            "records\n3. Owen Blakely (by phone)\nNot a witness Jane Roe\n")
    assert P._pn_numbered_list_names(text) == [
        "Rosa Delgado", "Tomas Delgado", "Owen Blakely"]
    z = _learn(text)
    reals = _reals(z, "person")
    assert {"Rosa Delgado", "Tomas Delgado", "Owen Blakely"} <= reals
    assert "Jane Roe" not in reals
    out = z.apply(text)
    _gone(out, "Delgado", "Blakely")
    assert "custodian of records" in out and "(by phone)" in out


# ── 2. Caption entities without the comma; the comma roster row ─────────────

CAPTION = ("GALPIN MOTORS INC., a California corporation; SUNBELT RENTALS LLC, "
           "a Delaware limited liability company; and DOES 1 through 20, "
           "inclusive,\nDefendants.\n")


def test_a_caption_entity_without_a_comma_before_its_suffix():
    z = _learn(CAPTION)
    reals = _reals(z, "entity")
    assert "GALPIN MOTORS INC." in reals and "SUNBELT RENTALS LLC" in reals, reals
    out = z.apply(CAPTION)
    _gone(out, "GALPIN", "SUNBELT")
    # The descriptor and the Doe clause are boilerplate and stay verbatim.
    assert "a California corporation" in out
    assert "a Delaware limited liability company" in out
    assert "DOES 1 through 20" in out


def test_the_bare_suffix_branch_admits_only_the_unambiguous_forms():
    names = P._pn_firm_names("Denver CO is nice. The parties Inc agreed. "
                             "Sunbelt Rentals LLC and Galpin Motors Inc. and "
                             "Acme Widgets Corp. were served.")
    assert "Sunbelt Rentals LLC" in names and "Galpin Motors Inc." in names
    assert "Acme Widgets Corp." in names
    assert not any("Denver" in n or "parties" in n.lower() for n in names), names


def test_the_descriptor_anchor_refuses_a_person_in_prose():
    text = ("Owen Blakely, a company employee, said so. Rosa Delgado, a "
            "corporation lawyer, agreed.\n")
    assert not P._pn_firm_names(text)
    assert not P._PN_CAPTION_ENTITY_RE.search(text)


def test_a_comma_led_caption_roster_row_is_a_docket_row():
    text = "OWEN BLAKELY, Plaintiff,\nvs.\nSUNBELT RENTALS LLC, Defendant.\n"
    names = P._pn_docket_roster_names(text)
    assert "OWEN BLAKELY" in names, names
    z = _learn(text)
    out = z.apply(text)
    _gone(out, "BLAKELY", "SUNBELT")
    assert ", Plaintiff," in out
    # A descriptor between the name and the role is not a roster row (it is
    # the descriptor anchor's), and a prose line never ends on the role.
    assert not P._pn_docket_roster_names(
        "HELEN RASHO, an individual, Plaintiff,\n"
        "and then served on Owen Blakely, Plaintiff.\n")


# ── 3. Date of birth and age ─────────────────────────────────────────────────

DOB = ("DOB: 03/14/1978\nDate of Birth: 03/14/1978\nHe was born on March 14, "
       "1978 in Fresno.\n(DOB 03/14/1978)\nFiled: 03/14/2024\n")


def test_a_date_of_birth_fakes_the_day_and_month_and_keeps_the_year():
    z = _learn(DOB)
    out = z.apply(DOB)
    assert "03/14/1978" not in out and "March 14, 1978" not in out, out
    nums = re.findall(r"DOB:? ?(\d{2}/\d{2}/\d{4})", out)
    assert len(nums) == 2 and len(set(nums)) == 1, out
    assert nums[0].endswith("/1978")
    word = re.search(r"born on ([A-Z][a-z]+ \d{1,2}, 1978)", out)
    assert word, out
    # One date, one draw: the numeric and the word spellings agree.
    mm, dd = nums[0].split("/")[:2]
    assert word.group(1).split()[1].rstrip(",") == str(int(dd))
    assert P._PN_MONTHS[int(mm) - 1] == word.group(1).split()[0].lower()
    # A filing date is not a date of birth and is never touched.
    assert "Filed: 03/14/2024" in out
    assert "date of birth" in P._PN_REID_CLASSES


def test_a_surviving_date_of_birth_is_a_reid_row():
    z = _pz()
    assert ("REID date of birth", "03/14/1978") in z.reid_scan("DOB: 03/14/1978")


def test_an_age_is_a_review_row_and_a_page_is_not():
    vals = {v for k, v in P._pn_review_findings(
        "Rosa Delgado, 67, of Fresno was age 67 and a 67-year-old. "
        "Page 12 and Stage 2.") if k == "age"}
    assert {"Rosa Delgado, 67,", "age 67", "67-year-old"} <= vals, vals
    assert not any("Page" in v or "Stage" in v for v in vals)


# ── 4. Driver licence and plate ──────────────────────────────────────────────

def test_a_driver_licence_and_a_plate_are_faked_char_wise():
    text = "Driver License No.: D1234567\nCA DL B7654321\nLicense Plate: 8ABC123\n"
    z = _learn(text)
    out = z.apply(text)
    _gone(out, "D1234567", "B7654321", "8ABC123")
    assert re.search(r"Driver License No\.: [A-Z]\d{7}\n", out), out
    assert re.search(r"CA DL [A-Z]\d{7}\n", out), out
    assert re.search(r"License Plate: [A-Z0-9]{7}\n", out), out
    cats = {r["category"] for r in z.records.values()}
    assert {"driver_license", "license_plate"} <= cats
    assert {"driver license", "license plate"} <= P._PN_ALNUM_IDS
    assert {"driver license", "license plate"} <= P._PN_REID_CLASSES
    # "dl" inside prose is not a label.
    assert not P._pn_identifier_values("the handle 1234567 broke")


# ── 5. P.O. Box and suffix-less streets ──────────────────────────────────────

def test_a_po_box_fakes_its_number_and_keeps_the_locality():
    text = "P.O. Box 1234, Bakersfield, CA 93301\nPO Box 98765\nPost Office Box 7\n"
    z = _learn(text)
    out = z.apply(text)
    assert re.match(r"P\.O\. Box \d{4}, Bakersfield, CA 93301\n"
                    r"PO Box \d{5}\nPost Office Box \d\n", out), out
    _gone(out, "Box 1234", "Box 98765", "Box 7\n")
    # Two spellings of one box draw one number.
    z2 = _learn("P.O. Box 1234 and PO Box 1234")
    nums = set(re.findall(r"Box (\d+)", z2.apply("P.O. Box 1234 and PO Box 1234")))
    assert len(nums) == 1 and "1234" not in nums


def test_suffix_less_streets_are_read_off_their_tail():
    text = ("1234 Broadway, Los Angeles, CA 90015\n"
            "1888 Avenue of the Stars, Suite 1500, Los Angeles, CA 90067\n"
            "100 Camino Real, Suite 200, Redwood City, CA 94063\n"
            "See 24 Hour Fitness Center opened.\n¶ 12 Smith Decl. #3\n")
    z = _learn(text)
    out = z.apply(text)
    _gone(out, "Broadway", "Avenue of the Stars", "Camino Real")
    # The house number, the suite and the whole City, ST ZIP tail are kept.
    assert re.search(r"^1234 \S+ \S+, Los Angeles, CA 90015$", out, re.M), out
    assert re.search(r"^1888 \S+ \S+, Suite 1500, Los Angeles, CA 90067$",
                     out, re.M), out
    assert re.search(r"^100 \S+ \S+, Suite 200, Redwood City, CA 94063$",
                     out, re.M), out
    assert "24 Hour Fitness Center opened" in out
    assert re.search(r"^¶ 12 \w+ Decl\. #3$", out, re.M), out


def test_the_suffix_less_branch_never_splits_a_word():
    # "25 LAMBOURNE 01234" (a docket spelling) was read as street "LAMBO",
    # city "UR", state "NE", zip 01234 before the run was bounded.
    assert not P._PN_ADDR_RE.search('("25 LAMBOURNE 01234"), because')
    assert not P._PN_ADDR_RE.search("25 STCP 01234")


# ── 6. Labelled identifiers with no class ────────────────────────────────────

IDS = {
    "routing number": ("Routing No. 122000247", "122000247"),
    "tax id": ("EIN 12-3456789", "12-3456789"),
    "claim number": ("Claim No. 22-0004567-01", "22-0004567-01"),
    "policy number": ("Policy No. HO-1234567-89", "HO-1234567-89"),
    "bond number": ("Bond Number: G131215420779", "G131215420779"),
    "medical record number": ("MRN: 00123456", "00123456"),
    "patient id": ("Patient ID 55443322", "55443322"),
    "employee id": ("Employee ID: 100234", "100234"),
    "parcel number": ("APN 5555-012-034", "5555-012-034"),
    "passport number": ("Passport No. 123456789", "123456789"),
    "medicare number": ("Medicare No. 1EG4-TE5-MK72", "1EG4-TE5-MK72"),
    "instrument number": ("Instrument No. 2021-0123456", "2021-0123456"),
    "charge number": ("EEOC Charge No. 480-2022-01234", "480-2022-01234"),
    "commission number": ("Commission # 2475537", "2475537"),
    "loan number": ("Loan No. 12345678", "12345678"),
}


def test_every_new_identifier_class_is_label_anchored_and_faked():
    for cls, (line, value) in IDS.items():
        found = dict(P._pn_identifier_values(line))
        assert found.get(cls) == value, (cls, found)
        z = _learn(line + "\n")
        out = z.apply(line + "\n")
        assert value not in out, (cls, out)
        label = line[:len(line) - len(value)]
        assert out.startswith(label), (cls, out)
        assert cls in P._PN_REID_CLASSES or cls == "routing number"
        # The bare value stays a bare value in the log: never a number rule.
        assert not P._pn_identifier_values(value), (cls, value)


def test_the_alphanumeric_classes_change_their_letters_too():
    for cls in ("claim number", "policy number", "bond number", "medicare number"):
        line, value = IDS[cls]
        out = _learn(line).apply(line)
        fake = out[len(line) - len(value):]
        assert fake != value and len(fake) == len(value), (cls, out)
        assert cls in P._PN_ALNUM_IDS
    # "Claim Number: 2025BOND0825" — letters inside a claim number.
    out = _learn("Claim Number: 2025BOND0825").apply("Claim Number: 2025BOND0825")
    assert "2025BOND0825" not in out and out.startswith("Claim Number: ")


def test_a_short_number_behind_a_label_stays_out():
    assert not P._pn_identifier_values("Employee ID: 12")
    assert not P._pn_identifier_values("Commission # 123")
    assert not P._pn_identifier_values("Document No. 12")


# ── 7. Card numbers ──────────────────────────────────────────────────────────

def test_a_card_is_faked_whole_and_luhn_valid():
    text = ("Account No. 4111 1111 1111 1111\nCard 4111-1111-1111-1111 on file.\n"
            "Bare 4111111111111111.\nAccount No. 1234 5678 9012 3456\n")
    z = _learn(text)
    out = z.apply(text)
    assert "4111" not in out and "1111" not in out, out
    fakes = re.findall(r"(\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4})", out)
    assert len(fakes) == 4
    digits = {re.sub(r"\D", "", f) for f in fakes[:3]}
    assert len(digits) == 1, fakes                      # one card, one fake
    assert all(P._pn_luhn_ok(f) for f in fakes[:3])
    # The half-fake is gone: the account-id capture holds all sixteen.
    assert "1234 5678 9012 3456" not in out and "5678 9012 3456" not in out
    assert ("account_id", "4111 1111 1111 1111") in z.records
    # Not Luhn-valid: the shape alone is not a card, and the bare detector
    # leaves it exactly alone.
    assert not P._pn_luhn_ok("1234 5678 9012 3456")
    assert _pz().apply("Ref 1234 5678 9012 3456") == "Ref 1234 5678 9012 3456"


def test_a_surviving_card_is_a_reid_row():
    z = _pz()
    rows = z.reid_scan("Card 4111 1111 1111 1111 and ref 1234 5678 9012 3456")
    assert ("REID card number", "4111 1111 1111 1111") in rows, rows
    assert not any("1234 5678" in s for _c, s in rows)


# ── 8. Titles ────────────────────────────────────────────────────────────────

def test_uniformed_and_clinical_titles_are_a_review_anchor():
    text = ("Detective Ramon Ochoa arrived. Deputy Luis Carbajal wrote. Nurse "
            "Priya Venkataraman took notes. Capt. Ivan Petrov agreed. Deputy "
            "Clerk Jane Roe filed it. Deputy District Attorney Ann Lee spoke.\n")
    z = _pz()
    z.note_original(text)
    rows = {s for _c, s in z.honorific_name_scan(text)}
    assert {"Ramon Ochoa", "Luis Carbajal", "Priya Venkataraman",
            "Ivan Petrov"} <= rows, rows
    assert not any("Roe" in s or "Lee" in s or "Clerk" in s or "District" in s
                   for s in rows), rows


def test_a_title_beside_a_bound_surname_is_not_a_half_scrub():
    text = "Nurse Owen Blakely helped. Detective Owen Blakely wrote.\n"
    z = _learn(text, parties=("Owen Blakely",))
    z.note_original(text)
    out = z.apply(text)
    _gone(out, "Blakely")
    assert out.startswith("Nurse ") and "Detective " in out
    assert not z.half_scrubbed_scan(out), z.half_scrubbed_scan(out)
    for t in ("nurse", "detective", "deputy", "sheriff", "agent", "trooper"):
        assert t in P._PN_HONORIFICS


# ── 9. Notary jurat ──────────────────────────────────────────────────────────

def test_a_jurat_names_the_notary_the_signer_and_the_commission():
    text = ("On March 1, 2024, before me,\nROSA DELGADO, Notary Public, "
            "personally appeared Owen Blakely, who proved to me on the basis "
            "of satisfactory evidence.\nCommission # 2475537\n")
    z = _learn(text)
    reals = _reals(z, "person")
    assert "ROSA DELGADO" in reals and "Owen Blakely" in reals, reals
    out = z.apply(text)
    _gone(out, "DELGADO", "Blakely", "2475537")
    assert "Notary Public, personally appeared" in out
    assert re.search(r"Commission # \d{7}\n", out), out


# ── 10. Letter furniture ─────────────────────────────────────────────────────

LETTER = ("Dear Brian Kowalczyk,\n\nWe write regarding your account.\n\n"
          "Sincerely,\n\nOwen Blakely\nSenior Manager\n\n"
          "Very truly yours,\nRosa Delgado\n"
          "Respectfully submitted,\n\nLAW OFFICES OF SCOTT STRATMAN\n\n"
          "By: /s/ Scott Stratman\nAttorneys for Plaintiff\n"
          "Regards,\nAttorneys For Plaintiff\n")


def test_a_letters_closing_and_salutation_are_harvested():
    z = _learn(LETTER)
    reals = _reals(z, "person")
    assert {"Brian Kowalczyk", "Owen Blakely", "Rosa Delgado"} <= reals, reals
    assert not any("Attorneys" in r or "Senior" in r for r in _reals(z)), _reals(z)
    out = z.apply(LETTER)
    _gone(out, "Kowalczyk", "Blakely", "Delgado", "STRATMAN")
    for furniture in ("Dear ", "Sincerely,", "Very truly yours,",
                      "Respectfully submitted,", "Attorneys for Plaintiff",
                      "Senior Manager", "Regards,\nAttorneys For Plaintiff"):
        assert furniture in out, out


def test_dear_and_a_title_binds_the_surname_behind_the_title_only(tmp_path):
    text = ("Dear Mr. Kowalczyk:\nMr. Kowalczyk agreed. Ms. Kowalczyk did not. "
            "Mr Kowalczyk signed. Kowalczyk Street is elsewhere.\n")
    z = _learn(text)
    out = z.apply(text)
    assert "Mr. Kowalczyk" not in out and "Ms. Kowalczyk" not in out, out
    assert "Mr Kowalczyk" not in out
    assert "Kowalczyk Street" in out                    # bare surname untouched
    fakes = set(re.findall(r"M[rs]\.? (\w+)", out))
    assert len(fakes) == 1, out
    # A one-word "Dear" never mints a two-word person.
    assert not any(r.lower().startswith("mr") for r in _reals(z, "person"))
    # …and the binding round-trips through the key.
    z.write_key(tmp_path / "pseudonym_key.xlsx", log)
    reg2 = P._PnFakeRegistry()
    terms2, _ = P._pn_load_key(tmp_path / "pseudonym_key.xlsx", reg2, log)
    assert P.Pseudonymizer(terms2, {}, registry=reg2).apply(text) == out


def test_a_subject_line_is_a_mail_header_row():
    text = "Re: Brian Kowalczyk\nRE: Motion to Compel\nSubject: Your Claim\n"
    z = _pz()
    z.note_original(text)
    rows = {s for _c, s in z.mail_header_name_scan(text)}
    assert "Brian Kowalczyk" in rows, rows
    assert not any("Motion" in s or "Claim" in s for s in rows), rows


# ── 11. Relationship appositives ─────────────────────────────────────────────

def test_relationship_appositives_are_harvested():
    text = ("She lived with her mother, Rosa Delgado, and her brother, Tomas "
            "Delgado, until 2019. Her supervisor, Owen Blakely, terminated her.\n"
            "ANA DELGADO, a minor, by and through her guardian ad litem, Maria "
            "Delgado\nhis mother Jane Roe said that the mother, Mary Roe, was "
            "there.\n")
    z = _learn(text)
    reals = _reals(z, "person")
    for who in ("Rosa Delgado", "Tomas Delgado", "Owen Blakely", "Maria Delgado",
                "ANA DELGADO"):
        assert who in reals, reals
    # No possessive, or no comma: not the shape.
    assert "Jane Roe" not in reals and "Mary Roe" not in reals, reals
    out = z.apply(text)
    _gone(out, "Delgado", "Blakely")
    assert "her mother, " in out and "her guardian ad litem, " in out


def test_the_unknown_name_tier_reads_the_capacity_roles():
    vals = {s for _c, s in P._pn_unknown_name_findings(
        "Decedent Rosa Delgado died. Insured Brian Kowalczyk paid. "
        "Deponent Owen Blakely testified. Employee Handbook governs.", set())}
    assert {"Rosa Delgado", "Brian Kowalczyk", "Owen Blakely"} <= vals, vals
    # One word behind a capacity word is the thing it heads, not a person.
    assert "Handbook" not in vals, vals


# ── 12. Object-position institutions ─────────────────────────────────────────

def test_object_position_institutions_are_review_rows():
    text = ("She was employed by Sunbelt Rentals and later worked at Galpin "
            "Motors. She attended Crescenta Valley High School and was treated "
            "at Providence Holy Cross Medical Center. He was admitted to the "
            "bar and attended the hearing. She worked for Defendant. He was "
            "treated at the County of Los Angeles facility.\n")
    z = _pz()
    z.note_original(text)
    rows = {s for _c, s in z.narrative_name_scan(text)}
    assert {"Sunbelt Rentals", "Galpin Motors", "Crescenta Valley High School",
            "Providence Holy Cross Medical Center"} <= rows, rows
    assert not any("bar" in s.lower() or "hearing" in s.lower()
                   or "Defendant" in s or "County" in s for s in rows), rows
    # A tracked party goes quietly.
    z2 = _learn(text, parties=("Sunbelt Rentals",))
    z2.note_original(text)
    out = z2.apply(text)
    assert not any("Sunbelt" in s for _c, s in z2.narrative_name_scan(out))


# ── 13. IP address, partial SSN, international phone ─────────────────────────

def test_the_lesser_shapes_are_reported():
    text = ("Signed from IP 192.168.1.25 (section 1.2.3.4). Call +44 20 7946 "
            "0958 or (818) 555-1212. XXX-XX-6789; SSN ending in 6789; the last "
            "four digits of her Social Security number are 4321.")
    review = P._pn_review_findings(text)
    assert ("ip address", "192.168.1.25") in review, review
    assert not any(v == "1.2.3.4" for _c, v in review)
    assert ("international phone", "+44 20 7946 0958") in review, review
    assert not any("818" in v for _c, v in review)
    rows = _pz().reid_scan(text)
    assert ("REID partial ssn", "XXX-XX-6789") in rows, rows
    assert ("REID partial ssn", "SSN ending in 6789") in rows, rows
    assert any(s.endswith("4321") for c, s in rows if c == "REID partial ssn")


# ── The mask still governs every new name anchor ────────────────────────────

def test_a_name_inside_a_citation_is_never_harvested_by_the_new_anchors():
    text = ("Her employer, Sunbelt Rentals LLC, cited Lukather v. General Motors "
            "LLC (2010) 181 Cal.App.4th 1041 and Kremerman v. White Holdings "
            "LLC (2021) 71 Cal.App.5th 358.\n")
    z = _learn(text)
    reals = _reals(z)
    assert "Sunbelt Rentals LLC" in reals
    assert not any("General Motors" in r or "Lukather" in r or "White" in r
                   or "Kremerman" in r for r in reals), reals
    assert "Lukather v. General Motors LLC (2010) 181 Cal.App.4th 1041" in z.apply(text)
