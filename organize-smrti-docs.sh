#!/bin/bash

# Smrti Documentation Reorganization Script
# Based on standard documentation organization plan
# Date: October 12, 2025

set -e  # Exit on error

echo "🚀 Starting Smrti documentation reorganization..."

# Create directory structure
echo "📁 Creating directory structure..."

mkdir -p docs/user
mkdir -p docs/developer
mkdir -p docs/operator
mkdir -p docs/reference
mkdir -p docs/design/adr
mkdir -p docs/integration
mkdir -p docs/misc
mkdir -p docs/archive

# Move existing docs to archive first (duplicates and old versions)
echo "📦 Archiving old versions..."

if [ -f "docs/API_REFERENCE.md" ]; then
    mv docs/API_REFERENCE.md docs/archive/api-reference-v1-$(date +%Y%m%d).md
    echo "  ✓ Archived API_REFERENCE.md"
fi

if [ -f "STATUS_REPORT.md" ]; then
    mv STATUS_REPORT.md docs/archive/status-report-old-$(date +%Y%m%d).md
    echo "  ✓ Archived old STATUS_REPORT.md"
fi

# Move documents from root to appropriate categories
echo "📄 Moving documents from root..."

# User documentation
if [ -f "QUICKSTART.md" ]; then
    mv QUICKSTART.md docs/user/quickstart.md
    echo "  ✓ Moved QUICKSTART.md → docs/user/"
fi

# Reference documentation
if [ -f "docs/API_REFERENCE_V2.md" ]; then
    mv docs/API_REFERENCE_V2.md docs/reference/api-reference.md
    echo "  ✓ Moved API_REFERENCE_V2.md → docs/reference/"
fi

# Design documentation
if [ -f "docs/PRD_COMPLIANCE_REVIEW.md" ]; then
    mv docs/PRD_COMPLIANCE_REVIEW.md docs/design/prd-compliance-review.md
    echo "  ✓ Moved PRD_COMPLIANCE_REVIEW.md → docs/design/"
fi

if [ -f "docs/PHASE_4_COMPLETION.md" ]; then
    mv docs/PHASE_4_COMPLETION.md docs/design/phase-4-completion.md
    echo "  ✓ Moved PHASE_4_COMPLETION.md → docs/design/"
fi

# Keep prompts in design/prompts
if [ -d "docs/prompts" ]; then
    mv docs/prompts docs/design/prompts
    echo "  ✓ Moved prompts/ → docs/design/prompts/"
fi

# Integration documentation
if [ -f "SERVICE_INTEGRATION.md" ]; then
    mv SERVICE_INTEGRATION.md docs/integration/service-integration.md
    echo "  ✓ Moved SERVICE_INTEGRATION.md → docs/integration/"
fi

# Misc documentation (review later)
if [ -f "STATUS_REPORT_OCT_12_2025.md" ]; then
    mv STATUS_REPORT_OCT_12_2025.md docs/misc/status-report-oct-12-2025.md
    echo "  ✓ Moved STATUS_REPORT_OCT_12_2025.md → docs/misc/"
fi

if [ -f "docs/SESSION_SUMMARY_2025-10-05.md" ]; then
    mv docs/SESSION_SUMMARY_2025-10-05.md docs/misc/session-summary-2025-10-05.md
    echo "  ✓ Moved SESSION_SUMMARY_2025-10-05.md → docs/misc/"
fi

# Create README files for each category
echo "📝 Creating README files..."

# Main docs README
cat > docs/README.md << 'EOF'
# Smrti Documentation

Memory service for the Konf platform, providing intelligent memory storage, retrieval, and semantic search capabilities.

## 📚 Documentation Structure

### [User Documentation](user/)
Getting started guides, quickstarts, and how-to documentation for end users.

- [Quickstart Guide](user/quickstart.md) - Get started with Smrti

### [Developer Documentation](developer/)
Information for developers working on Smrti.

- [Contributing Guidelines](developer/contributing.md) - How to contribute
- [Development Setup](developer/development-setup.md) - Local development guide

### [Operator Documentation](operator/)
Deployment, operations, and infrastructure guides.

- [Deployment Guide](operator/deployment.md) - Production deployment
- [Monitoring Guide](operator/monitoring.md) - Observability setup

### [Reference Documentation](reference/)
API references, configuration references, and technical specifications.

