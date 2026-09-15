"""
A law firm's document-ID footer — "308742 00148/8-13-23/blp/bp".

Printed at the foot of every page of a contract so a loose page can be traced
back to the file: the CLIENT number, the MATTER number under it, the date that
draft was generated, the drafting attorney's initials, the typist's.

It reached no pass at all before this. Every identifier class is label-anchored
and a footer carries no label; the docket harvest knows only court shapes; the
bare-number screens drop a five-digit matter number on sight; and the initials
are lower case, so every name tier walks past them. The stamp shipped verbatim
AND silently — no fake, no LEAK row, nothing in the worksheet.

Pinned here: the two numbers are faked and the DATE is kept; the client half is
one fake across every matter of that client while the matter half moves; one
person's initials take one fake wherever they are printed; every page of one
stamp reads identically; the whole stamp is one reversible record; a re-scrub
of the output is a fixed point; and the shapes that must never match — a
citation, a docket, a Bates range, an ordinary date — still do not.

Run:  cd PDF-Linker && python3 -m pytest tests/test_firm_file_stamp.py -v
"""
import pathlib
import re

import pytest

import pdf_linker as P

DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
STAMP = "308742 00148/8-13-23/blp/bp"


def _pz():
    return P.Pseudonymizer([], DET, registry=P._PnFakeRegistry())


def _apply(text, pz=None):
    return (pz or _pz()).apply(text)


def _stamp(text):
    """The one file-stamp match in `text`."""
    m = P._PN_FILE_STAMP_RE.search(text)
    assert m, f"no file stamp in {text!r}"
    return m


# ── the stamp is faked at all ───────────────────────────────────────────────

def test_a_firm_file_stamp_is_faked():
    out = _apply(f"Page 1 of 14\n{STAMP}\n")
    assert STAMP not in out
    assert _stamp(out)          # and what replaces it still reads as a stamp


def test_the_client_and_matter_numbers_both_move():
    m = _stamp(_apply(STAMP))
    assert m.group("client") != "308742"
    assert m.group("matter") != "00148"


def test_the_initials_both_move():
    m = _stamp(_apply(STAMP))
    assert m.group("inits") != "blp/bp"
    assert [g for g in re.findall(r"[A-Za-z]+", m.group("inits"))] != ["blp", "bp"]


def test_the_initials_keep_their_case_and_length():
    m = _stamp(_apply("308742 00148/8-13-23/BLP/Bp"))
    a, b = re.findall(r"[A-Za-z]+", m.group("inits"))
    assert a.isupper() and len(a) == 3
    assert b[0].isupper() and b[1:].islower() and len(b) == 2


# ── …and the DATE is kept ───────────────────────────────────────────────────
# A date identifies nobody, and in a contract dispute the draft date is
# routinely the thing being litigated — which version was circulated, which
# was signed. "The 8-13-23 draft" is how the document is cited in the papers.

@pytest.mark.parametrize("date", ["8-13-23", "08/13/2023", "8.13.23", "1/2/24"])
def test_the_drafting_date_is_kept_verbatim(date):
    out = _apply(f"308742 00148/{date}/blp/bp")
    assert _stamp(out).group("date") == date


def test_the_separators_are_kept_so_it_still_reads_as_a_stamp():
    out = _apply("308742.00148/8-13-23/blp/bp")
    assert re.fullmatch(r"\d{6}\.\d{5}/8-13-23/[a-z]{3}/[a-z]{2}", out)


# ── one value, one fake ─────────────────────────────────────────────────────

def test_every_page_of_one_stamp_reads_identically():
    out = _apply(f"{STAMP}\npage two\n{STAMP}\npage three\n{STAMP}\n")
    fakes = {m.group(0) for m in P._PN_FILE_STAMP_RE.finditer(out)}
    assert len(fakes) == 1


def test_two_matters_of_one_client_share_the_client_number():
    out = _apply("308742 00148/8-13-23/blp/bp\n308742 00203/9-01-23/blp/kj\n")
    a, b = list(P._PN_FILE_STAMP_RE.finditer(out))
    assert a.group("client") == b.group("client")
    assert a.group("matter") != b.group("matter")


def test_one_persons_initials_take_one_fake_wherever_printed():
    # "blp" drafted both; the typist differs. Faking the RUN as one string
    # would give "blp" one fake beside "bp" and another beside "kj" — one
    # word with two fakes, which is one person read as two.
    out = _apply("308742 00148/8-13-23/blp/bp\n308742 00203/9-01-23/blp/kj\n")
    a, b = list(P._PN_FILE_STAMP_RE.finditer(out))
    assert a.group("inits").split("/")[0] == b.group("inits").split("/")[0]
    assert a.group("inits").split("/")[1] != b.group("inits").split("/")[1]


