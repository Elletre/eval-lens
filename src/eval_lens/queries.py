"""The questions, as files.

Each file in `sql/` answers one of them against the tables in `schema.sql`, and each has
a twin in `metrics.py` written in Python. A test runs both and requires the same rows: a
query nobody checks is a claim nobody checked, and this project is entirely made of
claims computed from data.
"""

from __future__ import annotations

from pathlib import Path

SQL = Path(__file__).resolve().parents[2] / "sql"


def read(name: str) -> str:
    """The text of one query, by file stem."""
    path = SQL / f"{name}.sql"
    if not path.exists():
        raise FileNotFoundError(f"no query named {name} in {SQL}")
    return path.read_text()


def names() -> list[str]:
    return sorted(path.stem for path in SQL.glob("*.sql"))
