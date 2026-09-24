"""One shape for runs that were never meant to be compared with each other.

The two source projects answer different questions with different vocabularies: one
scores an MCP connector against seeded defects, the other scores an assistant against
deterministic gates. What they share is the shape of the evidence — a run made of
trials, a trial belonging to a case, a verdict, what it cost and what went wrong — and
that is all this schema keeps.

Anything project-specific (gate names, failure wording, families) is preserved as it was
written rather than translated, so a question that only makes sense inside one project
stays inside it.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Run:
    """One execution of one suite under one configuration."""

    run_id: str
    project: str
    suite: str
    """The dataset the run was scored against, as the project names it."""
    suite_version: str
    """Dataset hash where the project records one; otherwise a stand-in like a split name."""
    variant: str
    """What was under test: a seeded defect, a prompt policy, a control fixture."""
    model: str
    config: str
    """Fingerprint of the settings a comparison must hold constant."""
    recorded_at: str
    kind: str
    """`model` for a real model run, `fixture` for an oracle-driven control."""
    source: str
    """Path inside data/, so every row can be traced back to the bytes it came from."""


@dataclass(frozen=True)
class Trial:
    """One attempt at one case: the unit that gets a verdict."""

    run_id: str
    case_id: str
    family: str
    repeat: int
    passed: bool
    error: str
    """Set when the harness, not the model, ended the attempt. Excluded from rates."""
    failures: tuple[str, ...]
    """Canonical labels: gate names where a project has them, classified text where it does not."""
    gates: tuple[tuple[str, bool], ...] = ()
    """Every gate and its outcome, where the project records them. Empty otherwise."""
    tools: tuple[str, ...] = ()
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0


@dataclass(frozen=True)
class ToolCall:
    """One tool attempt inside a trial, in the order it happened."""

    run_id: str
    case_id: str
    repeat: int
    seq: int
    name: str
    ok: bool


@dataclass(frozen=True)
class Corpus:
    runs: list[Run] = field(default_factory=list)
    trials: list[Trial] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)

    def extend(self, other: Corpus) -> Corpus:
        return Corpus(
            runs=[*self.runs, *other.runs],
            trials=[*self.trials, *other.trials],
            tool_calls=[*self.tool_calls, *other.tool_calls],
        )
