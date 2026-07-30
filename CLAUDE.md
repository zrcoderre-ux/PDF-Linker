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

**Adding a document to a folder already sent out (the incremental re-run).** The
scrubbed exports go to an LLM for a draft, the draft says a filing is missing,
the operator drops that PDF in and re-runs. The documents already sent MUST come
back byte-identical or every earlier draft is invalidated — so a re-run beside
`pseudonym_key.xlsx` reuses it (`_pn_load_key`) and never re-derives a bound
value. Fakes are deterministic anyway (`_pn_rng` seeds SHA-256 on the real value
+ pool tag — no clock, no entropy), and `_pn_build_terms`' shortest-first
pre-bind makes them order-independent; the key's job is to pin what the pool
draw would otherwise shift when the input set changes. `_pn_load_key` seeds the
registry's used-pool and its per-slot memos — name/entity tokens, domains, AND
(because they are re-derived through their own slots) `caseno` and the
number-stripped `street` identity — so a value written a second way in the new
document folds onto the fake already in the key.
**The key pins every AUTHORITATIVE binding, matched or not.** `write_key` used
to write only rows that matched, so a party the template names but this batch
never mentioned had no row — and the fake was already minted (every term gets
one at build time), so the binding was thrown away for nothing. Now a row is
written when it matched, when it came from a reused key, OR when its source is
authoritative (`_PN_KEY_UNMATCHED_SOURCES` = the E-Court template and `--term`),
carrying Status `no match` so the sheet still says which values never reached an
export. The old rule's reasoning — `ReAnonymize` must never rewrite a Real Value
that was never a party — still governs everything INFERRED: a declarant read off
a signature block, a prefix, a court-staff name, and any SYNTHETIC spelling this
tool invents to widen matching (a `_pn_name_variants` near-miss, a wrap-split
hyphen spelling — flagged `_PnTerm.derived`) earns a row by MATCHING and never
merely by existing. `Pseudonymizer.__init__` must propagate `loaded`/`derived`
into the record dict — it silently dropped `loaded`, so the "preserve a reused
key's rows" branch never fired and a `--fix-leaks` rewrite could shrink the key.
**Exactly ONE row may REVERSE each fake.** The registry is injective, so two rows
sharing a Replacement are never two parties — only two spellings of one, since a
synthetic spelling is registered against the canonical value's fake. Right
forward, unusable backward: `DeAnonymize.bas` cannot tell a synthetic spelling
from the real one, so it treats a fake claimed by two Real Values as ambiguous
and retires the mapping — fail-safe, but the pseudonym is then left standing in
the tentative, which made every hyphenated party and every OCR-matched name
un-restorable. `write_key` marks the non-canonical rows (`Status` =
`_PN_KEY_ALT_STATUS`, "alt spelling") instead of dropping them, and gives the
owner the GROUP's status so it never reads `no match` for a fake the export is
full of. Marked, not dropped, because the rows are still needed forward:
`_pn_load_key` pins them, so a re-run with only the key — no template to rebuild
the variants from — reproduces the delivered exports byte-identically instead of
scrubbing the wrap-split form half by half ("Sedgwick- Linford"). `_pn_load_key`
must also carry the marker back onto the term (`_PnTerm.derived`), or the re-run
re-picks the owner by hit count, which the wrap-split spelling wins — it is the
form the text actually carries — and ownership flips on the first re-run. A group
that is ALL synthetic promotes one row, or the fake reverses to nothing.

`_pn_supplement_key_terms` is the fallback for what the key still cannot carry:
a key written by an older version, or a template AMENDED between runs (a Doe
defendant named). It re-reads `Order*.xlsx` (`_pn_find_party_template`, folder
then Downloads) and adds only what the key lacks, drawing through the same
memo-seeded registry so it can only ADD a fake, never move one. It runs BEFORE
`_pn_retire_kept_key_terms` so an operator `no` still wins — a kept value must
not come back to life just because it is also a template row.

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

A keep normally loses to a **full party match** — a kept word inside a
`_PN_PARTY_OVERRIDE_CATS` (person/entity/case_number) term is released so the real
party is faked ("CAL EQUIPMENT FE RANCH, LLC" faked whole, "John Doe" faked).
The ONE exception is `keep_strict_local`, a bracket typed in THIS folder: see the
keep-spec rule below — the bracket already says how to split the name and its
remainder is a term, so honouring it still scrubs the party. Bare
`*-token`/short-name terms and detectors do NOT release a keep.

