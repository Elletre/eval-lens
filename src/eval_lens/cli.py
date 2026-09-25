"""The commands: load the corpus, ask it the questions, write the report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SpanExporter

from eval_lens import otlp, queries, report
from eval_lens.comparisons import Comparison, derive
from eval_lens.ingest import read_corpus
from eval_lens.model import Corpus
from eval_lens.store import SCHEMA, Store, tables, write

ROOT = Path(__file__).resolve().parents[2]


def _loaded(data: Path, database: Path | None) -> tuple[Store, Corpus, list[Comparison]]:
    corpus = read_corpus(data)
    comparisons = derive(corpus)
    store = Store(database)
    store.load(corpus, comparisons)
    return store, corpus, comparisons


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
    dumped = commands.add_parser("export", help="write the tables as files a server can load")
    dumped.add_argument("--out", type=Path, required=True, help="directory to write into")
    traced = commands.add_parser("trace", help="replay one recorded run as OTLP spans")
    traced.add_argument("run", nargs="?", help="run_id; omit to list them")
    traced.add_argument(
        "--console",
        action="store_true",
        help="print the spans instead of sending them anywhere",
    )

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
            text = report.render(store, corpus, comparisons)
            args.out.write_text(text, encoding="utf-8")
            print(f"wrote {args.out}")
        elif args.command == "export":
            print("\n".join(str(path) for path in store_files(corpus, comparisons, args.out)))
        elif args.command == "trace":
            return _trace(corpus, args.run, console=args.console)
    finally:
        store.close()
    return 0


def store_files(corpus: Corpus, comparisons: list[Comparison], out: Path) -> list[Path]:
    """The corpus as loadable files, schema included, so it can live in a real server."""
    written = [path for path in write(tables(corpus, comparisons), out).values() if path]
    schema = out / "schema.sql"
    schema.write_text(SCHEMA.read_text(), encoding="utf-8")
    return [schema, *written]


def _trace(corpus: Corpus, run_id: str | None, *, console: bool) -> int:
    """Send one run to a receiver, or say which runs there are to send."""
    runs = sorted(run.run_id for run in corpus.runs)
    if not run_id:
        print("\n".join(runs))
        return 0
    if run_id not in runs:
        print(f"no run named {run_id}; run `eval-lens trace` for the list")
        return 2

    if console:
        exporter: SpanExporter = ConsoleSpanExporter()
        destination = "stdout"
    else:
        try:
            target = otlp.receiver()
        except KeyError as missing:
            print(missing.args[0])
            return 2
        exporter = target.exporter()
        destination = target.origin

    replay = otlp.export_run(corpus, run_id, exporter)
    print(
        f"sent {replay.trials} invocations and {replay.tool_calls} tool calls "
        f"({replay.spans} spans) to {destination}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
