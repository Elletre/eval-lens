"""The committed report must be what the corpus currently says.

A report that drifts from its data is worse than no report: it reads exactly the same.
"""

from pathlib import Path

from eval_lens import report
from eval_lens.cli import main
from eval_lens.comparisons import derive
from eval_lens.ingest import read_corpus
from eval_lens.store import Store

ROOT = Path(__file__).resolve().parents[1]


def test_the_committed_report_is_current():
    corpus = read_corpus(ROOT / "data")
    store = Store()
    try:
        comparisons = derive(corpus)
        store.load(corpus, comparisons)
        rendered = report.render(store, corpus, comparisons)
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
