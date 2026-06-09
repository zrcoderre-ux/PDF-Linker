"""
pdf_linker.py - Add citation hyperlinks to PDFs in a case folder, and inject
                invisible right-margin citation markers into pleading-paper
                pages so the Word paste macro can auto-generate citations.

Usage:
    pythonw pdf_linker.py "C:\\path\\to\\case\\folder"
    pythonw pdf_linker.py "C:\\path\\to\\case\\folder" --provider westlaw

For each *.pdf in the folder (processed from shortest to longest by file size):
  1. If the PDF has no text layer, runs Tesseract OCR via OCRmyPDF-style flow
     using pytesseract page-by-page to add a text layer.
  2. For files whose name contains "Declaration", "Decl.", "Separate Statement",
     "Compl.", "Complaint", "FAC", "SAC", "TAC", or "Proof of Service", link
     insertion is skipped — these documents rarely have citation-worthy material
     in the working judge's chambers. The right-margin marker injection (step 8)
     still runs on these files so the paste macro works there too.
  3. Extracts case, statute, and rule citations using the same patterns the
     workup search tool uses (extended to recognise CSM, Bluebook, the
     "flat" no-comma practitioner form, and Westlaw-only WL cites).
  4. Tracks first-seen full case citations and resolves later "supra" cites
     within the same PDF; also runs a second pass that links bare short-form
     "X v. Y" references (no reporter or year) to the URL of the matching
     full citation.
  5. Resolves each citation to a search URL on the active provider
     (--provider lexis or westlaw). Westlaw-only WL cites (e.g.
     "2023 WL 3035369") always resolve to a Westlaw URL even when the
     active provider is Lexis — Lexis doesn't carry those reporters.
  6. Adds a blue-and-underlined link annotation over each citation. Multi-
     line citations are matched safely: if the full text doesn't appear on
     a single line, line-fragments are used only when they are distinctive
     enough (no bare "Cal." or "Cal. App. 4th" links across the document).
  7. Replaces the original PDF with the linked version (original is deleted).
  8. Injects invisible white-on-white text markers in the right margin of
     each pleading-paper page. Each marker encodes the citation coordinates
     for that line — e.g. [Britton Decl.|p2:3¶7]. Adobe Reader's drag-select
     extends across the full row band, so a selection that reaches the right
     margin captures the marker; the PasteLegalQuotation Word macro then
     parses the markers and builds a single trailing citation summarizing
     the range. Markers do not affect visible rendering; the diff between
     before-and-after rasters at 150 DPI is zero pixels.

The Westlaw and Lexis search prefix tables, statute name variants, and URL
forms here are kept in sync with the cross-opener extension's content.js
and workups.html, which are validated against live Westlaw and Lexis+
pages. Those files are authoritative whenever they disagree with this one.

Logs to <folder>/pdf_linker.log.
"""

import logging
import os
import re
import sys
import traceback
from pathlib import Path

# ────────────────────────────────────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────────────────────────────────────
SHAREPOINT_BASE = (
    Path(os.environ.get("USERPROFILE", "C:/Users/ZCoderre"))
    / "Los Angeles Superior Court"
    / "Research Attorney and Law Clerk Unit - Zachary Coderre"
)

# Standard Tesseract install paths to try if not on PATH
TESSERACT_CANDIDATES = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tesseract.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Tesseract-OCR" / "tesseract.exe",
    Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
    Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
    Path(os.environ.get("USERPROFILE", "")) / "AppData" / "Local" / "Tesseract-OCR" / "tesseract.exe",
]

# Visual link styling
LINK_COLOUR = (0.0, 0.0, 0.85)  # blue (RGB 0..1)

# ────────────────────────────────────────────────────────────────────────────
# Code conversion (matches workups.html / cross-opener / harvester)
# ────────────────────────────────────────────────────────────────────────────
WL_SEARCH_PREFIX = {
    "BPC": "CA BUS & PROF", "COM": "CA COML", "CIV": "CA CIVIL",
    "CCP": "CA CIV PRO", "CORP": "CA CORP", "EDC": "CA EDUC",
    "ELEC": "CA ELEC", "EVID": "CA EVID", "FAM": "CA FAM",
    "FIN": "CA FIN", "FGC": "CA FISH & G", "FAC": "CA FOOD & AG",
    "GOV": "CA GOVT", "HNC": "CA HARB & NAV", "HSC": "CA HLTH & S",
    "INS": "CA INS", "LAB": "CA LABOR", "MVC": "CA MIL & VET",
    "PEN": "CA PENAL", "PROB": "CA PROBATE", "PCC": "CA PUB CONT",
    "PRC": "CA PUB RES", "PUC": "CA PUB UTIL", "RTC": "CA REV & TAX",
    "SHC": "CA STR & HWY", "UIC": "CA UNEMP INS", "VEH": "CA VEHICLE",
    "WAT": "CA WATER", "WIC": "CA WELF & INST",
}

LEXIS_SEARCH_PREFIX = {
    "BPC": "Cal Bus & Prof Code", "COM": "Cal U Com Code", "CIV": "Cal Civ Code",
    "CCP": "Cal Code Civ Proc", "CORP": "Cal Corp Code", "EDC": "Cal Ed Code",
    "ELEC": "Cal Elec Code", "EVID": "Cal Evid Code", "FAM": "Cal Fam Code",
    "FIN": "Cal Fin Code", "FGC": "Cal Fish & G Code", "FAC": "Cal Food & Agr Code",
    "GOV": "Cal Gov Code", "HNC": "Cal Harb & Nav Code", "HSC": "Cal Health & Saf Code",
    "INS": "Cal Ins Code", "LAB": "Cal Lab Code", "MVC": "Cal Mil & Vet Code",
    "PEN": "Cal Pen Code", "PROB": "Cal Prob Code", "PCC": "Cal Pub Contract Code",
    "PRC": "Cal Pub Resources Code", "PUC": "Cal Pub Util Code", "RTC": "Cal Rev & Tax Code",
    "SHC": "Cal Sts & Hy Code", "UIC": "Cal Unemp Ins Code", "VEH": "Cal Veh Code",
    "WAT": "Cal Wat Code", "WIC": "Cal Welf & Inst Code",
}

# ────────────────────────────────────────────────────────────────────────────
# Reporter list - both CSM (compact) and Bluebook (spaced) forms
# ────────────────────────────────────────────────────────────────────────────
_REPORTERS_RAW = [
    # California
    "Cal.5th", "Cal. 5th", "Cal.4th", "Cal. 4th", "Cal.3d", "Cal. 3d",
    "Cal.2d", "Cal. 2d", "Cal.",
    "Cal.App.5th Supp.", "Cal. App. 5th Supp.",
    "Cal.App.4th Supp.", "Cal. App. 4th Supp.",
    "Cal.App.3d Supp.", "Cal. App. 3d Supp.",
    "Cal.App.2d Supp.", "Cal. App. 2d Supp.",
    "Cal.App.5th", "Cal. App. 5th", "Cal.App.4th", "Cal. App. 4th",
    "Cal.App.3d", "Cal. App. 3d", "Cal.App.2d", "Cal. App. 2d",
    "Cal.App.", "Cal. App.",
    "Cal.Rptr.3d", "Cal. Rptr. 3d", "Cal.Rptr.2d", "Cal. Rptr. 2d",
    "Cal.Rptr.", "Cal. Rptr.",
    # Federal
    "U.S.", "S.Ct.", "S. Ct.", "L.Ed.2d", "L. Ed. 2d", "L.Ed.", "L. Ed.",
    "F.4th", "F. 4th", "F.3d", "F. 3d", "F.2d", "F. 2d", "F.",
    "F.Supp.3d", "F. Supp. 3d", "F.Supp.2d", "F. Supp. 2d", "F.Supp.", "F. Supp.",
    # F. App'x (Federal Appendix) — both straight apostrophe and curly U+2019.
    # PDF text extraction commonly produces the curly form; we accept either.
    "F. App'x", "F. App\u2019x", "F.App'x", "F.App\u2019x",
    # Common out-of-state
    "N.Y.2d", "N.Y. 2d", "N.Y.3d", "N.Y. 3d",
    "P.3d", "P. 3d", "P.2d", "P. 2d", "P.",
    "A.3d", "A. 3d", "A.2d", "A. 2d",
    "N.E.3d", "N.E. 3d", "N.E.2d", "N.E. 2d",
    "N.W.2d", "N.W. 2d",
    "S.E.2d", "S.E. 2d",
    "S.W.3d", "S.W. 3d", "S.W.2d", "S.W. 2d",
    "So.3d", "So. 3d", "So.2d", "So. 2d",
]
REPORTERS_SORTED = sorted(_REPORTERS_RAW, key=len, reverse=True)
REPORTER_PATTERN = "|".join(re.escape(r) for r in REPORTERS_SORTED)

# ────────────────────────────────────────────────────────────────────────────
# Statute code recognition
# ────────────────────────────────────────────────────────────────────────────
STATUTE_CODES = [
    # Long forms. Internal spaces are `\s+` (not literal " ") so the
    # patterns survive line-wrapped citations like "Code of Civil
    # \nProcedure section 430.10(e)" — common in body text where the
    # code name straddles a line break. A literal-space pattern would
    # silently fail to match such wraps, leaving the citation unlinked.
    (r"Code\s+of\s+Civil\s+Procedure", "CCP"),
    (r"Civil\s+Code", "CIV"),
    (r"Penal\s+Code", "PEN"),
    (r"Evidence\s+Code", "EVID"),
    (r"Business\s+(?:and|&)\s+Professions\s+Code", "BPC"),
    (r"Family\s+Code", "FAM"),
    (r"Government\s+Code", "GOV"),
    (r"Health\s+(?:and|&)\s+Safety\s+Code", "HSC"),
    (r"Labor\s+Code", "LAB"),
    (r"Probate\s+Code", "PROB"),
    (r"Vehicle\s+Code", "VEH"),
    (r"Welfare\s+(?:and|&)\s+Institutions\s+Code", "WIC"),
    (r"Corporations\s+Code", "CORP"),
    (r"Insurance\s+Code", "INS"),
    (r"Revenue\s+(?:and|&)\s+Taxation\s+Code", "RTC"),
    (r"Education\s+Code", "EDC"),
    (r"Elections\s+Code", "ELEC"),
    (r"Financial\s+Code", "FIN"),
    (r"Fish\s+(?:and|&)\s+Game\s+Code", "FGC"),
    (r"Food\s+(?:and|&)\s+Agricultural\s+Code", "FAC"),
    (r"Harbors\s+(?:and|&)\s+Navigation\s+Code", "HNC"),
    (r"Military\s+(?:and|&)\s+Veterans\s+Code", "MVC"),
    (r"Public\s+Contract\s+Code", "PCC"),
    (r"Public\s+Resources\s+Code", "PRC"),
    (r"Public\s+Utilities\s+Code", "PUC"),
    (r"Streets\s+(?:and|&)\s+Highways\s+Code", "SHC"),
    (r"Unemployment\s+Insurance\s+Code", "UIC"),
    (r"Water\s+Code", "WAT"),
    (r"Commercial\s+Code", "COM"),

    # CSM short forms
    (r"Code Civ\.\s*Proc\.", "CCP"),
    (r"Civ\.\s*Code", "CIV"),
    (r"Pen\.\s*Code", "PEN"),
    (r"Evid\.\s*Code", "EVID"),
    (r"Bus\.\s*(?:&|and)\s*Prof\.\s*Code", "BPC"),
    (r"Fam\.\s*Code", "FAM"),
    (r"Gov\.\s*Code", "GOV"),
    (r"Health\s*(?:&|and)\s*Saf\.\s*Code", "HSC"),
    (r"Lab\.\s*Code", "LAB"),
    (r"Prob\.\s*Code", "PROB"),
    (r"Veh\.\s*Code", "VEH"),
    (r"Welf\.\s*(?:&|and)\s*Inst\.\s*Code", "WIC"),
    (r"Corp\.\s*Code", "CORP"),
    (r"Ins\.\s*Code", "INS"),
    (r"Rev\.\s*(?:&|and)\s*Tax\.\s*Code", "RTC"),
    (r"Educ\.\s*Code", "EDC"),
    (r"Elec\.\s*Code", "ELEC"),
    (r"Fin\.\s*Code", "FIN"),
    (r"Fish\s*(?:&|and)\s*Game Code", "FGC"),
    (r"Food\s*(?:&|and)\s*Agric\.\s*Code", "FAC"),
    (r"Harb\.\s*(?:&|and)\s*Nav\.\s*Code", "HNC"),
    (r"Mil\.\s*(?:&|and)\s*Vet\.\s*Code", "MVC"),
    (r"Pub\.\s*Cont(?:ract)?\.?\s*Code", "PCC"),
    (r"Pub\.\s*Res(?:ources)?\.?\s*Code", "PRC"),
    (r"Pub\.\s*Util(?:ities)?\.?\s*Code", "PUC"),
    (r"Sts\.\s*(?:&|and)\s*Hy\.\s*Code", "SHC"),
    (r"Unemp\.\s*Ins\.\s*Code", "UIC"),
    (r"Wat\.\s*Code", "WAT"),
    (r"Com\.\s*Code", "COM"),

    # Extra variants validated by the cross-opener extension's content.js
    (r"Govt\.\s*Code", "GOV"),
    (r"Fish\s*(?:&|and)\s*G\.\s*Code", "FGC"),
    (r"Food\s*(?:&|and)\s*Agr\.\s*Code", "FAC"),

    # Practitioner-style "X Code" reorderings of multi-word codes. The CSM
    # short forms above use "Code Civ. Proc." (Code first), but California
    # briefs frequently write "Cal. Civ. Proc. Code" (Code last). Add the
    # reversed orderings so both word orders match.
    (r"Civ\.\s*Proc\.\s*Code", "CCP"),
    (r"Civil\s+Procedure\s+Code", "CCP"),

    # Bare short form without "Code". Some briefs write "Civ. Proc.
    # § 430.10(e)" with no preceding "Code". STATUTE_RE requires a "§"
    # (or "section") + section number right after the code name, so a
    # standalone "Civ. Proc." in body prose can't accidentally trigger
    # this — only the citation form will. Listed last so the longer
    # "Code Civ. Proc." and "Civ. Proc. Code" patterns win when present
    # (alternation tries patterns in length-descending order).
    (r"Civ\.\s*Proc\.", "CCP"),
]
STATUTE_CODES_SORTED = sorted(STATUTE_CODES, key=lambda x: len(x[0]), reverse=True)


def _build_statute_re():
    parts = [f"(?P<c{i}>{pat})" for i, (pat, _) in enumerate(STATUTE_CODES_SORTED)]
    code_alt = "|".join(parts)
    # Section number: digits, optional .digits, optional letter suffix (e.g.
    # "437c"), optional subsection like (b)(1)
    full = (
        r"\b(?:Cal\.\s*|California\s+)?"
        rf"(?:{code_alt})"
        r",?\s*"
        # Section marker (§, "section", or "sec.") is OPTIONAL: practitioners
        # routinely drop it, writing "Code of Civil Procedure 430.30(a)" or
        # "Penal Code 187". We capture whether it was present in `mk` so the
        # caller can apply a stricter section shape when it's absent (a bare
        # code name followed by a list counter like "2." at a paragraph break
        # must not be mistaken for a citation — see find_statute_citations).
        r"(?:(?P<mk>§§?|sections?|secs?\.?)\s*)?"
        r"(?P<sec>\d+(?:\.\d+)?[a-z]?(?:\([a-z0-9]+\))*)"
    )
    # IGNORECASE so all-caps practitioner forms like "CAL. CIV. PROC. CODE
    # § 1281.2" match alongside the conventional title-case forms. False
    # positives are held down by requiring the full code name AND, when no
    # section marker is present, a section number distinctive enough not to
    # be a list/paragraph counter (enforced in find_statute_citations).
    return re.compile(full, re.DOTALL | re.IGNORECASE)


STATUTE_RE = _build_statute_re()


# Federal statutes: "9 U.S.C. § 1", "42 U.S.C. § 1983", etc. These have a
# title number preceding the code abbreviation rather than the optional
# "Cal."/"California" prefix that STATUTE_RE handles. We detect them with
# a parallel regex and emit keys in their natural form: "9 U.S.C. § 1".
# URL building (see _build_usc_term) reads the title and section back out.
USC_RE = re.compile(
    # Word-boundary, then title number (1-3 digits), space-separated
    # "U.S.C." (with optional intervening spaces between letters as PDFs
    # sometimes render it), then section marker and section identifier.
    r"\b(?P<title>\d{1,3})\s+U\.\s*S\.\s*C\."
    r"(?:\s*App\.)?"                              # optional ", App."
    r"\s*"
    r"(?:§§?|sections?|secs?\.?)\s*"
    r"(?P<sec>\d+(?:\.\d+)?[a-z]?(?:\([a-z0-9]+\))*)",
    re.IGNORECASE,
)


def _statute_abbrev(match):
    for i, (_, abbrev) in enumerate(STATUTE_CODES_SORTED):
        if match.group(f"c{i}"):
            return abbrev
    return None


# After a primary statute citation matches, additional sections may follow
# in chained form like:
#   "Code of Civil Procedure sections 598 and 1048(b)"
#   "Civ. Code §§ 1542, 1543, and 1544"
#   "Pen. Code §§ 187, 189"
# This pattern matches a single continuation: a connector (",", " and ",
# ", and ") followed by another section number. The caller applies it
# repeatedly starting at the end of the previous match to extract every
# section in the chain. The continuation must immediately follow the
# previous match (anchored via re.match at scan_pos) — any intervening
# non-connector text breaks the chain.
ADDL_SEC_RE = re.compile(
    r"\s*(?:,\s*and|,|\s+and)\s+"
    r"(?P<sec>\d+(?:\.\d+)?[a-z]?(?:\([a-z0-9]+\))*)",
    re.IGNORECASE,
)


# ────────────────────────────────────────────────────────────────────────────
# Rule pattern
# ────────────────────────────────────────────────────────────────────────────
RULE_RE = re.compile(
    r"\b(?:Cal\.\s*Rules?\s*of\s*Court|California\s*Rules?\s*of\s*Court),?\s*"
    r"rules?\s+(\d+(?:\.\d+)*(?:\([a-z0-9]+\))*)",
    re.IGNORECASE,
)

# Rules of Professional Conduct.
RPC_RE = re.compile(
    r"\b(?:Cal(?:ifornia)?\.?\s+)?Rules?\s+of\s+(?:Prof(?:essional)?\.?\s+)?Conduct\s+"
    r"(\d+(?:\.\d+)*(?:\([a-z0-9]+\))*)",
    re.IGNORECASE,
)

# ────────────────────────────────────────────────────────────────────────────
# Case patterns - v.-anchor approach for accuracy across CSM/Bluebook
# ────────────────────────────────────────────────────────────────────────────
ANCHOR_RE = re.compile(r"(?<=\s)v\.(?=\s)")
# vol REPORTER page (with optional pin or pin range like 247-48)
REPORTER_PART = (
    rf"(\d{{1,4}})\s+({REPORTER_PATTERN})\s+(\d{{1,5}})"
    # Optional pin or pin-range. The dash character class accepts all common
    # PDF-extracted dashes: ASCII hyphen-minus, en dash (U+2013), em dash
    # (U+2014), figure dash (U+2012), and minus sign (U+2212). PDFs from
    # different layout tools render the same Bluebook pin range with
    # different code points, and missing one breaks otherwise-valid cites
    # (this caused "Santana v. FCA US, LLC, 56 Cal.App.5th 324, 345‒46
    # (2020)" to be undetected — the figure dash U+2012 wasn't in the class).
    rf"(?:,\s*\d{{1,5}}(?:[-\u2012\u2013\u2014\u2212]\d{{1,5}})?)?"
)
CSM_TAIL = re.compile(rf"\s*\((?:[^)]*?\b)?(\d{{4}})\)\s+{REPORTER_PART}")
# Bluebook tail: ", REPORTER (court year)" — allow optional court abbreviation
# in parens like (9th Cir. 2015), (S.D.N.Y. 2009), (Cal. 2004), or just (2001).
# The non-greedy [^)]*? before the year matches optional court text without
# backtracking issues.
#
# An optional comma is allowed AFTER the pin and before "(year)" — some
# briefs write "108 Cal. App. 4th 773, 780, (2003)" with a trailing comma
# after the pin. The trailing comma adds no information but is a real
# practitioner habit; we accept it rather than miss the cite.
BB_TAIL = re.compile(
    rf",\s+{REPORTER_PART}\s*,?\s*\((?:[^)]*?\b)?(\d{{4}})\)"
)

# Flat tail: " REPORTER (court year)" — same as Bluebook but WITHOUT the comma
# between the defendant and the volume. Common in California practitioner
# briefs and in tables of authorities:
#   "Donlen v. Ford Motor Co. 217 Cal. App. 4th 138 (2013)"
#   "Rattagan v. Uber Technologies, Inc. 17 Cal. 5th 1 (2024)"
#   "LiMandri v. Judkins 52 Cal.App.4th 326 (1997)"
# Required: a space (not comma) before the volume. Group order matches BB_TAIL
# so downstream code in find_case_citations can treat them identically.
# Some defendant names end with a period (e.g. "Inc.", "Corp.", "Am.", "Co.")
# — we accept that, otherwise we'd require the period to be optional and
# end up matching mid-sentence noise. The walk-back already validates that
# what precedes "v." is a real party name.
FLAT_TAIL = re.compile(
    rf"\s+{REPORTER_PART}\s*,?\s*\((?:[^)]*?\b)?(\d{{4}})\)"
)

# Westlaw-only citation tail: ", YYYY WL NNNNNN, at *N (court date)"
# (or without the pin "at *N"). Used for unpublished decisions that exist
# only on Westlaw; the year inside the parens may include a court abbreviation
# and a date like (C.D. Cal. Nov. 2, 2021).
# Group layout: (1) year-of-cite (in WL key), (2) WL number, (3) decision year
WL_TAIL = re.compile(
    r",\s+(\d{4})\s+WL\s+(\d{4,8})"          # YYYY WL NNNNNN
    # Optional ", at *N" pin, optionally followed by " n.M" footnote pin
    # ("at *5 n.7" is common in S.D.N.Y. citations).
    r"(?:,\s*at\s+\*?\d+(?:\s+n\.\d+)?)?"
    r"\s*\((?:[^)]*?\b)?(\d{4})\)"            # (court date)
)

# Lexis-only citation tail: ", YYYY U.S. Dist. LEXIS NNNNN (court date)".
# Structural parallel to WL_TAIL — both encode an online-database number
# that isn't a real page in any printed reporter, so the trailing number
# needs broader tolerance than the \d{1,5} page constraint used in the
# CSM/BB/FLAT reporter patterns. Same optional pin/footnote shape as WL.
# Group layout: (1) year-of-cite, (2) LEXIS number, (3) decision year.
# URL routing: cites matched here get lexis_only=True (mirrors wl_only),
# forcing resolution through Lexis regardless of the active provider —
# Westlaw doesn't carry LEXIS database numbers as a lookup key.
LEXIS_TAIL = re.compile(
    r",\s+(\d{4})\s+U\.S\.\s*Dist\.\s*LEXIS\s+(\d{4,8})"
    r"(?:,\s*at\s+\*?\d+(?:\s+n\.\d+)?)?"
    r"\s*\((?:[^)]*?\b)?(\d{4})\)"
)

# Slip-cite tail: "[, ]?Case No. <docket-id> (<court> [date])". These are
# decisions that haven't been published in a reporter and don't have a
# WL/LEXIS number assigned yet — the brief identifies them by their
# trial-court docket number and the court parenthetical. Because there's
# no reporter cite to look up, URL resolution falls back to a case-name
# search (handled in resolve_url via the slip_only branch).
#
# Match requirements:
#   * Comma is optional (the spreadsheet has "Li v. Experian Info. Sols.,
#     Inc. Case No. 25STCV22646" with no comma after "Inc.").
#   * Docket-id is letters, digits, and common docket punctuation
#     (BCV-24-100951, 25STCV22646, 1:16-cv-12653-ADB, 19-cv-01080).
#   * The court parenthetical may or may not contain a date — we don't
#     require a year because slip cites without dates do exist ("(Sup. Ct.
#     Cal. Los Angeles Cnty.)"). The parenthetical itself is required.
# Group layout: (1) docket id (for diagnostics), (2) full parenthetical
# contents (court + optional date), (3) year if present, else empty.
SLIP_TAIL = re.compile(
    r",?\s+Case\s+No\.\s+([A-Z0-9][A-Z0-9:\-]{3,30})"
    r"\s*\(([^)]{3,80})\)",
    re.IGNORECASE,
)

# Probate, conservatorship, and family-law cases use "in the matter of"
# conventions instead of "X v. Y": "In re Marriage of Smith", "Estate of
# Bowles", "Guardianship of Doe", "Conservatorship of Roe", "Adoption of
# Jones". All share the same citation-tail structure as In re, so we use
# one regex over a prefix alternation. The prefix isn't captured as its
# own group — that would shift the numeric group indices the consumer
# code relies on — so the consumer re-extracts it from `match.group(0)`
# via _NONV_PREFIX_RE below.
_NONV_PREFIX = (
    r"In re|"
    r"Estate of|"
    r"Guardianship of|"
    r"Conservatorship of|"
    r"Adoption of|"
    r"Marriage of"
)

# Used by the consumer to recover which prefix matched, since the prefix
# itself isn't a numbered capture group. Anchored at start-of-match.
_NONV_PREFIX_RE = re.compile(rf"^\s*({_NONV_PREFIX})\b")

# In re / Estate of / Guardianship of / etc. cases: support CSM "(year)
# vol REPORTER page", Bluebook ", vol REPORTER page (court year)", and
# flat " vol REPORTER page (court year)" (no-comma) forms. The
# Bluebook/flat forms also accept court abbreviations in parens (e.g.
# "In re Doe, 555 F.3d 100 (9th Cir. 2009)").
INRE_RE = re.compile(
    rf"\b(?:{_NONV_PREFIX})\s+([A-Z][A-Za-z0-9.\-'&, ]+?)\s*"
    rf"(?:"
    rf"\((\d{{4}})\)\s+(\d{{1,4}})\s+({REPORTER_PATTERN})\s+(\d{{1,5}})"
    rf"|"
    rf",?\s+(\d{{1,4}})\s+({REPORTER_PATTERN})\s+(\d{{1,5}})\s*"
    rf"\((?:[^)]*?\b)?(\d{{4}})\)"
    rf"|"
    # WL alternative: "In re X, [docket text], YYYY WL NNNNNN (court year)".
    # Federal district court WL cites commonly carry docket info between the
    # case name and the WL number ("In re Intuniv Antitrust Litig., Civil
    # Action No. 1:16-cv-12653-ADB, 2021 WL 517386 (D. Mass. Feb. 11, 2021)").
    # We allow up to ~80 characters of non-newline filler before the WL
    # number. The filler may include colons (docket numbers) which aren't
    # part of the case-name character class.
    rf"[,\s][^\n]{{0,80}}?,\s+(\d{{4}})\s+WL\s+(\d{{4,8}})"
    rf"(?:,\s*at\s+\*?\d+(?:\s+n\.\d+)?)?"
    rf"\s*\((?:[^)]*?\b)?(\d{{4}})\)"
    rf")"
)

