"""A DocuSign ENVELOPE ID is an identifier and nothing else.

It means nothing on its own and everything as the handle to one signing
transaction, and DocuSign stamps it up the left margin of EVERY PAGE of an
e-signed filing — so one left standing is left standing everywhere.

Two cues, and the second is what makes the first optional. The LABEL
("DocuSign Envelope ID:"), read tolerantly, since the stamp is small sideways
type and a scan puts marks and spaces through it and reads the I of ID as an
l, a 1 or a bar — behind it the value is read loosely, because a scan that
garbled the label garbled the GUID too. And the SHAPE, 8-4-4-4-12, which
nothing else a filing prints has: measured over this repo's notes, its module
and its tests, ZERO matches, so the bare shape needs no label at all.

The class is listed FIRST, and `_pn_identifier_values` now claims a match's
SPAN: a GUID whose first or last group happens to be capitals then digits was
matched by the production-stamp shape and faked as a Bates stamp — four
characters of thirty-six, the half-scrub this tool refuses, with the rest of
the envelope id shipping in the clear beside its own fake.

Run:  cd PDF-Linker && python3 -m pytest tests/test_envelope_id.py -v
"""
import pathlib
import re

import pytest

import pdf_linker as P

GUID = "4AF01234-BEEF-4DAD-8001-ABCDEF012345"


def _ids(text):
    return P._pn_identifier_values(text)


def _env(text):
    return [v for c, v in _ids(text) if c == "envelope id"]


# ── the two cues ─────────────────────────────────────────────────────────────

class TestTheLabel:
    @pytest.mark.parametrize("line", [
        f"DocuSign Envelope ID: {GUID}",
        f"DocuSign Envelope ID:{GUID}",
        f"Docu Sign  Envelope  ID : {GUID}",          # spaced by the scan
        f"DocuSign Envelope lD; {GUID}",              # the I read as an l
        f"DocuSign Envelope 1D - {GUID}",             # …and as a 1
        f"docusign envelope id {GUID}",
    ])
    def test_a_mangled_label_still_names_the_value(self, line):
        assert _env(line) == [GUID]

    def test_behind_the_label_the_marks_need_not_be_hyphens(self):
        """A scan gives the hyphens up as whatever marks it read. The label
        says what follows is an envelope id, so the value is read loosely
        there — which is the whole reason the label is a cue of its own."""
        assert _env("DocuSign Envelope lD; 1F3A2B4C.5D6E,7F80~91A2-B3C4D5E6F7A8") \
            == ["1F3A2B4C.5D6E,7F80~91A2-B3C4D5E6F7A8"]

    def test_the_value_stops_at_the_identifier(self):
        """A MARK is required at every seam, so the loose read cannot walk out
        of the identifier into the words printed beside it."""
        assert _env(f"DocuSign Envelope ID: {GUID} Page 1 of 4") == [GUID]

    def test_a_run_nothing_like_a_guid_is_refused(self):
        """The label standing in front of something else does not make that
        thing an envelope id — faking it would rewrite the something else."""
        assert _env("DocuSign Envelope ID: see p.3-4, ex. A-1 and B-2") == []


class TestTheShape:
    def test_a_bare_guid_needs_no_label(self):
        assert _env(f"(Envelope {GUID} attached)") == [GUID]

    def test_lower_case_and_inside_a_url_too(self):
        low = GUID.lower()
        assert _env(f"https://example.com/sign/{low}") == [low]

    def test_a_scan_s_letters_for_hex_digits_do_not_cost_the_match(self):
        """Read as ALPHANUMERIC and not as hex: the O for 0 and l for 1 a scan
        invents are what the shape is there to survive."""
        assert _env("Ol23456O-lOFE-4DAD-800l-ABCDEFOl2345") \
            == ["Ol23456O-lOFE-4DAD-800l-ABCDEFOl2345"]

    @pytest.mark.parametrize("line", [
        "RAM000013-RAM000018",                       # a Bates range
        "FMC_RAMIREZ_ERNEST_000007",                 # a Bates stamp
        "Case No. 25STCV37838, and 2:15-cv-01234",   # dockets
        "phone 818-953-0150 and SSN 123-45-6789",
        "APN 5555-012-034 / Medicare No. 1EG4-TE5-MK72",
        "Policy No. HO-1234567-89, Claim No. 22-0004567-01",
    ])
    def test_the_shapes_beside_it_are_not_envelope_ids(self, line):
        assert _env(line) == []

    def test_zero_matches_over_the_repo_s_own_text(self):
        """The measurement the bare-shape cue rests on: 8-4-4-4-12 is a
        fingerprint, so it is read with no label and no corroboration."""
        root = pathlib.Path(__file__).resolve().parent.parent
        texts = [(root / "CLAUDE.md").read_text(errors="ignore"),
                 (root / "pdf_linker.py").read_text(errors="ignore")]
        texts += [p.read_text(errors="ignore")
                  for p in (root / "tests").glob("*.py")
                  if p.name != pathlib.Path(__file__).name]
        assert sum(len(text) for text in texts) > 1_000_000
        rx = P._PN_ID_RES["envelope id"]
        hits = [m.group(0) for text in texts for m in rx.finditer(text)]
        assert hits == []


