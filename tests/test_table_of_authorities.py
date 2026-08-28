"""
A table of authorities is a list of PUBLISHED DECISIONS. Two things follow, and
the tool got both wrong.

**It must never be re-OCR'd.** `_text_looks_garbled` measures the fraction of
characters that are letters or digits, and a table of authorities is mostly dot
leaders — neither. So it reads as symbol soup and the page is sent into
DESTRUCTIVE re-OCR: the real text redacted, replaced by 300-dpi guesses. The
delivered Demurrer's page 5 is 100% `GlyphLessFont` over a single image, the
only OCR'd page in its folder. Measured on the real corpus the surviving tables
cleared the cut by ONE PERCENTAGE POINT (0.364 against 0.35), and the tool's own
extraction path put one at 0.342 — already over. The damage also conceals
itself: Tesseract turns leaders into letter-soup, so the rebuilt page measures
0.938 and a second run reads it as healthy.

**It must never be a SOURCE of terms.** Nothing in a table of authorities is a
value of this case, and everything in it is a name the tool must not rewrite.
Harvesting one is all cost — measured, a single table page offered up
`Greenwich Investors XXVI, LLC`, `Specialized Loan Serv., LLC`, `Peterson
Enters., LLC`, `Grancare, LLC` and the published docket number `BC543295` as
this case's parties and identifiers. Those are the names that then shipped
renamed.

Run:  cd PDF-Linker && python3 -m pytest tests/test_table_of_authorities.py -v
"""

import logging

import pytest

import pdf_linker as P

log = logging.getLogger("test")
DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}

# The real shape, from the pre-linker Opposition's table of authorities: the
# case name on its own line, the cite plus leader plus page below it.
TOA = """\
LAW OFFICES OF STEPHEN S. SMITH, P.C.
303 North Glenoaks Blvd., Suite 200
TABLE OF AUTHORITIES
CASE LAW
Hamilton v. Greenwich Investors XXVI, LLC
(2011) 195 Cal.App.4th 1039 .................................................. 7-8
Reeder v. Specialized Loan Serv., LLC
(2020) 52 Cal.App.5th 795 .................................................... 5
Annocki v. Peterson Enters., LLC
232 Cal. App. 4th 32 (2014) .................................................. 4
STATUTES
Code of Civil Procedure section 430.10 ....................................... 3
"""


def _harvest(text):
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms([], [], [], registry=reg), DET,
                        registry=reg)
    P._pn_learn_from_text(z, text)
    return z


# ─────────────────── the table is not a source of terms ─────────────────────

@pytest.mark.parametrize("authority", [
    "Greenwich Investors XXVI, LLC",
    "Specialized Loan Serv., LLC",
    "Peterson Enters., LLC",
])
def test_a_cited_decision_is_never_harvested_from_the_table(authority):
    reals = {t.real for t in _harvest(TOA).terms}
    assert authority not in reals, f"{authority!r} is a published decision"


def test_no_bare_token_of_an_authority_survives_either():
    # The bare tokens are what fired inside ordinary words elsewhere in the
    # folder ("Serv" -> "reservation", "Loan" -> "refinance a loan").
    bases = {P._pn_word_base(w) for t in _harvest(TOA).terms
             for w in str(t.real).split()}
    assert not bases & {"greenwich", "specialized", "loan", "serv", "peterson",
                        "enters", "annocki", "hamilton", "reeder"}


def test_a_published_docket_number_is_not_registered_as_an_identifier():
    text = TOA + "Krikorian Inv. Servs. v. Radmanesh\nNo. BC543295 ......... 9\n"
    assert not [t for t in _harvest(text).terms if "BC543295" in str(t.real)]


def test_the_letterhead_on_the_same_page_is_still_harvested():
    # Masking is scoped to the ENTRIES. The firm printed in the margin of a
    # table page is a real value and must keep being scrubbed.
    reals = {t.real for t in _harvest(TOA).terms}
    assert any("STEPHEN S. SMITH" in r for r in reals), reals


def test_a_body_page_is_untouched_by_the_mask():
    body = ("Declaration of Michael Rodgers, a registered California process "
            "server. Attn: Sarah Whitlock")
    reals = {t.real for t in _harvest(body).terms}
    assert {"Michael Rodgers", "Sarah Whitlock"} <= reals


def test_an_authority_cited_only_in_body_text_still_reaches_the_pruners():
    # The mask is preventive and scoped to tables; the reactive pruners still
    # own the case where a decision is cited in prose with no table to mask.
    body = ("Plaintiff relies on Hamilton v. Greenwich Investors XXVI, LLC "
            "(2011) 195 Cal.App.4th 1602.")
    reals = {t.real for t in _harvest(body).terms}
    assert "Greenwich Investors XXVI, LLC" in reals