SUPRA_RE = re.compile(
    rf"\b((?:(?:{_NONV_PREFIX})\s+)?[A-Z][A-Za-z0-9.\-'&]+(?:\s+v\.\s+[A-Z][A-Za-z0-9.\-'&]+)?)"
    r",\s*supra\b"
)

# Consolidated-litigation cases ending with the literal word "Cases", with no
# "v." or "In re": "Ford Motor Warranty Cases (2025) 17 Cal.5th 1122",
# "Gilead Tenofovir Cases (2024) 98 Cal.App.5th 911". Each prefix word must
# be Title Case (capital letter followed by at least one lowercase letter)
# so we don't match "TABLE OF AUTHORITIES Cases" headings as a citation.
_TITLE_WORD = r"[A-Z][a-z][A-Za-z]*"
# First word is constrained to NOT be one of the common connectors that
# could precede a case-name reference in body text ("The Ford Motor Warranty
# Cases held...", "In Ford Motor Warranty Cases the court..."). Without this
# guard the leading "The"/"In"/"See" gets glued onto the case name.
_CASES_FIRST = r"(?!The\b|In\b|See\b|Cf\b|But\b)" + _TITLE_WORD
CASES_RE = re.compile(
    rf"\b({_CASES_FIRST}(?:\s+{_TITLE_WORD}){{1,5}}\s+Cases)\s*"
    rf"(?:"
    rf"\((\d{{4}})\)\s+(\d{{1,4}})\s+({REPORTER_PATTERN})\s+(\d{{1,5}})"
    rf"|"
    rf",?\s+(\d{{1,4}})\s+({REPORTER_PATTERN})\s+(\d{{1,5}})\s*"
    rf"\((?:[^)]*?\b)?(\d{{4}})\)"
    rf")"
)

SIGNAL_PREFIXES = {
    "see", "cf", "cf.", "per", "in", "but", "compare", "accord", "e.g.",
    "also", "n", "of", "the", "and", "to", "by", "for", "with", "from",
    "as", "if", "when", "while", "since", "because", "though", "although",
    "court", "supreme", "federal", "state", "california",
}

# Tokens that are TOA section headers — when newline normalization runs, lines
# like "Cases\nSmith v. Jones..." become "Cases Smith v. Jones...", and the
# walk-back from "v." would otherwise pull "Cases" into the plaintiff name.
# We stop walk-back when we hit any of these as a standalone token. The match
# is case-insensitive and on the cleaned token (no surrounding punctuation).
_TOA_HEADERS = {
    "cases", "statutes", "rules", "authorities", "treatises",
    "regulations", "constitutional", "miscellaneous",
}

# Sentence-internal signal words that look like corporate abbreviations
# ("E.g.", "I.e.", "Cf.") and would otherwise pass the cap-then-short
# heuristic in walk-back. Listed here so `_walk_back_for_name` can refuse
# to collect them. Without this guard, "Song Beverly Act. E.g., Noori v.
# Jaguar..." gets collected as "Song Beverly Act. E.g., Noori".
# Stored without trailing punctuation because the matcher strips it before
# checking — entries are matched against `lower(strip("(.,;:\"\'", ",.;:"))`.
_STOPPER_ABBREVS = {
    "e.g", "i.e", "cf", "etc", "viz", "supra",
    "eg", "ie", "see", "accord", "compare",
}

# Corporate-suffix tokens that mark the end of a party name. Used by the
# digit-token rule in walk-back: a digit is only kept as part of the
# plaintiff if at least one of these has already been collected (otherwise
# the digit is almost certainly a page number bleeding in from a TOA layout).
# Stored without trailing punctuation — comparisons strip ".,;:" first.
_CORP_SUFFIX_LOWER = {
    "inc", "co", "corp", "ltd", "grp", "ass'n", "assn", "lp",
}
_CORP_SUFFIX_UPPER = {"LLC", "LLP", "LP", "LLLP", "PLLC", "PC", "PLC"}


def _short_name(plaintiff: str) -> str:
    p = plaintiff.strip()
    # Strip non-v. case-name prefixes ("In re", "Estate of",
    # "Guardianship of", etc.) plus "Ex parte" and "People v." so the
    # short name is the distinguishing subject ("Bowles", not "Estate").
    p = re.sub(rf"^(?:(?:{_NONV_PREFIX})\s+|Ex parte\s+|People v\.\s+)",
               "", p, flags=re.IGNORECASE)
    parts = p.split()
    return parts[0].rstrip(",.;:") if parts else p


def _walk_back_for_name(text: str, v_pos: int):
    """Return start index of plaintiff name, or None."""
    pos = v_pos - 1
    while pos > 0 and text[pos] == " ":
        pos -= 1

    # Skip a trailing ", et al." if present immediately before v.
    # Real text is "Juan Carlos Meneses, et al. v. FCA US LLC" — the walk-back
    # would otherwise hit "al." (lowercase) and abandon. We treat ", et al."
    # (or ", et al" without trailing period) as if it weren't there.
    et_al_match = re.search(r",\s*et\s+al\.?\s*$", text[: pos + 1])
    if et_al_match:
        pos = et_al_match.start() - 1
        while pos > 0 and text[pos] == " ":
            pos -= 1

    tokens = []  # (start, end, text) closest-to-v.-first
    while pos >= 0:
        while pos >= 0 and text[pos] in " \t":
            pos -= 1
        if pos < 0:
            break
        # Newline = stop (citation can't span paragraph)
        if text[pos] == "\n":
            break
        tok_end = pos + 1
        while pos >= 0 and text[pos] not in " \n\t":
            pos -= 1
        tok_start = pos + 1
        tok = text[tok_start:tok_end]
        if not tok:
            break

        # Hard sentence boundary: token ends with : ; ! ?  (the case name
        # cannot include these as the final character of a preceding token)
        if tok and tok[-1] in ":;!?":
            break

        # Stopper-abbreviations: "E.g.,", "I.e.,", "Cf.", "Etc." etc. look
        # superficially like the corporate-abbreviation pattern (capital-
        # then-lowercase-with-dots), but they're actually sentence-internal
        # signal words that mark the END of any case-name we should still be
        # collecting. Reject them explicitly so the walk-back doesn't slurp
        # text like "Song Beverly Act. E.g., Noori v. ..." into a plaintiff
        # name. The check is on the cleaned, lowercased form.
        _tok_clean_low = tok.lstrip("(.,;:\"'").rstrip(",.;:").lower()
        if _tok_clean_low in _STOPPER_ABBREVS:
            if tokens:
                break
            return None

        # End-of-sentence: ends with "." preceded by lowercase. We allow
        # any capitalized-then-short-lowercase token like "Co.", "Inc.",
        # "Ref.", "Mfg.", "Sav.", "Bldg." as part of a corporate name —
        # these appear constantly inside party names. The cap-then-short
        # heuristic matches abbreviations without false-positives on real
        # sentence ends ("approved.", "court.").
        if tok.endswith(".") and len(tok) > 1 and tok[-2].islower():
            inner = tok.rstrip(".")
            is_short_cap_abbrev = (
                inner and inner[0].isupper() and 1 <= len(inner) <= 6
            )
            if not is_short_cap_abbrev and tok.lower() not in {
                "co.", "inc.", "corp.", "ltd.", "ass'n.", "ass'n.",
            }:
                break

        connectors = {"of", "the", "and", "&", "de", "la", "du", "von", "van", "re"}
        # Strip leading punctuation. We also strip a leading hyphen because
        # PDFs sometimes render hyphenated party names like "Bigler-Engler"
        # with a stray space-hyphen-space sequence ("Bigler -Engler"), which
        # the tokenizer splits into two tokens "Bigler" and "-Engler". We
        # want "-Engler" to clean to "Engler" so the walk-back keeps going.
        clean = tok.lstrip("(.,;:\"'\u2010\u2011\u2012\u2013\u2014\u2212-").rstrip(",.;:")

        if not clean:
            break

        # Citation-join boundary: two citations strung together with "and"
        # (or "&") \u2014 "Orozco v. Casimiro (2004) 121 Cal.App.4th Supp. 7 and
        # Del Monte ... v. Dolan ...". Walking back from the second "v." we
        # must not cross into the first citation. If the connector's left
        # neighbour is a citation tail (a page number, or a reporter
        # abbreviation), the connector separates two citations rather than
        # two words of one party name, so stop and keep the name gathered so
        # far. A name-internal "&"/"and" ("Properties & Investments") has a
        # capitalized word \u2014 not a number/reporter \u2014 to its left and is kept.
        if clean.lower() in {"and", "&"} and tokens:
            _left = re.search(r"(\S+)\s*$", text[:tok_start])
            if _left:
                _lt = _left.group(1).rstrip(",.;:")
                if _lt.isdigit() or re.search(REPORTER_PATTERN, _lt):
                    break

        # Pure-digit tokens. These appear in real party names ("Studio
        # 1220, Inc.", "Advanced Grp. 400" — though that one's on the
        # defendant side) but ALSO appear as page numbers in TOAs that
        # bleed into the walk-back after newline normalization (e.g.
        # "...14, 16 McGee v. Mercedes-Benz..."). To distinguish, we
        # accept the digit if EITHER:
        #   (a) we've already collected a corporate-suffix token closer
        #       to v. — "Studio 1220, Inc." reaches "Inc." first, then
        #       "1220", at which point _has_corp_marker is true; OR
        #   (b) the digit is immediately preceded (in source order, i.e.
        #       the next leftward token we haven't tokenized yet) by a
        #       "local number" introducer like "Local", "Loc.", "No.",
        #       or "Chapter" — these unambiguously mark the digit as
        #       part of a party name ("Service Employees Local 660",
        #       "L.A. Coll. Fac. Guild Loc. 1521") rather than a page
        #       reference. Page references after newline normalization
        #       look like ", 16, 14, ..." with no such introducer.
        if clean[0].isdigit():
            # Comma-suffixed digit (e.g. "16,") is a page-reference list item
            # after TOA newline normalisation — never a company number.
            if tok.rstrip().endswith(","):
                if tokens:
                    break
                return None
            _has_corp_marker = any(
                t[2].rstrip(",.;:").lower() in _CORP_SUFFIX_LOWER
                or t[2].upper() in _CORP_SUFFIX_UPPER
                for t in tokens
            )
            # Peek at the leftward source text for a local-number introducer.
            # tok_start is the start index of the digit token in `text`.
            _local_intro = False
            _peek_left = text[:tok_start].rstrip()
            _last_tok_match = re.search(r"(\S+)$", _peek_left)
            if _last_tok_match:
                _prev = _last_tok_match.group(1).rstrip(",.;:").lower()
                if _prev in {"local", "loc", "no", "chapter", "ch"}:
                    _local_intro = True
            if not (_has_corp_marker or _local_intro):
                if tokens:
                    break
                return None
            tokens.append((tok_start, tok_end, tok))
            continue

        if clean[0].islower() and clean.lower() not in connectors:
            if tokens:
                break
            return None
        if not clean[0].isupper() and clean.lower() not in connectors:
            if tokens:
                break
            return None

        # Reject ALLCAPS tokens that are clearly heading text. We use a
        # length threshold of 5+ because:
        #   - Real party names sometimes have ALLCAPS abbreviations of 2-4
        #     chars: "OCM Principal", "FCA US LLC", "B.B.", "L.A. Times".
        #   - Heading words ("TABLE", "AUTHORITIES", "DEFENDANT", "MOTION",
        #     "SUMMARY", "JUDGMENT") are almost always 5+ chars.
        # We also reject law-firm suffixes that commonly appear in page
        # footers immediately above the body. "MORTENSON TAGGART ADAMS LLP"
        # in a footer + "Santa Clara Valley Water Dist. v. ..." on the next
        # line yielded "LLP Santa Clara Valley..." as the captured plaintiff
        # before this guard.
        alpha_chars = [c for c in clean if c.isalpha()]
        if (len(alpha_chars) >= 5
                and all(c.isupper() for c in alpha_chars)
                and clean.lower() not in connectors):
            if tokens:
                break
            return None
        if clean.upper() in {"LLP", "LLC", "LLLP", "PLLC", "PC", "PLC"}:
            # Law-firm-suffix token. Two scenarios:
            #   (a) Part of the plaintiff name — "Smith LLC v. Jones". When
            #       walked backward from v., LLC is the FIRST token collected,
            #       directly attached to the rest of the party name.
            #   (b) Page-footer artifact — "MORTENSON TAGGART ADAMS LLP\n
            #       Santa Clara Valley Water Dist. v. ...". Here LLC/LLP
            #       appears AFTER several plaintiff tokens have been
            #       collected, because the real plaintiff is "Santa Clara
            #       Valley Water Dist." and LLP is part of an upstream
            #       law-firm letterhead in the same flow.
            # We allow (a) and reject (b): break if we've already collected
            # tokens, accept otherwise.
            if tokens:
                break
            # Fall through to normal handling for first-token case.

        # Stop at TOA section-header words ("Cases", "Statutes", "Rules"...).
        # After newline normalization, a TOA layout that puts "Cases" on its
        # own line directly above a citation looks like "Cases Smith v. Jones".
        # Without this guard, "Cases" would get pulled into the plaintiff name.
        if clean.lower() in _TOA_HEADERS:
            if tokens:
                break
            return None

        tokens.append((tok_start, tok_end, tok))

    if not tokens:
        return None

    # tokens are reverse-order; reverse to forward
    tokens.reverse()

    # Strip leading signal words
    while tokens:
        first = tokens[0][2].lower().rstrip(",.;:").lstrip("(.,;:\"'")
        if first in SIGNAL_PREFIXES:
            # Preserve "In re"
            if first == "in" and len(tokens) > 1:
                second = tokens[1][2].lower().rstrip(",.;:")
                if second == "re":
                    break
            tokens.pop(0)
        else:
            break

    if not tokens:
        return None

    # Advance start past leading non-letter punctuation like "(" or quotation
    start = tokens[0][0]
    end = tokens[0][1]
    while start < end and not text[start].isalpha():
        start += 1
    return start


def find_case_citations(text: str):
    """Return list of citation dicts for full case cites in `text`."""
    results = []

    # v.-anchored cases
    for m in ANCHOR_RE.finditer(text):
        v_start = m.start()
        v_end = m.end()
        plaintiff_start = _walk_back_for_name(text, v_start)
        if plaintiff_start is None:
            continue
        plaintiff = text[plaintiff_start:v_start].strip()

        rest = text[v_end:]

        # Strategy: find first occurrence of any tail in `rest`, then pick
        # whichever appears earliest. This handles CSM, Bluebook, Westlaw-only,
        # Lexis-only, and flat (no-comma) citation forms uniformly.
        csm_search   = CSM_TAIL.search(rest)
        bb_search    = BB_TAIL.search(rest)
        wl_search    = WL_TAIL.search(rest)
        lexis_search = LEXIS_TAIL.search(rest)
        flat_search  = FLAT_TAIL.search(rest)

        # Restrict tail to within ~80 chars of v. - cite shouldn't span far.
        # With newline normalization, a single citation comfortably fits in
        # this window; anything farther is almost certainly a different case.
        max_dist = 80

        candidates = []
        if csm_search and csm_search.start() <= max_dist:
            candidates.append(("csm", csm_search))
        if bb_search and bb_search.start() <= max_dist:
            candidates.append(("bb", bb_search))
        if wl_search and wl_search.start() <= max_dist:
            candidates.append(("wl", wl_search))
        if lexis_search and lexis_search.start() <= max_dist:
            candidates.append(("lexis", lexis_search))
        if flat_search and flat_search.start() <= max_dist:
            candidates.append(("flat", flat_search))

        # Slip cite is a *fallback*: only consider it if no reporter-shaped
        # tail matched. Slip cites have no reporter cite to anchor a strong
        # match, so they're vulnerable to misreading "Case No." references
        # in body text that AREN'T citations. Requiring no other tail first
        # avoids picking the slip pattern over a real reporter cite when
        # both appear in the same sentence.
        if not candidates:
            slip_search = SLIP_TAIL.search(rest)
            if slip_search and slip_search.start() <= max_dist:
                candidates.append(("slip", slip_search))
        if not candidates:
            continue
        # Earliest tail wins. When two tails start at the same position
        # (FLAT_TAIL is a strict superset of BB_TAIL minus the comma —
        # they never tie because BB's comma takes a position FLAT can't),
        # the earliest-start rule resolves cleanly. CSM also can't tie BB/FLAT
        # because CSM's "(year)" lead disambiguates.
        chosen = min(candidates, key=lambda c: c[1].start())

        kind, mm = chosen
        defendant_text = rest[: mm.start()].rstrip(", ").strip()
        if not defendant_text or not defendant_text[0].isupper():
            continue
        if len(defendant_text) > 200:
            continue

        if kind == "csm":
            year, vol, reporter, page = mm.group(1), mm.group(2), mm.group(3), mm.group(4)
            rep_compact = re.sub(r"\s+", "", reporter)
            tail_for_key = f"({year}) {vol} {rep_compact} {page}"
        elif kind in ("bb", "flat"):
            # Group layout is identical: (vol, reporter, page, year).
            # The only structural difference is the comma at the start of BB,
            # which both patterns absorb internally before the captured groups.
            vol, reporter, page, year = mm.group(1), mm.group(2), mm.group(3), mm.group(4)
            rep_compact = re.sub(r"\s+", "", reporter)
            tail_for_key = f"({year}) {vol} {rep_compact} {page}"
        elif kind == "wl":
            wl_year, wl_num, decision_year = mm.group(1), mm.group(2), mm.group(3)
            tail_for_key = f"{wl_year} WL {wl_num}"
        elif kind == "lexis":
            lx_year, lx_num, decision_year = mm.group(1), mm.group(2), mm.group(3)
            tail_for_key = f"{lx_year} U.S. Dist. LEXIS {lx_num}"
        else:  # slip
            # Slip cites have no reporter cite — the docket id (group 1)
            # and court parenthetical (group 2) ARE the citation. Encode
            # both in the key so duplicate detection still works; URL
            # resolution falls back to a case-name search.
            docket = mm.group(1)
            court_paren = mm.group(2).strip()
            tail_for_key = f"Case No. {docket} ({court_paren})"

        plaintiff_clean = re.sub(r"\s+", " ", plaintiff).strip()
        defendant_clean = re.sub(r"\s+", " ", defendant_text).strip()
        key = f"{plaintiff_clean} v. {defendant_clean} {tail_for_key}"
        full_span = (plaintiff_start, v_end + mm.end())

        results.append({
            "kind": "case",
            "key": key,
            "span": full_span,
            "match_text": text[full_span[0]: full_span[1]],
            "short": _short_name(plaintiff_clean),
            # Westlaw-only unpublished decisions can't be served by Lexis;
            # always resolve these to a Westlaw URL even when the user's
            # default provider is Lexis.
            "wl_only": (kind == "wl"),
            # Lexis-only mirror: U.S. Dist. LEXIS database numbers can't be
            # served by Westlaw, so always resolve those to a Lexis URL.
            "lexis_only": (kind == "lexis"),
            # Slip cites have no reporter cite. URL resolution falls back
            # to a case-name search against the active provider.
            "slip_only": (kind == "slip"),
        })

    # In re / Estate of / Guardianship of / Conservatorship of /
    # Adoption of / Marriage of cases (no v.)
    for m in INRE_RE.finditer(text):
        name = re.sub(r"\s+", " ", m.group(1)).strip()
        # Recover which prefix matched. INRE_RE doesn't capture the
        # prefix as a numbered group (doing so would shift the numbered
        # captures the branch logic below depends on), so we re-extract
        # it from the matched text.
        prefix_m = _NONV_PREFIX_RE.match(m.group(0))
        prefix = prefix_m.group(1) if prefix_m else "In re"
        # Group layout: 1=name, then EITHER (2,3,4,5) for CSM form,
        # (6,7,8,9) for Bluebook form, or (10,11,12) for the WL form
        # (year-in-cite, WL-number, decision-year). Whichever branch
        # matched is non-None.
        wl_only = False
        if m.group(2):
            year, vol, reporter, page = m.group(2), m.group(3), m.group(4), m.group(5)
        elif m.group(6):
            vol, reporter, page, year = m.group(6), m.group(7), m.group(8), m.group(9)
        else:
            wl_year, wl_num, year = m.group(10), m.group(11), m.group(12)
            wl_only = True
        full_name = f"{prefix} {name}"
        if wl_only:
            key = f"{full_name} {wl_year} WL {wl_num}"
        else:
            rep_compact = re.sub(r"\s+", "", reporter)
            key = f"{full_name} ({year}) {vol} {rep_compact} {page}"
        results.append({
            "kind": "case",
            "key": key,
            "span": m.span(),
            "match_text": m.group(0),
            "short": _short_name(full_name),
            "wl_only": wl_only,
        })

    # "[Subject] Cases" — consolidated-litigation case names with no v./In re.
    for m in CASES_RE.finditer(text):
        name = re.sub(r"\s+", " ", m.group(1)).strip()
        if m.group(2):
            year, vol, reporter, page = m.group(2), m.group(3), m.group(4), m.group(5)
        else:
            vol, reporter, page, year = m.group(6), m.group(7), m.group(8), m.group(9)
        rep_compact = re.sub(r"\s+", "", reporter)
        key = f"{name} ({year}) {vol} {rep_compact} {page}"
        results.append({
            "kind": "case",
            "key": key,
            "span": m.span(),
            "match_text": m.group(0),
            "short": name.split()[0],
        })

    return results


def _skip_to_name_end(s: str) -> str:
    return s


def find_statute_citations(text: str):
    results = []
    for m in STATUTE_RE.finditer(text):
        abbrev = _statute_abbrev(m)
        if not abbrev:
            continue
        # First section: matched by the primary regex (anchored on a
        # code name).
        section = m.group("sec")
        # When the citation had no explicit "§"/"section"/"sec." marker, the
        # code name was directly followed by a number. Accept that only when
        # the number is clearly a statute section — it has a decimal part
        # ("430.30", "1010.6"), a letter suffix ("437c"), a subdivision
        # ("(a)"), or is at least three digits ("187"). This rejects the
        # paragraph/list counters ("1.", "2.") that frequently follow a code
        # name at a numbered-list break and would otherwise be linked as a
        # spurious "§ 2".
        if not m.group("mk"):
            distinctive = re.search(r"\.\d|[a-z]|\(", section, re.IGNORECASE)
            if not distinctive and len(re.sub(r"\D", "", section)) < 3:
                continue
        results.append({
            "kind": "statute",
            "key": f"{abbrev} § {section}",
            "span": m.span(),
            "match_text": m.group(0),
        })
        # Chained additional sections: "§§ A, B, and C" or
        # "sections A and B". The first section grabs the code-name
        # context; subsequent sections inherit the same abbreviation
        # without needing to repeat the code name.
        scan_pos = m.end()
        while True:
            cont = ADDL_SEC_RE.match(text, scan_pos)
            if not cont:
                break
            results.append({
                "kind": "statute",
                "key": f"{abbrev} § {cont.group('sec')}",
                "span": cont.span(),
                "match_text": text[cont.start():cont.end()].lstrip(),
            })
            scan_pos = cont.end()
    # Federal statutes: "9 U.S.C. § 1", "42 U.S.C. § 1983", etc.
    # Key form preserves the title number explicitly: "9 U.S.C. § 1".
    # These are detected by their own regex (USC_RE) rather than via
    # STATUTE_RE's California-code machinery; URL building keys off the
    # "U.S.C." literal in the key.
    for m in USC_RE.finditer(text):
        title = m.group("title")
        section = m.group("sec")
        results.append({
            "kind": "statute",
            "key": f"{title} U.S.C. \u00a7 {section}",
            "span": m.span(),
            "match_text": m.group(0),
        })
    return results


def find_rule_citations(text: str):
    results = []
    for m in RULE_RE.finditer(text):
        rule_num = m.group(1)
        key = f"Cal. Rules of Court, rule {rule_num}"
        results.append({
            "kind": "rule",
            "key": key,
            "span": m.span(),
            "match_text": m.group(0),
        })
    for m in RPC_RE.finditer(text):
        rule_num = m.group(1)
        key = f"Cal. Rules of Prof. Conduct, rule {rule_num}"
        results.append({
            "kind": "rule",
            "key": key,
            "span": m.span(),
            "match_text": m.group(0),
        })
    return results


def find_supra_citations(text: str, full_cites_in_order):
    """Find supra cites and resolve to first matching short_name."""
    seen = {}
    for c in full_cites_in_order:
        if c["kind"] == "case" and c.get("short"):
            seen.setdefault(c["short"], c["key"])

    results = []
    for m in SUPRA_RE.finditer(text):
        cite_text = m.group(1)
        sname = _short_name(cite_text)
        if sname in seen:
            results.append({
                "kind": "case",
                "key": seen[sname],
                "span": m.span(),
                "match_text": m.group(0),
                "short": sname,
                "is_supra": True,
            })
    return results


def _normalize_for_detection(text: str) -> str:
    """Normalize text for citation detection while preserving offsets.

    Replaces single newlines (bare line wraps) with a single space, while
    preserving paragraph breaks. PyMuPDF often emits paragraph breaks as
    \\n followed by space-runs and another \\n (e.g. "...end.\\n \\nNext..."),
    so we look through intervening whitespace when deciding whether a given
    newline is part of a paragraph break.

    Output length matches input length so spans returned by detection still
    index into the original text and PyMuPDF's `page.search_for(match_text)`
    still finds the original glyphs.
    """
    out = list(text)
    n = len(out)

    def _has_newline_within(i: int, direction: int, max_ws: int = 3) -> bool:
        # Look up to max_ws chars in `direction` (-1 or +1) past whitespace.
        # If we hit another \n, it's part of a paragraph break (keep it).
        j = i + direction
        steps = 0
        while 0 <= j < n and steps <= max_ws:
            ch = out[j]
            if ch == "\n":
                return True
            if ch == "\f":
                return True
            if not ch.isspace():
                return False
            j += direction
            steps += 1
        return False

    for i, ch in enumerate(out):
        if ch != "\n":
            continue
        if _has_newline_within(i, -1) or _has_newline_within(i, +1):
            continue  # part of a paragraph break, keep
        out[i] = " "
    return "".join(out)


