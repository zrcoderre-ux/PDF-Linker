# Project workflow

## Branch & merge policy (standing instruction from the repo owner)

- **Always work on the existing branch `claude/clever-franklin-glawt6`.** Do
  not create new feature branches — the owner cannot delete branches and does
  not want an ever-growing list. Reuse this one for every task.
- **After completing edits on a task, finish the loop automatically without
  waiting to be asked:**
  1. Commit and push to `claude/clever-franklin-glawt6`.
  2. Open a pull request into `main` (a new PR each time, since the prior one
     is merged/closed).
  3. Merge the pull request using **squash merge** (keeps `main` linear, one
     commit per task).
- Apply this on every task going forward, not just when explicitly requested.

# Architecture overview

**What it is.** A single module, `pdf_linker.py` (~12.5k lines), plus `tests/`
(pytest, ~500 tests). It does two jobs on a folder of California legal-filing
PDFs:

1. **Pseudonymize** the plain-text `.txt` exports — party/attorney/entity/
   declarant names, court personnel, PII (SSN/email/phone/address/URL), and
   case/department numbers become stable deterministic fakes, while published
   **case citations are left byte-for-byte intact** (renaming an authority is a
   worse failure than leaving a name in).
2. **Link** the PDFs — add citation hyperlinks (Westlaw/Lexis), a blue
   underline, and Table-of-Contents/bookmarks.

The PDF itself is never modified by pseudonymization; only the `.txt` export is
scrubbed. A `pseudonym_key.xlsx` round-trips real↔fake through the
`DeAnonymize.bas` Word macro, so every minted fake must be globally unique and
written to the key.