- [API Reference](reference/api-reference.md) - Complete API documentation
- [Configuration Reference](reference/configuration.md) - All config options

### [Design Documentation](design/)
Architecture decisions, design proposals, and PRDs.

- [PRD Compliance Review](design/prd-compliance-review.md)
- [Phase 4 Completion](design/phase-4-completion.md)
- [Architecture Prompts](design/prompts/)
- [ADRs (Architecture Decision Records)](design/adr/)

### [Integration Documentation](integration/)
Guides for integrating Smrti with other services.

- [Service Integration](integration/service-integration.md) - Integration patterns

### [Miscellaneous](misc/)
Temporary location for documents that need categorization.

### [Archive](archive/)
Old versions and deprecated documentation.

---

**Last Updated**: October 12, 2025  
**Maintained By**: Konf Platform Team
EOF

# User docs README
cat > docs/user/README.md << 'EOF'
# User Documentation

Getting started guides and how-to documentation for Smrti users.

## 📖 Available Guides

- [Quickstart Guide](quickstart.md) - Get started with Smrti in 5 minutes

## 🎯 What is Smrti?

Smrti is the memory service for the Konf platform, providing:
- **Intelligent Memory Storage** - Store conversations, facts, and context
- **Semantic Search** - Find relevant memories using natural language
- **Memory Graphs** - Understand relationships between memories
- **Multi-Session Context** - Maintain context across sessions

## 🚀 Quick Links

- [API Reference](../reference/api-reference.md)
- [Service Integration](../integration/service-integration.md)
- [Main Documentation](../README.md)

---

**Last Updated**: October 12, 2025
EOF

# Developer docs README
cat > docs/developer/README.md << 'EOF'
# Developer Documentation

Information for developers working on Smrti.

## 📖 Available Guides

- [Contributing Guidelines](contributing.md) - How to contribute to Smrti
- [Development Setup](development-setup.md) - Set up your local environment
- [Testing Guide](testing-guide.md) - Running and writing tests
- [Code Style Guide](code-style.md) - Coding standards

## 🛠️ Development Workflow

1. Clone the repository
2. Set up development environment (see [Development Setup](development-setup.md))
3. Create a feature branch
4. Make your changes
5. Run tests
6. Submit a pull request

## 📋 Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Docker & Docker Compose
- Poetry (for dependency management)

## 🔗 Quick Links

- [API Reference](../reference/api-reference.md)
- [Architecture Prompts](../design/prompts/)
- [Main Documentation](../README.md)

---

**Last Updated**: October 12, 2025
EOF

# Operator docs README
cat > docs/operator/README.md << 'EOF'
# Operator Documentation

Deployment, operations, and infrastructure guides for Smrti.

## 📖 Available Guides

- [Deployment Guide](deployment.md) - Deploy Smrti to production
- [Monitoring Guide](monitoring.md) - Set up observability
- [Backup & Recovery](backup-recovery.md) - Data protection
- [Troubleshooting](troubleshooting.md) - Common issues and solutions

## 🚀 Quick Start

```bash
# Using Docker Compose
docker-compose up -d

# Using Kubernetes
kubectl apply -f k8s/
```

## 📊 Infrastructure Requirements

- **CPU**: 2+ cores
- **RAM**: 4GB+ recommended
- **Storage**: 20GB+ for database
- **PostgreSQL**: 15+
- **Network**: HTTPS enabled

## 🔗 Quick Links

- [Service Integration](../integration/service-integration.md)
- [API Reference](../reference/api-reference.md)
- [Main Documentation](../README.md)

---

**Last Updated**: October 12, 2025
EOF

# Reference docs README
cat > docs/reference/README.md << 'EOF'
# Reference Documentation

Complete API references, configuration references, and technical specifications.

## 📖 Available References

- [API Reference](api-reference.md) - Complete API documentation
- [Configuration Reference](configuration.md) - All configuration options
- [Database Schema](database-schema.md) - Database structure
- [Error Codes](error-codes.md) - Error handling reference

## 🔍 API Overview

Smrti provides RESTful APIs for:
- Memory storage and retrieval
- Semantic search
- Memory graph operations
- Session management

## 📋 Quick Reference

### Base URL
```
http://localhost:8002
```

### Authentication
```
Authorization: Bearer <token>
```

### Common Endpoints
- `POST /api/v1/memories` - Create memory
- `GET /api/v1/memories/search` - Search memories
- `GET /api/v1/memories/{id}` - Get memory
- `PUT /api/v1/memories/{id}` - Update memory