def find_all_citations(text: str):
    """Find all citations in text, ordered by position."""
    # Normalize line wraps so cites split across lines still match. Spans
    # remain valid against the original text because length is preserved.
    norm = _normalize_for_detection(text)
    full_cases = find_case_citations(norm)
    statutes = find_statute_citations(norm)
    rules = find_rule_citations(norm)

    # Update match_text to use the original text (preserves original
    # whitespace for downstream page.search_for calls).
    for c in full_cases + statutes + rules:
        s, e = c["span"]
        c["match_text"] = text[s:e]

    # Order full cases by position for supra resolution
    full_ordered = sorted(full_cases, key=lambda c: c["span"][0])
    supras = find_supra_citations(norm, full_ordered)
    for c in supras:
        s, e = c["span"]
        c["match_text"] = text[s:e]

    all_cites = full_cases + statutes + rules + supras
    all_cites.sort(key=lambda c: c["span"][0])

    # Deduplicate overlapping spans (e.g. "Smith, supra" inside a longer match)
    dedup = []
    last_end = -1
    for c in all_cites:
        if c["span"][0] >= last_end:
            dedup.append(c)
            last_end = c["span"][1]
    return dedup


# ────────────────────────────────────────────────────────────────────────────
# URL resolution
# ────────────────────────────────────────────────────────────────────────────
def _bare_section(sec: str) -> str:
    """Strip parenthetical subdivisions from a section identifier so it
    can be used as a search term.

    Search engines on Lexis and Westlaw don't separately index
    subdivisions — there's no page for "§ 430.10(e)", only "§ 430.10".
    A search term that includes the subdivision returns no results and
    the user lands on an empty search page instead of the statute.
    The citation key keeps the subdivision (it drives the underline
    text on the link), but URL building uses just the bare section.

    Examples:
      "430.10(e)"   → "430.10"
      "430.10(e)(1)"→ "430.10"
      "1714.10"     → "1714.10"   (decimal IS the section)
      "437c"        → "437c"      (letter suffix is part of section)
      "15200"       → "15200"
    """
    return re.sub(r"\([^)]*\).*$", "", sec)


def _wl_search_term(key: str):
    # Federal U.S.C.: key is "9 U.S.C. § 1" — Westlaw accepts that form
    # directly as a search term.
    if re.match(r"^\d+\s+U\.S\.C\.\s*\u00a7", key):
        return key
    m = re.match(r"^([A-Z]+)\s*§\s*(.+)$", key)
    if not m:
        return None
    p = WL_SEARCH_PREFIX.get(m.group(1))
    return f"{p} § {_bare_section(m.group(2))}" if p else None


def _lexis_search_term(key: str):
    # Federal U.S.C.: same direct form works for Lexis.
    if re.match(r"^\d+\s+U\.S\.C\.\s*\u00a7", key):
        return key
    m = re.match(r"^([A-Z]+)\s*§\s*(.+)$", key)
    if not m:
        return None
    p = LEXIS_SEARCH_PREFIX.get(m.group(1))
    return f"{p} § {_bare_section(m.group(2))}" if p else None


# Validated against the cross-opener extension's injectFloatingButton — these
# are the URL forms that have been confirmed to land on the right pages.
LEXIS_PDMFID = "1530671"


# Westlaw's findType=Y&cite= and Lexis's pdsearchterms= both expect a bare
# reporter citation like "13 Cal.App.5th 1152" or "2021 WL 1234567" - NOT the
# full key with case name and year. The extraction below pulls the reporter
# portion out of any of pdf_linker's case-key forms:
#   "Smith v. Jones (2017) 13 Cal.App.5th 1152"      (CSM)
#   "Anderson v. Liberty Lobby, Inc. (1986) 477 U.S. 242"  (Bluebook)
#   "In re Doe (2009) 555 F.3d 100"                  (In re)
#   "Ford Motor Warranty Cases (2025) 17 Cal.5th 1122"  (Cases)
#   "Smith v. Jones 2021 WL 1234567"                 (Westlaw-only)
_CASE_TAIL_RE = re.compile(r"\((\d{4})\)\s+(\d{1,4})\s+(\S+?)\s+(\d{1,5})\s*$")
_WL_TAIL_RE   = re.compile(r"(\d{4})\s+WL\s+(\d{4,8})\s*$")
# Lexis database tail: "YYYY U.S. Dist. LEXIS NNNNN" at end of a case key.
# Parallel to _WL_TAIL_RE for use in URL building.
_LEXIS_TAIL_RE = re.compile(r"(\d{4})\s+U\.S\.\s*Dist\.\s*LEXIS\s+(\d{4,8})\s*$")


def _case_reporter_cite(case_key: str):
    """Return the reporter portion of a case key, e.g. '13 Cal.App.5th 1152'.
    Returns None if the key doesn't end with a parseable reporter cite."""
    m = _CASE_TAIL_RE.search(case_key)
    if m:
        _year, vol, reporter, page = m.groups()
        return f"{vol} {reporter} {page}"
    m = _WL_TAIL_RE.search(case_key)
    if m:
        year, num = m.groups()
        return f"{year} WL {num}"
    m = _LEXIS_TAIL_RE.search(case_key)
    if m:
        year, num = m.groups()
        return f"{year} U.S. Dist. LEXIS {num}"
    return None


def _slip_search_term(case_key: str) -> str:
    """Build a search term for a slip-cite key.

    Slip-cite keys are shaped:
      "<plaintiff> v. <defendant>[, ?]Case No. <docket> (<court>)"
    Both Westlaw and Lexis return useful results when searched by case
    name alone (the docket id is too narrow and depends on the
    provider's database indexing). We strip the "Case No. ... (...)"
    tail and return just the case name.
    """
    # Strip the slip tail.
    m = re.search(r",?\s*Case\s+No\.\s+", case_key, re.IGNORECASE)
    if m:
        return case_key[: m.start()].strip()
    return case_key


def _disambiguated_lexis_term(case_key: str) -> str:
    """Lexis search term that includes the first word of the plaintiff name.
    Prevents wrong-case hits when a nearby case in the same volume spans the
    target page (e.g. Sheppard v. Maxwell, 384 U.S. 333, spanning page 346,
    returned instead of Miranda v. Arizona, 384 U.S. 346).
    """
    m = _CASE_TAIL_RE.search(case_key)
    if not m:
        return case_key
    _year, vol, reporter, page = m.groups()
    reporter_cite = f"{vol} {reporter} {page}"
    name_part = case_key[: m.start()].strip().rstrip(",")
    nonv = re.match(rf"^({_NONV_PREFIX})\s+(\S+)", name_part, re.IGNORECASE)
    if nonv:
        # Preserve the prefix ("In re", "Estate of", etc.) plus the first
        # word of the subject name so the search disambiguates against
        # other cases sharing that subject word.
        return f"{nonv.group(1)} {nonv.group(2)} {reporter_cite}"
    cases_m = re.match(r"^((?:[A-Z]\S*\s+){1,4}Cases)\b", name_part)
    if cases_m:
        return f"{cases_m.group(1)} {reporter_cite}"
    first_word = name_part.split()[0].rstrip(".,;:") if name_part.split() else ""
    return f"{first_word} {reporter_cite}" if first_word else reporter_cite


def _build_westlaw_case_url(cite_text: str) -> str:
    """Westlaw direct-link form. cite_text MUST be just the reporter cite
    (vol REPORTER page) - including the case name confuses findType=Y and
    yields 'page not found'.
    
    WL citations (e.g., '2015 WL 13626022') use a search-based URL instead of
    findType=Y, which doesn't work reliably for unpublished WL reporters."""
    from urllib.parse import quote
    
    # Check if this is a WL citation (format: YEAR WL NUMBER)
    if " WL " in cite_text:
        # WL citations need search URLs, not direct link format
        return (
            f"https://1.next.westlaw.com/Search/Results.html"
            f"?query={quote(cite_text)}&jurisdiction=CA&contentType=CASE"
        )
    
    # Published reporters use direct link format
    return (
        f"https://1.next.westlaw.com/Link/Document/FullText"
        f"?findType=Y&cite={quote(cite_text)}"
    )


def _build_westlaw_search_url(query: str, statute: bool) -> str:
    from urllib.parse import quote
    base = (
        f"https://1.next.westlaw.com/Search/Results.html"
        f"?query={quote(query)}&jurisdiction=CA"
    )
    return base + "&contentType=STATUTE" if statute else base


def _build_lexis_search_url(term: str) -> str:
    from urllib.parse import quote
    return (
        f"https://plus.lexis.com/search/"
        f"?pdmfid={LEXIS_PDMFID}&pdsearchterms={quote(term)}"
    )


def resolve_url(cite, provider: str = "lexis") -> str:
    """Resolve citation to a search URL on the active provider.

    `provider` is "lexis" (default) or "westlaw".

    Westlaw-only unpublished decisions (`wl_only=True` on the cite) override
    the provider and always resolve to a Westlaw URL — Lexis doesn't carry
    those reporters, so a Lexis search would fail. Lexis-only unpublished
    decisions (`lexis_only=True`, used for U.S. Dist. LEXIS database
    numbers) are the symmetric case: always resolve to Lexis, regardless
    of the active provider.

    Earlier versions consulted a curated citation_repo.json that mapped
    keys to direct-link URLs (Lexis `lni=` document URLs and Westlaw
    direct-cite URLs). Those direct links rot — Lexis re-indexes content
    periodically, and stale `lni`s land on broken pages. Search URLs
    don't rot: the search engines tolerate variations in formatting and
    consistently land on the right document. The repo lookup was
    removed in favor of always building a search URL.
    """
    # Override for unpublished WL / LEXIS cites: each provider can't serve
    # the other's database numbers.
    if cite.get("wl_only"):
        effective_provider = "westlaw"
    elif cite.get("lexis_only"):
        effective_provider = "lexis"
    else:
        effective_provider = provider

    # Build a search URL using the active provider's form.
    if cite["kind"] == "case":
        if cite.get("slip_only"):
            # Slip cites have no reporter to anchor a direct-link URL.
            # Use a case-name search against the active provider. The full
            # key includes case name + "Case No. X (court)" which is enough
            # for the search engines to find the case (and short enough not
            # to overflow the URL).
            search_term = _slip_search_term(cite["key"])
            if effective_provider == "lexis":
                return _build_lexis_search_url(search_term)
            return _build_westlaw_search_url(search_term, statute=False)
        if effective_provider == "lexis":
            return _build_lexis_search_url(_disambiguated_lexis_term(cite["key"]))
        reporter_cite = _case_reporter_cite(cite["key"]) or cite["key"]
        return _build_westlaw_case_url(reporter_cite)

    if cite["kind"] == "statute":
        if effective_provider == "lexis":
            term = _lexis_search_term(cite["key"]) or cite["key"]
            return _build_lexis_search_url(term)
        term = _wl_search_term(cite["key"]) or cite["key"]
        return _build_westlaw_search_url(term, statute=True)

    # Rules (and any unrecognised statute)
    if effective_provider == "lexis":
        return _build_lexis_search_url(cite["key"])
    return _build_westlaw_search_url(cite["key"], statute=False)


# ────────────────────────────────────────────────────────────────────────────
# OCR helpers
# ────────────────────────────────────────────────────────────────────────────
def _find_tesseract():
    """Locate tesseract.exe; return path string or None."""
    # Check PATH first
    import shutil
    path_hit = shutil.which("tesseract")
    if path_hit:
        return path_hit
    for cand in TESSERACT_CANDIDATES:
        if cand and cand.exists():
            return str(cand)
    return None


def _ocr_pdf(doc, log):
    """OCR pages of a PyMuPDF doc that have no text. Adds an invisible text
    layer using the recognised text. Modifies doc in place."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        log.warning("pytesseract or Pillow not installed - skipping OCR")
        return False

    tess = _find_tesseract()
    if not tess:
        log.warning("Tesseract not found - skipping OCR. Install from "
                    "https://github.com/UB-Mannheim/tesseract/wiki")
        return False
    pytesseract.pytesseract.tesseract_cmd = tess

    import io

    ocr_count = 0
    for page in doc:
        # Only OCR if page has no text
        if page.get_text("text").strip():
            continue
        # Render page to image
        pix = page.get_pixmap(dpi=300)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        # OCR to hOCR for positioning
        try:
            hocr = pytesseract.image_to_pdf_or_hocr(img, extension="pdf")
        except Exception as e:
            log.warning(f"  OCR failed on page {page.number}: {e}")
            continue
        # Overlay OCR'd PDF page on top to add text layer
        try:
            import fitz
            ocr_doc = fitz.open(stream=hocr, filetype="pdf")
            page.show_pdf_page(page.rect, ocr_doc, 0, overlay=True)
            ocr_doc.close()
            ocr_count += 1
        except Exception as e:
            log.warning(f"  Could not overlay OCR text on page {page.number}: {e}")

    if ocr_count:
        log.info(f"  OCR'd {ocr_count} page(s)")
    return ocr_count > 0


# ────────────────────────────────────────────────────────────────────────────
# Files that should be skipped for hyperlink insertion
# ────────────────────────────────────────────────────────────────────────────
# Declarations and separate statements rarely contain citations worth linking
# (they're factual recitations or ruling-by-ruling responses), and Zachary's
# workflow doesn't benefit from links there. The right-margin marker
# injection still runs on these files — that's the citation-paste aid the
# Word macro relies on, separate from the link annotations — but the
# case/statute hyperlink insertion is skipped entirely.
#
# Match is case-insensitive against the filename stem (no extension), with
# spaces and underscores treated equivalently. Patterns must appear as a
# whole token or sequence so partial words ("Declaratory", "Decline") don't
# fire.
_SKIP_LINK_PATTERNS = [
    re.compile(r"(?:^|[\s_-])Declaration(?:[\s_-]|$)", re.IGNORECASE),
    re.compile(r"(?:^|[\s_-])Decl\.?(?:[\s_-]|$)", re.IGNORECASE),
    re.compile(r"(?:^|[\s_-])Separate[\s_-]+Statement(?:[\s_-]|$)", re.IGNORECASE),
    re.compile(r"(?:^|[\s_-])Compl\.?(?:[\s_-]|$)", re.IGNORECASE),
    re.compile(r"(?:^|[\s_-])Complaint(?:[\s_-]|$)", re.IGNORECASE),
    re.compile(r"(?:^|[\s_-])FAC(?:[\s_-]|$)", re.IGNORECASE),
    re.compile(r"(?:^|[\s_-])SAC(?:[\s_-]|$)", re.IGNORECASE),
    re.compile(r"(?:^|[\s_-])TAC(?:[\s_-]|$)", re.IGNORECASE),
    re.compile(r"(?:^|[\s_-])Proof[\s_-]+of[\s_-]+Service(?:[\s_-]|$)", re.IGNORECASE),
]


def should_skip_linking(filename: str) -> bool:
    """Return True if this filename indicates a doc type we don't link."""
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    for pat in _SKIP_LINK_PATTERNS:
        if pat.search(stem):
            return True
    return False


def derive_doc_shortname(filename: str) -> str:
    """Derive a citation-friendly short name from a PDF filename.
    
    Examples:
        Britton_Decl__ISO_MSJ.pdf      -> "Britton Decl."
        Kelley_Decl__ISO_Mot_.pdf      -> "Kelley Decl."
        Opposition.pdf                 -> "Opposition"
        Joint_Separate_Statement.pdf   -> "Joint Separate Statement"
    
    Strips "ISO ..." suffix common in declaration filenames, replaces
    underscores with spaces, normalises whitespace, and adds a trailing
    period to "Decl"-style abbreviations so the resulting string is
    suitable for direct use in a Bluebook/CSM citation.
    """
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    stem = re.sub(r"[_ ]ISO[_ ].+$", "", stem, flags=re.IGNORECASE)
    s = re.sub(r"_+", " ", stem).strip()
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" _-")
    if re.search(r"\bDecl$", s):
        s += "."
    return s


def _detect_line_anchors(page):
    """Per-page: find pleading-paper line numbers and gather body text on
    each numbered row.
    
    Returns list of {line_num, body_text} for each row that has both a
    line number in the gutter and body text in the same horizontal band.
    Returns [] if the page lacks a recognisable pleading-paper line-number
    column (e.g. exhibits, signature pages, cover sheets without lines).
    """
    from collections import Counter, defaultdict
    blocks = page.get_text("dict")["blocks"]
    
    # Step 1: find spans whose text is a small integer (1-30) on the left
    # third of the page. These are line-number candidates.
    line_spans = []
    for b in blocks:
        if "lines" not in b:
            continue
        for ln in b["lines"]:
            for sp in ln["spans"]:
                t = sp["text"].strip()
                if (re.fullmatch(r"\d{1,2}", t) and 1 <= int(t) <= 30
                        and sp["bbox"][0] < page.rect.width / 3):
                    line_spans.append({
                        "num": int(t),
                        "y_mid": (sp["bbox"][1] + sp["bbox"][3]) / 2,
                        "x0": sp["bbox"][0],
                    })
    if not line_spans:
        return []
    
    # Step 2: cluster by x to find the dominant line-number column.
    x_buckets = Counter(round(s["x0"] / 5) * 5 for s in line_spans)
    dominant_x = x_buckets.most_common(1)[0][0]
    line_col = [s for s in line_spans if abs(s["x0"] - dominant_x) < 8]
    if len(line_col) < 5:
        # Fewer than 5 line numbers: probably a caption page or similar
        # - not a real pleading-paper page.
        return []
    
    # Step 3: collect body-text spans (anything to the right of the
    # line-number column with a gap), bucketed by rounded y-midpoint.
    body_x_min = dominant_x + 20
    body_spans_by_y = defaultdict(list)
    for b in blocks:
        if "lines" not in b:
            continue
        for ln in b["lines"]:
            for sp in ln["spans"]:
                if not sp["text"].strip():
                    continue
                if sp["bbox"][0] < body_x_min:
                    continue
                y_mid = (sp["bbox"][1] + sp["bbox"][3]) / 2
                body_spans_by_y[round(y_mid)].append(sp)
    
    # Step 4: for each gutter line number, find the body-text row whose
    # rounded y_mid is CLOSEST, then assign each body row to at most one
    # gutter line (smallest distance wins; ties go to the lower line number).
    # A fixed ±8pt window was too tight: on some pleading-paper PDFs the gutter
    # digit bbox y_mid and body text bbox y_mid differ by up to ~12pt on the
    # same physical row (different cap-height / descender geometry), causing
    # every case-section line to miss. A larger window catches two adjacent rows
    # simultaneously, so we use nearest-neighbour with a 24pt ceiling instead.
    candidate_map = {}  # gutter line_num -> (best_y_key, best_diff)
    for lnd in sorted(line_col, key=lambda l: l["num"]):
        best_y_key = None
        best_diff = float("inf")
        for y_key in body_spans_by_y:
            diff = abs(y_key - lnd["y_mid"])
            if diff < best_diff:
                best_diff = diff
                best_y_key = y_key
        if best_y_key is not None and best_diff <= 24:
            candidate_map[lnd["num"]] = (best_y_key, best_diff)

    # Resolve conflicts: each body y_key -> single gutter line (smallest diff).
    claimed: dict = {}  # body y_key -> (gutter_num, diff)
    for g_num, (y_key, diff) in sorted(candidate_map.items()):
        if y_key not in claimed or diff < claimed[y_key][1]:
            claimed[y_key] = (g_num, diff)

    lnd_by_num = {lnd["num"]: lnd for lnd in line_col}

    results = []
    for y_key, (g_num, _) in sorted(claimed.items(),
                                    key=lambda kv: lnd_by_num[kv[1][0]]["num"]):
        lnd = lnd_by_num[g_num]
        spans_at_y = body_spans_by_y[y_key]
        if not spans_at_y:
            continue
        spans_at_y.sort(key=lambda s: s["bbox"][0])
        body_text = "".join(s["text"] for s in spans_at_y).strip()
        if not body_text:
            continue
        results.append({
            "line_num": lnd["num"],
            "body_text": body_text,
            "y_mid": lnd["y_mid"],
        })
    return results


def _annotate_paragraphs(anchors):
    """For each line, detect numbered-paragraph starts (1., 2., 3., ...) and
    forward-fill the active paragraph number to subsequent lines on the page.

    A page is treated as declaration-style only if it contains AT LEAST 3
    sequential paragraph starts (e.g. 1., 2., 3., or 4., 5., 6.). Pages with
    fewer paragraph starts (or non-sequential ones) get paragraph_num = None
    on every line — this avoids tagging an isolated "7." inside body text on
    a page that isn't actually a declaration body page.

    For declaration-style pages, every line within paragraph N carries
    paragraph_num = N (not just the line where N starts), so a paste from
    the middle of a paragraph still surfaces the paragraph reference for
    citation purposes.

    The ``starts_paragraph`` flag is also added: True on the line where the
    paragraph starts, False on continuation lines.
    """
    # First pass: find candidate paragraph-start lines and strip the leading
    # "N. " prefix into a separate field. Heuristic guard: only treat N. as
    # a paragraph start if 1 <= N <= 99 AND the next char is uppercase
    # (filters out "7." appearing mid-sentence).
    candidates = []  # list of (anchor_index, paragraph_num)
    for i, a in enumerate(anchors):
        m = re.match(r"^(\d{1,3})\.\s*(.*)$", a["body_text"])
        if m:
            num = int(m.group(1))
            rest = m.group(2)
            if 1 <= num <= 99 and rest and rest[0].isupper():
                candidates.append((i, num, rest))

    # Determine whether this page qualifies as declaration-style: need 3+
    # paragraph starts in strictly increasing sequence (need not be
    # contiguous integers — page might start mid-doc at 4., 5., 6. — but
    # must be monotonically increasing).
    qualifies = False
    if len(candidates) >= 3:
        nums = [c[1] for c in candidates]
        if all(nums[k] < nums[k + 1] for k in range(len(nums) - 1)):
            qualifies = True

    # Initialise all anchors with no paragraph context.
    for a in anchors:
        a["paragraph_num"] = None
        a["starts_paragraph"] = False

    if not qualifies:
        return anchors

    # Apply paragraph numbers: at each candidate index, strip the leading
    # "N." from body_text and set starts_paragraph; then forward-fill
    # paragraph_num to every subsequent anchor until the next candidate.
    candidate_indices = {c[0]: (c[1], c[2]) for c in candidates}
    active = None
    for i, a in enumerate(anchors):
        if i in candidate_indices:
            num, rest = candidate_indices[i]
            a["paragraph_num"] = num
            a["body_text"] = rest
            a["starts_paragraph"] = True
            active = num
        elif active is not None:
            a["paragraph_num"] = active
    return anchors


# ────────────────────────────────────────────────────────────────────────────
# Right-margin invisible markers (for the PasteLegalQuotation macro)
# ────────────────────────────────────────────────────────────────────────────
# For each detected pleading-paper line, we insert a tiny white-on-white text
# string into the right margin at the same vertical baseline. The markers are
# invisible to the eye, but when Zachary drag-selects a line of body text,
# Adobe Reader's selection rectangle naturally extends to the right across
# the full row band — so the marker gets included in the clipboard text.
# His PasteLegalQuotation macro then strips the markers and uses them to
# auto-generate the citation in his preferred "(Doc. at p. X:Y-Z.)" format.
#
# Why this works where the previous (v1-v10) inline-marker attempts failed:
#   - We're adding NEW text in empty whitespace (right margin), not splicing
#     into existing BT/ET blocks. PyMuPDF's insert_text handles all the
#     positioning math for us — no Td displacement to compute.
#   - White text in the margin doesn't anti-alias against any visible pixels,
#     so there's no grey halo. The right margin is empty whitespace.
#   - No edit-mode dependency. Markers extract correctly in normal Reader
#     mode because Reader's drag-select uses a rectangular band that
#     captures every text element in the row.
#
# Trade-off: partial selections that don't reach the right margin won't
# capture a marker. Per Zachary, that's acceptable — he can do a full-line
# (or longer) drag-select when he wants the auto-citation, and skip it
# otherwise. The visible cue is the selection rectangle extending into the
# margin, which he doesn't mind.

# ── Marker configuration ────────────────────────────────────────────────────
_MARKER_FONT_SIZE = 4.0
_MARKER_CHAR_WIDTH_EST = _MARKER_FONT_SIZE * 0.55
_MARKER_RIGHT_INSET = 2.0
# Place the marker baseline near the TOP of its line band so that in
# GEOMETRIC reading order (used by Acrobat's rectangle / column select)
# the marker sits above the body-text baseline on the same row.
# Pleading-paper lines are ~14pt tall; y_mid is the gutter digit centre.
# Subtracting 6.5pt from y_mid puts the marker baseline ~0.5pt below the
# top of the band — visually in the right margin, geometrically first in row.
# IMPORTANT: selection must be done with Acrobat's column/rectangle select
# (Alt+drag), not the normal I-beam text-select, because insert_text()
# appends markers to the PDF content stream after all body text.  For a
# rectangular selection Acrobat uses visual geometry (correct order); for a
# normal text-flow selection it uses stream order (wrong order).
_MARKER_TOP_OFFSET = -6.5   # subtract from y_mid to reach near line-band top

# Regex matching the exact marker formats produced below — used by
# _insert_right_margin_markers to detect existing markers on a page and
# skip re-insertion across reruns. Must match BOTH the full form
# "[ShortName|p3:7¶4]" and the compact form "[p3:7¶4]"; the paragraph
# suffix is optional. The character class for the shortname is the same
# as what derive_doc_shortname can produce: letters, digits, and a few
# punctuation characters. Anchored on the bracketed "p<digits>:<digits>"
# core which is distinctive enough that no real body text would match.
_MARKER_DETECT_RE = re.compile(
    r"\[(?:[A-Za-z0-9_.&'\- ]+\|)?p\d+:\d+(?:\u00b6\d+)?\]"
)


