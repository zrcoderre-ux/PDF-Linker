"""
The humans a service document names who carry no party-role anchor.

A motion-to-quash batch shipped the process server's real name 51 times and
the mailbox-store manager's 10. Neither is a party, so no party-role anchor
fired and neither ever entered the key — the whole harvest vocabulary was
built out of caption roles ("Defendant Travelers", "Attorneys for X").

The same batch's Reply carried a prior case's DOCKET as Exhibit A, a roster of
`SURNAME GIVENNAME <role>` rows. Every existing anchor is a role PREFIX, so a
role-SUFFIXED roster matched nothing: fourteen parties untouched, and — worse
— half-scrubbed wherever one token happened to be keyed from elsewhere
("Xiaoxia Deng" -> "Xiaoxia Ingersoll", 102 times). A half-scrub is more
dangerous than no scrub: a reviewer skimming for leaks sees the fake surname
and moves on.

Run:  cd PDF-Linker && python3 -m pytest tests/test_third_party_names.py -v
"""

import pytest

import pdf_linker as P

DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}


def _pz(names=()):
    reg = P._PnFakeRegistry()
    return P.Pseudonymizer(P._pn_build_terms(list(names), [], [], registry=reg),
                           DET, registry=reg)


# ─────────────────── third parties named by their job ───────────────────────

@pytest.mark.parametrize("text,name", [
    ("Michael Rodgers, a registered California process server, served it.",
     "Michael Rodgers"),
    ("Declaration of Lupe Lopez, the store manager, is attached.",
     "Lupe Lopez"),
    ("PROCESS SERVER: Ana Beltran", "Ana Beltran"),
    ("Registered Process Server: Ana Beltran", "Ana Beltran"),
    ("Notary Public: Harold Vance", "Harold Vance"),
    ("Custodian of Records: Priya Raman", "Priya Raman"),
    ("Person who served papers\na. Name: Roberto Salgado", "Roberto Salgado"),
])
def test_a_third_party_named_by_role_is_registered(text, name):
    assert name in P._pn_label_names(text), P._pn_label_names(text)


def test_the_process_server_is_actually_scrubbed():
    z = _pz()
    text = ("Michael Rodgers, a registered California process server, "
            "attempted service. Mr. Rodgers made three attempts.")
    z.register_label_names(text)
    out = z.apply(text)
    assert "Michael Rodgers" not in out
    assert "Rodgers" not in out, "the bare surname is the form the brief uses"


def test_the_role_words_themselves_are_left_alone():
    z = _pz()
    text = "Michael Rodgers, a registered California process server, served it."
    z.register_label_names(text)
    out = z.apply(text)
    for word in ("registered", "California", "process server"):
        assert word in out, f"{word!r} was rewritten"


# ─────────────────── the docket roster (role-SUFFIXED) ──────────────────────

DOCKET = """
Case Summary
Deng Xiaoxia          Plaintiff
WU JING               Plaintiff
Shi Fiona aka Yaqin Shi | Defendant
Weisskopf Stephen D.  Attorney for Plaintiff
Hou Zhenyang          Cross-Defendant
"""


def test_a_docket_roster_row_is_harvested():
    got = P._pn_docket_roster_names(DOCKET)
    assert "Deng Xiaoxia" in got
    assert "Hou Zhenyang" in got
    assert "Weisskopf Stephen D." in got, "a middle initial must not disqualify"


def test_a_two_letter_surname_still_qualifies():
    # The loose-harvest length screen applies to the ROW, not to each token:
    # a roster row carries its own corroboration, and "Wu"/"Yu"/"Ng" are real.
    assert "WU JING" in P._pn_docket_roster_names(DOCKET)


def test_an_aka_row_binds_both_spellings():
    z = _pz()
    z.register_docket_names(DOCKET)
    out = z.apply(DOCKET)
    for real in ("Shi", "Fiona", "Yaqin"):
        assert real not in out.split(), f"{real!r} survived the alias row"


def test_no_token_of_a_roster_name_survives():
    # The half-scrub is the finding this exists to prevent.
    z = _pz()
    z.register_docket_names(DOCKET)
    out = z.apply(DOCKET)
    for real in ("Deng", "Xiaoxia", "Jing", "Zhenyang", "Weisskopf"):
        assert real.lower() not in out.lower(), f"{real!r} survived"


def test_the_role_column_survives():
    z = _pz()
    z.register_docket_names(DOCKET)
    out = z.apply(DOCKET)
    for role in ("Plaintiff", "Defendant", "Cross-Defendant",
                 "Attorney for Plaintiff"):
        assert role in out


@pytest.mark.parametrize("text", [
    # A pleading caption: the role closes with a comma, not the line.
    "JOHN DOE,                    Plaintiff,",
    # A heading whose words are ordinary vocabulary.
    "The Motion To Quash Service   Defendant",
    # A date line.
    "Dated June 3, 2026            Plaintiff",
    # A single word before the role is not a name run.
    "Smith                        Plaintiff",
])
def test_a_non_roster_line_is_not_harvested(text):
    assert not P._pn_docket_roster_names(text), text


def test_a_public_entity_roster_row_is_kept():
    got = P._pn_docket_roster_names("County of Los Angeles     Defendant\n")
    assert not got, got


# ─────────────────── identifiers a public registry inverts ──────────────────

def test_a_labelled_registration_number_is_faked():
    # "a registered California process server, Registration No. 833, San
    # Bernardino County" names one person in the county's public registry.
    z = _pz()
    text = ("a registered California process server, Registration No. 833, "
            "San Bernardino County.")
    z.register_identifiers(text)
    out = z.apply(text)
    assert "833" not in out
    assert "Registration No." in out          # the label stays
    assert "San Bernardino County" in out     # the venue stays


def test_a_long_bond_number_is_faked_bare():
    z = _pz()
    text = "Bond Number 4429117 was posted with the county."
    z.register_identifiers(text)
    assert "4429117" not in z.apply(text)


def test_a_short_bare_counter_is_not_rewritten():
    # The reason a SHORT registration number is registered only in its
    # labelled form: a bare 3-digit number is a page, exhibit or paragraph
    # counter far more often than an identifier.
    z = _pz()
    text = ("Registration No. 833. See Response No. 101, Material Fact "
            "No. 110, and Exhibit 833 at page 833.")
    z.register_identifiers(text)
    out = z.apply(text)
    assert "Response No. 101" in out
    assert "Material Fact No. 110" in out
    assert "Exhibit 833 at page 833" in out


# ─────────────────── the e-filing stamp names two clerks ────────────────────

def test_the_filing_stamp_clerks_are_scrubbed():
    z = _pz()
    stamp = ("Electronically FILED 6/01/2026 9:42 AM\n"
             "David W. Slayton, Executive Officer/Clerk of Court\n"
             "By: V. Sino-Cruz, Deputy Clerk\n"
             "Superior Court of California, County of Los Angeles\n")
    z.register_court_names(stamp)
    out = z.apply(stamp)
    assert "Slayton" not in out, "the Executive Officer signs every stamp"
    assert "Sino-Cruz" not in out
    assert "Executive Officer/Clerk of Court" in out   # the role stays
    assert "County of Los Angeles" in out              # the venue stays
    assert "6/01/2026 9:42 AM" in out                  # the filing date stays
