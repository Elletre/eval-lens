"""What the suite is worth as an instrument.

Every metric here is about the eval suite, not about the models it scored. A case that
always passes and a case that always fails are both silent: they cost time and tell the
next comparison nothing. A suite whose repeats disagree with themselves cannot resolve a
difference smaller than that disagreement. Both are measurable from runs that already
happened.

Trials the harness cut short are excluded everywhere: they carry no verdict about the
model, and counting them as failures is the mistake one of the source projects already
made and fixed.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from eval_lens.comparisons import Comparison
from eval_lens.model import Corpus, Run, Trial

Scope = tuple[str, str]
"""A project and a dataset version: cases only mean the same thing inside one."""


def graded(trials: list[Trial]) -> list[Trial]:
    return [trial for trial in trials if not trial.error]


def case_rates(trials: list[Trial]) -> dict[tuple[str, str], float]:
    """Pass rate per (run_id, case_id), over the repeats that actually ran."""
    totals: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for trial in graded(trials):
        totals[(trial.run_id, trial.case_id)].append(trial.passed)
    return {key: sum(values) / len(values) for key, values in totals.items() if values}


@dataclass(frozen=True)
class CaseVerdict:
    """What one case did across every run of its scope."""

    project: str
    suite_version: str
    case_id: str
    family: str
    comparisons: int
    """How many comparisons the case took part in."""
    discriminated: int
    """In how many of them its pass rate differed between the two sides."""
    rates: tuple[float, ...]
    seconds: float
    """Mean seconds per trial, across the scope."""

    @property
    def label(self) -> str:
        if self.discriminated:
            return "informative"
        if self.rates and all(rate == 1.0 for rate in self.rates):
            return "saturated"
        if self.rates and all(rate == 0.0 for rate in self.rates):
            return "floored"
        return "quiet"
        # quiet: it moves between runs, but never between the two sides of a comparison,
        # so it contributes noise to a comparison without contributing an answer.


def case_information(corpus: Corpus, comparisons: list[Comparison]) -> list[CaseVerdict]:
    rates = case_rates(corpus.trials)
    runs = {run.run_id: run for run in corpus.runs}
    scope_of = {run_id: (run.project, run.suite_version) for run_id, run in runs.items()}

    taking_part: dict[tuple[Scope, str], int] = defaultdict(int)
    differing: dict[tuple[Scope, str], int] = defaultdict(int)
    for comparison in comparisons:
        if comparison.control not in scope_of or comparison.candidate not in scope_of:
            continue  # a comparison naming runs this corpus does not hold
        scope = scope_of[comparison.control]
        cases = {case for run_id, case in rates if run_id in comparison.runs}
        for case in cases:
            left = rates.get((comparison.control, case))
            right = rates.get((comparison.candidate, case))
            if left is None or right is None:
                continue
            taking_part[(scope, case)] += 1
            if left != right:
                differing[(scope, case)] += 1

    seconds: dict[tuple[Scope, str], list[float]] = defaultdict(list)
    families: dict[tuple[Scope, str], str] = {}
    scope_rates: dict[tuple[Scope, str], list[float]] = defaultdict(list)
    for trial in graded(corpus.trials):
        key = (scope_of[trial.run_id], trial.case_id)
        seconds[key].append(trial.seconds)
        families.setdefault(key, trial.family)
    for (run_id, case), rate in rates.items():
        if runs[run_id].kind == "model":
            scope_rates[(scope_of[run_id], case)].append(rate)

    verdicts = []
    for key, rate_values in sorted(scope_rates.items()):
        (project, suite_version), case = key
        durations = seconds.get(key, [0.0])
        verdicts.append(
            CaseVerdict(
                project=project,
                suite_version=suite_version,
                case_id=case,
                family=families.get(key, ""),
                comparisons=taking_part.get(key, 0),
                discriminated=differing.get(key, 0),
                rates=tuple(rate_values),
                seconds=sum(durations) / len(durations),
            )
        )
    return verdicts


@dataclass(frozen=True)
class RunNoise:
    """How much a run disagrees with itself when nothing changed."""

    run_id: str
    cases_with_repeats: int
    mixed_cases: int
    trials: int

    @property
    def share(self) -> float:
        return self.mixed_cases / self.cases_with_repeats if self.cases_with_repeats else 0.0


def repeat_noise(corpus: Corpus) -> list[RunNoise]:
    """Cases whose repeats disagree, per run — the instrument's own dispersion."""
    by_case: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for trial in graded(corpus.trials):
        by_case[(trial.run_id, trial.case_id)].append(trial.passed)

    counted: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for (run_id, _), verdicts in by_case.items():
        counted[run_id][2] += len(verdicts)
        if len(verdicts) < 2:
            continue
        counted[run_id][0] += 1
        counted[run_id][1] += int(len(set(verdicts)) > 1)
    return [
        RunNoise(
            run_id=run_id, cases_with_repeats=values[0], mixed_cases=values[1], trials=values[2]
        )
        for run_id, values in sorted(counted.items())
    ]


