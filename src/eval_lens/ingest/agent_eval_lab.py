"""agent-eval-lab: one JSON file per run, with every gate and every tool attempt in it.

This project already names its gates, so nothing is classified here. What it does not
carry is a timestamp, so the date comes from the directory name the run was published
under, which is how its own reports refer to it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from eval_lens.model import Corpus, Run, ToolCall, Trial

DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def read_run(path: Path, root: Path) -> Corpus:
    payload: dict[str, Any] = json.loads(path.read_text())
    provenance: dict[str, Any] = payload.get("provenance", {})
    name = path.stem
    fixture = payload["kind"] != "model"
    run = Run(
        run_id=f"lab:{name}",
        project="agent-eval-lab",
        suite="calendar-assistant-scenarios",
        suite_version=str(provenance.get("dataset_hash", ""))[:12] or "fixture",
        variant=str(payload["variant"]),
        model=str(provenance.get("model") or "oracle-fixture"),
        config=_config(provenance),
        recorded_at=(found.group(1) if (found := DATE.search(name)) else ""),
        kind="fixture" if fixture else "model",
        source=str(path.relative_to(root)),
    )

    rows: list[Trial] = []
    calls: list[ToolCall] = []
    for result in payload["results"]:
        case_id, repeat = str(result["scenario_id"]), int(result["trial"])
        usage = result.get("usage") or {}
        rows.append(
            Trial(
                run_id=run.run_id,
                case_id=case_id,
                family=str(result["family"]),
                repeat=repeat,
                passed=bool(result["passed"]),
                error=str(result.get("error") or ""),
                failures=tuple(str(item) for item in result.get("failures", [])),
                gates=tuple(
                    (str(gate), bool(value)) for gate, value in sorted(result["checks"].items())
                ),
                tools=tuple(str(call["name"]) for call in result.get("trace", [])),
                tool_calls=int(result.get("tool_calls", 0)),
                input_tokens=sum(int(item.get("input_tokens", 0)) for item in usage.values()),
                output_tokens=sum(int(item.get("output_tokens", 0)) for item in usage.values()),
                seconds=float(result.get("elapsed_seconds") or 0.0),
            )
        )
        for seq, call in enumerate(result.get("trace", [])):
            calls.append(
                ToolCall(
                    run_id=run.run_id,
                    case_id=case_id,
                    repeat=repeat,
                    seq=seq,
                    name=str(call["name"]),
                    ok=bool((call.get("result") or {}).get("ok", False)),
                )
            )
    return Corpus(runs=[run], trials=rows, tool_calls=calls)


def _config(provenance: dict[str, Any]) -> str:
    """The settings a comparison must hold constant, including the wall clock.

    The wall clock belongs here because it already decided one comparison in this
    corpus: the longer policy hit a 120-second limit nine times against the baseline's
    two, which charged thinking time to the model.
    """
    evaluation: dict[str, Any] = provenance.get("eval_config") or {}
    generation: dict[str, Any] = provenance.get("generation_config") or {}
    parts = [
        f"epochs={evaluation.get('epochs', '?')}",
        f"time_limit={evaluation.get('time_limit', '?')}",
        f"max_tokens={generation.get('max_tokens', '?')}",
        f"scorer={provenance.get('scorer_version', '?')}",
    ]
    return ";".join(parts)
