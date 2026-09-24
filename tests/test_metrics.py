"""Metric definitions, on cases small enough to check by hand."""

from pathlib import Path

import pytest

from eval_lens.comparisons import Comparison, derive
from eval_lens.ingest import read_corpus
from eval_lens.metrics import case_information, drift, repeat_noise
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
