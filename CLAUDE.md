# Project workflow

## Branch & merge policy

- **Work on a fresh branch per task**, named for the change. The old standing
  instruction pinned every task to one reused branch; it was removed at the
  owner's direction. Delete the branch after the merge so the list stays short.
- **Finish the loop without waiting to be asked:** commit, push, open a pull
  request into `main`, and **squash merge** it (keeps `main` linear, one commit
  per task).

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
**EVERY fake in an export must be reversible, and the run says so out loud.**
`draft` shipped as "Ainsworth" 72 times and `review` as "Sterling" 84, across
four documents, with neither mapping anywhere in the key. That is worse than the
leak that produced it: a leak is visible, an unreversible substitution is silent
and permanent. The path was `write_key` dropping the row for a value the
operator marked KEEP — true only while the keep HELD, and a soft `no` is
deliberately RELEASED inside a multi-word capitalized name run and inside a full
party match, after which the value is faked by the very row being dropped. The
occurrence COUNT settles it, because a local keep retires its binding
(`_pn_retire_kept_key_terms`), so a value really left verbatim still arrives
with count 0. `unreversible_fakes` is the standing assertion: every fake a
record applied, and every stand-in the registry minted that is found standing
in an export (`registry.minted_fakes`, read back off disk), must be reachable
from a written row — outright or word by word, which is what the macro can do.
The end-of-run gate reports and exits non-zero; the exports are NOT quarantined,
because they are not dangerous, they are unrestorable, and what the operator
needs is to know.
**A binding NO export has ever carried lives on its own sheet**
(`_PN_KEY_PINNED_SHEET`). Keeping a row the template named but this batch never
mentioned is right forward and a hazard in reverse — `ReAnonymizeTentative` runs
the map backwards and would replace a Real Value that was never in the document
(133 of the delivered key's 335 rows were of that kind). `DeAnonymize` reads the
ACTIVE sheet and cannot reach the second one; `_pn_load_key` reads BOTH, so the
pin still does its job. "Carried" is REACHABILITY, not the row's own count: the
macro reverses a composed fake word by word, so the token rows of a party whose
full name is the only form the export used are load-bearing even though they
matched nothing themselves.

`_pn_supplement_key_terms` is the fallback for what the key still cannot carry:
a key written by an older version, or a template AMENDED between runs (a Doe
defendant named). It re-reads `Order*.xlsx` (`_pn_find_party_template`, folder
then Downloads) and adds only what the key lacks, drawing through the same
memo-seeded registry so it can only ADD a fake, never move one. It runs BEFORE
`_pn_retire_kept_key_terms` so an operator `no` still wins — a kept value must
not come back to life just because it is also a template row.

**Correcting the key in place / durable KEEP store.** The `Replacement` column
of `pseudonym_key.xlsx` accepts the same operator control words the LEAKS `Fix?`
column does — `no` (keep this Real Value verbatim), a `[bracketed]` keep-spec
(keep the bracketed part, auto-fake the rest) and a `{braced}` one (same cut,
stronger promise) — so a mistake baked into the key
that never surfaced as a leak can be fixed where it lives (`_pn_load_key` returns
these as `key_decisions`). KEEP protection (`Pseudonymizer._keep_spans`, spans
added to `_substitute`'s `protected` set; records `kept_hits`) comes in **three
tiers**, all matched on **word boundaries** (never a substring, so `no` on "Cal"
never touches "California"):

- **`keep_soft`** (a `no` value) — keep the exact word ONLY where it stands
  alone. It is released inside a multi-word capitalized **name run** (a possible
  party like "Cal Equipment", via `_in_name_run` / `_pn_is_name_word`), and only
  for a single-word keep (an e-mail/phrase `no` uses the full-party rule alone).
- **`keep_strict`** (a bracketed keep-spec part) — "this fragment is never a
  name": kept even next to names, so `[Plaintiff]` stays in "Plaintiff John Doe"
  and `[Attached]` stays in "Jack Gerlach Attached".
- **`keep_nuclear`** (a `{braced}` part) — "this can never reveal anything":
  never faked in ANY folder, not even inside a party name. See below.

A keep normally loses to a **full party match** — a kept word inside a
`_PN_PARTY_OVERRIDE_CATS` (person/entity/case_number) term is released so the real
party is faked ("CAL EQUIPMENT FE RANCH, LLC" faked whole, "John Doe" faked).
The ONE exception is `keep_strict_local`, a bracket typed in THIS folder: see the
keep-spec rule below — the bracket already says how to split the name and its
remainder is a term, so honouring it still scrubs the party. Bare
`*-token`/short-name terms and detectors do NOT release a keep.

**The NUCLEAR keep is enforced where it cannot cost anything: at COMPOSITION
time.** `{Law}` must survive inside "Alder Law, P.C." — but protecting the span
outright would drop the party candidate that overlaps it and leave the firm
standing in full, the exact failure the party override exists to prevent. So a
brace does not fight the override; it removes the need for one.
`_pn_nuclear_words` puts each braced WORD on `registry.keep_words`, and
`registry.keeps_word` is what `_pn_fake_person` / `_pn_fake_entity_parts` /
`_pn_person_token_map` consult — the same hook `_PN_FIRM_WORDS` uses, which a
brace only ever ADDS to. The party's fake is therefore composed with the word
left verbatim ("Kaldor Law, P.C."), the word is never a bare token, never
harvested into a key row (`write_key`), never re-instated as one
(`_pn_load_key`), and `_pn_restore_furniture` repairs the binding an older key
baked in. `keep_nuclear` is still collected in `_keep_spans` (yielding to the
party match, which now costs nothing) so the word also survives every detector,
near-miss variant and bare token, and `surviving_reals` never flags it — with no
party-category exception, unlike the other two tiers. Because a keep the
composing faker honours can never leave a party in the clear, it needs no
fragment terms and so no local/inherited split: unlike a `[bracket]`'s faking
half, a brace applies in **every** folder. `_pn_set_keep_words` must run BEFORE
terms are built or a key is loaded (both run sites do; `--fix-leaks` reads the
master/folder decisions ahead of `_pn_load_key` for exactly this reason), or a
fake minted first would carry the very word that was braced. A brace typed into
the KEY is the circular case — the decision is inside the file being read — so
`_pn_load_key` PRE-SCANS its own Replacement column for keep-specs and seeds
`registry.keep_words` before processing any row. Without it a brace was a
per-ROW edit for one run: every other row kept applying its stored composed fake
for the same word, and the decision only took effect on the NEXT run, via the
master sheet. A brace whose text is not part of its row's Real Value cannot say
what to keep, so it neither seeds a word nor is silently applied — it falls
through as an explicit replacement (which would write a literal "{Law}" into the
export) and is WARNED about. The master KEEP sheet types a braced row
`KEEP-ALWAYS` (`_PN_KEEP_NUCLEAR_TYPE`).

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
  different long surnames rarely sit that close). Note what widening the
  distance DOES to an export: a variant that no longer draws a clean pool word
  now draws a deliberately misspelled one, so the count of misspelled-looking
  words in the delivered text goes UP with the fold's reach. That is the design
  working, and it is also indistinguishable from the scan getting it wrong —
  see `_report_minted_misspellings` in the OCR section, which is what tells the
  two apart. A multi-character length delta
  is mirrored (`reps`), so a real that gained two letters gets a fake that grew by
  two. A **welded** token (a column-splice glued two names, "ADLERMICHAEL" =
  "ADLER"+"MICHAEL") folds onto the CONCATENATION of the two parts' fakes
  ("Darrow"+"Fenmore"), guarded so an ordinary long surname is never split.
  A weld may carry a CONNECTOR, because a domain core is the party with its
  spaces gone: "cadillacofcalabasas" folded on the bound prefix alone left an
  11-char tail that drew ONE unrelated pool word ("eldridge"), tying the domain
  neither to the party nor to the "cadiilac" beside it. The connector is kept
  verbatim and the remainder folded, so the fake reads the same way
  ("cransfonofmarlowe" = "Cransfon of Marlowe" with the spaces gone) — but only
  when the post-connector remainder is ALREADY BOUND, or "smiththeodore" would
  lose its "the" and fold onto a mangled "odore".
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
- **A term matches WHOLE WORDS.** Built without boundaries, `person` and
  `entity` terms matched inside longer printed words and ate the text around
  them: an OCR fragment "RS, LLC" fired inside "General Motors, LLC" eleven
  times ("General Motocairnwood, LLC") and a declarant "Tue" inside "Vatue"
  ("Agreed Vabennett of Property"). The reason for the looser form does not
  survive inspection — `(?!\w)` is satisfied by an apostrophe, so a possessive
  still matches, and the pattern's whitespace runs already absorb a line wrap.
  The ONE relaxation is `_pn_build_pattern(follow=…)`, for the single place a
  weld is expected and its shape is known: extraction that lost the space in
  "Smith Decl." leaves "SmithDecl.", and the declarant-reference harvester is
  reading exactly that. The LEFT boundary always holds, which is the one that
  stops a short name firing inside a longer word. `_pn_load_key` builds loaded
  person/entity rows the same way, or a re-run would rewrite text the run that
  wrote the key never touched.
- **A DOCUMENT harvest is a GUESS, and has screens to clear** — none of which
  ever apply to the operator's own party template, because refusing a real name
  is the failure the whole method exists to prevent. A LOOSE harvest (a caption
  line, a capitalized run, an OCR fragment) needs `_PN_HARVEST_TOKEN_MIN` = 3
  distinctive characters: every 2-letter candidate in the fee-motion corpus was
  junk ("AL" off "JUAN LOPEZ, ET AL. V. GENERAL MOTORS", so every "et al."
  became "et aldrin."; "RS" off "MOTORS"; "NA", turning "CASE NA.ME" into "CASE
  GG.ME"), and `_PN_SHORT_TOKEN_STOP` is a 24-word list with none of them on it.
  A STRUCTURED harvest carries its own corroboration — "Yu Dec." is a
  declaration short cite and nothing else has that shape — so those sites screen
  on `_PN_CALENDAR_WORDS` alone (no filing names a party "Tue"), or a real
  two-letter declarant would be left standing. `_pn_strip_et_al` runs first,
  because `_PN_SKIP_PARTY_RE` only matches a cell that is ENTIRELY "et al.",
  which is what a spreadsheet column holds and not what a caption line carries.
  Two corpus-wide prunes run beside `prune_citation_only_terms`, with the full
  folder text: `prune_prose_word_terms` (a surname is capitalized wherever it
  stands and a verb is not, so a harvested word written in lower-case at least
  as often as capitalized is prose — no hand-kept gazetteer is ever complete)
  and `prune_fragment_terms` (a candidate the corpus only ever writes INSIDE a
  longer word is an OCR fragment).
- **A motion's own SUBJECT MATTER is not a party, and no word list will ever
  say so** (`prune_heading_only_terms`). Four hand-kept lists now exist to stop
  ordinary legal vocabulary being replaced by a surname — `_PN_COMMON_WORDS`
  (583 entries), `_PN_SERVICE_GENERIC_WORDS`, `_PN_FORM_LABEL_WORDS`,
  `_PN_SHORT_TOKEN_STOP` — and every one was written AFTER a motion type
  shipped with its vocabulary renamed ("MOTION TO MABRY SERVICE OF SUMMONS",
  "ELDRIDGE OF SERVICE", "process radley"). A list of words that are not names
  is a list of every noun in every motion type the tool has not met yet, which
  is why the standing note here was "expect the next motion type to reveal the
  next missing block" — a promise of recurrence, not a fix.
  `prune_prose_word_terms` is the general form of the same question and cannot
  reach these: a motion's subject matter lives in its CAPTION and HEADINGS,
  where every word is capitalised, so "Quash" is never once written lower-case
  in a motion to quash. The evidence that separates them is POSITION. A party
  is written into PROSE ("served on Mabry at his residence"); the subject
  matter appears only where everything around it is a title. So a candidate
  needs one CAPITALISED occurrence on a prose line (`_pn_line_is_prose`), and a
  lower-case occurrence is never evidence — a motion writes "moves to quash
  service" in its argument and "MOTION TO QUASH" in its caption, and counting
  the argument's occurrence rescued the very word this exists to drop. The line
  test ignores `_PN_TITLE_LOWER_WORDS`, since house style leaves "to"/"of"
  lower inside a title. **ONE prose word is enough, deliberately**: a CAPTION
  CELL is where a filing states its parties and carries exactly one
  ("HELEN RASHO, an individual,"), so a two-word floor would read every caption
  as a heading and drop the party the caption exists to name. Scoped like
  `prune_prose_word_terms` — document-harvested guesses and this tool's own
  DERIVED spellings only, never the operator's template, a `--term`, or a value
  a reused key pinned.
- **The people a SERVICE document names carry no party role, and a DOCKET names
  its parties role-LAST.** Every harvest anchor was a role PREFIX ("Defendant
  Travelers", "Attorneys for X"), so two whole populations reached no pass at
  all. A motion-to-quash batch shipped the process server's name 51 times and
  the mailbox-store manager's 10 — neither is a party, and nothing else in the
  document says who they are except their JOB. `_PN_LABEL_RES` now carries both
  orders of the service roles (name-first, "Michael Rodgers, a registered
  California process server"; label-first, "PROCESS SERVER:") plus the POS-010
  "Person who served papers" → "a. Name:" pair; a bare "Name:" is far too broad
  to anchor on and the compound is not. `_pn_docket_roster_names` reads the
  LASC case-summary shape (`DENG XIAOXIA<tab>Plaintiff`), where the anchor is
  deliberately narrow — the role word must CLOSE the line and the name run must
  be the whole rest of it — because a role word is common in prose and that
  shape is not. The row's own structure is the corroboration, so the
  `_PN_HARVEST_TOKEN_MIN` screen applies to the ROW and not to each token: one
  distinctive word is enough, and a real two-letter surname ("WU JING") is not
  refused. Missing these is how a Reply's Exhibit A shipped a prior case's
  whole party list — or worse, HALF of each name, wherever one token happened
  to be keyed from elsewhere.
- **A TABLE OF AUTHORITIES is never a SOURCE of terms, and neither is the
  inside of a citation.** A table of authorities lists published decisions, so
  nothing in it is a value of THIS case and everything in it is a name the tool
  must not rewrite — harvesting one is all cost. Measured, a single table page
  offers up `Greenwich Investors XXVI, LLC`, `Specialized Loan Serv., LLC`,
  `Peterson Enters., LLC`, `Grancare, LLC` and the published docket `BC543295`
  as this case's parties and identifiers. `_pn_mask_toa_entries` blanks the
  table's ENTRIES out of the harvest input at `_pn_learn_from_text`, the one
  choke point every `register_*` pass goes through, so no pass added later can
  quietly read from a table again. An entry is anchored on its DOT LEADER and
  extended back over the lines that wrap into it, because the name sits on its
  own line above the cite; the walk-back stops at a blank line, a heading and
  the previous entry, so it can never reach off the table into prose — which
  has no leader to anchor on in the first place. A page already rebuilt by the
  destructive re-OCR above carries its leaders as letter-soup, so
  `_PN_OCR_LEADER_RE` (a 25-letter unbroken run — no word is that long, the
  line `_wordish` already draws at 24) anchors those too; delivered folders
  carry such pages. Scoped to the ENTRIES and not the page, so the letterhead
  printed in a table page's margin is still harvested. **Honest accounting: on
  the corpus in hand this changes NOTHING** — `prune_citation_only_terms` and
  `prune_authority_party_terms` already drop every one of those names, and the
  delivered renaming came from a build predating them. It is kept because it
  makes "a table of authorities is never a source" true BY CONSTRUCTION rather
  than as the emergent result of four corpus-dependent pruning heuristics, each
  with its own precondition — and because prevention costs no pool word and
  leaves no bare token behind. The same reasoning covers the inside of a
  citation, where it is NOT merely belt-and-braces: `register_identifiers`
  masks protected citation spans, because a brief citing an unreported case
  gives its trial-court docket ("No. BC543295, 2015 WL 12751760") in a shape
  indistinguishable from a production stamp. That WAS registered and faked;
  span protection saved it in body text and not in the appendix's
  percent-encoded query, where no citation parses, so the published docket
  shipped as "No. GEARHART543295". A term never built cannot be applied
  anywhere, which is the only version of this that holds wherever the parser
  fails.
- **A REGISTRATION number is only safe to track behind its LABEL.** "a
  registered California process server, Registration No. 833, San Bernardino
  County" names one person in the county's public registry, and the pair
  shipped sixteen times. But a bare 3-digit number is a page, an exhibit or a
  paragraph counter far more often than an identifier — the reasoning the
  account-id screen already states — so a SHORT value registers as the LABELLED
  PHRASE ("Registration No. 833" -> "Registration No. 417"), which is the form
  a registry lookup needs anyway, and a 4+ digit bond number still registers
  bare. The e-filing stamp is the same shape of miss: the deputy who accepted
  the filing signs "By: N. Lachikian, Deputy Clerk" and was covered, while the
  Executive Officer/Clerk of Court signs with a role
  `_PN_COURT_STAFF_NAME_FIRST_RE` did not carry, so that name shipped on every
  stamped page.
- **A fake is never the name of an AUTHORITY the corpus cites.** "Stockton" is
  in the name pool and the corpus cited *Stockton Theatres, Inc. v. Palermo*
  (1956) 47 Cal.2d 469. The citation survives the forward pass — that is what
  span protection is for — but `DeAnonymize` searches for FAKES
  case-insensitively, so the first reversal rewrites the authority.
  `_pn_authority_tokens` reads the party words of YEAR-BEARING cites only
  (harvesting from every "X v. Y" scoops up the document's own caption, and then
  no party can be replaced at all); `registry.avoid_words` refuses them at draw
  time. It also RE-MINTS what was already drawn, which is what makes the screen
  useful rather than merely prospective — the template's parties are bound
  before a document has been read. The pre-scan is the one moment when every
  file has been read and no export has been written, so it now READS everything
  before LEARNING anything and calls `reserve_authority_names` in between.
  A run that REUSED a key moves nothing: reproducing the delivered exports byte
  for byte outranks it, and a fake already in circulation is a worse problem to
  create than the one being avoided.
- **Invariants that keep biting if broken** — a fake must never equal its real
  value (`_pn_guard_distinct_fake`, the `M & M` self-map loop); a state name is
  never faked inside a company name; a state-of-incorporation descriptor ("a
  Delaware corporation") stays verbatim; legal boilerplate is never a "name";
  court-form boilerplate (`_PN_NEVER_FAKE`: a Judicial Council form number
  "CIV-100", the "CASE NUMBER" field label, the "Default Only" checkbox) is
  never registered as a term and never flagged — matched on an alphanumeric,
  case-folded reduction so spacing/dash variants all catch. Extend the set as
  more form boilerplate appears.
- **The FURNITURE of a firm name is kept verbatim, and a KEY ROW IS A LIVE
  TERM.** "LAW OFFICES OF SCOTT STRATMAN" names one person: Stratman. Composed
  word for word it came out "BRAXTON MANSFFIELD BANCROFT MERRICK C WHITLOCK" —
  a string no reader can place, where "LAW OFFICES OF MERRICK C WHITLOCK" says
  exactly as much and hides exactly as much. `_PN_FIRM_WORDS` (law/office(s)/
  firm/associates/attorney(s)/counsel/esq…) and `_PN_NAME_CONNECTORS`
  (the/of/and/for/&, deliberately NOT "a"/"an" — An is a real surname — nor
  "de"/"la") are kept by BOTH composing paths (`_pn_fake_person`,
  `_pn_fake_entity_parts`, which also stops turning a lone INITIAL into a whole
  entity word: "Philip Y Kim" was "Mercer SOLSTICE Whitby"). Kept only while a
  distinctive word is still left to fake, or "The Law Firm" would map onto
  itself and scrub nothing. `_pn_is_generic_token` reads the set too, so none of
  them is ever a bare token.
  **The loop that made this survive every KEEP the operator typed:** the term
  builder already refused "Law"/"of" a bare term — but `write_key` harvests a
  row per word of every composed name, and `_pn_load_key` reads EVERY key row
  back as a live matching term. So the word declined at build time came straight
  back through the key on the next run ("the" -> a surname, applied 19 times in
  one folder), and no amount of bracketing could retire it: a keep is released
  inside a full party match and the loaded row IS one. Both ends are closed —
  `write_key` skips a `_pn_is_generic_token` word when harvesting, and
  `_pn_load_key` builds no term for a single-word generic `*-token` row (the
  registry memo is still seeded, exactly as for the judge's own surname, so a
  delivered export stays reversible). `_pn_restore_furniture` additionally
  repairs a stored composed fake on load, since a loaded row is applied
  literally and would otherwise keep reproducing the very output being
  bracketed away; it refuses any repair that would leave fake == real.
- **A POSSESSIVE is the party's own fake, not a second party.** The registry
  memoizes on the string it is handed, so `_pn_fake_name_token` drawing on the
  RAW token made "RASHO'S" a different real value from "Rasho" and it drew an
  unrelated fake (`Rasho -> ARCLIGHT` beside `RASHO'S -> BALFOUR`) — one party,
  two names, nothing saying they are the same person. Both the person path and
  `_pn_person_token_map` now draw on the `_pn_word_affixes` CORE and reassemble
  around it ("CLEARY'S"), which is what the entity path
  (`_pn_fake_entity_parts`) has always done. An apostrophe INSIDE a name
  ("O'Brien") is not a possessive and stays in the core. `_pn_load_key` repairs
  a divergent possessive row an older build wrote, folding it onto the base
  binding — but only when the base row is there to be authoritative.
- **An INITIAL agrees with the fake of the name it abbreviates.** A filing
  writes one attorney both ways, and only one of the two forms was faked:
  `STEVEN W. BURT -> AMBERLY W. YEARDLEY` beside
  `Steven Wayne Burt -> Amberly Ondine Yeardley`. The initial is kept verbatim
  on purpose (see the next bullet — faking "J." to a whole surname reads
  "TOLLIVER. Forsythe Ivers"), but that left two middle names for one person,
  the same confusion the compound-surname rule exists to prevent, AND the real
  middle initial standing in the clear. Two halves, because the disagreement
  arrives two ways. `_pn_align_initials` (run from `_pn_build_terms` and from
  `_add_terms`, so a declarant harvested per-file lands the same) gives a kept
  initial the FIRST LETTER OF THE FAKE its spelled-out form got — two terms
  are one person when the fakes of one's faked words are a strict subset of the
  other's, sharing ≥2; the registry is injective, so a shared fake means a
  shared real word, never a coincidence. `_pn_initial_spellings` closes the
  other half: bare tokens scrubbed what they knew and left the initial alone
  ("Amberly W. Yeardley") wherever the TEXT abbreviated a name the key spells
  out, so the abbreviated spellings are registered up front, with and without
  the period, carrying the fake's letter. MIDDLE names only, and "middle" is
  measured against the FAKED words, not word positions — the furniture of
  "LAW OFFICES OF Scott C. Stratman" puts the first name at index 3, and
  abbreviating it would invent the thin leading-initial pattern ("S. Stratman")
  this deliberately does not register. A LOADED binding is never realigned, so
  a reused key still reproduces what the delivered exports say. Residual, and
  accepted: a person the key names ONLY with an initial ("Geoffrey A. Bowen")
  has nothing to learn from, so that letter is still the real one.
- **A stand-in for INITIALS is never an ordinary WORD** (`_pn_reads_as_word`).
  `_pn_fake_initials_name` draws each letter on its own, so nothing saw what
  they spelt together and "M.W." came back "A.T." — conspicuous, and
  case-insensitively indistinguishable from the ordinary word wherever the
  export happens to use it. A sweep of every two-letter pair over every registry
  state found **196** such fakes. The check reduces to LETTERS, so the
  separators an initials name carries cannot hide it ("A.T.", "A & T" and "AT"
  read the same aloud, and the reduction is what the leak scans and the reversal
  macro see anyway); a lone letter is an initial, not a word. Only the LAST
  letter is re-drawn, under a key scoped to that name, from a pool excluding
  every completion that reads as a word — so the case-wide letter mapping
  survives and "M & M" stays a repeated initial. `_PN_TWO_LETTER_WORDS` is
  deliberately NOT the Scrabble list: the obscure entries (aa, ae, qi, xu)
  forbid perfectly good-looking initials while protecting no reader from
  anything. The same guard covers the bare-initialism path, which takes the
  acronym of the entity's OWN fake so the long and short forms stay one firm —
  when those initials spell a word that tie is worth less than the word costs,
  and `registry.alnum(..., avoid=...)` settles it.
- **An ADDRESS fakes the STREET NAME and nothing else.** The house number, the
  street-type suffix and the whole City/ST/ZIP tail are kept verbatim — a bare
  number identifies nobody, the street is what does, and the locality is kept by
  house standard anyway. Faking the number broke both directions at once: it was
  keyed on the number-stripped identity, so EVERY house on one street drew the
  same number and "122", "500" and "1450 East Foothill" all became
  "7227 Hickory Blvd" — three real addresses collapsed onto one fake, which the
  registry exists to prevent and which the macro cannot reverse (one fake, three
  Real Values, so it calls the mapping ambiguous and restores none of them).
  Keeping the number makes the whole address injective for free and keeps a
  range ("414-416") reading as one. `_pn_addr_canon` decides the street IDENTITY
  and must fold every spelling of one parcel: it EXPANDS directionals (the map
  used to send "s" to "S", normalising case but never folding "S Figueroa" onto
  "SOUTH FIGUEROA" — two identities, two unrelated fake streets for one office)
  and re-spaces an abbreviation written hard against the name ("S.Figueroa",
  which a whitespace split reads as one token and whose period then dissolves
  into the name). `_pn_load_key` seeds the memo with the NAME alone, reducing a
  key written when the whole composed street was stored.
- **Detectors** (`_PN_DETECTORS`: ssn/email/phone/address/url) run as regex over
  the text in `apply()`; `_detector_cands`/`_term_cands` produce candidates,
  highest-priority longest-non-overlapping wins.
- **Every OCR spelling of one E-MAIL address is ONE address.** A fax scan
  spaced the at-sign out ("barrylaw7 @gmail.com"), split the TLD
  ("BARRYLAW7@GMAIL. COM") and read `g` as `q`; the detector missed the first
  two outright, so the real address shipped in clear text — and the spellings
  it did catch each seeded their own fake, so ONE address went out under three
  ("abernathylaw@", "braddock@", and itself). Half-scrubbed and
  multiply-mapped at once, which is the pair of failures the whole email path
  exists to prevent. `_PN_AT_SIGN` now absorbs a step of horizontal
  whitespace; the TLD tolerates one after the final dot but only for a KNOWN
  TLD, or "bob@acme. Next" would swallow the next sentence's first word; and
  `_pn_email_canon` is what every fake derivation seeds on, so spelling can no
  longer fork identity. `_fake_email` strips the same whitespace before taking
  the address apart, since the two must agree on what one looks like.
- **A whitelisted URL is protected as a SPAN, not merely skipped by the
  detector** (`_whitelisted_url_spans`, in `_substitute`'s protected set beside
  the citation spans). `_detector_cands` always refused a whitelisted host, but
  a bare TOKEN term sees no URL context: a batch that harvested "Google" as a
  name rewrote the host of every appendix verification link
  ("scholar.denholm.com"), and nothing about that is provider-specific — any
  provider host that is also a name-shaped token ("lexis", "westlaw",
  "justia") is one minted fake away from the same corruption. Per the mirroring
  rule, `_surviving_records` ignores the same spans: a value standing where
  `_substitute` refuses to touch must never be REPORTED, or the export is
  quarantined by a leak nothing can ever clear.
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
- **An ALREADY-BOUND survivor is cured, not asked about** (`scrub_survivors`,
  the write-side mirror of `surviving_reals`, run beside `scrub_emails` /
  `scrub_welded`). A worksheet row asking "should I fake this?" for a value the
  case has already bound is not a decision: the fake is minted, the key row
  exists, and the answer can only be yes. Two things put one there, neither an
  operator's call — **a RECORD IS NOT A TERM** (`_term_cands` iterates
  `self.terms`, so anything minted into `self.records` during the run is
  substituted only where its own minting pass looked — the same gap that faked a
  display name at its `Name <addr>` pair and nowhere else), and `apply`'s
  overlap resolution dropping a shorter candidate wherever a longer one claimed
  the span, even when that longer one was then itself dropped for overlapping a
  citation, leaving the span scrubbed by neither. Curing mints no fake, draws no
  pool word and adds no key row. `_surviving_records` is the SINGLE eligibility
  rule the scan and the cure share, for the reason `_weld_core` is shared: a
  value one pass reports and the other cannot touch quarantines an export
  nothing is able to clean. `_substitute` gets the same protected set the main
  pass gets, so a cited authority still stays byte-for-byte and an operator KEEP
  still stays verbatim. ~50 ms an export, early-outing when nothing survived.
- **The ORIGINAL text is EVIDENCE, and the run uses it when it has it**
  (`note_original` / `confirm_findings`). A leak finding claims "real
  information survived into the export"; the run's OWN output cannot satisfy
  that claim, and where `known_fake_words` only INFERS which words are ours the
  unscrubbed original says so outright. "Langley" was one folder's stand-in for
  "Liu" — 44 times in the export, ZERO in the PDF — and it still reached the
  triage worksheet twice, once dragged along by a real misspelling and once
  inside an argument heading. A worksheet row can be marked `yes`, which mints
  the value into an authoritative `--term`, which is how a cited decision came
  to be renamed. The finding is REDUCED to its real remainder
  (`_real_remainder`), not kept-or-dropped whole, because that is what makes the
  worksheet answerable: "Ashely Langley" reads like the tool flagging its own
  output, and the question actually in it is "Ashely" — the complaint's own typo
  of the defendant's given name, which is why it survived the scrub.
  ("Langley" alone reduces to nothing and the row goes; "Langley Submitted No"
  reduces to "Submitted No".) A word is removed only when it is BOTH one of our
  fakes AND absent from the original, so a stand-in the source happens to
  contain is never stripped; and checking only our OWN fakes is the whole
  search, since a word this run never minted cannot be its output whatever the
  original says. A row left with nothing real stops gating delivery, and two
  phrasings that reduce to the same remainder merge into one row. The evidence
  is ALWAYS available, never gated on an output preference: a full run builds
  the unscrubbed body regardless (pure string assembly over pages already
  extracted — no OCR, no second read) and caches it in TEMP keyed by folder
  hash, exactly as `_folder_lock_file` is (`_originals_cache_dir`).
  `--fix-leaks` never reopens the PDFs, so it reads the in-folder copy when
  `original_text_subfolder` wrote one and that cache otherwise. TEMP and never
  the case folder — the case folder is the thing that gets synced and shared —
  and `_clear_originals_cache` drops it the moment the folder comes out clean.
  With no original recorded
  `_real_remainder` returns the value untouched — no evidence is not evidence of
  absence, and without that guard every stand-in would look absent and every
  finding would be gutted.
- **A triage row NAMES the authority it may have come from**
  (`_pn_authority_cite_index` / `authority_note`, the Notes column). "Angela
  White" in a worksheet is a question the operator can only answer by already
  knowing the batch's authorities — and answering it wrong is expensive, because
  a `yes` mints the value into an authoritative `--term` and renames the cited
  decision. "cited authority: Kremerman v. White (2021) 71 Cal.App.5th 358"
  beside the row IS the answer. The same year-bearing-cite harvest the fake-pool
  screen uses, keeping WHICH decision each party word came from. It INFORMS and
  never decides: sharing a surname with a cited decision is not proof (a real
  witness can be called White in a case that cites *Kremerman v. White*), so the
  row is still shown, and an operator's own note is appended to, never replaced.
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
  distinctness gate is the `_PN_COMMON_WORDS` gazetteer (~600 words: high-
  frequency English plus motion-practice vocabulary), so a title-case argument
  heading ("Defendant Cannot Establish...", "For Age Discrimination",
  "Voluntarily Resigned") reads as boilerplate, not a party — but it must never
  swallow a word that is also a real surname in the case (green/smart/raven/
  moore all leaked here) or a fake-pool word.
  **The gazetteer is only ever as wide as the motion types it was built from.**
  It grew out of demurrer / summary-judgment / arbitration / employment corpora
  and carried NO service-of-process vocabulary, so a motion to quash had the
  vocabulary of its own subject matter replaced by surnames: "NOTICE AND MOTION
  TO MABRY SERVICE OF SUMMONS" (Quash), "ELDRIDGE OF SERVICE" (Proof), "a
  registered California process radley" (Server, harvested from a capitalized
  "Process Server Institute" and then applied case-insensitively across four
  files), and `scholar.denholm.com` (Google). Adding the vocabulary is
  necessary and NOT sufficient — a loaded key row is a LIVE term, so the words
  came straight back on every re-run, the same loop the generic `*-token` rule
  exists for. `_pn_load_key` now declines a single-word HARVESTED person/entity
  row whose word is generic (memo still seeded, so a delivered export stays
  reversible); an AUTHORITATIVE row is never declined. Vocabulary that DOUBLES
  as a real surname (Bond, Branch, Store, Manager) goes in
  `_PN_SERVICE_GENERIC_WORDS`, not `_PN_COMMON_WORDS`, for the reason
  `_PN_FORM_LABEL_WORDS` states: withheld from ever becoming a bare token, still
  reportable when a party really carries the name. The lists are no longer the
  only line of defence — `prune_heading_only_terms` answers the same question
  from the corpus, so a vocabulary word the lists have never heard of is
  dropped on the evidence that nothing but a heading ever offered it. Keep
  extending them anyway: the prune needs the word to APPEAR somewhere, and a
  list entry costs nothing.
- **A HALF-SCRUBBED pair is the most dangerous thing the tool can emit, and the
  scans were structurally blind to it** (`half_scrubbed_scan`). "Xiaoxia
  Ingersoll" shipped 102 times in one batch, "Jiayin Sterling" in all seven
  files: one token of a person's name bound, the other not, so the pair READS
  as fully scrubbed and a reviewer skimming for leaks moves on. The blindness
  is structural, not incidental — the suppression above drops a phrase carrying
  one of our fakes unless TWO real name words still stand, a rule written for a
  fake dragged along by a non-name prefix, which by construction leaves exactly
  one. So the shape that matters most was the one guaranteed to be filtered
  out. The scan reports the pair as its REAL REMAINDER alone (the reason
  `_real_remainder` exists: "Xiaoxia Ingersoll" reads like the tool flagging its
  own output, and the question actually in it is "Xiaoxia"), scoped to PERSON
  fakes because an entity's fake word ("Relations", "Operations") stands beside
  capitalized prose constantly. Reported, never repaired — which token is real
  is a question only the key can settle, and a `yes` fakes the remainder alone.
- **A sweep is only as good as the SPELLING it was handed**
  (`fuzzy_survivor_scan`). `surviving_reals` answers "is this value still
  here?", and a fax-generation scan mangles precisely the values that matter: a
  process server's name, bound and scrubbed everywhere the page spelled it
  correctly, still shipped as "Michale Rodgers" and "Miachael Rodgers". The
  near spellings the tool is CONFIDENT about are already terms
  (`_pn_name_variants`); this is the net under them, at the same length-scaled
  fold distance the registry's own typo fold uses (`_pn_name_fold_dist`).
  REPORTED, never repaired — a near-miss substitution would rename a cited
  authority the moment the OCR mangled one, which is the trade the whole method
  refuses. Affordable via a 3-gram index over tracked tokens: a single edit in
  a token of length ≥ `_PN_NAME_FOLD_MIN` always leaves one shingle intact, so
  a shared shingle is a necessary condition and the comparison is never a
  product. The citation mask is now memoized (one entry, keyed on the text)
  because three scans over one export ask for the same masked body and the mask
  runs the whole citation parser.
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
  **A match must hold NO printed word boundary INSIDE it**
  (`_pn_span_is_unbroken`). `_pn_span_is_welded` inspects the characters OUTSIDE
  a match and was the only boundary test there was — so a core found spanning
  several printed words was replaced WHOLE, deleting the text between them.
  "Further, a substantial" shipped as "Furtthorpe substantial" (its reduction
  contains "hera", a four-letter party), "whether a party" as "whetthorpe
  party", and "the length" / "the lender" as "tbrandtgth" / "tbrandtder" —
  that pair consuming two entire lines, a newline and a bracket. A weld means
  characters ran together with NO separator, so a span holding a space, a comma
  or a bare line break proves the boundary was never lost; only an intra-word
  apostrophe/hyphen and a hyphen-then-wrap may sit inside. Applied in
  `scrub_welded` and `surviving_reals_reduced` alike, per the mirroring rule
  below. Losing the punctuation-variant coverage the reduction used to give by
  accident ("GENERAL MOTORS LLC" for "General Motors, LLC") is why
  `_pn_depunct_spelling` registers that spelling as a real ENTITY term instead —
  better than the reduced pass ever was, since a term yields to an operator KEEP
  and to citation protection. Not on the person path: a comma there is
  structural ("Burt, Steven Wayne" is surname-first).
  **Off a splice-flagged page the LONG tier fires on a WHOLE TOKEN**
  (`_pn_span_is_whole_token`). `_pn_span_has_hard_seam` sees a boundary lost
  where a span MEETS its neighbour; a token with no neighbour at all has no
  seam to find, so "HELENRASHO" — the plaintiff's full name with its space gone,
  alone on its line — shipped in a complaint's export while the leak scan called
  the file clean. A whole printed token reducing to exactly a tracked party's
  name cannot be a fragment of a longer word, and `_pn_span_is_unbroken` has
  already said it holds no boundary inside. Both tiers are COLLECTED on every
  page now; the per-match checks decide which may fire.
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
- **Nor are the form's own FIELD LABELS.** A form prints the label hard against
  the answer it asks for, so a harvest that reads the pair as one run offers the
  label up as a name and the tool then rewrites the form's furniture: "CITY AND
  ZIP CODE" came back "CITY AND ZIP CRESSWELL" and "BRANCH NAME" came back
  "BLUMEN NAME" — the form no longer saying what its own fields are, to protect
  nothing. Two guards, because the damage arrives two ways: the whole caption
  label is in `_PN_NEVER_FAKE` ("branchname", "cityandzipcode", "shorttitle" …,
  matched on the same case-folded reduction), and the WORDS labels are built
  from are in `_PN_FORM_LABEL_WORDS`, read by `_pn_is_generic_token` so none of
  them can become a free-standing token however it was harvested (that is the
  one that bit: "BRANCH NAME" registered `BRANCH`, "CITY AND ZIP CODE"
  registered `CODE`, since "Name"/"City" were already generic). Kept SEPARATE
  from `_PN_COMMON_WORDS` on purpose — that gazetteer also decides what the leak
  scans call boilerplate, and a word swallowed there stops being reportable, so
  a party really named Page or Short keeps their full name registered, keeps
  being scrubbed, and keeps surfacing for review if a bare one survives.
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

**...and the dark pixels must form a RING, or they are a glyph**
(`_InkRaster._has_border`). Size and aspect alone cannot tell a printed square
from ink that FILLS its own outline, and a form indexes every allegation —
`2.`, `a.`, `(1)`, `MV-2.` — printing that index in exactly the place a checkbox
sits, just left of the caption it governs. So the whole numbered body of a
PLD-PI-001 measured square, measured heavily inked, and came out `[X]` with the
number swallowed: page 2 of a four-page complaint reported "33 boxes, 32 marked"
— relief nobody requested, on a document where the checkbox IS the pleading, and
the numbering it is cited by deleted. A printed box is dark the whole way round
its border; an index number's ink is its own strokes, so its bounding box has no
continuous edge. Measured on this repo's fixtures, a printed square scores
**1.00** on its weakest edge and the worst index label **0.22**, so
`_INK_BORDER_MIN` at 0.6 still admits a badly broken border on a poor scan. A
page left with NO box then fails `if not boxes` and falls back to ordinary
extraction, which is what keeps the numbering.

- **The middle band is `[?]`, never rounded** (`_ink_state_from_fill`). A pencil
  tick too faint to separate from scanner speckle is exactly where guessing is
  worst, and the banner counts the unreadable ones.
- **A window holding real text is not a checkbox slot** at all
  (`_ink_span_blocks_window`: two or more alphanumerics), which is what keeps a
  neighbouring column, a gutter number or a wrapped caption from being probed.
  Conversely everything INSIDE a confirmed box is the mark and is dropped from
  the static text, so the export never reads `[X] 3 a. Enter default...`.
- **...except OCR's rendering of the empty box itself** (`_INK_BOX_OCR_TEXT`).
  A scanner with no character for `☐` hands back a letter or two of its shape —
  "CJ", "D", "O" — which is two alphanumerics, so a scanned form blocked every
  window that held one and found no box on the page at all: the export kept the
  raw `CJ x MOTOR VEHICLE` and the banner counted only the phantoms above. The
  artifact is transparent to the block test but is **never read AS a state**: a
  CHECKED box scans as the same letters plus the mark, so calling it empty would
  drop the answer — the raster measures the square underneath instead. Untethered
  these are ordinary text, so a token counts only when it **repeats** across the
  page (`_INK_BOX_OCR_MIN`), which a template artifact does and a middle initial
  does not. A state box also consumes the artifact wherever it sits, not only
  where the rect happens to contain it.
- **One printed box, one state cell** (`_INK_BOX_DEDUP`, plus the claimed-span
  check). Two captions within reach of the same square each reported it, which
  is where `[X] [X] [X] except defendant` and a tally several times the page's
  came from. It matters more now that a box artifact no longer blocks a window,
  since that puts more captions in reach.
- **`_INK_MARK_CHARS` admits no digits.** The ZapfDingbats check does extract as
  `3`, but the dingbat FONT already settles that; admitting bare digits would
  read a stray form number as a check for nothing, and on a scan an OCR'd digit
  falls through to the raster pass, which measures the actual ink anyway.
- **The gate is cheapest-first and must stay that way**: enough checkbox-sized
  squares in the page's own line art, else a Judicial Council form id in the
  footer — matched CASE-INSENSITIVELY (`_JC_FORM_NO_RE`), because a scan reads
  the "I" of PLD-PI-001 as an "l" about as often as not and a strict match
  denied the page the form treatment entirely. That regex only labels and gates,
  so a stray footer code costs a discarded pass; `_PN_FORM_ID_RE`, which decides
  what is PROTECTED from faking, stays strict for the opposite reason. An ordinary filing fails both in ~1.6 ms/page and never reaches the
  `get_text("dict")` or the render. An ink form page costs ~150 ms — negligible
  beside the seconds of OCR a scanned page already pays.
- **Widgets always win.** The ink pass runs only where they are absent, so an
  intact form is never read by inference.
- **The banner and the log both say when a state was inferred**, and ask for a
  check. An inferred checkbox on a default-judgment packet is precisely the fact
  nobody should take on trust, so it is never presented as equal to a widget's.
- Cost of the widget path: one `doc.is_form_pdf` check per document, and a
  ~0.02 ms per-page widget probe.

## Pleading-page extraction (what reaches the export at all)

**Text OUTSIDE the numbered band is still CONTENT** (`_detect_line_anchors`
Step 7). Step 3 collected body spans only to the RIGHT of the gutter and Step 4
kept only rows within half a lead of a line number — both written to stop such
text being ADOPTED onto a numbered line, which was a real bug (the running
footer arriving as `28  ...OPPOSITION TO DEFENDANT'S MOTION TO STRIKE`). But the
remedy was to DISCARD it, and a pleading page carries real text outside its
band: an e-filing stamp above line 1, a left-margin label, and — on the last
page of a filing — the whole SERVICE LIST, which sits above line 1 in its own
block. A Song-Beverly costs memo lost its service list entire: the case caption
naming the plaintiff, the case number, opposing counsel, a street address and
four e-mail addresses, one of which then survived OCR-mangled elsewhere in the
batch precisely because no pass had ever learned it. Discarded text never
reaches the export, so it never reaches the scrubber OR the leak scan, and the
run certifies a file it never read — the same reason `_page_detect_text` takes
the DECIDED form text. Emitted as UNNUMBERED rows, which keeps the original fix
intact: the text is back without claiming a line number, so a pinpoint "p.3:7"
still never lands on furniture. A bare 1-2 digit number LEFT of the body column
is a gutter number whatever the x-clustering decided — pleading paper
right-aligns the gutter, so the single digits sit in their own sub-column and a
page whose 10-29 outnumber its 1-9 puts `dominant_x` on the wider run
("1 SERVICE LIST"). `_FOOTER_MASK_PT` still masks the running footer, which
repeats the document title on every page and carries nothing else.

## Citation linking

`find_all_citations` (full/short-form/supra/statute/rule) over the combined
page text; `resolve_url` per provider. Links are inserted **page-scoped**: a
citation whose text occurs once is linked only on its own page (not searched
across all N — that was O(cites×pages)). `_repair_link_uris` fixes a PyMuPDF
annotation-naming splice. Declarations/complaints skip linking
(`should_skip_linking`).

**A pleading GUTTER NUMBER blinds the parser, and the authority gets renamed.**
The text export keeps the printed line number (`f"{num:>2}  "` + body), so a
citation that WRAPS carries one between its volume and its reporter — and the
reporter pattern tolerates whitespace there but not digits. The cite then parses
as NOTHING, `_protected_citation_spans` returns no span, and the ordinary entity
term rewrites the cited party: a fee-motion corpus shipped six citations naming
decisions that do not exist (*Ewald v. Nationstar Mortgage, LLC* went out as
*Ewald v. Sandpiper Monarch, LLC*), while the tables of authorities kept the
right names so nothing downstream flagged it. `find_all_citations` makes a
SECOND pass with `_blank_gutter_line_numbers` and MERGES what it adds. Merge,
never replace, is what makes a loose heuristic safe: pass two can only ADD a
span, so blanking a digit run that was really a volume costs nothing. Blanking
is length-preserving, for the same reason the newline normalization is. Gated on
`_ANY_REPORTER_RE` so a page that cites nothing pays one scan instead of a whole
second pipeline; a cited page pays ~2×, which is the price of the invariant.

**...and protection must not DEPEND on a parser succeeding.** A parse that fails
fails silently, and the next OCR artefact or unrecognised reporter blinds it
again. So `_substitute` refuses a name-shaped candidate (`_in_authority_context`)
standing between a " v. " and a year-in-parens or a volume+reporter run, whether
or not a citation parsed there. BOTH anchors are required, which is what keeps
it off the document's own caption — a caption's defendant is followed by a case
number and a role word, never by "(2017)" — and the caption exemption is applied
anyway for an inline recital that does carry a year. Protection-only, so its
worst case is a party name left unfaked at that one spot: the trade the whole
method is built on. Relatedly, `_side_is_trusted` needs MOST of a side's
identifying words, not any one — a case with a party named "North" cleared both
sides of *BMW of North America* and stripped its protection outright.

**A page must be APPENDABLE before anything is inserted into it**
(`_repair_page_annots`, called once after the already-linked fast path so a
document we would not have touched is never dirtied). `/Annots 175 0 R` is legal
PDF — "my annotations are over there" — and Word's e-filing export writes
exactly that, then emits `175 0 obj null` for a page that ended up with none.
READING tolerates it (`get_links()` returns `[]`), so the document looks fine
right up to the first `insert_link`: appending resolves the reference, gets a
null, and MuPDF raises "not an array (null)" from OUTSIDE a `fz_try`, so its
default handler calls **`abort()`**. There is no Python exception and nothing to
catch — the run just stops mid-file, the log ending after "Found N citations",
and on Windows leaves a python process at 0% CPU that looks hung. Four of the
six pages of one opposition brief were like this, and every document after it in
the folder went unprocessed. Nothing is lost by the repair: a null `/Annots` IS
no annotations, so it becomes `[]`. Only an indirect reference that fails to
resolve to an array is touched — an absent `/Annots`, a direct null, and an
indirect reference to a REAL array are all things MuPDF already handles, and the
last is both legal and common. Because the failure kills the interpreter, the
end-to-end test asserts it from a SUBPROCESS; an in-process assertion could not
survive to fail.

## OCR (the runtime bottleneck on scanned exhibits)

- **A TABLE OF AUTHORITIES must never be re-OCR'd, and the ratio is why.**
  `_text_looks_garbled` measures the fraction of characters that are letters or
  digits, and a table of authorities is mostly DOT LEADERS — neither. So it
  reads as symbol soup and the page goes into `_reocr_garbled_pages`, which is
  DESTRUCTIVE: the real text is redacted and replaced with 300-dpi guesses. A
  delivered Demurrer's page 5 is 100% `GlyphLessFont` (Tesseract's invisible
  text font) over a single image — the only OCR'd page in its folder — and it
  cost all 28 gutter numbers, put the rotated firm sidebar into body text, and
  turned reporter volumes into letters ("A Cal. App. 4th 857"). Measured on the
  real corpus the tables that SURVIVED cleared the cut by one percentage point
  (0.364 against 0.35), and the tool's own extraction path put one at **0.342**
  — already over. The damage also CONCEALS ITSELF: Tesseract renders a leader
  run as letter-soup, so the rebuilt page measures 0.938 and a second run reads
  it as healthy; the only surviving marker is the font name. The fix is to drop
  leaders from the measurement (`_LEADER_RUN_RE`) rather than move the
  threshold — it has been retuned twice already, once from letters-only to
  letters-plus-digits after digit-dominated damages tables were destroyed the
  same way, and each retune found a new character class. Belt:
  `_page_text_layer_is_sound` is a HARD PRECONDITION — a page whose text
  extracts as thirty-plus readable words, with no `(cid:` and no
  `GlyphLessFont`, is never rebuilt whatever the ratio says. It is deliberately
  NOT an embedded-font test: a base-14 page is perfectly sound and rejecting it
  would shred a good text layer for a property carrying no signal, while the
  page this heuristic exists to catch — a BROKEN encoding — fails the word test
  by construction. Every decision is logged, since a destructive pass that
  leaves no trace but a font name is not diagnosable.
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
- **A DESTRUCTIVE pass must PROVE it helped** (`_reocr_improves`, the gate on
  `_reocr_garbled_pages`' phase 2). The pass redacts a page's real text and
  overlays 300-dpi guesses, and it used to do that on a HEURISTIC alone:
  `_text_looks_garbled` said the old text was bad and the new text was adopted
  sight unseen. Two ways that ends badly, both of which have happened — the
  heuristic misjudges a page that was fine (a table of authorities, a
  digit-dominated damages table; the ratio has now been retuned THREE times for
  exactly this), or the rebuild is itself junk (a page ground down to 72 dpi, an
  image Tesseract cannot read, a page whose ink is a signature). Either way the
  run threw away the true text layer and kept a worse one, and nothing
  downstream can tell: the export reads as prose and the source is gone. So the
  rebuild is now measured against the same bar that condemned the page — if the
  new text ALSO reads as garbled it bought nothing and the ORIGINAL is at least
  what the document says, and if it recovered less than `_REOCR_MIN_YIELD` of
  the word-shaped tokens the page already had it lost content. The page keeps
  its own text, and the refusal is logged. This is the belt that makes the
  ratio's remaining false positives cheap: a misjudged page now costs a wasted
  render instead of the document.
- **A rebuilt page SAYS SO in the export, and its old layer is kept where that
  is free.** Two halves of the same gap. The export never marked a rebuilt
  page, so 300-dpi guesses sat in the middle of an accurately-extracted
  document reading exactly like the rest of it — which is how "A Cal. App. 4th
  857" shipped with nothing flagging it. `_REOCR_ATTR` (hung on the Document
  like `_LOW_DPI_ATTR`, recorded by `_note_rebuilt_page` only once the overlay
  has actually landed) drives a page banner in the same voice as the low-dpi
  and ink-form ones: an inferred reading is never presented as equal to a read
  one. The other half is that the OLD text was thrown away, and a broken
  ToUnicode is usually a SUBSTITUTION CIPHER — the glyphs are in the right
  order, so the word lengths, the spacing, the digits and the punctuation are
  the document's own and only the letters are wrong. Beside a reconstruction
  that reads "A Cal. App. 4th 857", that settles the argument. So
  `_garbled_appendix` prints it, at the end, **in the UNSCRUBBED copy only** —
  the `Original Text (real names - do not share)` file and the TEMP evidence
  cache, never the shared export. That line is where it is because garbled
  text is exactly the shape the whole-word patterns cannot match (the reason
  `scrub_welded` and the reduced scans exist): in the deliverable it would be
  real party names nothing can scrub, and the review scans would fill the
  worksheet with soup nobody can answer. In the do-not-share copy it costs
  nothing — that file carries the real names in plain text already. Both
  consumers of the unscrubbed body get it, because `--fix-leaks` reads the
  in-folder copy when there is one and the cache otherwise and the two must
  agree; as EVIDENCE it can only ADD words, and `_real_remainder` only removes
  a word ABSENT from the original, so a noisier original keeps a finding and
  never drops one. `_garbled_keepable` is the "is there anything usable here"
  gate: unmapped glyphs (`(cid:3)(cid:15)`) and replacement characters come out
  first and what is left must clear `_GARBLED_KEEP_MIN`, because a page of cid
  tokens carries no length, no spacing and no digits — it can settle nothing
  and costs the reader attention to skim.
- The grind never skips a page, but a page re-rendered below `_OCR_LOW_DPI`
  (150) has traded away real recognition quality, so it is named in the log as
  low-confidence. Silence there read as "recognised fine". **And the EXPORT says
  it too** (`_note_low_confidence` → the page banner in `_write_text_version`),
  because the log is a separate file that does not travel with the shared
  export: text recognised at 99 dpi comes back mostly wrong and otherwise sits
  in the middle of an accurate document looking exactly like the rest of it. A
  reviewer needs to know which paragraph is the document and which is a guess.
  Same reasoning the ink-form banner already follows — an inferred checkbox is
  never presented as equal to a widget's, and it says so where it is read.
- Per-page **timeout + grind**: a stalled page is re-rendered at lower
  resolution and retried, never skipped, never hangs (the earlier 0%-CPU hang).
- Env vars: `PDF_LINKER_OCR_WORKERS` (default cores-1, cap 10),
  `PDF_LINKER_OCR_TIMEOUT` (default 600s).
- **A misspelling in an export has TWO possible authors, and the run says which
  one wrote each** (`_report_minted_misspellings`). The typo fold mints one on
  purpose — a source that spells a party several ways gives each spelling its
  own reversible stand-in, and a typo of the one fake is what keeps them
  reading as one person — while the scan mangling a word means the page wants
  re-scanning. Opposite remedies, identical shape in the export — every
  `_PN_CONFUSABLES` pair is a plausible scan slip, which is exactly why the
  fold uses it. The worst collision is closed at the SOURCE: "a y came out as
  a v" is the signature of a page recognised below `_OCR_LOW_DPI`, where a
  thin descender is the first stroke lost — and the map used to funnel `u`,
  `w` AND `y` all onto `v`, so the fold was deliberately minting that exact
  artifact (43 of the 192 pool surnames carry a `y`). The map is now an
  INVOLUTION — every letter swaps with exactly one partner, so it is injective
  and a `v` is minted only from a `u`: a v-for-y in an export is ALWAYS the
  scan's work. (A reused key still reproduces delivered exports byte for byte
  — the memo pins every binding — but a re-run WITHOUT its key re-derives
  folded fakes under the new map, which is the standing rule for any change to
  the fold.) Measured on this repo's own settings — Tesseract
  5.3.4, `_ocr_base_dpi`, `_OCR_CONFIG` — a clean or lightly-degraded render is
  error-free at 300 and 198 dpi and stays so at 150; a degraded one breaks down
  at 150 (21 words wrong) and collapses at 99 (24-43, the wrong words being
  exactly "Ververty" for Beverly, "Vurtiey" for Yardley, "Vextesday's" for
  Yesterday's). So the grind's own low-dpi REVIEW line and this report are, in
  combination, the whole diagnosis: a misspelling NAMED here is ours and
  correct, one that is not came off the page. Reported at INFO — nothing in it
  is a fault, and saying so is the entire point. The same A/B measured
  `preserve_interword_spaces=1` as **exactly neutral** on character
  recognition (identical error counts in every dpi × degradation cell); it
  buys the spacing it is there for and costs no accuracy.

## Diagnosing a run that just stops

**A fatal failure must be VISIBLE** (`_install_crash_logging`, installed before
the first log line). The normal launch is `pythonw.exe`, which has NO console:
`sys.stderr` is None, so an uncaught exception's traceback is written precisely
nowhere. The process vanishes, `pdf_linker.log` stops wherever it had got to,
and Task Manager shows nothing running — indistinguishable from a hang, and what
sent an operator back to double-click the launcher two more times on a folder
whose first run had already died. Two hooks, because the two deaths differ:
`sys.excepthook`/`threading.excepthook` catch an ordinary exception (a
lazily-imported dependency is the usual one, and the usual reason the SAME
folder works on one machine and not another), and `faulthandler` writes into the
log's own stream for a C-level abort, which raises nothing at all and so cannot
be hooked — MuPDF calls `abort()` on a fatal error, so this is the only thing
that leaves a trace of one.

**A missing core dependency fails at STARTUP, by name**
(`_require_pymupdf`). `fitz` is imported lazily at each use site, so its absence
surfaced as a traceback 34 files into a run's setup — while openpyxl, the other
spreadsheet dependency, had always failed with a polite line naming its pip
command. The message names THIS interpreter by full path: the launcher runs the
`pythonw.exe` beside `sys.executable`, a machine can have several Pythons, and a
bare `pip install pymupdf` at whichever is on PATH is exactly how a folder ends
up working on one machine and not another. Checked after the `--fix-leaks`
branch, since that pass is text-only and needs no PDF.

**Log the filename BEFORE the work, not after.** `_pn_prescan_folder` names each
file as it opens it (`Pre-scan 17/34: X.pdf`), so when a death takes the
interpreter the LAST line names the file that did it. A line written afterwards
is a line never written. That phase also reads the whole folder before writing
anything, so without it a large folder simply went quiet for minutes.

**One run per folder** (`_acquire_folder_lock`; the lock file lives in TEMP,
keyed by a hash of the folder path — `_folder_lock_file`, so the case folder
never carries one. Kept in the folder it sat beside the exports, and since the
file is removed only on a CLEAN exit — the OS having already dropped the lock
itself when a run dies — every crash left one behind looking like debris. A
stale temp file is harmless: the lock is the OS's, not the file's. An older
build's in-folder `pdf_linker.lock` is swept up on sight). Both launchers start the work
detached and silent, so "nothing happened, click it again" is easy — and a real
log shows it done three times on one 34-file folder inside four minutes. Each
run saves `<name>_temp.pdf` then REPLACES the original, and they share the
exports and the key, so concurrent runs can replace a PDF another is mid-read
on. An OS-held file lock, NOT a pid file: the tool can die without cleaning up,
and a lock the dying process had to tidy would go stale on exactly those crashes
and block the folder forever — the OS drops a file lock however the process
ends. RE-ENTRANT per process (the hazard is two processes) and it FAILS OPEN: if
the lock cannot be taken for any reason other than "someone holds it", the run
proceeds, because a lock that cannot be acquired must never stop legitimate
work. `PDF_LINKER_NO_LOCK=1` skips it.

**`_InkRaster` caps its render** (`_INK_MAX_PIXELS`, mirroring
`_OCR_MAX_PIXELS`). A bitmap scales with page AREA, so an oversized page asks
for an allocation no fixed dpi bounds, and MuPDF failing that allocation aborts
the interpreter. Dropping the dpi only costs box detection on a page that size,
which then falls back to ordinary extraction.

## The upload cap (a folder with more than 20 documents)

The exports go to a drafting model that accepts at most **20 files**
(`max_text_files`, default `_COMBINE_DEFAULT_CAP`). Most folders are well under
it; a large case is not, and the operator's remedy — merge some exports by hand
and remember which — is the kind of bookkeeping that fails quietly. So
`_combine_exports_for_upload` does it, once every export is written: the excess
is **COMBINED** into single files that say so in their own first line, list
their members, and hold each document in full behind its own DOCUMENT banner.
Nothing is dropped and nothing is shortened; the parts are removed only once
the combined file is safely written, so `Text Files` is exactly the deliverable
set and nobody has to work out which of the files in front of them to skip. The
`Original Text` sibling (real names, never shared) is left per-document — the
cap is about what gets uploaded.

**Which files, in the operator's two rules.** Rule ONE
(`_combine_same_name_groups`): the same name with a part marker after it —
`Brief (1)`, `Brief part 2`, `Vol. II`, `Brief 2 of 5`, a bare trailing index.
`_combine_split_part` strips the marker and demands `_COMBINE_BASE_MIN` LETTERS
still stand, so "1 of 3" (which reduces to "1 of") groups with nothing, and the
bare form demands a separator, or `\d{1,2}` takes the last two digits of
"Order 2024" and files it under "Order 20". Rule TWO: the **smallest** exports,
bundled — the (excess + 1) smallest lands exactly on the cap. Both may run.

**Only as much as the cap asks.** `_combine_pick_groups` takes the smallest
group first, whole while it fits, and SLICES the one that would overshoot to
the first (excess + 1) parts. Combining is a cost — one leak holds every
document in the file, and each member loses its own filename — so a folder two
over does not fold a twelve-part exhibit set into one file when a two-part
declaration would have done. A part left out of a slice is still a complete
document under its own name, and the slice says so ("COMBINED 3 of 12 parts").

**A grouping already sent is REPRODUCED, not re-derived**, for the reason a
re-run reuses `pseudonym_key.xlsx` rather than re-deriving the fakes: adding one
document moves which files are "the smallest", so a re-derived plan reshuffles a
folder whose drafts are already written. The DOCUMENT banners are the record —
`_combined_sections` reads the members back off the previous run's own file, and
the header carries nothing volatile (no folder count, no timestamp) so an
unchanged folder reproduces the delivered file byte for byte. A prior grouping
is kept even once the folder fits again, and `max_text_files = 0` (combining
OFF) still honours it: "off" stops the tool combining, it never silently
re-splits a file the operator has sent. A combined file is superseded only once
**every** member exists as a separate export again; a member whose source PDF is
gone (or failed this run) has its section carried forward verbatim, because that
file is the only copy of it there is.

**Factored into the leak gate and `--fix-leaks`.** The gate quarantines FILES,
so `_combine_remap_tracking` moves `written` / `leaked_by_file` onto the
combined file — otherwise a leak is reported against a part path that no longer
exists, nothing is renamed and the export ships. Combining therefore runs BEFORE
the worksheet and the gate. A leak in any member holds the whole combined file:
that is the cost, and the gate's message says how many documents are held rather
than leaving the export count to be read as a document count. `--fix-leaks`
treats one as the single file it is — the fix applies across the whole thing,
the quarantine is released whole, and the grouping is never re-split (the
operator has already uploaded that shape) — but every finding is located by its
member document (`_pn_locate_export`), because each document in the file numbers
its pages from 1, so a bare "p.3:7" names as many places as there are documents,
and the member name is the only thing left in the worksheet saying which SOURCE
document a leak came from. A combined export QUARANTINED by an earlier run is
dropped by the same reachability rule `_pn_drop_superseded_quarantine` applies
and cannot reach here (the `.LEAK` is named for the combined file, not for any
source PDF), the moment every document in it has a fresh export of its own.

## Performance notes

- Term/record regex patterns are **compiled once** per run via a
  `Pseudonymizer._compiled` cache — Python's own re cache caps at 512, so a
  large case recompiled every pattern on every page (was ~75% of the scrub pass).
- Files are processed **heaviest-first** by OCR-weighted cost; the one-click
  re-run launcher is written **up front** so an interrupted run still leaves one.

## Folder artifacts (what a finished folder should contain)

**Both launchers run the work DETACHED AND MINIMIZED** and return at once
(`_bg_launcher_bat` / `_bg_launcher_sh`, shared so the pair cannot drift). The
re-run was already detached but echoed a five-line banner and sat on a
`timeout /t 3`; Apply-Leak-Fixes ran in the FOREGROUND and held its console open
on a `pause`. Both now echo nothing and wait for nothing: a window that closes
in milliseconds cannot be read anyway, so the notes live in the file's own `REM`
header and the feedback channel is the one the folder already has —
`pdf_linker.log` throughout, then a `DONE <time>.txt` stamp. `_launcher_exe`
gives BOTH the windowless `pythonw.exe` where it exists; Apply-Leak-Fixes used
to force the console interpreter on purpose (it printed an exit code), and that
reason is gone. `/min` and NOT `/b`: `/b` attaches the child to the launcher's
console, which is about to close, so a run that fell back to `python.exe` could
take a close event with it — a new minimized window is inert. POSIX uses
`nohup … &` so the work survives the Terminal window closing.

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
