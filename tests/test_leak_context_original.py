"""The LEAKS worksheet's Context column quotes the ORIGINAL text — the same
body the key's Context column reads — at the operator's direction.

It used to quote the scrubbed export, on the reasoning that the export is
where the leak stands. But the row's question is "what IS this value?", it is
decided once per value however many files carry it, and a `never` typed
against it applies in every future folder — so the evidence should be the
document's own sentence, with no pseudonyms substituted around the value.

`_pn_leak_context` is the one rule all three producers share (the PDF path,
the Word path, `--fix-leaks`): quote the value from the original; a phrase
carrying one of our own stand-ins is absent from the source by construction,
so its REAL REMAINDER — the value `confirm_findings` will reduce the row to —
is quoted instead; and with no original in hand at all the scrubbed export is
quoted rather than leaving the row unanswerable.

Run:  cd PDF-Linker && python3 -m pytest tests/test_leak_context_original.py -v
"""
import logging

import pytest

fitz = pytest.importorskip("fitz")

import pdf_linker as P

log = logging.getLogger("test")


def _pz(names=("Roxane Estrada",), casenos=()):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), list(casenos), [], registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    return P.Pseudonymizer(terms, det, registry=reg)


ORIGINAL = ("Ashely attended the deposition of Roxane Estrada in Van Nuys. "
            "The parties met and conferred afterwards.")


class TestLeakContextRule:
    def test_quotes_the_original_not_the_export(self):
        pz = _pz()
        scrubbed = pz.apply(ORIGINAL)
        assert "Roxane Estrada" not in scrubbed        # the scrub worked
        quote = P._pn_leak_context(P._pn_body_lines(ORIGINAL),
                                   P._pn_body_lines(scrubbed), pz, "Ashely")
        assert "Roxane Estrada" in quote               # the document's own words

    def test_a_phrase_carrying_our_fake_quotes_its_real_remainder(self):
        pz = _pz()
        scrubbed = pz.apply(ORIGINAL)
        pz.note_original(ORIGINAL)
        fake_surname = pz.apply("Roxane Estrada").split()[-1]
        assert fake_surname.lower() not in ORIGINAL.lower()
        value = f"Ashely {fake_surname}"               # the half-scrubbed shape
        assert pz._real_remainder(value) == "Ashely"   # the reduction the row gets
        quote = P._pn_leak_context(P._pn_body_lines(ORIGINAL),
                                   P._pn_body_lines(scrubbed), pz, value)
        assert "Roxane Estrada" in quote               # remainder found in source

    def test_with_no_original_the_export_is_quoted_not_nothing(self):
        pz = _pz()
        scrubbed = pz.apply(ORIGINAL)
        quote = P._pn_leak_context([], P._pn_body_lines(scrubbed), pz, "Ashely")
        assert "Ashely" in quote
        assert "Roxane Estrada" not in quote           # only the export exists


class TestWordPathContext:
    def test_leak_row_context_is_the_original_sentence(self, tmp_path,
                                                       monkeypatch):
        pz = _pz()
        # Force a deterministic LEAK finding: organic leaks need an extraction
        # pathology, and this test is about the row's plumbing, not the scans.
        monkeypatch.setattr(pz, "surviving_reals", lambda body: {"Ashely"})
        src = tmp_path / "Letter.docx"
        src.write_bytes(b"")
        assert P._write_word_text_version(src, ORIGINAL, log, pz)
        row = next(r for r in pz.leak_report if r["value"] == "Ashely")
        assert "Roxane Estrada" in row["context"]
        fake_surname = pz.apply("Roxane Estrada").split()[-1]
        assert fake_surname not in row["context"]


class TestPdfPathContext:
    def test_leak_row_context_is_the_original_sentence(self, tmp_path,
                                                       monkeypatch):
        doc = fitz.open()
        pg = doc.new_page()
        pg.insert_text((72, 100), ORIGINAL[:60], fontsize=11)
        pg.insert_text((72, 114), ORIGINAL[60:], fontsize=11)
        path = tmp_path / "letter.pdf"
        doc.save(path)
        doc.close()
        pz = _pz()
        monkeypatch.setattr(pz, "surviving_reals", lambda body: {"Ashely"})
        monkeypatch.setattr(pz, "surviving_reals_reduced",
                            lambda body, spliced=False: set())
        doc = fitz.open(path)
        assert P._write_text_version(path, doc, log, pseudonymizer=pz)
        row = next(r for r in pz.leak_report if r["value"] == "Ashely")
        assert "Roxane Estrada" in row["context"]

    def test_the_key_context_still_reads_the_original_too(self, tmp_path):
        # The rule the leaks column now shares was the key's already — pin
        # that the change did not disturb it.
        doc = fitz.open()
        pg = doc.new_page()
        pg.insert_text((72, 100), ORIGINAL[:60], fontsize=11)
        pg.insert_text((72, 114), ORIGINAL[60:], fontsize=11)
        path = tmp_path / "letter.pdf"
        doc.save(path)
        doc.close()
        pz = _pz()
        doc = fitz.open(path)
        assert P._write_text_version(path, doc, log, pseudonymizer=pz)
        assert "Roxane Estrada" in pz._key_context.get("roxane estrada", "")


class TestCachedOriginalsCollect:
    def test_collect_receives_the_texts(self, tmp_path):
        d = P._originals_cache_dir(tmp_path)
        d.mkdir(parents=True, exist_ok=True)
        (d / "a.txt").write_text(ORIGINAL, encoding="utf-8")
        pz = _pz()
        got = []
        try:
            n = P._load_cached_originals(tmp_path, pz, log, collect=got)
        finally:
            P._clear_originals_cache(tmp_path)
        assert n == 1 and got == [ORIGINAL]
