"""The commands: load the corpus, ask it the questions, write the report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval_lens import queries, report
from eval_lens.comparisons import derive
from eval_lens.ingest import read_corpus
from eval_lens.store import Store

ROOT = Path(__file__).resolve().parents[2]


def _loaded(data: Path, database: Path | None) -> tuple[Store, object, list[object]]:
    corpus = read_corpus(data)
    comparisons = derive(corpus)
    store = Store(database)
    store.load(corpus, comparisons)
    return store, corpus, comparisons  # type: ignore[return-value]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval-lens", description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data", help="corpus directory")
    parser.add_argument("--db", type=Path, default=None, help="keep the database on disk here")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("ingest", help="load the corpus and print what arrived")
    asked = commands.add_parser("query", help="run one query from sql/")
    asked.add_argument("name", nargs="?", help="query name; omit to list them")
    written = commands.add_parser("report", help="write the report")
    written.add_argument("--out", type=Path, default=ROOT / "REPORT.md")

    args = parser.parse_args(argv)
    if args.command == "query" and not args.name:
        print("\n".join(queries.names()))
        return 0

    store, corpus, comparisons = _loaded(args.data, args.db)
    try:
        if args.command == "ingest":
            counts = store.query("SELECT count() AS trials, uniqExact(run_id) AS runs FROM trials")[
                0
            ]
            print(
                f"{counts['runs']} runs, {counts['trials']} trials, {len(comparisons)} comparisons"
            )
        elif args.command == "query":
            for row in store.query(queries.read(args.name)):
                print(json.dumps(row, ensure_ascii=False))
        elif args.command == "report":
            text = report.render(store, corpus, comparisons)  # type: ignore[arg-type]
            args.out.write_text(text, encoding="utf-8")
            print(f"wrote {args.out}")
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
