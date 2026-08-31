"""ONE remembered rate could not seed TWO populations.

The seed was a single machine-wide number from whichever run finished last,
and full-run throughput spans 21x in two clear populations: a folder of
scanned filings and a folder of born-digital ones. Every run inherited
whichever kind ran last, so the seeded ETA was routinely wrong by HOURS — one
folder opened claiming it would finish at 00:14 and finished at 20:23. (The
mid-run estimate was never the problem: measured over 41 real runs its median
error is seven seconds.)

Two changes. The rate is kept per BUCKET, and it is a rolling MEDIAN of the
last few runs rather than the last one alone — 27 of 80 real runs overlapped
another, and concurrent runs share cores, so each measures a depressed rate
and last-writer-wins then hands that rate to whatever starts next.

Run:  cd PDF-Linker && python3 -m pytest tests/test_eta_rate_buckets.py -v
"""
import logging

import pytest

import pdf_linker as P

fitz = pytest.importorskip("fitz")
log = logging.getLogger("test")


@pytest.fixture(autouse=True)
def _isolate_rates(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "_eta_rates_path", lambda: tmp_path / "rates.txt")
    monkeypatch.setattr(P, "_eta_rate_path", lambda: tmp_path / "rate.txt")
    monkeypatch.setattr(P, "_eta_history_path", lambda: tmp_path / "hist.csv")


# ── which population a folder belongs to ────────────────────────────────────

def test_the_mix_is_measured_in_pages_not_work_units(tmp_path):
    """The 40:1 weight puts a folder with one scanned exhibit in ten at 82% of
    the WORK, so a work-share split would sort nearly every folder one way and
    split nothing."""
    assert P._eta_bucket(1, 9) == "native"
    assert P._eta_bucket(9, 1) == "scanned"
    assert P._eta_bucket(5, 5) == "scanned"      # the boundary is inclusive
    assert P._eta_bucket(0, 0) is None           # nothing could be measured


def test_the_profile_reports_the_mix_beside_the_weight(tmp_path):
    doc = fitz.open()
    for _ in range(3):
        doc.new_page().insert_text((72, 100), "ordinary native body text here")
    for _ in range(5):
        doc.new_page()                            # no text -> will need OCR
    p = tmp_path / "mixed.pdf"
    doc.save(str(p))
    doc.close()

    weight, ocr, text = P._pdf_work_profile(p)
    assert (ocr, text) == (5, 3)
    assert weight == 5 * P._WORK_OCR_PAGE + 3 * P._WORK_TEXT_PAGE
    # the old contract is unchanged for its own callers
    assert P._pdf_work_weight(p) == weight
    bad = tmp_path / "bad.pdf"
    bad.write_text("not a pdf")
    assert P._pdf_work_profile(bad) is None
    assert P._pdf_work_weight(bad) is None


# ── a folder is seeded from its OWN kind ───────────────────────────────────

def test_each_bucket_keeps_its_own_rate():
    P._record_eta_rate("scanned", 1.5)
    P._record_eta_rate("native", 0.1)
    assert P._load_eta_rate_for("scanned") == 1.5
    assert P._load_eta_rate_for("native") == 0.1


def test_a_native_folder_is_never_seeded_from_a_scanned_one():
    """The 6.4-hour miss, in one assertion: with only scanned history, a native
    folder gets NO seed rather than a number wrong by hours. The marker reads
    "(estimating…)" for one file, after which the live estimate is accurate to
    seconds."""
    P._record_eta_rate("scanned", 1.5)
    assert P._load_eta_rate_for("native") is None


def test_an_existing_install_keeps_a_seed_on_its_first_new_run():
    """The legacy single-rate file still answers until a bucket has history, so
    months of running are not thrown away."""
    P._save_eta_rate(0.42)
    assert P._load_eta_rate_for("scanned") == 0.42
    P._record_eta_rate("scanned", 1.5)
    assert P._load_eta_rate_for("scanned") == 1.5      # the bucket now wins


def test_an_unmeasurable_folder_falls_back_to_the_legacy_rate():
    P._save_eta_rate(0.42)
    assert P._load_eta_rate_for(None) == 0.42


# ── …and one bad sample does not become the seed ───────────────────────────

def test_the_seed_is_a_rolling_median_not_the_last_run():
    """Concurrent runs share cores and measure a depressed rate; last-writer-
    wins used to hand that straight to the next run."""
    for r in (1.5, 1.4, 1.6):
        P._record_eta_rate("scanned", r)
    P._record_eta_rate("scanned", 0.05)      # a run that shared the machine
    assert P._load_eta_rate_for("scanned") == pytest.approx(1.45)


def test_only_the_last_few_samples_are_kept():
    """Short on purpose: a genuinely faster machine is still followed."""
    for r in range(1, 12):
        P._record_eta_rate("native", float(r))
    kept = P._load_eta_samples()["native"]
    assert len(kept) == P._ETA_RATE_SAMPLES
    assert kept[0] == 11.0                    # newest first
    assert P._load_eta_rate_for("native") == 9.0