def _insert_right_margin_markers(page, anchors, shortname, page_num, log=None):
    """Insert one invisible white right-margin marker per anchor.

    ``page_num`` is the page label to embed in each marker — resolved by
    the caller from the printed footer page number where available, else
    the PDF page index. It is a string so printed labels pass through
    verbatim. The marker format stays ``[ShortName|p<page>:<line>¶<para>]``
    so the PasteLegalCitation Word macro and the idempotency detector are
    unaffected by the change in what the page number *means*.

    Returns the number of markers actually inserted.

    Markers are placed at the right edge of the page.  Use Acrobat's
    rectangle / column select (Alt+drag) — not the normal I-beam — to
    capture them together with the body text: rectangle select respects
    visual geometry and therefore picks up the marker in the correct row
    order regardless of its position in the PDF content stream.

    Idempotency: if any existing marker (matching _MARKER_DETECT_RE) is
    already present on the page, the entire pass is skipped for that
    page. Without this guard, each rerun would stack a fresh set of
    markers on top of the previous ones, doubling the count per run and
    inflating the file size. Single-marker detection is enough because
    markers are inserted as a batch per page — if one is present, all
    are; if none is present, the page hasn't been processed yet.
    """
    # Idempotency check: scan existing text for any marker-shaped string.
    page_text = page.get_text("text")
    if _MARKER_DETECT_RE.search(page_text):
        return 0

    page_width = page.rect.width
    inserted = 0
    for a in anchors:
        line_num = a["line_num"]
        para = a.get("paragraph_num")

        para_suffix = f"\u00b6{para}" if para is not None else ""
        full_marker    = f"[{shortname}|p{page_num}:{line_num}{para_suffix}]"
        compact_marker = f"[p{page_num}:{line_num}{para_suffix}]"

        available_width = 60.0
        marker_text = (full_marker
                       if len(full_marker) * _MARKER_CHAR_WIDTH_EST <= available_width
                       else compact_marker)

        marker_width_est = len(marker_text) * _MARKER_CHAR_WIDTH_EST
        marker_x = page_width - _MARKER_RIGHT_INSET - marker_width_est
        if marker_x < page_width - 80:
            marker_x = page_width - 80

        # Baseline near the TOP of the line band (see _MARKER_TOP_OFFSET note).
        marker_y = a["y_mid"] + _MARKER_TOP_OFFSET

        try:
            page.insert_text(
                (marker_x, marker_y),
                marker_text,
                fontname="helv",
                fontsize=_MARKER_FONT_SIZE,
                color=(1.0, 1.0, 1.0),
            )
            inserted += 1
        except Exception as e:
            if log:
                log.warning(f"  Marker insert failed on p{page_num}:{line_num}: {e}")
    return inserted


def _marker_page_numbers(doc):
    """Resolve the page number to embed in each pleading page's markers.

    Returns {pdf_page_index: (page_number_str, used_printed_bool)} for
    every page that carries pleading-paper line numbers.

    Resolution per page:
      * If the page has a printed footer page number (arabic), use it.
        A court cites the printed page, so the stamped number is always
        authoritative. Only arabic labels are accepted: the marker format
        and the PasteLegalCitation macro expect ``p<digits>``, and roman
        front-matter labels (i, ii) would break the idempotency
        detector's ``p\\d+:\\d+`` core.
      * Otherwise fall back to the page's ORDINAL POSITION within its
        contiguous run of pleading pages, not the raw PDF page index.
        Runs are separated by non-pleading pages (declaration/section
        divider sheets, exhibit covers, signature-only pages), so a gap
        in pleading pages marks a new sub-document. This is what makes a
        declaration that omits printed page numbers (common — e.g. an
        attorney declaration filed without footer pagination) still get
        per-declaration page numbers 1, 2, 3 … instead of the PDF's
        global index.

    A printed number RESYNCHRONISES the running counter (``within`` is
    set to the printed value), so when a declaration prints numbers on
    most pages but omits one, the omitted page continues the printed
    sequence rather than drifting. It also corrects for an unnumbered
    caption/first page that isn't itself a pleading page: the first
    pleading page starts the count at 1, and the first printed number
    snaps it to the true value.
    """
    result = {}
    prev_idx = None
    within = 0
    for page in doc:
        if not _detect_line_anchors(page):
            continue  # caption / divider / exhibit / signature page — a gap
        # New run (first pleading page, or a gap since the previous one).
        if prev_idx is None or page.number != prev_idx + 1:
            within = 1
        else:
            within += 1
        prev_idx = page.number

        label = _footer_page_label(page)
        if label and label.isdigit():
            within = int(label)              # resync to the printed page
            result[page.number] = (label, True)
        else:
            result[page.number] = (str(within), False)
    return result


def add_right_margin_markers(pdf_path: Path, doc, log: logging.Logger):
    """Add invisible right-margin markers to every pleading-paper page in
    the open doc. Operates on the doc in-memory; caller is responsible
    for saving.

    Each marker's page number is the *printed footer page number* for
    that page when one is stamped (so a pinpoint citation pasted via the
    Word macro reads the page a court cites, e.g. "Decl. p. 3 ¶ 4"). When
    a page has no printed number, the page's position within its
    declaration/sub-document is used instead (see _marker_page_numbers),
    so unnumbered declarations still get 1, 2, 3 … rather than the PDF's
    global page index. Declaration pages keep their paragraph suffix (¶N).

    Returns (total_markers, paragraph_anchors) where paragraph_anchors is
    a list of (page_index, paragraph_num) tuples — one per page on which
    at least one *new* paragraph starts, recording the lowest paragraph
    number that begins on that page. Used by the bookmark builder to
    produce the "Paragraphs" branch; documents without pleading-paper
    line numbers (briefs, often) yield no anchors.
    """
    shortname = derive_doc_shortname(pdf_path.name)
    page_numbers = _marker_page_numbers(doc)
    total = 0
    pages_with_markers = 0
    positional_pages = 0  # inserted pages numbered by position (no printed #)
    paragraph_anchors = []  # [(page_index, paragraph_num), ...]
    for page in doc:
        anchors = _detect_line_anchors(page)
        if not anchors:
            continue  # caption / exhibit / signature page
        anchors = _annotate_paragraphs(anchors)
        # Capture the lowest paragraph number that *starts* on this page,
        # if any. Continuation pages where every line is mid-paragraph
        # (no starts_paragraph=True) produce no entry, so a paragraph
        # spanning three pages adds only one bookmark instead of three.
        starts = [a.get("paragraph_num") for a in anchors
                  if a.get("starts_paragraph") and a.get("paragraph_num")]
        if starts:
            paragraph_anchors.append((page.number, min(starts)))

        page_num, used_printed = page_numbers.get(
            page.number, (str(page.number + 1), False))

        n = _insert_right_margin_markers(page, anchors, shortname, page_num, log)
        total += n
        if n:
            pages_with_markers += 1
            if not used_printed:
                positional_pages += 1
    if total:
        log.info(f"  Inserted {total} invisible markers across "
                 f"{pages_with_markers} page(s)")
        if positional_pages:
            log.info(f"  {positional_pages} marked page(s) had no printed "
                     f"page number; numbered by position within their "
                     f"sub-document")
    return total, paragraph_anchors


# ────────────────────────────────────────────────────────────────────────────
# Safe citation-text search (multi-line aware, no spurious wide matches)
# ────────────────────────────────────────────────────────────────────────────
# Minimum length for a search-for fragment to be considered "safe" — anything
# shorter risks matching tons of unrelated locations. "Cal." (4 chars) is the
# canonical example of an unsafe short fragment.
_MIN_FRAG_LEN = 12

# Generic substrings that, even if longer than _MIN_FRAG_LEN, appear too often
# in legal documents to be safe link targets on their own. We require a
# fragment to contain something *more* than these to be linkable.
# The patterns capture: California reporter abbreviations alone or with an
# ordinal ("Cal. App. 4th"), plus generic connector words. A safe fragment
# must contain content beyond these.
_GENERIC_FRAG_RE = re.compile(
    r"^(?:"
    r"Cal\.(?:\s*(?:App|Rptr))?\.?(?:\s*\d?(?:st|nd|rd|th|d))?"
    r"|U\.S\."
    r"|F\.\s*Supp\.(?:\s*\d?d)?"
    r"|F\.\s*\d?d"
    r"|the(?:\s+\w+)?"
    r"|see(?:\s+\w+)?"
    r"|in\s+re"
    r")\s*\d*\s*$",
    re.IGNORECASE,
)


def _is_safe_fragment(s: str) -> bool:
    """Return True if `s` is distinctive enough to use as a search target.

    A fragment is unsafe if it's too short to be unique, or if it consists
    only of reporter abbreviations and generic words. Both conditions
    matter: "Cal. App. 4th" is 13 chars (long enough) but matches every
    case in a TOA. "Smith" is distinctive but only 5 chars — likely too
    common as a name. We pair the length check with a generic-pattern check.
    """
    s = s.strip()
    if len(s) < _MIN_FRAG_LEN:
        return False
    if _GENERIC_FRAG_RE.match(s):
        return False
    return True


def _merge_quads_by_line(quads, *, require_x_adjacent: bool = False):
    """Merge a list of fitz.Quad into one quad per text-line.

    PyMuPDF's `Page.search_for` can return multiple per-word quads for a
    single match:
      - On phrases containing `\\n`, justified-text spacing sometimes
        causes per-word splitting on a line (e.g., "Intengan v. BAC
        Home Loans..." → one quad per word).
      - Even on single-line phrases, superscript glyphs like the "th"
        in "Cal.4th" come back as a separate quad with a slightly
        different y-range and font.

    Drawing an underline per quad makes one citation look like several
    disjoint underlined fragments. This helper groups quads by y-band
    (same logical line) and emits one merged quad per line, spanning
    min(x0) to max(x1).

    Args:
      quads: input quads from `page.search_for`.
      require_x_adjacent: when True, only merge quads on the same line
        if they are horizontally contiguous (x-gap < ~5pt). This is the
        safer mode for single-line searches, where multiple separate
        occurrences of a short phrase on one line must remain distinct.
        For multi-line searches, the same-line word-splits are always
        contiguous parts of one match, so this flag can be left False.
    """
    if not quads:
        return quads
    import fitz
    LINE_TOL = 4.0    # pt — quads on the same line are within ~4pt vertically
    X_GAP_TOL = 6.0   # pt — horizontally adjacent if x-gap is at most this

    # Sort by y-center then x to make line-grouping a linear scan.
    sorted_q = sorted(quads, key=lambda q: ((q.rect.y0 + q.rect.y1) / 2,
                                            q.rect.x0))
    groups = []  # list of list[Quad]
    for q in sorted_q:
        y_mid = (q.rect.y0 + q.rect.y1) / 2
        if groups:
            last_grp = groups[-1]
            last_y = (last_grp[0].rect.y0 + last_grp[0].rect.y1) / 2
            same_line = abs(y_mid - last_y) <= LINE_TOL
            if same_line and require_x_adjacent:
                # Also require horizontal adjacency to the previous quad
                # in this group — guards against two separate occurrences
                # of a short phrase on the same physical line.
                prev_x1 = max(qq.rect.x1 for qq in last_grp)
                if q.rect.x0 - prev_x1 > X_GAP_TOL:
                    same_line = False
            if same_line:
                last_grp.append(q)
                continue
        groups.append([q])

    merged = []
    for grp in groups:
        x0 = min(q.rect.x0 for q in grp)
        y0 = min(q.rect.y0 for q in grp)
        x1 = max(q.rect.x1 for q in grp)
        y1 = max(q.rect.y1 for q in grp)
        merged.append(fitz.Rect(x0, y0, x1, y1).quad)
    return merged


def _statute_section_token(cite):
    """Return the disambiguating section token for a statute cite, else None.

    For a statute the code name ("Code of Civil Procedure") is shared by
    every section of that code, so it is NOT distinctive — the section
    number is. Callers use this token to refuse anchoring a link on a bare
    code-name fragment. Returns the leading numeric part of the section
    (e.g. "430.10" from key "CCP § 430.10(a)", "1010.6" from
    "CCP § 1010.6", "1983" from "42 U.S.C. § 1983"); None for non-statutes.
    """
    if not cite or cite.get("kind") != "statute":
        return None
    m = re.search(r"§\s*(\d+(?:\.\d+)?)", cite.get("key", ""))
    return m.group(1) if m else None


def _safe_search_for_citation(page, match_text: str, cite=None):
    """Locate the citation `match_text` on `page`, handling multi-line wraps
    safely. Returns a list of fitz.Quad covering the citation's glyphs, or
    an empty list if not safely locatable.

    Strategy:
      1. Try the full match_text. If found, return its quads.
      2. If match_text spans multiple lines (contains \\n), split into
         fragments at line breaks. For each fragment that passes
         `_is_safe_fragment`, search the page. We require fragments to
         appear in vertically-adjacent positions on the page (within ~3
         lines of each other) so a TOA "Smith" plus an unrelated body
         "Smith" don't get linked together.
      3. If no fragment is safe, return [] — better to miss a link than to
         spray hyperlinks across unrelated text.

    `cite` (optional) lets statute citations be matched safely: the code
    name alone is not distinctive (every section shares it), so when a
    wrapped statute citation falls back to fragments, only a fragment that
    carries the section number may anchor the link.
    """
    section_token = _statute_section_token(cite)
    # Step 1: full text search
    quads = page.search_for(match_text, quads=True)
    if quads:
        # PyMuPDF may return multiple per-word/per-glyph quads for a
        # single match — driven by justified-text spacing (multi-line)
        # or superscripts like the "th" in "Cal.4th" (single-line).
        # Merging them produces a single rect per text-line so the
        # underline draws as one continuous span. For single-line
        # searches we additionally require x-adjacency so two distinct
        # occurrences of the same short phrase on one line don't get
        # accidentally fused into one mega-rect.
        is_multiline = "\n" in match_text
        quads = _merge_quads_by_line(quads,
                                     require_x_adjacent=not is_multiline)
        return quads

    # Step 2: multi-line splitting
    if "\n" not in match_text:
        return []
    fragments = [f.strip() for f in match_text.splitlines() if f.strip()]
    safe_frags = [f for f in fragments if _is_safe_fragment(f)]
    if not safe_frags:
        return []

    # Search each safe fragment, then group adjacent results.
    fragment_hits = []  # list of (fragment, quads)
    for frag in safe_frags:
        fq = page.search_for(frag, quads=True)
        if fq:
            fragment_hits.append((frag, fq))
    if not fragment_hits:
        return []

    # Statute guard: a section-bearing fragment must actually be present on
    # this page. If only code-name fragments were found, the citation isn't
    # really here (just a mention of the same code for a different section),
    # so linking would point at the wrong section. Covers both the single-
    # and multi-fragment branches below (e.g. a code name that wraps across
    # several lines while the section sits on its own short line).
    if section_token is not None and not any(
        section_token in f for f, _ in fragment_hits
    ):
        return []

    # If only one fragment is safely findable, decide whether it is
    # distinctive enough to anchor the link by itself.
    #
    # For a STATUTE the code name is never distinctive on its own. A
    # citation that wraps a line — e.g. "Code of Civil Procedure\nsection
    # 430.10" — splits into a code-name fragment ("Code of Civil Procedure")
    # and a section fragment ("section 430.10"). On a page that cites a
    # *different* section of the same code ("Code of Civil Procedure
    # § 1161(2)", or "...§ 1010.6"), only the generic code-name fragment is
    # present. Anchoring on it would attach THIS citation's URL (§ 430.10) to
    # a span that is really a different citation, so the reader clicks
    # "...§ 1161(2)" and lands on § 430.10. We therefore require the lone
    # fragment to carry the section number; a bare code name links nothing,
    # and the citation is picked up wherever its section actually appears
    # (via the full-text search in step 1 or the multi-fragment branch).
    #
    # For non-statutes the original rule stands: the fragment must be
    # >= 20 chars and identify exactly one location on the page.
    if len(fragment_hits) == 1:
        frag, fq = fragment_hits[0]
        if len(page.search_for(frag)) != 1:
            return []
        if section_token is not None:
            return fq if section_token in frag else []
        if len(frag) >= 20:
            return fq
        return []

    # Multiple fragments found: only keep quads from each fragment that
    # have a peer fragment-quad within 3 line-heights. This rejects cases
    # where one fragment matches in an unrelated place on the page.
    LINE_H_TOL = 60  # ~3 lines at 20pt
    out_quads = []
    for i, (_, fq) in enumerate(fragment_hits):
        for q in fq:
            y_mid = (q.rect.y0 + q.rect.y1) / 2
            paired = False
            for j, (_, fq2) in enumerate(fragment_hits):
                if j == i:
                    continue
                for q2 in fq2:
                    y2 = (q2.rect.y0 + q2.rect.y1) / 2
                    if abs(y_mid - y2) <= LINE_H_TOL:
                        paired = True
                        break
                if paired:
                    break
            if paired:
                out_quads.append(q)
    return out_quads


# ────────────────────────────────────────────────────────────────────────────
# Short-form case linking (second pass)
# ────────────────────────────────────────────────────────────────────────────
# Match a bare "X v. Y" (or "X v. Y, Inc." etc.) — no reporter, no year.
# Used in the second pass after full citations are linked, to also link
# subsequent shorter mentions of cases already cited in long form.
# Plaintiff: must start uppercase, allow internal letters/digits/'-./&.
# Defendant: same, plus permit a comma and a corporate suffix like ", Inc."
# We deliberately keep this conservative — only sequences that look like
# party-v-party, with no surrounding reporter/year, qualify. Limited to
# 1-4 tokens on each side to avoid runaway matches.
_PARTY_TOKEN = r"[A-Z][A-Za-z0-9.\-'&]*"
_SHORT_FORM_RE = re.compile(
    rf"\b({_PARTY_TOKEN}(?:\s+{_PARTY_TOKEN}){{0,3}})\s+v\.\s+"
    rf"({_PARTY_TOKEN}(?:\s+{_PARTY_TOKEN}){{0,4}}(?:,\s*(?:Inc|LLC|LLP|Ltd|Corp|Co)\.?)?)"
)

# Leading words to strip from a short-form plaintiff capture. These are
# common when a brief introduces a case — "In Smith v. Jones, ..." or
# "See Smith v. Jones, ..." — and would otherwise pollute the registry
# lookup. Mirrors the SIGNAL_PREFIXES set used by `_walk_back_for_name`.
_SHORTFORM_LEAD_RE = re.compile(
    r"^(?:In|See|Cf|Cf\.|Compare|Accord|But|Following|"
    r"Per|Under|Like|Citing|Quoting)\s+",
    re.IGNORECASE,
)