**Correcting the key in place / durable KEEP store.** The `Replacement` column
of `pseudonym_key.xlsx` accepts the same operator control words the LEAKS `Fix?`
column does — `no` (keep this Real Value verbatim) and a `[bracketed]` keep-spec
(keep the bracketed part, auto-fake the rest) — so a mistake baked into the key
that never surfaced as a leak can be fixed where it lives (`_pn_load_key` returns
these as `key_decisions`). KEEP protection (`Pseudonymizer._keep_spans`, spans
added to `_substitute`'s `protected` set; records `kept_hits`) comes in **two
tiers**, both matched on **word boundaries** (never a substring, so `no` on "Cal"
never touches "California"):

- **`keep_soft`** (a `no` value) — keep the exact word ONLY where it stands
  alone. It is released inside a multi-word capitalized **name run** (a possible
  party like "Cal Equipment", via `_in_name_run` / `_pn_is_name_word`), and only
  for a single-word keep (an e-mail/phrase `no` uses the full-party rule alone).
- **`keep_strict`** (a bracketed keep-spec part) — "this fragment is never a
  name": kept even next to names, so `[Plaintiff]` stays in "Plaintiff John Doe"
  and `[Attached]` stays in "Jack Gerlach Attached".

Both tiers still lose to a **full party match** — a kept word inside a
`_PN_PARTY_OVERRIDE_CATS` (person/entity/case_number) term is released so the real
party is faked ("CAL EQUIPMENT FE RANCH, LLC" faked whole, "John Doe" faked).
Bare `*-token`/short-name terms and detectors do NOT release a keep.

**The KEEP store is a SINGLE cross-folder sheet**, the `KEEP` tab of the master
workbook (`_pn_master_path`, next to the config or `PDF_LINKER_MASTER` /
`master_leaks_path`; a sibling of the `Master Leaks` tally tab — both preserved
by the multi-sheet-safe `_pn_master_load`/`_replace_sheet`/`_save` helpers). Every
run in every folder reads it (`_pn_read_master_keep`) and applies it, and records
its own local keeps back (`_pn_update_master_keep`, accumulating Times Seen /
Cases / dates) so the screening can learn from real history. This — NOT the
per-folder `LEAKS.xlsx` — is the preservation vehicle: the transient LEAKS triage
can be auto-deleted freely without ever dropping a keep. Safety: the full-party
override in `_keep_spans` means a keep (local OR global) can never leave a real
party un-faked — wherever a person/entity/case_number term matches, the keep is
released and the party is scrubbed. Persistence is macro-safe: the
`no`/bracket instruction is NEVER written into `pseudonym_key.xlsx` (a literal
"no" in a Replacement cell would poison the reversal macro); `write_key` also
drops any harvested reversal row for a kept value.

## Pseudonymization pipeline (the privacy-critical half)

- **Fake pools** (`_PN_NAME_WORDS` ~190 surnames, `_PN_ENTITY_WORDS` ~110): drawn
  without replacement per case, so they must stay ahead of a real filing's
  distinct name tokens (parties + counsel + staff + every declarant + e-mail
  display name) or the registry mints ugly numbered stand-ins ("Corwin Vance3",
  and in body text "HENDRY2 CORPORATIOLORNE10"). Keep the four pools
  (name/entity/city/street) disjoint (`TestPoolsAreDisjoint`) and every added
  surname a valid `_pn_is_name_token`.
- **OCR/typo folding** (`_PnFakeRegistry.token`): a name token near an already-
  bound token (min length `_PN_NAME_FOLD_MIN`) folds onto a *typo of that token's
  fake* (`_pn_typo_variants`), so "Palladina"/"Pallading" read as typos of the one
  "Keswick" the canonical "Palladino" got, each still keeping its own distinct
  (reversible) stand-in. The op mirrors the real's deviation so lengths track
  (insert↔duplicate, delete↔drop, sub↔visual confusable, adjacent-transpose↔swap).
  "Near" is **OSA / Damerau-Levenshtein** (`_pn_osa_distance`, so a swapped pair
  like "Adler"/"Alder" is ONE slip, not two subs) and the allowed distance
  **scales with length** (`_pn_name_fold_dist`: 1 for short names, 2 at ≥10 chars,
  3 at ≥16 — a long token plausibly carries more typos, and two genuinely
  different long surnames rarely sit that close). A multi-character length delta
  is mirrored (`reps`), so a real that gained two letters gets a fake that grew by
  two. A **welded** token (a column-splice glued two names, "ADLERMICHAEL" =
  "ADLER"+"MICHAEL") folds onto the CONCATENATION of the two parts' fakes
  ("Darrow"+"Fenmore"), guarded so an ordinary long surname is never split.
  Folding is **document-order-independent**: an edit-distance fold is symmetric,
  but a weld is strictly longer than its base, so `_pn_build_terms` runs a scratch
  pass (`_PnTokenOrderRecorder`) to enumerate the bare tokens and pre-binds them
  **shortest-first** — every base is bound before any token that contains or
  extends it. The single-edit domain OCR-fold uses the `k==1` wrapper
  `_pn_edit_distance_le1`.
- **Registry** (`_PnFakeRegistry`): injective, deterministic real→fake fakes,
  seeded on the real value (same input → same fake across runs, no two reals
  collide onto one fake). Draw every fake through it so the used-pool stays
  authoritative and the key round-trips.
- **Terms** come from the spreadsheet key (E-Court `Order*.xlsx`), `--term`, and
  a folder **pre-scan** that harvests names/localities/identifiers. Built in
  `_pn_build_terms` / `_pn_append_name_terms` → person vs entity paths.
- **Invariants that keep biting if broken** — a fake must never equal its real
  value (`_pn_guard_distinct_fake`, the `M & M` self-map loop); a state name is
  never faked inside a company name; a state-of-incorporation descriptor ("a
  Delaware corporation") stays verbatim; legal boilerplate is never a "name";
  court-form boilerplate (`_PN_NEVER_FAKE`: a Judicial Council form number
  "CIV-100", the "CASE NUMBER" field label, the "Default Only" checkbox) is
  never registered as a term and never flagged — matched on an alphanumeric,
  case-folded reduction so spacing/dash variants all catch. Extend the set as
  more form boilerplate appears.
- **Detectors** (`_PN_DETECTORS`: ssn/email/phone/address/url) run as regex over
  the text in `apply()`; `_detector_cands`/`_term_cands` produce candidates,
  highest-priority longest-non-overlapping wins.
- **Two-tier leak detection**: `surviving_reals` (a tracked real still present)
  and the high-recall REVIEW scans (`review_scan`, `unknown_name_scan`,
  `reid_scan`) surface anything name-shaped for human triage in `LEAKS.xlsx`.
  These scans must never re-flag the run's OWN fakes: `_pn_word_is_own_fake`
  recognises a bare fake ("Keswick") AND a welded one where a splice glued the
  fake to a neighbour ("CORPORATIOLORNE10" carries "lorne10", "POSTBOX4.ORGPANY"
  carries "postbox4"), and a phrase is suppressed once the fake tokens are
  removed and no real name still stands — so a fake dragged by a non-name
  prefix ("ASIC Pruett Keswick", "Nolan Relations") is not reported as
  unscrubbed. A genuinely-new real name beside a fake is still surfaced. The
  distinctness gate is the `_PN_COMMON_WORDS` gazetteer (~500 words: high-
  frequency English plus motion-practice vocabulary), so a title-case argument
  heading ("Defendant Cannot Establish...", "For Age Discrimination",
  "Voluntarily Resigned") reads as boilerplate, not a party — but it must never
  swallow a word that is also a real surname in the case (green/smart/raven/
  moore all leaked here) or a fake-pool word.
  (worksheet tab `LEAKS`; the old `pdf_linker_leaks.xlsx` name is still READ so
  a folder triaged under a prior version keeps its decisions). Columns lead
  with the flagged **Value** then its **Fix?** decision, with File/Type/Where/
  Notes trailing — the order driven by `_PN_LEAK_COLUMNS`. **One row per
  distinct value**: a name that leaks across many files is aggregated into a
  single row (files + locations merged) so the operator decides it once, not
  once per file. The **Fix?** column round-trips: `yes`=auto-fake, `no`=leave,
  **any other text = an explicit operator-typed replacement**, and
  **`[bracketed]` text naming part of the value = keep that part verbatim and
  auto-fake the rest** (`_pn_bracket_keep`; "Raytheon's [Human Resources]" fakes
  the name, keeps the department words). Government hosts (`*.gov`/`*.mil`) are public
  infrastructure — never faked or flagged. When in doubt a **bare number under
  6 digits** is not a re-identification key (`reid_scan` filters it; bar
  numbers, a definite State Bar lookup, are exempt). A **bare 1-3 digit account
  number** is not even tracked (`_pn_identifier_values` drops it): "Response
  No. 101" / "Material Fact No. 110" collide with page/exhibit/section numbers,
  so registering them faked the number where it could and leaked it (in
  citation-protected spans) where it couldn't — pure review noise; a 4+ digit
  or alphanumeric stamp ("DEAL# 23071") stays distinctive and is still scrubbed.
- **Column-spliced captions**: a two-column caption interleaves in extraction,
  welding party names to neighbours. Extraction is column-aware up front: a
  page-level column band needs multi-row support (`_COLUMN_BAND_MIN_ROWS`,
  scaled down on sparse pages), so a caption's label-value tab gap
  ("Department:&nbsp;&nbsp;&nbsp;55") stays one segment instead of splitting into a
  phantom column that hides the value from its label-anchored detector.
  Post-hoc, `surviving_reals_reduced` / `scrub_welded`
  recover welded party names via an alphanumeric-reduced substring match —
  restricted to NAME-type records only (`_PN_WELD_CORE_CATS`), never structured
  identifiers (a domain core nests inside the party it belongs to). Such pages
  are also flagged `REVIEW ... appears column-spliced` for a human.
- **`--fix-leaks`**: a text-only fast path that applies the worksheet's Fix?
  decisions to the `.txt`/`.LEAK` exports without reopening the PDFs.

## Citation linking

`find_all_citations` (full/short-form/supra/statute/rule) over the combined
page text; `resolve_url` per provider. Links are inserted **page-scoped**: a
citation whose text occurs once is linked only on its own page (not searched
across all N — that was O(cites×pages)). `_repair_link_uris` fixes a PyMuPDF
annotation-naming splice. Declarations/complaints skip linking
(`should_skip_linking`).

## OCR (the runtime bottleneck on scanned exhibits)

- `_ocr_pdf` OCRs pages with **no** text; `_reocr_garbled_pages` rebuilds pages
  whose text extracts as gibberish (bad encoding). Both **parallelize** render+
  OCR across worker threads (Tesseract is a subprocess → releases the GIL);
  **rendering stays on the main thread** (PyMuPDF is not thread-safe); overlay
  is serial.
- Per-page **timeout + grind**: a stalled page is re-rendered at lower
  resolution and retried, never skipped, never hangs (the earlier 0%-CPU hang).
- Env vars: `PDF_LINKER_OCR_WORKERS` (default cores-1, cap 10),
  `PDF_LINKER_OCR_TIMEOUT` (default 600s).

## Performance notes

- Term/record regex patterns are **compiled once** per run via a
  `Pseudonymizer._compiled` cache — Python's own re cache caps at 512, so a
  large case recompiled every pattern on every page (was ~75% of the scrub pass).
- Files are processed **heaviest-first** by OCR-weighted cost; the one-click
  re-run launcher is written **up front** so an interrupted run still leaves one.

## Conventions

- **No real judge name in the repo** — court-personnel scrubbing is name-agnostic
  (discovered from the document); the fictional "Dana Whitaker" is used in tests/
  comments.
- Runtime artifacts (`pdf_linker_eta_rate.txt`, logs, leaks/key xlsx, ETA/DONE
  markers, launchers) are gitignored — never commit them (a stray one broke a
  user's `git pull`).
- Run tests: `cd PDF-Linker && python3 -m pytest tests/ -q`. `fitz` (PyMuPDF),
  `openpyxl` needed; OCR tests stub `pytesseract`/`PIL`.
