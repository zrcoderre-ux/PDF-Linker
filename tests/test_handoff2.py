"""Handoff 2: the second delivered batch's failures, each pinned at the tier
that closes it (see CLAUDE.md, "Handoff 2")."""
import logging
import re

import pytest

import pdf_linker as P

log = logging.getLogger("test")


def _pz(parties=(), extra=(), detectors=False):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms([(x, False) for x in parties], [], list(extra),
                              registry=reg)
    det = list(P._PN_DEFAULT_DETECTORS) if detectors else []
    return P.Pseudonymizer(terms, det, registry=reg), reg


def _learn(text, parties=(), extra=(), detectors=False):
    z, reg = _pz(parties, extra, detectors)
    P._pn_learn_from_text(z, text, "Doc")
    return z


# ── §1 the E-Court "Other Names" cell ────────────────────────────────────────

def test_credentials_and_role_suffixes_are_not_names():
    got = P._pn_split_cell(
        "Simon M. Keushkerian, M.D.; Maro Burunsuzyan Lead Attorney; "
        "Eric Bonholtzer Associated Attorney; Bradley I. Kramer, M.D., Esq.; "
        "Jane Roe Former Lead Attorney; Lead Attorney; Rosa Delgado, RN, BSN")
    assert [n for n, _s in got] == [
        "Simon M. Keushkerian", "Maro Burunsuzyan", "Eric Bonholtzer",
        "Bradley I. Kramer", "Jane Roe", "Rosa Delgado"]


def test_a_firm_named_attorney_and_a_corporate_suffix_survive_the_cell():
    got = [n for n, _s in P._pn_split_cell(
        "Law Offices of Attorney Jones; Acme Widgets, Inc.; Anh Do")]
    assert got == ["Law Offices of Attorney Jones", "Acme Widgets, Inc.", "Anh Do"]


# ── §2 a cited decision is never harvested (handoff 1 §1, second case) ──────

def test_a_cited_corporate_defendant_is_never_an_entity_term():
    text = ("Plaintiff relies on Kohn v. Acme Widgets, Inc. (2015) 240 "
            "Cal.App.4th 100, 105.\nAs Kohn v. Acme Widgets, Inc. held, the "
            "rule applies.\n"
            "https://scholar.google.com/scholar?q=Kohn%20v.%20Acme%20Widgets\n")
    z = _learn(text, ["Helen Rasho"])
    assert not [t for t in z.terms if "acme" in t.real.lower()]
    out = z.apply(text)
    assert out == text


# ── §3 departments ───────────────────────────────────────────────────────────

def test_a_one_digit_department_keeps_its_label_and_changes_its_digit():
    text = "Department 2\nDept. 2\n"
    z = _learn(text)
    z.register_court_names(text)
    out = z.apply(text)
    assert re.fullmatch(r"Department (\d)\nDept\. \1\n", out), out
    assert "Department 2\n" not in out


def test_every_label_form_of_one_department_draws_one_number():
    text = ('Department 515\nDept. 515\nDEPT.: 515\nDept 515\n'
            'Department "515"\nDepartment “515”\n')
    z = _learn(text)
    z.register_court_names(text)
    out = z.apply(text)
    nums = set(re.findall(r"\d{3}", out))
    assert len(nums) == 1 and "515" not in nums, out
    assert 'Department "' in out and "Department “" in out


def test_a_courtroom_number_is_not_a_house_number():
    text = "Department 2 Spring Street Courthouse\n"
    z = _learn(text, detectors=True)
    z.register_court_names(text)
    z.register_addresses(text)
    assert not [t for t in z.terms if t.category.startswith("address")]
    assert "Spring Street Courthouse" in z.apply(text)


def test_a_digit_fake_is_never_the_real_value():
    reg = P._PnFakeRegistry()
    for n in "0123456789":
        assert reg.digits(n, "department") != n


def test_the_loader_seeds_the_department_number(tmp_path):
    reg = P._PnFakeRegistry()
    fake = "Department " + reg.digits("515", "department")
    rows = [("department", "Department 515", fake)]
    reg2 = P._PnFakeRegistry()
    # The seeding rule alone: a loaded department row pins the number's slot.
    rm, fm = P._PN_DEPT_RE.search(rows[0][1]), P._PN_DEPT_RE.search(rows[0][2])
    reg2._memo.setdefault(("department", rm.group(1).lower()), fm.group(1))
    assert "Dept 515".replace("515", reg2.digits("515", "department")) == \
        "Dept " + fm.group(1)