def _normalize_party(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    s = re.sub(r"[.,;:'\"]", "", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _link_short_form_cases(doc, full_cites,
                           provider: str, log: logging.Logger) -> int:
    """For each full case citation already matched, also link bare
    "X v. Y" mentions of the same case elsewhere in the document.

    Returns the number of additional citation occurrences linked.
    """
    try:
        import fitz
    except ImportError:
        return 0

    # Build a registry of (plaintiff_norm, defendant_norm) -> URL from
    # full citations. We extract plaintiff/defendant from the case key
    # ("Plaintiff v. Defendant (year) ..." or "... 2023 WL ...").
    registry = {}  # (plaintiff_norm, defendant_norm) -> (key, url, full_match)
    case_key_re = re.compile(r"^(.+?)\s+v\.\s+(.+?)\s+(?:\(\d{4}\)|\d{4}\s+WL)\b")
    for c in full_cites:
        if c.get("kind") != "case":
            continue
        url = resolve_url(c, provider)
        if not url:
            continue
        m = case_key_re.match(c["key"])
        if not m:
            continue
        p_norm = _normalize_party(m.group(1))
        d_norm = _normalize_party(m.group(2))
        if not p_norm or not d_norm:
            continue
        # First-seen wins (later identical references resolve to same URL anyway)
        registry.setdefault((p_norm, d_norm), (c["key"], url, c["match_text"]))

    if not registry:
        return 0

    extra_links = 0
    # Track spans we've already annotated (per page) to avoid double-linking
    # a span that was already linked in the main pass.
    for page in doc:
        text = page.get_text("text")
        # Find all bare X v. Y patterns on this page
        for m in _SHORT_FORM_RE.finditer(text):
            plaintiff_raw = m.group(1).strip()
            defendant = m.group(2).strip()
            # Strip leading signal/connector words ("In", "See", "Following"
            # etc.) so the normalized plaintiff matches the registry.
            plaintiff = _SHORTFORM_LEAD_RE.sub("", plaintiff_raw).strip()
            if not plaintiff:
                continue
            p_norm = _normalize_party(plaintiff)
            d_norm = _normalize_party(defendant)

            # Try exact (plaintiff, defendant) match first; then a relaxed
            # match where the short defendant is a prefix of the registered
            # one (e.g. short "Ford" matches registered "Ford Motor Co.").
            url = None
            if (p_norm, d_norm) in registry:
                _, url, _full = registry[(p_norm, d_norm)]
            else:
                for (rp, rd), (_k, ru, _ft) in registry.items():
                    if rp == p_norm and (rd.startswith(d_norm) or d_norm.startswith(rd)):
                        url = ru
                        break
            if not url:
                continue

            # Locate this bare reference on the page. We use the cleaned
            # case-name portion (without any leading "In"/"See"/etc.) so
            # the highlight covers only "Plaintiff v. Defendant", not the
            # connecting word that precedes it.
            snippet = f"{plaintiff} v. {defendant}"
            quads = page.search_for(snippet, quads=True)
            if not quads:
                continue

            # If the matched span overlaps a span already covered by a full
            # citation's annotations, skip — the full citation's link is
            # already there. We approximate "already covered" by checking
            # whether the rect overlaps any existing link annotation.
            existing_links = page.get_links()
            for q in quads:
                rect = q.rect
                already = False
                for el in existing_links:
                    er = el.get("from")
                    if er and rect.intersects(er):
                        # Substantial overlap means the span is already linked
                        # (probably as part of the full citation).
                        already = True
                        break
                if already:
                    continue
                if rect.x0 > page.rect.width - 90:
                    continue
                page.insert_link({
                    "kind": fitz.LINK_URI,
                    "from": rect,
                    "uri": url,
                })
                underline_y = rect.y1 - 0.5
                page.draw_line(
                    fitz.Point(rect.x0, underline_y),
                    fitz.Point(rect.x1, underline_y),
                    color=LINK_COLOUR,
                    width=1.0,
                )
                extra_links += 1

    if extra_links:
        log.info(f"  Linked {extra_links} short-form case reference(s)")
    return extra_links


# ────────────────────────────────────────────────────────────────────────────
# Table-of-Contents internal linking
# ────────────────────────────────────────────────────────────────────────────
# Detect a "Table of Contents" heading in the front matter and turn each
# entry into an internal jump to the page bearing that printed page number.
#
# Scope:
#   * Only the first TOC_SCAN_PAGES pages are searched for the *heading*.
#     This is a search budget to keep us out of the body of long briefs that
#     might mention "table of contents" in passing. Once the heading is
#     found, the TOC itself is walked to its natural end (terminator
#     heading or empty page) regardless of how many pages it spans.
#   * The "Table of Authorities" page is intentionally NOT processed here —
#     its entries are case/statute citations and the main citation-linking
#     pass already turns those into external Westlaw/Lexis links. A TOA
#     heading appearing after the TOC also acts as a TOC terminator.
#
# Page-number mapping:
#   The number printed on a TOC line ("3", "iii") is the page label the
#   author chose, not the PDF's underlying page index. A 2-page TOC after
#   a cover sheet means TOC's "1" might be PDF page index 3. We resolve
#   this by scanning each PDF page for a stamped page number in the top
#   or bottom margin band, building a {printed -> pdf_index} map, and
#   resolving each TOC entry through that map. Entries whose printed
#   number can't be found are left unlinked (better no link than wrong).
TOC_SCAN_PAGES = 5

_TOC_HEADING_RE = re.compile(
    r"\bT\s*A\s*B\s*L\s*E\s+O\s*F\s+C\s*O\s*N\s*T\s*E\s*N\s*T\s*S\b",
    re.IGNORECASE,
)

# Headings that end the TOC. Matching any of these on a line stops further
# entry collection on that page and prevents continuation onto later pages.
_TOC_END_RE = re.compile(
    r"\b("
    r"T\s*A\s*B\s*L\s*E\s+O\s*F\s+A\s*U\s*T\s*H\s*O\s*R\s*I\s*T\s*I\s*E\s*S"
    r"|INTRODUCTION"
    r"|STATEMENT\s+OF\s+(?:FACTS|THE\s+CASE)"
    r"|MEMORANDUM\s+OF\s+POINTS"
    r"|ARGUMENT(?!\s+(?:I|II|III|IV|V|\d))"   # bare "ARGUMENT" as a top-level section,
    r")\b",                                    # not a numbered subheading inside the TOC
    re.IGNORECASE,
)

# A TOC entry line: some label text, then either dot leaders or wide
# whitespace, then a trailing page number (arabic or roman). The label is
# kept non-greedy so the longest trailing token is the page number.
_TOC_ENTRY_RE = re.compile(
    r"""
    ^
    (?P<label>\S.*?\S)
    [\s\.]{2,}
    (?P<page>
        \d{1,4}
      | [ivxlcdm]{1,6}
      | [IVXLCDM]{1,6}
    )
    \s*$
    """,
    re.VERBOSE,
)

# A page-number stamp: a line that is *only* a page number (with optional
# decorations). Used to find the printed page label of each PDF page.
_PAGE_STAMP_RE = re.compile(
    r"""
    ^
    \s*
    (?:Page\s+|-\s*|—\s*)?
    (?P<num>\d{1,4} | [ivxlcdm]{1,6} | [IVXLCDM]{1,6})
    \s*
    (?:\s*-|\s*—|\.|\s+of\s+\d+)?
    \s*
    $
    """,
    re.VERBOSE,
)

# Margin band (in PDF points) within which a line qualifies as a page-number
# stamp. ~100pt covers the typical footer zone on pleading paper, where the
# printed page number often sits about an inch above the page edge — outside
# a strict 1-inch band but well above the bottom margin. The band is just a
# coarse filter; the candidate-ranking logic below disambiguates among
# multiple hits within the band.
_STAMP_BAND_PT = 100.0


def _collect_rows(page, y_tol: float = 4.0):
    """Return [(text, bbox)] for the page, grouping text runs that share a
    baseline. ReportLab and most pleading-paper layouts draw a TOC entry's
    label, dot leaders, and page number as separate text runs, which
    PyMuPDF returns as separate `lines` despite their visual co-location
    on one row. We merge runs whose y-center differs by no more than
    `y_tol` points and concatenate left-to-right with single spaces.

    The returned bbox is the union of the merged runs, which is what the
    TOC linker uses as the clickable rectangle.

    Marker runs (the invisible right-margin `[Demurrer|p1:2]`-style
    tags pdf_linker writes into its own output) are filtered out before
    grouping. Without this filter, a TOC entry like
    "TABLE OF AUTHORITIES ... ii" merges with the adjacent marker into
    "TABLE OF AUTHORITIES ... ii [Demurrer|p5:3]", which then fails
    `_TOC_ENTRY_RE`'s end-of-line page-number requirement — silently
    dropping every TOC entry on re-runs of an already-linked PDF.
    """
    try:
        d = page.get_text("dict")
    except Exception:
        return []
    runs = []  # (y_center, bbox, text)
    for block in d.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            bbox = line.get("bbox")
            if not bbox:
                continue
            text = "".join(
                span.get("text", "") for span in line.get("spans", [])
            ).strip()
            if not text:
                continue
            # Skip pdf_linker's own right-margin markers; otherwise they
            # contaminate merged rows on re-runs of an already-linked PDF.
            if _MARKER_DETECT_RE.fullmatch(text):
                continue
            y_center = (bbox[1] + bbox[3]) / 2
            runs.append((y_center, bbox, text))
    if not runs:
        return []
    runs.sort(key=lambda r: (r[0], r[1][0]))
    rows = []
    current = [runs[0]]
    for r in runs[1:]:
        if abs(r[0] - current[0][0]) <= y_tol:
            current.append(r)
        else:
            rows.append(current)
            current = [r]
    rows.append(current)
    merged = []
    for g in rows:
        g.sort(key=lambda r: r[1][0])
        text = " ".join(r[2] for r in g)
        x0 = min(r[1][0] for r in g)
        y0 = min(r[1][1] for r in g)
        x1 = max(r[1][2] for r in g)
        y1 = max(r[1][3] for r in g)
        merged.append((text, (x0, y0, x1, y1)))
    return merged


def _find_toc_heading(doc, max_pages: int):
    """Return the PDF page index containing a 'Table of Contents' heading,
    or None. Only the first `max_pages` pages are searched."""
    limit = min(max_pages, len(doc))
    for i in range(limit):
        text = doc[i].get_text("text")
        if _TOC_HEADING_RE.search(text):
            return i
    return None


def _build_printed_page_map(doc) -> dict:
    """Scan every page for a printed page-number stamp in the top or bottom
    margin band. Returns {printed_label_lower: [pdf_page_index, ...]}.

    The value is a list (not a single index) because reset numbering is
    common in briefs: the cover and notice section often carries arabic
    numbers 1-4, then TOA/TOC switches to roman i-iii, then the MPA
    restarts arabic from 1. A TOC entry "Introduction ... 1" targets the
    MPA's page 1, not the cover's page 1. Callers resolve the ambiguity
    with `_resolve_target`, which picks the first occurrence strictly
    after the TOC entry's own page (TOC entries always point forward).

    Algorithm per page:
      1. Walk merged rows from `_collect_rows`. A row whose entire text
         matches `_PAGE_STAMP_RE` is a candidate.
      2. Additionally scan per-line spans from `get_text("dict")` for
         span-level matches. This handles pleading paper where the
         left-margin line-number column (e.g., "28") shares a baseline
         with the centered page-number stamp (e.g., "i"); the row merger
         fuses them into "28 i", which no longer matches the stamp
         regex. The per-span pass recovers the legitimate stamp.
      3. Discard candidates whose horizontal center is far from page
         center (line-number-column matches). The legitimate stamp is
         essentially always centered or near-centered.
      4. Among remaining candidates, prefer (a) the bottom-most span
         (typical pleading footer), then (b) the span closest to
         horizontal page-center.
    """
    # Maximum horizontal distance from page center for a stamp candidate
    # to be considered legitimate. A real centered page-number stamp on
    # a letter-sized page sits within ~10pt of center; allow generous
    # slack for slightly off-center stamps and right-aligned footer
    # numbering. The pleading-paper line-number column sits 200+ pt
    # off-center and is reliably excluded.
    CENTER_TOL_PT = 120.0

    mapping: dict = {}  # label_lower -> [pdf_page_idx, ...] in document order
    for i, page in enumerate(doc):
        page_height = page.rect.height
        page_center_x = page.rect.width / 2
        candidates = []  # (y0, num_str, x_center)

        def _consider(text: str, bbox):
            y0, y1 = bbox[1], bbox[3]
            in_top = y1 <= _STAMP_BAND_PT
            in_bot = y0 >= page_height - _STAMP_BAND_PT
            if not (in_top or in_bot):
                return
            m = _PAGE_STAMP_RE.match(text)
            if not m:
                return
            x_center = (bbox[0] + bbox[2]) / 2
            if abs(x_center - page_center_x) > CENTER_TOL_PT:
                # Far from center: almost certainly a left-margin
                # line-number column entry, not a page stamp.
                return
            candidates.append((y0, m.group("num"), x_center))

        # Pass 1: whole-row matches via _collect_rows.
        for line_text, bbox in _collect_rows(page):
            _consider(line_text, bbox)

        # Pass 2: per-span fallback for column-collision rows. When the
        # line-number column shares a baseline with the centered page
        # stamp, _collect_rows merges them ("28 i") and Pass 1 misses
        # the stamp. Spans are individual atoms, so the stamp survives.
        try:
            raw = page.get_text("dict")
        except Exception:
            raw = {"blocks": []}
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    txt = span.get("text", "").strip()
                    if not txt:
                        continue
                    bbox = span.get("bbox")
                    if not bbox:
                        continue
                    _consider(txt, bbox)

        if not candidates:
            continue

        # Rank: bottom-most first (footers are the typical stamp
        # location), then closest to page center.
        candidates.sort(key=lambda c: (-c[0], abs(c[2] - page_center_x)))
        num = candidates[0][1]
        key = num.lower()
        mapping.setdefault(key, []).append(i)
    return mapping


def _footer_page_label(page, center_tol: float = 120.0):
    """Return the page number *printed* on this page (the "footer page
    number"), as a raw label string ("3", "ii"), or None if no centred
    page-number stamp is found.

    This is the per-page inverse of what `_build_printed_page_map`
    collects across the whole document: rather than {label -> [pages]},
    it answers "what page number does a reader see on THIS page?".
    Right-margin citation markers use it so a pasted pinpoint reference
    carries the page number a court actually cites — the printed page —
    instead of the PDF's physical page index.

    Detection mirrors `_build_printed_page_map` exactly (kept as a small
    standalone copy so the proven TOC-linking path is left untouched):
    scan merged rows and raw spans in the top/bottom margin band for a
    token that is *only* a page number (`_PAGE_STAMP_RE`); discard
    candidates far from horizontal centre (pleading-paper line-number
    column digits, right-margin Bates stamps); then prefer the
    bottom-most, most-centred candidate — i.e. the footer.

    Why per-page (not a running offset): in compiled filings — compendia,
    declaration bundles — page numbering restarts at every sub-document.
    Each declaration begins again at its own page 1/2/3, and a new
    exhibit typically switches scheme entirely (Bates numbers, "Page X of
    Y") or restarts. Reading each page's own stamp absorbs those resets
    for free: no counter is carried across pages, so a declaration or
    exhibit boundary can never desynchronise the count.

    The raw label is returned verbatim; the caller decides whether to
    accept non-arabic labels (the marker format and the Word macro expect
    arabic digits, so roman front-matter labels are declined upstream).
    """
    page_height = page.rect.height
    page_center_x = page.rect.width / 2
    candidates = []  # (y0, num_str, x_center)

    def _consider(text: str, bbox):
        y0, y1 = bbox[1], bbox[3]
        in_top = y1 <= _STAMP_BAND_PT
        in_bot = y0 >= page_height - _STAMP_BAND_PT
        if not (in_top or in_bot):
            return
        m = _PAGE_STAMP_RE.match(text)
        if not m:
            return
        x_center = (bbox[0] + bbox[2]) / 2
        if abs(x_center - page_center_x) > center_tol:
            return
        candidates.append((y0, m.group("num"), x_center))

    # Pass 1: whole-row matches (label + leaders fused rows are harmless
    # here since a pure stamp row is just the number).
    for line_text, bbox in _collect_rows(page):
        _consider(line_text, bbox)

    # Pass 2: per-span fallback for column-collision rows, where the
    # left-margin line-number digit shares a baseline with the centred
    # stamp and the row merger fuses them ("28 3").
    try:
        raw = page.get_text("dict")
    except Exception:
        raw = {"blocks": []}
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                txt = span.get("text", "").strip()
                bbox = span.get("bbox")
                if txt and bbox:
                    _consider(txt, bbox)

    if not candidates:
        return None
    # Bottom-most first (footers), then closest to horizontal centre.
    candidates.sort(key=lambda c: (-c[0], abs(c[2] - page_center_x)))
    return candidates[0][1]


def _resolve_target(printed_map: dict, page_label: str, after_idx: int):
    """Resolve a printed page label (e.g. "1", "ii") to a PDF page index.

    `after_idx` is the index of the page containing the reference (a TOC
    entry's own page). TOC entries always point forward, so we return
    the first occurrence strictly after `after_idx`. If the label has no
    forward occurrence, we fall back to the first occurrence anywhere —
    a reasonable last resort, though this case is unusual and may
    indicate a malformed TOC.

    Returns None if the label is unknown.
    """
    occurrences = printed_map.get(page_label.lower())
    if not occurrences:
        return None
    for idx in occurrences:
        if idx > after_idx:
            return idx
    # No forward occurrence — return the first occurrence as a fallback.
    return occurrences[0]


def _link_toc_entries(doc, log: logging.Logger):
    """Find the Table of Contents (if any) within the first TOC_SCAN_PAGES
    pages and add internal links from each entry to the PDF page bearing
    the entry's printed page number.

    Returns (linked_count, entries, toc_page_range) where:
      * entries is a list of (label, target_page_index) tuples in
        document order — one per successfully-resolved TOC entry,
        regardless of whether a new link was inserted for it this run
        (entries are produced even when the overlap-check skips
        re-linking, so re-runs surface the same set of bookmark
        candidates as first runs).
      * toc_page_range is (start_page_idx, end_page_idx_inclusive) for
        the pages that contain the TOC itself (the heading page plus
        any continuation pages with TOC entries). Used by the bookmark
        builder to point the "Contents" branch header at the TOC's own
        page, and by the section-heading detector to skip TOC pages.
        Returns None if no TOC heading was found at all.
    """
    try:
        import fitz
    except ImportError:
        return 0, [], None

    toc_start = _find_toc_heading(doc, TOC_SCAN_PAGES)
    if toc_start is None:
        return 0, [], None

    printed_map = _build_printed_page_map(doc)
    if not printed_map:
        log.info("  TOC heading found but no printed page numbers detected; "
                 "skipping TOC linking")
        # We still know where the TOC page itself is — return it so the
        # bookmark builder can point Contents at it, and so the section
        # detector knows to skip it.
        return 0, [], (toc_start, toc_start)

    linked = 0
    entries = []   # [(label, target_page_index), ...]
    last_toc_page = toc_start  # tracks the furthest TOC page walked
    # Walk forward from the TOC heading page. Stop on the first page that
    # contains a TOC-terminating heading (TOA, Introduction, Argument, etc.)
    # or that yields no entries — whichever comes first. The TOC_SCAN_PAGES
    # budget applied only to *finding* the heading; once found, the TOC
    # itself is walked to its natural end regardless of length.
    for page_idx in range(toc_start, len(doc)):
        last_toc_page = page_idx
        page = doc[page_idx]
        # Snapshot existing link annotations so a re-run on an already-
        # linked PDF doesn't stack a second GOTO on every TOC entry. New
        # links added during this page's processing are appended to the
        # snapshot list so we also avoid double-linking within one run.
        existing_links = page.get_links()
        # Group text runs by baseline so a TOC entry's label, dot leaders,
        # and right-aligned page number — which PyMuPDF often returns as
        # three separate "lines" — combine into one logical row before
        # entry matching. See _collect_rows for the grouping rule.
        page_lines = _collect_rows(page)

        # Stop the TOC if any line on this page is a terminating heading.
        # A line that parses as a TOC entry (label + leaders + page number)
        # is NEVER treated as a terminator, even if its label happens to be
        # "Introduction" or "Argument" — those are legitimate first entries
        # in most briefs. Terminators are bare standalone headings.
        end_hit = False
        for line_text, _ in page_lines:
            if _TOC_HEADING_RE.search(line_text):
                continue
            if _TOC_ENTRY_RE.match(line_text):
                continue
            if _TOC_END_RE.search(line_text):
                end_hit = True
                break

        entries_on_this_page = 0
        for line_text, bbox in page_lines:
            if _TOC_HEADING_RE.search(line_text):
                continue
            m = _TOC_ENTRY_RE.match(line_text)
            if not m:
                # Not a TOC entry. If it's a terminator heading, stop;
                # otherwise it's just a blank-ish line and we skip it.
                if _TOC_END_RE.search(line_text):
                    break
                continue
            # The line LOOKS like a TOC entry. Count it toward the "is
            # this page still part of the TOC?" signal whether or not we
            # can actually resolve its page target — a TOC that runs
            # several pages can have entries with targets that we failed
            # to detect (e.g., a missing printed page number), and that
            # shouldn't abort the walk through subsequent TOC pages.
            entries_on_this_page += 1

            page_label = m.group("page").lower()
            target_idx = _resolve_target(printed_map, page_label, page_idx)
            if target_idx is None:
                continue
            # Don't link an entry to the very page it sits on.
            if target_idx == page_idx:
                continue

            # Record this entry for the bookmark builder regardless of
            # whether we end up inserting a new link below — re-runs hit
            # the overlap-check skip path but should still surface the
            # same bookmark set as a first run.
            label = m.group("label").strip()
            entries.append((label, target_idx))

            rect = fitz.Rect(bbox)
            # Skip if this rect overlaps an existing link annotation —
            # primarily a re-run guard, but also catches the unlikely
            # case of a TOC line that overlaps a citation rect.
            already = False
            for el in existing_links:
                er = el.get("from")
                if er and rect.intersects(er):
                    already = True
                    break
            if already:
                continue
            page.insert_link({
                "kind": fitz.LINK_GOTO,
                "from": rect,
                "page": target_idx,
                "to": fitz.Point(0, 0),
            })
            existing_links.append({"from": rect, "kind": fitz.LINK_GOTO})
            # Underline the trailing page number only, not the whole row —
            # underlining a full TOC line (which is mostly dot leaders)
            # looks like a typesetting error. We locate just the number
            # via search_for, restricted to this line's bbox.
            num_quads = page.search_for(m.group("page"), clip=rect, quads=True)
            for q in num_quads:
                qr = q.rect
                # Only the right-most occurrence on this line — the leader
                # number, not a digit that happens to appear in the label.
                if qr.x1 < rect.x1 - 5:
                    continue
                underline_y = qr.y1 - 0.5
                page.draw_line(
                    fitz.Point(qr.x0, underline_y),
                    fitz.Point(qr.x1, underline_y),
                    color=LINK_COLOUR,
                    width=1.0,
                )
                break
            linked += 1

        if end_hit or entries_on_this_page == 0:
            # This page was either past the TOC (terminator heading or no
            # entries). Roll back last_toc_page to the previous page since
            # this one isn't TOC content. If this is the first page (no
            # prior TOC content), last_toc_page stays at toc_start since
            # that page at least had the heading.
            if entries_on_this_page == 0 and page_idx > toc_start:
                last_toc_page = page_idx - 1
            break

    if linked:
        log.info(f"  Linked {linked} TOC entry(ies) to internal pages")
    return linked, entries, (toc_start, last_toc_page)


# ────────────────────────────────────────────────────────────────────────────
# Section-heading detection (TOC fallback for the bookmark builder)
# ────────────────────────────────────────────────────────────────────────────
# When a document has no table of contents, the bookmark builder's
# `Contents` branch would be empty — we'd offer the user no high-level
# navigation. This block detects section headings heuristically so we
# can populate `Contents` from the document's structure even without a
# parsed TOC.
#
# Signal layering: a row is treated as a heading only if it combines a
# *visual* signal (larger font than body, or bold formatting) with a
# *structural* signal (an outline label like "I.", "A.", "1.", or a
# short ALL-CAPS line). Either signal alone produces too many false
# positives — body text is often bold for defined terms, and outline
# labels appear in body sentences ("Part I argues..."). Together they
# concentrate the matches on real headings.
#
# Scope: this fallback runs ONLY when TOC parsing produced no entries.
# Documents that have a TOC use the parsed entries — the heading
# detector is never invoked for them, so we don't risk regressing
# TOC-bearing documents with a noisier source.

# Outline labels: Roman numerals (capped at X to limit false positives
# from body text starting with "I."), single uppercase letter, 1-2
# digit number, and single lowercase letter. Each is followed by a
# period, then either end-of-line (label alone on the row, common when
# the label and heading text are typeset as separate runs) or
# whitespace + heading text.
_HEADING_LABEL_RE = re.compile(
    r"""
    ^
    \s*
    (?P<label>
        (?:I|II|III|IV|V|VI|VII|VIII|IX|X)\.        # Roman I-X
      | [A-Z]\.                                       # single uppercase letter
      | \d{1,2}\.                                     # 1-2 digit number
      | [a-z]\.                                       # single lowercase letter
    )
    (?:\s+(?P<text>\S.*?))?                           # optional heading text
    \s*$
    """,
    re.VERBOSE,
)

# Bare ALL-CAPS heading without outline label: "INTRODUCTION",
# "STATEMENT OF FACTS", "ARGUMENT", "CONCLUSION", "FIRST CAUSE OF
# ACTION", "SECTION 2", "COUNT 1". Require 2+ words OR a single word
# of 6+ chars (rules out short noise like "FILED" stamps or "EXHIBIT"
# which are caught elsewhere). The character class allows digits so
# numbered headings ("SECTION 2", "COUNT 1") match — these are common
# in complaints and longer briefs.
_HEADING_ALLCAPS_RE = re.compile(
    r"^\s*[A-Z][A-Z0-9\s'\-,&]{4,}[A-Z0-9]\s*$"
)

# A line that looks like a complete sentence (ends in period and has
# enough internal whitespace to be a sentence, not just a label
# followed by period). Used as a negative filter — sentences are not
# headings. Threshold: a line ending in ".", "!" or "?" with more than
# 8 whitespace-separated tokens is a sentence and not a heading.
_HEADING_MAX_TOKENS = 15

# Pages to skip at the start of every document when running the
# heading-detection pass. Pages 0-1 are reserved for caption layouts
# whose ALLCAPS court-name lines ("SUPERIOR COURT OF THE STATE OF
# CALIFORNIA", "COUNTY OF LOS ANGELES") and bold-centered case
# captions would otherwise be misread as section headings. By page 2
# the caption block has ended and either TOC or body content begins.
_HEADING_SKIP_LEAD_PAGES = 2

# Hard cap on how far into a document the heading detector scans.
# Briefs are limited to 20-25 pages by most court rules; 30 is a
# comfortable ceiling that covers oversized briefs without venturing
# into exhibit territory in documents that lack cover-page markers.
# The exhibit-cover stop (see _detect_section_headings) usually
# triggers first when exhibits exist — this cap is the fallback for
# memos whose exhibits are unmarked or absent but have a long
# appendix-style tail (e.g. proofs of service, declarations stapled
# without cover sheets).
_HEADING_MAX_SCAN_PAGES = 30


def _document_body_font_size(doc) -> float:
    """Return the modal font size across the document (the size that
    appears on the most text spans). This is the document's body font
    — any heading must be larger than this OR bold to qualify.

    Sampling: scan every page, count span sizes weighted by character
    length so a long body paragraph counts more than a short bold
    label. Returns 12.0 as a safe default if the document has no
    text spans at all.
    """
    from collections import Counter
    counts: Counter = Counter()
    for page in doc:
        try:
            d = page.get_text("dict")
        except Exception:
            continue
        for block in d.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for sp in line.get("spans", []):
                    t = sp.get("text", "")
                    if not t.strip():
                        continue
                    size = sp.get("size", 0)
                    if not size:
                        continue
                    # Round to 0.5pt to merge near-identical sizes
                    bucket = round(size * 2) / 2
                    counts[bucket] += len(t.strip())
    if not counts:
        return 12.0
    return counts.most_common(1)[0][0]


def _row_visual_signals(page, bbox, line_text):
    """Return (max_size, is_bold, is_centered) for the row at `bbox` on `page`.

    Walks every span whose vertical center lies inside the row's bbox
    and reports the largest font size seen and whether any span is
    bold (either flagged bold or with a font name containing "Bold").
    Centering is computed geometrically: the row's horizontal midpoint
    is within ~10pt of the page's horizontal midpoint, AND the row is
    narrower than ~70% of the page width (so a long body paragraph
    that happens to span the full page isn't treated as centered).
    """
    max_size = 0.0
    is_bold = False
    try:
        d = page.get_text("dict")
    except Exception:
        return max_size, is_bold, False
    y0, y1 = bbox[1], bbox[3]
    for block in d.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            lb = line.get("bbox")
            if not lb:
                continue
            line_y_center = (lb[1] + lb[3]) / 2
            if not (y0 - 1 <= line_y_center <= y1 + 1):
                continue
            for sp in line.get("spans", []):
                if not sp.get("text", "").strip():
                    continue
                size = sp.get("size", 0)
                if size > max_size:
                    max_size = size
                flags = sp.get("flags", 0)
                font = sp.get("font", "") or ""
                if (flags & 16) or "Bold" in font or "bold" in font:
                    is_bold = True
    # Centering: compare row x-midpoint to page x-midpoint.
    # Use the page's full width as the reference. Pleading paper has
    # a gutter on the left, but a centered heading on pleading paper
    # is centered relative to the whole page anyway (publishers center
    # over the printable area, not the gutter-adjusted body column),
    # so this works in both layouts. The narrow-line guard
    # (width < 70% of page width) filters out body paragraphs that
    # happen to have a midpoint near the page center.
    is_centered = False
    try:
        x0, _, x1, _ = bbox
        row_mid = (x0 + x1) / 2
        page_mid = page.rect.width / 2
        row_width = x1 - x0
        if abs(row_mid - page_mid) <= 10 and row_width < page.rect.width * 0.70:
            is_centered = True
    except Exception:
        pass
    return max_size, is_bold, is_centered


def _is_heading_row(line_text: str, font_size: float, is_bold: bool,
                    is_centered: bool, body_size: float) -> bool:
    """Decide whether a row is a section heading.

    Combines visual signals (font size > body, bold, centered) with
    structural signals (outline label, ALL-CAPS pattern). Rejects rows
    that look like full sentences. Conservative by design — false
    positives in the bookmark tree are more annoying than false
    negatives.

    Two paths to qualify:
      * Outline-label heading ("I. INTRODUCTION", "A. The Court..."):
        passes if EITHER larger-than-body OR bold. These headings
        are visually marked by their label structure, so a single
        visual cue is enough corroboration.
      * Bare ALL-CAPS heading ("SUMMARY OF ARGUMENT", "INTRODUCTION"):
        passes only if AT LEAST 2 of {bold, larger-than-body,
        centered} are true. The all-caps text alone could occur in
        body text (court names in captions, statute references), so
        we require two corroborating visual cues to commit to a
        bookmark.
    """
    text = line_text.strip()
    if not text:
        return False

    # Length cap — headings are never long sentences
    tokens = text.split()
    if len(tokens) > _HEADING_MAX_TOKENS:
        return False

    larger = font_size >= body_size + 1.0

    # Sentence rejection: ends in period with enough words to be a
    # sentence. Outline-label headings ("I. INTRODUCTION") end at
    # "INTRODUCTION" without a period, so a trailing period on a long
    # line is a sentence-shape signal. "I. Introduction" (no period
    # at end) passes; "We address each claim in turn." rejects.
    if text[-1] in ".!?" and len(tokens) > 5:
        label_only = _HEADING_LABEL_RE.match(text)
        if not (label_only and not label_only.group("text")):
            return False

    # Outline-label path: structural cue is strong, single visual cue
    # is enough.
    if _HEADING_LABEL_RE.match(text):
        if larger or is_bold:
            return True
        return False

    # ALL-CAPS path: structural cue is weaker (body text can be ALL-CAPS
    # for proper nouns or stylistic emphasis), so require 2 of 3 visual
    # cues. This is the user spec — "bold, large, underlined, and
    # centered" relaxed to a 2-of-3 majority (with underline omitted
    # because PyMuPDF doesn't natively expose underline as a span flag
    # and the styling rarely appears alone).
    if _HEADING_ALLCAPS_RE.match(text) and len(text) >= 6:
        visual_score = (1 if is_bold else 0) + (1 if larger else 0) \
                       + (1 if is_centered else 0)
        if visual_score >= 2:
            return True
        return False

    return False


def _detect_section_headings(doc, log: logging.Logger,
                              toc_page_range=None):
    """Return [(label, page_index), ...] for every section heading
    found in the document, in document order.

    Runs unconditionally on briefs (gated upstream by filename via
    should_skip_linking). Pages identified as TOC pages by
    _link_toc_entries are skipped — those headings are already
    covered by the Contents branch and would otherwise double-up
    in the outline.

    Skips the first _HEADING_SKIP_LEAD_PAGES PDF pages to avoid
    misreading caption ALL-CAPS text ("SUPERIOR COURT OF...") as
    headings.

    Scan range: stops at whichever comes first —
      * _HEADING_MAX_SCAN_PAGES (30) — hard cap covering even
        oversized briefs without venturing into exhibits.
      * The earliest exhibit cover page detected by
        _find_exhibit_cover_pages — once the exhibits start, headings
        inside attached documents are false positives. The detector
        is reused here without modification; it returns the same
        cover map _link_exhibit_references uses later. Calling it
        twice is cheap (no link insertion) and avoids reordering the
        process_pdf pipeline.

    toc_page_range: (start_idx, end_idx_inclusive) for pages occupied
    by the TOC itself, or None. Those pages are skipped during the
    section scan.

    Deduplicates against repeated identical headings appearing on
    consecutive pages (page headers/footers that read e.g. "ARGUMENT"
    on every page of the argument section). Only the first occurrence
    is kept as a bookmark target — subsequent identical hits are
    page-header artefacts.
    """
    body_size = _document_body_font_size(doc)

    # Build the set of pages to skip: TOC pages, computed once upfront.
    toc_skip_pages = set()
    if toc_page_range is not None:
        t_start, t_end = toc_page_range
        toc_skip_pages.update(range(t_start, t_end + 1))

    # Determine the scan stop. The page cap and the earliest exhibit
    # cover both lower-bound the inclusive end-of-scan index.
    scan_end = min(_HEADING_MAX_SCAN_PAGES, len(doc))
    try:
        cover_map, _ = _find_exhibit_cover_pages(doc)
        if cover_map:
            earliest_cover = min(min(pages) for pages in cover_map.values() if pages)
            # Only honor the exhibit-cover stop if the earliest cover
            # is at PDF index 3 or later (page 4+). Earlier "covers"
            # are almost certainly false positives — a TOC entry, a
            # caption block, or a heading that happens to mention an
            # exhibit. A real brief reserves its first 3 pages for
            # caption + TOC at minimum.
            if 3 <= earliest_cover < scan_end:
                scan_end = earliest_cover
    except Exception:
        # Cover detection failures are non-fatal here — fall back to
        # the page cap alone. The bookmark feature isn't worth
        # aborting over a cover-scan glitch.
        pass

    entries = []
    seen_labels = set()

    for page_idx in range(_HEADING_SKIP_LEAD_PAGES, scan_end):
        if page_idx in toc_skip_pages:
            continue
        page = doc[page_idx]
        rows = _collect_rows(page)
        for line_text, bbox in rows:
            max_size, is_bold, is_centered = _row_visual_signals(
                page, bbox, line_text)
            if not _is_heading_row(line_text, max_size, is_bold,
                                    is_centered, body_size):
                continue
            label = line_text.strip()
            # Dedup: only the first sighting of a given label string
            # becomes a bookmark. Repeated identical strings on later
            # pages are usually running headers.
            if label in seen_labels:
                continue
            seen_labels.add(label)
            entries.append((label, page_idx))

    if entries:
        log.info(f"  Detected {len(entries)} section heading(s) "
                 f"(scanned pages {_HEADING_SKIP_LEAD_PAGES+1}-"
                 f"{scan_end}; body font ~{body_size:.1f}pt)")
    return entries


# ────────────────────────────────────────────────────────────────────────────
# Cause-of-action detection and linking (Complaint-only)
# ────────────────────────────────────────────────────────────────────────────
# Complaints (and amended complaints — FAC/SAC/TAC) carry a distinctive
# structure: each claim is introduced by a heading like "FIRST CAUSE OF
# ACTION", "SECOND CAUSE OF ACTION", etc. We bookmark every one of these
# and, when the cover page also lists the causes in the same ALL-CAPS
# form, we add hyperlinks from each cover-page listing to its body
# occurrence.
#
# This block runs only for files whose name matches `is_complaint()`.
# Briefs, declarations, and other doc types pass through untouched —
# their bookmarks come from the TOC parser or the heading detector
# instead.
#
# Identifying a cause-of-action heading:
#   * "FIRST CAUSE OF ACTION", "SECOND CAUSE OF ACTION", … (English ordinals)
#   * "COUNT I", "COUNT II", … (Roman numerals)
#   * "COUNT ONE", "COUNT TWO", … (English cardinals)
#   * "FIRST CLAIM FOR RELIEF", "SECOND CLAIM FOR RELIEF", … (federal style)
# All in ALL-CAPS. Mixed-case body text mentioning these phrases ("the
# first cause of action…") never matches.
#
# Picking the bookmark target page when an ordinal appears multiple
# times: complaints commonly list every cause on the caption/cover page
# AND then have a section heading deeper in the document. We want the
# bookmark to jump to the body heading, not the cover listing. Rule:
# when an ordinal appears ≥2 times, the first occurrence (within the
# first 3 PDF pages) is treated as the cover listing and the next
# occurrence is the bookmark target. Single-occurrence ordinals
# bookmark wherever they appear.

# English ordinals up to 30 (rare to see complaints with more)
_CAUSE_ORDINALS_ENGLISH = [
    "FIRST", "SECOND", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH",
    "EIGHTH", "NINTH", "TENTH", "ELEVENTH", "TWELFTH", "THIRTEENTH",
    "FOURTEENTH", "FIFTEENTH", "SIXTEENTH", "SEVENTEENTH", "EIGHTEENTH",
    "NINETEENTH", "TWENTIETH", "TWENTY-FIRST", "TWENTY-SECOND",
    "TWENTY-THIRD", "TWENTY-FOURTH", "TWENTY-FIFTH", "TWENTY-SIXTH",
    "TWENTY-SEVENTH", "TWENTY-EIGHTH", "TWENTY-NINTH", "THIRTIETH",
]
_ORDINAL_TO_NUMBER = {w: i + 1 for i, w in enumerate(_CAUSE_ORDINALS_ENGLISH)}

# Roman numerals I-XXX for "COUNT I", "COUNT II", etc.
_CAUSE_ROMANS = [
    "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
    "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
    "XXI", "XXII", "XXIII", "XXIV", "XXV", "XXVI", "XXVII", "XXVIII",
    "XXIX", "XXX",
]
_ROMAN_TO_NUMBER = {r: i + 1 for i, r in enumerate(_CAUSE_ROMANS)}

# English cardinals (ONE, TWO, ...) for "COUNT ONE" style.
_CAUSE_CARDINALS = [
    "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT",
    "NINE", "TEN", "ELEVEN", "TWELVE", "THIRTEEN", "FOURTEEN", "FIFTEEN",
    "SIXTEEN", "SEVENTEEN", "EIGHTEEN", "NINETEEN", "TWENTY",
]
_CARDINAL_TO_NUMBER = {w: i + 1 for i, w in enumerate(_CAUSE_CARDINALS)}

# Matches: "FIRST CAUSE OF ACTION", "FIRST CLAIM FOR RELIEF",
# "SECOND CAUSE OF ACTION (Breach of Contract)", and "TWENTY-FIRST CAUSE OF
# ACTION". The ordinal is the only capture group used; downstream we
# normalize to an integer.
_CAUSE_ORDINAL_RE = re.compile(
    r"^\s*(?P<ord>" + "|".join(_CAUSE_ORDINALS_ENGLISH) + r")"
    r"\s+(?:CAUSE\s+OF\s+ACTION|CLAIM\s+FOR\s+RELIEF)"
    r"(?:\s|,|$|\(|—|-|:)",
    re.IGNORECASE,
)

# Matches "COUNT I", "COUNT II", … (Roman) and "COUNT ONE", "COUNT TWO", …
# (English cardinal). Case-insensitive for safety though most occur in
# ALL-CAPS.
_COUNT_ROMAN_RE = re.compile(
    r"^\s*COUNT\s+(?P<rom>" + "|".join(_CAUSE_ROMANS) + r")"
    r"(?:\s|,|$|\(|—|-|:|\.)",
    re.IGNORECASE,
)
_COUNT_CARDINAL_RE = re.compile(
    r"^\s*COUNT\s+(?P<card>" + "|".join(_CAUSE_CARDINALS) + r")"
    r"(?:\s|,|$|\(|—|-|:|\.)",
    re.IGNORECASE,
)

# Pages on which a cause-of-action ordinal is treated as a cover-page
# *listing* rather than the body target. Complaints have caption + cover
# listing within the first 3 PDF pages essentially always; once we're
# past page 3 we're in the body.
_COVER_LISTING_LAST_PAGE = 3   # 0-indexed exclusive bound — pages 1-3

# Document-name patterns that identify a complaint or amended complaint.
# Independent of `_SKIP_LINK_PATTERNS` so we can run cause-of-action
# linking on these documents even though TOC and citation linking are
# disabled for them. Declarations and separate statements are
# intentionally NOT here.
_COMPLAINT_PATTERNS = [
    re.compile(r"(?:^|[\s_-])Complaint(?:[\s_-]|$)", re.IGNORECASE),
    re.compile(r"(?:^|[\s_-])Compl\.?(?:[\s_-]|$)", re.IGNORECASE),
    re.compile(r"(?:^|[\s_-])FAC(?:[\s_-]|$)", re.IGNORECASE),
    re.compile(r"(?:^|[\s_-])SAC(?:[\s_-]|$)", re.IGNORECASE),
    re.compile(r"(?:^|[\s_-])TAC(?:[\s_-]|$)", re.IGNORECASE),
]


def is_complaint(filename: str) -> bool:
    """Return True if filename suggests a complaint or amended complaint."""
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    for pat in _COMPLAINT_PATTERNS:
        if pat.search(stem):
            return True
    return False


def _cause_number_from_row(text: str):
    """Return the integer ordinal (1-30) if `text` is a cause-of-action
    heading, else None. Recognises English ordinals, Roman COUNTs, and
    English cardinal COUNTs."""
    t = text.strip()
    m = _CAUSE_ORDINAL_RE.match(t)
    if m:
        return _ORDINAL_TO_NUMBER.get(m.group("ord").upper().replace(" ", "-"))
    m = _COUNT_ROMAN_RE.match(t)
    if m:
        return _ROMAN_TO_NUMBER.get(m.group("rom").upper())
    m = _COUNT_CARDINAL_RE.match(t)
    if m:
        return _CARDINAL_TO_NUMBER.get(m.group("card").upper())
    return None


def _detect_causes_of_action(doc, log: logging.Logger):
    """Find every cause-of-action heading and return:
      bookmark_entries: [(label, target_page_index), ...] ordered by
                        ordinal number, one entry per distinct cause.
      cover_occurrences: [(ordinal_n, page_index, label, bbox), ...]
                        every match found on PDF pages 1-3 (the cover
                        listing source for the link pass).
      body_occurrences: {ordinal_n: (page_index, label, bbox)}
                        the chosen body target per ordinal.

    Selection rule: for each ordinal, if it appears ≥2 times and at
    least one appearance is on PDF pages 1-3, the FIRST such
    appearance is the cover listing and the NEXT appearance is the
    body target. If only one appearance exists (cover only or body
    only), that one is the body target.

    No scan range cap — complaints can be 80+ pages. The structural
    constraint of ALL-CAPS-with-ordinal pattern keeps false positives
    extremely low without needing a page limit.
    """
    # all_hits[ordinal_n] = list of (page_idx, label, bbox) in document order
    all_hits = {}
    for page_idx, page in enumerate(doc):
        for line_text, bbox in _collect_rows(page):
            n = _cause_number_from_row(line_text)
            if n is None:
                continue
            all_hits.setdefault(n, []).append(
                (page_idx, line_text.strip(), bbox)
            )

    if not all_hits:
        return [], [], {}

    cover_occurrences = []
    body_occurrences = {}
    for n, hits in sorted(all_hits.items()):
        # Partition rule: for each ordinal, the FIRST occurrence (in
        # document order) is treated as the cover listing IF it sits
        # on PDF pages 1-3; subsequent occurrences are body
        # candidates. Single-occurrence ordinals bookmark wherever they
        # appear. This handles all common layouts:
        #   * Cover listing + body heading           → cover/body split
        #   * Body heading only (no cover listing)   → bookmark to body
        #   * Cover listing only (no body heading)   → bookmark to cover
        #     (it's the only target we have)
        first_page, _, _ = hits[0]
        if len(hits) >= 2 and first_page < _COVER_LISTING_LAST_PAGE:
            cover_occurrences.append(
                (n, hits[0][0], hits[0][1], hits[0][2])
            )
            body_occurrences[n] = hits[1]
        else:
            body_occurrences[n] = hits[0]

    # Bookmark entries: one per ordinal, ordered by ordinal number.
    bookmark_entries = [
        (body_occurrences[n][1], body_occurrences[n][0])
        for n in sorted(body_occurrences)
    ]
    return bookmark_entries, cover_occurrences, body_occurrences


def _link_cover_to_causes(doc, cover_occurrences, body_occurrences,
                           log: logging.Logger) -> int:
    """Insert GOTO links from each cover-page cause-of-action listing
    to the body occurrence. Returns count of links inserted.

    Skipped per-ordinal when (a) there's no separate body target for
    that ordinal (cover only), or (b) the cover and body occurrences
    are on the same page (rare but possible if a complaint puts both
    a cover-style listing and the actual heading on the same page).
    Idempotent: existing link annotations on the cover rect are
    detected and the new link is suppressed.
    """
    try:
        import fitz
    except ImportError:
        return 0

    linked = 0
    for n, cover_page_idx, label, bbox in cover_occurrences:
        body = body_occurrences.get(n)
        if not body:
            continue
        body_page_idx = body[0]
        if body_page_idx == cover_page_idx:
            # Same page — there's nothing to link to. Common when the
            # ordinal only appears once on the cover and the "body
            # target" we recorded is actually that same cover listing.
            continue
        page = doc[cover_page_idx]
        rect = fitz.Rect(bbox)

        # Idempotency: skip if an existing link already covers this rect
        existing_links = page.get_links()
        already = False
        for el in existing_links:
            er = el.get("from")
            if er and rect.intersects(er):
                already = True
                break
        if already:
            continue

        page.insert_link({
            "kind": fitz.LINK_GOTO,
            "from": rect,
            "page": body_page_idx,
            "to": fitz.Point(0, 0),
        })
        underline_y = rect.y1 - 0.5
        page.draw_line(
            fitz.Point(rect.x0, underline_y),
            fitz.Point(rect.x1, underline_y),
            color=LINK_COLOUR,
            width=1.0,
        )
        linked += 1

    if linked:
        log.info(f"  Linked {linked} cover-page cause-of-action reference(s)")
    return linked


# ────────────────────────────────────────────────────────────────────────────
# Exhibit cross-reference linking
# ────────────────────────────────────────────────────────────────────────────
# Turn body references like "Exhibit 5", "Ex. 12", "Exh. 3", "Exhibit A",
# "Ex. AA" into internal jumps to the corresponding exhibit page. Runs
# whenever 2+ distinct exhibit cover pages are detected, regardless of
# the document's total page count — the cover-count gate is sufficient
# to avoid false positives in short briefs that mention "Exhibit A" in
# passing (those won't have multiple labelled cover rows).
#
# Identifier forms:
#   Numeric  -- Exhibit 1, Ex. 12, Exh. 3   (1-3 digits)
#   Letter   -- Exhibit A, Ex. AA           (uppercase, 1-2 letters)
#   The same document can use both formats; we link whichever appears.
#   Each form is also matched in quoted variants — Exhibit "3" (straight)
#   and Exhibit \u201c3\u201d (curly). California pleading templates often
#   wrap exhibit numbers in quotes, and a single document frequently mixes
#   bare and quoted forms across paragraphs. Cover-page detection and
#   body-reference matching both handle all three spellings.
#   Plurals ("Exhibits"), ranges ("Exhibit 3-5"), and lowercase letter
#   references ("exhibit a", which is almost always natural English, not
#   a cite) are intentionally left alone.
#
# Letter-specific safeguards:
#   Letter references have a much higher false-positive rate than numeric
#   ones because most English sentences begin with a capital letter. To
#   keep this safe:
#     * Letters must be UPPERCASE. "Exhibit a" never matches.
#     * Letter cover rows must either be the label alone or be followed
#       by a separator (— – - :) before a descriptor. "Exhibit A copy of
#       the contract" is NOT treated as a cover row.
#     * Body-text linking uses a rect-validation probe to reject any quad
#       that's a fragment of a longer token. PyMuPDF's search_for is
#       glyph-based and would otherwise latch onto the "Exhibit A" part
#       of "Exhibit Apple" or "Exhibits A-C". The probe (see
#       _is_complete_phrase_rect) checks whether the next ~3pt to the
#       right of a match contains an alphanumeric glyph — if so, the
#       reference is a prefix of a longer word and is discarded. The
#       same logic protects numeric matches: "Exhibit 1" won't latch onto
#       "Exhibit 12" because "2" is the next glyph.
#
# Target selection:
#   For each exhibit identifier, we find every page whose layout shows the
#   label as a row of its own. The *nearest* such page AFTER the body
#   reference is the link target. This matters in combined filings that
#   contain two declarations each numbering their own exhibits 1, 2, 3 —
#   a reference in declaration A's body should jump to declaration A's
#   Exhibit 1, not declaration B's. If no cover page exists after the
#   reference, the nearest one before is used as a fallback.
# EXHIBIT_LINK_MIN_PAGES was a 30-page minimum gate retired when an
# 18-page declaration with Exhibits A/B/C failed to link them. The
# cover-count >= 2 gate inside _link_exhibit_references is now the
# sole guard. If you want to bring back a page-count minimum, restore
# the `if len(doc) <= N: return 0, {}` check at the top of that
# function — but be aware short multi-exhibit declarations exist.

# Quote characters that may surround an exhibit identifier. Both straight
# ("3") and the curly opener/closer (\u201c3\u201d) appear in real-world
# filings — the curly form is what Word produces with smart-quotes on,
# and many caption-page templates wrap the number that way.
_EXHIBIT_QUOTE_OPEN = "[\"'\u201c\u2018]"
_EXHIBIT_QUOTE_CLOSE = "[\"'\u201d\u2019]"

_EXHIBIT_COVER_RE = re.compile(
    r"""
    ^\s*
    (?:EXHIBIT|Exhibit|EX\.|Ex\.|EXH\.|Exh\.)
    \s+
    """ + _EXHIBIT_QUOTE_OPEN + r"""?                  # optional opening quote
    (?:
        (?P<num>\d{1,3}) \b
        """ + _EXHIBIT_QUOTE_CLOSE + r"""?             # optional closing quote
        .{0,40}                                        # numeric: any short trailing descriptor
      |
        (?P<letter>[A-Z]{1,2}) \b
        """ + _EXHIBIT_QUOTE_CLOSE + r"""?             # optional closing quote
        (?:\s*[\u2014\u2013\-:]\s*.{1,40})?            # letter: optional separator + descriptor
    )
    \s*$
    """,
    re.VERBOSE,
)


def _find_exhibit_cover_pages(doc):
    """Scan the document for pages bearing an exhibit label as a standalone
    row, and return (targets, label_pages):

      targets     -- {exhibit_id: [page_idx, ...]} with contiguous runs
                     collapsed to their first page. Exhibit IDs are
                     normalized strings: "1", "12", "A", "AA". These are
                     the candidate link targets for body references.
      label_pages -- set of every page index whose layout contains an
                     exhibit label row. These are excluded from the body-
                     reference scan so we don't link an exhibit content
                     page's own banner ("Exhibit 5 — page 2 of 9") back
                     to the cover sheet — that would be a self-link from
                     within the exhibit itself.

    A "standalone row" is what _collect_rows returns when the label is the
    whole text run on its baseline — this catches both true cover sheets
    (one big "EXHIBIT 5" on an otherwise blank page) and content pages
    whose top banner reads "Exhibit 5" or "Exhibit 5 — Description".
    """
    found: dict = {}
    label_pages: set = set()
    for i, page in enumerate(doc):
        for line_text, _bbox in _collect_rows(page):
            m = _EXHIBIT_COVER_RE.match(line_text)
            if not m:
                continue
            # Exactly one of `num` or `letter` matches; normalize both to
            # strings so the cover map can mix numbered and lettered IDs.
            ident = m.group("num") or m.group("letter")
            if not ident:
                continue
            found.setdefault(ident, []).append(i)
            label_pages.add(i)
            break  # one label-row per page is enough to register the page
    # Collapse contiguous runs to their first page: if Exhibit 5 has a
    # cover sheet at page 42 and content pages 43-50 each carry a banner
    # "Exhibit 5 — page N of 9", we want page 42 as the single link
    # target and don't need pages 43-50 as additional candidates. The
    # comparison tracks the previous *input* page, not the previous kept
    # page, so a full unbroken run collapses correctly. The `label_pages`
    # set keeps all of 42-50 — content pages still count as "inside the
    # exhibit" for self-link suppression.
    for ident, pages in found.items():
        pages.sort()
        deduped = [pages[0]]
        prev = pages[0]
        for p in pages[1:]:
            if p != prev + 1:
                deduped.append(p)
            prev = p
        found[ident] = deduped
    return found, label_pages


def _exhibit_target_for(ref_page: int, candidates) -> int:
    """Pick the nearest exhibit cover page for a body reference.

    Preference: the smallest candidate index that is > ref_page. If none
    exist after the reference, fall back to the largest candidate index
    that is < ref_page. Returns None if `candidates` is empty.
    """
    if not candidates:
        return None
    after = [p for p in candidates if p > ref_page]
    if after:
        return after[0]
    before = [p for p in candidates if p < ref_page]
    if before:
        return before[-1]
    return None


def _is_complete_phrase_rect(page, rect, probe_pt: float = 3.0) -> bool:
    """Return True if `rect` is the visual extent of a complete reference,
    i.e. not a prefix of a longer word/number. We check by probing the
    next ~3pt to the right of the rect: if a glyph there is alphanumeric
    AND not separated from the rect by whitespace, the rect is a fragment
    of a longer token (e.g. the "Exhibit 1" part of "Exhibit 12", or the
    "Exhibit A" part of "Exhibit Apple") and we should refuse to link it.

    PyMuPDF's search_for matches phrases case-insensitively at the glyph
    level and doesn't honour word boundaries. We use this probe to recover
    the boundary check our regex applies to the text stream.
    """
    try:
        import fitz
    except ImportError:
        return True
    probe = fitz.Rect(rect.x1, rect.y0, rect.x1 + probe_pt, rect.y1)
    after = page.get_text("text", clip=probe)
    for ch in after:
        if ch.isspace():
            return True  # whitespace before any other char → complete reference
        if ch.isalnum():
            return False  # word continues immediately → fragment
        # Punctuation (period, comma, paren) is fine — that's a real boundary
        return True
    return True  # nothing visible in the probe → complete reference


# Common identifier-form prefixes used in exhibit references. Used by the
# body-link pass to drive page.search_for for every cover-map identifier.
# (We don't loop over the regex directly because PyMuPDF's search_for is
# glyph-based and would miss case-folded variants if we passed only one
# spelling.)
_EXHIBIT_PREFIXES = ("Exhibit", "EXHIBIT", "Ex.", "EX.", "Exh.", "EXH.")


def _link_exhibit_references(doc, log: logging.Logger):
    """Find body references to exhibits and link them to the matching
    exhibit page.

    Returns (linked_count, cover_map) where cover_map is the
    {ident: [page_indices]} dict from _find_exhibit_cover_pages. The
    cover_map is empty (and linked_count is 0) when the document is
    too short, has fewer than 2 exhibits, or PyMuPDF isn't available;
    in those cases no linking happens and no bookmarks should be made.
    """
    try:
        import fitz
    except ImportError:
        return 0, {}

    cover_map, label_pages = _find_exhibit_cover_pages(doc)
    if len(cover_map) < 2:
        # Requires multiple detected exhibit covers — a single Exhibit 1
        # alone isn't worth a pass (and an empty map definitely isn't).
        # This gate is sufficient on its own: short documents without
        # real exhibits won't have 2+ covers detected. The previous
        # belt-and-suspenders page-count gate (EXHIBIT_LINK_MIN_PAGES)
        # was dropped because it excluded short declarations with
        # multiple legitimate exhibits (an 18-page declaration with
        # Exhibits A, B, C would never reach this code).
        return 0, {}

    linked = 0
    for page_idx, page in enumerate(doc):
        if page_idx in label_pages:
            # Don't link from within an exhibit's own pages — that would
            # turn the exhibit's header banner into a self-referential link.
            continue
        existing_links = page.get_links()
        # For each known exhibit identifier, look for every spelling of
        # "<prefix> <ident>" on this page. PyMuPDF's search_for is
        # glyph-based and doesn't honour word boundaries, so each quad
        # gets validated by _is_complete_phrase_rect before linking —
        # this is what prevents "Exhibit 1" from latching onto "Exhibit
        # 12", or "Exhibit A" from latching onto "Exhibit Apple".
        for ident, candidates in cover_map.items():
            target = _exhibit_target_for(page_idx, candidates)
            if target is None or target == page_idx:
                continue
            # Build every spelling we want to match for this identifier.
            # The bare form covers "Exhibit 5"; the quoted forms cover
            # "Exhibit \"5\"" (straight) and "Exhibit \u201c5\u201d" (curly).
            # All three appear in real filings, sometimes in the same
            # document — the body text of a declaration commonly switches
            # between forms paragraph to paragraph. Cover-page detection
            # is already quote-tolerant via _EXHIBIT_COVER_RE; this loop
            # is the body-reference counterpart.
            ident_forms = (
                ident,
                f"\"{ident}\"",
                f"\u201c{ident}\u201d",
            )
            for prefix in _EXHIBIT_PREFIXES:
                for ident_form in ident_forms:
                    phrase = f"{prefix} {ident_form}"
                    quads = page.search_for(phrase, quads=True)
                    for q in quads:
                        rect = q.rect
                        # PyMuPDF's search_for is case-insensitive, so a search
                        # for "Exhibit A" also matches lowercase "exhibit a"
                        # which is almost always natural English text rather
                        # than a cite. Clip the rect and confirm the glyph
                        # text matches the requested case exactly.
                        clipped = page.get_text("text", clip=rect).strip()
                        if clipped != phrase:
                            continue
                        # Reject quads that are fragments of longer tokens
                        # (e.g. "Exhibit 1" inside "Exhibit 12"). See the
                        # docstring of _is_complete_phrase_rect for the rule.
                        if not _is_complete_phrase_rect(page, rect):
                            continue
                        # Skip if an existing link annotation already covers
                        # this span — handles dedup across the multiple
                        # spellings ("Exhibit 1" / "EXHIBIT 1" both find the
                        # same glyph rect on a case-insensitive search) and
                        # also avoids stomping a TOC entry that happens to
                        # read "Exhibit 5 — Police Report".
                        already = False
                        for el in existing_links:
                            er = el.get("from")
                            if er and rect.intersects(er):
                                already = True
                                break
                        if already:
                            continue
                        page.insert_link({
                            "kind": fitz.LINK_GOTO,
                            "from": rect,
                            "page": target,
                            "to": fitz.Point(0, 0),
                        })
                        underline_y = rect.y1 - 0.5
                        page.draw_line(
                            fitz.Point(rect.x0, underline_y),
                            fitz.Point(rect.x1, underline_y),
                            color=LINK_COLOUR,
                            width=1.0,
                        )
                        linked += 1
                        existing_links.append({"from": rect,
                                               "kind": fitz.LINK_GOTO})

    if linked:
        log.info(f"  Linked {linked} exhibit reference(s) to exhibit pages "
                 f"({len(cover_map)} exhibits detected)")
    return linked, cover_map


# ────────────────────────────────────────────────────────────────────────────
# Bookmark (outline) builder
# ────────────────────────────────────────────────────────────────────────────
# Produce a PDF outline (the sidebar bookmarks Acrobat shows) from the same
# data the link passes already collected:
#   * Contents   <- TOC entries detected by _link_toc_entries
#   * Exhibits   <- exhibit cover pages from _link_exhibit_references
#   * Paragraphs <- per-page first-new-paragraph anchors from
#                   add_right_margin_markers
#
# The outline is set via doc.set_toc(), which *replaces* any pre-existing
# outline rather than appending. Two consequences:
#   * Idempotency is free — re-runs produce the same tree, no stacking.
#   * Bookmarks the source PDF came with are intentionally discarded, in
#     line with the policy decision to use a fresh, predictable outline
#     derived from the detected structure.
#
# Only the branches with content appear. A simple brief with no exhibits
# and no pleading-paper paragraphs gets just "Contents"; a declaration
# gets "Exhibits" and "Paragraphs"; a document with none of the three
# yields no outline change at all (set_toc is not called).


def _exhibit_sort_key(ident: str):
    """Order exhibits as a human would expect: numerics ascending first,
    then letters alphabetically. ("1", "2", "12", "A", "B", "AA")."""
    if ident.isdigit():
        return (0, int(ident), "")
    return (1, 0, ident.upper())


# ────────────────────────────────────────────────────────────────────────────
# Document-footer detection (for combined-filing splitter bookmarks)
# ────────────────────────────────────────────────────────────────────────────
# Many filings in Zachary's workflow are combined PDFs: a Motion followed by
# its Memorandum, a Declaration, and exhibits, all concatenated into one
# document. Each sub-document typically has its own running footer in the
# bottom margin (the document title, sometimes with a page number). The
# transition between sub-documents shows up as a footer change.
#
# This pass finds the *first* page of each unique footer and produces one
# bookmark per sub-document. Single-document PDFs (only one footer text
# across the entire file) get nothing — there's no value in a "Documents"
# branch with one entry; the user can navigate to page 1 trivially.
#
# Normalization for comparison:
#   * Bottom 72pt band only.
#   * Pleading-paper line-number gutter digits (lone "27", "28") are
#     filtered out before joining the band text.
#   * Trailing page-number tokens are stripped (" — 5", "- 12", "5.",
#     bare " 5" at end). This handles "OPPOSITION TO MSJ — 5" → "OPPOSITION
#     TO MSJ" across pages with different page numbers.
#   * Case-folded + whitespace-collapsed for the comparison key. The
#     bookmark label uses the cleaned text in its original case (the first
#     occurrence's casing).
#
# Behavioural rules (from user spec):
#   * Same footer appearing later in the file does NOT create a second
#     bookmark — first-appearance only.
#   * 1-page sub-documents (a unique footer that appears on exactly one
#     page) ARE bookmarked.
#   * 1-page footer "flicker" (footer A → footer B → footer A on
#     consecutive pages) is suppressed: the lone B page is treated as
#     noise and does NOT start a new document. This handles OCR/scan
#     artifacts on a single page without losing genuine 1-page sub-docs
#     (a real 1-page sub-doc doesn't revert to the prior footer
#     immediately after).
#   * Pages with no detectable footer inherit the previous page's footer
#     for grouping purposes.
#   * The whole pass is gated on ≥2 distinct footers in the document.

_FOOTER_BAND_PT = 50.0

# Minimum x-coordinate at which footer content can begin. Anything whose
# bbox sits entirely to the left of this threshold is considered to be in
# the left margin (pleading-paper line-number gutter or vertical firm
# letterhead) and excluded from the footer text. 90pt clears both:
#   * The line-number gutter (typically x ≈ 50-85pt on standard
#     pleading paper).
#   * Vertical firm letterheads ("OGLETREE, DEAKINS, NASH, SMOAK &
#     STEWART, P.C.") which run in the left margin and are read by
#     PyMuPDF as ordinary text spans with x_right ≈ 80pt or less.
# Standard 8.5x11 briefs and declarations put their body content (and
# any centered/right-aligned footer text) well to the right of 90pt.
_FOOTER_LEFT_MARGIN_PT = 90.0


def _normalize_footer_for_key(s: str) -> str:
    """Produce the comparison key for a footer string: strip every
    standalone digit-shaped token (page numbers, gutter digits, "of"-
    counters), normalize quote and dash variants, collapse whitespace,
    uppercase. Returns empty string if nothing meaningful remains.

    Standalone digit tokens are stripped wherever they occur — not
    just at the trailing edge — because real-world footers can have
    page numbers leading ("7 EXHIBIT A"), trailing ("OPPOSITION — 5"),
    or both ("Page 1 of 2 9 EXHIBIT A"). Any of these must normalize
    to the same key for grouping to work.

    Quote and dash normalization: page-to-page PDF text extraction
    can render the same source string with different code points
    depending on the font (curly U+2019 apostrophe on one page vs.
    straight U+0027 on another, en-dash vs. em-dash vs. hyphen).
    Without folding these to a common form, "DEFENDANTS' MOTION" on
    page 1 (curly) and "DEFENDANTS' MOTION" on page 5 (straight) would
    produce different keys and be detected as two separate documents.
    Labels (in _clean_footer_label) keep the original characters; only
    the comparison key is folded.

    What counts as a "digit token" here:
      * A bare 1-4 digit run, optionally preceded by a dash, "Page",
        "PAGE", or "p." and optionally followed by ".".
      * The literal word "of" between two digit tokens ("5 of 12").
    """
    if not s:
        return ""
    # Fold quote variants to ASCII apostrophe, dash variants to ASCII
    # hyphen-minus. This only affects the key, not the displayed label.
    cleaned = s.translate(_FOOTER_KEY_FOLD_MAP)
    # Strip "N of M" forms first ("5 of 12", "Page 1 of 2").
    cleaned = re.sub(
        r"(?:Page|PAGE|p\.)?\s*\d{1,4}\s+of\s+\d{1,4}",
        " ", cleaned, flags=re.IGNORECASE,
    )
    # Strip remaining standalone digit-shaped tokens with optional
    # leading dash/Page/p. and optional trailing period or dash. The
    # word boundary on both sides keeps "1281.2" (statute section) and
    # "12,345" (an unlikely but conceivable footer figure) intact —
    # we only match isolated 1-4 digit numbers, not numbers embedded
    # in a larger word. The trailing-dash allowance handles stylized
    # page indicators like "- 4 -" where the digit is bracketed by
    # dashes; without it, the leading dash gets consumed but the
    # trailing dash survives and corrupts the key.
    cleaned = re.sub(
        r"(?:^|\s)"
        r"(?:-\s*|Page\s+|PAGE\s+|p\.\s*)?"
        r"\d{1,4}"
        r"\s*[-.]?"
        r"(?=\s|$)",
        " ", cleaned, flags=re.IGNORECASE,
    )
    cleaned = cleaned.strip()
    if not cleaned:
        return ""
    return re.sub(r"\s+", " ", cleaned).upper()


# Maps used by _normalize_footer_for_key to fold typographic variants
# (curly quotes, fancy dashes) to ASCII equivalents BEFORE digit-token
# stripping. PDFs from different page sources can render the same
# source text with different Unicode code points; folding ensures the
# comparison key is stable across pages even when the underlying glyph
# code points differ. The label-cleanup pass uses no fold so the
# bookmark text preserves what the PDF actually contains.
_FOOTER_KEY_FOLD_MAP = str.maketrans({
    # Apostrophes / single quotes
    "\u2018": "'", "\u2019": "'",
    "\u201A": "'", "\u201B": "'",
    # Double quotes
    "\u201C": '"', "\u201D": '"',
    "\u201E": '"', "\u201F": '"',
    # Dash variants
    "\u2010": "-", "\u2011": "-",
    "\u2012": "-", "\u2013": "-",
    "\u2014": "-", "\u2015": "-",
    "\u2212": "-",
})


def _clean_footer_label(s: str) -> str:
    """Produce the bookmark label: same digit-stripping as the key,
    but preserve the original case and apply minimal cleanup.
    """
    if not s:
        return ""
    cleaned = s
    cleaned = re.sub(
        r"(?:Page|PAGE|p\.)?\s*\d{1,4}\s+of\s+\d{1,4}",
        " ", cleaned, flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"(?:^|\s)"
        r"(?:[-\u2010\u2011\u2012\u2013\u2014\u2015]\s*|Page\s+|PAGE\s+|p\.\s*)?"
        r"\d{1,4}"
        r"\s*[-\u2010\u2011\u2012\u2013\u2014\u2015.]?"
        r"(?=\s|$)",
        " ", cleaned, flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _extract_footer_text(page) -> str:
    """Return the joined footer text from the bottom _FOOTER_BAND_PT of
    the page, or empty string if no footer text is present.

    Works at the SPAN level rather than the row level. PyMuPDF's row
    merger ('_collect_rows') joins all spans on a shared baseline,
    which on pleading-paper layouts splices vertical-letterhead text
    in the left margin together with the real centered footer text
    on the same y. To avoid that, we walk individual spans inside
    the footer y-band and drop any span whose bbox sits entirely
    inside the left margin (x_right < _FOOTER_LEFT_MARGIN_PT). That
    cleanly excludes:
      * Pleading-paper gutter line-number digits ("28").
      * Vertical firm letterhead text ("OGLETREE, DEAKINS, NASH,
        SMOAK & STEWART, P.C.").

    Remaining spans are sorted by visual reading order (top-to-bottom,
    then left-to-right) and joined with a single space. The page-
    number stripping in _normalize_footer_for_key handles any page
    labels (leading or trailing) baked into the joined text.
    """
    try:
        d = page.get_text("dict")
    except Exception:
        return ""
    page_height = page.rect.height
    band_top = page_height - _FOOTER_BAND_PT

    # Collect surviving spans as (y_mid, x0, text) for sorting.
    spans = []
    for block in d.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for sp in line.get("spans", []):
                t = sp.get("text", "").strip()
                if not t:
                    continue
                bbox = sp.get("bbox")
                if not bbox:
                    continue
                x0, y0, x1, y1 = bbox
                y_mid = (y0 + y1) / 2
                if y_mid < band_top:
                    continue
                # Drop spans entirely inside the left margin
                # (firm letterheads, gutter line numbers).
                if x1 < _FOOTER_LEFT_MARGIN_PT:
                    continue
                # Drop lone digit tokens (lone bare page numbers) outright
                # — these otherwise survive the span filter and get joined
                # mid-string into the comparison key.
                if re.fullmatch(r"\d{1,4}", t):
                    continue
                spans.append((y_mid, x0, t))
    if not spans:
        return ""
    # Sort by y first (top-to-bottom of the footer band), then x.
    spans.sort(key=lambda s: (s[0], s[1]))
    return " ".join(s[2] for s in spans)


# ────────────────────────────────────────────────────────────────────────────
# Fuzzy footer-key matching
# ────────────────────────────────────────────────────────────────────────────
# Real-world PDF text extraction produces footer text that varies slightly
# from page to page within the same document, even after the
# digit-stripping / quote-folding normalization in _normalize_footer_for_key.
# Sources of variation:
#   * Court reporters / e-discovery vendors stamp watermark text into the
#     bottom margin ("STENO.COM (888) 707-8366", "Page 234", "YVer1f"
#     anti-piracy fingerprints). These tokens are unique per page and
#     would split a single exhibit into N sub-documents in strict matching.
#   * Stylized page indicators like "- 4 -" leave punctuation residue
#     even after digit stripping.
#   * Optional appendix labels appear only on some pages ("Exhibit A
#     Page 1 of 6" on the first page, "Page · Exhibit A Page 5 of 6" on
#     a later page).
# To handle these, we compute token-set Jaccard similarity between keys
# and treat any pair above _FOOTER_KEY_SIMILARITY_THRESHOLD as the same
# document.
#
# Safeguards against over-merging:
#   * Short footers (< _FOOTER_MIN_TOKENS_FOR_FUZZY significant tokens)
#     are compared by exact equality only — fuzzy matching on tiny token
#     sets has too much false-positive risk ("EXHIBIT A" vs "EXHIBIT B"
#     would share 1 of 2 tokens, 0.33 Jaccard, so they wouldn't merge
#     anyway, but the policy makes the intent explicit and protects
#     against future regressions).
#   * Stopwords and short tokens are dropped before comparison, so a
#     footer of mostly noise can't accidentally match a real title
#     just because both contain "for the of".
#   * First-seen-key wins: when a new page key fuzzy-matches a key we've
#     already seen, the new page inherits the prior key's identity. It
#     does NOT update the canonical key text — the canonical key stays
#     as whatever was first detected for that document.

_FOOTER_KEY_SIMILARITY_THRESHOLD = 0.7
_FOOTER_MIN_TOKENS_FOR_FUZZY = 3

# Stopwords excluded from token-set comparisons. Lowercase. The intent is
# to eliminate function words that contribute nothing to identity, so a
# single substantive token disagreement weighs more in the similarity
# score. Conservative list — only words that appear in essentially every
# title/footer in California legal practice. We intentionally do NOT
# include single-letter articles "a"/"an": exhibit identifiers like
# "Exhibit A" rely on the letter to distinguish from "Exhibit B", and
# isolated articles are rare enough in footer text that keeping them
# doesn't hurt Jaccard discrimination.
_FOOTER_FUZZY_STOPWORDS = frozenset({
    "of", "the", "and", "in", "to", "for", "by",
    "on", "at", "or", "with", "from",
})


def _fuzzy_token_set(key: str) -> frozenset:
    """Return the set of significant tokens for fuzzy comparison.

    Lowercases, strips surrounding punctuation, then drops:
      * Empty tokens (length 0 after punctuation stripping).
      * Pure-digit tokens (page numbers, phone-number fragments, year
        stamps) — these carry no identity and would inflate Jaccard
        similarity between unrelated footers that happen to share
        watermark numerics.
      * Stopwords (see _FOOTER_FUZZY_STOPWORDS).
    Single-letter tokens ARE kept: they're how exhibit identifiers
    ("Exhibit A", "Exhibit B") stay distinguishable, and the Jaccard
    threshold of 0.7 prevents incidental shared single letters from
    over-merging unrelated footers.
    Returns a frozenset for hashability so callers can cache.
    """
    if not key:
        return frozenset()
    raw_tokens = key.lower().split()
    out = set()
    for tok in raw_tokens:
        # Strip surrounding punctuation. Keep internal apostrophes
        # and dots so "bernards'" or "steno.com" stay distinguishable.
        stripped = tok.strip(".,;:!?()[]{}\u2018\u2019\u201C\u201D\"'·")
        if not stripped:
            continue
        if stripped.isdigit():
            continue
        if stripped in _FOOTER_FUZZY_STOPWORDS:
            continue
        out.add(stripped)
    return frozenset(out)


def _fuzzy_keys_equivalent(key_a: str, key_b: str,
                           tokens_a=None, tokens_b=None) -> bool:
    """Return True if two normalized footer keys should be treated as
    the same document under the fuzzy-match policy.

    Two paths to "equivalent":
      * Identical keys (cheap fast path).
      * Token-set Jaccard ≥ _FOOTER_KEY_SIMILARITY_THRESHOLD, when both
        keys have ≥ _FOOTER_MIN_TOKENS_FOR_FUZZY significant tokens.
      * SUBSET COVERAGE: the short key's tokens are a non-empty
        subset of the long key's tokens, AND the short key has ≥ 2
        significant tokens, AND the long key has ≥
        _FOOTER_MIN_TOKENS_FOR_FUZZY significant tokens. This handles
        the case where one page renders only the core title
        ("EXHIBIT A") and another page adds watermark noise around
        the same title ("STENO.COM 707-8366 EXHIBIT A"). Without
        subset coverage, the short version would never reach the
        ≥3-token gate and the two would be split into separate
        documents.

    Pre-computed token sets may be passed via tokens_a/tokens_b to
    avoid recomputation in inner loops.
    """
    if key_a == key_b:
        return True
    if tokens_a is None:
        tokens_a = _fuzzy_token_set(key_a)
    if tokens_b is None:
        tokens_b = _fuzzy_token_set(key_b)

    # Subset-coverage path. Identify short/long by token count.
    if len(tokens_a) <= len(tokens_b):
        short, long_ = tokens_a, tokens_b
    else:
        short, long_ = tokens_b, tokens_a
    if (len(short) >= 2
            and len(long_) >= _FOOTER_MIN_TOKENS_FOR_FUZZY
            and short
            and short <= long_):
        return True

    # Strict Jaccard path — both keys must have enough tokens.
    if (len(tokens_a) < _FOOTER_MIN_TOKENS_FOR_FUZZY
            or len(tokens_b) < _FOOTER_MIN_TOKENS_FOR_FUZZY):
        return False
    union = tokens_a | tokens_b
    if not union:
        return False
    inter = tokens_a & tokens_b
    return len(inter) / len(union) >= _FOOTER_KEY_SIMILARITY_THRESHOLD


def _canonicalize_key(key: str, canon_index: list) -> str:
    """Map `key` to a canonical key from `canon_index` (a list of
    previously-seen keys with their pre-computed token sets) using the
    fuzzy-equivalence rule. If no canonical match exists, append the
    new key to canon_index and return it as-is. First-seen-key wins.

    canon_index is a list of (canonical_key, token_set) tuples and is
    mutated in place.
    """
    new_tokens = _fuzzy_token_set(key)
    for canon_key, canon_tokens in canon_index:
        if _fuzzy_keys_equivalent(key, canon_key,
                                   tokens_a=new_tokens,
                                   tokens_b=canon_tokens):
            return canon_key
    canon_index.append((key, new_tokens))
    return key


def _detect_document_footers(doc, log: logging.Logger):
    """Walk the document; for each transition to a new unique footer,
    record the page where the new footer first appears. Returns a list
    of (label, page_idx) tuples, or [] if fewer than 2 distinct footers
    are detected (single-document file — no value in a sub-document
    bookmark branch).

    Implementation notes:
      * Pages with no detectable footer inherit the previous page's
        footer key for grouping (they're "inside" the prior sub-doc).
      * 1-page flicker (A → B → A) is suppressed by buffering one page
        of look-ahead: a new key only commits if the next page either
        also has the new key, has no footer (still inside the new
        sub-doc), or has a *different* new key (i.e. moves forward to
        another sub-doc rather than reverting).
      * Same-key reappearance later in the file is ignored — we only
        bookmark the *first* occurrence of each key. Tracked via
        `seen_keys`.
    """
    if len(doc) < 2:
        # Single-page documents don't need a Documents branch.
        return []

    # First pass: per-page (raw_text, key). Empty key means "inherit
    # from previous page". Keys are canonicalized via fuzzy matching:
    # when a page's normalized key is "close enough" (≥70% Jaccard
    # similarity on significant tokens) to a previously-seen canonical
    # key, it inherits that canonical key. This handles per-page
    # variation introduced by court-reporter watermarks, stylized page
    # indicators, and other low-information noise that survives the
    # strict-normalization pass. See the comment block above
    # _fuzzy_token_set for the rationale.
    canon_index: list = []  # list of (canonical_key, token_set)
    per_page = []
    for page in doc:
        raw = _extract_footer_text(page)
        if raw:
            strict_key = _normalize_footer_for_key(raw)
            key = _canonicalize_key(strict_key, canon_index) if strict_key else ""
        else:
            key = ""
        per_page.append((raw, key))

    # Forward-fill empty keys from the previous non-empty key. Pages
    # before the first detected footer keep an empty key.
    filled = []
    prev_key = ""
    prev_raw = ""
    for raw, key in per_page:
        if key:
            filled.append((raw, key))
            prev_key = key
            prev_raw = raw
        else:
            # Inherit prior key (and reuse its raw text for label
            # purposes — won't be used unless this page becomes a
            # boundary, which it won't, since key matches prior).
            filled.append((prev_raw, prev_key))

    # Walk filled keys; collect first-appearance boundaries with the
    # 1-page-flicker guard. A boundary is committed when:
    #   * The page's key differs from the previously-committed key
    #     (or this is the first non-empty key in the file), AND
    #   * The new key has not been seen before, AND
    #   * Either: this is the last page, OR the next page's key is
    #     not equal to the previously-committed key (i.e. we don't
    #     immediately revert — that would be flicker).
    entries = []
    seen_keys = set()
    last_committed_key = ""
    n = len(filled)
    for i, (raw, key) in enumerate(filled):
        if not key:
            # Pages before any footer ever appears.
            continue
        if key == last_committed_key:
            continue
        if key in seen_keys:
            # Reappearance later in the file: per user spec, do NOT
            # create a second bookmark. We also DON'T update
            # last_committed_key — if the document flips back to an
            # earlier footer and then to yet another new one, the next
            # new one is still a fresh sub-document.
            last_committed_key = key
            continue
        # Flicker check: if the *next* page reverts to last_committed_key,
        # this page is a 1-page noise blip, not a real sub-document.
        # 1-page sub-docs are allowed only when they don't revert.
        next_key = filled[i + 1][1] if i + 1 < n else None
        if (last_committed_key and next_key == last_committed_key
                and key != last_committed_key):
            # Flicker: skip this page, don't commit, don't mark seen.
            # The next iteration will pick up the reverted key (but
            # last_committed_key already equals it, so it'll be a no-op).
            continue
        # Commit a new boundary.
        label = _clean_footer_label(raw)
        if not label:
            # Shouldn't happen — non-empty key implies non-empty raw —
            # but guard anyway.
            continue
        entries.append((label, i))
        seen_keys.add(key)
        last_committed_key = key

    # Gate: need at least 2 distinct footers for the branch to be useful.
    if len(entries) < 2:
        return []

    log.info(f"  Detected {len(entries)} sub-document(s) by unique footer")
    return entries


def _build_bookmark_tree(doc, toc_entries, exhibit_cover_map,
                        paragraph_anchors, cause_entries=None,
                        document_entries=None, section_entries=None,
                        toc_page_range=None):
    """Assemble the [level, title, page_1_based] list that doc.set_toc
    expects. Returns the list, or None if there's nothing worth adding.

    toc_entries:        [(label, target_page_index), ...]
    exhibit_cover_map:  {ident: [page_indices]}
    paragraph_anchors:  [(page_index, paragraph_num), ...]
    cause_entries:      [(label, target_page_index), ...] — ordered by
                        ordinal number, one entry per distinct cause of
                        action. Only populated for complaint files.
    document_entries:   [(label, target_page_index), ...] — one entry per
                        sub-document detected by unique footer text, in
                        page order. Populated for combined filings where
                        multiple sub-docs share one PDF (e.g. Motion +
                        Declaration + Exhibits concatenated together).
    section_entries:    [(label, page_index), ...] — section headings
                        detected by _detect_section_headings, in
                        document order. Only populated for briefs (the
                        filename-skip gate excludes declarations and
                        complaints).
    toc_page_range:     (start, end_inclusive) page-index range of the
                        TOC itself, or None. The Contents branch header
                        is pointed at this range's start page so
                        clicking "Contents" navigates to the actual
                        TOC page rather than the first entry's target.

    Hierarchy rules (from user spec):
      * Contents and Causes of Action are flat top-level branches.
      * Exhibits and Documents are top-level branches whose children are
        the individual exhibit / sub-document entries.
      * Sections (when present) nest under whichever Document contains
        their page. If no Documents exist, sections become a top-level
        "Sections" branch. Sections inside an exhibit's page range are
        dropped — exhibits don't get section bookmarks.
      * Paragraphs nest under whichever Section, Document, or Exhibit
        owns their page, in that priority order. A paragraph at page P
        nests under the Section that contains P if any; else under the
        Document; else under the Exhibit; else (no parent) appears in
        the top-level fallback Paragraphs branch.
      * Exhibits take precedence over Documents on contested pages:
        once the document enters its first exhibit's page range, all
        subsequent paragraphs nest under exhibits regardless of any
        footer-detected sub-document that may continue.
      * A sub-document whose start page falls inside an exhibit's page
        range becomes a CHILD of that exhibit, not a top-level Documents
        entry. Its paragraphs then nest under it (one level deeper).
      * Inside an exhibit with both direct paragraphs (no inner sub-doc)
        AND a child sub-document, the direct paragraphs come first and
        the sub-document(s) follow. (Within each group, page order.)
      * Redundant nested labels suppressed: a sub-document inside
        Exhibit N whose cleaned label is just "Exhibit N" / "EXHIBIT N" /
        "Exhibit N — something-trivial" is dropped — the exhibit
        bookmark already covers it.
      * If paragraphs exist but no Documents/Exhibits/Sections do, the
        Paragraphs branch falls back to a top-level flat list so
        standalone declarations still get paragraph navigation.
    """
    n_pages = len(doc)
    tree = []

    # ── Contents (flat, top-level) ──────────────────────────────────────
    valid_toc = [(lbl, p) for (lbl, p) in toc_entries if 0 <= p < n_pages]
    if valid_toc:
        # Branch header points at the TOC's own page (where "TABLE OF
        # CONTENTS" appears), not at the first entry's target. So
        # clicking "Contents" in the bookmark sidebar navigates to the
        # TOC page itself. If toc_page_range is unavailable for any
        # reason, fall back to the first entry's target page.
        contents_header_page = (toc_page_range[0] + 1
                                if toc_page_range
                                else valid_toc[0][1] + 1)
        tree.append([1, "Contents", contents_header_page])
        for label, page_idx in valid_toc:
            tree.append([2, label, page_idx + 1])

    # ── Causes of Action (flat, top-level) ──────────────────────────────
    valid_causes = [(lbl, p) for (lbl, p) in (cause_entries or [])
                    if 0 <= p < n_pages]
    if valid_causes:
        tree.append([1, "Causes of Action", valid_causes[0][1] + 1])
        for label, page_idx in valid_causes:
            tree.append([2, label, page_idx + 1])

    # ── Compute page-range ownership for Documents and Exhibits ─────────
    # Each document/exhibit owns a contiguous range [start, end_inclusive].
    # Documents end where the next document starts OR where the first
    # exhibit cover begins (exhibits take precedence).
    # Exhibits end where the next exhibit cover begins.
    valid_docs = sorted(
        [(lbl, p) for (lbl, p) in (document_entries or [])
         if 0 <= p < n_pages],
        key=lambda x: x[1],
    )
    exhibits_sorted = sorted(
        ((ident, pages[0]) for ident, pages in (exhibit_cover_map or {}).items()
         if pages and 0 <= pages[0] < n_pages),
        key=lambda x: (x[1], _exhibit_sort_key(x[0])),
    )

    # The page where exhibits start (exhibits take precedence past here).
    first_exhibit_page = exhibits_sorted[0][1] if exhibits_sorted else n_pages

    # Build exhibit ranges: each exhibit owns from its cover page to one
    # before the next exhibit's cover page. The LAST exhibit normally
    # runs to the end of the document, but there's one important case
    # where it must end sooner: a TRAILING POST-EXHIBIT DOCUMENT, like
    # a Proof of Service appearing after Exhibit C. Without capping,
    # such a document would be nested under the last exhibit (just
    # because nothing else followed it) instead of being a top-level
    # peer.
    #
    # To distinguish a trailing post-exhibit document from a genuine
    # sub-document INSIDE an exhibit (e.g. Exhibit 5 is itself a
    # declaration with its own "Declaration of Smith" footer), we
    # require a confirmation signal that the exhibit had its own
    # running footer text: at least one footer-detected document inside
    # the tentative exhibit range whose cleaned label is redundant
    # with the exhibit's identifier (e.g. footer "EXHIBIT C" detected
    # on pages within Exhibit C's range). The presence of this
    # redundant entry means there's a clear "this is still the
    # exhibit" footer marker, so when the footer changes to a non-
    # redundant label, we know the exhibit's content has ended.
    #
    # Without this signal — e.g. exhibits whose content pages have no
    # footer at all — we don't cap, and any sub-document detected
    # inside the tentative range gets nested as before.
    exhibit_ranges = []  # list of (ident, start_idx, end_inclusive)
    for i, (ident, start) in enumerate(exhibits_sorted):
        if i + 1 < len(exhibits_sorted):
            end = exhibits_sorted[i + 1][1] - 1
        else:
            end = n_pages - 1
            # Tentative range is [start, n_pages-1]. Check whether any
            # footer-detected document inside this range has a redundant
            # label — i.e. the exhibit has its own running footer.
            has_redundant_marker = any(
                start <= d_start <= end
                and _label_is_just_exhibit_id(d_lbl, ident)
                for d_lbl, d_start in valid_docs
            )
            if has_redundant_marker:
                # Look for a post-exhibit, non-redundant Document to
                # cap at.
                for d_lbl, d_start in valid_docs:
                    if d_start <= start:
                        continue
                    if _label_is_just_exhibit_id(d_lbl, ident):
                        continue
                    end = d_start - 1
                    break
        exhibit_ranges.append((ident, start, end))

    # Partition documents: top-level vs. nested-under-exhibit. A document
    # whose start page is within some exhibit's range becomes that
    # exhibit's child; otherwise it's top-level.
    def _containing_exhibit(page_idx):
        for ident, start, end in exhibit_ranges:
            if start <= page_idx <= end:
                return ident
        return None

    top_level_docs = []           # [(label, start_idx, end_inclusive), ...]
    nested_docs_by_exhibit = {}   # {ident: [(label, start, end_inclusive)]}
    for i, (lbl, start) in enumerate(valid_docs):
        # Range end of this document candidate: bounded by the next
        # document's start AND by the first exhibit page (documents
        # cede to exhibits at that boundary).
        next_doc_start = (valid_docs[i + 1][1]
                          if i + 1 < len(valid_docs) else n_pages)
        end = min(next_doc_start, first_exhibit_page, n_pages) - 1
        containing = _containing_exhibit(start)
        if containing is not None:
            # Nested under the exhibit. The end is bounded by the
            # exhibit's own end too — a sub-document can't extend past
            # its parent exhibit.
            for ex_ident, ex_start, ex_end in exhibit_ranges:
                if ex_ident == containing:
                    # The nested doc's end is bounded by the NEXT nested
                    # doc in the same exhibit (if any) OR the exhibit's
                    # own end, whichever comes first.
                    next_in_same_ex = None
                    for j in range(i + 1, len(valid_docs)):
                        _, p_next = valid_docs[j]
                        if ex_start <= p_next <= ex_end:
                            next_in_same_ex = p_next
                            break
                    nested_end = (next_in_same_ex - 1
                                  if next_in_same_ex is not None
                                  else ex_end)
                    # Redundant-label suppression: if the cleaned label
                    # is essentially just the exhibit identifier
                    # ("Exhibit N", "EXHIBIT N", "Ex. N"), drop it.
                    if _label_is_just_exhibit_id(lbl, ex_ident):
                        break
                    nested_docs_by_exhibit.setdefault(ex_ident, []).append(
                        (lbl, start, nested_end)
                    )
                    break
        else:
            # Top-level document. Its end is bounded by the first
            # exhibit page (exhibits take precedence past that point).
            top_level_docs.append((lbl, start, end))

    # ── Section partitioning ────────────────────────────────────────────
    # Each section owns a contiguous range from its start page to one
    # before the next section's start (or to the end of its containing
    # Document, whichever comes first). Sections inside exhibit ranges
    # are dropped — exhibits don't carry sections. Sections that fall
    # outside any Document range, when no Documents exist at all,
    # become top-level under a "Sections" branch.
    valid_sections = sorted(
        [(lbl, p) for (lbl, p) in (section_entries or [])
         if 0 <= p < n_pages],
        key=lambda x: x[1],
    )
    # Drop sections inside any exhibit range.
    valid_sections = [(lbl, p) for (lbl, p) in valid_sections
                      if _containing_exhibit(p) is None]

    # Map each section to its containing Document (or None if it falls
    # outside all Document ranges — possible when no Documents exist).
    # Compute each section's page-range end: bounded by the next section
    # in the same parent (or globally if top-level), and by the parent
    # Document's end if any.
    sections_in_doc = {}  # doc_index_in_top_level_docs -> [(lbl, start, end)]
    top_level_sections = []  # [(lbl, start, end), ...] when no Documents

    def _containing_doc_idx(page_idx):
        for di, (_, dstart, dend) in enumerate(top_level_docs):
            if dstart <= page_idx <= dend:
                return di
        return None

    for si, (lbl, start) in enumerate(valid_sections):
        # End of section: next section's start - 1, capped by containing
        # parent's end.
        next_section_start = (valid_sections[si + 1][1]
                              if si + 1 < len(valid_sections)
                              else n_pages)
        di = _containing_doc_idx(start)
        if di is not None:
            parent_end = top_level_docs[di][2]
            # Only allow next-section bound if that section is in the
            # same parent Document. Otherwise this section runs to
            # parent_end.
            if next_section_start - 1 > parent_end:
                end = parent_end
            else:
                # Check that the next section is still in this Document
                # (if not, this section runs to parent_end).
                next_di = _containing_doc_idx(next_section_start)
                if next_di == di:
                    end = next_section_start - 1
                else:
                    end = parent_end
            sections_in_doc.setdefault(di, []).append((lbl, start, end))
        else:
            # No containing Document — only relevant when there are no
            # Documents at all. If Documents exist but this section
            # falls outside them all, drop the section.
            if not top_level_docs:
                end = min(next_section_start - 1, n_pages - 1)
                # Cap by first exhibit if any (sections don't extend
                # into exhibit territory).
                if exhibits_sorted:
                    end = min(end, first_exhibit_page - 1)
                if end >= start:
                    top_level_sections.append((lbl, start, end))

    # ── Paragraphs: filter to valid page range; dedup happens per-range ─
    # The source list records the lowest paragraph number that *starts*
    # on each page, so duplicates within one sub-document shouldn't
    # occur. Global dedup would be incorrect because paragraph numbers
    # reset at each sub-document boundary (every declaration starts at
    # ¶ 1). We dedup inside _paragraphs_in_range so each range gets a
    # fresh dedup window.
    valid_paras = [(p_idx, num) for (p_idx, num) in (paragraph_anchors or [])
                   if 0 <= p_idx < n_pages]

    # Helper: emit the paragraphs that fall within [start, end_inclusive]
    # at a given indent level. Paragraphs are filtered by page range and
    # deduplicated against consecutive identical numbers WITHIN this range.
    def _paragraphs_in_range(start, end_inclusive):
        out = []
        last_num = None
        for (p_idx, num) in valid_paras:
            if not (start <= p_idx <= end_inclusive):
                continue
            if num == last_num:
                continue
            out.append((p_idx, num))
            last_num = num
        return out

    # Helper: emit paragraphs in [start, end_inclusive] that do NOT fall
    # inside any of the given sub-ranges (which represent child
    # sub-document or section ranges that will get their paragraphs
    # under their own bookmarks).
    def _paragraphs_in_range_excluding(start, end_inclusive, sub_ranges):
        def _in_any(p_idx):
            return any(s <= p_idx <= e for s, e in sub_ranges)
        return [(p_idx, num) for (p_idx, num)
                in _paragraphs_in_range(start, end_inclusive)
                if not _in_any(p_idx)]

    # ── Documents branch (top-level) ────────────────────────────────────
    if top_level_docs:
        tree.append([1, "Documents", top_level_docs[0][1] + 1])
        for di, (lbl, start, end) in enumerate(top_level_docs):
            tree.append([2, lbl, start + 1])
            sections_here = sections_in_doc.get(di, [])
            section_ranges = [(s, e) for (_, s, e) in sections_here]
            # Direct paragraphs of the Document: those not under any
            # section in this Document.
            for p_idx, num in _paragraphs_in_range_excluding(
                    start, end, section_ranges):
                tree.append([3, f"\u00b6 {num}", p_idx + 1])
            # Sections under this Document, each with its paragraphs.
            for slbl, s_start, s_end in sections_here:
                tree.append([3, slbl, s_start + 1])
                for p_idx, num in _paragraphs_in_range(s_start, s_end):
                    tree.append([4, f"\u00b6 {num}", p_idx + 1])

    # ── Sections branch (top-level, when no Documents) ──────────────────
    # Sections become a top-level branch only when there are no
    # Documents to nest them under. This is the standalone-brief case
    # — single document with detected section headings.
    if not top_level_docs and top_level_sections:
        tree.append([1, "Sections", top_level_sections[0][1] + 1])
        for slbl, s_start, s_end in top_level_sections:
            tree.append([2, slbl, s_start + 1])
            for p_idx, num in _paragraphs_in_range(s_start, s_end):
                tree.append([3, f"\u00b6 {num}", p_idx + 1])

    # ── Exhibits branch (top-level, with optional nested docs) ──────────
    if exhibits_sorted:
        tree.append([1, "Exhibits", exhibits_sorted[0][1] + 1])
        for ident, ex_start, ex_end in exhibit_ranges:
            tree.append([2, f"Exhibit {ident}", ex_start + 1])
            # Direct paragraphs of this exhibit: paragraphs whose page is
            # within the exhibit's range but NOT within any nested doc's
            # range. Per user spec, these come BEFORE the nested
            # sub-documents in the bookmark tree.
            nested = nested_docs_by_exhibit.get(ident, [])
            nested_page_ranges = [(n_start, n_end)
                                  for (_, n_start, n_end) in nested]

            direct_paras = _paragraphs_in_range_excluding(
                ex_start, ex_end, nested_page_ranges)
            for p_idx, num in direct_paras:
                tree.append([3, f"\u00b6 {num}", p_idx + 1])
            # Nested sub-documents and their paragraphs.
            for nlbl, n_start, n_end in nested:
                tree.append([3, nlbl, n_start + 1])
                for p_idx, num in _paragraphs_in_range(n_start, n_end):
                    tree.append([4, f"\u00b6 {num}", p_idx + 1])

    # ── Paragraphs top-level fallback ───────────────────────────────────
    # If neither Documents nor Exhibits nor Sections exist but there
    # ARE paragraphs, show them as a flat top-level branch — preserves
    # the standalone-declaration use case.
    if (valid_paras and not top_level_docs and not exhibits_sorted
            and not top_level_sections):
        all_paras = _paragraphs_in_range(0, n_pages - 1)
        if all_paras:
            tree.append([1, "Paragraphs", all_paras[0][0] + 1])
            for page_idx, num in all_paras:
                tree.append([2, f"\u00b6 {num}", page_idx + 1])

    return tree if tree else None


# Match labels that are essentially just an exhibit identifier — used to
# suppress redundant nested bookmarks inside the exhibit they belong to.
# "Exhibit 5", "EXHIBIT 5", "Ex. 5", "Exhibit B", "EXHIBIT AA". Allows
# optional trailing punctuation. The label has ALREADY been stripped of
# its page-number tail by _clean_footer_label upstream, so this is
# purely a label-shape match.
_LABEL_JUST_EXHIBIT_RE = re.compile(
    r"^\s*(?:Exhibit|EXHIBIT|Ex\.?|EX\.?|Exh\.?|EXH\.?)\s+([A-Za-z0-9]+)\s*[.:]?\s*$"
)


def _label_is_just_exhibit_id(label: str, ident: str) -> bool:
    """Return True if `label` (a sub-document label) is essentially just
    the identifier of `ident` (an exhibit identifier). Used to suppress
    redundant nested bookmarks.

    Numeric idents are compared numerically (so "Exhibit 5" matches
    ident "5"); letter idents are compared case-insensitively.
    """
    m = _LABEL_JUST_EXHIBIT_RE.match(label or "")
    if not m:
        return False
    label_id = m.group(1)
    if ident.isdigit() and label_id.isdigit():
        return int(label_id) == int(ident)
    return label_id.upper() == ident.upper()


def _set_bookmarks(doc, toc_entries, exhibit_cover_map, paragraph_anchors,
                   log: logging.Logger, cause_entries=None,
                   document_entries=None, section_entries=None,
                   toc_page_range=None):
    """Build and apply the bookmark outline. No-op if all inputs are
    empty. Failure is non-fatal — the function logs and returns."""
    try:
        tree = _build_bookmark_tree(doc, toc_entries, exhibit_cover_map,
                                    paragraph_anchors, cause_entries,
                                    document_entries, section_entries,
                                    toc_page_range)
        if not tree:
            return
        doc.set_toc(tree)
        # Count second-level entries (the actual bookmarks; level 1 are
        # the branch headers) for the log line.
        n_leaves = sum(1 for entry in tree if entry[0] == 2)
        branches = [entry[1] for entry in tree if entry[0] == 1]
        log.info(f"  Bookmarks: {n_leaves} entry(ies) across "
                 f"{', '.join(branches)}")
    except Exception as e:
        log.warning(f"  Bookmark generation failed (non-fatal): {e}")


# ────────────────────────────────────────────────────────────────────────────
# Main per-PDF processing
# ────────────────────────────────────────────────────────────────────────────
def process_pdf(pdf_path: Path, log: logging.Logger,
                provider: str = "lexis") -> bool:
    """Process one PDF. Returns True on success."""
    try:
        import fitz
    except ImportError:
        log.error("PyMuPDF (fitz) not installed - aborting. "
                  "Install with: pip install pymupdf")
        return False

    log.info(f"Processing: {pdf_path.name}")
    out_path = pdf_path  # Output will overwrite the original (after we're done with it)
    temp_path = pdf_path.with_name(pdf_path.stem + "_temp.pdf")
    if temp_path.exists():
        log.info(f"  Skipping - {temp_path.name} already exists (temp file)")
        return True

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        log.error(f"  Could not open PDF: {e}")
        return False

    # Check whether any page lacks text. The OCR gate is intentionally
    # triggered by "any page lacks text" rather than "every page lacks
    # text" — mixed-state documents are common in declarations, where the
    # body and exhibit content pages have text but image-only "EXHIBIT A"
    # cover sheets do not. Without per-page OCR, the cover sheets stay
    # textless, _find_exhibit_cover_pages can't see them, and exhibit
    # linking silently produces nothing. _ocr_pdf itself has its own
    # per-page check (it skips any page that already has text), so this
    # outer gate just needs to admit any document with at least one
    # textless page. Idempotent across re-runs because re-runs find every
    # page already has text and _ocr_pdf is a no-op.
    any_textless = any(not page.get_text("text").strip() for page in doc)
    if any_textless:
        textless_count = sum(1 for p in doc if not p.get_text("text").strip())
        if textless_count == len(doc):
            log.info("  No text layer detected - running OCR")
        else:
            log.info(f"  {textless_count} page(s) lack text - running OCR "
                     f"on those page(s)")
        _ocr_pdf(doc, log)

    # Skip link insertion for declarations and separate statements: they
    # rarely contain citation-worthy material in Zachary's workflow, and
    # avoiding the link-insertion pass eliminates spurious annotations on
    # body text that happens to share substrings with TOA citations from
    # related briefing. The right-margin markers still get injected below —
    # those are independent of the link annotations and are exactly what
    # the Word paste macro relies on for declaration citations.
    skip_links = should_skip_linking(pdf_path.name)
    if skip_links:
        log.info(f"  Skipping link insertion (Decl./Separate Statement): "
                 f"{pdf_path.name}")
        all_cites = []
    else:
        # Build full-document text + per-page text spans for supra resolution
        page_texts = []
        for page in doc:
            page_texts.append(page.get_text("text"))

        full_text = "\n\f\n".join(page_texts)
        all_cites = find_all_citations(full_text)
        log.info(f"  Found {len(all_cites)} citations")

    # For each citation, locate occurrences on each page using PyMuPDF's
    # search_for, and add (1) a clickable link annotation and (2) a blue
    # underline annotation. We keep the original text colour untouched —
    # changing text colour on existing PDFs requires redacting and
    # reinserting glyphs, which shifts layout in unpredictable ways. The
    # blue underline plus clickability is unambiguous as a hyperlink cue
    # and matches how other PDF tools (e.g. Adobe Acrobat's web-link
    # converter) handle the same job.
    #
    # CRITICAL — multi-line citations: if a citation in the source text
    # spans a line break (e.g., "Smith v. Jones (2017)\n13 Cal.App.5th 1152"),
    # `match_text` will contain that newline, and `page.search_for(match_text)`
    # returns nothing because PyMuPDF doesn't match across line breaks.
    # The previous fallback — searching for `match_text.splitlines()[0]` —
    # was unsafe: when the first line was a generic substring like "Cal."
    # or "Smith", `search_for` returned matches all over the document and
    # every "Cal." on every page got linked to the same wrong URL.
    # Instead, we now split the match into both halves and require BOTH
    # to be found nearby on the SAME page. If only one half is on a page,
    # we annotate just that half rather than blasting links across unrelated
    # text. We also reject any single-fragment search whose fragment is
    # too short or too generic to be meaningful (`_is_safe_fragment`).
    link_count = 0
    linked_rects: dict = {}

    # Pre-seed linked_rects with link annotations already on each page so a
    # re-run on an already-linked PDF doesn't stack duplicate URI links and
    # double-paint the blue underline. The same `_already_linked` substantial-
    # overlap check that prevents duplicates within one run also catches
    # rects covered by a prior run.
    for _seed_page in doc:
        for _seed_ln in _seed_page.get_links():
            _seed_rect = _seed_ln.get("from")
            if _seed_rect:
                linked_rects.setdefault(_seed_page.number, []).append(_seed_rect)

    def _already_linked(page_num: int, rect) -> bool:
        for r in linked_rects.get(page_num, []):
            inter = rect & r
            if not inter.is_empty:
                smaller = min(rect.get_area(), r.get_area())
                if smaller > 0 and inter.get_area() / smaller > 0.5:
                    return True
        return False

    def _record_linked(page_num: int, rect) -> None:
        linked_rects.setdefault(page_num, []).append(rect)

    for cite in all_cites:
        url = resolve_url(cite, provider)
        if not url:
            continue
        match_text = cite["match_text"]
        found_anywhere = False
        for page in doc:
            quads = _safe_search_for_citation(page, match_text, cite)
            if not quads:
                continue
            for q in quads:
                rect = q.rect
                # Skip quads in the right-margin page-number column:
                # search_for can return a separate quad for the page-ref
                # numbers ("13, 19") on TOA lines. Those quads have x0 well
                # into the right margin. Suppress them so links only cover
                # the citation text, not the page references.
                if rect.x0 > page.rect.width - 90:
                    continue
                # Skip if already covered by a previously-inserted link
                # (prevents duplicate annotations when multiple citation
                # patterns match the same text, e.g. RPC "1.9" and "1.9(a)").
                if _already_linked(page.number, rect):
                    continue
                _record_linked(page.number, rect)
                # 1. Clickable link
                page.insert_link({
                    "kind": fitz.LINK_URI,
                    "from": rect,
                    "uri": url,
                })
                # 2. Blue underline
                underline_y = rect.y1 - 0.5
                page.draw_line(
                    fitz.Point(rect.x0, underline_y),
                    fitz.Point(rect.x1, underline_y),
                    color=LINK_COLOUR,
                    width=1.0,
                )
                found_anywhere = True
        if found_anywhere:
            link_count += 1

    # After all full citations are linked, do a second pass for short-form
    # case references — bare "X v. Y" mentions (no reporter or date) — and
    # link them to the URL of the matching full citation. This handles the
    # common pattern where a brief introduces "Chillon v. Ford Motor Co.,
    # 2023 WL 3035369..." once and then refers to it as just "Chillon v.
    # Ford" or "Chillon v. Ford Motor Co." in the surrounding discussion.
    # Skipped when link insertion is suppressed (Decl./Separate Statement).
    if not skip_links and all_cites:
        link_count += _link_short_form_cases(doc, all_cites, provider, log)

    log.info(f"  Linked {link_count} citation occurrence(s)")

    # Add internal jumps for any Table of Contents found in the front matter.
    # Skipped for the same filename patterns that skip citation linking
    # (Decl./Decl./Separate Statement/Complaint/FAC/SAC/TAC/Proof of Service):
    # those documents don't carry TOCs in Zachary's workflow, and any
    # TOC-shaped match in their body text would be a false positive.
    # Failure here is non-fatal.
    #
    # toc_page_range is the (start, end_inclusive) page-index range
    # occupied by the TOC itself. The bookmark builder uses it to point
    # the Contents branch header at the TOC page; the section-heading
    # detector uses it to skip TOC pages during its scan (heading text
    # inside the TOC is already represented by the Contents children).
    toc_entries: list = []
    toc_page_range = None
    if not skip_links:
        try:
            _, toc_entries, toc_page_range = _link_toc_entries(doc, log)
        except Exception as e:
            log.warning(f"  TOC linking failed (non-fatal): {e}")

    # Section-heading detection. Runs unconditionally on briefs (the
    # same skip_links gate that excludes declarations and complaints
    # excludes them here too). Always-on rather than a TOC fallback:
    # a brief that HAS a TOC may also have pre-numbered headings
    # ("SUMMARY OF ARGUMENT") that wouldn't appear in the TOC because
    # they precede the formal Roman-numeral structure. Those still
    # get bookmarked. The TOC page range is passed in so the scan
    # skips TOC pages (which would otherwise produce phantom heading
    # bookmarks for every TOC entry). Failure is non-fatal.
    section_entries: list = []
    if not skip_links:
        try:
            section_entries = _detect_section_headings(
                doc, log, toc_page_range=toc_page_range)
        except Exception as e:
            log.warning(f"  Section heading detection failed (non-fatal): {e}")

    # Link body references to exhibit pages — this runs regardless of the
    # filename skip rules, because the document type most likely to need it
    # is a Declaration ("Attached hereto as Exhibit 1 is..."), which IS on
    # the skip list. The pass gates itself on the number of detected
    # exhibit covers (>= 2) inside _link_exhibit_references. Failure here
    # is non-fatal.
    exhibit_cover_map: dict = {}
    try:
        _, exhibit_cover_map = _link_exhibit_references(doc, log)
    except Exception as e:
        log.warning(f"  Exhibit linking failed (non-fatal): {e}")

    # Insert invisible right-margin markers so the PasteLegalQuotation macro
    # can auto-generate citations on PDF paste. See _insert_right_margin_markers
    # for the design rationale. Failure here is non-fatal: the linked PDF is
    # still useful even if marker insertion fails.
    paragraph_anchors: list = []
    try:
        _, paragraph_anchors = add_right_margin_markers(pdf_path, doc, log)
    except Exception as e:
        log.warning(f"  Right-margin marker insertion failed (non-fatal): {e}")

    # Cause-of-action detection and linking for complaints (and amended
    # complaints — FAC/SAC/TAC). Runs on its own gate, independent of
    # `skip_links` (citation/TOC linking is still suppressed for these
    # files — only the cause-of-action structure is added). Produces:
    #   - bookmark entries for the "Causes of Action" branch
    #   - GOTO links from cover-page listings to body headings, when
    #     the cover lists causes in the same ALL-CAPS form.
    # Failure is non-fatal: bookmarks and citation linking still ship
    # even if cause detection fails.
    cause_entries: list = []
    if is_complaint(pdf_path.name):
        try:
            cause_entries, cover_occs, body_occs = _detect_causes_of_action(
                doc, log)
            if cause_entries:
                log.info(f"  Detected {len(cause_entries)} cause(s) of action")
                _link_cover_to_causes(doc, cover_occs, body_occs, log)
        except Exception as e:
            log.warning(f"  Cause-of-action detection failed (non-fatal): {e}")

    # Detect combined-filing sub-documents by unique footer text. Runs
    # on every file; if there's only one distinct footer (typical for
    # standalone briefs and declarations), the function returns []
    # and no Documents branch appears. Failure is non-fatal.
    document_entries: list = []
    try:
        document_entries = _detect_document_footers(doc, log)
    except Exception as e:
        log.warning(f"  Footer-based document detection failed (non-fatal): {e}")

    # Build the PDF outline (sidebar bookmarks) from the structure the
    # three passes above collected. set_toc replaces atomically, so this
    # is idempotent across re-runs and discards any pre-existing outline
    # the source PDF came with. Failure is non-fatal.
    _set_bookmarks(doc, toc_entries, exhibit_cover_map,
                   paragraph_anchors, log, cause_entries=cause_entries,
                   document_entries=document_entries,
                   section_entries=section_entries,
                   toc_page_range=toc_page_range)

    try:
        # Save to temp file first
        doc.save(str(temp_path), garbage=3, deflate=True)
        log.info(f"  Saved to temp: {temp_path.name}")
    except Exception as e:
        log.error(f"  Could not save linked PDF: {e}")
        doc.close()
        return False
    finally:
        doc.close()

    # Replace original with the linked version
    try:
        import shutil
        shutil.move(str(temp_path), str(out_path))
        log.info(f"  Replaced original: {out_path.name}")
    except Exception as e:
        log.error(f"  Could not replace original PDF: {e}")
        return False

    return True


# ────────────────────────────────────────────────────────────────────────────
# Entry point
# ────────────────────────────────────────────────────────────────────────────
def main():
    # Backward-compatible CLI: positional <folder>, plus optional --provider.
    # The mail-merge macro calls `pythonw pdf_linker.py "<folder>"` with no
    # flag, which keeps the historical Westlaw-default behaviour.
    import argparse

    parser = argparse.ArgumentParser(
        description="Add citation hyperlinks to PDFs in a case folder."
    )
    parser.add_argument("folder", help="Folder containing PDFs to link.")
    parser.add_argument(
        "--provider",
        choices=("westlaw", "lexis"),
        default="lexis",
        help="Which service citations should resolve to (default: lexis). "
             "Selects the search-URL form used for each citation.",
    )
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"Not a folder: {folder}")
        sys.exit(1)

    log_path = folder / "pdf_linker.log"
    logging.basicConfig(
        filename=str(log_path),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        filemode="a",
    )
    log = logging.getLogger("pdf_linker")
    log.info("=" * 60)
    log.info(f"Run started for folder: {folder} (provider={args.provider})")

    # Collect PDFs excluding _linked and _temp files, then sort by file size (smallest first)
    pdfs = [p for p in folder.glob("*.pdf") 
            if not p.stem.endswith("_linked") and not p.stem.endswith("_temp")]
    pdfs = sorted(pdfs, key=lambda p: p.stat().st_size)
    log.info(f"Found {len(pdfs)} PDF(s) to process (sorted by size)")

    success = 0
    failed = 0
    for pdf in pdfs:
        try:
            if process_pdf(pdf, log, provider=args.provider):
                success += 1
            else:
                failed += 1
        except Exception as e:
            log.error(f"Unhandled error processing {pdf.name}: {e}")
            log.error(traceback.format_exc())
            failed += 1

    log.info(f"Done: {success} succeeded, {failed} failed")


if __name__ == "__main__":
    main()
