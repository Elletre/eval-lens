"""The committed picture must be what the corpus and the exporter currently produce."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from trace_svg import OUT, render  # noqa: E402 - the tools directory is not a package


def test_the_committed_trace_picture_is_current():
    assert OUT.read_text(encoding="utf-8") == render(), (
        "run `uv run python tools/trace_svg.py` and commit the result"
    )
