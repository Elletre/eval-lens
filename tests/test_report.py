"""The committed report must be what the corpus currently says.

A report that drifts from its data is worse than no report: it reads exactly the same.
"""

from pathlib import Path

from eval_lens import report
from eval_lens.cli import main
from eval_lens.comparisons import derive, null_pairs
from eval_lens.ingest import read_corpus
from eval_lens.store import Store

ROOT = Path(__file__).resolve().parents[1]


def test_the_committed_report_is_current():
    corpus = read_corpus(ROOT / "data")
    store = Store()
    try:
        comparisons = derive(corpus)
        store.load(corpus, comparisons)
        rendered = report.render(store, corpus, comparisons, null_pairs(corpus))
    finally:
        store.close()
    committed = (ROOT / "REPORT.md").read_text()
    assert rendered == committed, "run `uv run eval-lens report` and commit the result"


def test_the_report_is_the_same_twice(tmp_path):
    first, second = tmp_path / "one.md", tmp_path / "two.md"
    assert main(["report", "--out", str(first)]) == 0
    assert main(["report", "--out", str(second)]) == 0
    assert first.read_text() == second.read_text(), "the report must not depend on when it ran"


def test_ingest_and_query_run_from_the_command_line(capsys):
    assert main(["ingest"]) == 0
    assert "16 runs, 1179 trials, 7 comparisons" in capsys.readouterr().out
    assert main(["query"]) == 0
    assert "case_information" in capsys.readouterr().out
    assert main(["query", "silence_cost"]) == 0
    assert "informative_cases" in capsys.readouterr().out


def test_trace_lists_the_runs_and_replays_one_without_a_receiver(capsys, monkeypatch):
    for variable in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "OTEL_EXPORTER_OTLP_ENDPOINT"):
        monkeypatch.delenv(variable, raising=False)
    assert main(["trace"]) == 0
    listed = capsys.readouterr().out
    assert "mcpqa:2026-09-18-llama3-8b-baseline" in listed

    assert main(["trace", "nope"]) == 2
    assert main(["trace", "mcpqa:2026-09-18-llama3-8b-baseline", "--console"]) == 0
    assert "sent 81 invocations" in capsys.readouterr().out

    assert main(["trace", "mcpqa:2026-09-18-llama3-8b-baseline"]) == 2
    assert "no OTLP receiver configured" in capsys.readouterr().out
