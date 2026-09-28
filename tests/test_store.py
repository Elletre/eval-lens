"""The store must hold the corpus exactly, and hold it once."""

from pathlib import Path

import pytest

from eval_lens import queries
from eval_lens.cli import store_files
from eval_lens.comparisons import derive
from eval_lens.ingest import read_corpus
from eval_lens.store import STRUCTURES, Store

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def store():
    handle = Store()
    handle.load(read_corpus(ROOT / "data"))
    yield handle
    handle.close()


def test_the_corpus_arrives_whole(store):
    counts = store.query("SELECT count() AS trials, uniqExact(run_id) AS runs FROM trials")[0]
    assert counts == {"trials": 1260, "runs": 17}
    assert store.query("SELECT count() AS n FROM runs")[0]["n"] == 17
    assert store.query("SELECT count() AS n FROM tool_calls")[0]["n"] == 1436


def test_loading_twice_does_not_double_anything(store):
    store.load(read_corpus(ROOT / "data"))
    assert store.query("SELECT count() AS n FROM trials")[0]["n"] == 1260


def test_gates_survive_as_a_queryable_map(store):
    rows = store.query(
        "SELECT arrayJoin(mapKeys(gates)) AS gate, count() AS n FROM trials GROUP BY gate"
    )
    gates = {row["gate"] for row in rows}
    assert {"expected_status", "exact_final_state", "authorized_write_attempts"} <= gates
    assert all(row["n"] == 576 for row in rows), "every agent-eval-lab trial records every gate"


def test_a_trial_can_be_traced_back_to_the_file_it_came_from(store):
    row = store.query(
        "SELECT r.source AS source FROM trials AS t JOIN runs AS r ON t.run_id = r.run_id LIMIT 1"
    )[0]
    assert (ROOT / "data" / row["source"]).exists()


def test_the_exported_files_load_back_into_the_same_numbers(store, tmp_path):
    """The export is the migration path off chDB, so it has to be loadable, not just written."""
    corpus = read_corpus(ROOT / "data")
    files = store_files(corpus, derive(corpus), tmp_path / "export")
    assert {path.name for path in files} == {
        "schema.sql",
        "runs.jsonl",
        "trials.jsonl",
        "tool_calls.jsonl",
        "comparisons.jsonl",
    }

    reloaded = Store()
    try:
        for table, structure in STRUCTURES.items():
            reloaded.query(
                f"INSERT INTO {table} SELECT * FROM "
                f"file('{tmp_path / 'export' / f'{table}.jsonl'}', JSONEachRow, '{structure}')"
            )
        question = queries.read("case_information")
        assert reloaded.query(question) == store.query(question)
    finally:
        reloaded.close()
