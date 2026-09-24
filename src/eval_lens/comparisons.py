"""Which runs may be held against each other, derived rather than declared.

Two runs are comparable when everything a result depends on is equal except the one
thing under test: same project, same dataset version, same model, same configuration —
and the configuration is where the sampling temperature, the wall clock, the harness
version and the scorer version live. In this corpus that rule is not pedantry: the
wall clock alone moved one published conclusion, and the harness version moved another.

Within a comparable group, the control variant is the run everything else is measured
against. Each project names its control differently, which is the only thing this
module has to be told.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from eval_lens.model import Corpus, Run

CONTROL_VARIANTS = {
    "mcp-connector-testkit": "clean",  # the connector with no seeded defect
    "agent-eval-lab": "baseline",  # the minimal prompt policy
}


@dataclass(frozen=True)
class Comparison:
    name: str
    project: str
    control: str
    """run_id of the side everything is measured against."""
    candidate: str
    factor: str
    """What differs: the seeded defect, the prompt policy under test."""
    config: str = ""
    """The settings both sides share, kept so a report can say which ones varied."""

    @property
    def runs(self) -> tuple[str, str]:
        return (self.control, self.candidate)


def comparable_key(run: Run) -> tuple[str, ...]:
    return (run.project, run.suite, run.suite_version, run.model, run.config)


def derive(corpus: Corpus) -> list[Comparison]:
    """Every pair inside a comparable group that differs only in variant.

    Fixture runs are excluded: an oracle-driven control and a deliberately corrupted
    one prove that the harness reacts, and comparing them measures nothing about a
    model.
    """
    groups: dict[tuple[str, ...], list[Run]] = defaultdict(list)
    for run in corpus.runs:
        if run.kind == "model":
            groups[comparable_key(run)].append(run)

    comparisons: list[Comparison] = []
    for runs in groups.values():
        control_variant = CONTROL_VARIANTS.get(runs[0].project)
        control = next((run for run in runs if run.variant == control_variant), None)
        if control is None:
            continue
        for run in runs:
            if run.run_id == control.run_id:
                continue
            comparisons.append(
                Comparison(
                    name=f"{run.project}: {control.variant} → {run.variant} ({run.config})",
                    project=run.project,
                    control=control.run_id,
                    candidate=run.run_id,
                    factor=run.variant,
                    config=run.config,
                )
            )
    return sorted(comparisons, key=lambda comparison: comparison.name)
