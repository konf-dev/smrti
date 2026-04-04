# Telemetry

## Overview

smrti uses the Rust `tracing` crate for structured telemetry. Every Memory method emits a span with timing and context fields. If you configure an OpenTelemetry (OTEL) collector, these spans are exported automatically.

Python users do not need to instrument their code. Telemetry is emitted at the Rust level and is visible when an OTEL exporter is configured in the process environment.

## Spans emitted

Each Memory method emits a `debug`-level span. The span name follows the pattern `smrti.memory.<method>`:

| Span name | Key fields |
|---|---|
| `smrti.memory.add_nodes` | `namespace`, `count` |
| `smrti.memory.add_edges` | `namespace`, `count` |
| `smrti.memory.get_or_create` | `namespace`, `node_type`, `has_key` |
| `smrti.memory.search` | `mode`, `namespaces`, `limit`, `has_vector`, `has_text` |
| `smrti.memory.traverse` | `node_id`, `depth` |
| `smrti.memory.aggregate` | `edge_type`, `namespace` |
| `smrti.memory.state_set` | `namespace`, `session_id`, `key` |
| `smrti.memory.purge_namespace` | `namespace` |

## Enabling OTEL export

smrti does not start an OTEL exporter itself. To collect traces, configure an OTEL exporter in your application or use the standard OTEL environment variables.

### Environment variables

Set these before starting your Python process:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
export OTEL_SERVICE_NAME="my-agent"
```

The exact mechanism depends on your tracing setup. If you are using a Rust binary that links `smrti-core`, you can initialize a `tracing-opentelemetry` subscriber. If you are using the Python package, the Tokio runtime inside smrti will emit spans that any process-level OTEL SDK can pick up.

### Docker Compose example with Jaeger

```yaml
services:
  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"   # Jaeger UI
      - "4317:4317"     # OTLP gRPC
```

Then run your Python script with the environment variables above and open `http://localhost:16686` to see traces.

## Correlating with `_meta`

Every smrti response includes `_meta.duration_ms`. You can correlate this with OTEL spans to match application-level timing with infrastructure-level traces.

```python
result = memory.search(
    query_vector=vec,
    text_query="hello",
)
print(f"Search took {result['_meta']['duration_ms']:.1f}ms")
# The same duration will appear in the OTEL span for smrti.memory.search
```

For write operations, `_meta.event_ids` provides a stable identifier you can attach to your own spans or logs for end-to-end tracing.

## Log levels

smrti's Rust core uses these `tracing` levels:

| Level | What |
|---|---|
| `debug` | Method entry/exit with parameters |
| `info` | Connection lifecycle (connect, close, migrations) |
| `warn` | Retries, fallbacks (e.g., trigram fallback in text search) |
| `error` | Unrecoverable failures |

To see debug-level output in development, set:

```bash
export RUST_LOG="smrti_core=debug"
```