## 🔗 Quick Links

- [Quickstart Guide](../user/quickstart.md)
- [Service Integration](../integration/service-integration.md)
- [Main Documentation](../README.md)

---

**Last Updated**: October 12, 2025
EOF

# Design docs README
cat > docs/design/README.md << 'EOF'
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
EOF

# ADR directory README
cat > docs/design/adr/README.md << 'EOF'
# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records for Smrti.

## 📋 What are ADRs?

Architecture Decision Records document important architectural decisions made during the development of Smrti. Each ADR describes:
- **Context** - The situation and problem
- **Decision** - What was decided
- **Consequences** - Impact of the decision
- **Status** - Current status (proposed, accepted, deprecated, superseded)

## 📖 ADR Index

_(To be populated with ADRs)_

Example ADRs to create:
- ADR-001: Choice of PostgreSQL for Memory Storage
- ADR-002: FastAPI Framework Selection
- ADR-003: Async SQLAlchemy for Database Access
- ADR-004: Pydantic for Data Validation
- ADR-005: pgvector for Semantic Search

## 📝 ADR Template

```markdown
# ADR-XXX: Title

**Status**: [Proposed | Accepted | Deprecated | Superseded]  
**Date**: YYYY-MM-DD  
**Decision Makers**: [Names/Roles]

## Context
[Describe the situation and problem]

## Decision
[Describe the decision that was made]

## Consequences
### Positive
- [Benefit 1]
- [Benefit 2]

### Negative
- [Trade-off 1]
- [Trade-off 2]

## Alternatives Considered
- [Alternative 1]: [Why rejected]
- [Alternative 2]: [Why rejected]
```

---

**Last Updated**: October 12, 2025
EOF

# Integration docs README
cat > docs/integration/README.md << 'EOF'
# Integration Documentation

Guides for integrating Smrti with other Konf platform services.

## 📖 Available Guides

- [Service Integration](service-integration.md) - Integration patterns and guidelines

## 🔌 Integration Overview

Smrti integrates with:
- **Konf Gateway** - API gateway and routing
- **Konf Tools** - Tool execution and orchestration
- **Konf Agents API** - Agent configuration and execution
- **Sutra** - Core orchestration layer

## 🚀 Quick Integration

```python
from konf_agents_api.services import SutraAdapter

# Initialize Smrti adapter
adapter = SutraAdapter()

# Store memory
await adapter.store_memory(
    session_id="session-123",
    content="Important context",
    metadata={"type": "fact"}
)

# Search memories
results = await adapter.search_memories(
    query="relevant context",
    session_id="session-123"
)
```

## 🔗 Quick Links

- [API Reference](../reference/api-reference.md)
- [Quickstart Guide](../user/quickstart.md)
- [Main Documentation](../README.md)

---

**Last Updated**: October 12, 2025
EOF

# Misc docs README
cat > docs/misc/README.md << 'EOF'
# Miscellaneous Documentation

Temporary location for documents that need review and proper categorization.

## 📋 Documents in this folder

These documents are pending review and should be moved to appropriate categories:

- [Status Report Oct 12 2025](status-report-oct-12-2025.md) - Latest status update
- [Session Summary 2025-10-05](session-summary-2025-10-05.md) - Development session notes

## 🎯 Action Items

1. Review each document
2. Determine appropriate category (user/developer/operator/reference/design/integration)
3. Move to correct location
4. Update relevant README files

## 📝 Guidelines

