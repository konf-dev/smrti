# Telemetry Guide

smrti has built-in OpenTelemetry (OTEL) instrumentation. Every public operation emits spans and metrics that you can export to any OTEL-compatible backend -- Jaeger, Langfuse, Datadog, Honeycomb, or a simple console exporter.

If OpenTelemetry is not installed, all instrumentation is a no-op. Zero overhead, no import errors, no configuration needed.

## Installation

Install smrti with the telemetry extra:

```bash
pip install smrti[telemetry]
```

This installs `opentelemetry-api` as a dependency. You also need an exporter SDK -- which one depends on your backend.

## How It Works

smrti creates a tracer named `"smrti"`:

```python
# Inside smrti/telemetry.py
try:
    from opentelemetry import trace
    tracer = trace.get_tracer("smrti")
except ImportError:
    tracer = None  # No-op -- zero overhead
```

Every public method on the storage provider is wrapped in a span. If `tracer` is `None` (OTEL not installed), the wrapper is `contextlib.nullcontext()` -- literally nothing happens.

## What's Instrumented

### Spans

Every provider method gets a span with relevant attributes:

| Span Name | Attributes |
|-----------|-----------|
| `smrti.provider.apply_event` | `event.type`, `event.namespace` |
| `smrti.provider.get_node` | `node.id` |
| `smrti.provider.get_or_create_node` | `node.namespace`, `node.node_key`, `node.created` |
| `smrti.provider.search_nodes` | `search.mode`, `search.namespaces`, `search.limit`, `search.node_type` |
| `smrti.provider.traverse_graph` | `traverse.start_node_id`, `traverse.depth`, `traverse.max_nodes` |
| `smrti.provider.aggregate_edges` | `aggregate.edge_type`, `aggregate.namespaces` |
| `smrti.provider.get_events` | `events.after_id`, `events.limit` |
| `smrti.provider.migrate` | `migration.files_applied` |

### Metrics

| Metric Name | Type | Description |
|------------|------|-------------|
| `smrti.events.total` | Counter | Total events applied, labeled by event type |
| `smrti.search.duration_ms` | Histogram | Search latency, labeled by mode |
| `smrti.search.results` | Histogram | Number of results per search |
| `smrti.pool.connections` | Gauge | Active database connections |

## _meta Mirrors Span Attributes

The `_meta` dict returned by every Memory method contains the same data that populates OTEL span attributes. This is intentional -- you get the same observability information whether you read the return value or look at traces.

```python
result = await memory.search("test query", mode="hybrid")

# This data is in both _meta and the OTEL span:
print(result["_meta"]["search_mode"])       # "hybrid"
print(result["_meta"]["duration_ms"])        # 12.3
print(result["_meta"]["total_candidates"])   # 47
```

## Configuring an OTEL Collector

The most common setup sends traces and metrics to an OpenTelemetry Collector, which then routes them to your backend.

### 1. Install the OTEL SDK and exporter

```bash
pip install smrti[telemetry] \
    opentelemetry-sdk \
    opentelemetry-exporter-otlp
```

### 2. Configure the tracer and meter in your application

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

# Set up the tracer provider
resource = Resource.create({"service.name": "my-agent"})
provider = TracerProvider(resource=resource)

# Export to an OTEL Collector running on localhost:4317
exporter = OTLPSpanExporter(endpoint="http://localhost:4317")
provider.add_span_processor(BatchSpanProcessor(exporter))
trace.set_tracer_provider(provider)
```

### 3. Use smrti normally

```python
from smrti import Memory, SmrtiConfig

config = SmrtiConfig(
    dsn="postgresql://localhost:5432/mydb",
    embedding_provider=my_embedder,
)
memory = Memory(config)
await memory.connect()

# All operations now emit OTEL spans automatically
await memory.search("test query")
```

No changes to smrti code are needed. The `trace.get_tracer("smrti")` call inside smrti picks up whatever `TracerProvider` you configured globally.

## Using with Jaeger

Jaeger is a popular open-source tracing backend. Run it locally with Docker:

```bash
docker run -d --name jaeger \
    -p 16686:16686 \
    -p 4317:4317 \
    jaegertracing/all-in-one:latest
```

Then configure the OTEL exporter to point to Jaeger's OTLP endpoint:

```python
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

exporter = OTLPSpanExporter(endpoint="http://localhost:4317")
```

Open `http://localhost:16686` to view traces. You will see:

- A top-level span for each Memory method call
- Child spans for provider operations
- Attributes showing search mode, namespace, duration, result counts
- The full call chain: `memory.search` -> `smrti.provider.search_nodes`

## Using with Langfuse

Langfuse provides LLM-specific observability and supports OTEL ingestion via its OTEL exporter.

```bash
pip install smrti[telemetry] langfuse
```

```python
from langfuse import Langfuse
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Langfuse OTEL exporter
from langfuse.opentelemetry import LangfuseSpanExporter

langfuse = Langfuse(
    public_key="pk-...",
    secret_key="sk-...",
    host="https://cloud.langfuse.com",
)

provider = TracerProvider()
provider.add_span_processor(
    BatchSpanProcessor(LangfuseSpanExporter(langfuse))
)
trace.set_tracer_provider(provider)

# Now all smrti spans appear in Langfuse
```

This lets you see smrti memory operations alongside your LLM calls in a single trace timeline -- useful for understanding how memory retrieval affects agent responses.

## What You See in Traces

A typical agent interaction produces a trace like this:

```
[my-agent] handle_message (500ms)
  |-- [llm] generate_response (300ms)
  |-- [smrti] smrti.provider.search_nodes (45ms)
  |     search.mode = "hybrid"
  |     search.namespaces = ["user:alice"]
  |     search.limit = 10
  |     search.node_type = null
  |-- [smrti] smrti.provider.traverse_graph (12ms)
  |     traverse.start_node_id = "abc-123"
  |     traverse.depth = 2
  |     traverse.max_nodes = 100
  |-- [smrti] smrti.provider.apply_event (8ms)
        event.type = "NODE_CREATED"
        event.namespace = "user:alice"
```

Each span shows:
- **Duration** -- how long the operation took
- **Attributes** -- the parameters and results
- **Parent-child relationships** -- what triggered what
- **Errors** -- if an operation failed, the span is marked with error status and the exception message

## Console Exporter for Development

During development, you can print spans to the console:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    ConsoleSpanExporter,
)

provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(provider)
```

This prints every span to stdout as JSON -- useful for verifying that instrumentation is working.

## Zero Overhead Without OTEL

If `opentelemetry-api` is not installed, smrti's telemetry module falls back to a complete no-op:

```python
# smrti/telemetry.py
try:
    from opentelemetry import trace
    tracer = trace.get_tracer("smrti")
except ImportError:
    tracer = None

def start_span(name, attributes=None):
    if tracer is None:
        return contextlib.nullcontext()
    return tracer.start_as_current_span(name, attributes=attributes or {})
```

There are no conditional imports scattered through the codebase, no try/except blocks in hot paths, and no performance cost. The `contextlib.nullcontext()` call is essentially free.

This means you can deploy smrti in production without OTEL and add observability later by installing the package -- no code changes required.
