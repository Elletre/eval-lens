"""Every question is asked twice — once in Python, once in SQL — and must answer the same.

The SQL is what a reader is meant to read and what would move to a real ClickHouse
cluster; the Python is what the tests can reason about. Neither is allowed to drift from
the other: a query nobody checks is a claim nobody checked.
"""

from pathlib import Path

import pytest

from eval_lens import metrics, queries
from eval_lens.comparisons import derive
from eval_lens.ingest import read_corpus
from eval_lens.store import Store

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def loaded():
    corpus = read_corpus(ROOT / "data")
    comparisons = derive(corpus)
    store = Store()
    store.load(corpus, comparisons)
    yield store, corpus, comparisons
    store.close()


def test_every_query_file_runs_and_returns_rows(loaded):
    store, _, _ = loaded
    assert queries.names(), "no queries found"
    for name in queries.names():
        assert store.query(queries.read(name)), f"{name} returned nothing"


def test_case_information_agrees(loaded):
    store, corpus, comparisons = loaded
    in_sql = {
        (row["project"], row["suite_version"], row["case_id"]): (
            row["label"],
            row["comparisons"],
            row["discriminated"],
        )
        for row in store.query(queries.read("case_information"))
    }
    in_python = {
        (verdict.project, verdict.suite_version, verdict.case_id): (
            verdict.label,
            verdict.comparisons,
            verdict.discriminated,
        )
        for verdict in metrics.case_information(corpus, comparisons)
    }
    assert in_sql == in_python


def test_repeat_noise_agrees(loaded):
    store, corpus, _ = loaded
    in_sql = {
        row["run_id"]: (row["cases_with_repeats"], row["mixed_cases"], row["trials"])
        for row in store.query(queries.read("repeat_noise"))
    }
    in_python = {
        item.run_id: (item.cases_with_repeats, item.mixed_cases, item.trials)
        for item in metrics.repeat_noise(corpus)
    }
    assert in_sql == in_python


def test_drift_agrees(loaded):
    store, corpus, _ = loaded
    in_sql = {
        (row["project"], row["suite_version"], row["variant"]): row["spread"]
        for row in store.query(queries.read("drift"))
    }
    in_python = {
        (item.project, item.suite_version, item.variant): round(item.spread, 6)
        for item in metrics.drift(corpus)
    }
    assert in_sql == pytest.approx(in_python)


def test_case_cost_agrees(loaded):
    store, corpus, _ = loaded
    in_sql = {
        (row["project"], row["suite_version"], row["case_id"]): (
            row["trials"],
            round(row["seconds"], 3),
            row["input_tokens"],
        )
        for row in store.query(queries.read("case_cost"))
    }
    in_python = {
        (cost.project, cost.suite_version, cost.case_id): (
            cost.trials,
            round(cost.seconds, 3),
            cost.input_tokens,
        )
        for cost in metrics.case_cost(corpus)
    }
    assert in_sql == in_python


def test_silence_cost_agrees(loaded):
    store, corpus, comparisons = loaded
    in_sql = {
        (row["project"], row["suite_version"]): (
            row["informative_cases"],
            row["silent_cases"],
            row["uncompared_cases"],
            round(row["silent_seconds"], 3),
        )
        for row in store.query(queries.read("silence_cost"))
    }
    verdicts = metrics.case_information(corpus, comparisons)
    in_python = {
        (cost.project, cost.suite_version): (
            cost.informative_cases,
            cost.silent_cases,
            cost.uncompared_cases,
            round(cost.silent_seconds, 3),
        )
        for cost in metrics.silence_cost(verdicts, metrics.case_cost(corpus))
    }
    assert in_sql == in_python


def test_failure_profile_and_silent_gates_agree(loaded):
    store, corpus, _ = loaded
    in_sql = {
        (row["project"], row["label"]): (row["trials"], row["runs"])
        for row in store.query(queries.read("failure_profile"))
    }
    in_python = {
        (item.project, item.label): (item.trials, item.runs)
        for item in metrics.failure_profile(corpus)
    }
    assert in_sql == in_python

    gates_in_sql = {
        (row["project"], row["gate"], row["trials"])
        for row in store.query(queries.read("silent_gates"))
    }
    assert gates_in_sql == set(metrics.silent_gates(corpus))