# ── one value, one category, one fake ────────────────────────────────────────

class TestOneValueOneCategory:
    @pytest.mark.parametrize("guid", [
        "ABCD1234-5D6E-7F80-91A2-B3C4D5E6F7A8",      # caps-then-digits lead
        "4AF01234-BEEF-4DAD-8001-ABCDEF012345",      # …and tail
    ])
    def test_no_piece_of_a_guid_is_read_as_a_bates_stamp(self, guid):
        got = _ids(f"DocuSign Envelope ID: {guid}")
        assert got == [("envelope id", guid)]

    def test_a_repeat_occurrence_claims_its_span_too(self):
        """The value is deduped out of the list and its second occurrence is
        still claimed, or a narrower class reads a piece of it there."""
        got = _ids(f"Envelope {GUID} signed.\nRe-sent under {GUID} today.")
        assert got == [("envelope id", GUID)]

    def test_an_identifier_somewhere_else_is_untouched(self):
        """The claim is on the SPAN, so a value standing at its own place in
        the text is read exactly as it was before."""
        got = _ids(f"DocuSign Envelope ID: {GUID}\nBates RAM000013")
        assert got == [("envelope id", GUID),
                       ("production number", "RAM000013")]

    def test_every_id_class_yields_its_value(self):
        """`_pn_identifier_values` reads the first group that MATCHED, because
        this class is read two ways. Every other class has one group, so for
        them that is the read it always was."""
        for cls, rx in P._PN_ID_RES.items():
            assert rx.groups >= 1, cls
            if cls != "envelope id":
                assert rx.groups == 1, cls


# ── end to end ───────────────────────────────────────────────────────────────

def _pz(names=("Rachel Ashworth",)):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), [], [], registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    return P.Pseudonymizer(terms, det, registry=reg)


BODY = (f"DocuSign Envelope ID: {GUID}\n"
        f"Signed by Rachel Ashworth under envelope {GUID}.\n")


class TestTheScrub:
    def test_the_stamp_is_faked_on_every_page_it_stands_on(self):
        pz = _pz()
        pz.register_identifiers(BODY)
        out = pz.apply(BODY)
        assert GUID not in out
        assert out.count("DocuSign Envelope ID:") == 1     # the label is kept
        assert pz.surviving_reals(out) == []

    def test_the_fake_keeps_the_printed_shape(self):
        pz = _pz()
        pz.register_identifiers(BODY)
        fake = pz.records[("envelope_id", GUID.lower())]["fake"]
        assert re.fullmatch(r"[A-Z0-9]{8}(?:-[A-Z0-9]{4}){3}-[A-Z0-9]{12}", fake)
        assert fake != GUID

    def test_the_fake_could_not_itself_be_an_envelope_id(self):
        """Drawn from the WHOLE alphabet and not from hex, so it cannot be
        somebody's real envelope — the case-number marker's reasoning."""
        seen = set()
        for n in range(40):
            pz = _pz()
            g = f"4AF0123{n % 10}-BEEF-4DAD-8001-ABCDEF01234{n % 10}"
            pz.register_identifiers(f"DocuSign Envelope ID: {g}")
            seen.add(pz.records[("envelope_id", g.lower())]["fake"])
        assert any(re.search(r"[G-Zg-z]", f) for f in seen)

    def test_our_own_stand_in_is_not_reported_back(self):
        """A row for the tool's own output is a question with no right
        answer — and the fake's own last group is Bates-stamp-shaped."""
        pz = _pz()
        pz.register_identifiers(BODY)
        out = pz.apply(BODY)
        assert pz.reid_scan(out) == []

    def test_a_surviving_envelope_id_is_a_REID_row(self):
        pz = _pz()
        rows = pz.reid_scan(f"DocuSign Envelope ID: {GUID}")
        assert ("REID envelope id", GUID) in rows

    def test_the_binding_reaches_the_key(self, tmp_path):
        pz = _pz()
        pz.register_identifiers(BODY)
        pz.apply(BODY)
        import logging
        key = tmp_path / "pseudonym_key.xlsx"
        pz.write_key(key, logging.getLogger("test"))
        from conftest import key_body_rows
        reals = [str(r[1]) for r in key_body_rows(key)]
        assert GUID in reals