**The KEEP store is a SINGLE cross-folder sheet**, the `KEEP` tab of the master
workbook (`_pn_master_path`, next to the config or `PDF_LINKER_MASTER` /
`master_leaks_path`; a sibling of the `Master Leaks` tally tab — both preserved
by the multi-sheet-safe `_pn_master_load`/`_replace_sheet`/`_save` helpers). Every
run in every folder reads it (`_pn_read_master_keep`) and applies it, and records
its own local keeps back (`_pn_update_master_keep`, accumulating Times Seen /
Cases / dates) so the screening can learn from real history. This — NOT the
per-folder `LEAKS.xlsx` — is the preservation vehicle: the transient LEAKS triage
can be auto-deleted freely without ever dropping a keep.
**A keep-spec means what it says IN ITS OWN FOLDER, and only its keep
elsewhere.** `Alder Law, P.C. -> [Law]` yields `<fake> Law, P.C.` in the case
that made it: `keep_strict_local` beats even the full-party override, which is
safe because the bracket's REMAINDER is registered as its own term, so the party
is scrubbed either way. Elsewhere only the bracket applies — the lesson "this
fragment is never a name" generalises, the remainder ("Alder" is that matter's
law firm) does not, and an inherited keep-spec builds no fragment terms, so it
must keep losing to the party match or the whole name would ride through.
Ownership is the `Origin` column of the master KEEP sheet (`_pn_decision_is_ours`),
NOT `Cases`: the local `LEAKS.xlsx` is consumed once resolved, so a decision made
here survives only on the master sheet, and `Cases` accumulates every folder the
keep has since protected text in. Only the folder that first recorded a value
authors it. Inheriting the faking half is cross-case inference — the
failure the closed-entity rule exists to prevent — and it put another case's law
firm in every folder's log and, once unmatched authoritative bindings were
pinned, every folder's KEY (`Alder Law, P.C. -> [Law]` wrote a `no match`
"Alder" row into cases that never mentioned it). A firm that genuinely recurs is
caught by that case's own party list or pre-scan. `_pn_keep_values` reads the
decisions directly, so withholding the fragments cannot weaken the keep. Safety:
the full-party
override in `_keep_spans` means a keep (local OR global) can never leave a real
party un-faked — wherever a person/entity/case_number term matches, the keep is
released and the party is scrubbed. Persistence is macro-safe: the
`no`/bracket instruction is NEVER written into `pseudonym_key.xlsx` (a literal
"no" in a Replacement cell would poison the reversal macro); `write_key` also
drops any harvested reversal row for a kept value.

**A keep RETIRES the key row it corrects** (`_pn_retire_kept_key_terms`), so the
re-run leaves a CLEAN key — real values against the fakes actually applied, no
control words and no row for a value that is no longer faked that way. Needed
because a loaded key row is itself a full party match, so the safety override
above turns against the operator's own edit: `no` on a keyed value faked it
anyway *and* dropped its row (an unreversible fake in the exports), and a
`[bracketed]` keep-spec faked the whole flagged phrase while the dirty row
survived. Retired, `John Doe's Opposition -> ['s Opposition]` becomes
`John Doe -> Yorke Deverell` — the fragment INHERITS the retired fake when the
two align word for word (memo pre-seed), so exports already in circulation keep
reading the same. A `no` also retires the bare `*-token` rows derived from its
words, unless another party still carries the word ("Doe" stays bound for "Jane
Doe"), or the value would be reassembled token by token. Retirement is for LOCAL
edits only — this folder's key or LEAKS. A keep merely INHERITED from the master
sheet must never retire this case's binding (the safety rule above still fakes
the party), so its row stays reversible.

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
- **Hyphenated compound surnames** are two name components, so the fake is
  compound too: "Ardeshirpour-Zartoshti" → "Sedgwick-Linford", each half
  **exactly the fake that half gets standing alone**. One pool word for the whole
  made the compound and its shorthand ("Dr. Ardeshirpour" → "Dr. Sedgwick") read
  as two unrelated people. It also makes reversal ORDER-ROBUST — the compound
  fake is literally its parts' fakes joined, so the macro's token-by-token pass
  rebuilds it whichever row it applies first. Composition happens in
  `_PnFakeRegistry.token` (after the typo fold, so a genuine OCR slip still folds;
  a compound needs one part ≥ `_PN_NAME_FOLD_MIN`, so "Al-Amin" takes a single
  word). Costs two pool words per compound — pool headroom matters that much
  more. `_pn_append_person_terms` also registers the wrap-split spelling
  ("Ardeshirpour- Zartoshti", same fake) and each half as its own token, so the
  shorthand a brief actually uses is never left standing beside a faked given
  name as a half-scrubbed pair.
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
- **A `display-name` record is a record, not a term.** `_display_name_cands`
  recognises the NAME in a "Name <addr@domain>" pair and mints it into
  `self.records` — enough for `surviving_reals` to report it and `write_key` to
  write a reversal row — but `_term_cands` iterates `self.terms`, so the name
  was faked at the pair site and NOWHERE else. A firm's paralegal, named once
  beside her address and then printed on every page of the letterhead, survived
  on all of them, and the key PROMISED the reversal, so `DeAnonymize` would map
  the fake back onto pages still carrying the real name.
  `_display_name_repeat_cands` closes it: every known display-name is matched
  standing alone, word-bounded and case-insensitively (`_substitute` case-matches
  the fake, so an ALL-CAPS letterhead is covered). It runs AFTER
  `_display_name_cands` in both `apply` and `apply_lines`, so a name first met in
  a text has its other occurrences covered on that same pass.
