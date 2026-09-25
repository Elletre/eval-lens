"""Recorded runs, replayed as OpenTelemetry spans.

A trial is an agent invocation with tool calls inside it, which is a shape the GenAI
semantic conventions already describe, so a trace viewer that knows nothing about either
source project can still show what happened. Langfuse is the one shown in the README; the
exporter speaks plain OTLP and does not care.

The timestamps are reconstructed from the recorded durations. They are the real durations
of the real trials, laid end to end from a chosen start: a replay, not a measurement of
when it happened.

The attribute names follow the GenAI semantic conventions as they stand in
`opentelemetry-semantic-conventions` 0.65b0, where they are still marked development and
still live in a private module — so they are written out here rather than imported, and
everything this project invents is prefixed `eval.`. When the conventions move, the
`gen_ai.*` names change and nothing else does.

A failed trial is not a failed span. The span status is set only where the harness stopped
the attempt: a model that answered wrongly produced a result, not an error, and a trace
viewer that paints those red hides the ones that actually broke.
"""

from __future__ import annotations

import base64
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime

from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.trace import Span, SpanKind, Tracer, set_span_in_context
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util.types import AttributeValue

from eval_lens.model import Corpus, Run, ToolCall, Trial

NANOSECOND = 1_000_000_000
LANGFUSE_CLOUD = "https://cloud.langfuse.com"


@dataclass(frozen=True)
class Replay:
    spans: int
    trials: int
    tool_calls: int


@dataclass(frozen=True)
class Receiver:
    """Where the spans are sent, resolved from the environment rather than from flags.

    Keys never appear in a command line or in this repository: Langfuse Cloud wants its
    project keys as HTTP Basic auth, any other OTLP receiver is configured through the
    standard `OTEL_EXPORTER_OTLP_*` variables, and both paths end in the same exporter.
    """

    endpoint: str
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def origin(self) -> str:
        """The endpoint without its path, which is the part that is safe to print."""
        scheme, _, rest = self.endpoint.partition("://")
        return f"{scheme}://{rest.partition('/')[0]}" if rest else self.endpoint

    def exporter(self) -> SpanExporter:
        return OTLPSpanExporter(endpoint=self.endpoint, headers=self.headers)


def receiver(env: Mapping[str, str] | None = None) -> Receiver:
    """The configured receiver, or a KeyError naming the variables that would set one."""
    env = os.environ if env is None else env
    public, secret = env.get("LANGFUSE_PUBLIC_KEY"), env.get("LANGFUSE_SECRET_KEY")
    if public and secret:
        host = env.get("LANGFUSE_HOST") or LANGFUSE_CLOUD
        token = base64.b64encode(f"{public}:{secret}".encode()).decode()
        return Receiver(
            endpoint=f"{host.rstrip('/')}/api/public/otel/v1/traces",
            headers={"Authorization": f"Basic {token}"},
        )
    signal = env.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    base = env.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not signal and not base:
        raise KeyError(
            "no OTLP receiver configured: set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY, "
            "or OTEL_EXPORTER_OTLP_ENDPOINT"
        )
    endpoint = signal or f"{(base or '').rstrip('/')}/v1/traces"
    return Receiver(endpoint=endpoint, headers=_headers(env.get("OTEL_EXPORTER_OTLP_HEADERS", "")))


def _headers(raw: str) -> dict[str, str]:
    """`key=value,key=value`, as the OpenTelemetry environment specification writes it."""
    headers: dict[str, str] = {}
    for part in raw.split(","):
        key, separator, value = part.strip().partition("=")
        if key and separator:
            headers[key] = value
    return headers


def export_run(
    corpus: Corpus,
    run_id: str,
    exporter: SpanExporter,
    *,
    started_at: datetime | None = None,
) -> Replay:
    """Replay one run as spans: an invocation per trial, a child per tool call."""
    run = next((item for item in corpus.runs if item.run_id == run_id), None)
    if run is None:
        raise KeyError(f"no run named {run_id}")
    trials = [trial for trial in corpus.trials if trial.run_id == run_id]
    calls: dict[tuple[str, int], list[ToolCall]] = {}
    for call in corpus.tool_calls:
        if call.run_id == run_id:
            calls.setdefault((call.case_id, call.repeat), []).append(call)

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": "eval-lens",
                "eval.project": run.project,
                "eval.run_id": run.run_id,
            }
        )
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    tracer = provider.get_tracer("eval_lens")

    clock = int((started_at or datetime.now(UTC)).timestamp() * NANOSECOND)
    exported_calls = 0
    for trial in sorted(trials, key=lambda item: (item.case_id, item.repeat)):
        duration = max(int(trial.seconds * NANOSECOND), NANOSECOND // 1000)
        with _span(tracer, f"invoke_agent {run.variant}", clock, clock + duration) as span:
            for key, value in _trial_attributes(run, trial).items():
                span.set_attribute(key, value)
            if trial.error:
                span.set_status(Status(StatusCode.ERROR, trial.error))
            inside = calls.get((trial.case_id, trial.repeat), [])
            step = duration // max(len(inside), 1)
            for index, call in enumerate(inside):
                begin = clock + index * step
                with _span(
                    tracer,
                    f"execute_tool {call.name}",
                    begin,
                    begin + step,
                    parent=span,
                ) as child:
                    child.set_attribute("gen_ai.operation.name", "execute_tool")
                    child.set_attribute("gen_ai.tool.name", call.name)
                    child.set_attribute("eval.tool.ok", call.ok)
                    child.set_attribute("langfuse.session.id", run.run_id)
                exported_calls += 1
        clock += duration

    provider.force_flush()
    provider.shutdown()
    return Replay(spans=len(trials) + exported_calls, trials=len(trials), tool_calls=exported_calls)


@contextmanager
def _span(
    tracer: Tracer, name: str, begin: int, end: int, *, parent: Span | None = None
) -> Iterator[Span]:
    """A span with explicit times and an explicit parent.

    The parent is passed rather than taken from the ambient context: a replay walks
    finished trials in a loop, so there is no ambient context to inherit, and a tool call
    that ends up at the root of a trace looks like an agent that called nothing.
    """
    context: Context | None = set_span_in_context(parent) if parent is not None else None
    span = tracer.start_span(name, context=context, kind=SpanKind.INTERNAL, start_time=begin)
    try:
        yield span
    finally:
        span.end(end_time=end)


def _trial_attributes(run: Run, trial: Trial) -> dict[str, AttributeValue]:
    return {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.agent.name": run.variant,
        "gen_ai.request.model": run.model,
        "gen_ai.usage.input_tokens": trial.input_tokens,
        "gen_ai.usage.output_tokens": trial.output_tokens,
        "eval.project": run.project,
        "eval.run_id": run.run_id,
        "eval.suite_version": run.suite_version,
        "eval.case_id": trial.case_id,
        "eval.family": trial.family,
        "eval.repeat": trial.repeat,
        "eval.passed": trial.passed,
        "eval.failures": list(trial.failures),
        "eval.stopped_by_harness": bool(trial.error),
        # Vendor-specific, and the only such name here: it makes one run arrive in Langfuse
        # as one session instead of eighty-one unrelated traces. Other receivers ignore it.
        "langfuse.session.id": run.run_id,
    }