# ─────────────────── the span walk-back cannot escape the table ─────────────

def test_the_mask_is_length_preserving():
    assert len(P._pn_mask_toa_entries(TOA)) == len(TOA)


def test_the_walk_back_stops_at_a_heading():
    masked = P._pn_mask_toa_entries(TOA)
    assert "TABLE OF AUTHORITIES" in masked
    assert "CASE LAW" in masked
    assert "STATUTES" in masked


def test_the_walk_back_stops_at_the_previous_entry():
    # Two entries in a row: the second must not swallow the first's page line.
    masked = P._pn_mask_toa_entries(TOA)
    assert "Hamilton" not in masked and "Reeder" not in masked


def test_an_ocr_mangled_leader_still_anchors_an_entry():
    # A page already rebuilt by the destructive re-OCR carries its leaders as
    # letter-soup, so the dot anchor finds nothing. Delivered folders have
    # these pages.
    soup = ("Annocki v. Peterson Enters., LLC,\n"
            "232 Cal. App. 4th 32 (2014) oo. "
            "eececcssccesecsseeseessesseceseceaecaeecaececesseesaecaecaeesseeeeeseeeaeenaeeneeeas 4\n")
    assert "Peterson" not in P._pn_mask_toa_entries(soup)


def test_ordinary_prose_has_no_leader_to_anchor_on():
    prose = ("The Court finds that Plaintiff has not pleaded reliance... "
             "Defendant Michael Rodgers disagrees.")
    assert P._pn_mask_toa_entries(prose) == prose


# ─────────────────── the table is not re-OCR'd ──────────────────────────────

def _leader_page(entries=40, dots=90):
    head = "TABLE OF AUTHORITIES\nCASE LAW\n"
    rows = "".join(f"Case Number {i} v. Defendant Number {i}\n"
                   f"(20{i:02d}) {i} Cal.App.4th {i * 7} {'.' * dots} {i}\n"
                   for i in range(1, entries + 1))
    return head + rows


def test_a_leader_page_is_not_garbled():
    page = _leader_page()
    ns = sum(1 for c in page if not c.isspace())
    ratio = sum(1 for c in page if c.isalpha() or c.isdigit()) / ns
    assert ratio < 0.35, "the fixture must be over the old cut to mean anything"
    assert P._text_looks_garbled(page) is False


@pytest.mark.parametrize("dots", [40, 90, 160])
def test_leader_density_never_makes_a_table_garbled(dots):
    # The old ratio degraded monotonically with leader width; the fix removes
    # the dependence entirely rather than moving the threshold, which has been
    # retuned twice and each time found a new character class.
    assert P._text_looks_garbled(_leader_page(dots=dots)) is False


def test_broken_encoding_still_fires():
    assert P._text_looks_garbled("(cid:12)(cid:5) " * 60) is True
    assert P._text_looks_garbled("�" * 400 + "text " * 60) is True


def test_symbol_soup_that_is_not_leaders_still_fires():
    assert P._text_looks_garbled("#$%^&*<>{}[]|~ " * 80) is True


def test_real_prose_is_never_garbled():
    prose = ("The demurrer is overruled. Plaintiff has alleged reliance with "
             "the particularity required of a promissory fraud claim. ") * 12
    assert P._text_looks_garbled(prose) is False


# ─────────────────── the hard precondition on the page itself ───────────────
# A ratio answers "does this look like content?", and a table of authorities
# makes it say no. The precondition answers a different question — "did this
# text come out of a real font correctly?" — and the page the heuristic exists
# to catch, one with a BROKEN encoding, fails it by construction.

import fitz


def _page(text, fontname="times-roman"):
    """A one-page PDF carrying `text`, wrapped so nothing clips off the edge
    (a single long insert_text run is truncated at the page margin)."""
    doc = fitz.open()
    pg = doc.new_page()
    words, line, y = text.split(), [], 72
    for w in words:
        line.append(w)
        if len(" ".join(line)) > 60:
            pg.insert_text((72, y), " ".join(line), fontsize=11,
                           fontname=fontname)
            line, y = [], y + 14
    if line:
        pg.insert_text((72, y), " ".join(line), fontsize=11, fontname=fontname)
    return doc, doc[0]


WORDS = ("the court finds that plaintiff has alleged reliance with the "
         "particularity required of a promissory fraud claim and the demurrer "
         "to that cause of action is therefore overruled without leave ") * 3


def test_a_real_text_layer_is_sound():
    _doc, pg = _page(WORDS)
    assert P._page_text_layer_is_sound(pg) is True


