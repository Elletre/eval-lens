"""ClickHouse without a ClickHouse server.

chDB is the same engine in process, so the SQL in `sql/` is the SQL a server would run,
and CI needs no container. At a few thousand trials a server would be a liability; at a
few hundred million the same queries move to one, which is the point of keeping them in
files rather than in Python.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from chdb import session as chdb_session

from eval_lens.comparisons import Comparison
from eval_lens.model import Corpus

SCHEMA = Path(__file__).parent / "schema.sql"
DATABASE = "eval_lens"

Row = dict[str, Any]

STRUCTURES = {
    "runs": (
        "run_id String, project String, suite String, suite_version String, variant String, "
        "model String, config String, recorded_at String, kind String, source String"
    ),
    "trials": (
        "run_id String, case_id String, family String, repeat UInt16, passed UInt8, error String, "
        "failures Array(String), gates Map(String, UInt8), tools Array(String), tool_calls UInt16, "
        "input_tokens UInt32, output_tokens UInt32, seconds Float64"
    ),
    "tool_calls": (
        "run_id String, case_id String, repeat UInt16, seq UInt16, name String, ok UInt8"
    ),
    "comparisons": ("name String, project String, control String, candidate String, factor String"),
}


class Store:
    """An embedded ClickHouse holding one corpus."""

    def __init__(self, path: Path | None = None) -> None:
        self._session = chdb_session.Session(str(path) if path else None)
        self._session.query(f"CREATE DATABASE IF NOT EXISTS {DATABASE}")
        self._session.query(f"USE {DATABASE}")
        for statement in SCHEMA.read_text().split(";"):
            if statement.strip():
                self._session.query(statement)

    def query(self, sql: str, **parameters: str | int | float) -> list[dict[str, Any]]:
        """Run a statement and return rows as dictionaries."""
        text = sql.format(**parameters) if parameters else sql
        result = self._session.query(f"USE {DATABASE}; {text}", "JSONEachRow")
        payload = str(result).strip()
        return [json.loads(line) for line in payload.splitlines() if line.strip()]

    def load(self, corpus: Corpus, comparisons: list[Comparison] | None = None) -> None:
        """Replace the contents with this corpus. Loading twice must not double anything."""
        with TemporaryDirectory() as directory:
            for table, path in write(tables(corpus, comparisons), Path(directory)).items():
                self._session.query(f"TRUNCATE TABLE {DATABASE}.{table}")
                if path is None:
                    continue
                self._session.query(
                    f"INSERT INTO {DATABASE}.{table} "
                    f"SELECT * FROM file('{path}', JSONEachRow, '{STRUCTURES[table]}')"
                )

    def close(self) -> None:
        self._session.close()


def tables(corpus: Corpus, comparisons: list[Comparison] | None = None) -> dict[str, list[Row]]:
    """The corpus as rows, in the column types the schema declares."""
    return {
        "runs": [asdict(run) for run in corpus.runs],
        "trials": [_trial_row(trial) for trial in corpus.trials],
        "tool_calls": [asdict(call) | {"ok": int(call.ok)} for call in corpus.tool_calls],
        "comparisons": [asdict(comparison) for comparison in comparisons or []],
    }


def write(rows: dict[str, list[Row]], directory: Path) -> dict[str, Path | None]:
    """One JSONEachRow file per table, which is what both chDB and a server can read."""
    directory.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path | None] = {}
    for table, values in rows.items():
        if not values:
            written[table] = None
            continue
        path = directory / f"{table}.jsonl"
        path.write_text("\n".join(json.dumps(value) for value in values), encoding="utf-8")
        written[table] = path
    return written


def _trial_row(trial: Any) -> dict[str, Any]:
    row = asdict(trial)
    row["passed"] = int(trial.passed)
    row["gates"] = {gate: int(passed) for gate, passed in trial.gates}
    row["failures"] = list(trial.failures)
    row["tools"] = list(trial.tools)
    return row
