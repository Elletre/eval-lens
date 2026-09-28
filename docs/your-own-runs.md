# Pointing this at your own runs

Nothing here is specific to the two suites in `data/`. What the measurements need is four
facts per attempt, and an adapter that produces them.

## What a suite has to record

| Fact | Why it is needed | Without it |
| --- | --- | --- |
| **case id** | every question is per case | nothing works |
| **repeat number** | repeats of one case under unchanged settings | no noise measurement |
| **verdict** | pass or fail | nothing works |
| **duration** | what the case costs | no cost of silence |
| *labels of what failed* | the failure profile and the silent gates | those two sections are empty |
| *tool calls, tokens* | the trace replay and the token columns | the replay is thinner |

Two more facts belong to the **run**, not the attempt, and they decide what may be compared
with what: the dataset version (a hash if you have one) and a configuration fingerprint —
every setting that could move a result and is not the thing under test. In this corpus that
fingerprint is what caught a wall clock and a harness version changing published conclusions,
so it is worth being generous about what goes in it.

## The adapter

An adapter is one function: bytes on disk in, `Corpus` out. The dataclasses are in
[`model.py`](../src/eval_lens/model.py) and there is nothing else to implement.

```python
from eval_lens.model import Corpus, Run, Trial

def read_run(path: Path, root: Path) -> Corpus:
    payload = json.loads(path.read_text())
    run = Run(
        run_id=f"mine:{path.stem}",
        project="my-suite",
        suite="my-dataset",
        suite_version=payload["dataset_hash"][:12],
        variant=payload["variant"],          # the thing under test
        model=payload["model"],
        config=f"temperature={payload['temperature']};scorer={payload['scorer']}",
        recorded_at=payload["date"],
        kind="model",                        # "fixture" for an oracle-driven control
        source=str(path.relative_to(root)),
    )
    trials = [
        Trial(
            run_id=run.run_id,
            case_id=row["case"],
            family=row["category"],
            repeat=row["repeat"],
            passed=row["passed"],
            error=row.get("stopped_by_limit", ""),   # excluded from every rate
            failures=tuple(row.get("failures", ())),
            seconds=row["seconds"],
        )
        for row in payload["results"]
    ]
    return Corpus(runs=[run], trials=trials)
```

Register it in [`ingest/__init__.py`](../src/eval_lens/ingest/__init__.py) and everything else
— the comparisons, the queries, the report, the replay — follows, because nothing downstream
knows which project a row came from.

## Two things worth copying whether or not you use this

**Say what a stopped attempt is.** A trial the harness ended on a limit carries no verdict
about the model. Scored as a failure it becomes a measurement of your wall clock; one of the
source suites published a conclusion that way before catching it.

**Keep the runs you are not proud of.** Half of what this project can see comes from runs that
were kept as evidence of a mistake — a scorer that rejected valid answers, a harness that
answered on the connector's behalf. Deleting them removes the only record of how the
instrument behaves when it is wrong.