@dataclass(frozen=True)
class Drift:
    """The same variant, scored twice, with something else changed."""

    project: str
    suite_version: str
    variant: str
    model: str
    observations: tuple[tuple[str, str, float], ...] = field(default_factory=tuple)
    """(run_id, config, pass rate) for each run of this variant."""

    @property
    def spread(self) -> float:
        rates = [rate for _, _, rate in self.observations]
        return max(rates) - min(rates) if rates else 0.0


def drift(corpus: Corpus) -> list[Drift]:
    """How far the same policy moves between runs — the floor under any comparison."""
    runs = {run.run_id: run for run in corpus.runs if run.kind == "model"}
    rates = case_rates(corpus.trials)
    run_rate: dict[str, float] = {}
    for run_id in runs:
        values = [rate for (rid, _), rate in rates.items() if rid == run_id]
        if values:
            run_rate[run_id] = sum(values) / len(values)

    groups: dict[tuple[str, str, str, str], list[Run]] = defaultdict(list)
    for run in runs.values():
        groups[(run.project, run.suite_version, run.variant, run.model)].append(run)

    results = []
    for (project, suite_version, variant, model), members in sorted(groups.items()):
        if len(members) < 2:
            continue
        results.append(
            Drift(
                project=project,
                suite_version=suite_version,
                variant=variant,
                model=model,
                observations=tuple(
                    (run.run_id, run.config, run_rate[run.run_id])
                    for run in sorted(members, key=lambda item: item.run_id)
                    if run.run_id in run_rate
                ),
            )
        )
    return results


@dataclass(frozen=True)
class CaseCost:
    """What one case costs to ask, and whether the answer was worth it."""

    project: str
    suite_version: str
    case_id: str
    trials: int
    seconds: float
    input_tokens: int
    output_tokens: int


def case_cost(corpus: Corpus) -> list[CaseCost]:
    totals: dict[tuple[Scope, str], list[float]] = defaultdict(lambda: [0, 0.0, 0, 0])
    scope_of = {run.run_id: (run.project, run.suite_version) for run in corpus.runs}
    for trial in graded(corpus.trials):
        row = totals[(scope_of[trial.run_id], trial.case_id)]
        row[0] += 1
        row[1] += trial.seconds
        row[2] += trial.input_tokens
        row[3] += trial.output_tokens
    return [
        CaseCost(
            project=scope[0],
            suite_version=scope[1],
            case_id=case,
            trials=int(row[0]),
            seconds=row[1],
            input_tokens=int(row[2]),
            output_tokens=int(row[3]),
        )
        for (scope, case), row in sorted(totals.items())
    ]


@dataclass(frozen=True)
class SilenceCost:
    """The share of a suite's running time that bought no answer."""

    project: str
    suite_version: str
    informative_cases: int
    silent_cases: int
    uncompared_cases: int
    """Cases in a dataset version that no comparison ever used: unjudged, not silent."""
    informative_seconds: float
    silent_seconds: float

    @property
    def wasted_share(self) -> float:
        total = self.informative_seconds + self.silent_seconds
        return self.silent_seconds / total if total else 0.0