def test_a_base_14_font_is_not_rejected_for_not_being_embedded():
    # An earlier shape of this check required an EMBEDDED font, which would
    # send a perfectly sound base-14 page to the shredder for a property that
    # carries no signal. The word test is what proves the mapping works.
    _doc, pg = _page(WORDS, fontname="helvetica")
    assert P._page_text_layer_is_sound(pg) is True


def test_a_cid_soup_page_is_not_vouched_for():
    # The page this heuristic actually exists to catch must still fail the
    # precondition, or sparing on it would spare a page that needed rebuilding.
    _doc, pg = _page("(cid:12)(cid:5)(cid:99) " * 40 + WORDS)
    assert P._page_text_layer_is_sound(pg) is False


def test_a_page_with_too_few_words_is_not_vouched_for():
    _doc, pg = _page("a b c")
    assert P._page_text_layer_is_sound(pg) is False


def test_an_empty_page_is_not_vouched_for():
    doc = fitz.open()
    pg = doc.new_page()
    assert P._page_text_layer_is_sound(pg) is False


# ────────────── a trial-court docket is faked, citation or not ──────────────
# A trial court number identifies a MATTER, so every one of them is faked now,
# including inside a citation span. A published authority is cited by volume,
# reporter and page and carries no docket number at all, so a docket standing
# in a brief is a matter's number rather than a citation's.
#
# The cost is real and was accepted with it in view: an UNREPORTED decision IS
# cited by its docket — "Krikorian Inv. Servs., Inc. v. Radmanesh, No.
# BC543295, 2015 WL 12751760" — and this renames it, so the export carries a
# cite whose decision cannot be looked up. The reversal key still holds the
# binding, so the original is recoverable; what is lost is the cite reading
# correctly in the deliverable. These tests pin that trade rather than the
# older rule (never build a term for a docket in a cite), which left a real
# docket standing wherever a citation could be read around it.
#
# An UNPUBLISHED appellate docket goes the same way, and for a sharper reason:
# a published opinion is cited by volume, reporter and page and carries no
# docket at all, so a docket in a brief is either a trial-court number or an
# unpublished opinion's — and in a trial court filing that is overwhelmingly
# this case's own prior appeal. The appellate record is public, so the number
# gives up the real parties on remand.
#
# What is NOT faked stays pinned below: a PUBLISHED citation has no docket to
# fake, and the cited decision's PARTY NAMES are as protected as they ever
# were.

CITE = ("Krikorian Inv. Servs., Inc. v. Radmanesh, No. BC543295, "
        "2015 WL 12751760 (Cal. Super. Ct. 2015)")


def _ids(text):
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms([], [], [], registry=reg), DET,
                        registry=reg)
    z.register_identifiers(text)
    return {(t.category, t.real) for t in z.terms}


def test_a_docket_inside_a_citation_is_faked():
    """The trade, stated: this renames the cited decision's docket."""
    assert ("case_number", "BC543295") in _ids(CITE)


def test_a_docket_in_a_table_entry_is_faked_too():
    assert ("case_number", "BC543295") in _ids(TOA + f"{CITE} ............ 9\n")


def test_the_cited_decision_keeps_its_PARTY_names():
    """Only the docket moves. Renaming an authority is still the cardinal
    failure, so the span around the number protects everything else."""
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms([("Radmanesh", False)], [], [],
                                          registry=reg), DET, registry=reg)
    z.register_identifiers(CITE)
    out = z.apply(CITE)
    assert "Krikorian Inv. Servs., Inc. v. Radmanesh" in out
    assert "2015 WL 12751760" in out
    assert "BC543295" not in out and P._PN_CASENO_MARK in out


def test_an_unpublished_appellate_docket_is_faked():
    """A PUBLISHED opinion is cited by reporter and carries no docket at all,
    so a docket standing in a brief is either a trial-court number or an
    UNPUBLISHED opinion's — and in a trial court filing the latter is
    overwhelmingly this case's own prior appeal, which is a re-identification
    key: the appellate record is public, so the number gives up the parties."""
    assert P._pn_docket_numbers("our prior opinion, No. B258976, reversed.") \
        == ["B258976"]
    assert P._pn_docket_numbers("review denied, No. S271234.") == ["S271234"]


def test_a_published_citation_carries_no_docket_to_fake():
    """The fact the whole rule rests on. Nothing in a published cite has the
    shape, so strict protection of published authority costs nothing here."""
    cite = "Kremerman v. White (2021) 71 Cal.App.5th 358."
    assert P._pn_docket_numbers(cite) == []
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms([], [], [], registry=reg), DET,
                        registry=reg)
    z.register_identifiers(cite)
    assert z.apply(cite) == cite


def test_only_a_real_district_letter_counts():
    """A-H are the six Courts of Appeal and S the Supreme Court; no other
    letter is a district, which is what keeps this off an arbitrary
    single-letter identifier."""
    assert P._pn_docket_numbers("X123456, Z999999, J1234567") == []


