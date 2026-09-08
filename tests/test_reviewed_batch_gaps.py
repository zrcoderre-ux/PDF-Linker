"""Seven shapes a reviewed batch shipped in the clear, each a near-miss of a
rule that already existed.

  * an instrument number with a TWO-digit year ("25-0810028");
  * the dotted "A.P.N." label and a SPACED parcel number;
  * a house number WELDED to its directional ("1100N Central Ave");
  * a notary named only in the STAMP BOX (name alone on a line above
    "Notary Public");
  * a one-word, coined dba ("Fundamental Capital LLC dba Kapitus");
  * a title report's "GRANTOR:" / "GRANTEE:" / "TRUSTOR:" / "LENDER:"
    labels and the SOS "Agent for Service of Process:" label;
  * a person named in a CAPACITY ("Robert Kersnick, as Co-Trustee") and a
    role-first JUDGMENT CREDITOR.

Run:  cd PDF-Linker && python3 -m pytest tests/test_reviewed_batch_gaps.py -v
"""
import pytest

import pdf_linker as P


def _scrub(text, parties=()):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms([(p, False) for p in parties], [], [], registry=reg)
    z = P.Pseudonymizer(terms, list(P._PN_DEFAULT_DETECTORS), registry=reg)
    P._pn_learn_from_text(z, text, "Doc")
    return z, z.apply(text)


def _gone(text, *values, parties=()):
    _z, out = _scrub(text, parties)
    for v in values:
        assert v not in out, (v, out)
    return out


def _kept(text, *values):
    _z, out = _scrub(text)
    for v in values:
        assert v in out, (v, out)
    return out


# ── identifiers ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("line", [
    "Instrument No. 25-0810028",
    "Document No. 25-0668490",
    "recorded as Instrument No. 2003-9335023",
])
def test_an_instrument_number_with_a_two_digit_year_is_faked(line):
    out = _gone(line, line.split()[-1])
    assert out.startswith(line.rsplit(" ", 1)[0])       # the label stands


@pytest.mark.parametrize("line", [
    "A.P.N.: 2181-028-003",
    "APN 2181 028 005",
    "APN: 2181-028-002",
    "Assessor's Parcel Number: 2181-028-004",
])
def test_the_parcel_number_is_faked_under_every_label_spelling(line):
    _gone(line, line.split()[-1] if "-" in line.split()[-1] else "2181 028 005")


def test_a_short_reference_number_is_not_an_instrument():
    _kept("Reference No. 25-08 is the file.", "25-08")


# ── the welded directional ──────────────────────────────────────────────────

def test_a_house_number_welded_to_its_directional_is_an_address():
    z, out = _scrub("1100N Central Ave #1, Glendale, CA 91201\n"
                    "1100 N Central Ave #1, Glendale, CA 91201")
    lines = out.split("\n")
    assert "Central" not in out
    assert lines[0] == lines[1], "the two spellings are one parcel"
    assert lines[0].startswith("1100 ")                 # the number is kept


def test_a_number_glued_to_prose_is_not_an_address():
    _kept("24Hour Fitness Center opened", "24Hour Fitness Center")


# ── the notary's stamp box ──────────────────────────────────────────────────

STAMP = ("State of California\nCounty of Los Angeles\n"
         "SHABBIR AZAM\nNotary Public - California\nLos Angeles County\n"
         "Commission # 2475537\n\n"
         "JASPER JULIAN JORGENSEN-HANSEN\nCOMM. #2475538\n"
         "NOTARY PUBLIC - CALIFORNIA\n\n"
         "WITNESS my hand and official seal.\nSignature\nNotary Public\n")


def test_a_notary_named_only_in_the_stamp_box_is_faked():
    out = _gone(STAMP, "SHABBIR AZAM", "JORGENSEN-HANSEN", "2475537", "2475538")
    for furniture in ("State of California", "County of Los Angeles",
                      "Los Angeles County", "Notary Public - California",
                      "Signature\nNotary Public"):
        assert furniture in out, (furniture, out)


# ── the one-word dba ────────────────────────────────────────────────────────

def test_a_coined_one_word_dba_is_harvested():
    out = _gone("Fundamental Capital LLC dba Kapitus filed a claim.",
                "Kapitus", "Fundamental Capital")
    assert " dba " in out


def test_a_vocabulary_word_is_not_a_dba():
    _kept("Acme Widgets LLC dba Court filed a claim.", "dba Court")


def test_the_dba_head_stops_at_a_capacity_word():
    # The head phrase may wrap; it must not reach back into the party named
    # in a capacity on the line above.
    z, out = _scrub("Mary Vance, Successor Trustee\n"
                    "Fundamental Capital LLC dba Kapitus filed a claim.")
    assert out.count("\n") == 1, out
    assert not any("Successor" in t.real for t in z.terms), \
        [t.real for t in z.terms]
    assert "Kapitus" not in out and "Mary Vance" not in out


# ── the title report's labels ───────────────────────────────────────────────

TICOR = ("GRANTOR: MARK SEREBRYANYY AND SVETLANA SEREBRYANAYA\n"
         "GRANTEE: OFER ADI, A SINGLE MAN\n"
         "TRUSTOR: ROBERT KERSNICK\n"
         "LENDER: WASHINGTON MUTUAL BANK FA\n"
         "Agent for Service of Process: Edward Shkolnikov\n")


def test_title_report_labels_harvest_the_names_behind_them():
    out = _gone(TICOR, "SEREBRYANYY", "SEREBRYANAYA", "OFER ADI",
                "KERSNICK", "WASHINGTON MUTUAL", "Shkolnikov")
    for label in ("GRANTOR:", "GRANTEE:", "TRUSTOR:", "LENDER:",
                  "Agent for Service of Process:", "A SINGLE MAN"):
        assert label in out, (label, out)


# ── capacities and the judgment creditor ────────────────────────────────────

@pytest.mark.parametrize("line,name", [
    ("Robert Kersnick, as Co-Trustee of the Kersnick Family Trust, signed.",
     "Robert Kersnick"),
    ("Mary Vance, Successor Trustee, executed the deed.", "Mary Vance"),
    ("Owen Blakely, in his capacity as Executor, filed the petition.",
     "Owen Blakely"),
    ("Judgment creditor Damon Paikos recorded an abstract of judgment.",
     "Damon Paikos"),
    ("The judgment debtor Rosa Delgado owns the parcel.", "Rosa Delgado"),
])
def test_a_person_named_in_a_capacity_is_faked(line, name):
    out = _gone(line, name)
    # The capacity word itself is furniture and stays.
    for word in ("Co-Trustee", "Successor Trustee", "Executor",
                 "Judgment creditor", "judgment debtor"):
        if word in line:
            assert word in out, (word, out)
