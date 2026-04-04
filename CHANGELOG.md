# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **smrti-core Rust crate** — complete graph memory engine
- **Event-sourced storage** — append-only event log, nodes/edges as projections
- **Hybrid search** — vector (pgvector), full-text (tsvector), trigram, and RRF fusion
- **Graph traversal** — recursive CTE, configurable depth and edge type filters
- **Edge aggregation** — COUNT/SUM/AVG/MIN/MAX on edge metadata
- **Multi-tenant** — namespace isolation on all operations, multi-namespace search
- **Temporal edges** — valid_from/valid_to with point-in-time queries
- **Session state** — lightweight KV store for agent working memory with TTL
- **get_or_create** — atomic find-or-create with advisory locking
- **Batch transactions** — apply_events_batch for single-transaction bulk writes
- **GDPR purge** — purge_namespace physically deletes all data + audit log
- **Hybrid SQL filtering** — all queries use parameterized binds, zero string interpolation
- **Memory (Layer 1)** — LLM-friendly API with flat params, string IDs, JSON returns with _meta
- **StorageProvider (Layer 2)** — typed Rust API with UUID, Pydantic models
- **ScopedMemory** — namespace-bound wrapper for cleaner multi-tenant code
- **Telemetry** — tracing crate integration, optional OTEL export via feature flag
- **17 configurable parameters** — every default, threshold, algorithm choice in SmrtiConfig
- **40 tests** — 7 unit + 33 integration (vector search, text search, hybrid, traversal, aggregation, session state, GDPR, namespace isolation)
- Project infrastructure: CI/CD (GitHub Actions), MkDocs documentation site, issue templates
- Comprehensive documentation: spec, plan, quickstart, concepts, guides
