"""Readers for the formats the two source projects happen to write."""

from __future__ import annotations

from pathlib import Path

from eval_lens.ingest.agent_eval_lab import read_run as read_agent_eval_lab
from eval_lens.ingest.mcpqa import read_run as read_mcpqa
from eval_lens.model import Corpus

__all__ = ["Corpus", "read_agent_eval_lab", "read_corpus", "read_mcpqa"]


def read_corpus(root: Path) -> Corpus:
    """Read every vendored run under `root` (the `data/` directory)."""
    corpus = Corpus()
    for directory in sorted((root / "mcp-connector-testkit").glob("*")):
        if (directory / "trials.jsonl").exists():
            corpus = corpus.extend(read_mcpqa(directory, root))
    for path in sorted((root / "agent-eval-lab").glob("*.json")):
        corpus = corpus.extend(read_agent_eval_lab(path, root))
    return corpus