- **Two-tier leak detection**: `surviving_reals` (a tracked real still present)
  and the high-recall REVIEW scans (`review_scan`, `unknown_name_scan`,
  `reid_scan`) surface anything name-shaped for human triage in `LEAKS.xlsx`.
  **A KEPT value is not a leak** — it is present because the operator said so,
  so `surviving_reals` skips it (the REVIEW scans always did). Reporting it put
  a row in `LEAKS.xlsx` that no answer could clear: `no` is what produced it,
  and the durable decision lives on the master KEEP sheet, so consuming the
  local worksheet never retired it either. Scoped to the categories a keep
  survives in — a keep is RELEASED inside a full party match, so a
  `_PN_PARTY_OVERRIDE_CATS` real still standing was faked nowhere and IS a leak.
  These scans must never re-flag the run's OWN fakes: `_pn_word_is_own_fake`
  recognises a bare fake ("Keswick") AND a welded one where a splice glued the
  fake to a neighbour ("CORPORATIOLORNE10" carries "lorne10", "POSTBOX4.ORGPANY"
  carries "postbox4"), and a phrase is suppressed once the fake tokens are
  removed and no real name still stands — so a fake dragged by a non-name
  prefix ("ASIC Pruett Keswick", "Nolan Relations") is not reported as
  unscrubbed. A genuinely-new real name beside a fake is still surfaced —
  correctly, but the phrase is then HALF-SCRUBBED, and taking it at face value
  when the operator marks it yes fed our own fake back in as a REAL value. Only
  the surname was bound ("Penuela" -> "Sable"), the export reads "Melissa
  Sable", and keying that phrase faked it a second time ("Melissa Sable" ->
  "Ramsey Ellery") — so the macro walked a two-generation chain that never
  reached "Penuela", and every re-run grew another generation.
  `_pn_strip_prior_fakes` / `_pn_drop_prior_fakes_from_terms` fake only the real
  remainder ("Melissa"), leaving the established stand-in alone, so the pair
  reverses to "Melissa Penuela". It bites in **`--fix-leaks`**, where the text is
  already scrubbed and the PDFs are never reopened; a full run self-heals because
  the pre-scan re-reads the real name from the PDF. An EXPLICIT typed
  replacement is left as the operator's deliberate choice, but warns when its
  value carries one of our fakes. The
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
  the name, keeps the department words). **Website vs e-mail**: a government
  WEBSITE (`*.gov`/`*.mil`) is public infrastructure — never faked, never flagged
  — but the `@` settles it, so `clerk@courts.ca.gov` names a person and is faked
  like any other address (`_pn_url_whitelisted` gates urls only). An **e-mail is
  never a worksheet row**: it is always faked, so "should I fake this?" has one
  answer and the row is pure triage cost. `_pn_is_email_value` keeps addresses
  out of `LEAKS.xlsx` (the console log and `pdf_linker.log` still report them, so
  a detector miss is never hidden), the url/domain review class ignores a host
  preceded by `@` (OCR that spaced an address out left the host standing), and
  `scrub_emails` cures the export with the fake the record already carries so
  the miss does not survive either — scoped to `email` records, since an address
  never sits inside a published citation but a bare URL can. When in doubt a **bare number under
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
  **The only stage that PREVENTS a weld** is the normalize-before-detect rebuild
  in `_page_lined_rows`: `_detect_line_anchors(page, desplice=True)` rebuilds the
  body spans from CHARACTER geometry (`_despliced_body_spans`, via `rawdict`) and
  splits each welded span at its column jumps, so the name comes out contiguous
  and the ordinary whole-word patterns can replace it. Everything below merely
  cures a weld that already reached the scrubber. It is gated on
  `_page_weld_score`, NOT on `_page_looks_spliced` — the verdict misses
  "MICHAEL14." and cannot be widened to see it (the ~90% false-positive result
  below). A COUNT can use signals a VERDICT cannot afford, because it is only
  ever read comparatively: `_PN_WELD_DIGIT_SEAM_RE` is in the score and not in
  the verdict, and whatever it misfires on it misfires on identically in both
  scores. The rebuild is adopted only when it STRICTLY REDUCES that score, which
  is what makes a loose gate cheap in risk rather than expensive — a rebuild
  that doesn't help is discarded and the original rows stand. A clean page pays
  nothing (score 0 → no second pass); a page with weld evidence pays ~4 ms.
  Post-hoc, `surviving_reals_reduced` / `scrub_welded`
  recover welded party names via an alphanumeric-reduced substring match —
  restricted to NAME-type records only (`_PN_WELD_CORE_CATS`), never structured
  identifiers (a domain core nests inside the party it belongs to). Such pages
  are also flagged `REVIEW ... appears column-spliced` for a human.
  **The core-length gate is two-tier** (`_weld_core`, the single eligibility
  rule both passes share — they must stay mirrored, or detection out-runs
  replacement and quarantines an export nothing can clean). The default
  `_PN_WELD_CORE_MIN` is 8 because a reduced core carries no word boundary, but
  that is longer than most first and last names — "michael", "carroll",
  "amezcua", "maria", "juan" are 4-7 — so the gate skipped precisely the values
  the pass exists for, and a spliced opposition put the defendant's name in the
  export while `surviving_reals` called the file clean. A SHORT core
  (`_PN_WELD_SHORT_CORE_MIN` 4) is allowed only when coincidence is implausible
  AND the value is not a guess: a PERSON token (`_PN_WELD_SHORT_CORE_CATS` — an
  entity's words are generic, "law"/"firm" nest inside "lawsuit"/"confirm"),
  named by the operator's own party list (`_trusted_party_tokens`, which already
  drops connectors so the "De" of "Cruz De Amezcua" never qualifies), not in
  `_PN_COMMON_WORDS`, name-shaped, and **actually welded** at the match site
  (`_pn_span_is_welded`) — a clean standalone occurrence belongs to the
  boundary-anchored pass, which yields to keeps and citations this pass cannot
  see.
  **Classify the SEAM, not the page, where the page signal cannot reach.** A
  caps run welded to a paragraph NUMBER ("MICHAEL14.", "MARIA46.") is invisible
  to `_page_looks_spliced`, and the obvious repair — add `[A-Z]{3,}\d{2,}` —
  measures **~90% false positives on this repo's own corpus**, all of them
  shapes the tool handles most: a California case number ("25STCV37838"), a
  federal docket, a VIN, a Bates stamp ("RAM000013"), a reservation code.
  Tightening it (caps run ≥5, short digit run, anchored to a word start so
  backtracking cannot slide past the leading year of a case number) still fires
  on a surname-prefixed Bates stamp ("RAMIREZ000013") and on "COVID19" — and a
  false page flag is NOT free, because it switches the ≥8-char reduced pass on
  document-wide and that tier has no boundary check at all.
  `_pn_span_has_hard_seam` asks instead whether the matched span meets its
  neighbour across a **letter↔digit transition or a case flip** — evidence a
  printed boundary was lost at that exact spot. It needs no guess about the
  page because it only runs where a trusted party token already matched:
  "COVID19"/"CIV100"/"RAM000013" are untouched unless the case has a party named
  Covid, Civ or Ram, and "Juanita"/"Carrollton"/"Marianne" have no transition so
  they keep their letters. So `scrub_welded` / `surviving_reals_reduced` take a
  `spliced` flag: `True` (the default, and what a flagged page or a `.LEAK`
  quarantine passes) is the full pass; `False` is the narrow hard-seam pass that
  now runs on EVERY page. The two must stay mirrored tier for tier, or detection
  out-runs replacement. Cost on an ordinary page is ~0.5 ms — the candidate
  scan early-outs before citation detection when no core is present.
  Residual, and accepted: a Bates stamp built on a party's own surname
  ("AMEZCUA001234") is faked, which is what the tool already does to a
  production number.
