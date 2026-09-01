"""
A COURT'S CASE-TYPE CODE is not a name, and a broken case number is still one.

A delivered folder came back with the letters of its dockets replaced by a
surname — "STCP" faked as "LAMBOURNE" — while the number they belong to shipped
in the clear. Both halves come from one cause: a case number does not always
reach the text glued. Extraction spaces it out, a narrow caption column wraps
it, and the strict statewide shape then matches nothing, so

  * the docket was never tracked, never faked and never reported, and
  * the code was left standing beside the caption as an ordinary capitalised
    word, where any name harvest could read it as a party.

The letters of a docket say which courthouse and which kind of proceeding.
That is public taxonomy: it identifies no one, so renaming it protects nobody
and costs the reader the form of the document.

Run:  cd PDF-Linker && python3 -m pytest tests/test_court_code_case_numbers.py -v
"""

import pdf_linker as P


def _pz(text=None):
    """A pseudonymizer that has read `text` the way the pre-scan does — the
    whole corpus first (`note_docket_codes`), then the harvest."""
    reg = P._PnFakeRegistry()
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    pz = P.Pseudonymizer([], det, registry=reg)
    if text is not None:
        pz.note_docket_codes(text)
        P._pn_learn_from_text(pz, text)
    return pz


def _reals(pz, category=None):
    return [t.real for t in pz.terms
            if category is None or t.category == category]


CAPTION = ("HELEN RASHO, an individual,        Case No.: 25STCP01234\n"
           "                Petitioner,        [Assigned to Dept. 82]\n")


# ───────────────────── the code is never a name ─────────────────────────────

def test_the_letters_of_a_case_number_are_never_harvested_as_a_name():
    pz = _pz(CAPTION + "This matter, 25 STCP 01234, is at issue.\n")
    for real in _reals(pz):
        assert "STCP" not in real.upper() or real.upper().startswith("25")
    assert not [t for t in pz.terms
                if t.category in ("person", "entity") and "STCP" in t.real]


def test_a_code_standing_alone_in_a_name_slot_is_refused():
    # The residual the mask cannot reach: the code written away from any
    # digits, in a slot a name harvest anchors on. The folder's own dockets
    # are the corroboration that those letters are a court code.
    pz = _pz(CAPTION + "Attn: STCP Clerk\n")
    assert not [t for t in pz.terms if "STCP" in t.real.upper()
                and t.category != "case_number"]
    assert "STCP Clerk" in pz.apply("Attn: STCP Clerk\n")


def test_a_refused_code_takes_its_near_spellings_with_it():
    # `_pn_name_variants` mints "STCCP"/"STPC" carrying the refused term's own
    # fake. Screened one at a time they outlive their parent and go on
    # renaming a mistyped code.
    pz = _pz(CAPTION + "Attn: STCP Clerk\n")
    for t in pz.terms:
        assert P._pn_osa_distance(t.real.upper(), "STCP") > 2 or \
            t.category == "case_number"


def test_the_operators_own_party_list_is_never_screened():
    # Refusing a real name the operator supplied is the failure the whole
    # method exists to prevent: a party genuinely named for those letters is
    # theirs to declare, and the screen is scoped to a document harvest.
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Stcp Holdings, LLC"], ["25STCP01234"], [],
                              registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    pz = P.Pseudonymizer(terms, det, registry=reg)
    pz.note_docket_codes(CAPTION)
    assert [t for t in pz.terms if "Stcp Holdings" in t.real]


# ───────────────────── a broken number is still a number ────────────────────

def test_a_spaced_case_number_is_faked_and_marked():
    pz = _pz(CAPTION + "Related to 25 STCP 05678 in this court.\n")
    out = pz.apply("Related to 25 STCP 05678 in this court.\n")
    assert "25 STCP 05678" not in out
    assert "STZV" in out
    assert out.startswith("Related to 25 ")     # the filing year survives


def test_a_wrapped_case_number_is_faked():
    body = CAPTION + "Case No.: 25STCP\n07777\n"
    pz = _pz(body)
    assert "25STCP\n07777" not in pz.apply("Case No.: 25STCP\n07777\n")


def test_both_spellings_of_one_docket_share_their_digits():
    # One matter has one number. Seeded on the spelling, the two drew
    # unrelated digit runs and one docket read as two.
    pz = _pz(CAPTION + "Also filed as 25 STCP 01234.\n")
    fakes = {t.real: str(t.fake) for t in pz.terms
             if t.category == "case_number"}
    glued = fakes["25STCP01234"]
    spaced = fakes["25 STCP 01234"]
    assert spaced.replace(" ", "") == glued        # same number to a reader
    assert spaced != glued                         # two reversible rows


def test_a_glued_case_number_fakes_exactly_as_it_always_did():
    # The canonical spelling of a glued number is itself, so nothing already
    # delivered moves.
    reg = P._PnFakeRegistry()
    was = reg.digits("25STCP01234", "caseno", keep_prefix=2,
                     template=P._pn_caseno_template("25STCP01234"))
    assert P._pn_fake_caseno("25STCP01234", P._PnFakeRegistry()) == was


# ───────────────────── the seam needs corroboration ─────────────────────────

def test_a_statute_cite_of_the_same_shape_is_never_taken_for_a_docket():
    # "42 USC 12345" and "29 CFR 160000" have exactly the open-seam shape.
    # Renaming authority is the failure the whole method refuses, so the code
    # must be one this folder writes inside a well-formed docket.
    text = CAPTION + "See 42 USC 12345 and 29 CFR 160000.\n"
    pz = _pz(text)
    out = pz.apply("See 42 USC 12345 and 29 CFR 160000.\n")
    assert "42 USC 12345" in out and "29 CFR 160000" in out


def test_an_uncorroborated_open_seam_is_left_alone():
    # Stated residual: with no well-formed docket anywhere in the folder there
    # is nothing to say those letters are a court code, so the value stands.
    # The MASK is looser and still refuses it a name — that costs nothing.
    text = "Filed as 25 STCP 05678 in this court.\n"
    pz = _pz(text)
    assert not [t for t in pz.terms if t.category == "case_number"]
    assert not [t for t in pz.terms if "STCP" in t.real.upper()]


def test_corroboration_reaches_across_the_folder():
    # A caption states the number properly and the exhibit page whose text
    # layer broke it apart carries only the open spelling. Corroboration that
    # stopped at the file boundary would leave that page's docket in the clear.
    pz = _pz()
    pz.note_docket_codes(CAPTION)
    P._pn_learn_from_text(pz, "EXHIBIT A\nCase 25 STCP 09090 (Dept. 82)\n")
    assert [t for t in pz.terms
            if t.category == "case_number" and t.real == "25 STCP 09090"]


def test_the_mask_preserves_length_and_whitespace():
    # Offsets a label-anchored pattern depends on have to survive the blanking.
    raw = "Attn: Helen Rasho\nCase No.: 25STCP01234\nDept. 82\n"
    masked = P._pn_mask_case_numbers(raw)
    assert len(masked) == len(raw)
    # Blanking turns the value's characters into spaces, so masked text holds
    # MORE whitespace — but every character that was whitespace still is, at
    # the same offset, so the line structure is untouched.
    assert all(masked[i].isspace() for i, c in enumerate(raw) if c.isspace())
    assert masked.count("\n") == raw.count("\n")
    assert "25STCP01234" not in masked
