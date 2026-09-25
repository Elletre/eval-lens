# eval-lens

**Measure the measuring instrument.** An eval suite is supposed to tell you whether a change
made a system better. This asks the question one step back: how much of the suite carries
information at all, how much of what it reports is its own noise, and what each answer costs.

![python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue)
![clickhouse](https://img.shields.io/badge/ClickHouse-chDB%20(embedded)-ffcc01)
![otel](https://img.shields.io/badge/OpenTelemetry-GenAI%20spans-4d4dff)
![license](https://img.shields.io/badge/license-MIT-green)

Nobody publishes the fraction of their eval suite that never separated two candidates. It is
not a flattering number, and it is not hard to compute: every run you have already recorded
contains it. This repository computes it — along with the suite's noise floor, the time spent
on cases that cannot answer anything, the gates that have never once failed, and what happens
to published conclusions when the silent cases are removed.

## The corpus is real, and it is not this project's

Two public repositories of mine recorded **1,179 trials** across 16 runs over five days: an
[MCP connector test kit](https://github.com/Elletre/mcp-connector-testkit) scoring a connector
against seeded defects, and an [agent evaluation lab](https://github.com/Elletre/agent-eval-lab)
scoring an assistant against deterministic gates. Their artifacts are vendored here verbatim,
including the runs both repositories keep as evidence of a mistake rather than as results.
Provenance, down to the source commit, is in [`data/MANIFEST.md`](data/MANIFEST.md).

Those two suites were written carefully, by someone who was trying. That is what makes them
worth measuring: the findings below are not about a careless suite.

## What it found

Read [**REPORT.md**](REPORT.md) — it is generated, and CI fails if it drifts from the data.
Every number in it comes from a query in [`sql/`](sql) or its twin in
[`metrics.py`](src/eval_lens/metrics.py), and a test holds the two equal.

- **A third to a half of each suite never separated anything.** Of the connector suite's 27
  cases at its current dataset version, 12 are informative and 15 are saturated, floored or
  merely noisy; the assistant suite is 19 informative out of 27. Two whole families — six
  prompt-injection cases, six context-pressure cases — have never once told two candidates
  apart.
- **The instrument disagrees with itself on 35% of the cases it repeats** (assistant suite,
  `qwen3:8b`), against 7% for the connector suite's more mechanical checks.
- **The same policy moves 14 points between runs** when nothing about the policy changed —
  which is the floor under any difference these suites can claim.
- **22% to 39% of the running time goes to cases that answer nothing.**
- **Two gates recorded on 565 trials have never failed.** Either nothing in the suite breaks
  those rules, or the rules are written so that nothing can. A pass rate cannot see the
  difference.
- **The thing under test is usually the smallest term** in the spread of verdicts: cases differ
  from each other far more than the variants differ from each other.

And the claim the project was built to test, fixed in writing before it was computed:

> Remove the cases with no discriminating power and the published conclusions do not change,
> while the suite gets materially shorter.

**It held: 7 of 7 comparisons keep their verdict at 5%, with 18% to 55% of the running time
removed.** Each comparison was recomputed on the cases that *other* comparisons found
informative, never on the ones it decided itself — otherwise the answer is true by
construction. The effects got *larger* on the shorter suite, because the silent cases had been
averaging them down.

## Quick start

```bash
git clone https://github.com/Elletre/eval-lens
cd eval-lens
uv sync --all-groups
make check                      # lint, types, tests, and the report diff
```

```bash
uv run eval-lens ingest         # 16 runs, 1179 trials, 7 comparisons
uv run eval-lens query          # the questions, by name
uv run eval-lens query silence_cost
uv run eval-lens report         # regenerate REPORT.md
uv run eval-lens export --out /tmp/eval-lens    # the tables, for a real ClickHouse
uv run eval-lens trace <run-id> --console       # one run as OpenTelemetry spans
```

## How it works

```
committed run artifacts of two repositories
        │   eval-lens ingest      one schema, three source formats
        ▼
   ClickHouse (chDB, in process)  ──►  sql/*.sql  ──►  eval-lens report ──► REPORT.md
        │
        └── eval-lens export      the same tables, for a ClickHouse that is a server

   the same corpus ── eval-lens trace ──► OTLP ──► Langfuse, or any receiver
```

**Ingest** reads the formats the two projects happened to write and normalises them into
`runs`, `trials` and `tool_calls`. Project-specific vocabulary — gate names, families, failure
wording — is preserved rather than translated, so a question that only makes sense inside one
project stays inside it. Loading twice does not double anything.

**Comparability is derived, not declared.** Two runs may be held against each other only when
project, dataset version, model and configuration match and exactly one variant differs. The
configuration fingerprint includes the sampling temperature, the wall clock, the harness
version and the scorer version — in this corpus that is not pedantry: the wall clock alone
moved one published conclusion, and the harness version moved another.

**Every metric is written twice**, in Python and in ClickHouse SQL, and
[a test](tests/test_sql_parity.py) holds the two equal. A query nobody verified is an
instrument nobody calibrated, which is the whole subject of this repository.

**Why ClickHouse for 1,179 rows.** It is overkill, and that is said out loud. It is here
because the schema and the queries *are* the artifact: they are what moves to a server when
the corpus is a hundred million trials instead of a thousand, and `eval-lens export` writes the
tables so that move is a command rather than a promise. chDB runs the same engine in process,
so CI needs no container.

**Traces are for eyes, not for numbers.** `eval-lens trace` replays a recorded run as GenAI
spans — one `invoke_agent` per trial, `execute_tool` children inside it — for a trace viewer
such as Langfuse. The durations are the real recorded ones; the timestamps are not, because the
artifacts say how long each attempt took and not when it started. Nothing in the report is
computed from the traces. See [docs/replay.md](docs/replay.md).

## What is in the repository

```
src/eval_lens/
  ingest/          three source formats → one schema
  schema.sql       four tables and the view the questions build on
  comparisons.py   which runs may be compared, and which pair is an A/A control
  metrics.py       every measurement, as pure functions
  otlp.py          a recorded run as OpenTelemetry spans
  report.py        the report, assembled from the queries and nothing else
  store.py         embedded ClickHouse
sql/               the same questions in SQL, readable on their own
data/              16 vendored runs and where each came from
docs/method.md     definitions: units, comparability, every metric, the claim
docs/replay.md     the trace side: attributes, receivers, what the timestamps mean
REPORT.md          generated; CI fails when it stops matching the data
```

## What this does not show

- **The corpus is two suites written by one person, scored by two small local models over five
  days.** A saturated case is saturated *for these models*; a case that never moved might move
  against a better one. The same measurements on a larger corpus would be worth more, and the
  queries would not change.
- **Nothing here judges the models.** A suite that cannot separate two policies is a statement
  about the suite.
- **The variance decomposition is shaky** on twenty-seven cases and is reported as a direction,
  not a measurement. No conclusion rests on it.
- **No dashboard.** The artifact is the report, the queries and the tests; the trace viewer is
  an illustration.
- **The GenAI semantic conventions are still in development.** The version the attributes follow
  is named in [`otlp.py`](src/eval_lens/otlp.py), and it is not presented as stable.

## License

MIT.