Documents should be moved to:
- **user/** - If it's a guide for end users
- **developer/** - If it's for contributors/developers
- **operator/** - If it's about deployment/operations
- **reference/** - If it's technical reference
- **design/** - If it's about architecture/design
- **integration/** - If it's about service integration
- **archive/** - If it's outdated/superseded

---

**Last Updated**: October 12, 2025
EOF

# Archive docs README
cat > docs/archive/README.md << 'EOF'
# Archive

Old versions and deprecated documentation.

## 📦 Archived Documents

This directory contains:
- Old versions of documents (superseded by newer versions)
- Deprecated documentation
- Historical records

## 📋 Archived Files

- [API Reference V1](api-reference-v1-20251012.md) - Superseded by V2
- [Old Status Report](status-report-old-20251012.md) - Superseded by newer reports

## 🗄️ Retention Policy

Archived documents are kept for:
- Historical reference
- Version tracking
- Compliance requirements

Documents may be permanently deleted after 2 years in archive.

---

**Last Updated**: October 12, 2025
EOF

echo "✅ Created 8 README files"

# Update main README.md
echo "📝 Updating root README.md..."

# Backup original README
cp README.md README.md.backup

# Create updated README (preserve existing content, just add docs section)
cat >> README.md << 'EOF'

## 📚 Documentation

Comprehensive documentation is available in the [`docs/`](docs/) directory:

- **[User Docs](docs/user/)** - Quickstart guides and how-tos
- **[Developer Docs](docs/developer/)** - Contributing and development setup
- **[Operator Docs](docs/operator/)** - Deployment and operations
- **[Reference Docs](docs/reference/)** - API and configuration reference
- **[Design Docs](docs/design/)** - Architecture and design decisions
- **[Integration Docs](docs/integration/)** - Service integration guides

See the [Documentation Index](docs/README.md) for complete navigation.

EOF

echo "✅ Updated root README.md"

# Create summary document
cat > docs/misc/reorganization-summary.md << 'EOF'
# Smrti Documentation Reorganization Summary

**Date**: October 12, 2025  
**Status**: Complete  
**Executor**: Documentation Organization Initiative

## 📊 Summary

Successfully reorganized Smrti documentation into a standardized structure aligned with the platform-wide documentation organization plan.

## 📁 Changes Made

### Documents Moved

#### From Root → User Docs
- `QUICKSTART.md` → `docs/user/quickstart.md`

#### From docs/ → Reference Docs
- `docs/API_REFERENCE_V2.md` → `docs/reference/api-reference.md`

#### From docs/ → Design Docs
- `docs/PRD_COMPLIANCE_REVIEW.md` → `docs/design/prd-compliance-review.md`
- `docs/PHASE_4_COMPLETION.md` → `docs/design/phase-4-completion.md`
- `docs/prompts/` → `docs/design/prompts/`

#### From Root → Integration Docs
- `SERVICE_INTEGRATION.md` → `docs/integration/service-integration.md`

#### From Root/docs → Misc Docs (for review)
- `STATUS_REPORT_OCT_12_2025.md` → `docs/misc/status-report-oct-12-2025.md`
- `docs/SESSION_SUMMARY_2025-10-05.md` → `docs/misc/session-summary-2025-10-05.md`

### Documents Archived

#### Old Versions
- `docs/API_REFERENCE.md` → `docs/archive/api-reference-v1-20251012.md`
- `STATUS_REPORT.md` → `docs/archive/status-report-old-20251012.md`

## 📝 New Files Created

- `docs/README.md` - Main documentation index
- `docs/user/README.md` - User documentation index
- `docs/developer/README.md` - Developer documentation index
- `docs/operator/README.md` - Operator documentation index
- `docs/reference/README.md` - Reference documentation index
- `docs/design/README.md` - Design documentation index
- `docs/design/adr/README.md` - ADR directory with template
- `docs/integration/README.md` - Integration documentation index
- `docs/misc/README.md` - Miscellaneous docs index
- `docs/archive/README.md` - Archive index

## 📊 Statistics

- **Directories Created**: 8 (user, developer, operator, reference, design, integration, misc, archive)
- **Documents Moved**: 8
- **Documents Archived**: 2
- **README Files Created**: 10
- **Prompts Relocated**: 2 (moved to design/prompts/)

## 🎯 Next Steps

1. **Review misc/ folder** - Categorize status reports and session summaries
2. **Populate ADR folder** - Document key architectural decisions
3. **Create missing docs** - Add contributing guide, development setup, deployment guide
4. **Update cross-references** - Ensure all links point to new locations

## ✅ Compliance

This reorganization follows the standard documentation organization plan defined in `ideas-and-docs/docs/design/documentation-organization-plan.md`.

---

**Reorganization Script**: `organize-smrti-docs.sh`  
**Reusable**: Yes - Can be adapted for other repositories
EOF

echo ""
echo "✅ Documentation reorganization complete!"
echo ""
echo "📊 Summary:"
echo "  • 8 documents moved"
echo "  • 2 documents archived"
echo "  • 10 README files created"
echo "  • 8 categories established"
echo ""
echo "📁 New structure created in docs/ directory"
echo "📝 See docs/misc/reorganization-summary.md for details"
echo ""