def silence_cost(verdicts: list[CaseVerdict], costs: list[CaseCost]) -> list[SilenceCost]:
    """Time spent on cases that never separated two sides, per dataset version."""
    seconds = {(cost.project, cost.suite_version, cost.case_id): cost.seconds for cost in costs}
    grouped: dict[Scope, list[float]] = defaultdict(lambda: [0, 0, 0, 0.0, 0.0])
    for verdict in verdicts:
        scope = (verdict.project, verdict.suite_version)
        spent = seconds.get((verdict.project, verdict.suite_version, verdict.case_id), 0.0)
        if not verdict.comparisons:
            # A dataset version nothing was ever compared on cannot be called wasteful:
            # the corpus simply never asked it a question.
            grouped[scope][2] += 1
            continue
        informative = verdict.label == "informative"
        grouped[scope][0 if informative else 1] += 1
        grouped[scope][3 if informative else 4] += spent
    return [
        SilenceCost(
            project=scope[0],
            suite_version=scope[1],
            informative_cases=int(values[0]),
            silent_cases=int(values[1]),
            uncompared_cases=int(values[2]),
            informative_seconds=values[3],
            silent_seconds=values[4],
        )
        for scope, values in sorted(grouped.items())
    ]


@dataclass(frozen=True)
class VarianceSplit:
    """Where the spread in verdicts comes from, inside one comparison.

    A crude decomposition of a binary outcome, and it is reported as a direction rather
    than a measurement: with 27 cases and three repeats the residual term absorbs
    anything the other two cannot explain, including the interaction between them.
    """

    comparison: str
    between_cases: float
    between_variants: float
    residual: float


def variance_split(corpus: Corpus, comparisons: list[Comparison]) -> list[VarianceSplit]:
    rows: list[VarianceSplit] = []
    for comparison in comparisons:
        outcomes = [trial for trial in graded(corpus.trials) if trial.run_id in comparison.runs]
        if not outcomes:
            continue
        grand = sum(trial.passed for trial in outcomes) / len(outcomes)
        total = sum((trial.passed - grand) ** 2 for trial in outcomes)
        if total == 0:
            rows.append(VarianceSplit(comparison.name, 0.0, 0.0, 0.0))
            continue

        by_case: dict[str, list[bool]] = defaultdict(list)
        by_run: dict[str, list[bool]] = defaultdict(list)
        for trial in outcomes:
            by_case[trial.case_id].append(trial.passed)
            by_run[trial.run_id].append(trial.passed)
        case_ss = sum(
            len(values) * (sum(values) / len(values) - grand) ** 2 for values in by_case.values()
        )
        run_ss = sum(
            len(values) * (sum(values) / len(values) - grand) ** 2 for values in by_run.values()
        )
        rows.append(
            VarianceSplit(
                comparison=comparison.name,
                between_cases=case_ss / total,
                between_variants=run_ss / total,
                residual=max(0.0, 1 - (case_ss + run_ss) / total),
            )
        )
    return rows


@dataclass(frozen=True)
class FailureProfile:
    """Which gates fail, and which ones never fire at all."""

    project: str
    label: str
    trials: int
    runs: int


def failure_profile(corpus: Corpus) -> list[FailureProfile]:
    trials_with: Counter[tuple[str, str]] = Counter()
    runs_with: dict[tuple[str, str], set[str]] = defaultdict(set)
    project_of = {run.run_id: run.project for run in corpus.runs}
    for trial in graded(corpus.trials):
        for label in set(trial.failures):
            key = (project_of[trial.run_id], label)
            trials_with[key] += 1
            runs_with[key].add(trial.run_id)
    return [
        FailureProfile(
            project=project, label=label, trials=count, runs=len(runs_with[(project, label)])
        )
        for (project, label), count in trials_with.most_common()
    ]


def silent_gates(corpus: Corpus) -> list[tuple[str, str, int]]:
    """Gates that a project records on every trial and that never once failed.

    A gate that never fails is either a rule nothing in the suite breaks, or a rule
    written so that nothing can break it. Both are worth knowing; neither is visible
    from a pass rate.
    """
    seen: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    project_of = {run.run_id: run.project for run in corpus.runs}
    for trial in graded(corpus.trials):
        for gate, passed in trial.gates:
            row = seen[(project_of[trial.run_id], gate)]
            row[0] += 1
            row[1] += 0 if passed else 1
    return [
        (project, gate, values[0])
        for (project, gate), values in sorted(seen.items())
        if values[1] == 0
    ]
