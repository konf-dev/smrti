# Contributing to smrti

Thanks for your interest in contributing!

## Development Setup

```bash
# Clone the repo
git clone https://github.com/konf-dev/smrti.git
cd smrti

# Ensure you have Rust installed (https://rustup.rs/)
rustup update stable

# Build
cargo build --manifest-path smrti-core/Cargo.toml

# Run tests (needs Docker for integration tests)
cargo test --manifest-path smrti-core/Cargo.toml
```

### Integration Tests

Integration tests use testcontainers and require Docker running locally with the `pgvector/pgvector:pg17` image:

```bash
docker pull pgvector/pgvector:pg17
cargo test --manifest-path smrti-core/Cargo.toml
```

## Running Tests

```bash
# All tests
cargo test --manifest-path smrti-core/Cargo.toml

# Unit tests only (no Docker needed)
cargo test --manifest-path smrti-core/Cargo.toml --lib

# With telemetry feature
cargo test --manifest-path smrti-core/Cargo.toml --features telemetry
```

## Linting

```bash
cargo fmt --manifest-path smrti-core/Cargo.toml -- --check
cargo clippy --manifest-path smrti-core/Cargo.toml -- -D warnings
```

## Making Changes

1. Create a branch from `main`
2. Make your changes
3. Add tests for new functionality
4. Ensure all tests pass and lint is clean
5. Update `CHANGELOG.md` if the change is user-facing
6. Submit a pull request

## Code Style

- Follow existing patterns in the codebase
- All public functions and types need doc comments
- Use `thiserror` for error types
- All config values come from `SmrtiConfig` — no hardcoded defaults
- Error messages must be clear enough for an LLM to understand and act on

## Documentation

- Update docs if you change the API
- Doc comments are used for API reference — write them well
- Run `mkdocs serve` to preview docs locally (requires Python + mkdocs-material)
