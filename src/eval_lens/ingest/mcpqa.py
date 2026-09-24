"""mcp-connector-testkit: one JSONL file of trials, plus a summary when the run finished.

Its failures are sentences written for a person ("answered without looking: called none
of [...]"), not gate names. They are classified into labels here, and the original text
is left in the file it came from: a label that turns out to be wrong should send the
reader back to the trial, not to a translation of it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from eval_lens.model import Corpus, Run, ToolCall, Trial

# Ordered: the first pattern that matches wins.
FAILURE_LABELS: tuple[tuple[str, str], ...] = (
    (r"^expected .* first", "wrong_first_tool"),
    (r"^answered without looking", "answered_without_looking"),
    (r"^never called", "missing_required_tool"),
    (r"^called forbidden tool", "forbidden_tool"),
    (r"was never called with|expected one of", "wrong_arguments"),
    (r"^the answer does not mention|^the answer mentions none of", "missing_fact"),
    (r"^the answer contains", "leaked_fact"),
    (r"^the mailbox changed", "unexpected_state_change"),
    (r"^expected a new fact", "missing_state_change"),
    (r"^expected a removed fact", "missing_removal"),
    (r"^removed \d+ facts", "removed_too_much"),
    (r"^a tool returned \d+ characters", "over_output_budget"),
    (r"^the episode ended without an answer", "no_answer"),
    (r"unreadable turn", "unreadable_turn"),
)


def classify(failure: str) -> str:
    for pattern, label in FAILURE_LABELS:
        if re.search(pattern, failure):
            return label
    return "other"


def read_run(directory: Path, root: Path) -> Corpus:
    name = directory.name
    trials = [
        json.loads(line)
        for line in (directory / "trials.jsonl").read_text().splitlines()
        if line.strip()
    ]
    summary: dict[str, Any] = {}
    summary_path = directory / "summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())

    environment = str(summary.get("environment", ""))
    run = Run(
        run_id=f"mcpqa:{name}",
        project="mcp-connector-testkit",
        suite="acme-mail-cases",
        # The dataset changed shape once; the archived partial run is the only survivor of v1.
        suite_version="v1" if "dataset-v1" in name else "v2",
        # `acme-mail+vague-tool-descriptions` means the connector carried that defect.
        variant=environment.partition("+")[2] or "clean",
        # The project writes the sampling temperature into the model name; it belongs
        # in the configuration fingerprint, not in the model identity.
        model=str(summary.get("model", "ollama/llama3:latest")).split(" at temperature")[0],
        config=_config(name, summary),
        recorded_at=str(summary.get("started_at", ""))[:10] or name[:10],
        kind="model",
        source=str(directory.relative_to(root)),
    )

    rows: list[Trial] = []
    calls: list[ToolCall] = []
    for trial in trials:
        rows.append(
            Trial(
                run_id=run.run_id,
                case_id=str(trial["case_id"]),
                family=str(trial["category"]),
                repeat=int(trial["repeat"]),
                passed=bool(trial["passed"]),
                error=str(trial.get("error") or ""),
                failures=tuple(classify(str(item)) for item in trial.get("failures", [])),
                tools=tuple(str(item) for item in trial.get("tools_called", [])),
                tool_calls=len(trial.get("tools_called", [])),
                input_tokens=int(trial.get("input_tokens", 0)),
                output_tokens=int(trial.get("output_tokens", 0)),
                seconds=float(trial.get("seconds", 0.0)),
            )
        )
        for seq, tool in enumerate(trial.get("tools_called", [])):
            calls.append(
                ToolCall(
                    run_id=run.run_id,
                    case_id=str(trial["case_id"]),
                    repeat=int(trial["repeat"]),
                    seq=seq,
                    name=str(tool),
                    # This project records which tools ran, not how each one ended.
                    ok=True,
                )
            )
    return Corpus(runs=[run], trials=rows, tool_calls=calls)


def _config(name: str, summary: dict[str, Any]) -> str:
    """What two runs must share before their difference means anything."""
    model = str(summary.get("model", ""))
    temperature = model.partition(" at temperature ")[2] or "0"
    harness = "v1" if "harness-v1" in name else "v2"
    repeats = summary.get("repeats", 3)
    return f"temperature={temperature};repeats={repeats};harness={harness}"
