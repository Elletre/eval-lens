"""The exporter must speak OTLP over HTTP to something that is not itself.

An in-memory exporter proves the spans are built; it proves nothing about what leaves the
process. This starts a receiver on a loopback port, points `eval-lens trace` at it, and
decodes the protobuf that actually arrives — including the Authorization header a Langfuse
project expects. No account, no network, no vendor.
"""

import base64
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from eval_lens.cli import main

RUN = "mcpqa:2026-09-18-llama3-8b-baseline"
ENVIRONMENT = (
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_HOST",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_EXPORTER_OTLP_HEADERS",
)


class Receiver:
    """Whatever an OTLP/HTTP receiver would see, kept for inspection."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, str], bytes]] = []

    @property
    def spans(self) -> list[object]:
        spans = []
        for _, _, body in self.requests:
            request = ExportTraceServiceRequest()
            request.ParseFromString(body)
            for resource in request.resource_spans:
                for scope in resource.scope_spans:
                    spans.extend(scope.spans)
        return spans


@pytest.fixture
def receiver(monkeypatch):
    for variable in ENVIRONMENT:
        monkeypatch.delenv(variable, raising=False)
    collected = Receiver()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", 0))
            collected.requests.append((self.path, dict(self.headers), self.rfile.read(length)))
            self.send_response(200)
            self.send_header("Content-Type", "application/x-protobuf")
            self.end_headers()
            self.wfile.write(b"")

        def log_message(self, *_: object) -> None:
            """Quiet: the test output is the assertion, not the access log."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    collected.url = f"http://127.0.0.1:{server.server_address[1]}"
    yield collected
    server.shutdown()
    server.server_close()


def test_the_spans_arrive_as_protobuf_at_a_plain_otlp_endpoint(receiver, monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", receiver.url)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "x-api-key=secret")

    assert main(["trace", RUN]) == 0

    paths = {path for path, _, _ in receiver.requests}
    assert paths == {"/v1/traces"}, "the base endpoint gets the signal path appended"
    headers = receiver.requests[0][1]
    assert headers["Content-Type"] == "application/x-protobuf"
    assert headers["x-api-key"] == "secret"

    spans = receiver.spans
    assert len(spans) == 162, "81 invocations and the 81 tool calls inside them"
    invocations = [span for span in spans if span.name.startswith("invoke_agent")]
    assert len(invocations) == 81
    attributes = {
        item.key: item.value.string_value or item.value.bool_value
        for item in invocations[0].attributes
    }
    assert attributes["gen_ai.operation.name"] == "invoke_agent"
    assert attributes["eval.run_id"] == RUN


def test_langfuse_keys_arrive_as_basic_auth_on_the_langfuse_path(receiver, monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_HOST", receiver.url)

    assert main(["trace", RUN]) == 0

    path, headers, _ = receiver.requests[0]
    assert path == "/api/public/otel/v1/traces"
    scheme, token = headers["Authorization"].split()
    assert scheme == "Basic"
    assert base64.b64decode(token).decode() == "pk-lf-test:sk-lf-test"
    assert receiver.spans, "a receiver that answers 200 gets the whole run"
