"""The ETA accuracy ledger: one CSV row per run, prediction beside outcome.

The rate files remember only the last run's throughput, and the marker dance
destroys each prediction at the moment the outcome becomes known (DONE
replaces the ETA file). `_note_eta_accuracy` appends both to
`pdf_linker_eta_history.csv` beside the config: the FIRST seeded ETA audits
the cross-run seed, the LAST mid-run ETA audits convergence, and the error
columns are readable without arithmetic. Append-only, header once,
best-effort — a ledger that cannot be written never costs a run.

Run:  cd PDF-Linker && python3 -m pytest tests/test_eta_history.py -v
"""
import csv
import datetime

import pytest

import pdf_linker as P


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    path = tmp_path / "pdf_linker_eta_history.csv"
    monkeypatch.setattr(P, "_eta_history_path", lambda: path)
    return path


def _note(path_kind="full run", seed=True, **over):
    started = datetime.datetime(2026, 8, 20, 9, 0, 0)
    seeded = datetime.datetime(2026, 8, 20, 9, 10, 0) if seed else None
    finished = datetime.datetime(2026, 8, 20, 9, 12, 30)
    kw = dict(kind=path_kind, folder="C:/Cases/Rasho", files=13,
              work=1234.0, seed_rate=2.5 if seed else None,
              seeded_eta=seeded,
              last_eta=datetime.datetime(2026, 8, 20, 9, 12, 0),
              started=started, finished=finished, elapsed=750.0,
              final_rate=1.645)
    kw.update(over)
    P._note_eta_accuracy(**kw)


def _rows(path):
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


def test_header_once_rows_appended(ledger):
    _note()
    _note(path_kind="fix-leaks", last_eta=None)
    rows = _rows(ledger)
    assert rows[0] == list(P._ETA_HISTORY_COLUMNS)
    assert len(rows) == 3
    assert rows[1][1] == "full run" and rows[2][1] == "fix-leaks"


def test_error_columns_are_finished_minus_prediction(ledger):
    _note()
    row = dict(zip(P._ETA_HISTORY_COLUMNS, _rows(ledger)[1]))
    # Finished 09:12:30; seeded ETA 09:10:00 (+150s late); last ETA 09:12:00.
    assert row["Seeded ETA Error (sec)"] == "150"
    assert row["Last ETA Error (sec)"] == "30"
    assert row["Elapsed (sec)"] == "750"
    assert row["Files"] == "13" and row["Work Units"] == "1234"


def test_nothing_to_predict_with_leaves_empty_cells(ledger):
    # A first run has no stored rate; a single-file batch never updates
    # mid-run. Neither may invent a prediction to grade.
    _note(seed=False, last_eta=None)
    row = dict(zip(P._ETA_HISTORY_COLUMNS, _rows(ledger)[1]))
    assert row["Seed Rate"] == "" and row["Seeded ETA"] == ""
    assert row["Seeded ETA Error (sec)"] == ""
    assert row["Last ETA"] == "" and row["Last ETA Error (sec)"] == ""


def test_a_ledger_that_cannot_be_written_never_costs_the_run(tmp_path,
                                                             monkeypatch):
    monkeypatch.setattr(P, "_eta_history_path",
                        lambda: tmp_path / "no-such-dir" / "h.csv")
    _note()   # must not raise
