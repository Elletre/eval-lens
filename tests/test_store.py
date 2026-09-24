"""The store must hold the corpus exactly, and hold it once."""

from pathlib import Path

import pytest

from eval_lens.ingest import read_corpus
from eval_lens.store import Store

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def store():
    handle = Store()
    handle.load(read_corpus(ROOT / "data"))
    yield handle
    handle.close()


def test_the_corpus_arrives_whole(store):
    counts = store.query("SELECT count() AS trials, uniqExact(run_id) AS runs FROM trials")[0]
    assert counts == {"trials": 1179, "runs": 16}
    assert store.query("SELECT count() AS n FROM runs")[0]["n"] == 16
    assert store.query("SELECT count() AS n FROM tool_calls")[0]["n"] == 1355


def test_loading_twice_does_not_double_anything(store):
    store.load(read_corpus(ROOT / "data"))
    assert store.query("SELECT count() AS n FROM trials")[0]["n"] == 1179


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