def test_a_new_machine_is_followed_within_a_few_runs():
    for _ in range(P._ETA_RATE_SAMPLES):
        P._record_eta_rate("scanned", 0.1)
    for _ in range(P._ETA_RATE_SAMPLES // 2 + 1):
        P._record_eta_rate("scanned", 2.0)
    assert P._load_eta_rate_for("scanned") == 2.0


# ── the store never costs a run ────────────────────────────────────────────

@pytest.mark.parametrize("junk", ["", "garbage", "scanned\n", "scanned x y\n",
                                  "scanned -1\n", "\x00\x00"])
def test_an_unreadable_store_is_no_history_never_an_error(tmp_path, junk):
    (tmp_path / "rates.txt").write_text(junk, encoding="utf-8")
    assert P._load_eta_rate_for("scanned") is None
    P._record_eta_rate("scanned", 1.25)       # and it recovers
    assert P._load_eta_rate_for("scanned") == 1.25


def test_a_non_positive_rate_is_never_recorded():
    P._record_eta_rate("scanned", 1.5)
    P._record_eta_rate("scanned", 0)
    P._record_eta_rate("scanned", -3)
    assert P._load_eta_samples()["scanned"] == [1.5]


# ── the ledger gains the columns that make the split auditable ─────────────

OLD_HEADER = ("Run Started,Kind,Folder,Files,Work Units,Seed Rate,Seeded ETA,"
              "Last ETA,Finished,Elapsed (sec),Final Rate,"
              "Seeded ETA Error (sec),Last ETA Error (sec)\n")
OLD_ROW = ("8/29/2026 17:47,full run,C:\\Convert,28,14240,0.613977,"
           "8/30/2026 0:14,8/29/2026 20:24,8/29/2026 20:23,9282,1.534196,"
           "-13840,-35\n")


def _hist(tmp_path):
    import csv
    with (tmp_path / "hist.csv").open(encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


def test_an_older_ledger_is_migrated_by_name(tmp_path):
    """A column added later would write rows that no longer line up with the
    header the file was started with."""
    (tmp_path / "hist.csv").write_text(OLD_HEADER + OLD_ROW, encoding="utf-8")
    import datetime
    P._note_eta_accuracy("full run", tmp_path, 3, 120.0, 0.5, None, None,
                         datetime.datetime.now(), datetime.datetime.now(),
                         200.0, 0.6, ocr_share=1.0, bucket="scanned")
    rows = _hist(tmp_path)
    assert tuple(rows[0]) == P._ETA_HISTORY_COLUMNS
    assert len(rows) == 3                       # header + the old row + the new
    old = dict(zip(rows[0], rows[1]))
    assert old["Work Units"] == "14240"         # carried across by NAME
    assert old["Final Rate"] == "1.534196"
    assert old["Seeded ETA Error (sec)"] == "-13840"
    assert old["Rate Bucket"] == ""             # it never recorded one
    new = dict(zip(rows[0], rows[2]))
    assert new["Rate Bucket"] == "scanned"
    assert new["OCR Page Share"] == "1.00"


def test_a_fresh_ledger_needs_no_migration(tmp_path):
    import datetime
    for _ in range(2):
        P._note_eta_accuracy("fix-leaks", tmp_path, 3, 120.0, 0.5, None, None,
                             datetime.datetime.now(), datetime.datetime.now(),
                             200.0, 0.6)
    rows = _hist(tmp_path)
    assert tuple(rows[0]) == P._ETA_HISTORY_COLUMNS and len(rows) == 3
    assert dict(zip(rows[0], rows[1]))["Rate Bucket"] == ""   # not a full run


def test_a_ledger_that_cannot_be_read_is_left_alone(tmp_path):
    """Append-only and best-effort: a ledger must never cost a run."""
    (tmp_path / "hist.csv").write_text("\x00 not a csv\n", encoding="utf-8")
    P._eta_history_migrate(tmp_path / "hist.csv")
    assert (tmp_path / "hist.csv").read_text(encoding="utf-8")


# ── end to end: a run records into its own bucket, and seeds from it ───────

def _folder(tmp_path, name, scanned, files=2, pages=2):
    d = tmp_path / name
    d.mkdir()
    for i in range(files):
        doc = fitz.open()
        for _ in range(pages):
            pg = doc.new_page()
            if not scanned:
                pg.insert_text((72, 100), "ordinary native body text here")
        doc.save(str(d / f"doc{i}.pdf"))
        doc.close()
    return d


def _run(folder, monkeypatch, tmp_path):
    import sys
    monkeypatch.setattr(P, "_config_path", lambda: tmp_path / "pdf_linker.config")
    monkeypatch.setattr(sys, "argv",
                        ["pdf_linker.py", str(folder), "--no-pseudonymize"])
    try:
        P.main()
    except SystemExit:
        pass


def test_a_run_records_into_the_bucket_its_folder_belongs_to(tmp_path,
                                                             monkeypatch):
    _run(_folder(tmp_path, "scans", scanned=True), monkeypatch, tmp_path)
    assert list(P._load_eta_samples()) == ["scanned"]
    _run(_folder(tmp_path, "briefs", scanned=False), monkeypatch, tmp_path)
    assert sorted(P._load_eta_samples()) == ["native", "scanned"]


def test_the_ledger_records_the_mix_and_the_bucket(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "_eta_history_path", lambda: tmp_path / "hist.csv")
    _run(_folder(tmp_path, "scans", scanned=True), monkeypatch, tmp_path)
    row = dict(zip(*_hist(tmp_path)[:2]))
    assert row["Kind"] == "full run"
    assert row["Rate Bucket"] == "scanned"
    assert row["OCR Page Share"] == "1.00"
    assert row["Final Rate"]