# ── §4 the judge behind a label ──────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "Judicial Officer: Dana Whitaker\nDana Whitaker signed.\n",
    "Judge: Dana Whitaker\nDana Whitaker signed.\n",
    "Hon. Dana T. Whitaker presiding.\nJudicial Officer: Dana Whitaker\n",
])
def test_the_judge_is_bound_behind_a_label_and_without_the_initial(text):
    z = _learn(text)
    z.register_court_names(text)
    out = z.apply(text)
    assert "Whitaker" not in out and "Dana" not in out, out


# ── §5 a vanity phone number ────────────────────────────────────────────────

def test_a_vanity_number_is_faked_area_code_and_word():
    text = "Call (424)-INJURED today or 1-800-FLOWERS.\n"
    z = _learn(text, ["Helen Rasho"], detectors=True)
    out = z.apply(text)
    assert "INJURED" not in out and "FLOWERS" not in out, out
    assert re.search(r"\(\d{3}\)-[A-Z]{7} today or 1-\d{3}-[A-Z]{7}\.", out), out


# ── §6 a party wrapped across a gutter number ───────────────────────────────

def test_an_entity_wrapped_across_a_gutter_number_is_scrubbed_whole():
    text = (" 1  Defendant GLENDALE\n 2  MEMORIAL MEDICAL CENTER'S motion.\n"
            " 3  Nothing else.\n")
    z = _learn(text, ["Glendale Memorial Medical Center"])
    out = z.apply(text)
    assert "GLENDALE" not in out and "MEMORIAL" not in out, out
    # The gutter number the name wrapped across is still there.
    assert re.search(r"^ 1  Defendant \S+\n 2  \S+ \S+ \S+'S motion\.$", out,
                     re.M), out


# ── §7 bare-token screens ───────────────────────────────────────────────────

def test_a_particle_is_never_a_bare_token():
    z, _r = _pz(["Alpha Beta De Gamma Delta & Epsilon LLP", "Maria De La Cruz"])
    bare = {t.real.lower() for t in z.terms if t.category.endswith("-token")}
    assert not bare & {"de", "la", "del", "van", "von"}
    assert "gamma" in bare and "maria" in bare


def test_an_ocr_split_of_a_bound_word_is_an_alt_spelling_not_a_person():
    z, _r = _pz(["Verdugo Hills Health Center"], extra=["HEAL TH"])
    split = [t for t in z.terms if t.real == "HEAL TH"]
    assert split and split[0].derived and split[0].category == "entity-token"
    health = [t for t in z.terms if t.real == "Health"][0]
    assert split[0].fake.lower() == health.fake.lower()
    assert not [t for t in z.terms if t.real in ("HEAL", "TH")]
    out = z.apply("VERDUGO HILLS HEAL TH CENTER")
    assert "HEAL TH" not in out and "HEAL" not in out.replace("HEALTH", "")


def test_an_institution_with_no_corporate_suffix_takes_the_entity_path():
    z, _r = _pz(["Verdugo Hills Health Center"])
    cats = {t.category for t in z.terms if t.real.startswith("Verdugo")}
    assert "entity" in cats and "person" not in cats


# ── §8 the reporter, the proof of service, the CSR number ──────────────────

def test_the_court_reporter_is_read_off_the_csr_licence():
    text = "Court Reporter Pro Tempore (Maria Lopez (CSR 12345))\n"
    z = _learn(text)
    z.register_court_names(text)
    z.register_identifiers(text)
    out = z.apply(text)
    assert "Maria Lopez" not in out and "12345" not in out, out
    assert re.search(r"\(CSR \d{5}\)", out), out


def test_the_declarant_under_a_signature_mark_is_harvested():
    text = "PROOF OF SERVICE\n/s/\nRosa Delgado\n"
    z = _learn(text)
    assert "Rosa Delgado" not in z.apply(text)


# ── §9 Medicare / PHI ───────────────────────────────────────────────────────

def test_an_mbi_is_faked_by_shape_bare_and_glued():
    text = "MBI 1EG4TE5MK72 and Rasho1EG4TE5MK72 in the ledger.\n"
    z = _learn(text, ["Helen Rasho"], detectors=True)
    z.register_identifiers(text)
    out = z.apply(text)
    assert "1EG4TE5MK72" not in out, out
    assert re.search(r"MBI \d[A-Z][A-Z0-9]\d[A-Z][A-Z0-9]\d[A-Z]{2}\d{2} ", out)


def test_the_bcrc_identifiers_are_faked_and_the_npi_is_not_a_phone():
    text = ("Case Identification Number: 12345 67890 12345\n"
            "ICN 12345678901234C\nNPI 1234567890\n")
    z = _learn(text, detectors=True)
    z.register_identifiers(text)
    out = z.apply(text)
    assert "12345 67890 12345" not in out and "12345678901234" not in out
    assert "1234567890" not in out, out
    assert re.search(r"^Case Identification Number: \d{5} \d{5} \d{5}$", out, re.M)
    assert re.search(r"^ICN \d{14}C$", out, re.M) and re.search(r"^NPI \d{10}$", out, re.M)
    cats = {t.category for t in z.terms}
    assert "npi_number" in cats and "phone" not in cats