- **`--fix-leaks`**: a text-only fast path that applies the worksheet's Fix?
  decisions to the `.txt`/`.LEAK` exports without reopening the PDFs.
  **Nothing to APPLY is not nothing to DO**, so the pass never returns before it
  runs: a worksheet whose rows are all `no` says the flagged values are fine to
  leave, and a `no` never gates delivery (the same filter the main gate applies
  to `pz.suppressed`), so the exports are still re-checked, every quarantine
  that no longer carries a *gating* leak is released, the worksheet and launcher
  go once nothing is held, and the ETA marker becomes a **DONE** stamp. Bailing
  out early left the folder quarantined forever for a leak the operator had
  already dismissed — while a full re-run of that same folder delivered it — and
  left an `ETA … (applying leak fixes)` marker on a folder nothing was working
  on. With no fix terms the pass is strictly LESS invasive than an ordinary one
  (the same key-loaded terms, minus the flagged values) and a file is rewritten
  only when its content changes. The ONE thing that still blocks the release is
  a decision the operator MEANT to apply that had to be dropped — a typed
  replacement identical to the value (`rejected`): nothing fixed it, so its file
  stays held (`held`, unioned into `offenders`) and the worksheet stays, per file
  rather than per batch so a typo in one cell never rides out on another row's
  coat-tails. A crash after the ETA is projected clears the marker without
  stamping DONE (the pass did not finish).
