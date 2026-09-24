"""Metric definitions, on cases small enough to check by hand."""

from pathlib import Path

import pytest

from eval_lens.comparisons import Comparison, derive
from eval_lens.ingest import read_corpus
from eval_lens.metrics import (
    case_cost,
    case_information,
    drift,
    failure_profile,
    pruning_experiment,
    repeat_noise,
    sign_test_exact,
    silence_cost,
    silent_gates,
    variance_split,
)
from eval_lens.model import Corpus, Run, Trial

ROOT = Path(__file__).resolve().parents[1]


def run(run_id: str, variant: str, config: str = "c=1", kind: str = "model") -> Run:
    return Run(
        run_id=run_id,
        project="p",
        suite="s",
        suite_version="v1",
        variant=variant,
        model="m",
        config=config,
        recorded_at="2026-09-25",
        kind=kind,
        source=f"{run_id}.json",
    )


def trial(run_id: str, case: str, repeat: int, passed: bool, error: str = "") -> Trial:
    return Trial(
        run_id=run_id,
        case_id=case,
        family="f",
        repeat=repeat,
        passed=passed,
        error=error,
        failures=(),
        seconds=1.0,
    )


@pytest.fixture
def toy() -> Corpus:
    """Four cases: one that moves, one always green, one always red, one that only wobbles."""
    trials = []
    for repeat in (1, 2):
        trials += [
            trial("a", "moves", repeat, passed=False),
            trial("b", "moves", repeat, passed=True),
            trial("a", "always-green", repeat, passed=True),
            trial("b", "always-green", repeat, passed=True),
            trial("a", "always-red", repeat, passed=False),
            trial("b", "always-red", repeat, passed=False),
        ]
    # Wobbles inside each run but ends at the same rate on both sides.
    trials += [
        trial("a", "wobbles", 1, passed=True),
        trial("a", "wobbles", 2, passed=False),
        trial("b", "wobbles", 1, passed=False),
        trial("b", "wobbles", 2, passed=True),
    ]
    return Corpus(runs=[run("a", "control"), run("b", "candidate")], trials=trials)


@pytest.fixture
def toy_comparison() -> list[Comparison]:
    return [Comparison(name="toy", project="p", control="a", candidate="b", factor="candidate")]


def test_a_case_is_informative_only_when_it_moves_between_the_two_sides(toy, toy_comparison):
    labels = {v.case_id: v.label for v in case_information(toy, toy_comparison)}
    assert labels == {
        "moves": "informative",
        "always-green": "saturated",
        "always-red": "floored",
        "wobbles": "quiet",
    }


def test_a_trial_the_harness_cut_short_is_not_evidence(toy_comparison):
    trials = [
        trial("a", "one", 1, passed=True),
        trial("a", "one", 2, passed=False, error="time limit"),
        trial("b", "one", 1, passed=True),
        trial("b", "one", 2, passed=False, error="time limit"),
    ]
    corpus = Corpus(runs=[run("a", "control"), run("b", "candidate")], trials=trials)
    (verdict,) = case_information(corpus, toy_comparison)
    assert verdict.rates == (1.0, 1.0), "the stopped attempts must leave the rate alone"
    assert verdict.label == "saturated"


def test_noise_counts_cases_that_disagree_with_themselves(toy):
    noise = {item.run_id: item for item in repeat_noise(toy)}
    assert noise["a"].cases_with_repeats == 4
    assert noise["a"].mixed_cases == 1
    assert noise["a"].share == 0.25


def test_drift_needs_the_same_variant_scored_twice(toy):
    assert drift(toy) == []
    corpus = Corpus(
        runs=[run("a", "control", config="c=1"), run("b", "control", config="c=2")],
        trials=[
            trial("a", "one", 1, passed=True),
            trial("b", "one", 1, passed=False),
        ],
    )
    (moved,) = drift(corpus)
    assert moved.spread == 1.0
    assert [config for _, config, _ in moved.observations] == ["c=1", "c=2"]


def test_a_fixture_run_is_never_compared_with_a_model_run():
    corpus = Corpus(
        runs=[run("a", "control", kind="fixture"), run("b", "faults", kind="fixture")],
        trials=[trial("a", "one", 1, passed=True), trial("b", "one", 1, passed=False)],
    )
    assert derive(corpus) == []


