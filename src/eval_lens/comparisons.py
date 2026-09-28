"""Which runs may be held against each other, derived rather than declared.

Two runs are comparable when everything a result depends on is equal except the one
thing under test: same project, same dataset version, same model, same configuration —
and the configuration is where the sampling temperature, the wall clock, the harness
version and the scorer version live. In this corpus that rule is not pedantry: the
wall clock alone moved one published conclusion, and the harness version moved another.

Within a comparable group, the control variant is the run everything else is measured
against. Each project names its control differently, which is the only thing this
module has to be told.

A group can also hold the same variant twice. That pair is not a comparison — nothing
differs between its sides — so it is kept apart, as the A/A control: whatever it reports
is what this instrument reports when the answer is known to be nothing.
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
    null_pair: bool = False
    """Both sides are the same variant: an A/A control rather than a comparison."""

    @property
    def runs(self) -> tuple[str, str]:
        return (self.control, self.candidate)


def comparable_key(run: Run) -> tuple[str, ...]:
    return (run.project, run.suite, run.suite_version, run.model, run.config)


def derive(corpus: Corpus) -> list[Comparison]:
    """Every pair inside a comparable group that differs in exactly one variant.

    Fixture runs are excluded: an oracle-driven control and a deliberately corrupted
    one prove that the harness reacts, and comparing them measures nothing about a
    model.
    """
    return [pair for pair in _pairs(corpus) if not pair.null_pair]


def null_pairs(corpus: Corpus) -> list[Comparison]:
    """Pairs whose two sides are the same variant under the same settings.

    An A/A control: the difference it reports is the instrument, not the policy, and the
    cases it separates were separated by sampling alone.
    """
    return [pair for pair in _pairs(corpus) if pair.null_pair]


def _pairs(corpus: Corpus) -> list[Comparison]:
    groups: dict[tuple[str, ...], list[Run]] = defaultdict(list)
    for run in corpus.runs:
        if run.kind == "model":
            groups[comparable_key(run)].append(run)

    pairs: list[Comparison] = []
    for runs in groups.values():
        control_variant = CONTROL_VARIANTS.get(runs[0].project)
        candidates = [run for run in runs if run.variant == control_variant]
        if not candidates:
            continue
        # The earliest run of the control variant is the control, and a tie is broken by
        # run_id. Where a variant was run twice, which side is the control decides what
        # every comparison in the group is measured against, and that must not depend on
        # the order files happened to be read in.
        control = min(candidates, key=lambda run: (run.recorded_at, run.run_id))
        for run in runs:
            if run.run_id == control.run_id:
                continue
            repeated = run.variant == control.variant
            label = f"{run.variant} again" if repeated else run.variant
            pairs.append(
                Comparison(
                    name=f"{run.project}: {control.variant} → {label} ({run.config})",
                    project=run.project,
                    control=control.run_id,
                    candidate=run.run_id,
                    factor=label,
                    config=run.config,
                    null_pair=repeated,
                )
            )
    return sorted(pairs, key=lambda pair: pair.name)