- **A re-run drops the quarantine it supersedes**
  (`_pn_drop_superseded_quarantine`, called from both export write sites). The
  gate renames `Brief.txt` to `Brief.txt.LEAK` and leaves it for triage; when a
  later run re-scrubs the same document and the export comes out clean, the
  worksheet and launcher were already cleaned up but that file was not — so a
  re-run that "resolved the leaks" still said there was triage pending, and kept
  the one copy in the folder carrying the real names verbatim. Every name the
  export may have been quarantined under is checked (the scrubbed one, the
  source stem, the pre-subfolder case-root location) and only the tool's own
  `.txt.LEAK` extension is ever unlinked. Safe because the gate re-creates the
  quarantine at the end of the run if THIS run's export leaks too.

## Judicial Council forms (the checkbox-heavy half of a filing)

A filled Judicial Council form — CIV-100 and the rest of a **default-judgment
packet**, the **discretionary complaint forms** PLD-C-001 / PLD-PI-001 and their
per-cause-of-action attachments — arrives one of two ways, and BOTH are handled:
as an **AcroForm** whose answers are widget annotations (below), or **filled with
ink** and flattened or scanned, where the answers are marks on the page (the
subsection after it). Either way the checkbox IS the pleading, so a rendering
that drops its state drops the document.

Taking the AcroForm case first: the answers live in WIDGET
annotations, not in the page content stream. Plain extraction therefore prints
the blank form's boilerplate first and then every answer in one unanchored heap
at the end, so no value sits beside the label it answers. A **checkbox fares
worse than that**: a CHECKED box paints the ZapfDingbats check glyph, which
extracts as a bare **`3`**, and an UNCHECKED box paints **nothing at all**. So
the export carried a scatter of `3`s naming no item, and nothing whatsoever
separated "clerk's judgment requested" from "not requested" — on these forms the
checkbox IS the pleading, so that is the whole content of the document.

`_form_page_text` rebuilds such a page from geometry: static template spans
(minus anything a widget painted — the widget object is authoritative for its
own box, so the check glyph and the label-less value copy are dropped by a
centre-in-widget-rect test) plus one synthesized cell per widget, sorted into
rows and laid out at each cell's own column (`_FORM_CHAR_W`). A checkbox becomes
`[X]`/`[ ]` immediately left of the caption it governs; a field value lands
beside its own label; a multi-line value walks down its own field box so its
lines stay separate rows; an empty field prints nothing. A one-line banner names
the form and tallies the boxes, so "did the checkboxes come through?" is
answerable at the top of the page.

