//! Telemetry utilities for smrti.
//!
//! Uses the [`tracing`] crate for structured diagnostics. Zero cost when no
//! subscriber is configured — all instrumentation compiles to no-ops.
//!
//! ## OTEL Export
//!
//! Enable the `telemetry` feature flag to get OpenTelemetry export via
//! `tracing-opentelemetry`:
//!
//! ```toml
//! [dependencies]
//! smrti-core = { version = "0.1", features = ["telemetry"] }
//! ```
//!
//! Then configure an OTEL exporter in your application:
//!
//! ```ignore
//! use opentelemetry_otlp::WithExportConfig;
//! use tracing_subscriber::layer::SubscriberExt;
//!
//! let tracer = opentelemetry_otlp::new_pipeline()
//!     .tracing()
//!     .with_exporter(opentelemetry_otlp::new_exporter().tonic())
//!     .install_batch(opentelemetry::runtime::Tokio)?;
//!
//! let telemetry = tracing_opentelemetry::layer().with_tracer(tracer);
//! let subscriber = tracing_subscriber::registry().with(telemetry);
//! tracing::subscriber::set_global_default(subscriber)?;
//! ```
//!
//! This works with any OTEL-compatible collector: Langfuse, Jaeger, Grafana,
//! Datadog, etc. smrti emits standard OTEL signals — the application decides
//! where they go.
//!
//! ## Span Naming Convention
//!
//! All spans follow the pattern `smrti.{layer}.{operation}`:
//!
//! | Span | Layer | Emitted by |
//! |------|-------|------------|
//! | `smrti.provider.connect` | Provider | PostgresProvider |
//! | `smrti.provider.apply_event` | Provider | PostgresProvider |
//! | `smrti.provider.search` | Provider | PostgresProvider |
//! | `smrti.provider.traverse` | Provider | PostgresProvider |
//! | `smrti.provider.aggregate` | Provider | PostgresProvider |
//! | `smrti.provider.get_node` | Provider | PostgresProvider |
//! | `smrti.provider.get_or_create` | Provider | PostgresProvider |
//! | `smrti.provider.purge` | Provider | PostgresProvider |
//! | `smrti.memory.add_nodes` | Memory | Memory |
//! | `smrti.memory.add_edges` | Memory | Memory |
//! | `smrti.memory.search` | Memory | Memory |
//! | `smrti.memory.traverse` | Memory | Memory |

// This module exists primarily for documentation and to provide a central
// place for telemetry-related utilities if needed in the future.
//
// Currently, instrumentation is done directly in the provider and memory
// modules using tracing macros (debug!, info!, warn!, tracing::info_span!).
// The `tracing` crate is always available as a dependency.
//
// The `telemetry` feature flag enables OTEL export crates:
// - tracing-opentelemetry
// - opentelemetry
// - opentelemetry-otlp

/// Initialize a basic console tracing subscriber for development/debugging.
///
/// This is a convenience function — applications can configure their own
/// subscriber for production use (e.g., with OTEL export).
///
/// # Example
///
/// ```ignore
/// smrti_core::telemetry::init_dev_tracing();
/// ```
pub fn init_dev_tracing() {
    use tracing_subscriber::EnvFilter;

    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("smrti_core=debug,sqlx=warn"));

    tracing_subscriber::fmt()
        .with_env_filter(filter)
        .with_target(true)
        .with_thread_ids(false)
        .with_file(false)
        .init();
}
