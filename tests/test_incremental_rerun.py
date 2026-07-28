"""
Adding a document to an already-pseudonymized folder.

The working pattern: the scrubbed .txt exports go out for a draft, the draft
comes back saying a filing is missing, the operator drops that PDF in and
re-runs. For that re-run to be usable, the documents already sent must come
back BYTE-IDENTICAL — otherwise every earlier draft is invalidated and the
work starts over.

So long as `pseudonym_key.xlsx` is beside the exports:

  * every value the key binds keeps its exact fake, whatever the new document
    adds (the key is loaded first and seeds the registry, so a later draw can
    neither move nor collide with an established fake);
  * a party the key never bound — one named ONLY in the missing document, so
    it matched nothing on the first run and `write_key` rightly omitted it —
    is still scrubbed, re-read from the E-Court party template; and
  * an operator KEEP still wins over that supplement: a value marked `no`
    does not come back to life just because it is also a template row.

Run:  cd PDF-Linker && python3 -m pytest tests/test_incremental_rerun.py -v
"""
import logging
import re

import openpyxl
import pytest

import pdf_linker as P

log = logging.getLogger("test")
DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}

PARTIES = ["Ernest N Ramirez", "Ford Motor Company", "Jane Roe",
           "Marcus Bellweather"]
CASENO = "24STCV23198"

# Docs 1-3, the batch that was sent out. Jane Roe is a listed party but is
# named only in the declaration that got left out.
SENT = ("Plaintiff Ernest N Ramirez sued Ford Motor Company in 24STCV23198. "
        "Marcus Bellweather declares. Offices at 414 S. Maple Ave., "
        "Montebello, CA 90640. Write rlally@mortensontaggart.com.")
# The document the draft flagged as missing.
ADDED = ("Declaration of Jane Roe. Jane Roe worked with Ernest N Ramirez at "
         "Ford Motor Company, 414-416 S Maple Avenue, in 24STCV23198.")


@pytest.fixture
def folder(tmp_path):
    """A case folder holding the E-Court party template."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Case Number", "Title Plaintiff", "Title Defendant",
               "Other Names"])
    ws.append([CASENO, PARTIES[0], PARTIES[1], "; ".join(PARTIES[2:])])
    wb.save(tmp_path / "Order_Template_Input.xlsx")
    return tmp_path


def _first_run(folder):
    """The original batch: mint fresh fakes from the template, write the key."""
    names, casenos = P._pn_terms_from_xlsx(
        folder / "Order_Template_Input.xlsx", None, log)
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(names, casenos, [], registry=reg),
                        DET, registry=reg)
    out = z.apply(SENT)
    z.write_key(folder / "pseudonym_key.xlsx", log)
    return z, out


def _rerun(folder, decisions=None):
    """The re-run with the missing document added: load the key, supplement
    from the template, honour any operator KEEP."""
    reg = P._PnFakeRegistry()
    terms, key_decisions = P._pn_load_key(folder / "pseudonym_key.xlsx", reg, log)
    terms += P._pn_supplement_key_terms(terms, folder, None, reg, log)
    terms, retired = P._pn_retire_kept_key_terms(
        terms, {**(decisions or {}), **key_decisions}, reg, log)
    return P.Pseudonymizer(terms, DET, registry=reg)


# ── the documents already sent must not move ────────────────────────────────

def test_already_sent_documents_are_byte_identical(folder):
    _z1, sent_out = _first_run(folder)
    assert _rerun(folder).apply(SENT) == sent_out


def test_every_keyed_fake_is_reused_exactly(folder):
    z1, _ = _first_run(folder)
    rows = {str(r[1]): str(r[2]) for r in
            openpyxl.load_workbook(folder / "pseudonym_key.xlsx").active
            .iter_rows(min_row=2, values_only=True) if r[1]}
    z2 = _rerun(folder)
    z2.apply(ADDED)                       # the new document draws its own fakes
    for real, fake in rows.items():
        assert z2.apply(real) == fake, f"{real!r} moved: {z2.apply(real)!r}"


def _street(text):
    """The faked "<number> <name>" of the first address in `text`."""
    return re.search(r"\d+ [A-Z][a-z]+", text).group(0)


def test_case_number_and_address_stay_consistent(folder):
    _z1, sent_out = _first_run(folder)
    faked_caseno = sent_out.split(" in ")[1].split(".")[0]
    z2 = _rerun(folder)
    added_out = z2.apply(ADDED)
    assert faked_caseno in added_out
    # the same parcel written a second way folds onto the same faked street
    assert _street(added_out) == _street(sent_out.split("Offices at ")[1])


# ── the party the key never bound is still scrubbed ─────────────────────────

def test_party_named_only_in_the_added_document_is_scrubbed(folder):
    z1, _ = _first_run(folder)
    # precondition: she matched nothing, so the key rightly has no row for her
    keyed = {str(r[1]) for r in
             openpyxl.load_workbook(folder / "pseudonym_key.xlsx").active
             .iter_rows(min_row=2, values_only=True)}
    assert "Jane Roe" not in keyed
    out = _rerun(folder).apply(ADDED)
    assert "Jane Roe" not in out


def test_supplemented_party_does_not_disturb_the_others(folder):
    _z1, sent_out = _first_run(folder)
    z2 = _rerun(folder)
    z2.apply(ADDED)                       # supplement draws first, if it can
    assert z2.apply(SENT) == sent_out


def test_supplement_is_skipped_when_no_template_remains(folder):
    # The template may not have been kept beside the exports; the re-run must
    # still work off the key alone rather than failing.
    _z1, sent_out = _first_run(folder)
    (folder / "Order_Template_Input.xlsx").unlink()
    assert _rerun(folder).apply(SENT) == sent_out


# ── an operator KEEP still beats the supplement ─────────────────────────────

def test_keep_is_not_resurrected_by_the_party_template(folder):
    # The operator decided this listed value stays verbatim. Re-reading the
    # template must not quietly start faking it again.
    _first_run(folder)
    keep = {"marcus bellweather": {
        "value": "Marcus Bellweather", "type": "KEEP", "fix": "no",
        "replacement": None, "fake_values": None, "fixcell": None,
        "notes": "test"}}
    out = _rerun(folder, keep).apply("Marcus Bellweather declares.")
    assert "Marcus Bellweather" in out


def test_keep_is_not_reassembled_from_supplemented_tokens(folder):
    _first_run(folder)
    keep = {"marcus bellweather": {
        "value": "Marcus Bellweather", "type": "KEEP", "fix": "no",
        "replacement": None, "fake_values": None, "fixcell": None,
        "notes": "test"}}
    z = _rerun(folder, keep)
    assert z.apply("Marcus said so.") == "Marcus said so."
    assert z.apply("Bellweather said so.") == "Bellweather said so."