def test_a_bates_stamp_is_not_read_as_a_docket():
    """The older Los Angeles shape is held to KNOWN courthouse prefixes, or a
    production stamp would be faked in a docket's shape instead of its own."""
    assert P._pn_docket_numbers("Bates AB000123 and XY654321.") == []
    assert P._pn_docket_numbers("consolidated with BC543295.") == ["BC543295"]


def test_a_two_letter_docket_is_not_read_as_an_appellate_one():
    """"BC543295" is a trial-court number, not "B" plus six digits — the
    Los Angeles shape has to claim it first."""
    assert P._pn_docket_numbers("BC543295") == ["BC543295"]


def test_a_form_id_is_never_taken_for_a_docket():
    assert P._pn_docket_numbers("Form CIV-100; see PLD-PI-001(2).") == []


def test_every_covered_shape_is_harvested():
    assert P._pn_docket_numbers("24STCV00123") == ["24STCV00123"]
    assert P._pn_docket_numbers("23STLC00412") == ["23STLC00412"]
    assert P._pn_docket_numbers("No. 2:15-cv-01234,") == ["2:15-cv-01234"]


@pytest.mark.parametrize("text,cat", [
    ("Counsel of record, State Bar No. 230831, appeared.", "bar_number"),
    ("Reservation ID: 264859302214 confirms the hearing.", "reservation_id"),
    ("Production stamp RAM000013-RAM000018 was produced.", "production_number"),
    ("a registered California process server, Registration No. 833",
     "registration_number"),
])
def test_this_cases_own_identifiers_still_register(text, cat):
    assert cat in {c for c, _r in _ids(text)}, _ids(text)


def test_an_identifier_beside_a_citation_is_still_ours():
    # The sentence around a citation is ordinary document text, and the docket
    # inside it is now ours as well.
    text = f"See {CITE}. Counsel's State Bar No. 230831 appears below."
    got = _ids(text)
    assert ("bar_number", "230831") in got
    assert ("case_number", "BC543295") in got


def test_one_value_takes_one_category_and_one_fake():
    """A docket is claimed by the docket pass, so the label-anchored pass can
    never register the same value a second time as a production number."""
    got = _ids("Case No. BC543295 was consolidated.")
    assert ("case_number", "BC543295") in got
    assert not [c for c, r in got if r == "BC543295" and c != "case_number"]


# ────────── this case's own number, swallowed by an over-reaching span ──────
# The citation parser walks backwards over a case name, so "Case No.
# 25STCV37838." on the line above a cite lands INSIDE the protected span. The
# number was then neither faked (`_substitute` refuses a protected span) nor
# reported (`surviving_reals` masks the same spans) — the real docket shipped,
# silently, which is the worse of the two failures the protection trades
# between. `_punch_own_casenos` cuts the number out of the span at the single
# choke point every consumer reads, so the write side and the leak scans
# cannot answer differently.

SWALLOWED = ("Case No. 25STCV37838.\n"
             "Stockton Theatres, Inc. v. Palermo (1956) 47 Cal.2d 469.")


def _pz_caseno():
    reg = P._PnFakeRegistry()
    return P.Pseudonymizer(
        P._pn_build_terms([], ["25STCV37838"], [], registry=reg), {},
        registry=reg)


def test_the_parser_really_does_swallow_the_number():
    """Guard for the test below: if the parse ever stops over-reaching, this
    fails and the case it pins has to be rebuilt on a span that still does."""
    reg = P._PnFakeRegistry()
    bare = P.Pseudonymizer(P._pn_build_terms([], [], [], registry=reg), {},
                           registry=reg)
    i = SWALLOWED.index("25STCV37838")
    assert any(s <= i and i < e for s, e in bare._protected_citation_spans(
        SWALLOWED))


def test_a_swallowed_case_number_is_faked():
    out = _pz_caseno().apply(SWALLOWED)
    assert "25STCV37838" not in out
    assert P._PN_CASENO_MARK in out


def test_the_authority_in_the_same_span_is_untouched():
    """The cut is the number and nothing else."""
    out = _pz_caseno().apply(SWALLOWED)
    assert "Stockton Theatres, Inc. v. Palermo (1956) 47 Cal.2d 469" in out


def test_detection_and_replacement_still_agree():
    """The punch happens where every consumer reads it, so a number left
    standing is visible to the leak scan instead of being masked away."""
    pz = _pz_caseno()
    i = SWALLOWED.index("25STCV37838")
    assert not any(s <= i and i < e
                   for s, e in pz._protected_citation_spans(SWALLOWED))
    assert pz.surviving_reals(pz.apply(SWALLOWED)) == []
    assert pz.surviving_reals(SWALLOWED) == ["25STCV37838"]
