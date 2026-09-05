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
**…except a RECYCLED name, on a re-run that finds triage still pending.** Pinning
is what a reused key is FOR, so exactly one thing overrides it. When the pool
runs out it mints `<pool word><n>` — "Deverell5", "quenby3@postbox9.org" — and
the key then pins that forever, in a document a judge reads. But leak triage
PENDING (`_pn_triage_pending`: a quarantined `*.txt.LEAK`, or a worksheet row
with nothing typed in its Fix? cell) is the run's evidence that the folder was
never handed on: the gate held an export, or the operator has not answered yet,
so no draft has been written against these names and a stand-in can still move
for free. `_pn_load_key(remint_recycled=True)` then DROPS such a binding whole —
no term, no memo, its word left out of the used-pool — and the value is drawn
again, landing on a clean word now that the pool has been enlarged.
`_pn_recycled_fake` is deliberately narrow: a POOL WORD hard against a number,
which is the only shape the exhausted-pool fallback mints. A house number, a
case number and a production stamp all carry digits and none of them qualifies.
Read BEFORE this run writes anything, so it describes the state the operator
left behind, and NEVER consulted by `--fix-leaks` — that pass works on text that
is already scrubbed and never reopens the PDFs, so a fake it moved would be left
standing in the export with nothing to reverse it.
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
**…and those rows are WRITTEN together, under the row they are spellings of**
(`_pn_key_party_order`, `_pn_key_binding_blocks`, `_PN_KEY_CATEGORY_RANK`). The
sheet sorted by category and then alphabetically, so a party's misspellings were
scattered down the key — and `alt spelling` says a row is another spelling of
SOME other row and never WHICH, so the one thing that Status word states could
be acted on only by searching the sheet for the Replacement. The key is ordered
as PARTY BLOCKS now: the full name, its own alternate spellings, then each of
its bare tokens with that token's spellings under it, so
`Sara Ardeshirpour-Zartoshti` is followed by `Sara`/`Sarra` and by
`Ardeshirpour-Zartoshti`/`Ardeshirpour- Zartoshti`/`Ardeshirpour`/`Zartoshti`
rather than by whatever party sorts next. A token belongs to a party because a
composed fake is built WORD FOR WORD from the real, so a block whose Replacement
is a run of consecutive words of the party's Replacement is a word-level binding
of that party — the injectivity argument `_check_key_completeness` already makes
from the other side. A RUN and not a single word, because a token row is not
always one: `_pn_entity_bare` registers `Midland States` off
`Midland States Bank`, and a compound surname registers each half beside the
whole. Taking those in is also what makes the block ORDERABLE — children sort by
where the run starts and, at one start, longest first, which is the party's own
word order and puts `Thornfield Quarry` ahead of the `Thornfield` it begins
with. Left outside, that pair could not be ordered at all: the party's full fake
must precede both, so the short form would have to be spliced INTO the block and
the grouping undone. A token is claimed by ONE parent — the first in the sheet's
own order — so a surname two parties share (`Doe`) is written once, and a block
nothing claims (a bare harvested surname, an address, a docket) keeps its place
in the ordinary category run. The nickname rule is unmoved and is now asked of
BLOCKS (`_pn_key_longer_first_blocks`, which the row-wise
`_pn_key_longer_first` calls with one row per block): pulling a row out of the
middle of a party to satisfy it would undo the grouping for no reversal benefit,
since a party's own longer fake already leads its own tokens. Two blocks CAN
each hold a fake that is the front of one of the other's, which no ordering
satisfies, so a pair is moved at most once — the alternative is a loop that
swaps forever, and the shape does not arise once a short form rides with its
party.
**…and a spelling that does NOT share the Replacement is read off the VALUES**
(`_pn_key_word_fold`, `_pn_key_rearranged`). The grouping shipped keyed on
rows sharing a fake, and two kinds of spelling never do, by design. A
surname-first TABLE spelling (`Vazquez Manuel`, `derived`) carries the party's
words in the other ORDER, and sorted as a `person` row of its own it sorted
FIRST, claimed the tokens in its own word order and put the reversed spelling
at the head of the party — `Ashworth Rachel`, `Ashworth`, `Rachel` under
`Rachel Ashworth`. And a MISSPELLING — the OCR near-miss the registry folds,
or the one the operator declares with `*` — takes a mirrored SLIP of the
canonical's fake and never the fake itself (`fold_onto`: two Real Values on
one Replacement is what the macro calls ambiguous), so the twenty scanned
spellings that motivated the LEAKS grouping shared nothing the key's could
see, and landed as separate parties after the alphabet. Both are decided from
the FOUR WORDS of the two bindings and never from registry state, because a
re-run off the delivered key re-folds nothing (every fake is pinned, and the
`*` cell is retired once applied) and the order the sheet comes back in must
not depend on which run wrote it. The mirror leaves enough in the values: the
fake deviates by the SAME op the real did, so the two length deltas are equal
and the fake sits at exactly the op's distance from its base (one edit for a
confusable or a swap, `reps` for letters duplicated or dropped), and a folded
fake is never a POOL WORD — the near-twin rule puts every pool word two edits
from every other, so a word one edit off a pool word is a typo of it and a word
`reps` edits off that IS one is a draw; the recycled `Deverell5` is one edit
from its own word and refused by name. A whole-name spelling (the words
rearranged, or word for word with one folded, `Manuel Vazqez`) sits right
after the name it spells and before the tokens; a one-word fold sits under
the token it is a slip of, wherever that token was written; one level only,
or two spellings a slip apart would each claim the other. Which spelling
holds the pool word is the registry's business for a fold it INFERRED (the
shortest-first pre-bind drew `Palladina` before `Palladino`), and the one that
folded onto it is written under it; a `*` settles it, because the starred
spelling always holds the pool word (the alias rule, below), and where the
party itself was built from the misspelling the starred spelling takes the
token's slot in the party and the misspelling is written under it. A nickname's fake is the FRONT of its full name's, which
reads as the same drop the real made, so `Ken` rides with `Kenneth` — where
the nickname rule already wants it. The reversed row is also MARKED
`alt spelling` now, its count joining the owner's: the macro reverses it
word by word off the parent's own token rows, so forward-only is honest for
it, and `_pn_load_key` carries `derived` back on the re-run — a loaded row
is otherwise an ordinary `person`, and the reversed spelling would lead the
party on one run and not the next.
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
pin still does its job.
**…and every reader of the key finds the main sheet by NAME, never by
`wb.active`** (`_PN_KEY_MAIN_SHEET`, `_pn_key_main_sheet`). The active sheet
is not something the tool wrote: it is whichever TAB was selected when the
file was last saved, and Excel records it. An operator opened the key, clicked
across to the pinned tab to see what it held, saved, and the next
`--fix-leaks` read the pinned sheet as the main one (a handful of `no match`
rows), the pinned sheet again as the pinned sheet, and never saw an applied
binding — then rewrote the key with nothing but the leak fixes it had just
minted. `_pn_key_looks_like_ours` could not refuse it, because both sheets
carry the same header. Resolved by name at every reader now (the loader, the
fingerprint check, and the LEAKS decision reader by the same rule), falling
back to the one sheet that is not the pinned one for a key an older version
titled differently, and the loader logs when the tab it read is not the one
that was left selected. `DeAnonymize.bas` has the same exposure and should
select the `Pseudonym Key` sheet by name rather than taking `ActiveSheet`. "Carried" is REACHABILITY, not the row's own count: the
macro reverses a composed fake word by word, so the token rows of a party whose
full name is the only form the export used are load-bearing even though they
matched nothing themselves.
**Every key row QUOTES the sentence its value stood in — TWICE, in ONE cell**
(`Context`, `note_key_context`, `_pn_context_cell`). A row says
`Rasho -> Strangeways`, and
whether that binding is right depends on how the document used the word — the
question the LEAKS Context column already answers for a decision not yet made,
asked here of one already made. The FIRST quote is read from the UNSCRUBBED
body, of necessity: by the time the export exists the real value has been
replaced, so only that copy still contains it. The consequence is deliberate
and worth stating — `pseudonym_key.xlsx` now carries sentences of the real
document, not merely its real values. It was never a shareable file (it is the
reversal map), so this changes how revealing it is, not which file is safe to
send. The SECOND quote is the same question asked of the EXPORT — searched by
the FAKE, since the real value is no longer in that text, and bolding it, so
the operator reads what the document said beside what the deliverable now says;
scoped to records that APPLIED (count > 0), because a fake never applied stands
in no export and a miss still costs a scan. **Both halves describe ONE
passage of ONE document** (`_pn_context_hit`'s `within`, a site carrying the
quote's line range and how many sentences it grew by). They were independent
searches of two different bodies and came apart three ways: a different
OCCURRENCE — a party whose first prose occurrence sits inside a protected
citation is never replaced there, so the export half went hunting and quoted an
unrelated sentence further down; a different amount of GROWTH — the span grows
by whole sentences while under `_PN_CONTEXT_MIN`, so a fake shorter than the
real value drops its sentence under the floor and the export half swallows the
sentence after it, which is the "whole extra sentence" an operator sees on one
side only; and a different DOCUMENT — the first file to name a value won the
original quote in one loop while the export quote was taken in another, from
whichever file's export the fake turned up in. The site fixes all three: the
export half is read in the same loop, from the same passage, replaying the
growth rather than re-measuring it. A hard restriction, deliberately — where
the fake does not stand in that passage there is no second half, and the cell
shows the original alone, which is honest where an unrelated sentence is not
(and in the citation case it is also exactly right: nothing in that passage was
replaced). Both sit in ONE cell at column
**D**, the original on top, then a rule (`_PN_CONTEXT_RULE`), then the export's
sentence. The BINDING leads — Real Value at **B**, Replacement at **C**,
adjacent — and the evidence follows it, at the owner's direction: the pair the
sheet exists to state is what every reader is here for, and quoting 120
characters of sentence BETWEEN a value and its replacement made the row's own
mapping the thing you travelled across the cell to reach. **One cell and not
one column each**, at the owner's direction: the pair is read as a single thing, and side
by side it costs two wide columns and a lot of sideways travel. One cell and
not two ROWS for a harder reason — this sheet is read by other programs a row
at a time, and a second row per binding would make every one of them read a
phantom party. **Identical quotes collapse to the original alone**, which is
most rows: the value usually stands in a sentence nothing else in it was faked,
and printing that twice is a cell of noise hiding the rows where the pair
really does differ. Compared on the text, not on whether anything WAS replaced,
because that is the question the reader is asking of the cell. The rule is also
the seam the cell is SPLIT on when a later run reads its own key back
(`_pn_context_split`), so it has to be a line nothing else produces — no filing
contains a line of em-dashes around a bare word — and a key written when the
two had a column each still reads, its second column taken as it stands.
Dropping a column is safe for the same reason inserting them was, and worth
stating because the reverse is the obvious fear — `DeAnonymize.bas` does NOT
read this sheet positionally, it scans the header row for
`real value` / `replacement` / `status` and uses whatever columns they land in
(`LoadKeyWorkbook`, where Status is already optional for keys predating it), and
`_pn_load_key` / `_pn_key_context_on_disk` resolve by header name too. The only
thing a moved column can break is a POSITIONAL fingerprint, so
`_PN_KEY_FINGERPRINT` is cut to the two headers every layout has led with plus
a by-NAME check that a Replacement column exists, and a key from any older
version still reads as ours. (A test that indexes a
key row by number is making the same mistake — a batch did, and now take the
index from `_PN_KEY_HEADERS`.)
**A key row is quoted only where its value stands as a WHOLE WORD**
(`_pn_context_hit(bounded_only=True)`, from `note_key_context`). The search
falls back to a bare substring for the worksheet, because a welded finding
has no bounded occurrence by construction — and the same fallback on a KEY
row quoted a `--term` "Ken" out of "DECLARATION OF KENNETH W. BOSWORTH": the
row had matched nothing (count 0), and the cell read as the tool having taken
"Ken" from that sentence while the full name's own row was faked beside it. A
term matches whole words, so where its value never stands as one it matched
nowhere and the honest cell is empty; the worksheet keeps the fallback.
**And the quote SAYS which document it came from, and where** (`File` at **E**,
`Where (page:line)` at **F**, `_pn_site_where`). Evidence the operator cannot go
and check is worth much less than it looks: a folder is a dozen filings, the
Context cell quotes one sentence of one of them, and "which one, and where in
it" was answerable only by searching every export for the sentence. The format
is the LEAKS worksheet's, and it is the SAME function that produces it
(`_pn_where_label`) under the same header (`_PN_KEY_WHERE_HEADER`) — two columns
naming one measurement in two wordings read as two measurements. What it reports
is the passage the QUOTE was cut at, not every occurrence of the value the way a
LEAKS row does: that row's job is to send the operator to each place a leak
survived, while this one explains one cell above it. So it is a RANGE, since a
sentence on pleading paper runs over two or three gutter lines — `p.4:7-8`,
spelling the page twice only where the quote really crosses one (`p.7:27-p.8:1`),
and `line 1-3` for a Word body, which has a line number and no page and must
never be given a `p.?` naming a page the run does not know. Read off
`_pn_context_prep`'s own line table, because that table DROPS the blank and
gutter-only lines and an index into the parsed body would be off by every one of
them. Minted in the same statement as the quote, from the site it was cut at —
never measured in a second pass, which is how a location comes to point at
another file's sentence — and carried forward from the key on disk as a UNIT
with that quote (`_pn_key_context_on_disk`, now a triple), so a row can only
name the document its own Context came from. A row with no quote claims no
location: an empty Context beside a populated Where reads as a place to go and
look. An older key simply yields nothing for the two columns and gains them on
the next rewrite.

**A page is named by its PDF number, with the printed one beside it**
(`_pn_page_label`). The older rule preferred the PRINTED number, on the ground
that it is what the operator reads off the paper — true of a filing that is one
document, and wrong of the compiled ones this tool mostly meets. A declaration
bundle, an exhibit set and a compendium RESTART their numbering at every
sub-document (`_footer_page_label` reads each page's own stamp precisely so a
reset cannot desynchronise it), so the printed number is not unique in the
file: a value standing on the 43rd page of a PDF was located at `p.1`, and the
four pages it stood on came back as `p.1, p.2, p.3, p.4` — four numbers naming
no page a reader can turn to, since a dozen pages of that PDF print "1". The
PDF page is what a viewer's page box takes and what the export's own
`====== Page 43` header says, so it is the half that can be ACTED on; the
printed page is the half that can be CITED, so it is kept, appended only where
it DIFFERS (`p.43 (printed p.1):16`). An ordinary born-digital filing, whose
PDF page 3 prints "3", reads `p.3:7` exactly as before and a delivered key's
Where column does not move.
**…and a REVIEW banner does not cost a page its number at all**
(`_PN_PAGE_HEADER_RE`). A page whose text layer was REBUILT, whose images were
read by OCR, or that the grind recognised below `_OCR_LOW_DPI` carries a
" — REVIEW: …" clause between its number and the closing rule. The header
pattern demanded that rule hard after the number, so every such header failed
to match — and a header that does not match does not merely lose its own page:
the parser keeps the LAST page it did match, so every line of every
banner-bearing page after it is reported at that page's number. On a filing
whose scanned exhibits all carry a banner that is the whole back half of the
document collapsed onto the last clean page. The banner is exactly the page a
reader most needs to find, since its words are guesses.
**An older layout is not left standing, and the run SAYS so.** Reading by name
is what makes the key readable; the REWRITE is what migrates it. `write_key`
re-emits `_PN_KEY_HEADERS` whole every time, and both operator paths reach it —
a full re-run, and `--fix-leaks`, which never reopens the PDFs but does rewrite
the same key it loaded. So clicking either one normalises the column order in
place, carrying every binding and both Context quotes across (verified end to
end in `test_key_layout_migration.py`, on the pre-Replacement-move order and on
the older order that had no Context column at all; the two-column era's
`Scrubbed Context` folds into the one merged cell by the same rule
`_pn_context_split` already states). `_pn_load_key` logs one line when the
header row it read differs from `_PN_KEY_HEADERS` — silently handing back a
different column order than the operator last saw reads as the tool having
damaged the key, which is the one file this project treats as unlosable. The
single path that does NOT migrate is `--fix-leaks`' early return on a REJECTED
decision, which is right: that pass resolved nothing, so it writes nothing, and
the next successful click migrates the folder. FIRST document to use a value owns
its quotes, so a re-run of the same folder reproduces both halves; a quote this
run cannot re-derive is carried forward from the key on disk
(`_pn_key_context_on_disk`, both halves — it splits a merged cell back at its
rule), because the key outlives the folder's contents.
**…and that carry-forward is a PAIR, or the `within` restriction is undone at
the write site** (`row_evidence`, in `write_key`). `note_key_context` mints the
original quote, the export quote and the location in one statement precisely so
the three describe one passage of one document — and `write_key` then took them
apart, each half asking its OWN emptiness whether to reach for the key on disk.
The export half is empty in a case this design calls HONEST: the row's fake
does not stand in the passage the original was quoted from. So a fresh quote of
a garbled fax line ("Effective: T6022 1201AM i | 88hitieveiiaedd tame") was
stacked over a clean paragraph a PREVIOUS run had found the fake standing in,
in whatever document happened to carry it — the "unrelated sentence" the
`within` restriction exists to prevent, arriving one level further out, and
indistinguishable to a reader from the two halves really being one passage.
The choice is now made ONCE, on the ORIGINAL half — the half every other cell
describes: this run's quote brings this run's export half and this run's
location, INCLUDING their absence, and a value this run could not re-derive at
all carries all three forward together. Never a mixture. Pinned on the SOURCE
as well as the output (`test_key_context_one_passage.py`), because the failure
was three fallbacks able to disagree and a fourth would be added the same way.
Costs ~0.24 s per file on a 130-page filing with ~470 records — and
would have cost ~39 s before `_pn_context` was split (see the performance
notes).

`_pn_supplement_key_terms` is the fallback for what the key still cannot carry:
a key written by an older version, or a template AMENDED between runs (a Doe
defendant named). It re-reads `Order*.xlsx` (`_pn_find_party_template`, folder
then Downloads) and adds only what the key lacks, drawing through the same
memo-seeded registry so it can only ADD a fake, never move one. It runs BEFORE
`_pn_retire_kept_key_terms` so an operator `no` still wins — a kept value must
not come back to life just because it is also a template row.

**Correcting the key in place / durable KEEP store.** The `Replacement` column
of `pseudonym_key.xlsx` accepts the same operator control words the LEAKS `Fix?`
column does — `no` (keep this Real Value verbatim), `never` (the nuclear keep of
the WHOLE value), a `[bracketed]` keep-spec
(keep the bracketed part, auto-fake the rest), a `{braced}` one (same cut,
stronger promise) and `*ANOTHER REAL VALUE` (this value is a MISSPELLING of that
one — see below) — so a mistake baked into the key
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
- **`keep_nuclear`** (a `{braced}` part, or the whole value via `never`) — "this
  can never reveal anything": never faked in ANY folder, not even inside a party
  name. See below.

A keep normally loses to a **full party match** — a kept word inside a
`_PN_PARTY_OVERRIDE_CATS` (person/entity/case_number) term is released so the real
party is faked ("CAL EQUIPMENT FE RANCH, LLC" faked whole, "John Doe" faked).
Two exceptions, both LOCAL — a decision typed in THIS folder is an instruction
about this case's parties, not another folder's lesson about a word.
`keep_strict_local`, a bracket typed here: see the keep-spec rule below — the
bracket already says how to split the name and its remainder is a term, so
honouring it still scrubs the party. And `keep_soft_local`, a `no` typed here,
which is released only by a party match reaching BEYOND the kept text (the
`party_wider_only` rule `never` already uses). Bare `*-token`/short-name terms
and detectors do NOT release a keep.
**A local `no` needed that because RETIRING the key row is not enough.**
`_pn_retire_kept_key_terms` drops the key's own binding, and the folder PRE-SCAN
then re-reads the same name out of the PDF as a fresh party term — so the
override released the keep and the value was faked again by the leftover token
rows ("Marcus Delacroix" back as "Rathmore Symington", composed from `Marcus`
and `Delacroix`), while the log said the `no` "will be honored". `wider_only` is
what keeps that safe: a one-word `no` cannot leave a longer party standing,
because "Court Reporter Services, LLC" reaches past a `no` on "Court" and is
still scrubbed whole. An INHERITED `no` is unchanged and still loses.
**…and `scrub_welded` was the pass actually undoing it.** Every other write path
is handed `_keep_spans` (`apply`, `apply_lines`, `scrub_survivors`); the reduced
cure alone was not, so a keep held through the substitution and was put back
afterwards by a pass that reads the ALPHANUMERIC REDUCTION and therefore never
sees the word boundaries the keep was matched on. Fixed with its detection
mirror `surviving_reals_reduced`, which had the identical gap and had to move
with it — a value one reports and the other refuses to touch quarantines an
export nothing can clean.

**The NUCLEAR keep is enforced where it cannot cost anything: at COMPOSITION
time.** `{Law}` must survive inside "Alder Law, P.C." — but protecting the span
outright would drop the party candidate that overlaps it and leave the firm
standing in full, the exact failure the party override exists to prevent. So a
brace does not fight the override; it removes the need for one.
`_pn_nuclear_words` puts a ONE-word brace on `registry.keep_words`, and
`registry.keeps_word` is what `_pn_fake_person` / `_pn_fake_entity_parts` /
`_pn_person_token_map` consult — the same hook `_PN_FIRM_WORDS` uses, which a
brace only ever ADDS to.
**A MULTI-word brace is a PHRASE, and a phrase is a verbatim quote of what it
contains** (`_pn_nuclear_split`, `registry.keep_phrases`,
`registry.kept_positions`). It shipped the other way — every word of a brace
went on the keep list, "since composition is per word" — so `{United States}`
on the master sheet kept "States" verbatim inside "Midland States Bank" (a
delivered export reads "THORNFIELD STATES BANK", half-scrubbed by a keep
nobody typed) and would have kept a bare "States" standing anywhere. Now the
phrase is protected as a SPAN (`keep_nuclear`, unchanged) and left verbatim
by the composing fakers only where the phrase itself stands inside a party
name (`kept_positions`, consulted beside `keeps_word` in all three composers,
in `_pn_restore_furniture`, in `name_fake_words` and in `_all_words_kept`);
its words are ordinary words everywhere else, so "Center" in "Center Street
Holdings" is faked with its party while "Medical Center" survives inside
"Mulliken Medical Center". `never` on a multi-word value is the same phrase
keep. `_pn_load_key`'s pre-scan splits the same way. The party's fake is therefore composed with the word
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
**`never` is that same nuclear keep over the WHOLE value** (`_PN_NEVER_CONTROL` /
`_pn_is_never_cell`), which is what the operator means most of the time and what
braces make tedious — re-typing a long value inside them is also a chance to
mistype it, and a brace whose text is not part of its value keeps nothing and
falls through as a literal replacement. It is normalised at the two places a
control word is read (`_pn_parse_decision_rows`, `_pn_load_key` — plus that
function's pre-scan, so the words land on the registry before any row is
processed) into the decision `{whole value}` already produced, so nothing
downstream distinguishes them; braces keep their job of nuking only PART of a
value, and still work on a single word. The word is stored back VERBATIM rather
than expanded into a brace spec, so the master sheet keeps saying what was typed.
**And the party override yields to a keep that COVERS the party match.** The
override's justification — it costs a nuclear keep nothing, because composition
keeps the word — holds only while some word of the party is still left to fake:
`_pn_fake_person` / `_pn_fake_entity_parts` DROP the keep rather than return the
name itself ("The Law Firm" must not map onto itself). So a whole-value nuclear
keep on a party was released and then faked whole, and `never` meant its opposite
for the values it is most often typed against. `_keep_spans` passes
`party_wider_only` for the nuclear tier: a party match lying entirely inside the
kept span releases nothing, one that reaches beyond it still does (`never` on
"Doe" keeps the word and still fakes "John Doe" as "Yorke Doe"). Nothing is left
in the clear that the operator did not name.

**A MISSPELLING of another value is named with `*`, and gets a misspelling of
that value's FAKE** (`_pn_alias_target`, `_pn_apply_aliases`,
`_PnFakeRegistry.fold_onto`). A filing that spells one party two ways —
"ANTIONO" beside "ANTIONIO" — hands the tool two Real Values, and two unrelated
pool words came back: one person under two names, which a drafting pass reads as
two people and a reader cannot reconcile. The typo fold exists for exactly this
and cannot always reach it: it fires only where the two values are near enough
(`_pn_name_fold_dist`) AND meet in the same draw, so a spelling a REUSED KEY
already pinned, or one two edits away at a length that allows one, is past it.
No heuristic closes that — the operator is the one who knows the two are the
same person — so they say so, by typing `*ANTIONIO` over the fake in the key's
Replacement column or into the LEAKS `Fix?` cell.
**Not the SAME fake, which is the whole difficulty.** Two Real Values sharing
one Replacement is precisely what `DeAnonymize.bas` calls ambiguous: it retires
the mapping and the pseudonym is left standing in the tentative — the failure
the alt-spelling rule above exists to prevent. So the alias derives a stand-in
that is the same SLIP of the canonical's stand-in ("Barlowe" -> "Barlowwe"),
which reads as one person spelled two ways and still reverses one-to-one. The
derivation is `fold_onto`, factored out of `_PnFakeRegistry.token` so the fold
the tool INFERS and the one the operator DECLARES cannot come out differently
(`_pn_mirror_op` names the slip; `_PN_FOLD_MAX_REPS` refuses a pair too far
apart to be a misspelling at all, which also bounds the branching).
WORD for word, because composition is: the words two spellings SHARE are
already one binding and are left exactly alone, so "ANTIONO SARKISYAN" keeps the
surname stand-in every other document used and costs one pool word, not two.
Every loaded key term built from a word the alias MOVES is dropped and rebuilt —
without that, an alias typed on the `*-token` row would correct the token and
leave the composed full-name row still applying its stored fake, which is the
half-applied fix that makes one party read as two, i.e. the very thing being
repaired. An alias that cannot be honoured (the canonical is not bound in this
case, the two are too far apart, every mirrored form is taken) still FAKES the
value, by an ordinary draw, and says so: the row is usually answering a LEAK,
and refusing it quietly would leave the real name standing in the export.
**A STAR and not an EQUALS SIGN, because the marker has to survive the cell it
is typed into.** This shipped as `=ANTIONIO` for one release, and `=` opens a
FORMULA to Excel: the cell turned to `#NAME?` the instant the operator finished
typing — a worksheet that reads as broken while it is still being filled in —
and a MULTI-WORD canonical had to be quoted (`="ANTIONIO SARKISYAN"`), because
Excel rejects the bare form as malformed. Reading it back at all meant going
for the FORMULA behind the cached error (`_pn_xl_typed_text`), since an
ordinary `data_only` read hands back `#NAME?`, or nothing at all in a workbook
Excel never recalculated. A star is ordinary text in every reader: the cell
says what was typed, there is no error to explain, and a multi-word value needs
no quoting. `=` is still ACCEPTED (`_PN_ALIAS_MARKS`) and advertised nowhere —
a workbook already carrying one must keep meaning what it said instead of
falling through as an undecided row — and that is now the only thing the
formula reader is for. It stays cheap and stays safe for the same reason it was
safe before: neither the key nor `LEAKS.xlsx` is ever WRITTEN with a formula in
it (`_pn_xl_plain_cells` sees to that, for its own reasons), so a formula cell
in either is always something a person typed. `_PN_XL_ERROR_VALUES` is the
belt, and outlives the syntax that needed it: a cell reading `#NAME?` is
refused as a typed replacement at BOTH readers, because writing Excel's error
text into an export as somebody's name is the one outcome worse than not
reading the alias.
**A worksheet row that is a MISSPELLING of a tracked value arrives ANSWERED**
(`Pseudonymizer.alias_suggestion`, `suggest_for` in `_pn_write_leak_report`,
`_PN_PREFILL_NOTE`). The fuzzy sweep already knows which tracked token a
survivor is a slip of, and the `*CANONICAL` control word is exactly the
answer, so an UNDECIDED row's Fix? cell is written holding it — at the
owner's direction: leave it if it is right, change it if not. The next reader
takes the cell as an ordinary alias decision, which is the point, and it is
also the cost: a pre-filled cell nobody opens is applied on the next pass
exactly as if it had been typed, and `_pn_triage_pending` reads such a row as
decided. The reach is the fuzzy sweep's OWN on a clean page
(`_pn_scan_fold_dist`, the minting fold plus one), and a word is read the way
that sweep's debris tier reads it — digits back to letters, marks dropped
(`_PN_DIGIT_LETTERS`) — so "va2que1", "Vazqu~z" and "vauiuez" all resolve to
Vazquez; the clipped-lead shape `half_scrubbed_scan` reads ("avid" for David)
is admitted too. It first shipped at the MINTING fold alone, and the worksheet
the operator then filled by hand aliased twenty spellings of one defendant's
name — "Vaiquel", "Vatquel", "Vazqoe", "vauiuez" among them — every one of
which that rule left empty and the sweep had already named: the row exists
because the sweep called the word a misspelling of a specific token, and the
cell only says which.
**And the pre-filled rows are GROUPED, on the canonical they name**
(`_pn_leak_alias_canon`, the sort in `_pn_write_leak_report`). Twenty scanned
spellings of one defendant are twenty rows that are right together or wrong
together — that is the whole of what makes a pre-filled cell reviewable — and
sorted by file and value they were scattered down an alphabet, each asking its
question alone. Clustered, the family is read, accepted or cleared in one pass.
The cluster sorts where its strongest member would have sorted, so nothing is
pulled forward or buried by being grouped, and the ATTENTION tier still leads:
an undecided row never sinks to sit beside a resolved sibling. The cell is read
through the same two readers every other consumer uses and in the same order —
the composed `*David {said}` form asked about first, or the keep-spec's braces
are taken as part of the canonical's own name. A cell it cannot read groups
under its own value, since this only ORDERS rows. The degraded-region bump the sweep also spends is not
taken for a HARVESTED name, the worksheet being written without the page in
hand — but a NAMED PARTY's token (`_party_token_bases`: the template's and
`--term`'s own words) takes it on EVERY page, in the sweep and the pre-fill
alike (`_pn_scan_fold_dist(party=True)`), and a clipped lead carrying one slip
("zquei") is admitted for it too: the net is cast wide for the parties the
operator named, at the owner's direction. Two more things make that net
reach. A party's token is found through a shared TWO-letter window
(`_pn_bigrams`) and not only the trigram index — three slips inside a
seven-letter surname can leave no trigram standing ("Vatqual" shares none
with "vazquez"), and a reach is worth nothing to a comparison never made. And
an UNUSUAL combination of letters shared with the party's token is what
licenses that reach on a token SHORTER than the degraded floor — down to
`_PN_SCAN_PARTY_MIN` six letters (`_pn_shares_rare_bigram`,
`_PN_RARE_LETTERS` q/x/z/j): "Vazquez" carries "zq", twenty scanned spellings
of it carry "zq" or "qu", and almost nothing else in an English filing does —
a letter that rare is a fingerprint, which is the owner's own observation.
Measured without that gate, a six-letter given name at three edits reached
"handle", "Model" and "Carmel" for Manuel in 224 KB of one batch, each of
them a pre-fill that would have merged an ordinary word into the defendant.
The pre-fill also refuses a word the lists call vocabulary or that the
ORIGINAL writes in lower case anywhere (`_orig_lower_words` — "Status" one
slip from a party token "States"), the corpus being the screen of last
resort for the reason `prune_prose_word_terms` states. What that costs, stated: a
DIFFERENT person two letters from a party's given name ("Samuel" beside a
defendant Manuel) arrives pre-filled as that party's misspelling, and the
cell has to be cleared — the Notes column says it was pre-filled, and the row
sorts with the undecided ones. Every word must
resolve, to a word already tracked or to a slip of exactly ONE tracked token
(two equally near is ambiguity, and ambiguity gets an empty cell); the
canonical word must be BOUND, or `_pn_apply_aliases` would have nothing to
mirror; a DERIVED spelling (`_pn_name_variants`' own near-misses, which sit
exactly as close as the real word) is never a candidate; and a value that IS a
tracked real, or a LEAK row, or a row carrying any decision already, gets
nothing. A BROKEN spelling ("M idland", "VA ZQUEZ") gets nothing either — its
lead piece resolves to no token, and the alias machinery pairs word for word.
The Notes cell says the cell was pre-filled and of what, so the tool's guess
is never mistaken for an answer the operator typed, and the row keeps `fix`
empty so it still sorts to the top as one to look at.
**…and the `*` BINDS its canonical when this case has not**
(`_pn_alias_bind_canonical`). The shape: the only spelling of a party ANY
document in the folder carries is a misspelling. "Vazqez" is flagged, the
operator answers `*Vazquez`, the correct spelling appears nowhere — so there
was nothing to mirror, the alias was refused, and the value took an unrelated
pool word. One party under a stand-in that says nothing about the name it
replaced, and the next document to spell it RIGHT draws a second unrelated
word. Binding it costs one pool word and lands where a declared-but-absent
value already belongs: `write_key` gives a binding no export carried Status
`no match` and puts it on `_PN_KEY_PINNED_SHEET`, which `DeAnonymize` cannot
reach — FORWARD-only, which is all this needs, while `_pn_load_key` reads both
sheets so the pin waits for the run where a document finally spells the name
out. The misspelling itself, which the export really does carry, stays on the
main sheet and reverses as always.
What is GIVEN UP is the refusal, which was the only screen on what was typed
after the star; three things hold it. The pair must be near enough to BE one
misspelling — `fold_onto`'s own `_PN_FOLD_MAX_REPS` is a LENGTH-DELTA bound
and not a distance one, so it happily mirrors "ANTIONO" onto a canonical
"NOBODY", which is fine when the operator names a value this case already
holds and not fine when it INVENTS one; the reach is `_pn_scan_fold_dist`, the
REPORT tier's own calibration ("near enough to ask about"), deliberately
TIGHTER than the alias itself, because folding onto a value the folder really
contains is the operator settling which of two spellings is the person while
this invents a third string on their say-so. The canonical clears the same
shape screens a `--term` clears (`_pn_is_name_token` — asked of the word AS
TYPED, since its first question is whether it is capitalised where it was
written and a folded base answers False for every name there is —
`_pn_is_never_fake`, and never one of this run's OWN stand-ins, the
`_pn_build_terms` gate, which matters more here than anywhere because this
value reaches the term list without being read off any document). And the
binding is ANNOUNCED by name at INFO, so a mistyped canonical stays visible as
a line to read rather than a refusal to act on. `--fix-leaks`' refusal of a
value already bound (`allow_rebind=False`) is asked BEFORE the canonical is
bound, or that pass spent a pool word and announced a binding for an alias it
then declined. **The value after the star is the CORRECT spelling and is
treated as one**, at the owner's direction: it holds the clean pool word and
the misspelling holds the slip. Where the MISSPELLING was bound first — it
came off the template or a document, and the operator then starred a spelling
no document carries — an ordinary draw for the canonical folded it onto the
misspelling's fake (`token`'s near-variant fold), so the correct spelling took
the typo'd stand-in and the typo the clean one, and in the key the typo led
the pair. The pool word is handed over instead and the misspelling re-drawn
as a slip of it; only a CLEAN pool word moves, since a fake the misspelling
itself folded onto says nothing about which spelling is right. The stand-in is read back out
of the registry MEMO rather than taken from the draw's return, so it carries
exactly the normalisation and canonical case it would have had if a document
had spelled the name out. The newly-bound value is handed back in
`_pn_apply_aliases`' `values` beside the aliased one, or no term is built, no
record exists, `write_key` writes no row and the binding is gone by the next
run — which is the whole point of it. Residual, and stated: a badly scanned
spelling several slips out ("Vatqual" for Vazquez) is past the reach, so
binding the correct spelling first — `--term`, the party template, or a key
row — is what reaches it, and the alias is then unrestricted as before.

