"""The replay must produce spans a trace viewer can read without knowing this project."""

import base64
from datetime import UTC, datetime
from pathlib import Path

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace.status import StatusCode

from eval_lens.ingest import read_corpus
from eval_lens.otlp import export_run, receiver

ROOT = Path(__file__).resolve().parents[1]
RUN = "lab:experiments__2026-09-22-qwen3-8b__improved"


@pytest.fixture(scope="module")
def spans():
    corpus = read_corpus(ROOT / "data")
    exporter = InMemorySpanExporter()
    replay = export_run(corpus, RUN, exporter, started_at=datetime(2026, 9, 25, tzinfo=UTC))
    return replay, exporter.get_finished_spans()


def test_a_trial_becomes_an_invocation_with_its_tool_calls_inside(spans):
    replay, exported = spans
    assert replay.trials == 81
    assert len(exported) == replay.spans
    agents = [span for span in exported if span.name.startswith("invoke_agent")]
    tools = [span for span in exported if span.name.startswith("execute_tool")]
    assert len(agents) == 81
    assert len(tools) == replay.tool_calls
    assert {span.parent.span_id for span in tools} <= {span.context.span_id for span in agents}


def test_spans_carry_the_conventional_attributes_and_the_verdict(spans):
    _, exported = spans
    agent = next(span for span in exported if span.name.startswith("invoke_agent"))
    assert agent.attributes["gen_ai.operation.name"] == "invoke_agent"
    assert agent.attributes["gen_ai.request.model"] == "ollama/qwen3:8b"
    assert agent.attributes["eval.case_id"]
    assert isinstance(agent.attributes["eval.passed"], bool)
    tool = next(span for span in exported if span.name.startswith("execute_tool"))
    assert tool.attributes["gen_ai.operation.name"] == "execute_tool"
    assert tool.attributes["gen_ai.tool.name"] in tool.name


def test_durations_are_the_recorded_ones(spans):
    _, exported = spans
    agent = next(span for span in exported if span.name.startswith("invoke_agent"))
    seconds = (agent.end_time - agent.start_time) / 1_000_000_000
    assert 0 < seconds < 600


def test_an_unknown_run_is_refused():
    corpus = read_corpus(ROOT / "data")
    with pytest.raises(KeyError):
        export_run(corpus, "nope", InMemorySpanExporter())


def test_only_a_harness_stop_makes_a_span_an_error(spans):
    """A wrong answer is a result; a trial the harness cut short is a broken span."""
    _, exported = spans
    agents = [span for span in exported if span.name.startswith("invoke_agent")]
    failed = [span for span in agents if not span.attributes["eval.passed"]]
    assert failed, "this run has failing trials, so the distinction is testable"
    for span in agents:
        stopped = span.attributes["eval.stopped_by_harness"]
        assert (span.status.status_code is StatusCode.ERROR) == stopped


def test_one_run_arrives_as_one_session(spans):
    """Every span, not only the roots: a viewer groups children by their own attribute too."""
    _, exported = spans
    assert {span.attributes["langfuse.session.id"] for span in exported} == {RUN}


def test_langfuse_keys_become_basic_auth_over_otlp_http():
    target = receiver({"LANGFUSE_PUBLIC_KEY": "pk-lf-1", "LANGFUSE_SECRET_KEY": "sk-lf-2"})
    assert target.endpoint == "https://cloud.langfuse.com/api/public/otel/v1/traces"
    scheme, token = target.headers["Authorization"].split()
    assert scheme == "Basic"
    assert base64.b64decode(token).decode() == "pk-lf-1:sk-lf-2"
    assert target.origin == "https://cloud.langfuse.com"


def test_a_self_hosted_langfuse_is_the_same_two_keys_and_a_host():
    target = receiver(
        {
            "LANGFUSE_PUBLIC_KEY": "pk",
            "LANGFUSE_SECRET_KEY": "sk",
            "LANGFUSE_HOST": "http://localhost:3000/",
        }
    )
    assert target.endpoint == "http://localhost:3000/api/public/otel/v1/traces"


def test_any_other_receiver_is_configured_the_standard_way():
    target = receiver(
        {
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4318",
            "OTEL_EXPORTER_OTLP_HEADERS": "x-api-key=abc, x-tenant=eval",
        }
    )
    assert target.endpoint == "http://collector:4318/v1/traces"
    assert target.headers == {"x-api-key": "abc", "x-tenant": "eval"}


def test_a_missing_receiver_says_which_variables_would_set_one():
    with pytest.raises(KeyError, match="LANGFUSE_PUBLIC_KEY"):
        receiver({})
