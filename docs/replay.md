# Replaying a recorded run as traces

`eval-lens trace` turns one recorded run into OpenTelemetry spans and sends them to any OTLP
receiver. It exists because the corpus already contains everything a trace needs — a duration
per trial, the model, the token counts, the tools in the order they were called — and because
the questions this project asks in SQL are not the questions a person asks while staring at
one bad trial.

```bash
uv run eval-lens trace                      # the run ids it can replay
uv run eval-lens trace <run-id> --console   # print the spans, send nothing
```

## What a trial becomes

One trial becomes one `invoke_agent {variant}` span with an `execute_tool {name}` child for
each tool call, in order. Attributes follow the GenAI semantic conventions where they have a
name for something, and are prefixed `eval.` where they do not:

| Attribute | Value |
| --- | --- |
| `gen_ai.operation.name` | `invoke_agent`, or `execute_tool` on a child |
| `gen_ai.agent.name` | the variant under test |
| `gen_ai.request.model` | e.g. `ollama/qwen3:8b` |
| `gen_ai.usage.input_tokens` / `.output_tokens` | as the run recorded them |
| `gen_ai.tool.name` | on each child span |
| `eval.case_id`, `eval.family`, `eval.repeat` | which case, and which attempt at it |
| `eval.passed`, `eval.failures` | the verdict and the labels behind it |
| `eval.stopped_by_harness` | the attempt hit a limit and carries no verdict |
| `eval.project`, `eval.run_id`, `eval.suite_version` | provenance, also on the resource |

A failing trial is **not** a failing span. The span status is set only where the harness cut
the attempt short: a model that answered wrongly produced a result, not an error, and a trace
viewer that paints those red hides the ones that actually broke.

## Sending it somewhere

Credentials are read from the environment; nothing is passed on the command line, and no key
belongs in this repository.

**Langfuse Cloud** — create a project, take its two keys:

```bash
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
uv run eval-lens trace lab:experiments__2026-09-22-qwen3-8b__improved
```

The two keys become HTTP Basic auth against `$LANGFUSE_HOST/api/public/otel/v1/traces`, where
`LANGFUSE_HOST` defaults to `https://cloud.langfuse.com`. Self-hosted Langfuse is the same two
keys and a different host:

```bash
export LANGFUSE_HOST=http://localhost:3000
```

**Any other OTLP receiver** — a collector, Jaeger, Grafana Tempo, Phoenix — is configured the
standard way, and the exporter does not know the difference:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
export OTEL_EXPORTER_OTLP_HEADERS='x-api-key=...'
```

All 81 trials of one run arrive under one `langfuse.session.id`, so a run reads as a session
rather than as eighty-one unrelated traces. That is the only vendor-specific attribute in the
exporter; every other receiver ignores it.

## What the timestamps are

**The durations are real. The times are not.** The trials are laid end to end from the moment
the command runs, because the source artifacts record how long each attempt took and not when
it started. A trace view of this data answers "what happened inside this trial, and how long
did each part take"; it cannot answer "what was happening at 14:32", and a replay that looked
like live traffic would be a lie told with true numbers.

Nothing in the report is computed from the traces. The replay is for looking at one trial with
human eyes; the measurements come from the corpus, through SQL, and are checked by tests.