def test_the_real_corpus_yields_the_comparisons_its_projects_published():
    corpus = read_corpus(ROOT / "data")
    names = {comparison.factor for comparison in derive(corpus)}
    assert names == {"improved", "vague-tool-descriptions", "untrusted-content-unmarked"}
    assert len(derive(corpus)) == 7, "three prompt comparisons and four defect comparisons"


def test_silence_is_counted_in_seconds_not_only_in_cases(toy, toy_comparison):
    verdicts = case_information(toy, toy_comparison)
    (cost,) = silence_cost(verdicts, case_cost(toy))
    assert cost.informative_cases == 1 and cost.silent_cases == 3
    assert cost.uncompared_cases == 0
    # Every trial in the toy corpus takes a second, and each case ran four times.
    assert cost.informative_seconds == 4.0
    assert cost.wasted_share == pytest.approx(12 / 16)


def test_a_dataset_version_nobody_compared_is_not_called_wasteful(toy_comparison):
    corpus = Corpus(
        runs=[run("solo", "control")],
        trials=[trial("solo", "one", 1, passed=True)],
    )
    (cost,) = silence_cost(case_information(corpus, toy_comparison), case_cost(corpus))
    assert (cost.informative_cases, cost.silent_cases, cost.uncompared_cases) == (0, 0, 1)
    assert cost.wasted_share == 0.0


def test_variance_split_finds_the_variant_when_the_variant_is_all_there_is(toy_comparison):
    """Every case behaves the same, and only the side differs."""
    trials = [trial("a", f"case-{i}", 1, passed=False) for i in range(4)]
    trials += [trial("b", f"case-{i}", 1, passed=True) for i in range(4)]
    corpus = Corpus(runs=[run("a", "control"), run("b", "candidate")], trials=trials)
    (split,) = variance_split(corpus, toy_comparison)
    assert split.between_variants == pytest.approx(1.0)
    assert split.between_cases == pytest.approx(0.0)
    assert split.residual == pytest.approx(0.0)


def test_a_gate_that_never_fails_is_reported():
    trials = [
        Trial(
            run_id="a",
            case_id="one",
            family="f",
            repeat=1,
            passed=False,
            error="",
            failures=("expected_status",),
            gates=(("expected_status", False), ("known_tools_only", True)),
        )
    ]
    corpus = Corpus(runs=[run("a", "control")], trials=trials)
    assert silent_gates(corpus) == [("p", "known_tools_only", 1)]
    profile = failure_profile(corpus)
    assert [(item.label, item.trials) for item in profile] == [("expected_status", 1)]


@pytest.mark.parametrize(
    ("up", "down", "expected"),
    [(0, 0, 1.0), (3, 3, 1.0), (5, 0, 0.0625), (6, 0, 0.03125), (0, 6, 0.03125)],
)
def test_sign_test_matches_the_exact_binomial(up, down, expected):
    assert sign_test_exact(up, down) == pytest.approx(expected)


def test_pruning_never_judges_a_case_by_the_comparison_it_is_used_to_recompute():
    """A case that only ever moves in one comparison must be dropped from that one."""
    runs = [run("a", "control"), run("b", "candidate")]
    trials = [
        trial("a", "only-here", 1, passed=False),
        trial("b", "only-here", 1, passed=True),
        trial("a", "quiet", 1, passed=True),
        trial("b", "quiet", 1, passed=True),
    ]
    corpus = Corpus(runs=runs, trials=trials)
    comparison = Comparison(name="one", project="p", control="a", candidate="b", factor="x")
    (result,) = pruning_experiment(corpus, [comparison])
    assert result.kept_cases == 0, "with no other comparison to judge it, nothing is informative"
    assert result.delta_all == pytest.approx(0.5)


def test_pruning_keeps_a_case_that_moved_in_another_comparison():
    runs = [run("a", "control"), run("b", "candidate"), run("c", "other", config="c=2")]
    trials = []
    for run_id, passed in (("a", False), ("b", True), ("c", True)):
        trials.append(trial(run_id, "moves", 1, passed=passed))
        trials.append(trial(run_id, "silent", 1, passed=True))
    corpus = Corpus(runs=runs, trials=trials)
    here = Comparison(name="here", project="p", control="a", candidate="b", factor="x")
    elsewhere = Comparison(name="elsewhere", project="p", control="a", candidate="c", factor="y")
    results = {item.comparison: item for item in pruning_experiment(corpus, [here, elsewhere])}
    assert results["here"].kept_cases == 1 and results["here"].dropped_cases == 1
    assert results["here"].delta_kept == pytest.approx(1.0)
    assert results["here"].time_saved == pytest.approx(0.5)
