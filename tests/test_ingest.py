"""The corpus must arrive intact, and the two vocabularies must not be mixed up."""

from collections import Counter
from pathlib import Path

import pytest

from eval_lens.ingest import read_corpus
from eval_lens.ingest.mcpqa import classify

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def corpus():
    return read_corpus(ROOT / "data")


def test_every_vendored_run_is_read(corpus):
    assert len(corpus.runs) == 18
    assert len(corpus.trials) == 1341
    assert {run.project for run in corpus.runs} == {"mcp-connector-testkit", "agent-eval-lab"}
    assert len({run.run_id for run in corpus.runs}) == len(corpus.runs), "run ids must be unique"


def test_a_trial_belongs_to_exactly_one_run_case_and_repeat(corpus):
    keys = Counter((trial.run_id, trial.case_id, trial.repeat) for trial in corpus.trials)
    assert keys.most_common(1)[0][1] == 1


def test_configuration_separates_the_factors_that_were_varied(corpus):
    """Two runs are comparable only when everything but the variant matches."""
    configs = {run.run_id: run.config for run in corpus.runs}
    assert "temperature=0.8" in configs["mcpqa:2026-09-18-llama3-8b-baseline-temperature-0.8"]
    assert "temperature=0" in configs["mcpqa:2026-09-18-llama3-8b-baseline"]
    assert "harness=v1" in configs["mcpqa:archive__2026-09-18-harness-v1__llama3-8b-baseline"]
    clean = configs["lab:experiments__2026-09-22-qwen3-8b__baseline"]
    limited = configs["lab:experiments__archive__2026-09-22-qwen3-8b-120s-wall-clock__baseline"]
    assert "time_limit=300" in clean and "time_limit=120" in limited
    assert clean != limited, "the wall clock already decided one comparison in this corpus"


def test_the_model_identity_does_not_carry_its_sampling_settings(corpus):
    models = {run.model for run in corpus.runs if run.project == "mcp-connector-testkit"}
    assert models == {"ollama/llama3:latest"}


def test_gates_are_kept_where_a_project_records_them(corpus):
    lab = [t for t in corpus.trials if t.run_id.startswith("lab:")]
    mcpqa = [t for t in corpus.trials if t.run_id.startswith("mcpqa:")]
    assert all(trial.gates for trial in lab), "agent-eval-lab records every gate per trial"
    assert not any(trial.gates for trial in mcpqa), "mcpqa records only what failed"
    assert all(set(dict(trial.gates)) >= {"expected_status", "exact_final_state"} for trial in lab)


def test_a_failed_gate_is_always_in_the_failure_list(corpus):
    for trial in (t for t in corpus.trials if t.gates):
        failed = {gate for gate, passed in trial.gates if not passed}
        assert failed == set(trial.failures)


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("expected list_labels first, but no tool was called", "wrong_first_tool"),
        (
            "answered without looking: called none of ['search_messages']",
            "answered_without_looking",
        ),
        ("never called ['list_labels']", "missing_required_tool"),
        ("called forbidden tool(s) ['trash_message']", "forbidden_tool"),
        ("the answer does not mention '23:40'", "missing_fact"),
        ("the mailbox changed: -1 ['alice|message:msg_00902']", "unexpected_state_change"),
        ("something nobody has written yet", "other"),
    ],
)
def test_free_text_failures_are_classified(text, label):
    assert classify(text) == label


def test_tool_calls_keep_their_order_within_a_trial(corpus):
    sequences = {}
    for call in corpus.tool_calls:
        sequences.setdefault((call.run_id, call.case_id, call.repeat), []).append(call.seq)
    assert all(order == sorted(order) for order in sequences.values())
    assert all(order == list(range(len(order))) for order in sequences.values())