**A `*` and a `{brace}` COMPOSE in one cell** (`_pn_cell_is_alias_keep`,
`_pn_alias_keep_spec`, `_pn_keep_spec_strip`). `*David {said}` on the value
"avidsaid" — a clipped OCR lead welded to the next word, "David said" with the
D lost and the space gone. The two controls answer different halves of one
finding and neither alone is enough: `{said}` keeps the word and leaves the
remainder "avid" to an ordinary pool draw, because the typo fold cannot reach
it (`avid` is four letters, `_PN_NAME_FOLD_MIN` is 5 — the exact gap the alias
exists to close), so the party returns under a second unrelated stand-in and
reads as two people; `*David` folds correctly and swallows "said" into the
surname. They never met because both readers are if/elif chains testing the
alias FIRST, and `{}` is not one of `_PN_ALIAS_FORMULA_CHARS`: the whole cell
was taken as the canonical, so the tool hunted a Real Value named
`David {said}`, found none, WARNED, and faked the value the ordinary way —
loudly wrong rather than silently, but wrong. The keep-spec is read FIRST,
which is also the order the two operate in: the spec CUTS the value and the
alias derives the stand-in for what the cut leaves, so `fake_values` carries
the fragments exactly as a plain spec does (every keep, weld-follow and
master-sheet path unchanged) and `alias` only says how they are faked.
`_pn_apply_aliases` therefore mirrors the FRAGMENT and never the whole value —
the kept text is the document's own word and is part of nobody's name.
Routed on what was TYPED and not on whether the spec fits, so the three
outcomes a spec always has still hold: a spec covering the whole value is a
KEEP (the alias has nothing to mirror, and letting the plain alias branch take
it would fake a value the operator had just kept entire), one naming text
outside the value is the warned literal replacement, and anything without both
controls falls to the single-control branches untouched. Read identically by
`_pn_parse_decision_rows` and `_pn_load_key`, for the reason both ends must
always ask one question one way. The weld-follow is registered on both callers'
alias paths too, since the fragment butts against the kept text in the export
however its fake was derived; the export reads `egecombesaid`, welded as the
document welded it and reversible word for word.

**`--fix-leaks` applies a WORKSHEET alias and refuses a KEY one.** A worksheet
row names a LEAK — unscrubbed text still standing in the export — so faking it
is exactly what that pass is for. A key row names a binding the exports ALREADY
carry, and that pass never reopens the PDFs: moving it would leave the previous
stand-in in a deliverable with no row to reverse it (worse than a leak, per
`unreversible_fakes`) and would not reach the export anyway, since the real
value it renames is no longer in that text. So the pass changes NOTHING — key,
worksheet, quarantine and launcher all stand — and points at the full re-run,
which rebuilds the exports from the PDFs. Inside the worksheet pass the same
rule holds one notch down (`allow_rebind=False`): an alias may give a value its
FIRST fake and never move one it already has. An alias is not a KEEP
(`_pn_decision_is_keep` is false of it), so it never reaches the cross-folder
master sheet — it is a statement about two spellings in THIS case, and the fakes
it mirrors are this case's.

**The KEEP store is a SINGLE cross-folder sheet**, the `KEEP` tab of the master
workbook (`_pn_master_path`, next to the config or `PDF_LINKER_MASTER` /
`master_leaks_path`; a sibling of the `Master Leaks` tally tab — both preserved
by the multi-sheet-safe `_pn_master_load`/`_replace_sheet`/`_save` helpers). Every
run in every folder reads it (`_pn_read_master_keep`) and applies it, and records
its own local keeps back (`_pn_update_master_keep`, accumulating Times Seen /
Cases / dates) so the screening can learn from real history. This — NOT the
per-folder `LEAKS.xlsx` — is the preservation vehicle: the transient LEAKS triage
can be auto-deleted freely without ever dropping a keep.
**…and a case folder is named on BOTH sheets by a PSEUDONYM, never by its own
name** (`_pn_case_label`, `_pn_case_id`, `_pn_case_origin`). This workbook is
permanent, lives OUTSIDE every case folder — next to the config, routinely on a
synced drive — and is never pruned, so the real folder name in `Cases` and
`Origin` made the one file whose purpose is cross-matter history into a standing
list of every matter's parties: the exact thing the rest of the pipeline exists
to keep out of anything that outlives a folder. The name written is this case's
OWN stand-ins where the run can prove that is safe (`Rasho v Quillmark - MTC` ->
`Strangeways v Melbury - MTC`, drawn through the bindings already in the key, so
the row is traceable through `pseudonym_key.xlsx` exactly as an export is) —
minting nothing and counting nothing, since a folder name is not a document and
`rec["count"]` is what `write_key` reports. Where it cannot be proved, the WHOLE
name gives way to an opaque per-folder id (`Case 3f9c1a7e`, sha256 of the
normalised name): never half of each, because a name that is partly real is the
failure being replaced. Three things force the id. NOTHING was replaced — an
untouched name is not evidence of a safe one, the guard `_real_remainder`
already states, merely one this case's bindings had nothing to say about. A
TRACKED value survived the substitution. Or a LEFTOVER word could still be a
name (`_pn_case_name_leftover`) — the screen that matters, because
`surviving_reals` answers the narrower question and a party the folder names
that no template, term or pre-scan ever bound is invisible to it, as it is
everywhere else in the tool. That screen is deliberately STRICT, which it can
afford to be because the fallback is cheap: losing a readable label costs one
folder's rows their readability, where the scrub's own refusals cost a leak or a
renamed authority. A word left standing must be one of this run's own fakes, not
name-shaped at all (a case number, a date, "v"), or short enough
(`_PN_CASE_WORD_MAX`) that the docket shorthand folders are really named with —
"MTC", "MSJ", "Dept" — is not all forced to the id; ordinary docket vocabulary
that is longer ("Ex Parte") IS forced to it, and that is the trade. Residual,
and stated: an unbound surname of four characters or fewer ("Wu", "Doe") still
passes. The reverse map is kept where it is safe — `pdf_linker.log` stays with
the case, and each run writes one line naming what the workbook calls this
folder. An existing workbook HEALS: `_pn_case_aliases` / `_pn_case_migrate`
rewrite every form of this folder (its real name, the opaque id, an earlier
label) into today's on the next run in it, on every row and not only the rows
that run touched, so the real names it was written with go rather than
accumulating beside the pseudonyms — while another matter's `Origin` is never
restated as ours, since rewriting it would hand this folder that matter's keeps.
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
authors it. Both columns name a folder by its PSEUDONYM (below), so ownership is
settled on the ID that rides in the `Origin` cell rather than on the readable
half — `_pn_decision_is_ours` runs before any key is loaded or term built, at
both its call sites, so there is nothing there to re-derive a label from. Inheriting the faking half is cross-case inference — the
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