- **Rows group by vertical OVERLAP, not centre distance** (`_FORM_ROW_PAD`): a
  checkbox rect is taller than its caption and a field box taller than its
  label, so a fixed centre tolerance either splits a printed row or welds two.
  Each cell's extent is capped to a nominal text line (`_FORM_CELL_HALF`) so one
  tall field box (a three-line attorney block) cannot annex the rows below it.
- **A radio has to match its OWN on-state** (`_widget_is_on`): every widget in a
  radio group carries the group's value, so comparing to `Off` alone reports all
  of them checked the moment one is. `Off` is the name the PDF spec reserves for
  the off state, which is what makes "anything else is on" safe across the export
  values real forms use ("Yes", "On", "1").
- **The form path wins over the pleading-rows path only when the page carries a
  checkbox state** (`_form_has_state_boxes`, asked of the rendered text so it
  holds for a widget form and an ink one alike). That state is invisible to every other rendering, which is
  worth giving up gutter line numbers (and "p.3:7" pinpoint cites) for; a
  text-only form on pleading paper (an MC-025 attachment) keeps its numbers, and
  a text-only form off pleading paper still takes the form path because its
  values would otherwise stay unanchored.
- **Detection reads what the export writes.** `_page_detect_text` takes the
  DECIDED form text via the `_FORM_UNDECIDED` sentinel — distinct from `None`,
  which means "decided against it" — because a page whose form rendering was
  suppressed must not be leak-scanned against a rendering it never got. Form
  values reach the scrubber and the leak scan precisely because they are in this
  text; a party named only inside a widget would otherwise be certified clean.
- **A form id is never faked, BY SHAPE** (`_PN_FORM_ID_RE`, checked from
  `_pn_is_never_fake`). Naming them one at a time does not scale — a
  default-judgment packet carries several and the complaint forms carry a
  numbered attachment per cause of action — and a form number faked as a case
  number is a nonsense stamp that destroys the form's identity.
### The same form, filled with INK (`_ink_form_cells`)

A form that was printed, marked by hand and scanned — or filled on screen and
FLATTENED — has no widgets left: the checkbox is a printed square and the answer
is ink inside it. There is nothing authoritative to read, so the state is
MEASURED, from three sources that differ in how far they can be trusted:

1. **a state GLYPH inside the box** — the ZapfDingbats check a flattened form
   keeps, an empty-box character (`□`, which positively means UNCHECKED — reading
   it as a mark would report relief nobody requested), or the stray character OCR
   makes of a pen stroke. Exact.
2. **a VECTOR path strictly inside the box** — a flattened pen stroke or drawn X,
   distinguished from the box's own border by being narrower than it. Exact.
3. **RASTER INK** — the scanned case. Inferred, and said to be.

**For (3) the box position cannot come from the caption's geometry.** A probe
window centred by estimate lands a point or two off, the border bleeds into the
measured interior, and empty boxes then measure as heavily inked as marked ones
(0.14 vs 0.15 — indistinguishable, and it flips with a 1 pt shift). So the box is
found IN THE RASTER first: the bounding box of the dark pixels in the window IS
the printed square, and only its interior, inset clear of the border
(`_INK_INSET`), is measured. That **self-registers** — the same box measures the
same fill however far off the estimate was, and empty vs marked separates ~0.00
vs ~0.33, verified unchanged as the box-to-caption distance moves. A box touching
the window edge may be clipped, so it yields NO verdict rather than a guess.

- **The middle band is `[?]`, never rounded** (`_ink_state_from_fill`). A pencil
  tick too faint to separate from scanner speckle is exactly where guessing is
  worst, and the banner counts the unreadable ones.
- **A window holding real text is not a checkbox slot** at all
  (`_ink_span_blocks_window`: two or more alphanumerics), which is what keeps a
  neighbouring column, a gutter number or a wrapped caption from being probed.
  Conversely everything INSIDE a confirmed box is the mark and is dropped from
  the static text, so the export never reads `[X] 3 a. Enter default...`.