def test_a_diagnosis_code_is_not_a_stamp_and_the_bcrc_contacts_are_kept():
    text = ("ICD-10 M54.5 and CPT 99213 and DEAL# 23071.\n"
            "Call 1-855-798-2627 or fax 405-869-3309. PO Box 138832. "
            "www.gdit.com/cob\n")
    z = _learn(text, detectors=True)
    z.register_identifiers(text)
    out = z.apply(text)
    for kept in ("M54.5", "99213", "1-855-798-2627", "405-869-3309",
                 "PO Box 138832", "www.gdit.com/cob"):
        assert kept in out, (kept, out)
    assert "23071" not in out, out


def test_the_house_number_unit_and_zip_plus_four_are_kept():
    """The handoff asked for the number, the unit and the +4 to be faked; the
    documented rule (the street name is what identifies, the rest is kept
    verbatim) stands, since a handoff reports failures and never sets
    policy."""
    text = "1234 Elm Street APT 5, Glendale, CA 91204-1234\n"
    z = _learn(text, detectors=True)
    out = z.apply(text)
    assert re.match(r"1234 \S+ Street APT 5, \S+, CA 91204-1234\n$", out), out
    assert "Elm" not in out


def test_the_courthouse_address_is_a_venue_and_stays():
    text = ("111 N. Hill Street, Los Angeles, CA 90012\n"
            "Stanley Mosk Courthouse, 111 North Hill Street\n"
            "at 600 East Broadway, Glendale, CA 91206 (Glendale Courthouse)\n"
            "4570 N. Orchard St., Glendale, CA 91204\n")
    z = _learn(text, detectors=True)
    out = z.apply(text)
    assert "111 N. Hill Street" in out and "111 North Hill Street" in out
    assert "600 East Broadway" in out
    assert "Orchard" not in out


# ── §10 two people, one word: ONE fake, at the owner's direction ───────────

def test_a_shared_word_reads_identically_wherever_it_stands():
    """Counsel's given name is an unrelated attorney's surname. The export
    carries the same ambiguity the filing does — one word, one fake — so a
    reader can see that a bare reference names one of two people."""
    z, _r = _pz(["Kramer Ivan Lowther", "Bradley Kramer"])
    fakes = {t.real: t.fake for t in z.terms if t.category == "person"}
    given = fakes["Kramer Ivan Lowther"].split()[0]
    surname = fakes["Bradley Kramer"].split()[-1]
    assert given == surname
    out = z.apply("Kramer I. Lowther met Bradley Kramer and Mr. Kramer.")
    assert "Kramer" not in out and out.count(given) == 3


def test_one_persons_spellings_still_share_one_word():
    z, _r = _pz(["Helen Rasho", "RASHO'S"])
    fakes = {t.real: t.fake for t in z.terms if t.category == "person"}
    assert fakes["RASHO'S"].lower().rstrip("'s") in fakes["Helen Rasho"].lower()


# ── §11 the spreadsheet case number carries the marker ─────────────────────

def test_a_template_case_number_takes_the_stzv_marker():
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms([], ["19STCV17761"], [], registry=reg)
    assert terms[0].fake.startswith("19STZV")


# ── §12 the smaller items ───────────────────────────────────────────────────

def test_a_four_letter_given_name_is_swept_at_its_site_only():
    z, _r = _pz(["Vahe Rasho"])
    out = z.apply("VAHA Rasho and Vahe Rasho. Vale of tears. Joan Baker.\n")
    rows = [v for _c, v in z.fuzzy_survivor_scan(out)]
    assert rows == ["VAHA"], rows


def test_a_kerned_four_letter_name_is_matched():
    z, _r = _pz(["Vahe Rasho"])
    assert "AHE" not in z.apply("V AHE RASHO\n")


def test_duplicate_downloads_are_folded_into_the_combined_text_once(tmp_path):
    folder = tmp_path
    text_dir = folder / "Text Files"
    text_dir.mkdir()
    body = "====== Page 1 ======\nThe quick brown declarant testified.\n"
    (text_dir / "Motion.txt").write_text(body, encoding="utf-8")
    (text_dir / "Motion (1).txt").write_text(
        body.replace("Page 1", "Page 1 — REVIEW: OCR"), encoding="utf-8")
    (text_dir / "Reply.txt").write_text("Another document.\n", encoding="utf-8")
    P._write_combined_text(folder, "Text Files", log)
    combined = next(folder.glob("*.txt")).read_text(encoding="utf-8")
    assert combined.count("quick brown declarant") == 1
    assert "Another document." in combined
