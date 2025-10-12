# Design Documentation

Architecture decisions, design proposals, PRDs, and technical designs for Smrti.

## 📖 Available Documentation

- [PRD Compliance Review](prd-compliance-review.md) - Product requirements status
- [Phase 4 Completion](phase-4-completion.md) - Phase 4 implementation summary
- [Architecture Prompts](prompts/) - System architecture and design
- [ADRs (Architecture Decision Records)](adr/) - Key architectural decisions

## 🏗️ Architecture Overview

Smrti follows a modular architecture:
- **API Layer** - FastAPI-based REST API
- **Service Layer** - Business logic and orchestration
- **Repository Layer** - Database access
- **Memory Engine** - Semantic search and retrieval
- **Graph Engine** - Memory relationships

## 📋 Key Design Principles

1. **Separation of Concerns** - Clear layer boundaries
2. **Async by Default** - Non-blocking operations
3. **Type Safety** - Strong typing with Pydantic
4. **Testability** - Dependency injection for testing
5. **Observability** - Comprehensive logging and metrics

## 🔗 Quick Links

- [API Reference](../reference/api-reference.md)
- [Development Setup](../developer/development-setup.md)
- [Main Documentation](../README.md)

---

**Last Updated**: October 12, 2025