- **`_INK_MARK_CHARS` admits no digits.** The ZapfDingbats check does extract as
  `3`, but the dingbat FONT already settles that; admitting bare digits would
  read a stray form number as a check for nothing, and on a scan an OCR'd digit
  falls through to the raster pass, which measures the actual ink anyway.
- **The gate is cheapest-first and must stay that way**: enough checkbox-sized
  squares in the page's own line art, else a Judicial Council form id in the
  footer. An ordinary filing fails both in ~1.6 ms/page and never reaches the
  `get_text("dict")` or the render. An ink form page costs ~150 ms — negligible
  beside the seconds of OCR a scanned page already pays.
- **Widgets always win.** The ink pass runs only where they are absent, so an
  intact form is never read by inference.
- **The banner and the log both say when a state was inferred**, and ask for a
  check. An inferred checkbox on a default-judgment packet is precisely the fact
  nobody should take on trust, so it is never presented as equal to a widget's.
- Cost of the widget path: one `doc.is_form_pdf` check per document, and a
  ~0.02 ms per-page widget probe.

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
  is serial. Note what this means for a WELD: a filed pleading is born-digital,
  so neither path touches it — a welded caption there is an EXTRACTION failure,
  not a recognition one, and no OCR setting can affect it.
- `_OCR_CONFIG` (`-c preserve_interword_spaces=1`) is passed on **every** call
  site, the grind rungs included. Tesseract otherwise collapses the run of
  spaces a two-column caption depends on — a weld manufactured at recognition
  time, upstream of every cure the pseudonymizer has.
- The grind never skips a page, but a page re-rendered below `_OCR_LOW_DPI`
  (150) has traded away real recognition quality, so it is named in the log as
  low-confidence. Silence there read as "recognised fine".
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

## Folder artifacts (what a finished folder should contain)

`Re-run PDF-Linker.bat` (`_write_rerun_launcher`), `Apply Leak Fixes.bat`
(`_write_fix_launcher` — it needs `pseudonym_key.xlsx`, which is what
`--fix-leaks` reads, AND a `LEAKS.xlsx` to apply: it is that worksheet's
companion, so it is written beside one and REMOVED when there is none. The
end-of-run block settles it, after `_pn_write_leak_report` has decided the
worksheet's fate — the up-front copy can only see the previous run's state) and the `ETA …`/`DONE …` markers (`_write_eta_marker` /
`_write_done_marker`). Gate them on **`pdfs or word_texts`**, never `pdfs`
alone: an **all-Word folder is a real batch** — same scrubbed exports, same
key, same LEAKS worksheet — and gating on the PDF list left it with leaks to
triage and nothing to double-click. The live ETA stays PDF-only (it projects
from per-page OCR weights and Word has no OCR to project from), but a Word run
still stamps `DONE` so a finished folder is distinguishable from an untouched
one. `_pdfs_in_folder` is **non-recursive** — case subfolders are not walked, so
pointing the launcher at a parent folder does nothing at all.

**An all-Word folder never borrows another case's party list.** Key resolution
normally falls back to the newest `Order*.xlsx` in Downloads (where the E-Court
export lands) — right for a PDF batch, wrong for a Word one: a Word folder is
usually a one-off with no template of its own, so "newest in Downloads" hands
it whatever case was downloaded LAST. The run then hunted a stranger's parties,
left this case's in the clear, and (since the key now pins authoritative rows)
wrote their names into this case's key. `_is_word_only_folder` withholds that
guess at all three fallback sites — the two in key resolution and the one in
`_pn_find_party_template`. Folder-local inputs are unambiguous and still win: an
explicit `--key`, this folder's `pseudonym_key.xlsx`, or an `Order*.xlsx` the
operator put IN the folder. With no list at all the run still scrubs via
detectors + pre-scan harvest and says so loudly — never silently, since silence
reads as "fully scrubbed".

## Conventions

- **No real judge name in the repo** — court-personnel scrubbing is name-agnostic
  (discovered from the document); the fictional "Dana Whitaker" is used in tests/
  comments.
- Runtime artifacts (`pdf_linker_eta_rate.txt`, logs, leaks/key xlsx, ETA/DONE
  markers, launchers) are gitignored — never commit them (a stray one broke a
  user's `git pull`).
- Run tests: `cd PDF-Linker && python3 -m pytest tests/ -q`. `fitz` (PyMuPDF),
  `openpyxl` needed; OCR tests stub `pytesseract`/`PIL`.