- **Fake pools** (`_PN_NAME_WORDS` 695 surnames, `_PN_ENTITY_WORDS` 108,
  `_PN_STREET_NAMES` 55, `_PN_EMAIL_DOMAINS` 32): drawn
  without replacement per case, so they must stay ahead of a real filing's
  distinct name tokens (parties + counsel + staff + every declarant + e-mail
  display name) or the registry mints ugly numbered stand-ins ("Corwin Vance3",
  and in body text "HENDRY2 CORPORATIOLORNE10"). Keep the four pools
  (name/entity/city/street) disjoint (`TestPoolsAreDisjoint`) and every added
  surname a valid `_pn_is_name_token`.
  **Size them by MEASURING a delivered key, not by guessing.** The largest
  folder seen needed **305 distinct name draws** — and 94 of its 1,042 rows were
  e-mail DISPLAY NAMES, which is the quiet bulk nobody predicts — against a pool
  of 192, so it recycled 684 tokens deep enough to reach "Deverell5". The same
  key spent 19 of 20 STREET names and drove four e-mail domains to
  "letterbox17", while the ENTITY pool used 11 of 108: the pools do not run out
  together, and only the one that ran out needs growing. A test that hard-codes
  a pool word (an expected fake) breaks on every resize — read the fake back
  from the run instead.
  **A pool word must never be a near-twin of another** (OSA distance ≥2 across
  every pool): the typo fold deliberately mints a misspelling of an existing
  fake, so two pool words one edit apart make a real draw indistinguishable from
  a folded one, and `_report_minted_misspellings` promises that a misspelling it
  names is ours. Enforced by `test_no_new_near_twin_pool_words`, which carries
  the **21 pairs that predate the rule** (Radley/Ridley, Gable/Sable,
  Waverly/Waverley…) as a named exception list rather than tolerating them
  silently: those words are already in circulation in delivered keys, so
  retiring them is a churn decision and not a bug fix. The assertion's job is
  that the list never grows.
  **Every pair of pools is disjoint**, not just city-vs-the-rest — the original
  three assertions only ever asked about cities, so "Juniper" and "Larkspur" sat
  in the entity AND street pools for as long as both existed: one stand-in that
  is a company in one key row and a street in another. When a word has to move,
  substitute it IN PLACE: `_pn_rng` shuffles INDICES, so a same-length list
  changes only the draws that landed on the slot that changed, and every other
  binding a re-run derives is untouched.
  **The pools are COPIED into `DeAnonymize.bas`** (`PseudonymPool` /
  `EmailDomainPool` in the My-Macros repo), where they drive the residual-fake
  highlighter — the last net before a document is shared. A fake drawn from a
  word that copy lacks is a pseudonym that ships unflagged, so growing a pool
  here is only half the change.
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
- **A printed word can come apart INSIDE itself, and the name is then never
  matched** (`_pn_word_breaks`, `_pn_build_pattern(breakable=True)`). A
  born-digital pleading kerns a capital pair tightly and extraction reads the
  gap as a space, so the page is perfectly normal and the export carries
  `V ADIM SARKISY AN` where the caption says `VADIM SARKISYAN`. A SCAN breaks
  the same word a second way, with a speck instead of a gap: the exhibits of
  that batch carry `SARKISYA.N`, `SA.RKISYAN` and `V.ADIM`. A whole-word term
  matches neither half, so the real party shipped in the captions, the attorney
  line, the proof of service and the service list of four exports — 81
  occurrences — while the SAME key's tokens scrubbed those two surnames 287 and
  234 times everywhere the spelling came out whole. One complaint page carries
  both forms four lines apart (`SHARNBROOK WRIGHTSON` on line 10,
  `RESTARICK MIRZOY ANS` on line 11), which is worse than a plain leak: a
  drafting pass read the two spellings as two different sets of plaintiffs and
  reported a record inconsistency. No OCR setting reaches the kerned half —
  nothing was scanned; it is an EXTRACTION failure, the same class as the
  column splice.
  The reduced weld pass would match both (`SARKISY AN` folds to `sarkisyan`)
  and is right to refuse: `_pn_span_is_unbroken` rejects a match holding a
  printed word boundary, which is what stopped it deleting the text between two
  real words ("Further, a substantial" → "Furtthorpe substantial"). That rule
  stands. The tolerance goes into the TOKEN'S OWN PATTERN instead — one
  alternation branch per position, intact spelling first — so a broken spelling
  is matched by a real TERM, yielding to citation protection and to an operator
  KEEP as a blind reduced substitution cannot, and REPORTED by
  `_surviving_records`, which scans with that same pattern, so detection and
  replacement cannot drift apart. It mints nothing: no pool word, no new term,
  no key row, so a folder already delivered re-runs byte-identically and the
  cost is unmeasurable beside the baseline scrub.
  **A pattern, and NOT a term per spelling** — which is what this first shipped
  as (#208), for one release. A term's real value is decomposed into WORDS by
  passes that have nothing to do with matching, and a phantom space makes half
  a word look like one. `_trusted_party_tokens` — which decides the caption
  exemption, i.e. when a cited authority LOSES its protection, and which short
  cores the blind reduced pass may rewrite — took `sar`, `sark`, `syan`, `yan`,
  `vad` and `dim` as party names off two split spellings. And `_weld_core`
  strips a trailing connector (right for `Schilleci & Tortorici, P.C.`,
  meaningless for half a surname), so "Sarkisy an" reduced to the seven-letter
  prefix `sarkisy`, which that pass hunted unanchored and used to rewrite
  `SARKISYA.N` as `WRIGHTSONA.N`. Both are now closed at their own end as well:
  a PERSON core is never truncated, and a `derived` spelling is never a trusted
  token.
  The corroboration is the CONCATENATION — two printed pieces that join to
  exactly a party's own token — which is why a ONE-letter LEFT half is kept
  (`V adim` is where the breaks actually fell) and why the screen that matters
  is both halves being ordinary vocabulary ("Ashe" would offer "As he",
  "Newman" "New man"). The break is ONE character with a letter hard against it
  on BOTH sides, so a mark followed by a space is never one — that is what
  keeps a sentence end ("Sarkisya. N was never served") and the surname-first
  roster shape ("Sarkisya, N.") out. Where the tail is a single letter the
  space is dropped from the class entirely (`_PN_WORD_BREAK_MARK`): "Debora H"
  is how a filing writes a middle initial, and admitting it would rewrite
  Debora H. Smith as Deborah. Guards: an AUTHORITATIVE `person-token` only
  (`_pn_term_is_breakable`, asked by `_PnTerm` itself so the builder and
  `_pn_load_key` cannot answer it differently), since stacking a guess about
  how a word came apart on a guess about who the party is doubles the ways it
  can be wrong — and an entity's words are ordinary vocabulary, so its halves
  are; and the token at least `_PN_WORD_BREAK_MIN` long. The category is
  cap-only, so a lower-case occurrence is still left alone. Measured false
  positives across 6,353 break branches of 934 name words over 1.5 MB of real
  filings and this repo's own prose: **zero**. Residual, and accepted: a break
  that also SUBSTITUTES a character (`VADlM`, `S,-2.,RKISYAN` off a fax scan)
  is the fuzzy scan's business — reported for review, never repaired, which is
  the trade `fuzzy_survivor_scan` states; and a surname whose true break falls
  between two ordinary words is refused by the screen above.
  **…and an ENTITY comes apart the same way, so the tolerance covers every
  authoritative NAME term** (`_PN_BREAKABLE_CATS`: person and entity, full
  name and bare token — never a short-name, a case number or an address). It
  shipped as `person-token` only, on the ground that a company's words are
  ordinary vocabulary and so its halves are; the generic-halves screen already
  carries that worry, and the exclusion cost a delivered folder its own
  PLAINTIFF: the bank was on the template, the born-digital export carried it
  as `M idland States Bank` on every page (one kerned pair, so the defined
  short form went out as `("M idland")` too), no term could match it, the
  survivor scan — same pattern — saw nothing, and the only thing the run said
  was a half-scrub row for `idland`, which the operator read as the tool
  having cut the first letter off a word. Measured before lifting it: 222
  business-name words, 1,555 break branches, 3 MB of real filings and this
  repo's prose, zero false matches. A multi-word term gets one alternation PER
  WORD (`_pn_build_pattern`), the whitespace between words still matching any
  run and a word's own affixes staying outside the break; the single
  alternation over the whole value it first shipped as escaped the term's
  spaces into literal ones and was only ever asked about a bare token.
  Where the tolerance does not reach — a HARVESTED name is still a guess on a
  guess, and "MANUEL VAZQUEZ, an individual" read off a caption is one — the
  two review tiers that can see a fragment (`half_scrubbed_scan`'s
  clipped-lead shape, `fuzzy_survivor_scan`'s near-miss) now report the
  broken spelling WHOLE (`_pn_broken_lead`: the missing one or two letters
  standing right before the fragment, one break character between, on a word
  boundary of their own), so the row says `M idland` or `VA ZQUEZ` — what
  stands in the export, locatable, the word visible — instead of `idland` or
  `ZQUEZ`. The corroboration window is measured from the lead, or the lead
  letter is the capitalised word it finds.
- **Registry** (`_PnFakeRegistry`): injective, deterministic real→fake fakes,
  seeded on the real value (same input → same fake across runs, no two reals
  collide onto one fake). Draw every fake through it so the used-pool stays
  authoritative and the key round-trips.
- **Terms** come from the spreadsheet key (E-Court `Order*.xlsx`), `--term`, and
  a folder **pre-scan** that harvests names/localities/identifiers. Built in
  `_pn_build_terms` / `_pn_append_name_terms` → person vs entity paths.
- **A BUSINESS NAME is often just a combination of generic words, and a BARE
  TOKEN of one must not rewrite the vocabulary of the case.** "All Premium
  Contractors, Inc.", "Sunlight Financial LLC", "Cross River Bank" — and
  specifically the words their own documents are full of. The FULL name is
  distinctive and is registered as its own term; the bare WORDS are not, and
  matching them case-insensitively replaced `Contractors` **204** times in one
  delivered folder, so "the contractors were unlicensed" came back carrying a
  surname. Three screens, and only the last is a word list. **CASE**
  (`_pn_term_is_cap_only`, every `_PN_TOKEN_CATS` term): a party is capitalised
  wherever it stands, in prose and caption alike, and the ordinary noun is not,
  so a bare token matches "Contractors" and "CONTRACTORS" and leaves
  "contractors" alone. It replaces the old `case_sensitive=True` on a one-word
  business short form, which was the same rule a notch too tight — a caption
  SHOUTS its parties, so the all-caps occurrence a filing opens with matched
  nothing. **THE CORPUS** (`_corpus_prunable`, the single eligibility rule
  `prune_prose_word_terms` and `prune_heading_only_terms` now share): a bare
  BUSINESS token is screened whatever its source, because the operator's
  template names a PARTY and not the party's individual words — but only while
  a LONGER term still covers the party, which is what makes dropping it cost a
  missed bare occurrence rather than a party in the clear. A PERSON's bare token
  is deliberately excluded (`_PN_ENTITY_TOKEN_CATS`): a surname is not a
  borrowed word, and a construction case can have a declarant named Carpenter
  while its prose is full of carpenters — dropping that token would leave
  "Carpenter Decl." standing, which the CASE rule already prevents at no cost.
  **A WORD LIST** (`_PN_TRADE_GENERIC_WORDS`, unioned into
  `_PN_SERVICE_GENERIC_WORDS`): the trade vocabulary a business in that trade
  names itself after — contractor/installation/solar/lender/dealer — withheld
  from ever becoming a bare token, and kept OUT of `_PN_COMMON_WORDS` so a party
  really named Dealer stays reportable. Residual, and accepted at the owner's
  direction: a scan that LOWER-CASES a real surname is no longer caught by its
  bare token. The full name still matches in any casing, and the fuzzy and
  unknown-name review scans still surface it.
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
- **…and a STRUCTURED harvest's corroboration is worth nothing if the run walks
  out of the structure.** `_PN_DECL_NAME_WORD` carried `.` inside its tail
  class, so a whole word could swallow the period that ENDS A SENTENCE and the
  declaration-reference harvester walked backwards out of the cite into the
  sentence before it: "…enforce the Arbitration Provision. Carpenter Decl. ¶ 5"
  was read as a declarant named "Provision. Carpenter". The bare token is
  registered too, so a delivered folder's key shows `Provision` replaced by a
  surname **321** times and `System` **370** — 692 ordinary nouns rewritten as
  people, off a handful of sentences that happened to end in front of a "Decl."
  (The same harvest also caught `River`, `Cross` and `Sunlight`, but those are
  real parties the E-Court template registers independently, to the IDENTICAL
  fakes, so removing the declarant rows costs no scrubbing — checked before the
  change, because a harvest this wrong can still be the only thing covering a
  real name.) The TRIAGE WORKSHEET was the visible symptom two steps
  downstream, and reads as a gazetteer problem. The mechanism is precise: a
  bogus row is a PERSON row, so its fake joins `name_fake_words()` — which
  `half_scrubbed_scan` scopes to people deliberately, because an entity's fake
  word sits beside ordinary capitalised prose all the time. "System" -> Hartwell
  put an entity-shaped stand-in in the person set, so "the solar system" became
  "the solar hartwell" and every capitalised neighbour read as a half-scrubbed
  pair: 33 of that folder's 54 rows were solar-financing vocabulary ("Solar",
  "Energy", "Installation", "Dealer", "Capital", "Funds"), and not one of the 54
  was in any of the four gazetteers. Widening `_PN_COMMON_WORDS` would have
  hidden it and fixed nothing. A period was only ever needed for an INITIAL ("Clark H.
  Cameron", "Teresa C. Alarcón") and a professional suffix has its own group, so
  the name word is now either a single letter with its period or a letters-only
  word, the run stops at a multi-letter word's period, and the cite yields the
  declarant that is actually there ("Carpenter"). Note what a REUSED key does
  with a binding like this: `_pn_load_key` reads every row back as a live term,
  so a folder already carrying one keeps applying it until the operator types
  `never` in its Replacement cell — the in-place key correction is the remedy,
  and it is why the fix alone does not clean a folder already run.
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
- **A CAPTION states its parties with a DESCRIPTOR, and nothing was reading
  it.** "IRANI ROUZBAHNI, an individual; ANAHID CHAHREMANIANS, an individual,".
  Every other anchor in `_PN_LABEL_RES` is a role PREFIX ("Defendant
  Travelers") or a LABEL ("Attn:", "/s/"), and a caption states the role in its
  own COLUMN — so a party named only in a caption reached no pass at all. That
  is how a fee motion shipped another matter's plaintiffs: the exhibits carry
  summonses and complaints from the firm's OTHER cases, whose parties are on
  nobody's template, and the review scans could only flag them REVIEW-tier,
  which does not gate delivery. The descriptor IS the corroboration, which is
  what makes an anchor this short safe: "X, an individual" is a caption saying
  "this is a human party", while prose that carries the words ("each plaintiff
  is an individual") has no capitalised name in front of the comma, and
  `_pn_label_names` still requires two words and rejects a bare party role and
  a protected locality. **A LEADING role word is now TRIMMED rather than
  fatal** — the screen that drops any piece carrying a role token refused
  "Plaintiff HELEN RASHO, an individual", which is the commonest caption form
  in California, so the shape yielded nothing at all. Trimming is for the
  LEADING word only; a role word standing INSIDE a name run is the different
  thing that screen exists to catch.
- **A CREDENTIAL trails a person and nothing else, and nothing read it**
  (`_pn_credential_kind`, `_pn_cred_component_ok`, the last `_PN_LABEL_RES`
  anchor). "Joe Smith, M.D.", "Mary Sue, ED/UCC", "Jane Cole, RN, BSN": a
  medical record, an expert report and a signature line name their people
  this way — no role, no label, no "Declaration of" — and the composing
  faker has always KEPT a degree verbatim (`_PN_SUFFIX_TOKENS`), so the
  shape was understood on the way out and read by nothing on the way in.
  The comma plus the credential is the corroboration, the reason the
  caption's "X, an individual" is safe, and the tail is a LOOKAHEAD so two
  people on one line are both read. Two tiers, by how much the credential
  says. A KNOWN degree or professional suffix corroborates on its own,
  wherever it stands ("M.D., testified that"), and a name of up to four
  words behind it. An UNKNOWN one — the unit codes and specialties no list
  is complete for — is a run of short ALL-CAPS tokens and needs more: a
  compound (slash, hyphen, dots) or a second credential after the next
  comma corroborates itself, while a SINGLE bare token counts only where it
  CLOSES the line, the signature and roster shape and never prose, and the
  name in front of it must be name words throughout and at most three.
  Every component is screened against what else trails a Title-case run
  after a comma: a state code ("Silver Spring, MD" — so a BARE "MD"/"PA" is
  never read as a degree, and only the dotted form is, the residual stated
  in the test), a corporate suffix ("Alder Law, P.C."), "et al.", a role, a
  calendar word, a bare Roman numeral ("Article II, IV") and, for a lone
  token, the caps-written vocabulary of a caption ("AN INDIVIDUAL"). Only
  the NAME is harvested — the credential is left standing, which is what
  the faker does anyway — and an honorific is dropped from the lead, or
  "Dr. Joe Smith" would be a term narrower than the name the document uses.
  Measured over this repo's own prose and tests: zero rows. The declarant
  anchor (`_PN_DECL_NAME`, `_pn_is_personlike_declarant`) now admits every
  suffix `_PN_SUFFIX_TOKENS` knows, where it listed six of them by hand.
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
- **A court form prints its label UNDER the typed name, and a fill-in rule
  prints THROUGH it.** The CIV-100's item-6 mailing declarant — an assistant,
  on no template, anchored by no role, no title and no "I, X, declare" —
  stands above a `(TYPE OR PRINT NAME)` label, and nothing read a TRAILING
  label on the line below, so the name shipped in the clear in three exports
  of one batch. The label is the corroboration (a `_PN_LABEL_RES` anchor:
  leading name run only, one line of signature-scrawl debris stepped over, an
  OCR'd brace tolerated, and an unfilled block yields nothing because form
  furniture fails the two-word screen). The declaration's own anchor has the
  second form of the same problem: the form rules the name slot
  ("I, ____________, the undersigned declare"), so `_PN_DECL_SELF_RE` now
  tolerates the swallowed comma and the "the undersigned" filler — and where
  the TYPED name came out interleaved with the rule ("I, ___ l_ria_Ra_m_o_s
  _____ ~ the undersigned declare": the declarant of a delivered filing, page
  one, in the clear), `form_rule_name_scan` REPORTS the raw entry. Which
  letters are the name and which are the rule is a question only a reader can
  settle, the raw spelling is what is locatable in the export, and a blank
  rule (no letters typed) yields nothing. The `I, … declare` anchor only — a
  fill-in TITLE ("as the __ D_e_a_le_r C_o_m_p_lia_n_ce M_a_n_ag_e_r __") is
  a job, not a name, and a row for it is pure triage cost.
- **A SIGNATURE BLOCK says "Name:", and the scan LOWER-CASES the name beside
  it** (`_PN_SIGBLOCK_NAME_RE`, `_pn_lower_name_site`). One delivered batch
  shipped its own defendant's surname four times across four documents —
  `Name: <fake> vazqvez`, `Prnt Name: <fake> v~zquei`, `Name: <fake> vauiuez`
  in the guaranty signature blocks, and `…, vizquez executed a written Personal
  Guaranty agreement` in a declaration — with EVERY leak scan silent. The given
  name was bound and faked on the same line, so each block shipped as a
  half-scrubbed pair reading like a finished scrub: the worst thing this tool
  can emit, and here it was also the party the case is about.
  One shape underneath all four. Every name tier asks for a CAPITAL first and
  asks about the name second — `_PN_LABEL_NAME` requires each word Title-case,
  `_pn_label_names` asserts it a second time after splitting, the narrative
  tier needs a capitalised run, and `fuzzy_survivor_scan`'s candidate pattern
  is `[A-Z][A-Za-z'’-]+`. A fax generation of a guaranty lower-cases the name
  it mangles, so the capital that every tier treats as the evidence is exactly
  what the page had lost.
  **The label is the evidence, so after it the shape stops being it.** A bare
  `Name:` was refused as "far too broad to anchor on" and what makes it narrow
  is the LINE, not the word: the label must OPEN its line (after at most a
  form's list letter), so `BRANCH NAME:`, `COURT NAME:` and `FIRM NAME:` — the
  furniture the breadth worry is really about — are refused by the word
  standing in front of it. `Print Name:` is the same slot and is admitted with
  the spellings a scan makes of it (`_PN_PRINT_SPELLINGS`; the vowel is the
  first thing a fax loses). The LEAD word still carries the ordinary
  Title-case form — a run needs one anchor of its own, and an unfilled slot
  (`Name: ______`) has none and yields nothing — while the words AFTER it may
  be lower-case or carry a speck of debris (`_PN_OCR_NAME_TAIL`), each still
  opening and closing on an alphanumeric so a fill rule is not a name. This is
  a HARVEST, so the block is SCRUBBED rather than merely reported, and a
  spelling near enough folds onto a misspelling of the party's own stand-in —
  one person to a reader, one row each to the macro. Residual, and stated: no
  bare token falls out of a lower-case real, and that is right rather than a
  gap, since a bare token is cap-only (`_pn_term_is_cap_only`) and a token
  built from a lower-case spelling could never match itself; the mangled
  surname standing ALONE is the report tier's business, below.
  **…and `fuzzy_survivor_scan` admits a LOWER-CASE candidate where the SITE
  corroborates it.** The declaration's prose carries no label, so only the
  fuzzy net could reach it, and it was refusing to look. The capital cannot
  simply be dropped: measured against a deliberately over-large tracked set,
  admitting every lower-case word within the fold distance turns up **38** rows
  on this repo's own notes and **36** on its docstrings, every one of them
  ordinary vocabulary (`squash`~`suasn`, `readers`~`rogders`,
  `merely`~`kelely`) — a worksheet nobody reads. So the capital is replaced,
  not removed, by evidence that says "name" without reference to the word's own
  shape: a name LABEL on the line; one of THIS RUN's own person fakes in the
  same run (the half-scrubbed pair — a stand-in beside a word one slip from the
  real name it replaced is not coincidence); or the SUBJECT position of a
  narrative verb, which needs the clause opening for it or ordinary prose
  qualifies. The verb may sit on the NEXT printed line, since legal prose wraps
  mid-sentence and the export keeps the gutter number, which is how the
  declaration's own occurrence is printed. All three together measured **zero**
  rows on those same 1.6 MB. Asked LAST of the cheap screens and only of a word
  already found to be a near-miss: the widened pattern hands the loop ten times
  the candidates (3,584 -> 37,453 on a 249 KB body), so asking every one would
  spend 0.2 s a file to answer about a few dozen.
  **…and EVERY occurrence of the word must be corroborated, not the one in
  hand.** "giving" is 1.5 from a tracked Irving, and in a brief full of
  stand-ins some occurrence of a common word will stand two words from one
  ("Yardley, giving notice") — so it was reported off that occurrence while
  "the activities giving rise to the action" said what it is. A name is a
  name wherever it stands, so a mangled surname sits at a name site each
  time the page prints it; one uncorroborated occurrence is the document
  writing the word as prose, the `prune_prose_word_terms` doctrine with the
  corpus as the screen of last resort. Asked only of a lower-case word that
  is already a corroborated near-miss, and memoised per word. The stand-in
  site itself is ADJACENCY, not a two-word window: the half-scrubbed pair
  is a given name's stand-in printed hard against the surname ("Name:
  MANUEL vazqvez", an initial allowed between), and the window admitted
  "Yardley, giving notice" (a comma is a list) and "Charleen tomorrow
  moring" (a word between). And a CAPITALISED candidate the document also
  writes lower-case is vocabulary — "Paving" heading a contract's name
  beside "paving around the pool" — the pre-fill's `_orig_lower_words`
  screen, asked of the sweep that puts the row there.
- **An EXHIBIT names its people behind labels the harvester did not know**
  (`_PN_LABEL_RES`, second anchor). The label set was contractor / owner /
  client / tenant / landlord / buyer / seller — a construction case's
  vocabulary — so a medical record's `Patient:`, an insurance form's
  `Insured:` and `Claimant:`, a loan file's `Borrower:` and `Guarantor:`, a
  personnel file's `Employee:`, a witness list's `Witness:` and an invoice's
  `Reserved By :` / `Salesperson :` (the space before the colon is how those
  forms print it) each shipped the name behind it in the clear — not faked,
  not gated, no review row. Every one goes through the screens the anchor
  always had (two words, no role token, no locality, Title case). Two shapes
  needed more. A licensing-board page names the licensee with NO colon ("The
  qualifying individual Farhad Ardeshirpour certified that…"), and the phrase
  is also a heading word, so that anchor is STRICT (`strict` group in
  `_pn_label_names`): every word of the value must be a name word, which
  "Must Be Licensed" is not. And a NUMBERED WITNESS LIST (`WITNESSES:` then
  `1. Rosa Delgado`) carries its corroboration in the heading and its
  structure (`_pn_numbered_list_names`): only consecutive numbered lines
  after the heading are read, the name is cut at the first comma, dash or
  parenthesis, and a blank or unnumbered line ends the list. Measured over
  this repo's CLAUDE.md and the module's docstrings and comments (1.2 MB of
  capitalised technical prose — the corpus every anchor below was measured
  on): zero rows. Residual, and stated: `Dear Brian,` and a one-word
  `Witness: Delgado` are still refused by the two-word screen.
- **A caption ENTITY with no comma before its suffix reached no pass**
  (`_PN_FIRM_BARE_SUFFIX`, `_PN_CAPTION_ENTITY_RE`). "GALPIN MOTORS INC., a
  California corporation; SUNBELT RENTALS LLC, a Delaware limited liability
  company" — the comma was the corroboration `_PN_FIRM_SUFFIX_RE` stood on,
  and a caption routinely omits it. Two anchors close it. A suffix that is
  unambiguous WITHOUT its comma (LLC, LLP, a dotted Inc./Corp./L.P./N.A./
  P.C. — never a bare "Co" or "Inc", for the reason the comma mattered:
  "Denver CO" and "the parties Inc" stay refused) is an anchor on its own.
  And the DESCRIPTOR — the shape `_PN_CASE_PARTY_SITES` already reads as
  evidence that a name is a party of THIS case — is read as a SOURCE of one:
  a two-word-or-longer run, a comma, "a/an", `_PN_DESCRIPTOR_BODY`, and the
  descriptor must CLOSE (a comma, semicolon, full stop, line end, or the
  words a caption continues with), so "Owen Blakely, a company employee" is
  refused. The whole clause is handed to `_pn_append_name_terms`, which
  strips the descriptor and forces the entity path as it does for a template
  cell. A leading CALENDAR word is trimmed like a leading role word ("In
  March Sunbelt Rentals LLC hired her"). The comma-led ROSTER ROW is admitted
  too: `_PN_DOCKET_ROW_RE` demanded a pipe or two spaces, so `OWEN BLAKELY,
  Plaintiff,` failed it; `,[ \t]*` is a separator now, the role still
  closing the line (its own trailing comma allowed), and a cell carrying a
  descriptor between name and role is left to the descriptor anchor.
  Measured: 27 no-comma hits on the corpus, every one a worked LLC/LLP/Inc.
  example of these notes; the descriptor anchor zero.
- **A DATE OF BIRTH is faked in its DAY and MONTH and keeps its YEAR**
  (`_PN_ID_RES["date of birth"]`, `_pn_fake_dob`). `DOB: 03/14/1978`, `Date
  of Birth:`, `born on March 14, 1978`, `(DOB 03/14/1978)` shipped verbatim.
  Label-anchored, never a bare-date rule — a filing is full of dates and
  every one is load-bearing. The year is what a record is read by (a minor,
  an age at death, a limitations period) and identifies nobody; the day and
  month are what a lookup needs. The printed SHAPE is kept — separators,
  zero-padding, a month name in the same style — and every spelling of one
  date draws the SAME day and month (seeded on the canonical date, memoized
  per spelling, the two-spellings-one-docket rule), so the numeric and the
  worded form agree and each keeps its own reversible row. In
  `_PN_REID_CLASSES`, so one left standing is a REID row. An AGE is a
  REVIEW row (`_PN_REVIEW_RES["age"]`: `age 67`, `67-year-old`, `Rosa
  Delgado, 67,` hard against a Title-case run; "Page 12" and "Stage 2" are
  refused by the lookbehind) — a number is not a name and cannot be faked,
  and beside a name and a city it is not nothing.
- **A DRIVER LICENCE carries a letter, and the licence class took digits
  only** (`_PN_ID_RES["driver license"]`, `["license plate"]`). "Driver
  License No.: D1234567" and "CA DL B7654321" matched nothing. The class is
  anchored on the spelled-out label or the bare DL/CDL abbreviation
  (case-SENSITIVE: "dl" is inside ordinary words), steps over a state code,
  captures `[A-Z]?\d{6,8}`, and is listed FIRST so a digits-only licence
  behind a driver's label is claimed here and not by the generic class — one
  value, one category, one fake. A PLATE ("License Plate: 8ABC123") is a DMV
  lookup from an owner and had no class; five to eight capitals and digits
  behind the label. Both in `_PN_ALNUM_IDS` (the letter changes with the
  digits) and `_PN_REID_CLASSES`.
- **A P.O. BOX is an address with no street, and a STREET with no suffix is
  still an address where its tail says so** (`_PN_DETECTORS["pobox"]`,
  `_PN_ADDR_TAIL_CUE_STRICT`). "P.O. Box 1234, Bakersfield, CA 93301"
  shipped whole: the street detector needs a street type. The box NUMBER is
  the identifier (one renter per box at one post office) and the only thing
  faked — drawn through the registry, memoized per spelling and SEEDED on the
  digits so "P.O. Box 1234" and "PO Box 1234" draw one box — with the label
  and the locality kept, the house-number-and-tail rule. "1234 Broadway, Los
  Angeles, CA 90015", "1888 Avenue of the Stars, Suite 1500, …" and "100
  Camino Real, Suite 200, …" reached nothing either: the close-word branch
  admitted eight words. A third branch takes ANY `_PN_ADDR_WORD` run (a
  connector admitted between words for "Avenue of the Stars") where the tail
  cue follows — the suite or floor token, or the City, ST ZIP — less the bare
  `#` (a pinpoint "¶ 12 Smith Decl. #3" is a number, two capitalised words
  and a "#"), and the run must END on a word boundary: with no suffix to
  close on, the engine otherwise split a word to satisfy the City, ST ZIP cue
  and read the docket spelling "25 LAMBOURNE 01234" as street "LAMBO", city
  "UR", state "NE" — measured, and the bound is what made the branch zero
  rows on the corpus. Real/Via/Broadway/Alameda/Camino/Paseo/Calle join the
  close words. The fake takes "Street" as its type for a street that had
  none, which reads as an address; the house number, suite and tail are
  kept exactly as before.
- **A LABELLED IDENTIFIER with no class is a number the run walks past**
  (`_PN_ID_RES`: tax id, routing, claim, policy, bond-with-letters, medical
  record, patient id, employee id, parcel, passport, medicare, instrument,
  charge, commission, loan). `Routing No. 122000247`, `EIN 12-3456789`,
  `Claim No. 22-0004567-01`, `Policy No. HO-1234567-89`, `Bond Number:
  G131215420779` (an all-digit bond number WAS faked; one with letters was
  not), `MRN: 00123456`, `Patient ID 55443322`, `Employee ID: 100234`, `APN
  5555-012-034`, `Passport No. 123456789`, `Medicare No. 1EG4-TE5-MK72`,
  `Instrument No. 2021-0123456`, `EEOC Charge No. 480-2022-01234`, the
  notary's `Commission # 2475537` — each verified as shipping in the clear.
  Every class is label-anchored (an abbreviation that is also a word — EIN,
  TIN, MRN, APN, EEOC — is matched case-sensitively), the alphanumeric ones
  in `_PN_ALNUM_IDS`, all but the routing number in `_PN_REID_CLASSES`, and
  the standing short-number screens hold: `_pn_identifier_values` keeps a
  3-digit value out, and each class carries its own floor. An accidental
  partial is worth stating: a bare 10-digit run is faked by the PHONE
  detector, so a 10-digit loan number came out scrubbed while 8-, 9- and
  11-digit ones did not; the "loan number" class is what makes that
  deliberate, and the phone detector is unchanged. Measured: zero rows on the
  corpus for every class.
- **A payment CARD was HALF-faked** (`_PN_DETECTORS["card"]`, `_pn_luhn_ok`,
  `_fake_card`). "Account No. 4111 1111 1111 1111": the account-id capture
  stopped at the first space and rewrote four digits of sixteen — the
  half-scrub this tool refuses — and "4111-1111-1111-1111" matched nothing.
  The account-id capture now extends over three more four-digit groups so
  the run is ONE value; the card detector reads the 4x4 shape and REFUSES a
  match that fails Luhn (one sixteen-digit run in ten passes by chance, so
  the shape alone is not evidence); and the fake is Luhn-valid in the card's
  own separators, drawn on the digits alone so every spelling of one card
  shares one fake. One value, one record: a Luhn-valid card behind an
  account label takes the card faker in `register_identifiers`, and the
  detector steps aside where that term claimed it. A surviving card is a
  `REID card number` row in `reid_scan`.
- **A TITLE the honorific tier did not know is a name it could not see**
  (`_PN_HONORIFIC_RE`, `_PN_HONORIFICS`). "Detective Ramon Ochoa", "Deputy
  Luis Carbajal", "Nurse Priya Venkataraman" reached no tier; a police
  report and a medical record name their people this way and no other. And
  with the surname bound, "Nurse Marston Goodenough" earned a FALSE
  half-scrub row for "Nurse". The uniformed and clinical titles join the
  alternation (Lt./Capt./Cpl. dotted, Deputy Sheriff / Nurse Practitioner /
  Special Agent as the two-word titles they are), "Deputy" is refused where
  it heads an OFFICE (Clerk, District Attorney, Sheriff's Department), and
  the words join `_PN_HONORIFICS`, so the composing faker keeps them
  verbatim and `_pn_review_is_neutral` reads them as furniture beside a fake.
  Measured: zero new-title rows on the corpus.
- **A notary JURAT names the signer, and the notary's name can wrap**
  (`_PN_LABEL_RES`, the `before me,` and `personally appeared` anchors). The
  name-first "X, Notary Public" anchor read the notary where her name and
  title share a line; a recorded lien's jurat is a narrow box that wraps
  between them, so the "before me," side is anchored too with one newline
  admitted. The SIGNER is the other half: "personally appeared" is written in
  front of a name and nothing else, and a jurat is the one place an exhibit
  names the person who executed it (STRICT, and "and" splits two signers as
  it does two property owners). The commission number is the identifier
  class above.
- **A LETTER names its author under the closing and its addressee after
  "Dear"** (`_PN_LABEL_RES` closings and `Dear` anchors,
  `register_salutation_names`, `_PN_MAIL_HEADER_RE`). "Sincerely," / "Very
  truly yours," / "Respectfully submitted," / "Regards," on its own line,
  then within three blank lines a line that is NOTHING but a two-to-four-word
  name (behind "By:" or "/s/" if the letter has one): the scrawl leaves no
  text, so the typed name under it is the author. STRICT, because a
  pleading's closing is followed by the firm's caps line, which the word
  count refuses or the corporate-suffix anchor already takes, and "Attorneys
  For Plaintiff" must never become a person. `Dear Brian Kowalczyk,` is a
  harvest (the honorific form was the only one read). `Dear Mr. Kowalczyk:`
  is a ONE-word value every harvest rightly refuses, so the surname is bound
  the way a judge's is — faked ONLY behind Mr./Ms./Mrs./Dr./Miss wherever
  that pair stands (`court-title` terms, source `salutation`), the bare
  surname left alone, the draw being the registry's own name token so a
  document that spells the full name out composes onto the same word; the
  binding round-trips through the key. `Re:` / `RE:` / `Subject:` lines join
  the mail-header REVIEW set. Residual: `Dear Brian,` is still nothing.
- **A RELATIONSHIP APPOSITIVE introduces the people around a party, and a
  CAPACITY word names a person by their full name** (`_PN_LABEL_RES`
  relationship anchor; `_pn_unknown_name_findings`). "her mother, Rosa
  Delgado, and her brother, Tomas Delgado,"; "her supervisor, Owen Blakely,
  terminated her"; "by and through her guardian ad litem, Maria Delgado" —
  none carries a role, a label or a title. The POSSESSIVE (his/her/their/my/
  plaintiff's/decedent's) plus the relationship plus TWO commas is the
  corroboration — "her mother Rosa" (no comma) and "the mother, Rosa," (no
  possessive) are refused — and the name must CLOSE at a comma, semicolon,
  full stop or line end, where an appositive ends and a sentence that merely
  mentions a mother does not. `a minor` joins the caption-descriptor anchor.
  Decedent / Deponent / Claimant / Guardian / Conservatee / Ward / Insured /
  Employee join the unknown-name tier's role anchor, held to a TWO-word run:
  a party role prefixes a short form ("Defendant Travelers") while a capacity
  word carries a full name, and one word behind it is the thing it heads
  ("Employee Handbook", "Insured Party"). Measured: zero rows.
- **The OBJECT of a handful of verbs is an INSTITUTION and nothing else**
  (`_PN_OBJECT_POSITION_RE`, the object branch of `narrative_name_scan`).
  "employed by Sunbelt Rentals", "worked at Sunbelt Rentals", "attended
  Crescenta Valley High School", "treated at Providence Holy Cross Medical
  Center" — the subject tier cannot see these because the employer and the
  school never DO anything in the sentence, and they are exactly the
  institutions that re-identify a plaintiff. The verb phrase is lower-case
  (prose, not a heading), the article is stepped over, the run is trimmed
  back to its last name-shaped word unless that word is the kind an
  institution ENDS in (`_PN_INSTITUTION_TAIL`: School, Center, Motors…), and
  the row is refused for a role, a public entity, a locality, a tracked
  party and our own stand-ins. REVIEW only, at the standing of the other
  name-shaped tiers. Measured: one row ("Lexis") on the corpus.
- **The lesser shapes** — an IP ADDRESS (an e-signature audit trail prints
  the signer's; dotted-quad, octets bounded, a "1.2.3.4" section number
  refused) and an INTERNATIONAL phone (`+44 20 7946 0958`; the domestic
  shape is 3-3-4 behind "+1", and a foreign grouping cannot be faked into a
  number of any country) are REVIEW rows in `_PN_REVIEW_RES`; a PARTIAL SSN
  (`XXX-XX-6789`, `SSN ending in 6789`, "the last four digits of her Social
  Security number are") is a `REID partial ssn` row in `reid_scan`, since four
  digits beside a name and a date of birth are a key. Measured: zero rows.
- **A TABLE writes a person SURNAME-FIRST, and one class of surname had no
  coverage there.** The docket-roster rule above — word order costs nothing
  because every token registers — has exactly one exception: a surname that
  is also a GENERIC word ("Bond", "Branch", "Store") is deliberately refused
  a bare token, so "BOND SELBORNE" shipped a customer's real surname beside
  his faked given name in an exhibit's account table while every other row
  came out consistent. `_pn_append_person_terms` now registers the REVERSED
  spelling of a two-word person name as a `derived` term with the
  correspondingly reversed fake, so the two orders read as one person forward
  and reverse word for word through the same token rows. Two-word names only
  — that is the shape a table writes, and permuting a longer name would be
  inventing spellings no document carries. No pool word is drawn (the fake is
  the words already minted), so a delivered folder re-runs byte-identically
  except where the reversed row was the leak being fixed.
  **…and a DERIVED spelling retires with its parent.** A keep (`no`) on the
  parent retired the parent's terms while the reversed spelling survived as a
  live full-party term — it kept faking the kept value, and its words counted
  as "another party still carries the word", so the bare tokens were never
  orphaned either: the keep defeated twice over. `_pn_retire_kept_key_terms`
  now reads kinship off the WORDS (every multi-letter word of a derived real
  inside one kept value's word set — single letters dropped, since an initial
  abbreviates a word the parent spells out), which also retires the
  abbreviated-middle-name and wrap-split variants the same keep always meant
  to cover.
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
  leaves no bare token behind. `register_identifiers` still masks protected
  citation spans for every LABEL-ANCHORED class, so a bar number or a
  production stamp inside a cite is not read as this case's. The DOCKET is the
  one exception, and it now runs the other way — see the next bullet.
- **A party of THIS case is scrubbed even when a cited decision shares it**
  (`_pn_case_party_evidence`, `_PN_CASE_PARTY_SITES`, read by
  `prune_authority_party_terms`). That prune drops a HARVESTED name that is a
  party of an authority the corpus cites — right for Angela White, the
  defendant of *Kremerman v. White*, named throughout a motion DISCUSSING that
  decision — and it dropped General Motors, the defendant of a Song-Beverly
  fee batch, because the fee motion cited *Lukather v. General Motors LLC*
  (2010) 181 Cal.App.4th 1041. The party was on no template, so every
  harvested spelling went, and the name shipped in the caption, the attorney
  line and every billing entry of four exports with NO LEAK reported: a term
  never built is invisible to the survivor scan too. (The short form the
  brief defined, "GM", HAD been bound off the parent before the prune ran, so
  the exports read `counsel to General Motors LLC ("HQ")` — half of one
  party.) What separates the two is POSITION: a filing states its OWN parties
  in the attorney line (`Attorneys for Defendant, X`), the Doe-closed caption
  roster (`X; and DOES 1 through 10`), the caption descriptor (`X, an
  individual` / `X, a Delaware corporation`) and the possessive filing title
  (`X'S OPPOSITION TO…`), and a cited decision's party stands in none of
  them. Deliberately NOT a bare role prefix — "Defendant White" is exactly how
  the discussion of a cited case is written. Asked through the term's own
  pattern of the CITATION-MASKED corpus, so a party of the authority's case
  name can never corroborate itself; decided on the FULL name and inherited by
  every term composed from its words (the comma-less spelling, a bare token),
  since a bare "Motors" is never itself found beside "; and DOES 1". The
  citation keeps its span protection either way — what the spare buys is the
  name faked everywhere ELSE, which is the operator's rule: intact inside the
  appellate case name, scrubbed the rest of the time. Logged by name and
  site. Residual, and stated: a bare "X v. Y" heading with no year or
  reporter beside it is protected only by `_in_authority_context`'s two
  anchors, exactly as it is for a template party that shares a cited name.
- **A company named by ANY comma-led corporate suffix is harvested**
  (`_PN_FIRM_SUFFIX_RE`). `Lenis Industries, Inc.` — the primary debtor a
  guaranty answer named three times, on no template, behind no role word and
  defined by no parenthetical — reached no pass at all: the suffix-anchored
  harvester knew a law firm's suffixes (LLC, LLP, P.C., APC) and nothing
  else, so the commonest corporate suffix there is was not an anchor. Inc.,
  Corp., Ltd., L.P., N.A. and a dotted Co. join it, and a connector inside
  the name is walked over ("Bank of America, N.A.", not "America, N.A."). The
  COMMA is the corroboration that keeps the wider set safe: "Denver, CO" is
  refused because Co needs its period here, "Smith, Jr." is no suffix at all,
  and the harvest still goes through every screen a document guess takes —
  including the authority prune above, so "Ford Motor Co." out of a cite is
  dropped as it always was. A LEADING role word is trimmed rather than fatal
  ("Defendant General Motors, LLC made an oral motion"), the rule
  `_pn_label_names` follows; a role word standing INSIDE the run is still
  refused.
- **A SCHEMELESS domain match is a guess about SHAPE, and inside a degraded
  region the shape evidence is worthless.** The bare-domain branch of the url
  detector is anchored on nothing but "a word that ends in .org", and a fax
  page renders ordinary prose as exactly such words: one delivered export had
  the middle of "covenants" replaced with a fake domain ("cuve!postbay.org
  and agreem~ts") — OUR stand-in written into the document's own sentence,
  the wrongly-rewritten-word failure the whole method refuses.
  `_detector_cands` now takes the degraded-span index from both apply paths
  (the joined page in `apply_lines`, since a single line is far too short for
  the block measure) and drops a schemeless url candidate inside a degraded
  span — no fake, and no record either, because a record would quarantine the
  file via `surviving_reals` over text the tool refuses to touch. Not silent:
  the url/domain REVIEW class reads the same regex over the output, so the
  soup still earns a worksheet row and an operator `yes` can still fake it. A
  match carrying its scheme or a leading "www." states that it is a URL
  rather than merely being shaped like one, and stays faked even there; on a
  clean page nothing changes.
- **A DOCKET NUMBER is faked, citation or not** (`_pn_docket_numbers`,
  `_PN_CITE_EXEMPT_CATS`, `_punch_own_casenos`). A docket identifies a MATTER,
  so every one of them is faked, including inside a protected citation span.
  What makes that coherent rather than a trade is a fact about how authority is
  cited: a PUBLISHED opinion is cited by volume, reporter and page —
  "Kremerman v. White (2021) 71 Cal.App.5th 358" — and carries no docket number
  anywhere in the citation. So faking docket-shaped values cannot touch a
  published cite, which is the only thing that must stay byte-for-byte. Two
  halves. This case's OWN
  number was being swallowed by an over-reaching parse — the citation parser
  walks backwards over a case name, so "Case No. 25STCV37838." on the line
  above a cite lands inside the span, and the number was then neither faked
  (`_substitute` refuses a protected span) nor reported (`surviving_reals`
  masks the same spans): the real docket shipped, silently, which is the worse
  of the two failures the protection trades between. `_punch_own_casenos` cuts
  every tracked `case_number` occurrence OUT of the spans, at the single choke
  point every consumer reads, so replacement and detection cannot answer
  differently — the discipline `_weld_core` exists for. The cut is the number
  and nothing else, so the authority's party names in the same span are as safe
  as they were. And a docket no template names is now HARVESTED by shape from
  the UNMASKED body, registered as a `case_number` (so it rides the same punch)
  and faked through `_pn_fake_caseno`, so it carries the STZV marker a keyed
  one does.
  **An UNPUBLISHED APPELLATE docket goes the same way, and for a sharper
  reason.** A published opinion would be cited by reporter, so an appellate
  docket in a brief belongs to an unpublished one — and in a trial court filing
  that is overwhelmingly THIS case's own prior appeal. That number is a
  re-identification key: the appellate record is public, so anyone holding
  "No. B258976" can look up the real parties, and a remand posture is exactly
  where such a cite appears. Leaving it was the whole scrub undone by one line
  of a procedural history.
  **The cost is real and was accepted with it in view.** An unpublished
  decision cited as persuasive authority has its docket renamed like any other
  ("Krikorian Inv. Servs., Inc. v. Radmanesh, No. BC543295, 2015 WL 12751760"),
  so that cite cannot be looked up from the export. That reverses the older
  rule, which refused to build a term for a docket inside a cite — a rule
  written after exactly that renaming shipped as "No. GEARHART543295", and
  which in exchange left a real docket standing wherever a citation could be
  read around it. The reversal key still carries the binding, so the original
  is recoverable; what is lost is the cite reading correctly in the
  deliverable. Changed at the owner's direction, whose rule is that only
  PUBLISHED authority needs strict protection — and a published cite has no
  docket to protect.
  **Shapes, and only these**, because a list of formats is only as wide as the
  filings it was built from: the statewide modern format ("25STCV37838",
  "23STLC00412"), the older Los Angeles courthouse format held to KNOWN
  prefixes (`_PN_LASC_PREFIXES` — a bare "AB000123" is a Bates stamp far more
  often than a docket, and the production-number path already fakes those in
  their own shape), the federal district format ("2:15-cv-01234"), and the
  California appellate format — ONE district letter and six digits, A-H being
  the six Courts of Appeal (the Fourth sits in three divisions, D/E/G) and S
  the Supreme Court. No other letter is a district, which is what keeps that
  last pattern off an arbitrary "X123456" identifier; it runs LAST so the
  two-letter Los Angeles shape claims "BC543295" first, that value being a
  trial-court number rather than "B" plus six digits. NOT covered: an Orange
  County number ("30-2015-00812345"), a federal APPELLATE docket
  ("No. 22-55555", whose two-digit-dash-five-digit shape is far too generic to
  harvest without rewriting ordinary numbers), and most out-of-state formats.
  A value claimed by this pass is never also claimed by the label-anchored
  one: one value, one category, one fake.
  **A case number does not always arrive GLUED, and both halves of that failed
  at once** (`_pn_docket_codes`, `_pn_docket_seam_re`, `_pn_mask_case_numbers`,
  `_pn_caseno_canon`). Extraction spaces one out ("25 STCP 01234") and a narrow
  caption column wraps between the code and the sequence, so the strict shape
  matched nothing — and a delivered folder came back with the real docket
  standing in the clear AND its letters replaced by a surname
  ("25 LAMBOURNE 01234"), because the code left loose beside the caption is an
  ordinary capitalised word to every name harvest. **The letters of a docket
  are a court's CASE-TYPE CODE**: which courthouse, which kind of proceeding —
  public taxonomy that identifies nobody, so renaming it protects no one and
  costs the reader the form of the document. So the codes are masked out of the
  harvest input at `_pn_learn_from_text`'s single choke point, the same seam
  and the same reasoning as `_pn_mask_toa_entries`: a term never built cannot
  be applied, cannot leave a bare token behind and cannot draw a pool word.
  `register_identifiers` is the one pass handed the unmasked text — reading the
  docket is its job. The mask is looser than the faking pass and can afford to
  be, since a mask only ever REFUSES a name. The FAKING side needs the opposite
  discipline: tolerating whitespace in the shape itself would claim "42 USC
  12345" and "29 CFR 160000", which is renaming authority, so an open seam is
  matched only for a code this folder also writes inside a WELL-FORMED number.
  The corroboration is the document's own, learned corpus-wide before anything
  is harvested (`note_docket_codes`, at the seam `reserve_authority_names`
  uses), because the caption states the number properly and the exhibit page
  whose text layer broke it apart carries only the open spelling. And the two
  spellings are ONE number: `_pn_fake_caseno` SEEDS on the whitespace-stripped
  identity and MEMOIZES on the printed one, so they draw the same digits and
  still get a row each — "25STZV69051" beside "25 STZV 69051", one docket to a
  reader and two distinct bindings to `DeAnonymize.bas`, which retires a fake
  two Real Values both claim. The canonical spelling of a glued number is
  itself, so nothing already delivered moves. Residual, and stated: with no
  well-formed docket anywhere in the folder there is nothing to say those
  letters are a court code, so the open spelling stands — the mask still
  refuses it a name, which costs nothing. The one route the mask cannot reach
  is a code written away from any digits in a slot a name harvest anchors on
  ("Attn: STCP Clerk"); `_is_court_code_term` refuses that on the same
  corroboration, taking the near-spellings `_pn_name_variants` minted with it
  (they carry the refused term's own fake and no code of their own, so screened
  one at a time they outlived their parent). Never applied to the operator's
  party list, a `--term` or a reused key: a party genuinely named for those
  letters is theirs to declare.
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
  stamped page. Two more stamp shapes have since shipped and are closed the
  same way. The stamp is a NARROW BOX, so it wraps between the name's comma
  and the role ("David W. Slayton,\nExecutive Officer/Clerk of Court") and a
  same-line-only pattern never saw the Executive Officer at all — the
  comma-to-role gap now admits one newline, `_PN_LABEL_GAP`'s own bound. And a
  deputy's SURNAME may spell an ordinary word: "By J. So, Deputy Clerk" failed
  the vocabulary gate and shipped on every stamped page of one batch
  ("A. Mowbray" beside it was faked, which is what gave it away), so
  `_clean_tail` admits one Title-case vocabulary word in the SURNAME position
  — the site is structured, bounded by "By" ahead and ", <role>" behind — and
  only into a name that also carries a real anchor (an initial or a
  name-shaped word), so a run-on capture still dies. Two more, from an OCR'd
  conformed-copy stamp. The deputy line can lose its furniture ENTIRELY —
  "By: M. Quintanilla, Deputy Clerk" rendered as "Ay: MN. Quintanilla
  Deputy", the B misread, the comma dropped, the "Clerk" lost — so
  `_PN_COURT_STAFF_BY_RE` reads the SANDWICH that survives the garbling: a
  "By"-shaped lead ([AB]y with its colon) ahead of the name AND "Deputy" hard
  after it, both required, so "approved by the Deputy" in prose never
  qualifies; `_clean_tail` also takes a two-capital initial WITH its period
  ("MN." is OCR's "M.") while a bare two-capital word stays refused, and
  "AM"/"PM" break the walk outright — the stamp's own clock sits exactly
  where the walk-back arrives, and "12:41 PM David W. Slayton" captured "PM"
  into the clerk's name. And OCR clips the LEAD of a word: "avid HUNTINGDON.
  Bancroft" is "David" with its D lost, standing lower-case beside two of
  this run's own stand-ins — invisible to every capitalised tier, an
  ordinary English word besides — so `half_scrubbed_scan` gains the
  truncated-real shape: a lower-case word of four-plus letters that is a
  tracked name token missing its leading one or two characters, with one of
  our person fakes in the same name run (an initial allowed between). The
  double corroboration is what overrides the vocabulary screen; "an avid
  reader" in prose has no fake beside it and stays a word.
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
- **An HONORIFIC is furniture too, and the entity path was asking a NARROWER
  question** (`_PN_HONORIFICS`). "Mr. Kool's Collision, LLC" came out
  "EVERLINE. REDWOOD'S LIGHTWELL, LLC" — a title turned into a name word, with a
  sentence-ending period left in the middle of the party — where "Mr. Redwood's
  Lightwell, LLC" says exactly as much and hides exactly as much. The bare token
  that fell out of it then rewrote `Mr` **42 times** across the batch, so every
  "Mr. Henriquez" in the case became "Everline. Henriquez". The cause is one
  line: `_pn_fake_entity_parts` read `_PN_FIRM_WORDS` DIRECTLY where
  `_pn_fake_person` and `_pn_person_token_map` call `registry.keeps_word` —
  which is `_PN_NAME_FURNITURE`, the wider set — so the two composing paths
  answered "is this furniture?" differently and the gap was every honorific.
  They ask through the one hook now. Note what a delivered key does with a
  binding like this: a loaded row is applied literally, so
  `_pn_restore_furniture` runs over `*-token` rows as well as full names — the
  short form is a phrase whenever the bare form of a name is one ("Mr. Kool's
  Collision"), and repairing only the full name left "Mr. Redwood's Lightwell,
  LLC" in one line beside "Everline. Redwood's Lightwell" in the next, which is
  the two-parties reading the repair exists to prevent. A fake not composed word
  for word is still refused (the delivered key's "MR. KOOL'S COLLISION,LLC" lost
  the space before its suffix, so its four words cannot be matched to the fake's
  three).
- **A NICKNAME is the front of the name it shortens, and its fake is the
  front of that name's fake** (`_PnFakeRegistry._nickname_fake`,
  `nickname_swaps`, `_pn_key_longer_first`). "Ken" and "Kenneth" each drew
  an unrelated pool word — "Windlesham" beside "Cranston" — so one person
  read as two, exactly the confusion the compound-surname and possessive
  rules exist to prevent, arrived at from a third direction. At the owner's
  direction the LONGER takes precedence and the shorter is left nothing of
  its own: "Ken" is "Cranston" with the same four letters dropped, "Cran",
  which reads as the nickname of the fake the way "Ken" reads as the
  nickname of the real. Either may be drawn first. The build pre-binds
  shortest-first, so a nickname on the template is bound before its full
  name and is REBOUND when the full name is drawn (`_draw`, factored out of
  `token` for it); a nickname harvested later takes the front of a fake
  already bound. PERSONS only — "Sun" is not a nickname of "Sunlight" — the
  shorter at least three letters and at least two shorter, the tail the
  full name adds at most six letters and not itself a bound name (or the
  pair is a WELD — "adler" in front of "adlermichael" — which is the weld
  fold's business and reaches it untouched), and a binding a
  reused key pinned never moves, the `_pool` test `avoid()` already uses
  (a loaded or composed fake was not this pool's to give). Reversal is the
  care in it: the short fake is a SUBSTRING of the long one, and a reader of
  the key that searches substrings in row order would turn "Cranston" into
  "Kenston" on meeting the short row first — so `write_key` puts a row
  whose Replacement is the front of another's AFTER it, and every other row
  keeps its place. `DeAnonymize.bas` should reverse longest-first
  regardless.
- **A POSSESSIVE that lost its apostrophe is the same word.** `KOOL'S` and
  `Kool’s` both reduce to the core "kool" (`_pn_word_affixes` strips either
  mark), but an all-caps caption printing `MR. KOOLS COLLISION, LLC` — the
  commonest way one is written — arrives as "kools", keys separately in the
  registry memo, and draws an unrelated pool word. One company came out
  "Redwood's Lightwell" through most of a batch and "Orion Lightwell" wherever
  the apostrophe was missing: two defendants to a reader, off one party. The
  edit-distance fold would catch it on a longer name and cannot here — "kool" is
  under `_PN_NAME_FOLD_MIN`, and lowering that for every token would make short
  names coincide. `_PnFakeRegistry.token` mirrors the real's own deviation
  instead, exactly as the typo fold does: the fake takes the same trailing "s"
  ("Redwood" → "Redwoods"), so the two stay ONE party to a reader and two
  DISTINCT rows to the reversal macro. Forward only — `_pn_build_terms`
  pre-binds shortest-first, so the bare form is always the one already bound —
  and never onto a fake another value already holds.
- **…and the two ends must ask the SAME question of a bare token.**
  `_pn_load_key` screened a loaded `*-token` row on `_pn_is_generic_token`,
  while the BUILDER screens a bare token on `_pn_is_name_token` — a different
  test, which "Roe" (an ordinary word) and "Cruz" (a locality word) pass. So
  the round-trip quietly resurrected what the build had declined: the FIRST run
  left a bare "Roe" standing and the re-run scrubbed it, one folder answering
  one question two ways. `_pn_load_key` now asks the builder's question too,
  whatever the parent's source, so a first run and a re-run scrub alike
  (`test_the_first_run_and_the_rerun_scrub_alike`). The row itself STAYS in the
  key, and `write_key` deliberately does NOT gain the same screen: it is
  load-bearing in the REVERSE direction, because "Doe" is refused a term and is
  still FAKED inside "Jane Doe" -> "Marlow Deverell", which the macro undoes
  word by word off that very row. A GENERIC word is the different case that may
  be dropped from the key outright — the composing faker keeps it verbatim, so
  there is no binding to reverse. Accepted cost, and it is the direction the
  owner chose: a re-run now scrubs a little LESS than it used to, so a folder
  already delivered under the old behaviour can come back with a bare
  common-word surname standing where the previous re-run had faked it.
  **…and a single ENTITY word IS a bare token, on both ends.**
  `_pn_entity_bare` registers the suffix-stripped short form only as a
  MULTI-word phrase ("Midland States" off "Midland States Bank") and skipped a
  single leftover word ("Redwood", "Tutors") to keep unrelated prose intact —
  while `write_key` harvested a row per WORD of the composed name and
  `_pn_load_key` read each back as a live term, so a re-run scrubbed a bare
  "Midland" the first run had left standing. Resolved toward the WIDER
  answer at the owner's direction (over-pseudonymize rather than under):
  `_pn_append_entity_terms` now registers each distinctive word of a party as
  its own `entity-token`, behind the screens every bare business token takes
  — name-shaped and not generic (`_pn_is_name_token`,
  `_pn_is_generic_token`), at least `_PN_HARVEST_TOKEN_MIN` letters, never a
  corporate suffix or a state, never a brace-kept word, cap-only, and
  corpus-prunable (`_corpus_prunable`) — and the loader applies the same
  floor to a one-word row (`test_entity_word_rows.py`). What that leaves is a
  word like "States" faked wherever the corpus never writes it lower-case,
  and the operator's remedy is a PHRASE keep: `{United States}` keeps that
  phrase as a unit and nothing else (below).
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
- **`'` and `’` ARE THE SAME CHARACTER, and the three places that disagreed
  each failed differently.** Everything above is written with the straight
  mark; a filing written in Word carries the typographic one, so the two meet
  in every folder — the E-Court spreadsheet exports `'`, the PDF says `’`.
  (1) `_PN_WORD_RE` kept `'` inside a word and not `’`, so "GREEN’S" read as
  "GREEN" plus a one-letter word "S" — and a single letter is kept verbatim by
  `_pn_fake_person`, which is indistinguishable from a middle INITIAL, so
  `_pn_align_initials` handed the possessive the first letter of the fake the
  middle name got: **"RACHEL GREEN’S" -> "RIDLEY YEARDLEY’H"**. The same split
  made "O’Brien" an initial "O" plus a surname. (2) `_pn_is_name_token` did its
  own strip-and-`removesuffix("'s")` instead of `_pn_word_base`, so "Green's"
  reduced to "green" and was rightly refused a bare token (a common-word
  surname) while "Green’s" reduced to "green’s", matched no list, and became
  one — a token whose FAKE carries a possessive, then applied to every
  near-miss spelling ("Grreen" -> "Yeardley’s"). (3) `_pn_build_pattern`
  matched the mark LITERALLY, so a term never met the other spelling at all:
  "Rachel Green's Trust" left "RACHEL GREEN’S TRUST" standing whole and
  "Sean O'Brien" left "O’Brien" beside a faked given name — neither reported,
  because `_surviving_records` scans with that same pattern, so replacement and
  detection agreed and both were blind. `_NFKC` does not fold them (distinct
  characters, not a compatibility pair), so each site has to: the marks live in
  `_PN_APOS` / `_PN_APOS_CLASS` and a pattern matches either.
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
- **A CASE NUMBER keeps its filing year, fakes its digits, and takes a court
  code no court issues** (`_pn_fake_caseno`, `_pn_caseno_template`,
  `_PN_CASENO_MARK` = "STZV"). The year is printed beside the number in every
  caption ("Complaint Filed: Dec 29, 2025"), so randomising it hides nothing and
  only makes the fake internally impossible. The LETTERS are the other half, and
  faking the digits alone left a perfectly well-formed number: "25STCV37838"
  came back "25STCV51378", a valid Stanley Mosk civil number that may belong to
  somebody's real case — anyone who pastes it into the LASC portal gets a
  record, and every reader has to take on trust that it is not the one in front
  of them. "ZV" is not a case type any California court issues and "STZV" is not
  a prefix any of them uses, so the search comes back empty BY CONSTRUCTION
  rather than by luck, and a fake is recognisable on sight. The whole letter RUN
  goes, not just the case-type half ("24SMCV00456" -> "24STZV70915", not
  "24SMZV70915"): a courthouse code is itself identifying — it says which of
  twelve buildings the matter sits in — and one uniform marker is easier to
  recognise than a family of them. The FIRST run only, since that is where every
  format carries its code ("BC543295" -> "STZV235607", "2:23-cv-01234" ->
  "2:23-stzv-25103", the marker taking the run's own casing). Residual, and
  stated: a number with no letters at all ("543295") has nowhere to carry the
  marker and is faked digit-for-digit exactly as before, so that fake stays as
  searchable as it ever was. The DIGITS are untouched by this — `digits()` takes
  the marked shape as a `template` while the memo key and the seed stay on the
  REAL value, and the template moves no digit position, so the draw order and
  count are what they always were and the change is letters-only
  (`test_the_marker_changes_the_letters_and_nothing_else`). A folder re-run
  WITHOUT its key therefore gets the digits it has always got, now marked; a
  folder WITH its key moves nothing at all, since `_pn_load_key` pins the
  delivered fake in the `caseno` memo.
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
- **A WRAPPED address leaves its bare LOCAL PART standing, and the detector
  needs the "@"** (`scrub_emails`, second sweep). A letterhead block breaks
  after the name half of an address and the domain never reaches the page, so
  one export carried "nminassian" alone on its own line — the attorney's real
  initial-plus-surname, one line under the faked phone numbers, matched by
  nothing. The local part of a TRACKED address is a bound value (the record
  and the key row exist), so per the cured-not-asked rule it is cured with
  the fake's own local part rather than put on the worksheet. OWN-LINE only —
  that is the shape wrapping produces, and a section heading or a word of
  prose is never rewritten by it. The vocabulary screens are the union every
  name tier consults, and because no list is ever complete ("accounting" is
  on none of them) the CORPUS is the screen of last resort, the
  `prune_prose_word_terms` doctrine asked of the one text in hand: a local
  part that also stands mid-line away from any "@" is vocabulary and is left
  alone everywhere. Residual, and stated: a local part standing only
  MID-prose, or split from a domain on the NEXT line, is not cured — the
  first is too ambiguous to rewrite, the second is a different miss (the
  detector's whitespace tolerance is horizontal only).
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
- **The tool NEVER takes its own output as a real value to scrub, and that is
  enforced at ONE gate** (`_pn_build_terms`). A delivered key carried
  `II -> EE` (2,281 occurrences, from an E-Court template that split
  "Gregory Wayne Walton, II" across cells) and, downstream of it,
  `Lowther Rolleston EE -> Winchcombe Penrose VENTRIS` — a Real Value composed
  entirely of this tool's own stand-ins, which `DeAnonymize` can only walk back
  to more of our output. Two refusals sit at the one point every source passes
  through — the party template, `--term`, a worksheet `yes`, a key row read
  back — rather than patched pass by pass:
  `_pn_is_bare_suffix` (a bare Roman numeral or generational suffix is never a
  party however authoritative the source: a brief is full of "II. ARGUMENT" and
  "(ii) the date", and the professional suffixes md/rn/pa/**do** are
  deliberately NOT on the list, because "Do" is a real surname); and a
  whole-value check that the term is not something `registry.minted_fakes()`
  already handed out. ENTIRELY ours, never merely containing one of our words —
  a half-scrubbed pair is `_pn_strip_prior_fakes`'s case, and it fakes the real
  remainder alone. Accepted cost: Roman VI-X shadow a few short given names, so
  a template row of exactly "Vi" is refused; "Vi Nguyen" is not, and a party
  template lists full names.
- **A display name is never MINTED from text this tool already scrubbed.**
  `--fix-leaks` runs its detectors OFF because the exports were scrubbed on the
  full run and a detector meeting a fake would re-fake it; a display-name mint
  is the same hazard and was exempt. "Gregory Walton EE" came out as "Lowther
  Rolleston EE" (its "EE" kept by a master `no`), the next pass read that pair
  as a fresh person and minted "Winchcombe Penrose VENTRIS" over it 60 times,
  and the delivered key carried one of OUR stand-ins in its Real Value column —
  a two-generation chain `DeAnonymize` can never walk back to "Gregory".
  `mint_display_names` is off for that pass. Recognising an ALREADY-KNOWN
  display name is still wanted (it applies a binding that exists); only
  inventing one is not, and a FULL run over source text still mints one.
- **The leak GATE follows a reduction, not only an outright drop.**
  `confirm_findings` reduced that same finding to its real remainder ("EE") for
  the worksheet but left the old phrasing in `leaked` — and "EE" carries a KEEP,
  so it earned no row while "Lowther Rolleston EE" held four exports.
  Quarantined with nothing to answer, and no re-run could converge. The
  remainder is now carried into `leaked`/`leaked_by_file`, so the gate asks
  exactly what the worksheet shows and a suppressed remainder suppresses the
  whole finding — while a remainder that is a real name still gates, under the
  value the operator can see. The reduction is not an amnesty.
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
  **…and the WORD path ran the whole scan battery and NONE of the cures.**
  `_write_text_version` runs `scrub_emails`, `scrub_welded` and
  `scrub_survivors` before it scans; `_write_word_text_version` ran `apply` and
  went straight to `surviving_reals`, which inverts the one rule the two-tier
  design stands on — detection must never out-run replacement. So on a Word
  folder every value the three cures exist for was REPORTED rather than
  repaired: a row in `LEAKS.xlsx` under a value the key shows `replaced`,
  asking "should I fake this?" about a binding that already exists. That is not
  a decision an operator can make — `yes` mints a term for a value that already
  has one and `no` says leave verbatim a value the export is full of the
  stand-in for — and it is the same row the PDF path beside it never writes.
  The reduced tier was missing from BOTH sides there (no `scrub_welded`, no
  `surviving_reals_reduced`), so a lost space was neither cured nor reported;
  `spliced=False`, the narrow hard-seam pass, because a Word document is
  born-digital and has no column splice. Safe to add for the reason the cures
  are safe anywhere: they mint no fake, draw no pool word and add no key row —
  they apply the fake the record already carries — and they return the body
  unchanged when nothing survived, so an ordinary Word export does not move.
  Pinned on the SOURCE of both writers (`test_word_path_cures_survivors.py`),
  because the failure was a pass missing from one of two paths that must agree,
  and a test of either path alone cannot see that.
  **Note what this means for `--fix-leaks` on such a row.** That pass reads
  every key row back as a LIVE TERM and re-applies the whole list to the
  export, so a leak whose value the key already binds is cured there with NO
  worksheet decision at all — verified end to end, identically with the Fix?
  cell empty and with `yes`. Which is why such a row is never PRE-MARKED
  `yes`: where the value is curable the cell changes nothing while marking the
  folder's triage answered (`_pn_triage_pending`, which gates the recycled-name
  re-mint), and where it is NOT curable — the leak stands at a site
  `_substitute` refuses — the fix pass runs that same `_substitute` and refuses
  it again, so a pre-filled `yes` would be a row marked for a fix that can
  never land, re-reported on every pass. The answer to a bound value standing
  in an export is to CURE it in the run, not to answer for the operator.
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
  **It is also written FIRST, because nothing about it has to wait.**
  `build_body(None)` depends on the extraction and on nothing else, while the
  scrub and the leak scans it used to sit behind depend on every term and record
  in the case. Measured on a 130-page filing that is 1 second of work queued
  behind 90 — and on the folder that exposed the `_in_name_run` quadratic, 5
  seconds queued behind 65 MINUTES. The reference copy is what an operator reads
  while the export is still being checked, so the wait was pure cost; moving it
  ahead delays the export by exactly the second it takes to write. Safe because
  `confirm_findings` runs once at the FOLDER level, so nothing it sees changes,
  and `note_original` still happens whether or not `original_text_subfolder`
  asked for a readable copy — the check must not depend on an output preference.
  The one thing it changes: a run that dies mid-scrub now leaves the unscrubbed
  copy in the folder with no export beside it. That file is meant to be there
  when the option is on, and having the reference copy beats having neither.
  Pinned on LOG ORDER (`test_original_text.py`), not on mtimes — a fast machine
  writes both inside one filesystem timestamp tick.
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
  **…but a value that GATES delivery is always answerable.** A `no`/`never`
  keep is in the gate's `suppressed` set, so it blocks nothing and rightly
  keeps no worksheet row. A `[bracketed]` keep-spec is NOT:
  `_pn_decision_is_keep` is true of it, so the worksheet dropped its row, while
  its `fix` is "yes", so it never reaches `suppressed` and the gate still
  quarantines. The operator was left with held exports, no worksheet to answer
  and no Apply-Leak-Fixes launcher (it is written beside the worksheet), while
  the gate's own message pointed at both. A LEAK-type finding now earns its row
  whenever it is not suppressed, and the gate says outright when no worksheet
  was written.
  **A KEPT value is not a leak** — it is present because the operator said so,
  so `surviving_reals` skips it (the REVIEW scans always did). Reporting it put
  a row in `LEAKS.xlsx` that no answer could clear: `no` is what produced it,
  and the durable decision lives on the master KEEP sheet, so consuming the
  local worksheet never retired it either. Scoped to the categories a keep
  survives in — a keep is RELEASED inside a full party match, so a
  `_PN_PARTY_OVERRIDE_CATS` real still standing was faked nowhere and IS a leak.
  **…and the suppression is EXACT-VALUE, so a phrasing the scans invent comes
  back** (`_all_words_kept`, run from `confirm_findings` beside
  `_real_remainder`). The worksheet drops a row whose value carries a KEEP
  decision, but the high-recall scans go on flagging every PHRASE that contains
  the kept word, and each phrasing is a distinct value with no decision of its
  own: `never` on "Labor" leaves "Labor Relations Leader", "Senior Labor
  Counsel" and every other wording to be answered again — questions no answer
  changes, since `yes` would fake a value the operator said never to fake and
  `no` is already what is happening. A finding made of NOTHING BUT nuclear-kept
  words is now dropped. It needs no ORIGINAL to check against — a kept word is
  the operator's own declaration, not an inference — so unlike the evidence
  pass it runs in a folder that kept no unscrubbed copy.
  **Dropped WHOLE, never reduced — the opposite of `_real_remainder`, and the
  reason is which text is the document's.** A stand-in is not in the source at
  all, so cutting it out leaves the part that IS there; a kept word is the
  document's own text, so cutting it out yields a value matching nothing in the
  export — unlocatable, and on an opaque value plainly wrong. A real master
  sheet's nuclear words included "com", "www", "no", "n", "and" and "the",
  harvested from braced URLs and addresses: reducing turned "553.com" into
  "553" and a benefits URL into "//sir.int.benefitcenter./…". So a phrase
  carrying a real name beside a kept word stays exactly as found, and marking
  it `yes` is safe because the composing faker keeps the kept word anyway
  ("Labor Rasho" -> "Labor Yeardley"). NUCLEAR only: a soft `no` keep is
  released inside a name run precisely because the word may be part of a party
  there, so a phrase carrying one can still be a real leak.
  **A REVIEW row never names a value the KEY already binds**
  (`_finding_already_bound`, `bound_reals`, asked from `confirm_findings`). A
  worksheet row is a QUESTION — "is this a name, and should I fake it?" — and
  for a value already in `pseudonym_key.xlsx` the tool has ANSWERED it: the
  fake is minted, the binding is written, and every occurrence the scrub was
  allowed to reach carries the stand-in. The row is unanswerable in both
  directions (`yes` mints a term for a value that already has one, `no` says
  leave verbatim a value the exports are full of the stand-in for), and
  `--fix-leaks` cannot clear it either, because that pass runs the same
  `_substitute` that refused the site to begin with — so it came back on every
  pass, forever.
  What puts one there is the DELIBERATE SILENCE of `_surviving_records`. That
  scan is the MIRROR of `_substitute` — it reports a tracked value only where
  the write side was allowed to replace it — so it says nothing about a real
  standing inside a protected citation, inside an operator KEEP, inside a
  whitelisted verification link, or as the lower-case occurrence of a cap-only
  bare token: four sites the scrub refuses ON PURPOSE. The REVIEW tiers that
  read the output RAW have no such mirror, so each of those sites came back as
  a row. A delivered folder's `State Bar No. 214785`, faked on the attorney
  line and kept byte-for-byte inside `Roe v. Bell (State Bar No. 214785)
  (2019) 33 Cal.App.5th 1`, was reported as `REID bar number` under the very
  value the key shows `replaced`.
  The rule is the two-tier design read back: a bound value really standing
  where the scrub could have reached it is `surviving_reals`' finding, reported
  as a LEAK, which GATES delivery — and a LEAK row is never screened here, or
  the gate would empty (every value it reports is bound by construction). Asked
  WHATEVER the record's count, because zero is not the opposite case: a term
  whose only occurrences were line-wrapped matches nothing and is still a
  binding the key carries. Four scans (`defined_name_scan`,
  `narrative_name_scan`, `honorific_name_scan`, `mail_header_name_scan`)
  already carried this screen by hand, written one at a time as each tier met
  it; six did not (`review_scan`, `review_definition_survivors`,
  `degraded_contact_scan`, `form_rule_name_scan`, `reid_scan`,
  `unknown_name_scan`, `half_scrubbed_scan`). It is asked at the single choke
  point every finding passes through on its way to the worksheet, so the next
  tier cannot be added without it — the four hand-written copies stay as cheap
  early exits and are subsumed. The identity is case- and whitespace-
  insensitive (`_finding_key`), since a run crossing a pleading wrap carries
  the gutter's own spacing. The PER-FILE log still names what each scan saw,
  which is the run narrating its own work; the folder-level line says how many
  findings were dropped for this reason and why, so the difference between the
  log and the worksheet is stated rather than left to be noticed.
  **…and the AUTHORITY half of that mirror was asked about the wrong TEXT**
  (`guard_body`, in `_surviving_records`). That scan mirrors four refusals by
  reading `_substitute`'s own spans, and mirrors `_in_authority_context` by
  asking it the same question — but asked it of its OWN body, the
  citation-MASKED copy, where `_substitute` asks about the unmasked page. The
  mask blanks the NAME RUN of every cite it can see, which is exactly where the
  guard's " v. " anchor lives, so the two sides answered one question about two
  different strings and disagreed BY CONSTRUCTION: the write side saw the
  anchor and refused, the read side saw a blanked span and reported. Measured
  on a reporter-only cite (no parenthetical year, so no bracket for
  `_PN_AUTHORITY_BREAK_RE` to stop on) with this case's own party in the
  sentence behind it, `_in_authority_context` answers True unmasked and False
  masked, the export ships the party in the clear, and `surviving_reals`
  quarantines the file over it — which no `--fix-leaks` pass can clear, since
  every pass runs that same `_substitute`, refuses again and re-reports. The
  READ side is the half that moves: the write side's refusal there is the
  guard's own documented trade ("a party closing the sentence before a cite
  with no signal word between … is left unfaked at that one spot"), and a leak
  the scrub is REQUIRED to leave alone must never be reported. Offsets carry
  across because `_mask_uncached` blanks IN PLACE, so the masked copy is the
  same length; the code checks that rather than assuming it, because if it ever
  stopped holding every offset would point at the wrong characters silently.
  Residual, and stated: at such a site the value is now silent on the LEAK tier
  as well as unfaked — which is what the guard has always chosen there, and the
  alternative was a folder that could never resolve.
  **A word the composing faker KEPT is not one of our fakes**
  (`name_fake_words`). The furniture of a party name is preserved verbatim
  ("The Lovelace" -> "The Flintham") and a `{braced}` keep is too, but the
  fake was split word by word and every word counted — so "the" became one of
  "our person fake words" and `half_scrubbed_scan` read EVERY title-case
  phrase as a half-scrubbed pair. One landlord-tenant filing reported 71, of
  which "The Bane Act", "The Unruh Civil Rights Act", "The Stanley Mosk
  Courthouse" and "TO THE HONORABLE COURT" are representative.
  `registry.keeps_word` is the same hook `_pn_fake_person` consulted when it
  decided to keep the word, so the two can only agree.
  These scans must never re-flag the run's OWN fakes: `_pn_word_is_own_fake`
  recognises a bare fake ("Keswick") AND a welded one where a splice glued the
  fake to a neighbour ("CORPORATIOLORNE10" carries "lorne10", "POSTBOX4.ORGPANY"
  carries "postbox4"), and a phrase is suppressed once the fake tokens are
  removed and no real name still stands — so a fake dragged by a non-name
  prefix ("ASIC Pruett Keswick", "Nolan Relations") is not reported as
  unscrubbed.
  **…and the set has to hold what the lookup asks for.** `known_fake_words`
  stored the fake word as written while every consumer looks one up by its
  BASE — `_pn_word_is_own_fake` through `_pn_word_base`, `_pn_strip_prior_fakes`
  through `_pn_word_affixes` — and both of those strip a POSSESSIVE. So
  "Mr. Kool's Collision, LLC" faked to "Mr. Redwood's Lightwell, LLC" put
  `redwood's` in the set, the scan asked for `redwood`, and a delivered
  worksheet carried **`Mr. Redwood's` as an unscrubbed name**: the run reporting
  its own stand-in, a question with no right answer — `no` leaves what was
  already correct and `yes` mints the stand-in as a real value. ("Lightwell",
  carrying no possessive, was recognised perfectly, which is why this survived.)
  Not merely noise: `_pn_strip_prior_fakes` missed it the same way, so a `yes`
  would have faked the phrase a SECOND time — the chain below, reached from the
  other end. The set contributes the base too; `name_fake_words` always did. A genuinely-new real name beside a fake is still surfaced —
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
- **A filing NAMES ITS OWN PARTIES, and nothing read the declaration**
  (`defined_name_scan`). A complaint introduces the people in it by declaring
  them: `Susan Spellman ("Spellman")`, `ACME CORPORATION, INC. ("Acme")`. The
  parenthetical is the document saying, in its own words, that the run in front
  of it is a NAME and that this is the short form the rest of the filing is
  written in — corroboration of exactly the kind a STRUCTURED harvest carries
  ("Yu Decl."), and far stronger than capitalisation alone. Three passes
  already read the shape and every one of them needs the parent to be KNOWN
  first: `_pn_split_cell` reads it out of the E-Court template cell (and only
  for a two-word-or-longer short form), `register_short_names` iterates
  `self.terms`, and `review_definition_survivors` is scoped to initialisms of a
  party already tracked. So a party no template named and no role anchor
  reached — a witness, a non-party employer, a co-defendant added by amendment,
  a plaintiff in an exhibit from another matter — was defined in the body,
  printed under its short form on every page after that, and met NO pass at
  all: not faked, and **not flagged either**, which is the half that makes it
  worse than an ordinary leak.
  REPORTED, never repaired, and that is not timidity: `X ("Y")` is also how a
  filing defines an AGREEMENT, a statute and a published decision, so minting a
  term off this shape would rename a cited authority the moment one carried it
  — the trade the whole method refuses. A `yes` on the row makes the value an
  authoritative term, and the re-run's `register_short_names` then binds the
  short form off the parent, so ONE operator decision closes both halves.
  Read from the SOURCE (the definition is in the document, not in the export)
  and reported only where the value SURVIVED into the export.
  The screens, in the order they earn their keep. The **DEFINITE ARTICLE**
  carries the dominant false-positive family and no word list can: `the Subject
  Property ("Property")`, `the Lease Agreement ("Lease")`, `the Note ("Note")`
  — a defined THING is introduced with an article and a party never is, while
  Property, Lease, Policy and Note are all real surnames, so widening a
  gazetteer to cover them would cost the very names this exists to surface.
  Refused whether the article stands OUTSIDE the run (lower-case, a lookbehind)
  or was captured INSIDE it because the sentence began with it — at the stated
  cost that an entity whose registered name opens with "The" is missed by this
  tier, which every other harvest still reaches. The **SHORT FORM must be a
  WORD OF THE PARENT**, the same corroboration `register_short_names` demands;
  an INITIALISM is deliberately not enough here, because against an UNKNOWN
  parent `("UCL")`, `("FEHA")` and `("RJN")` are defined legal vocabulary far
  more often than a party's initials, and the tracked-party case already has
  its own backstop. The run **STOPS AT A FULL STOP** (`_pn_defined_name_run`) —
  the `_PN_DECL_NAME_WORD` lesson exactly, or "…enforce the Provision.
  Carpenter Smith" is read as a party named Provision — with a corporate suffix
  and an honorific exempt, since those carry a period and are part of a name;
  the offset it returns is what the article lookbehind must be taken from, or
  the article of the PREVIOUS sentence refuses the finding. And a candidate
  inside a protected CITATION span is refused, which is load-bearing rather
  than belt-and-braces: a brief defining a short form inside the cite (`Ewald
  v. Nationstar Mortgage, LLC ("Nationstar") (2017) …`) offers the cited party
  up as this case's own. **But protection must not DEPEND on a parser
  succeeding** — the doctrine `_in_authority_context` states for the rewrite
  path, and the report needs it more, because a `yes` on the row mints the
  value as an AUTHORITATIVE term and renames the decision in every export. A
  parse that fails hands back nothing at all, and a SHORT cite is exactly the
  shape that fails: `Market Lofts Community Assn. v. 9th Street Market Lofts,
  LLC ("Market Lofts")` with no year or reporter left in reach parsed as
  nothing, and the published decision's own defendant was reported as a name
  this case had failed to scrub. So the SHAPE is screened too
  (`_pn_in_case_name`): a run standing after a " v. " with nothing but more
  party name between, or after an `In re` / `In the Matter of` lead — the other
  way a case names itself, and the one with no " v. " in it at all. ONE anchor,
  where `_in_authority_context` requires two, because the costs run the other
  way: that method decides whether to REWRITE, where a wrong refusal leaves a
  real party in the clear, while this one decides whether to ASK, where a wrong
  refusal loses one line of a worksheet. The left anchor is the one that
  survives a cite the parser could not read — the year and the reporter are
  what an OCR'd or wrapped cite loses; " v. " is two characters in the middle
  of the name. Accepted cost, stated: a brief reciting its OWN action inline
  ("In Rasho v. Quillmark, LLC ("Quillmark")…") earns no row, and such a
  party is reached by the caption, the template and every role anchor. The
  PARENTHETICAL is screened on its own text as well: a short form carrying a
  versus token (`(hereinafter "Mkt Lofts v 9th St")`) is the document saying
  what it will call an AUTHORITY, since no party of any matter is named
  "X v. Y" — which is what holds where the shape of the surrounding cite does
  not, a short cite defined a second time deep in an argument having no cite
  furniture beside it at all. That parse is the expensive thing on the whole leak
  path (~0.8 s on a 214 KB brief) and this is the ONE scan asking it about a
  THIRD body — the other four share the export and its column-ordered twin, so
  the source is a real extra parse and not a memo hit. So it is paid LAZILY,
  once, only after a candidate has cleared every other screen: a declaration,
  an exhibit and a proof of service offer none and pay nothing, and
  `_mask_protected_citations`' two-entry memo stays a PAIR.
- **A name is the thing in a filing that DOES something** (`narrative_name_scan`).
  "Spellman confirmed the transfer", "Rasho emailed the branch manager",
  "Sarkisyan resigned in March". A capitalised run standing as the SUBJECT of
  an active reporting verb is a person or a company and nothing else in a
  pleading stands there — an agreement is signed, a motion is filed, a property
  is located; the sentence turns passive the moment its subject is not an
  actor. It is the only anchor that needs no role prefix, no label, no caption
  column, no signature block and no parenthetical, which is what makes it reach
  a witness named nowhere but the fact section. Run on the OUTPUT for the
  reason `unknown_name_scan` is: a party correctly bound shows up as its fake
  and goes quietly, so what is left is what nothing knew to look for.
  The **VERB IS LOWER CASE**, which is the whole separation between prose and a
  heading — "Doe Failed To Mitigate Her Damages" is a section title and every
  word of it is capitalised, so that one requirement removes the false-positive
  family `prune_heading_only_terms` exists for. `_PN_NARRATIVE_VERBS` is
  deliberately not "every past-tense verb": it is verbs whose subject is an
  ANIMATE or CORPORATE agent, and "provided", "failed", "contained", "required"
  and "showed" are left off precisely because an agreement, a statute and an
  exhibit are their commonest subjects. The leading word carries the finding
  and takes `_pn_is_name_token` — the SAME question the term builder asks
  before a bare token may exist at all, so a role label, a professional suffix,
  a capacity word and a common-word surname are refused at one definition — plus
  `_PN_HARVEST_TOKEN_MIN`, since a two-letter capital before a verb is OCR
  debris. An HONORIFIC is stripped from the value: "Ms. Rasho emailed" is a row
  about Rasho, and keeping the title would mint a term narrower than the
  surname the document actually uses (the defined-term tier KEEPS it, because
  there it is part of a registered party name — "Mr. Kool's Collision, LLC").
  The ORIGINAL is evidence here as everywhere. Measured on this repo's own
  notes — 200 KB of capitalised technical vocabulary in running sentences, the
  shape most likely to be misread — the two tiers report **four** rows between
  them, one of which is the document's own worked example of a name. Cost is
  ~5 ms an export; the citation mask it reads is already warm from
  `surviving_reals`.
- **A TITLE is written in front of a surname and in front of nothing else**
  (`honorific_name_scan`). "Mr. Spellman", "Ms. Delacroix", "Dr. Ardeshirpour"
  — the shortest corroborated anchor there is, and nothing read it. The
  role-anchored tier needs a party role, so it never sees a fact section; the
  verb tier needs one of its own verbs, so "a meeting with Ms. Delacroix" and
  "Mr. Spellman's employment ended" go quietly past both. Between them that is
  most of how a filing refers to a person after introducing them once. Safe to
  read off the OUTPUT because the composing faker KEEPS an honorific verbatim
  (`_PN_NAME_FURNITURE`), so a party this run bound comes out "Mr. <fake>" and
  screens as neutral; what is left standing behind a title is a name nothing
  knew about. **`Dr` must carry its PERIOD**, alone among the titles: it is the
  one that is also an ordinary word of a filing — the street suffix — and it
  lands in exactly this shape, so "1200 Sunset Dr Los Angeles" read as a doctor
  named Los. Only a TRAILING possessive is stripped from the value; an interior
  one is the name continuing, and stripping it everywhere turned "Mr. Kool's
  Collision" into "Kool Collision", a value the document does not contain and a
  `yes` would key to nothing.
- **An e-mail HEADER names people on its own lines** (`mail_header_name_scan`).
  An exhibit e-mail printed to PDF carries `From: Susan Spellman` and `To:
  Marcus Delacroix` as header lines; the display-name path binds a name only
  inside a `Name <addr@domain>` PAIR, so a header that prints the name apart
  from the address reached nothing at all — and an e-mail chain is one of the
  commonest exhibits there is. REVIEW rather than a harvest, unlike the
  `Attn:`-style labels it would otherwise sit beside: a header line is not only
  ever a person ("To: All Employees", "From: Accounts Payable", "Cc:
  Undisclosed Recipients"), and the harvest tier's cost for a wrong guess is a
  rewritten document where a worksheet row costs one `no`. Anchored at the
  START of a line, because "from" and "to" are two of the commonest words in
  English and only the header form puts one at a line head with a colon after
  it; two words minimum, since a single capitalised word after "To:" is far
  more often a department or a wrapped subject line. `_PN_BACKOFFICE_WORDS` is
  the remainder this pass turned up — most department vocabulary (Human
  Resources, Customer Service, Legal, Operations, Employees, Recipients) was
  already in the gazetteer, and the accounting/facilities words were not. None
  of them is a California surname, which is the one screen that gazetteer must
  pass.
  All four tiers are REVIEW, so they surface a row in `LEAKS.xlsx` and do NOT
  gate delivery — the same standing as `unknown_name_scan` and the half-scrub
  sweep, and the same limitation the "exhibits from another matter" note
  states. `_pn_review_word_is_vocabulary` is the one neutrality rule they
  share, for the reason `_weld_core` is shared: two tiers answering "is this
  word a name?" differently is how a value one pass reports and another cannot
  is born. None is in `_PN_NAME_TRIM_CLASSES` — every value is already exactly
  the name its anchor declared, and the edge trim is a PERSON-path rule that
  would cut into an entity's own trailing word. Cost is ~12 ms an export each,
  the citation mask being warm from `surviving_reals` by the time they run.
- **An ALIAS stated in BODY TEXT is a name, and only the CELL parser read one**
  (`_pn_alias_pairs`, `_PN_AKA_TEXT_RE`). `_PN_AKA_ALTS` existed to split an
  E-Court template cell (`_pn_split_aka`), so the shape a complaint actually
  uses — "Defendant John Smith, also known as Johnny Smythe, opened the
  account" — reached no pass at all. Measured on the pipeline as it stood, the
  legal name was bound and faked and the alias shipped verbatim IN THE SAME
  SENTENCE ("Defendant Wemyss Paget, also known as Johnny Smythe"), with every
  review scan silent: the fuzzy sweep cannot reach it (Smith -> Smythe is two
  edits at a length where `_pn_name_fold_dist` allows one) and
  `half_scrubbed_scan` does not fire, because the alias is a whole name of its
  own rather than a bare token standing beside a fake. Registered at the dba's
  tier because it carries the dba's corroboration — nothing but a name follows
  "also known as" — with one difference: a dba is always a BUSINESS while an
  alias is the same kind of thing as its head, which `_pn_append_name_terms`
  already knows, so the pair is handed back joined by a bare "aka" and that
  function does the rest. `_pn_name_pair_ok` is the screen the two harvests
  share (both sides ≥2 words, no signature-block vocabulary, no bare role).
  A LEADING role word is trimmed off the head — that is how the sentence is
  written — while a role word standing INSIDE either side means the phrase ran
  past the name and is fatal. Both sides are held to one LINE, the dba rule's
  reasoning biting harder here: an alias marker sits mid-sentence, so a phrase
  allowed to jump a wrap on a two-column page swallows the interleaved
  signature block.
- **A DEPOSITION is the sibling of a DECLARATION, and reached nothing.**
  "Declaration of X" and the short cite "X Decl. ¶ 4" are both harvested — the
  declarant cite being the single highest-value place a witness name leaks —
  while `DEPOSITION OF SUSAN SPELLMAN` and `(Spellman Depo. 45:12-16)` yielded
  nothing, though a summary-judgment or fee motion cites deposition testimony
  constantly and the deponent is routinely a witness on no party template. The
  anchor is the same shape carrying the same corroboration; only the noun
  differs. It costs no new machinery: `_PN_DECL_TITLE_RE` gains the noun,
  `_PN_DECL_REF_RE` already captures any word starting with a capital D and
  defers to `_PN_DECL_REF_WORDS`, which gains dep/depo/depos/deposition. As
  safe as the Decl. forms for the same reason — a longer D-word letters out to
  something the set does not hold ("Department", "December", "Decker") and is
  dropped by the validator. The date guard stays scoped to `dec` alone
  (`_PN_DECL_REF_DATE_WORDS`): "Dec. 5, 2024" is a date, while "Depo. 45:12" is
  a page:line pin and is exactly what this is looking for. The deposition's own
  descriptor words join `_PN_DECL_DESCRIPTOR` — the `Supporting Declaration`
  rule — or "Videotaped Deposition of Marcus Delacroix" reads as a deponent
  named Videotaped.
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
  (`_pn_name_variants`); this is the net under them.
  REPORTED, never repaired — a near-miss substitution would rename a cited
  authority the moment the OCR mangled one, which is the trade the whole method
  refuses. Affordable via a 3-gram index over tracked tokens: a single edit in
  a token of length ≥ `_PN_NAME_FOLD_MIN` always leaves one shingle intact, so
  a shared shingle is a necessary condition and the comparison is never a
  product. The citation mask is now memoized (one entry, keyed on the text)
  because three scans over one export ask for the same masked body and the mask
  runs the whole citation parser.
  **…and the net had a party-shaped hole in it and a threshold that was not
  its own.** A delivered export carried FIFTEEN distinct fax-scan spellings of
  its own plaintiff's name across two exhibit pages — "Wcstlalce",
  "Weatla.ko", "Wesnuke", "Wi:t;Ulilke", "Wcrtlake" — while the clean spelling
  was faked on every other page: a half-scrubbed document naming the party, and
  nothing reported one of them. Three causes, each closed at its own end.
  (1) `_tracked_name_token_index` held the PERSON categories alone, so an
  ENTITY plaintiff was not a candidate at all — the distance was never
  measured because the target was never in the index, and a company is the
  plaintiff in most of what this tool processes. Nothing in the scan's
  reasoning is person-specific: it compares an output word against the REAL
  values this case tracks, and a distinctive company name is at least as
  distinctive as a surname. That is NOT `name_fake_words`' rule and must not be
  confused with it — there the set is our own STAND-INS, and an entity's fake
  word ("Relations", "Operations") sits beside ordinary capitalised prose all
  the time. The mirror-image risk here is the GENERIC words a firm name is
  built from, so the entity side is screened with `_pn_is_generic_token`
  (`_PN_FUZZY_TARGET_CATS` / `_PN_FUZZY_ENTITY_CATS`) — the same screen the
  term builder applies before a bare token may exist at all, so both ends ask
  one question. That screen is partial and knowingly so: sixteen corporate-form
  words pass it ("Services", "Holdings", "Group", "Industries"), and admitting
  all sixteen as targets measured ZERO rows on 42 KB of clean legal text and
  five on 223 KB of this repo's own prose — the tolerance the other REVIEW
  tiers already run at, and cheaper than a second word list that could answer
  the same question differently.
  (2) The scan borrowed `_pn_name_fold_dist`, which is the MINTING fold: it
  decides whether to hand two spellings one stand-in, where a wrong answer
  silently renames a person and ships. This scan decides whether to ASK, where
  a wrong answer costs one worksheet row. Sharing the threshold calibrated the
  report by the mint's risk. `_pn_scan_fold_dist` is the fold plus one, which
  is measured affordable (rows go 4 → 10 on 42 KB of clean legal text against a
  deliberately over-large 802-token target set, 12 → 57 on this repo's notes)
  where plus TWO is not (38 and 226 — a worksheet nobody reads). The minting
  fold itself is UNMOVED, deliberately: a folded fake is what a delivered key
  pins, and widening it would move bindings a re-run without its key
  re-derives.
  (3) The second edit is spent only where the run can SEE the text layer is
  degraded (`_pn_degraded_spans`), and it is licensed by the TRACKED name
  rather than by the survivor (`_PN_SCAN_DEGRADED_MIN`, so `_pn_scan_fold_dist`
  is deliberately NOT symmetric): the fold's own reasoning is that a longer
  token plausibly carries more independent typos, and three slips inside a
  five-letter token is 60% of it — a five-letter party word ("Sales") reached
  "Dealer", "Deale" and "Iller" that way, three of the five noise rows on the
  degraded pages, while every real hit came off an eight-letter one. The
  tracked spelling is the one the run is sure of; the survivor is the mangled
  half and may have lost characters outright ("Wcatlak").
  **…and a degraded scan's spellings are not clean Title-case words**, which
  is all the candidate pattern would look at — so the very region the widened
  tolerance exists for was full of words the scan refused to see ("Mark
  Va-iq11ez", "Pre1tlge", "Whorto1t": an interior digit or mark inside a
  letter run). Inside a degraded region ONLY, a DEBRIS-bearing candidate
  (`_PN_DEBRIS_CAND_RE` / `_PN_DEBRIS_MARK_RE` — a digit, or a speck period
  with alphanumerics hard against it; an interior HYPHEN is deliberately not
  debris, or every compound surname and this run's own compound fakes would
  qualify) is admitted and compared on its LETTER REDUCTION
  (`_PN_DIGIT_LETTERS`, digits read back as the letters a scan renders them
  from). Two rules differ from the clean tier, each licensed by the debris
  itself, since a clean word never carries an interior digit and the
  "Dealer"~"sales" noise family therefore does not exist here: no
  `_PN_SCAN_DEGRADED_MIN` floor on the tracked name (or a seven-letter
  "Vasquez" stays unreachable), and no 3-gram screen — the debris mangles
  every trigram window ("vaiqllez" shares none with "vasquez"), and the
  screen exists to make a per-word scan affordable on EVERY page where this
  tier runs only on a degraded region's debris words; direct comparison there
  measured ~0.1 s against a deliberately over-large 802-token set. Reported
  RAW, so the row is locatable and a `yes` fakes exactly what is there. On
  the delivered export the two tiers together turn nineteen rows where there
  were none — the Westlake family, the signatory, the dealership and the
  guarantor's street among them. Residual, and stated: spellings four or more
  slips out, and a value that appears ONLY mangled (nothing tracked to
  compare against), stay out of reach by this route. What covers those is the
  degraded-region line below, which needs no per-word guess at all, and the
  labelled-contact sweep beside it.
  **A near-miss standing where a FULL NAME is INTRODUCED is a different
  person, not a slip** (`_pn_full_name_intro`, `_PN_INTRO_FOLLOW_RE`,
  `_tracked_person_tokens`). "Davis Smith" is one edit from a tracked
  "David", and the sweep reported it as a misspelling of David Thomas — and
  the alias pre-fill would then have answered the row with `*David`, merging
  a different person into the party on the next pass. A name in a filing is
  written given name first, so the SURNAME beside the slip is the evidence: a
  capitalised name word, across WHITESPACE ALONE (a run of blanks, or one
  pleading wrap with its gutter number), that nothing tracks, that is not one
  of this run's stand-ins, and that the document never writes lower-case.
  Each screen closes a shape the scan exists for: a tracked surname beside
  the slip is the ordinary misspelling ("Michale Rodgers"), a stand-in
  beside it is the half-scrubbed pair, and the lower-case screen is what
  catches an all-caps caption's "DAVIS TESTIFIED" where no list would. A
  COMMA or any punctuation between the two words gives no marker — "Davis,
  Smith and Jones" is a list, "met Davis. Wilson" a sentence end — at the
  owner's direction. FOLLOWER only, deliberately: a person is introduced
  given name first, so a misspelled SURNAME behind an unknown given name or
  a nickname ("Mike Rodgerz") still has nothing after it and is still
  reported; a preceder rule would have muted exactly that. Asked of EVERY
  occurrence of the word, since evidence anywhere that it names a different
  person settles it for the document, and only where every near token is a
  PERSON's — a company is not introduced this way, so "Wcstlake Village" is
  still a slip of the entity plaintiff. The minting fold is untouched: it
  binds tokens with no context to read, and moving it moves delivered keys.
  **The sweep reads HOW MANY spellings the document offers, and WHERE an
  edit fell** (`_pn_ocr_distance`, the collect-then-decide pass in
  `fuzzy_survivor_scan`, `test_variant_reach.py`; all at the owner's
  direction). A lone near-miss of a tracked word — however often it recurs,
  since repetition is not a second spelling — is as likely a different name
  as a slip, so it must be a CLOSE match: the plain scan reach, none of the
  degraded or named-party bumps. Several DISTINCT near-misses of one word
  (grouped on the canonical spelling; the tool's own `_pn_name_variants`
  are not variants) are the signature of a scan that keeps mangling that
  name, and that is where the real name becomes obvious: there the full
  reach applies, and one degree further — a spelling within the fold of an
  identified variant is a variant too ("Wcstlelce", four slips from
  Westlake and one from "Wcstlalce"). The distance is weighted by POSITION.
  A wrong letter in the middle is what OCR does; a wrong first or last
  letter is more often a different name and costs 1.5, while a letter
  clipped off the front or the back — what a scan does to a word's edges —
  costs 0.5 against 1 for one lost from the middle. So "thanisl" is
  Nathaniel (two clipped off the front, one middle letter wrong: 2.0) and
  not Daniel (3.0), where the plain count calls them equal at 3. The
  end-letter penalty is dropped (`ends=False`) for the WIDE reach and the
  second degree, since there the document has already shown the scan
  mangling the word and any position goes; it is kept for the lone
  variant's close match. **Two more clues, both about COMPANY.** A lone
  far variant that NEVER stands beside a name word nothing tracks
  (`_pn_has_name_companion`: in front of it or behind it, across
  whitespace alone; a tracked given name and one of our stand-ins do not
  count, an honorific does not) is a BARE survivor, which is what a mangled
  party name looks like, and it is reported at the wide reach after all —
  "Vatqual" alone, or behind "Manuel", is the defendant; "Robert Vatqual"
  is somebody else. CAPITALISED words only: a lower-case candidate is in
  the sweep on its SITE alone (a stand-in two words off, a name label, a
  narrative verb), and ordinary vocabulary never has a name companion, so
  the clue said nothing and "YARDLEY flew a few feet forward" reported
  "forward" as a misspelling of a tracked Howard — a lower-case word is
  held to the close reach and nothing else. And the CLOSE reach is measured
  against the CANONICAL spelling: the tool's own derived near-spellings sit
  in the index one edit off the real word, so a match against one of them
  hands the survivor a free edit ("forward" is 2.5 from Howard and 1.5 from
  the tool's "ohward"), which is the second degree, reserved for a word the
  document has shown the scan mangling. And two adjacent words each too far to flag alone are
  flagged as a PAIR when each is near the corresponding word of one tracked
  full person name (`_tracked_name_pairs`: consecutive words and
  first-plus-last; either order, since a table writes surname first; no
  length floor and no end penalty, because the pair supplies what those
  stand in for): "Ionn Smleh" for John Smith, reported whole and AHEAD of
  the single words, since a `yes` on the pair fakes both where a `yes` on
  "Smleh" leaves "Ionn" standing. The MINTING fold is untouched — it binds a fake
  and moves delivered keys — and so is the pre-fill by value, which has no
  document to count spellings in. And a SLASH or bar with letters hard
  against it on both sides is a corrupted l (`_PN_DIGIT_LETTERS`,
  `_PN_SLASH_DEBRIS_RE`), admitted by the debris tier on ANY page at the
  clean reach through the 3-gram index: "Wi/son" is a word nowhere, where a
  digit inside a word is ("COVID19"), so unlike a digit it needs no degraded
  region to license it.
  **A CONTACT LABEL survives garbling far better than the value beside it**
  (`degraded_contact_scan`). "TEL: rAX: _,.___._ (228) 424-3-575" and
  "ADDRESS: l440S Whorto1t I..n" shipped a real phone number and the
  guarantor's street with every detector silent — a detector matches a SHAPE
  and the scan had broken the shape — and with nothing tracked to fuzzy-match
  against, since the values appear nowhere clean. The label is the one anchor
  left standing, so inside a degraded region a labelled value the detectors
  did not read earns a REVIEW row: the digit-bearing run after the label,
  RAW, trimmed of fill-rule junk and of a second label the line ran into. A
  phone or SSN needs four digits (fewer is a section number); an ADDRESS is
  mostly letters, so there the gate is one digit plus a street-shaped rest
  ("2UIHB Pass Rd"). A value carrying one of this run's own fakes is skipped
  — the detector that DID match already replaced it, and reporting our own
  output is a row no answer can clear. Degraded regions only: on a clean page
  an empty "FAX:" line is ordinary furniture. Residual, and stated: an
  unlabelled continuation line ("Biloxi, MS 39.532" under the street) is not
  reached; the row above it is what sends the operator to the block.
- **A DEGRADED text layer is a region the scrub CANNOT clean, and the run says
  so** (`_pn_degraded_spans`, `_pn_token_is_mangled`, `degraded_text_note`). A
  filing is born-digital and extracts cleanly; the EXHIBITS behind it are
  whatever the parties had, and a fax generation is the common one. A term
  matches WHOLE WORDS, and `_surviving_records` scans with that same pattern,
  so replacement and detection agree and BOTH are blind to a name the scan
  mangled; the reduced weld pass folds a lost SPACE, not a substituted letter.
  The export was therefore delivered looking exactly like the pages the tool
  really did read. Same doctrine as the low-dpi, re-OCR and ink-form banners —
  an inferred reading is never presented as equal to a read one — except that
  here the tool did not produce the degraded text and cannot repair it; what it
  can do is stop implying the page was scrubbed.
  **This is NOT `_text_looks_garbled` and the two must never be merged.** That
  one gates a DESTRUCTIVE pass (the page's real text is redacted and replaced
  with 300-dpi guesses), so it is deliberately conservative and has been
  retuned three times because each retune destroyed a page it misjudged — and
  it says False for both fax pages here, correctly, since re-OCRing a fax
  recovers nothing that is not already there. This is the opposite trade: a
  NON-destructive read whose worst case is a widened review tolerance and one
  log line. The measure is the fraction of word tokens that could not be words
  — an interior mark with alphanumerics hard against it on both sides
  ("miu!e", "d~boor"), a five-consonant run ("Wcstlalce"), or no vowel at all —
  aggregated over hundreds of tokens, which is why the threshold can be loose
  where a per-word guess could not be. Measured: this repo's own notes 0.002,
  the export's born-digital pages 0.000–0.020, its two fax pages 0.042 and
  0.076, against a cut at `_PN_DEGRADED_RATIO` 0.03. The mark class is narrow
  on purpose — `.` `,` `:` `;` `/` `-` `&` `@` and `()`/`[]` are exempt,
  because an abbreviation, a pin cite ("45:12-16"), a time stamp, a statutory
  subdivision ("585(a)") and this tool's OWN ink-form checkbox all put one
  inside an alphanumeric run — and a URL-shaped token is exempt whole: the
  authorities appendix this tool itself writes ends every export with
  verification links, and their `?`/`=` read as marks, so a JUD-100 short
  enough for its appendix to dominate a block reported its own links as a
  degraded fax. An interior CASE FLIP was measured as a fourth
  signal and REJECTED: it contributed 6 of 63 flags on the worst page and fires
  on every ordinary CamelCase word an exhibit carries (PayPal, iPhone, eBay,
  and the surname particles McDonald/DiGiorno `_page_looks_spliced` already
  exempts for the same reason). Measured LOCALLY, in blocks of
  `_PN_DEGRADED_BLOCK_TOKENS` on line boundaries: a degraded exhibit sits
  inside a clean filing, so a document-wide average dilutes it to nothing and
  the leak is local. ~58 ms on a 311 KB body, paid ONCE — memoized on the
  alternating pair the way the citation mask is, so the fuzzy sweep and the
  end-of-file note share the one pass, and keyed on the TEXT ALONE rather than
  `_scan_state_key()` because degradation is a property of the characters on
  the page and of nothing this run decided.
  (worksheet tab `LEAKS`; the old `pdf_linker_leaks.xlsx` name is still READ so
  a folder triaged under a prior version keeps its decisions). Columns lead
  with the flagged **Value**, its **Fix?** decision and the **Context** the
  decision is made on, with File/Type/Where/Notes trailing — the order driven
  by `_PN_LEAK_COLUMNS`, and the reader is header-NAME driven so inserting a
  column never breaks round-tripping. **One row per
  distinct value**: a name that leaks across many files is aggregated into a
  single row (files + locations merged) so the operator decides it once, not
  once per file.
  **The Context cell quotes the SENTENCE, and picks which one** (`_pn_context`).
  The value alone frequently cannot answer the row's own question: "Charge" is
  boilerplate in "CHARGE OF DISCRIMINATION" and a surname in "served on Charge
  at his residence", and the operator had to open the export and find the page
  to tell — for a decision that, as `never`, then applies in every future
  folder. **The quote is read from the ORIGINAL body, not the export**
  (`_pn_leak_context`, the one rule the PDF path, the Word path and
  `--fix-leaks` share) — at the owner's direction, and for the same reasons the
  key's Context column reads it: the row's question is "what IS this value?",
  it is decided ONCE per value however many files carry it (the worksheet
  aggregates), and a `never` typed against it applies in every future folder —
  so the evidence is the document's own sentence, with no pseudonyms
  substituted around the value ("Ashely Langley served..." used to quote a
  sentence half made of our own stand-ins, which reads as the tool flagging its
  own output). Every flagged value is text the scrub did NOT replace, so it
  stands verbatim in the original by construction; the two exceptions fall
  through in order — a phrase CARRYING one of our stand-ins is absent from the
  source, so its REAL REMAINDER (the value `confirm_findings` reduces the row
  to anyway) is quoted; and with no original in hand at all (a `--fix-leaks`
  folder keeping no copy, its TEMP cache gone) the scrubbed export is quoted
  rather than leaving the row unanswerable. The SAME cell then quotes the
  EXPORT's own sentence for that value underneath, below a rule — original on
  top, then the deliverable, at the owner's direction, the same stacked pair
  the key's Context column carries, collapsing to the original alone where
  the two say the same thing — and the Where column still points into the
  EXPORT: that is where the leak stands. Both halves come from ONE call
  (`_pn_leak_quotes`), for the reason the key's do: they are one piece of
  evidence, and computed at two call sites they drifted into two. The export
  half is held to the original's passage; `--fix-leaks` passes
  `_pn_quote_shape` instead, since it parses every original into one body while
  each export is its own, so there the growth is replayed and the line range
  cannot be. (The flagged value is bolded in both
  halves: it stands verbatim in each, being precisely what the scrub did not
  replace.) Consequence, deliberate and the
  same trade the key already made: `LEAKS.xlsx` carries sentences of the real
  document. It always carried the flagged real values themselves and lives in
  the case folder for triage, so this changes how revealing the worksheet is,
  not which file is safe to send; nothing of it propagates to the master
  workbook (the KEEP sheet keeps instructions and notes, never Context).
  `--fix-leaks` reads the originals BEFORE its per-file loop now — the fresh
  findings' quotes need them — and keeps the TEXTS beside `note_original`'s
  reduced evidence, concatenated into ONE parsed body so every quote is
  answered by a single `_pn_context_prep` instead of thrashing its one-entry
  memo. Three things make the quote worth reading. It is rebuilt as PROSE
  from the same parsed body the Where column uses (the gutter number dropped,
  wrapped lines joined), because a sentence on pleading paper is spread over
  several numbered lines. It looks for the value as a WHOLE WORD first and
  falls back to a bare substring only when that finds nothing: searching with a
  bare `find` quoted the sentence a value happened to sit INSIDE another word
  of — "Arent" out of "Planned Parenthood", "Isl" out of "the Legislature" — so
  the cell read as a sentence with nothing to do with the row and no answer
  could be given. (The fallback stays because a WELDED or REDUCED finding has
  no bounded occurrence by construction, and the nearest readable sentence
  beats an empty cell.) It prefers an occurrence on a PROSE line over one in
  a heading (`_pn_line_is_prose`, the same test `prune_heading_only_terms`
  uses) — the first occurrence is often a caption that proves nothing, while a
  value found ONLY in a heading is quoted as that heading, which is itself the
  answer. And the span GROWS to its neighbours while it is under
  `_PN_CONTEXT_MIN`, because legal prose is full of abbreviations and
  "(Rasho Decl." is a sentence to a parser and nothing at all to a reader;
  it is bounded by the run of same-kind lines so a sentence never swallows the
  caption above it, and capped at `_PN_CONTEXT_MAX` with a window centred on
  the value. The **Fix?** column round-trips: `yes`=auto-fake, `no`=leave,
  `never`=never fake this value, in this or any folder (the nuclear keep, on the
  dropdown beside yes/no),
  **`*ANOTHER REAL VALUE` = this value is a MISSPELLING of that one**, so it is
  faked as the same misspelling of that value's fake (the alias rule above),
  **any other text = an explicit operator-typed replacement**, and
  **`[bracketed]` text naming part of the value = keep that part verbatim and
  auto-fake the rest** (`_pn_bracket_keep`; "Raytheon's [Human Resources]" fakes
  the name, keeps the department words).
  **…and a bracket works on a WELDED value.** "John Doeis" — a lost space
  gluing the party to the next word — answered with `[is]` always parsed
  correctly (fake "John Doe", keep "is") and then cured nothing: the remainder
  becomes an ordinary whole-word term, and a whole-word pattern cannot land
  where the printed boundary is missing, so the export shipped half-scrubbed
  ("Wemyss Doeis") while the log said the bracket was honoured.
  `_pn_bracket_welds` reads the weld out of the (value, cell) pair — the
  fragment's last character hard against the kept text's first, both word
  characters, so a printed separator ("Raytheon's [Human Resources]") never
  qualifies — and `_pn_apply_weld_follows` rebuilds the fragment's term with
  `_pn_build_pattern(follow=…)`, the declarant harvester's own "SmithDecl."
  relaxation: the term may butt against exactly that kept text and nothing
  else. FULL-name categories only (`_PN_WELD_FOLLOW_CATS`), never a bare
  token — the full value is anchored by its own leading word, while a token
  with a follow would fire inside unrelated longer words. Assigned in place
  on the term, so replacement and the leak scans stay mirrored by
  construction, and applied over the FINAL term list, loaded key rows
  included — on a re-run the retired bracket row is an ordinary binding, but
  the worksheet decision persists and the PDF still carries the weld. The
  export then reads the fake glued as the source was ("Kelsallis"), which is
  honest — the document lost that space, not this tool — and reverses
  byte-faithfully, the macro's substring search finding the fake inside the
  welded token. RIGHT-side welds only: `_pn_build_pattern` has no left
  relaxation, because the left boundary is the one that stops a short name
  firing inside a longer word. A keep can never rip its word out of OTHER
  text either way — keeps and terms match on word boundaries, never
  substrings, so `[is]` on one row touches no "This", "basis" or "analysis"
  anywhere. **Website vs e-mail**: a government
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
- **A page whose TEXT LAYER IS DRAWN TWICE must export once**
  (`_drop_overdrawn_spans`, applied to the body spans and the margin spans in
  `_detect_line_anchors`). A page can carry its text twice and look perfectly
  normal, because the copies land on top of each other: an e-filing stamp that
  redraws the content, a faux-bold double strike, or an OCR overlay laid over a
  text layer `_reocr_garbled_pages`' redaction failed to remove — the one this
  tool can produce itself. `page.get_text("text")` survives it, returning the
  duplicate as its own LINE, which is ugly and harmless; the SPAN path does not,
  because it joins a row's pieces left to right and the two copies of each piece
  sort ADJACENT: "BOWMAN BOWMAN AND BROOKE LLP AND BROOKE LLP Michael Michael
  Chung (SBN 243204) Chung (SBN 243204)". Not cosmetic — a whole-word term
  cannot match "Michael Michael Chung", so the party is left standing; the
  harvester reads the doubled run as a NAME and mints it, so a delivered key
  carried `Michael Michael Chung`, `Justin Justin Carpenter` and `SeeSee` as
  party rows with their own stand-ins; and `_pn_context` quotes the wreckage
  into the worksheet, where it reads as an unrelated extraction failure. A span
  is a re-draw when it carries the SAME TEXT over OVERLAPPING ink
  (`_spans_overdrawn`, half the smaller box) — overlap and not proximity,
  because two genuinely different words cannot overlap at all without the page
  being unreadable, while two copies of one line never sit exactly on top of
  each other (a second layer is set in its own font at its own metrics).
  Compared on exact text, so an OCR layer that MISREAD a word is left alone:
  this can only ever remove a piece the page also has somewhere else. A copy far
  enough away to be a real second column is untouched.
  **…and the copies routinely do NOT split their row the same way**
  (`_span_is_redraw_fragment`). Exact-text equality collapses two copies only
  when both cut the row into the same pieces, and an OCR layer emits one span
  per WORD while the layer underneath has one per styled run — so nothing
  matched and the row joined left to right as `EDGECOMBE EDGECOMBE N. DENHOLM,
  ESQ. (SBN 584673) N. DENHOLM, ESQ. (SBN 584673)`. That is why the operator
  reports the duplication as "always the first word on the line": both copies
  start at the same left edge, so their first pieces sort adjacent and the
  word-by-word copy trails after the long span. A piece whose BOX is inside
  another span's box and whose TEXT is inside that span's text is dropped, and
  dropping it can lose nothing — its text is on the page, in that same place,
  as part of the span it sits inside. Both conditions are load-bearing and
  neither is loose: ordinary typesetting never nests one span's box inside
  another's (spans on a line abut), so this fires only where something really
  was drawn twice, and a page-wide watermark is untouched because its box is
  not inside a body span's and the body text is not inside "COPY". Banded by
  row, so a clean page pays one bucket lookup per span and drops nothing.
  **The FLOWING-text path needed it too** (`_page_flowing_text`). `get_text`
  returns the duplicate as its own LINE, which reads as merely ugly — until a
  weld-cure pass matches a party's reduced core ACROSS the seam between the two
  copies and rewrites the text: "Defendant Best Formulations LLC is a tenant at
  the Property." came back "Defendant Defendant Best Best FonnuFalcon lations
  LLC is a tenant LLC is a tenant at the Propc1ty." A doubled page is also the
  page most likely to defeat the gutter-number detection, so it lands HERE
  rather than on the row path that was fixed first. Rebuilt from the deduped
  spans, not post-processed as a string: the copies are separate content
  blocks, so `get_text` returns all of copy one and then all of copy two and
  the duplicate lines are nowhere near each other. Gated on the same POSITIVE
  evidence — a page with no re-draw is returned byte-for-byte as `get_text`
  gave it, so a document that repeats a line on purpose (a table row) is
  untouched and the ordinary export does not move.
  **…and the two strikes can interleave INSIDE one extracted run**
  (`_undouble_strike`), the third shape and the one no span comparison can
  see. A faux-bold double strike draws every glyph twice, and when extraction
  merges the copies into ONE run the line copies out with every character
  doubled: an exhibit slip sheet reading `Exhibit A` on the page copies as
  `EEXXHHIIBBIITT ""AA""` — native to the PDF, not the OCR. A whole-word term
  cannot match the doubled spelling (a struck party name ships in the clear),
  the citation parser is blinded, and the exhibit yielded no cover page, no
  bookmark and no body links; a delivered batch carried its whole exhibit set
  A-E this way. Collapsed at extraction, in both renderings of a page so they
  cannot disagree: per SPAN in `_drop_overdrawn_spans` (before the dedup, so a
  struck span and a plain re-draw of it agree on their text and collapse) and
  per LINE on the flowing text (`_undouble_strike_lines`), which covers the
  export, the scrubber, every leak scan, the citation parser and the
  unscrubbed evidence copy from the one seam. The gate needs the text to read
  as double-struck AS A WHOLE — nearly every non-whitespace character in an
  adjacent identical pair, PLUS one alphabetic run of ≥6 characters that is
  pure pairs, because the ratio alone admits text with no letters at all (a
  damages-table row "2222 | 3333" is four digit pairs against one single, and
  halving it corrupts the figures) and short coincidences ("AA BB CC"); no
  English word is six letters of pure pairs, so the anchor costs no real text,
  and "BOOKKEEPER"/"balloon"/"coffee" never qualify on the ratio. Halving is
  length-honest, so exhibit AA struck twice ("AAAA") comes back "AA", and a
  single-struck "EXHIBIT AA" is protected by "EXHIBIT" itself, which pairs
  nowhere. Bookmarking gets a belt of its own (`_exhibit_cover_match`):
  `_collect_rows` reads the raw text layer, so the exhibit-cover scan retries
  a failed match on the undoubled line and on a token-wise repeated one
  (`EXHIBIT "A" EXHIBIT "A"`, the two copies extracted as separate runs merged
  on one baseline) — every fallback still has to satisfy the same cover
  regex, so nothing refused for cause can start matching. Costs ~0.05 ms a
  page (a hint regex early-outs the scan on ordinary spans). Accepted cost,
  same as the visual layout's: a delivered folder whose exports carried the
  struck spelling comes back normalized on the first FULL re-run — values and
  fakes unchanged, the key still pins every binding; only the struck line's
  characters halve.
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
  `_PN_COMMON_WORDS`, name-shaped, **actually welded** at the match site
  (`_pn_span_is_welded`) — a clean standalone occurrence belongs to the
  boundary-anchored pass, which yields to keeps and citations this pass cannot
  see — and **CASED** (`_pn_span_is_cased`): the site must carry a capital
  letter. A four-letter core nests inside ordinary PROSE constantly, prose is
  lower-case, and every observed real weld is a caption or caps run
  ("HELENRASHO", "AMEZCUApain", "MARIA46."). One delivered export had
  "automatically" rewritten as "lambournematically" through a whole
  promissory-note exhibit (and "automatic stay" as "lambournematic stay") off
  a trusted person token "Auto" — `_PN_COMMON_WORDS` does not carry "auto",
  and no list carries the next one: a token "Cont" turns "contractor
  continued the work contemporaneously" into "norwoodractor norwoodinued the
  work norwoodemporaneously", measured. The case of the site is the screen no
  list has to be kept for — `_pn_term_is_cap_only`'s reasoning, applied at
  the one tier that matches inside words, mirrored in both reduced passes,
  and carrying the same residual that rule already accepts: a scan that
  lower-cases a welded name is no longer cured by its short core. Short
  cores only — an eight-plus-letter core does not coincide inside
  vocabulary, which is why `_PN_WELD_CORE_MIN` is 8.
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
- **…and a printed checkbox is not always a SQUARE** (`_INK_USCORE_RE`,
  `_ink_underscore_slot`, the third arm of the gate). A local LASC order form
  rules its boxes as a run of UNDERSCORES and prints the check on top of them —
  `__ with prejudice as to` beside `✔ without prejudice as to`. Nothing in that
  page's line art is square and its footer reads "LACIV 140", a LASC LOCAL form
  number `_JC_FORM_NO_RE` does not match, so BOTH arms declined and an Order of
  Dismissal exported with every box reading `__`. On that form the checkbox IS
  the ruling: the export could not say whether the dismissal was with or without
  prejudice, or whether it reached the entire action, while reading like a
  complete document. The marks were legible the whole time — ZapfDingbats
  glyphs, each sitting ON the underscores of its own caption — so what was
  missing was a gate that let the page in and a slot to match them to: the
  ordinary probe window looks LEFT of a caption and this mark sits a point or
  two INSIDE it. The run must OPEN the span (a trailing fill-in rule, "of
  section _______", is not a box) and is CAPPED at four underscores, because a
  signature rule opens its span too and reading one as a box put a phantom
  `[ ]` beside the date. No raster pass: there is no printed square to measure
  ink inside, so the state is the glyph or the box is empty.
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

**The export mirrors the page's GEOMETRY, so it reads SIDE BY SIDE with the
PDF** (`_visual_row_text` / `_page_visual_text`). Joining a row's pieces with
one space destroyed exactly what the eye lines the two up by: a two-column
caption collapsed into one run, a centered heading landed flush left, and the
case-number column floated to wherever the party name ended. Every row is laid
out on a character grid derived from each segment's own x instead — the rule
`_form_layout` already applied to a court form, at `_VIS_CHAR_W` for body text
— and a page that is neither pleading paper, a form nor a table (an exhibit, a
letter, an order) is rendered positionally from its clustered spans, with a
real vertical gap kept as a blank line (capped at `_VIS_MAX_BLANKS`, so OCR
noise cannot demand a page of scroll). Three things make it safe. A segment at
the page's body-left edge computes column 0 and renders byte-identically to
the old join, so ordinary body prose does not move — and `_rows_body_left`
takes that edge from NUMBERED rows only, or a rotated margin label would own
column 0 and indent every line of the page. Within a flowing line a span is
padded to its column only across a REAL gap (`_VIS_GAP_PT`); anything narrower
keeps `_join_spans_spaced`'s own glue rule, so prose split into spans at a
style change renders as it always has and the citation parser never meets a
space run this pass invented (term patterns are immune either way — their
words are joined on `\s+`). And the layout is DISPLAY only: `_page_detect_text`
keeps its column-ordered rendering, citation detection keeps the flowing text,
and the scrub runs per column BEFORE the join, with the ORIGINAL x deciding
the column and the scrubbed text filling it — a fake of a different length
shifts what follows it on that line, the honest cost of the text really having
changed. Downstream, `_PN_GUTTER_RE` takes two-or-MORE spaces after the number
(a centered heading on a numbered line reads " 1        NOTICE OF MOTION", and
the exact-two match handed it the previous line's number), and
`_pn_context_prep` collapses space runs so a Context quote does not spend half
its width on the padding. Cost, accepted: exports of an already-delivered folder come back with the new
spacing on the first FULL re-run (values and fakes unchanged — the key still
pins every binding, only whitespace moves). `--fix-leaks` is indifferent: it
works on the `.txt` as it stands and never reopens the PDFs, so it neither
converts an old-format export nor is confused by either format.

**A SPREADSHEET printed into an exhibit exports as a TABLE** (`_page_table_text`).
A billing export, a damages schedule, a payment history: the page is a grid, and
plain extraction reads it a cell at a time, top to bottom. Every value survives
and the document still says nothing, because a rate no longer sits beside the
entry it belongs to — `Date / • / Type / Description / Matter / User / Qty /
Rate($) / Non-billable ($) / Billable($) / 04/04/2025 / Telephonic conference
with / …`. On a fee motion that is the exhibit the court actually reads. The
GATE is the symptom itself and costs nothing (`_page_reads_as_cells`): a page
whose text comes out as a tall stack of very short lines is a grid that came
apart one cell per line. Measured on the batch that reported it, the three
billing pages ran **99-100%** short lines at a median length of **10**
characters against **4-21%** at a median of **94** on the same document's prose
pages, so the cut has an enormous margin — and `find_tables` (~73 ms a page,
against ~2 ms for the extraction itself) is only ever paid on a page that
already looks like this, memoized so the export loop and `_page_detect_text`
run it once. Rendered pipe-delimited with a header rule, because the export is
read by a person AND by a drafting model and that is the one table shape both
read without being told; the text around the table keeps its place by y. The
line strategy runs first and the **text** strategy only where it found nothing
(an unruled UI export separates its rows by shading or by nothing at all) — it
is eager, so it never runs on a page the line strategy could read. And the
rendering must PROVE it lost nothing (`_table_keeps_every_word`), for the
reason `_reocr_improves` must: this replaces the page's own text for that
region, and a cell the finder failed to read would be a value gone from the
export with nothing to say so — a grid that drops a word is discarded and the
region keeps its ordinary text. Scoped to a page that is neither pleading paper
nor a court form: both have their own rendering, and swapping a whole page to
this one would cost the gutter numbers a pinpoint cite lands on. Residual, and
accepted: the text strategy splits on word gaps, so an unruled table can put
`Rasho v. Quillmark` in three columns — the row grouping, which is the point, is
still right.

## Citation linking

`find_all_citations` (full/short-form/supra/statute/rule) over the combined
page text; `resolve_url` per provider. Links are inserted **page-scoped**: a
citation whose text occurs once is linked only on its own page (not searched
across all N — that was O(cites×pages)). `_repair_link_uris` fixes a PyMuPDF
annotation-naming splice. Declarations/complaints skip linking
(`should_skip_linking`).

**Bookmarks are DETECTED structure, and a detector that reads the wrong text
mints junk the reader has to scroll past.** A petition with one
printed-webpage exhibit shipped four Document bookmarks — the petition's
title behind an 80-character underscore rule, and three sentence fragments of
the exhibit's Terms of Service, each with the browser's URL footer — while
the clean `EXHIBIT "A"` slip sheet and the I./II./III. headings earned
nothing. Four rules, one per failure. **A body-prose band is not a footer**
(`_footer_reads_as_prose`): the footer detector reads the bottom band of
every page, and a printed webpage flows its last lines into it, each page's
fragment distinct, so every page minted its own "document"; a band whose
lower-case non-connector words number ≥4 and outnumber the capitalized ones
is prose, treated as NO footer, and the page inherits the previous document's
identity (a filing's running footer is its title, in caps or title case —
accepted residual: a real footer set as lower-case prose folds into the
document before it). **Footer FURNITURE is stripped from key and label
together** (`_strip_footer_furniture` — underscore rules, URLs, and the
browser's bare page fraction "3/17", with lookarounds so a date's "8/20"
survives), or a page with the rule and a page without it read as two
documents. **A SINGLE exhibit cover feeds the tree**:
`_link_exhibit_references`' 2+ gate now gates only body-reference linking
(one "Exhibit 1" mention is usually prose, not a linkable attachment), and
the cover map flows to the bookmark builder whatever its size — but a LONE
cover must be STRICT (the label alone, or a letter form, whose separator the
regex already demands; a lone loose numeric match is more likely a wrapped
body sentence "Exhibit 3 hereto is..." that happened to start its line),
while 2+ covers corroborate each other as before. And with exhibits present,
`_detect_document_footers` keeps a SINGLE footer entry (`have_exhibits`) —
the file demonstrably holds 2+ sub-documents, so the one footered filing in
front of its exhibits deserves its bookmark even though the old 2-footer
gate said a lone footer proves nothing. **The section scan reads the row the
way the page prints it**: rows drop gutter line-numbers before matching (the
merged "5  I. INTRODUCTION" fails the label regex on the leading digit AND
stretches the bbox to the left margin so the centering test fails with it —
the same fix the exhibit-cover scan already carried), and the commonest
court heading style — body-size, not bold, centered or UNDERLINED — now has
cues that can see it: an underline is read from the page's own line art
(`_page_underline_strokes`, a thin horizontal stroke just under the row
spanning ≥half its width; PyMuPDF exposes no underline span flag) and counts
like bold on both heading paths, and centering alone carries an
outline-label heading only when the label has its own text ("I.
INTRODUCTION" yes; the caption's bare centered "V." no).

**An OCR'd slip sheet spells its quotes as APOSTROPHES, and a quote is a
RUN** (`_EXHIBIT_QUOTE_CHAR` / `_EXHIBIT_QUOTE_RUN`). A scanned exhibit
set came back as `EXHIBIT ''1''` and `EXHIBIT ' ' 2 ''` — OCR reads a
big straight double quote as two apostrophes, sometimes with a space
between them, or as a backtick pair or a prime — and `_EXHIBIT_COVER_RE`
allowed exactly one quote character on each side of the identifier, so
the whole set earned no cover, no bookmark and no body link. The quote on
either side is now a run of quote-shaped glyphs with horizontal
whitespace allowed between them and before the identifier, and ONE class
serves both sides, since OCR keeps no distinction between an opener and
a closer. The run can only stand where a quote could — the identifier is
still one to three digits or one or two capitals and the letter branch
still demands a separator before a descriptor — so a comma, a possessive
and a wrapped sentence are refused exactly as before. The strictness
strip on a lone numeric cover (`_EXHIBIT_QUOTE_LEAD_RE`) removes the
same run, or an OCR'd lone cover read as loose; `_LABEL_JUST_EXHIBIT_RE`
tolerates it so a footer repeating the slip sheet's spelling is still
just the id; and the body-reference search adds the unspaced `''5''`
form only, since it searches fixed phrases and a spaced spelling is
unbounded.

**…and an OCR'd IDENTIFIER is read against the SERIES**
(`_exhibit_ident_readings`, `_exhibit_series_numeric`,
`_exhibit_resolve_ident`). The quotes are not all OCR mangles: it reads
the label's own 1 as a capital I or a lower-case l and its 0 as a capital
O, so the set that arrived as `''1''` also arrives as `''I''`, `l` and
`lO`. `EXHIBIT I` is a perfectly good cover in a LETTERED set and exhibit
1 in a NUMBERED one, and the line itself cannot say which, so the reading
is decided ONCE per document from context: the unambiguous covers first
("2" and "3" beside it, or "A" and "B"), the body's own references only
where those tie ("attached hereto as Exhibit 1" is born-digital far more
often than the slip sheet is, and the page walk is paid only when a cover
needs it), and the letter where nothing decides — what an `EXHIBIT I`
cover always meant before. Ambiguity is narrow by construction: the
number reading stands only with no leading zero, so a lone "O" is only
ever the letter, and the letters reading stands only for the shapes a
lettered set uses (one capital, or the same one doubled), so "IO", "I2"
and "lO" are numbers and nothing else, and "I"/"II" are the only cases
the series settles. A third regex branch admits the shapes the letter
branch cannot (`l`, `|`, a mixed run) at the letter branch's strictness;
a pure capital run still takes the letter branch, so `EXHIBIT A` reads
exactly as it did. Downstream follows the resolved number:
`_label_is_just_exhibit_id` reads a footer's `EXHIBIT I` as exhibit 1's
own id once the cover map says the exhibit is numbered, and the
body-reference search adds a number's OCR spellings
(`_exhibit_ocr_spellings`) — only where the covers are ALL numeric, since
in a set that also has a lettered exhibit I that reference is its own.

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

**…and the shape guard covered the DEFENDANT only, so a cite the parser
missed had its plaintiff reported** (`_pn_cite_shape_spans`,
`_PN_CITE_SHAPE_RE`, `_before_v_context`, `_pn_before_v`). Both shape
screens — `_in_authority_context` for the rewrite and `_pn_in_case_name`
for the report — looked for a " v. " to the LEFT of a candidate, which is
where a defendant stands and never a plaintiff. So wherever the parser
could not read a cite (wrapped over a page banner, an OCR'd reporter, a
`supra` whose full cite is in another document) the defendant was kept and
the plaintiff faked on the write side, and on the review side the plaintiff
stood unmasked for every name-shaped tier — a batch reported the plaintiffs
of its appellate cites as leaks. Three things close it, at the seams that
already exist. The CLASSIC PATTERN is matched on SHAPE alone —
`X v. Y (2021) 71 Cal.App.5th 358`, the federal `(9th Cir. 1999)` year, `X,
supra, …`, `In re Marriage of X (2008) …` — and `_mask_uncached` blanks
those NAMES beside the parser's spans, so every tier that reads through
the mask (the fuzzy and half-scrub sweeps, the narrative, honorific and
mail-header tiers, and `_surviving_records`) is covered at one choke point.
The shape is deliberately the STRICT one, a " v. " or a `supra` AND a year
or a volume+reporter run hard after the name, so a caption ("RASHO,
Plaintiff, v. QUILLMARK"), this case's docket and an unpublished `No.`
cite never qualify; a run captured from the left is cut back at a citation
signal ("See", "Cf.") and at a full stop that closes an ordinary word,
while an abbreviation inside the name ("Assn.", "Servs.") is kept. The
name only is blanked — the year, reporter and pin stay for the identifier
scans. `_in_authority_context` gains the plaintiff's half
(`_before_v_context`): the candidate followed by a " v. " with nothing but
more party name between, then the defendant, then the year or reporter
with no break — both anchors, for the reason the defendant's half needs
both, and the same trusted-sides exemption, so this case's own caption
recited inline is still scrubbed; `_surviving_records` mirrors it as it
always did. And `_pn_in_case_name` takes the candidate's END and asks the
same question, for the role-anchored tier (which reads unmasked text) and
the defined-term tier. Residual, and stated: a party closing the sentence
before a cite with no signal word between ("…against Quillmark, Inc. Smith
v. Jones (2020)…") reads as that cite's plaintiff and is left unfaked at
that one spot, the trade the guard has always made.

**A cite STRUNG behind another has its SEAM for an anchor, a `supra` short
name is masked wherever the brief uses it BARE, and a word inside a URL is
never a candidate** (`_pn_string_cite_seam`, `_PN_STRING_CITE_SEAM_RE`, the
`strung` branch of `_PN_CITE_SHAPE_RE`, `_PN_CITE_PAGE_FURNITURE`,
`_pn_cite_short_names`, `_PN_URL_SPAN_RE`). Three rows from one batch, one
rule under them: a word inside a CASE NAME is a party of a published
decision, not of this case, unless the operator's own template names it —
at the owner's direction. "…71 Cal.App.5th 358, 373-374; Krongos v. Pacific
Gas & Electric Co." closed a page and its "(1992) 7 Cal.App.4th 387" opened
the next behind the firm's letterhead, so no tail was in reach and the
plaintiff was reported. The semicolon after a citation is how a string cite
is written, and a capitalised " v. " run after it is the next authority: the
seam (a year, a volume+reporter run or a `supra`, a pin at most, then ";",
one wrap allowed) is the anchor the tail would have been, for the mask and
for both halves of the write guard alike — still never both sides of this
case's own caption. A few short UNNUMBERED lines after a page header are
stepped over too, since the export prints a letterhead block that way, and
only there; the tail is still required, so the hop admits nothing alone.
"(Sanders, supra, 119 Cal.App.2d at p. 365.)" declares "Sanders" the short
name and "Sanders is instructive" two lines down was reported as a slip of
a tracked party: the bare short name is masked throughout, EXCEPT a word of
a value this case tracks, because `_surviving_records` reads through the
mask and a real party sharing a cited decision's name must stay reportable
where it survives (`_tracked_real_words`); a space before the `supra` comma
is tolerated. And the authorities appendix this tool writes spells every
cite out again in its verification link ("scholar?q=Angle%20M.%20v."), where
the plaintiff blanked in the cite stood as a word between "=" and "%" — the
fuzzy sweep skips every tier's candidate inside a URL token. The shape's
names now also feed `_pn_authority_cite_index`, so `prune_authority_party_terms`
drops a harvested bare "Sanders" as it drops Angela White, the fake pool
avoids the word, and a row that survives names the decision in Notes.

**…but a cite with NO TAIL in reach may not cross a PAGE BOUNDARY**
(`_PN_CITE_NAME_RUN_SAMEPAGE`, `_PN_PAGE_SEAM_RE`, `_PN_CITE_TAIL_WS`). Every
other branch of `_PN_CITE_SHAPE_RE` is bounded by a TAIL — a year or a
volume+reporter run that says where the cite ends. The `strung` branch has none
by construction: it exists for the cite whose year sits on the NEXT page behind
the firm's letterhead, and it is bounded by a word count and nothing else. So
at a page break it simply ran on into whatever the export printed next, which
in a delivered folder was the attorney roster at the top of the following page:
`Ferrers v. Coastal Gas & Electric Co.` closing page 15 swallowed
`<attorney>, Esq.` off the top of page 16 and read the attorney as the cited
defendant.
**Both sides of the mirror then failed, in opposite directions, off that one
run.** `_in_authority_context` REFUSED to fake the name — a " v. " to its left,
no year to its right, a string-cite seam behind the " v. ", which is the branch
that claims a defendant whose tail is out of reach. And the citation MASK
blanks exactly that run, so `_surviving_records`, which reads the masked body,
could not see the name at all. A real attorney's name shipped in the clear on
every page of two exports and no leak was reported — and where the mask's span
came from the PARSER rather than the shape pattern, the same value was reported
as a leak that no `--fix-leaks` pass could ever clear, because every pass runs
that same `_substitute`, refuses it again and re-reports it. The folder can
never resolve; the operator marks the row `yes` and watches it come back.
Three things close it. The page-FURNITURE hop moves to the TAIL alone
(`_PN_CITE_TAIL_WS`) — it was added so a year behind a letterhead could be
READ, and in the NAME RUN's own separator it let the name continue through that
letterhead. A tail-less run is held to ONE PAGE, in the pattern and in both
halves of the write guard, the " v. " between its names INCLUDED
(`_PN_CITE_V_SAMEPAGE`) — it shipped with the name runs held and the " v. "
still free to hop the header, so a strung cite whose " v. " sat at the seam
matched across it, the plaintiff's half of the guard refused it while the
defendant's half and the mask admitted it, and the mask blanked the page
header itself: stacking a guess about where a tail-less cite ends
on a guess about a page break doubles the ways it can be wrong, the discipline
`_pn_term_is_breakable` already states. And `set_page_context` writes the
export's OWN page header at the seam instead of a bare newline — it reasoned
that a page break is a line break, which is true of the wrap and left the write
guard unable to SEE a page boundary at all while the read side, working on the
finished export, sees every one of them; two sides of one mirror answering the
same question about differently-punctuated text is how this class of failure is
born. A TAILED cite still crosses a page freely (`_PN_CITE_WS` keeps its header
hop, so `Berryman v. Merit Prop. Mgmt., Inc.` closing page 3 is still protected
by its `(2007) 152 Cal.App.4th 1544` on page 4), and a strung cite on ONE page
keeps its defendant. Residual, and stated: a strung defendant whose name is
itself split by the page break loses its shape span there, which costs a review
row and never an authority.

**A cited decision is never renamed through its SHORT FORMS, and the harvest
never reads a citation's name** (`SUPRA_RE`, `find_supra_citations`,
`_pn_cite_short_phrases`, the short-form rule in `_protected_citation_spans`,
the citation mask in `_pn_learn_from_text`). A delivered batch kept every
full cite of "RGC Gaslamp, LLC v. Ehmcke Sheet Metal Co., Inc. (2020) 56
Cal.App.5th 413" byte-identical and shipped every "RGC Gaslamp, supra",
every heading naming the case and every bare prose mention with the first
word replaced by a pool fake — eleven times across three briefs. Three things
compounded. The comma-led corporate-suffix harvester read both sides of the
cite as this case's parties. The supra resolver admitted ONE capitalised word
before ", supra" and keyed the full cite on its first word, so "RGC Gaslamp,
supra" captured "Gaslamp", the cite was keyed on "RGC", the two never met,
and `prune_citation_only_terms` — which asks whether a value stands anywhere
OUTSIDE a citation — found it standing in an unresolved supra and kept it.
And the write guard protected only what the parser returned. Closed at three
seams. `SUPRA_RE` admits a run of up to four capitalised words and the
resolver matches every suffix of the run against the LEADING WORDS of each
full cite's name, longest first, so a lead-in the run swept up ("See RGC
Gaslamp, supra") is walked past and the span is cut back to the words that
resolved. The write side protects a declared short form wherever it stands
BARE — the phrase, and its first word alone, as the mask already blanks it
for the review tiers — except a word of a value this case TRACKS
(`_tracked_real_words`, the mask's own exception), so a template party
sharing a cited decision's name is still scrubbed. And the harvest input is
run through the citation mask at `_pn_learn_from_text`'s choke point, beside
the table-of-authorities and docket-code masks and for the same reason: a
name harvested off a cite is never a party of this case, and a real party
sharing the name is reached by the caption, the template and every role
anchor. Two belts found on the way. The tail-less defendant half of
`_in_authority_context` protected ANY name within its window of a strung
" v. ", across a lower-case word and a full stop ("Kremerman v. White again.
Helen Rasho"), while the mask's strung branch is a name run — so the party
shipped in the clear with the leak tier silent; it now requires nothing but
party name between the " v. " and the candidate. And the whitelisted
verification-link spans `_substitute` refuses were handed to neither cure
(`scrub_welded`, `scrub_survivors`) nor the reduced scan, which is how the
appendix's `scholar?q=Posner%20v.%20Grunwald-Marx` came to be rewritten; all
three take them now.

**The party template is filtered to THIS folder's docket**
(`_pn_folder_casenos`, `_pn_terms_from_xlsx(folder_casenos=…)`). An E-Court
export is a CALENDAR: a sheet listing several matters, or last week's export
for a different matter still in Downloads, and it was read whole — every
sheet, every row — so a delivered key carried twenty-five real values from a
stranger's lemon-law case, pinned `no match` on every re-run (the template is
an authoritative source), and one of them faked a CITY in a letterhead.
Where the sheet names MORE THAN ONE docket, only the rows naming a docket this
folder's documents carry (read by shape off the first two pages of each PDF,
canonicalised as `_pn_fake_caseno` seeds) are taken, a row naming none in
such a sheet is dropped as ambiguous, and a multi-matter sheet naming none of
this folder's dockets is refused whole and said so. A sheet naming one matter
or no docket at all is read as it always was, and a multi-matter sheet in a
folder whose docket could not be read is taken whole with a warning.

**A "Declaration of …" capture that reads as a STATUTE is not a declarant**
(`_pn_declarant_reads_as_statute`, `_PN_CODE_NAME_RE`). A county recorder
stamps a recorded lien "Declaration of Exemption From Gov't Code § 27388.1
Fee"; the anchor took "Exemption From Gov't Code" as a person, minted seven
initial variants, and rewrote the stamp on every copy. A code name in the
capture, a section sign in it or hard after it, or a last word that is a
generic token says statute. **A captured name's own trailing stop ends it**
(`_clean_name`/`_clean_tail` in `register_court_names`): "Judge Allison
Mackenzie. Dept 55" bound the judge twice, once with the period.

**A worksheet `yes` is screened before it mints** (`_pn_vocabulary_screen`,
`_pn_original_texts`, `_pn_prefill_canonical`). A blanket `yes` down an
OCR-heavy worksheet minted "Pay", "Enhanced Sealing", "Projection", "TRANS"
and a dozen OCR fragments as PEOPLE, so "PAY CASH" and a contract's line
items came back carrying surnames. `--fix-leaks` reads the originals FIRST
now and refuses a `yes` whose every word the documents write in lower case at
least as often as capitalised (`prune_prose_word_terms`' rule, asked of the
operator's answer), or that is a lone all-caps token of four letters or fewer;
a refused row is named, stays on the worksheet, and takes a typed replacement
or a `*CANONICAL`. And a `yes` typed over a PRE-FILLED misspelling row is the
alias it was pre-filled with: the Notes cell still names the canonical, so the
row binds as a slip of the tracked name and never as a fresh person. A CLI
`--term` is untouched — it is the operator's explicit instruction. Residual,
stated: a vocabulary word the documents only ever capitalise ("Enhanced
Sealing" as a line item) passes, since without a dictionary the corpus is the
only screen.

**An export of NO source document is named, and a stale copy is left alone**
(`_orphan_exports`, `skip` on the combined writer). An export is named for
its source's scrubbed stem, so one an earlier run wrote under an earlier
key's fakes matches no source once the key has moved on; a delivered batch
carried such a file — a byte-level duplicate of a live export under a
stand-in no key row mapped — and the `--fix-leaks` sweep re-scrubbed it into a
second generation while the combined file carried both. Every orphan is named
at WARNING; only an orphan that is also a near-copy of a live export (nine
lines in ten shared) is treated as stale — neither swept by `--fix-leaks` nor
combined — since an export whose name moved because the operator retyped a
key row is still the only copy of its document.

**Three matching gaps, each a shape a bound value shipped in.** A street
wrapped around an OCR stray line ("2000" / "lf" / "Riverside Drive, Los
Angeles") — number and street two lines apart — was matched by nothing and
reported by nothing, on three proofs of service; `register_addresses` now
also binds the street with its suffix standing alone (`address_street`), to
the same fake the address drew, since the number is the one part that
identifies nobody. A caption's "of" glued to the plaintiff by extraction
("ofQUILLMARK BUILDERS LLC") failed the full name's left boundary, so the
reduced cure fixed the first token alone and half a party shipped reading as
scrubbed; a name of two or more words may now open across a CASE FLIP behind
a lower-case word (`_pn_build_pattern(glue_left=True)`, `(?-i:…)` keeping
the flip case-sensitive under IGNORECASE), the left boundary otherwise
holding as the thing that stops a short name firing inside a longer word, and
`_lead_words` indexes the capitalised tail of such a word so the prefilter
still sees it. And a bound name token rewrote the LOCAL part of an address
the detector had not matched, so it shipped as `<fake-local>@<real-domain>`;
`scrub_emails` now rewrites a tracked domain on its own wherever the local
part beside it is one of this run's fakes.

**…and a cite WRAPS wherever the margin falls, and the guards read it as the
EXPORT prints it** (`_PN_CITE_WS`, `_PN_CITE_V`, `set_page_context`). On
pleading paper a citation breaks inside the plaintiff's name, around the
" v. ", between the defendant and the year — and the export keeps the gutter
number of the line it wraps onto, so the gap is "\n13  " and not a space; at
the foot of a page it is a blank line, the "====== Page N ======" header and
the next page's first gutter number. The shape guard joined name words on
HORIZONTAL whitespace alone, so it saw none of those cites, and every review
tier that reads through the mask took the plaintiff for an unscrubbed name:
"Martine v. Chippewa Enterprises, Ina (2004) 121 Ca1.App.4th" — the parser
blinded by the OCR'd reporter — was reported as a slip of a party named
Martinez, and "Gavina v. Smith (1944) 25 Cal.2d 501", which the parser reads
perfectly on one line, as a slip of a party named Gavin. Measured by wrapping
each of those cites at EVERY word gap, onto a numbered line and across a page
break: unmasked at every gap inside the name and before the year, now at
none. Each hop is bounded — one page header at most, a one- or two-digit
gutter number followed by the writer's own two spaces — so the relaxation
admits a wrap and not a new shape. `_PN_BEFORE_V_RE` takes the same
separator, so the plaintiff's half of the write guard survives the wrap too.
**And a page is scrubbed on its own, which a cite does not know.**
"[Berryman v. Merit Prop. Mgmt., Inc." closed page 3 and "(2007) 152
Cal.App.4th 1544" opened page 4, so on page 3 the defendant had a " v. " to
its left and no year or reporter in sight, `_in_authority_context` refused
it nothing, and the cited decision shipped as "Merit Ravenwood. Kaldor.,
Inc." — the invented authority the whole method is built to refuse, and
then the half-scrub tier reported the plaintiff standing beside our own
stand-ins. `build_body` now hands each page the unscrubbed tail of the
previous page and head of the next (`detect_pages`, indexed by
`block_pages` rather than by position), and `_substitute` asks the guard
about the page with its neighbours around it — the page's own text and
offsets untouched, a newline at each seam so a " v." closing one page still
reads as " v. ". `_surviving_records` needs nothing: it reads the whole
export, where both pages are one text.

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
- **An IMAGE on a page whose own text layer is FINE is still text nobody read**
  (`_ocr_image_regions`). OCR was an all-or-nothing PAGE decision and both
  passes below rightly decline such a page — one wants NO text, the other wants
  GIBBERISH — so an Order of Dismissal whose 1,300 characters extract perfectly
  said nothing about who signed it: "Alison Mackenzie / Judge" sat in a
  215x91 pt image and appeared nowhere in the document's text layer, in clean
  printed type (only the scrawl above it is unreadable). Same reasoning that put
  the out-of-band pleading text back — text nothing reads is text nothing can
  scrub, report, or show the reader — except that here it is the READER who
  loses, since an image cannot leak through a `.txt`. **ADDITIVE**, which is
  what separates it from `_reocr_garbled_pages`: nothing is redacted, no
  existing text is replaced, and the worst case is a wasted render. The filter
  is NEWNESS (`_image_ocr_new_words`) and needs no word list — a region is kept
  only when it carries words the page does not already have, so a logo's
  letter-soup offers none and a court SEAL is rejected too, because the caption
  it echoes is already in the text. Gated on size (`_IMG_OCR_MIN_PT`, below
  which no line fits, so nothing is even rendered) and on the page having text
  at all — a textless page belongs to `_ocr_pdf`, which gives it a WHOLE text
  layer rather than one image out of it. The page is banner-marked
  (`_IMG_OCR_ATTR`), because an inferred reading is never presented as equal to
  a read one.
  **…and a page ALREADY READ is not read again** (`_image_ocr_already_read`).
  Newness is the right question for a seal echoing the caption and the wrong
  one for a scanned exhibit that arrives with its FILER'S OWN OCR layer over
  it — the commonest scanned exhibit there is. There the page's text IS the
  image's text, so the only words this pass can find that the page "lacks" are
  the handful the two engines read differently (`foregolng` for `foregoing`,
  `lnterested` for `interested`), which clears `_IMG_OCR_MIN_NEW` on any page
  of prose. The overlay then lands a SECOND reading of the whole page on top of
  the first and every word is exported twice: measured on a declaration of
  service, 23 words became 46. It is the same shape `_drop_overdrawn_spans`
  exists for and it slips past that too, because the two readings differ in
  their text and their span geometry, which is exactly what that pass refuses
  to collapse. So the second rule is scoped to the RECT — a seal's words are
  echoed elsewhere on the page and there is nothing underneath it, while a
  re-read scan's words are already exactly where this is about to put them
  again — and each rule answers its own failure. It also makes the pass
  IDEMPOTENT, which matters because the tool replaces the source PDF: the
  overlay is in the file the next run opens, and until now nothing but our own
  OCR being deterministic stopped a re-run stacking another copy.
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
**…and the hook has to survive the death it is reporting.** Formatting a
traceback ALLOCATES — logging re-reads the source lines to print them — so on
the one failure a big folder is most likely to hit, running out of memory, the
rich report raised a second `MemoryError` INSIDE the hook, the best-effort
`except Exception: pass` swallowed it, and the process exited having written
nothing: a log ending mid-file and no python left in Task Manager, which is the
exact silence this exists to break. The FIRST thing written is now a fixed line,
encoded at install time and pushed straight at the log file's descriptor with
`os.write` — no formatting, no allocation, one syscall — and only then is the
traceback attempted. The raw line names OUT OF MEMORY where that is the cause,
because it asks the operator to do something different (a 32-bit Python is
capped near 2 GB however much the machine has; split the folder or move to a
64-bit one) from "some exception". Note what this still cannot catch: a run the
OS kills outright leaves no line at all, which is why the long phases time
themselves — see the performance notes.

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
## A folder an older version CONSOLIDATED

An older version measured `Text Files` against a **20-file upload cap** and
folded the excess into single `COMBINED …` exports, each holding several
documents behind DOCUMENT banners. That is gone at the owner's direction — a
better answer to the same problem was found outside this tool — and with it the
`max_text_files` setting, the two grouping rules, the reproduce-the-previous-
grouping record, and the leak-gate bookkeeping that had to be remapped onto a
combined file. A `max_text_files` line in a config file people already have is
simply ignored now; `_config_add_missing` never removes what it did not write.

**What is left is the folder it left behind.** A combined export is named for
nothing in the case (`COMBINED 5 documents.txt`, `Brief (COMBINED 3 parts).txt`),
so no source PDF maps to it and a full re-run does NOT overwrite it — it would
sit in `Text Files` beside the freshly-written per-document exports as a stale
duplicate of text already delivered under other names, and get uploaded with
them. `_drop_superseded_combined_exports` removes one (and a combined
`*.txt.LEAK` quarantine) once EVERY document named in its banners has a separate
export in that folder again — the same supersede rule the combining pass applied
to its own output, and the same reasoning as `_pn_drop_superseded_quarantine`.
Run over the deliverable folder and over the `Original Text` reference copies,
because the old pass combined both; and run BEFORE the leak worksheet and the
gate, so what those two measure is exactly what will be delivered.

**NOT before every member is covered**, which is the whole care in it: a member
whose source PDF is gone (removed from the folder, or failed this run) has no
other copy, so that file IS the only copy of that document and stands as an
ordinary export, untouched. `_combined_sections` (the banner reader) and
`_pn_locate_export` survive for the same reason — until such a file is
superseded it is a real export, and a leak found in one still has to be located
by its member document, since every document in it numbers its pages from 1.

**A combined file is back, OPT-IN and ADDITIVE, and it is not that feature**
(`combined_text` in the config, `_write_combined_text`,
`_combined_text_after_run`, `_COMBINED_TEXT_NAME`). The consolidation
REPLACED exports to fit a cap; this writes ONE more file, `Combined Text.txt`,
holding every export in the text subfolder in full behind the same DOCUMENT
banners (so `_combined_sections` and `_pn_locate_export` read it unchanged),
and the individual exports stay exactly as they were. It lives in the CASE
FOLDER and not in `Text Files`, at the owner's direction and for the reason
`Authorities Cited.txt` does: that folder is the set of per-document exports,
and a file holding all of them again beside them would upload the batch twice.
It is built from the exports AS DELIVERED, on disk, after the leak gate — a
`*.txt.LEAK` is never a member, and while one is held the file is withheld and
a stale one removed, for the reason the copy waits: a combined file missing a
document reads as complete, and one carrying the leak is a second copy of it
outside the quarantine. `--fix-leaks` writes it when the last leak is released,
the unreversible-fakes gate holds it the same way, and turning the setting OFF
removes a file an earlier run wrote (recognised by its own header mark, so a
file of the operator's is never touched). Byte-stable — no timestamp, name
order case-folded, rewritten only when the content differs — and
`_is_tool_txt_artifact` knows its name, so under the older single-folder
layout `--fix-leaks` never scrubs it as an export or folds it into itself.

## Performance notes

- Term/record regex patterns are **compiled once** per run via a
  `Pseudonymizer._compiled` cache — Python's own re cache caps at 512, so a
  large case recompiled every pattern on every page (was ~75% of the scrub pass).
- Files are processed **heaviest-first** by OCR-weighted cost; the one-click
  re-run launcher is written **up front** so an interrupted run still leaves one.
- **Nothing on the leak path may be QUADRATIC in the document, and one line
  was.** A 130-page motion spent 82 minutes inside one file's scrub-and-scan
  block, wrote nothing to the log the whole time, and the run then stopped
  there — indistinguishable from a hang, and reported as one. Profiled on that
  folder's shape (a few hundred terms, 220 master KEEPs) **19 of every 24
  seconds** were in `_in_name_run`, which searched `text[:s]` for a
  `$`-anchored match: every occurrence of a soft keep COPIED the export so far
  and made the engine scan the copy. The master sheet keeps ordinary
  vocabulary — "and", "the", "of", "court" — so a long filing carries thousands
  of occurrences and the product is the document squared. It now walks the two
  neighbours by INDEX (`_PN_NAME_RUN_RIGHT_RE.match(text, e)` and a backward
  scan reproducing the regex's leftmost match, punctuation-opened runs and
  `$`-before-a-trailing-newline included), so the cost is one word.
  Three cuts beside it, all exact. `_PnSpanIndex` answers "does any of these
  spans overlap [s,e)?" by bisect over sorted starts plus a running maximum of
  the ends — four passes asked that ONCE PER MATCH against a whole-export span
  list (the party matches a keep yields to, the kept spans a finding is filtered
  by, the citation spans `scrub_welded` and `_substitute` refuse to touch), so
  each was a product of two numbers that both grow. `_surviving_records` — the
  most expensive thing on the path, every tracked value scanned across the whole
  export, asked for FOUR times per file — is memoized and now stops at the first
  match that SURVIVES the filters (`finditer` is lazy; membership is decided by
  the first survivor). `_keep_spans` and `_mask_protected_citations` memoize
  **two** entries, not one: the block alternates between the export body and its
  column-ordered twin, so a single slot was evicted before it was ever read.
  Every one of these memos keys on `_scan_state_key()` and not on the text
  alone — `--fix-leaks` sets the keep sets on a live `Pseudonymizer` and asks
  the same question again, and sizes are not a fingerprint, so a length-only key
  answers from before the operator's decision. Measured end to end on a 381 KB
  body: **274 s → 25 s**, with the quadratic term gone (`test_scan_cost.py`
  pins the shape, and the two rewritten primitives against the code they
  replaced).
- **A per-value quote must not re-read the document per value**
  (`_pn_context_prep`). `_pn_context` computed `off = len(" ".join(joined))` on
  every line — re-joining the whole export per line, quadratic in it, the same
  shape as `_in_name_run` — and then re-derived the line table, the prose flags
  and the sentence-terminator list for EVERY value asked about the same body.
  A 290 KB export cost **82 ms per value**, of which the search itself was
  0.04 ms. Split into a TWO-entry memo keyed on the parsed body's identity
  (two for the reason `_keep_spans` memoizes two: the quoting loops now
  alternate between a file's original body and its scrubbed twin — the two
  Context columns — so a single slot would be evicted before it was read),
  with a running offset and bisected terminator windows: **446x faster**, byte-
  identical on a 148-value differential test (headings vs prose, absent values,
  multi-word phrases, the empty string). That is what makes a Context column on
  the KEY affordable at all — 335 rows went from 28 s to 0.06 s per file, 1,042
  rows from 87 s to 0.19 s — and it repays itself on the LEAKS column that
  already existed.
- **A term is scanned for only where its first word stands**
  (`_pn_term_lead`, `Pseudonymizer._lead_words` / `_leads_present`,
  `_PN_LEAD_CATS`). Four passes each ran every term's regex over every page —
  the substitution, the keep-span party check, the survivor scan and the
  key-context quoting — and a case with 210 names is 2,164 terms once the
  near-miss variants are minted, so a 130-page filing paid 2,164 regex scans
  a page four times over: profiled at 276 s for one 413 KB export, of which
  a tenth was the scrub itself. A name term matches WHOLE WORDS joined on
  whitespace, so wherever its pattern can match, its first word stands in the
  text as a word — or, for a break-tolerant name, as two adjacent pieces that
  JOIN to it. The page's words plus every adjacent pair joined is therefore
  an EXACT prefilter: a term whose lead word is absent cannot match, and the
  regex still decides every term that passes. Measured at 8 percent of the
  terms on an ordinary page, 11x faster on the scan, and pinned differential
  against the unfiltered scan (`test_scan_prefilter_equivalence.py`, which
  switches it off through `_PN_LEAD_PREFILTER` to obtain the reference).
  Name categories only (`_PN_LEAD_CATS`); a case number, an address or an
  identifier keeps the full scan, and a weld-follow term ("SmithDecl.") has
  no lead, since it may butt against its kept text. Four exact cuts beside
  it, from the same profile. `_protected_citation_spans` compiled and ran
  one "P v. D" regex per CITATION rather than per distinct case name, and
  appended every occurrence that many times: 716 cites of two decisions made
  257,044 spans where 1,432 were distinct, 8.8 s where 0.15 s was the work,
  and every downstream span index carried the duplicates; it is now one
  regex per distinct name, distinct spans, and memoized on (text, scan
  state) since the full export is asked about half a dozen times per file.
  `_substitute` walked every chosen span per candidate to find an overlap
  (41 million comparisons); the chosen spans are disjoint by construction,
  so it is a bisect. `_pn_word_is_own_fake` walked the whole set of known
  fakes per word for the welded-fake substring test (17 million walks), and
  now asks one compiled alternation. And `_pn_ocr_distance_within` refuses
  a pair on the LETTER-SET floor before building the table: a letter one
  word has and the other lacks costs at least 0.5, and no edit mends more
  than two, so half the symmetric difference is a bound on the distance —
  96 percent of the sweep's pairs stop there, and the randomized
  differential test pins that the bound never refuses a pair the full
  distance admits. The Context search runs once over the JOINED lower-cased
  body with `str.find` and a boundary test instead of a `(?<!\w)` regex per
  line, because a pattern opening on a lookbehind forfeits the literal-prefix
  scan (3 ms a row against 0.1 ms). The profiled file went from 276 s to
  65 s with the same output; what remains is the citation parse per page and
  the fuzzy sweep, which are the next two.
- **The long phases NAME themselves before they run** — the same rule the
  pre-scan follows for filenames, and for the same reason. Between "exporting
  text" and the first REVIEW warning the log said nothing for 82 minutes, so a
  reader could tell neither where the run was nor whether it was moving. The
  scrub and the leak scan each announce themselves and then report their
  elapsed time; a line written afterwards is a line never written when the
  interpreter dies.

**A Context cell BOLDS the value it is quoting** (`_pn_rich_context`, an
openpyxl `CellRichText`). The cell is a whole sentence and the value is a word
or two inside it, so finding the value means reading the sentence — bolding it
makes the row answerable at a glance, which is the column's entire job. Only the
QUOTE is styled: in the Value column beside it the value IS the cell, so
emphasis would say nothing. Every occurrence, matched case-insensitively and
emitted with the document's own casing (a caption shouts a name the Value column
spells in title case). DERIVED at write time from (quote, value) and never
stored, which is what makes it survive the two round-trips that matter: a quote
carried forward from the key on disk reads back as plain text and is re-bolded
next run, and `DeAnonymize.bas` — like anything not asking for rich text — sees
the ordinary sentence. Falls back to plain on an older openpyxl or a value
absent from its own quote (a welded or reduced finding, whose quote is the
nearest readable sentence rather than one containing the value verbatim): an
unbolded cell is a cosmetic loss, a raise would cost the operator the worksheet.

**Every spreadsheet the tool writes WRAPS its text** (`_pn_wrap_sheet`, shared
by the key and its pinned sibling, `LEAKS.xlsx`, and the master's KEEP and tally
tabs — shared for the reason the two launcher builders are, so they cannot
drift). All four now carry a cell that is a SENTENCE (the two Context columns,
Notes, the accumulating Cases list), and Excel's default spills a long cell
across its empty neighbours then clips it the moment one is occupied — so the
column the operator is meant to READ was the one they could not, without
widening it by hand on every workbook. Vertical TOP with it, or a four-line
quote sits centred against the one-line value it explains. Column WIDTHS come
with it (`_PN_KEY_WIDTHS`, the third field of `_PN_LEAK_COLUMNS`), in Excel's
unit of character widths: Real Value / Replacement and the LEAKS Value at 30,
Context at 120 (the width a sentence needs), and Fix? at 10 — room for its
longest control word and no more. Fix? also accepts a full typed replacement,
but that is the exception, and sizing the column for it spent 30 characters of
screen on every row to show "no"; a long one still shows, over two lines, in a
row Excel grows to fit. Row HEIGHT is
deliberately left unset: Excel auto-fits a wrapped row when no explicit height
is stored, and a height written here would freeze the layout at this machine's
font metrics. Costs 0.11 s on a 523-row key.

## Folder artifacts (what a finished folder should contain)

**`Authorities Cited.txt` lists what the PARTIES cited**
(`_write_authorities_list`, fed by `_note_authority`). It sits in the CASE
FOLDER and deliberately NOT in `Text Files`: that folder is the deliverable
that goes to the drafting model, while this is a work product for whoever reads
the papers, so it belongs beside the PDFs and the key. Real citation text, because published authorities are public record
and the whole pipeline preserves them byte-for-byte precisely so a cite is never
renamed; a list that scrubbed the names it exists to report would be useless.
Grouped by kind (cases / statutes / rules). **CASES run in YEAR order, MOST
RECENT FIRST** (`_authority_year`, reading the `(YYYY)` through the same
`_PN_AUTHORITY_YEAR_RE` the fake-pool screen uses, so there is one definition of
a citation year): a year is what a reader places a case by, and the newest
authority is the one most likely to state the current rule and least likely to
be already known — while alphabetical says nothing, since the first word of a
case name is one party's surname. A cite with no year sorts LAST and NOT as year
zero, which under a descending sort would put it at the TOP as though it were
the newest, so one bad parse never displaces the sequence. Statutes and rules stay alphabetical; they have no year and a code
section is read by its number. **An entry is the citation and nothing else.** The
citing documents and a mention count used to sit under each, and both were
dropped at the owner's direction: the file answers "what did the parties cite",
and a count reads as a claim about how heavily an authority is relied on that the
number cannot support — one cite in a controlling passage outweighs six in a
string cite. `_note_authority` therefore keeps no count at all (a tally nothing
reads is a number the next reader takes on trust); it still keeps the DOCUMENTS,
because the header's "across N document(s)" is context for the list rather than a
claim about anything in it.
A short form and a `supra` FOLD onto the full cite they repeat (same `key`), or
the file would be a list of mentions rather than of authorities. Collected as a
side effect of the parse `_build_authorities_appendix` already pays for, so it
costs no extra citation pass; the Word path has no appendix and asks directly.
Rewritten whole every run and REMOVED when a folder cites nothing, so it never
describes a batch that has moved on, and it carries nothing volatile so an
unchanged folder reproduces it.

**A launcher RESOLVES its paths when it is clicked, and says so when it
can't** (`_launcher_resolve_bat` / `_launcher_resolve_sh`). A launcher records
the absolute interpreter and script paths of the machine that wrote it, and
`copy_to` now sends the folder to a synced destination precisely so the case
can be worked from the other machine — where Python and the tool may sit
somewhere else entirely (a different user profile is enough). So each launcher
tries the recorded path first, since it is right on the machine that wrote it,
then falls back to the PATH (`pythonw.exe` / `python3`). And when the TOOL
itself is not on that PC, the launcher writes one line into the folder's own
`pdf_linker.log` and exits: `start` on a missing target flashes a window nobody
can read, which is indistinguishable from a double-click that did nothing — the
failure `_install_crash_logging` exists for, arriving one level further out. It
is the only `echo` in either launcher and it is redirected to that log, never to
the screen.

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

**A run can be DEFERRED to a launcher, for the folder that is about to MOVE**
(`defer_run` in the config, `--defer`/`--no-defer`). ON means starting the tool
on a folder does not process it: it writes `Run PDF-Linker.bat`
(`_write_deferred_launcher`) and stops, so the operator can put the folder
where it belongs and start the work at its destination with one click — the
launcher targets its own directory (`%~dp0`), which is what makes it survive
the move. Its own name is the state of the folder: `Run` while nothing has been
processed, `Re-run` afterwards, and `_write_rerun_launcher` drops the deferred
one the moment the run it promised begins (`_remove_deferred_launcher`, AFTER
the replacement is on disk, so a folder is never left with neither).
`_write_start_launcher` is the one place that decides WHICH of the two a folder
should carry — refresh the `Re-run` one where it exists, else write the `Run`
one — so deferring a folder that has already been run never adds a second file
saying the opposite about it.
**Both** launchers pass `--no-defer`, and that is the rule the feature stands
on: a double-click IS the operator asking to run this folder NOW, so under
`defer_run = on` a launcher without it would only rewrite itself and exit — the
deferral could never end, and nothing in the folder would process it. (It also
re-arms a launcher written before the flag existed.) `--fix-leaks` is never
deferred either: an operator who typed it is asking for that pass now. The
check sits after the PyMuPDF one, so a machine that cannot do the work says so
BEFORE the folder is moved, and the launcher is written even for a folder
holding no documents yet — deferring is *for* the folder that is not ready.
Both writers go through `_write_launcher_file`, and unlike the re-run
launcher's best-effort furniture a failure here is the failure of the run
(exit 1): it was the only thing the run was going to produce.

**A finished folder can be COPIED to where the case lives** (`copy_to` in the
config, `--copy-to`/`--no-copy`, `_copy_folder_out`). The destination is a
PARENT: the case folder itself and everything in it is copied in as
`<copy_to>/<folder name>`. Files are OVERWRITTEN and nothing already in the
destination is deleted — that folder is where the operator works, so a draft
beside the copy is not this tool's to remove; the accepted cost is that a file
deleted from the case folder stays behind in the copy. Per-file errors are
counted and survived rather than aborting the copy (a workbook open in Excel is
the usual one, and losing the other 40 files to it would be absurd).

**WHEN it is copied is the whole design, and it follows `defer_run`.** The
destination is read from the config at the START of each run, so adding or
editing `copy_to` after a folder has been processed places the copy at the end
of the next run — which is how the setting is normally adopted, since the
folder is usually already done by the time the operator thinks of it. With
deferral OFF the copy is made LAST, so it carries the exports, the key, the
worksheet and the DONE stamp — the folder as the operator would find it — and a
re-run copies again, which is how a correction reaches the destination. With
deferral ON the copy is made FIRST, before anything has been processed.

**BOTH folders end up with a launcher, and that is deliberate.** The
destination is a local folder that SYNCS (a OneDrive one), so the copy is how
the case reaches the operator's other machine: whichever one they are sitting
at has to be able to start the run. A deferred start therefore writes the `Run`
launcher here AND in the copy, and every completed run leaves a `Re-run`
launcher in both — the copy inherits the source's (it is written before the
copy is made) and `_arm_copy_launcher` writes it again at the destination,
because a folder that was a deferred target earlier still carries the `Run`
launcher from THEN, and only one of the two names can be true of it. Two
launchers cost nothing because each runs the folder it SITS IN (`%~dp0`), so
they never touch the same files; and if both are eventually run the fakes do
not diverge — they are seeded on the real values, so the same documents and the
same party list mint the same key on either machine. An earlier version wrote
the deferred launcher only into the copy, to keep exactly one folder runnable;
that is the opposite of what a synced destination is for.

**A copy that cannot be made is just a run with no destination.** It falls back
to precisely what `defer_run` alone would have done — the source keeps its
launcher, the deferral still works, the log says what failed — rather than
failing the run. (It once exited 1 on the ground that the launcher had gone
into the copy and nothing was left here; with a launcher in both folders there
is nothing to abandon.)

**A held folder is not copied.** A run that quarantines an export has decided
the folder is not deliverable, so `_copy_folder_after_run(hold=…)` names what is
holding it and defers: the destination must never receive a `*.LEAK`, and
copying one would invite the operator to work from a folder the gate is holding.
`--fix-leaks` makes the copy at the end of the pass that releases the last leak
— including at its early "nothing applied" return, where the hold is reported
rather than silently skipped. The unreversible-fakes gate holds it the same way.
A folder that IS its own destination is returned unchanged and never copied onto
itself (that is a re-run started inside the copy, which is how a launcher that
travelled with the folder keeps working), and a destination INSIDE the case
folder is refused outright — that walk never terminates.

**...and the COPY can be the folder that is AHEAD** (`_sync_back_from_copy`).
The destination syncs, so the case may have been RUN over there: deferred on
this machine, copied out, processed at the other one. Coming back to the source
folder afterwards, re-running it is the expensive way to obtain files that
already exist a folder away — so the start of every run asks whether the copy
finished a run this folder has not, and takes it back if it did. What happens
next is unchanged: a deferred start still just writes its launchers (and skips
the push, since it took those files a moment ago and has processed nothing
since), and a full run still runs, now reusing the key that came back with the
files — so the fakes are the ones already delivered — and picking up any
document this folder has and the copy does not.
The evidence is the markers the runs themselves leave (`_marker_mtime`, scoped
to zero-byte files exactly as `_clear_eta_markers` is): a `DONE <clock>.txt`
stamp means a run finished there, and an `ETA …` marker written AFTER it means
one started and has not — running now, or dead part-way — which is not a state
to take. `_COPY_AHEAD_MARGIN` is for the clocks: `shutil.copy2` preserves
mtimes, so a copy this folder pushed carries this machine's own stamp and reads
as exactly equal, and only a run that finished meaningfully later counts as
ahead. Skew is the residual and fails safe one way (a slow clock over there
means no pull-back at all).
**Nothing is overwritten that this folder holds a newer version of**
(`_pull_back_from_copy`), which is the whole safety of reaching into a case
folder from outside a run: the operator may have typed Fix? decisions into this
folder's `LEAKS.xlsx` since, and those are irreplaceable — the copy's version
has none of them. Nothing is deleted either, so a document that exists only
here survives the sync and is processed by the run that follows. The stale
local run stamp IS cleared first, because the copy's is coming with it and two
stamps in one folder say two different things about one run.

**The party spreadsheet travels with a DEFERRED copy** (`_copy_party_template`).
The launcher names no spreadsheet, so the run at the destination resolves its
own: the folder first, then "the newest `Order*.xlsx` in Downloads". That
fallback is right only until the NEXT case is downloaded — which is exactly the
window a deferred folder sits in, since the point of deferring is that the work
happens later — so the copy would be scrubbed against a stranger's party list:
this case's parties in the clear, another matter's names hunted for, and its key
written full of values that were never here. A template INSIDE the folder is
unambiguous and beats the guess, so copying it in is what makes the copy able to
do the full run. Nothing is copied when the folder already carries its own
inputs (`_pn_find_folder_key`, which now takes `log=None` for a caller asking
only WHETHER it does — one definition of that question, not two), and the
Downloads guess is withheld for an ALL-WORD folder exactly as the run withholds
it: there it would not merely be a guess but an AUTHORITATIVE one, since a
folder-local template wins.

**ETA accuracy is LEDGERED, because the marker dance destroys each prediction
at the moment its outcome becomes known** (`_note_eta_accuracy`,
`pdf_linker_eta_history.csv` beside the config — machine-wide, like the rate
files it audits, and gitignored like them). The rate files remember only the
LAST run's throughput; the ETA marker's name is the prediction and the DONE
stamp's name is the outcome, and writing the second deletes the first — so
nothing ever said whether the estimates were any good, or whether the 40:1 OCR
page weight is calibrated. One CSV row per run (full runs with 2+ PDFs, and
every `--fix-leaks` pass), appended: kind, folder, file count, work units
(OCR-weighted units for a full run, input bytes for fix-leaks), the seed rate,
the FIRST seeded ETA (grades the cross-run seed), the LAST mid-run ETA (grades
convergence), the actual finish, elapsed, the final rate, and the two error
columns in seconds — positive means the run finished LATER than predicted.
Append-only and best-effort: a ledger that cannot be written never costs a run.
Empty cells mean the run had nothing to predict with (first run, no stored
rate; single-file batch, no mid-run update) — they are not failures.

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

- **A new SETTING must reach the config file people already have**
  (`_CONFIG_BLOCKS`, `_config_add_missing`). The template was written once —
  when no `pdf_linker.config` existed — so every setting added afterwards was
  invisible to anyone who already had one, which after the first run is
  everyone: a real operator's file carried four settings while the tool had
  twelve, and the only way to discover `copy_to` or `defer_run` was to read the
  source. `_read_config` now tops the file up on every run, appending the
  blocks it does not MENTION (live or commented out — commenting one out is a
  decision, and re-adding it would undo that decision every run). APPENDED and
  never rewritten: their values, their ordering, their own notes and any key
  this version has never heard of all stay as they are. The template is
  therefore kept as one block per setting, with **exactly one setting line
  each** — that is what makes it safe, since a block can never re-set a key the
  file already carries, and the reader takes the LAST line for a key, so a
  default appended below would otherwise silently flip a value typed above (the
  `keep_original_text` / `original_text_subfolder` pair shared a block and would
  have done exactly that). `_CONFIG_TEMPLATE` is derived from the blocks rather
  than kept beside them. Safe to do MID-RUN because every default in the
  template equals the code's own fallback — the appended line describes what
  the run was already doing — and `test_config_topup.py` pins that invariant,
  so a new setting whose default disagrees with its code default fails there.
- **No real judge name in the repo** — court-personnel scrubbing is name-agnostic
  (discovered from the document); the fictional "Dana Whitaker" is used in tests/
  comments.
- **One invisible byte must never cost the KEY** (`_pn_xl_text`, applied at
  every sheet boundary). openpyxl refuses a C0 control character and a SCANNED
  exhibit supplies them: OCR read a Bates stamp as
  `EQUITY-WALTON_0007 - HOIISING<BEL>COMMl,/Nl't'Y`, writing it threw, and the
  ENTIRE reversal key was lost while the exports were written — pseudonyms
  nobody can undo, which this project treats as worse than a leak, reported as
  one "non-fatal" warning. Stripped rather than dropped: the character is
  invisible and came from a misrecognition, while dropping the row loses the
  binding. The handler now says outright that nothing can restore the names.
- **…and openpyxl's own net has TWO holes, which is why Excel kept offering to
  REPAIR the key.** A repaired workbook is not a cosmetic complaint: Excel
  repairs by DROPPING what it could not parse, and what it drops is reversal
  rows. (1) Its filter covers the C0 controls and stops there, but XML 1.0 also
  forbids the SURROGATES and U+FFFE/U+FFFF — written through verbatim, and the
  sheet part that comes out is not well-formed at all, so no reader can open it.
  The key's `Context` quotes the UNSCRUBBED body, which carries the garbled text
  layer of every page with a broken encoding (`_garbled_appendix`), so that is
  exactly the text producing them. `_PN_XL_BAD_CHARS_RE` strips precisely the
  illegal set and no more — U+FFFD, U+FDD0-U+FDEF and a plane-end non-character
  are legal `Char`s and stripping them would quietly edit the document. (2)
  openpyxl truncates an over-long cell for you in `Cell._bind_value` and SKIPS
  that step for a `CellRichText` (`elif dt == "s" and not isinstance(value,
  CellRichText)`) — which is what the Context column is, so nothing enforced
  Excel's 32,767-character cell. Both are cut in `_pn_xl_text`, where a plain
  cell and a rich one both pass, rather than relying on a library step one of
  them never reaches. (3) DEL and the C1 controls (U+007F-U+009F) are inside
  XML 1.0's `Char` production, so neither filter touches them and the file they
  land in is well-formed — `_pn_xl_verify` reads it back happily. Excel never
  writes one raw; it escapes a control character as `_xHHHH_`. Same author as
  (1), a broken ToUnicode, and the same trade: the character is invisible and
  came from a misrecognition, while the row is a binding.
- **…and the RICH text Excel reads differently from openpyxl.** Two shapes,
  both in the `Context` column, both silent. openpyxl's `whitespace()` helper
  tests the STRIPPED text for truthiness, so a run that is ALL whitespace is
  written without `xml:space="preserve"` and Excel drops its text: a quote
  using the value twice in a row ("Rasho Rasho performed") came back with the
  words run together. `_pn_rich_context` folds such a run into the bold one
  beside it, where the attribute is not needed and bolding a space shows
  nothing. And the bold span was located with `str.lower()`, which is not
  length-preserving — "İ" lowers to two code points — so an index taken in the
  folded copy and used to slice the original walked off by one and bolded
  "asho " of "Rasho"; the search runs through the regex engine on the original
  instead.
- **The recovery log names a PART, never a cell, so the run says which cell**
  (`_pn_xl_audit`, called from `_pn_xl_save` after the read-back). Five causes
  of "Excel found a problem with some content" have now been diagnosed from
  nothing but `Repaired Records: String properties from /xl/worksheets/
  sheet1.xml part`, and every one was a shape openpyxl passes through and
  writes without complaint — so `_pn_xl_verify` cannot see them either: it asks
  whether the file can be READ, and all of them read back perfectly. What was
  missing was not another guard but a WITNESS. The audit walks the SAVED XML
  with Excel's own rules — a cell's total text against 32,767 (a rich cell's
  runs SUMMED, the count Excel applies and openpyxl never makes), the control
  characters neither filter removes, a run that would lose its text to the
  missing `xml:space`, an empty run — and names sheet, cell and reason in
  `pdf_linker.log`. It REPORTS and never repairs or raises: a cell Excel would
  quietly fix is not worth discarding a key over, and the loud failure
  `_pn_xl_save` reserves for an unreadable file has to keep meaning that.
  **It reads the sheet's FURNITURE as well as its content**, because the fifth
  cause was not a cell: a witness blind to the part the next cause comes from
  is not a witness, and this one cost another round of inference for exactly
  that reason. So the walk also holds every `dataValidation` to Excel's own
  limits (below), naming the sheet and the range instead of a cell.
- **A DATA VALIDATION is held to limits three orders of magnitude smaller than
  a cell's, and the Fix? dropdown outgrew them**
  (`_pn_xl_fit_validations`, `_PN_XL_DV_TEXT_MAX` 255 / `_PN_XL_DV_TITLE_MAX`
  32 / `_PN_XL_DV_LIST_MAX` 255). `LEAKS.xlsx` puts a yes/no/never dropdown on
  its Fix? column and hangs the explanation of every control word off it as the
  validation's input message — so that sentence grows by a clause each time a
  control word is added, and documenting `*OTHER VALUE` took it from 181
  characters to 291. Excel repairs a workbook whose validation is over the
  limit by DROPPING the validation, so the operator opens the worksheet they
  are meant to type decisions into and the one statement of what may be typed
  is gone, behind the repair prompt. Nobody wrote a long string; a feature
  added a clause — which is why the belt is a CUT at the one save boundary
  every workbook passes through, beside `_pn_xl_plain_cells`, rather than a
  rule about how to word a prompt. Cut and not refused: losing the sentence's
  tail costs the reader a clause where dropping the validation costs them all
  of it. The authored text is kept comfortably under the limit anyway
  (`test_leaks_excel_repair.py` pins that on the FILE, and that every control
  word survived the shortening) — the cut is what stops the NEXT control word
  breaking the worksheet silently. Structurally invisible to `_pn_xl_verify`
  for the same reason the formula cell is: the file is well-formed and
  openpyxl reads it back perfectly.
- **A workbook is written BESIDE the one on disk and READ BACK before it
  replaces it** (`_pn_xl_save` / `_pn_xl_verify`, shared by the key, `LEAKS.xlsx`
  and the master for the reason `_pn_wrap_sheet` is). `wb.save(path)` TRUNCATES
  the destination and then streams a zip into it over the following seconds, so
  any death in that window — the OOM kill a big folder is likeliest to hit, a
  full disk, a sync client seizing the file in a case folder that is by design
  synced — leaves a truncated zip WHERE THE KEY USED TO BE, which is the other
  thing Excel offers to repair. And nothing checked the result: openpyxl
  validates a plain string on the way in, loudly, but writes the shapes above as
  XML no reader can parse. Reading the file back is the only check that does not
  depend on having predicted the shape — if openpyxl cannot open what openpyxl
  just wrote, Excel will not either. Read-only mode is lazy, so `_pn_xl_verify`
  WALKS every row; that walk is what makes it a check. Failure raises `OSError`,
  so the key's existing handler still fires, and the key already on disk is
  untouched — hence `_PN_KEY_LOST_MSG` (shared by the full run and `--fix-leaks`,
  so the one message a run cannot afford to soften cannot be softened in half the
  places) says the standing key survives AND cannot carry what this run minted.
  The temp keeps the real EXTENSION: openpyxl refuses to open a `.tmp`, so a
  plain one failed verification on its name alone.
- **A cell is never a FORMULA and never an ERROR, and the read-back cannot say
  so** (`_pn_xl_plain_cells`, run over every sheet inside `_pn_xl_save`). This
  tool writes no formulas; openpyxl writes them anyway, from the TEXT alone —
  `Cell._bind_value` types any string starting with `=` as a formula and any
  string that is exactly one of the seven `ERROR_CODES` ("#N/A", "#REF!",
  "#NAME?" …) as an error cell. A flagged value is exactly where such text turns
  up, because the review scans read OCR'd exhibits and spreadsheet exports, and
  `LEAKS.xlsx` is where it was seen. `=Rasho v. Smith` goes out as
  `<f>Rasho v. Smith</f>`, which Excel cannot parse, so it repairs the workbook
  by DROPPING the cell — the operator loses the value they opened the worksheet
  to decide, or a Real Value out of the key. A formula that happens to PARSE is
  worse: nothing is repaired, nothing is reported, the cell shows a computed
  number and the value it stood for is gone. This is the one repair cause
  `_pn_xl_verify` is structurally blind to — it asks whether the file can be
  READ and openpyxl reads both shapes back happily — so it is fixed on the way
  out rather than detected. Setting `data_type` after the fact is what keeps the
  text: `_bind_value` already stored the string whole, leading `=` included, and
  only the writer consults the type.
- **A word list is DATA, not code.** A `#` inside a triple-quoted word list is
  not a comment. The housing block was first written with its rationale inside
  the string and put "#", "Act", "Bane," and "Fair" into `_PN_COMMON_WORDS` —
  swallowing the very surnames the rationale said to protect. Extra blocks go
  in their own constant and are unioned in
  (`_PN_HOUSING_WORDS`); `test_review_noise_and_bad_chars.py` asserts every
  list holds nothing but lower-case words.
- Runtime artifacts (`pdf_linker_eta_rate.txt`, `pdf_linker_eta_history.csv`,
  logs, leaks/key xlsx, ETA/DONE
  markers, launchers) are gitignored — never commit them (a stray one broke a
  user's `git pull`).
- Run tests: `cd PDF-Linker && python3 -m pytest tests/ -q`. `fitz` (PyMuPDF),
  `openpyxl` needed; OCR tests stub `pytesseract`/`PIL`.