def test_the_zero_padding_of_a_matter_number_is_kept():
    # A matter number is padded to a fixed width; randomising the padding
    # makes the fake stop reading as a matter number.
    m = _stamp(_apply("308742 00148/8-13-23/blp/bp"))
    assert m.group("matter").startswith("00")
    assert len(m.group("matter")) == 5


# ── reversibility ───────────────────────────────────────────────────────────

def test_the_whole_stamp_is_one_reversible_record():
    pz = _pz()
    out = _apply(f"{STAMP}\n{STAMP}\n", pz)
    recs = [r for r in pz.records.values() if r["category"] == "file stamp"]
    assert len(recs) == 1
    assert recs[0]["real"] == STAMP
    assert recs[0]["fake"] == _stamp(out).group(0)
    assert recs[0]["count"] == 2          # so `write_key` writes its row


def test_re_scrubbing_the_output_is_a_fixed_point():
    pz = _pz()
    once = _apply(STAMP, pz)
    assert pz.apply(once) == once


def test_the_fake_is_never_the_real_value():
    for client, matter in (("0000", "000"), ("1111", "111"), ("308742", "00148")):
        real = f"{client} {matter}/8-13-23/ab/cd"
        assert _apply(real) != real


# ── the shapes that must NOT match ──────────────────────────────────────────
# Nothing here is labelled, so the SHAPE is the whole corroboration. A false
# positive rewrites the document's own text, which costs more than a value
# left standing.

@pytest.mark.parametrize("text", [
    "Kremerman v. White (2021) 71 Cal.App.5th 358",
    "(2008) 160 Cal.App.4th 53, 61",
    "Case No. 2:15-cv-01234",
    "25STCV37838",
    "EQ 000123/000456",
    "Invoice 1234 5678 dated 8/13/23",
    "Rule 3.1350(d)",
    "Exhibit 12 at 345/8-13-23",              # no initials
    "308742 00148/blp/bp",                    # no date
    "308742/8-13-23/blp",                     # no matter number
    "1234567 890/8-13-23/blphq",              # 5-letter initials run
    "308742 00148/8-13-23/blp/bp/xx/yy",      # more groups than a footer has
    "42 U.S.C. section 12345",
    "see pages 1234-5678/9",
])
def test_these_are_not_file_stamps(text):
    assert not P._PN_FILE_STAMP_RE.search(text), text
    assert _apply(text) == text


def test_zero_rows_on_this_repos_own_prose():
    """The measurement every anchor in this tool is held to: run the shape over
    the corpus most likely to defeat it — this project's own notes, sources and
    tests, which are full of citations, dockets, section numbers and dates."""
    root = pathlib.Path(__file__).resolve().parent.parent
    hits = []
    for pat in ("*.py", "*.md", "*.bas", "*.txt"):
        for p in root.rglob(pat):
            if ".git" in p.parts or p.name == pathlib.Path(__file__).name:
                continue
            for m in P._PN_FILE_STAMP_RE.finditer(p.read_text(errors="replace")):
                # …other than the worked example the notes and the source
                # comment are written around, which is a real stamp and is
                # supposed to match.
                if m.group(0) == STAMP:
                    continue
                hits.append((str(p.relative_to(root)), m.group(0)))
    assert hits == []


# ── one value, one category, one fake ───────────────────────────────────────

@pytest.mark.parametrize("lead", ["", "File No. ", "Our File No. ",
                                  "Client/Matter: "])
def test_a_labelled_stamp_is_still_one_record(lead):
    """A label in front of the stamp puts a label-anchored identifier class in
    reach of its first number. The stamp is the longer candidate at the same
    priority and wins the overlap, so the value stays ONE record with one fake
    — never the half-scrub of a faked client number beside a real matter one."""
    pz = _pz()
    text = f"{lead}{STAMP}"
    pz.register_identifiers(text)
    out = pz.apply(text)
    assert out == f"{lead}{_stamp(out).group(0)}"
    assert STAMP not in out
    assert pz.surviving_reals(out) == []
    assert len([r for r in pz.records.values()
                if r["real"].endswith("blp/bp")]) == 1


# ── the module-level fallback agrees with the registry-backed faker ─────────

def test_the_fallback_faker_keeps_the_same_parts():
    """`_PN_DETECTORS` carries a registry-free faker for callers with no
    Pseudonymizer. It must move exactly the parts the real one moves, or the
    two answer one question two ways."""
    out = P._pn_fake_file_stamp(STAMP)
    m = _stamp(out)
    assert m.group("date") == "8-13-23"
    assert m.group("client") != "308742"
    assert m.group("matter") != "00148"
    assert m.group("inits") != "blp/bp"
    assert out != STAMP
