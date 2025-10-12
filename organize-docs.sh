#!/bin/bash
# organize-docs.sh - Reorganize ideas-and-docs into proper structure

set -e

echo "🔄 Starting documentation reorganization..."
echo ""

REPO_ROOT="/home/bert/code/ideas-and-docs"
cd "$REPO_ROOT"

# Create new directory structure
echo "📁 Creating directory structure..."
mkdir -p docs/{user,developer,operator,reference,design/adr,integration,misc,archive}

# Create README files for each directory
echo "📝 Creating README files..."

# Root docs README
cat > docs/README.md << 'EOF'
# Ideas and Docs - Documentation Index

**Last Updated:** October 12, 2025  
**Status:** Active  

## 📚 Documentation Structure

- **[user/](./user/)** - User-facing documentation
- **[developer/](./developer/)** - Developer documentation  
- **[operator/](./operator/)** - Operations and deployment
- **[reference/](./reference/)** - Reference materials
- **[design/](./design/)** - Design documents, PRDs, ADRs
- **[integration/](./integration/)** - Integration guides
- **[misc/](./misc/)** - Miscellaneous/uncategorized
- **[archive/](./archive/)** - Old/deprecated documents

## 🎯 Quick Links

### Platform Documentation
- [Platform Enhancement Roadmap](./design/roadmap.md)
- [Grand Plan](./design/grand-plan.md)
- [Platform Status](./misc/platform-status.md)

### Guides
- [Integration Testing Guide](./integration/integration-testing-guide.md)
- [Memory Best Practices](./user/memory-best-practices.md)

### Infrastructure
- [Infrastructure Setup](./operator/infrastructure.md)
- [Service Integration](./integration/service-integration.md)
EOF

# User docs README
cat > docs/user/README.md << 'EOF'
# User Documentation

**Audience:** End users, developers using the platform

## Documents

- [Memory Best Practices](./memory-best-practices.md) - How to use memory effectively
- [Examples and Showcases](../../showcase/) - Working examples

## External Links

- Main README: [../../README.md](../../README.md)
EOF

# Developer docs README
cat > docs/developer/README.md << 'EOF'
# Developer Documentation

**Audience:** Core developers, contributors

## Documents

- [Developer Experience Improvements](./developer-experience.md)
- [Documentation Update Summary](./documentation-updates.md)

## External Links

- Contributing guides in individual repos
EOF

# Operator docs README
cat > docs/operator/README.md << 'EOF'
# Operator Documentation

**Audience:** DevOps, SRE, platform operators

## Documents

- [Infrastructure Setup](./infrastructure.md)
- [Monitoring Setup](./monitoring.md)
- [Service Integration](../integration/service-integration.md)

## Configuration Files

- [docker-compose.yml](../../docker-compose.yml)
- [prometheus.yml](../../prometheus.yml)
- [init-databases.sql](../../init-databases.sql)
EOF

# Reference docs README
cat > docs/reference/README.md << 'EOF'
# Reference Documentation

**Audience:** All

## Documents

Currently empty. Will contain:
- API specifications
- Configuration references
- Error code references
EOF

# Design docs README
cat > docs/design/README.md << 'EOF'
# Design Documentation

**Audience:** Product managers, architects, senior developers

## Documents

- [Grand Plan](./grand-plan.md) - Original platform vision
- [Enhancement Roadmap](./roadmap.md) - Future enhancements (2026-2027)
- [PRDs](./prds/) - Product Requirements Documents
- [Ideas](./ideas/) - Design ideas and explorations
- [ADRs](./adr/) - Architecture Decision Records

## Current State

- [Current State Documentation](../../curent_state/) - Status of each service
EOF

# Integration docs README
cat > docs/integration/README.md << 'EOF'
# Integration Documentation

**Audience:** Developers integrating services

## Documents

- [Integration Testing Guide](./integration-testing-guide.md)
- [Service Integration](./service-integration.md)

## Related

- Individual service integration docs in their respective repos
EOF

# Misc docs README
cat > docs/misc/README.md << 'EOF'
# Miscellaneous Documentation

**Audience:** Various

## Documents

Documents that don't yet have a clear home. These should be reviewed periodically and either:
1. Moved to proper category
2. Merged with other docs
3. Archived if outdated

Current contents:
- [Platform Status](./platform-status.md)
- [Documentation Update Summary](./documentation-updates.md)
- [Langfuse V3 Upgrade](./langfuse-v3-upgrade.md)

## Action Items

- [ ] Review and categorize all docs in this folder
- [ ] Move to appropriate locations
- [ ] Archive if no longer relevant
EOF

# Archive README
cat > docs/archive/README.md << 'EOF'
# Archived Documentation

**Status:** Historical reference only

## Archive Policy

Documents are archived (not deleted) when they are:
1. Replaced by newer versions
2. No longer relevant to current platform
3. Superseded by other documentation

## Archived Documents

*None yet - archive will be populated during migration*

## Restoration

If you need information from an archived document:
1. Check if there's a newer version in active docs
2. If the archived doc is still relevant, consider updating and restoring it
3. Contact maintainers if unsure
EOF

echo "✅ Created README files"

# Now move/copy existing docs to appropriate locations
echo ""
echo "📦 Organizing existing documents..."

# Design documents
if [ -f "GRAND_PLAN.md" ]; then
    mv GRAND_PLAN.md docs/design/grand-plan.md
    echo "  ✅ Moved GRAND_PLAN.md → docs/design/grand-plan.md"
fi

if [ -f "KONF_PLATFORM_ENHANCEMENT_ROADMAP.md" ]; then
    mv KONF_PLATFORM_ENHANCEMENT_ROADMAP.md docs/design/roadmap.md
    echo "  ✅ Moved KONF_PLATFORM_ENHANCEMENT_ROADMAP.md → docs/design/roadmap.md"
fi

# Move PRDs and ideas folders
if [ -d "prds" ]; then
    mv prds docs/design/
    echo "  ✅ Moved prds/ → docs/design/prds/"
fi

if [ -d "ideas" ]; then
    mv ideas docs/design/
    echo "  ✅ Moved ideas/ → docs/design/ideas/"
fi

# User documentation
if [ -f "MEMORY_ISSUES_EXPLAINED.md" ]; then
    mv MEMORY_ISSUES_EXPLAINED.md docs/user/memory-best-practices.md
    echo "  ✅ Moved MEMORY_ISSUES_EXPLAINED.md → docs/user/memory-best-practices.md"
fi

# Developer documentation
if [ -f "DEVELOPER_EXPERIENCE_AND_IMPROVEMENTS.md" ]; then
    mv DEVELOPER_EXPERIENCE_AND_IMPROVEMENTS.md docs/developer/developer-experience.md
    echo "  ✅ Moved DEVELOPER_EXPERIENCE_AND_IMPROVEMENTS.md → docs/developer/developer-experience.md"
fi

# Operator documentation
if [ -f "INFRASTRUCTURE.md" ]; then
    mv INFRASTRUCTURE.md docs/operator/infrastructure.md
    echo "  ✅ Moved INFRASTRUCTURE.md → docs/operator/infrastructure.md"
fi

# Integration documentation
if [ -f "INTEGRATION_TESTING_GUIDE.md" ]; then
    mv INTEGRATION_TESTING_GUIDE.md docs/integration/integration-testing-guide.md
    echo "  ✅ Moved INTEGRATION_TESTING_GUIDE.md → docs/integration/integration-testing-guide.md"
fi

if [ -f "SERVICE_INTEGRATION.md" ]; then
    mv SERVICE_INTEGRATION.md docs/integration/service-integration.md
    echo "  ✅ Moved SERVICE_INTEGRATION.md → docs/integration/service-integration.md"
fi

# Misc documentation (things we're not sure about yet)
if [ -f "KONF_PLATFORM_STATUS.md" ]; then
    mv KONF_PLATFORM_STATUS.md docs/misc/platform-status.md
    echo "  ✅ Moved KONF_PLATFORM_STATUS.md → docs/misc/platform-status.md"
fi

if [ -f "DOCUMENTATION_UPDATE_SUMMARY.md" ]; then
    mv DOCUMENTATION_UPDATE_SUMMARY.md docs/misc/documentation-updates.md
    echo "  ✅ Moved DOCUMENTATION_UPDATE_SUMMARY.md → docs/misc/documentation-updates.md"
fi

if [ -f "LANGFUSE_V3_UPGRADE.md" ]; then
    mv LANGFUSE_V3_UPGRADE.md docs/misc/langfuse-v3-upgrade.md
    echo "  ✅ Moved LANGFUSE_V3_UPGRADE.md → docs/misc/langfuse-v3-upgrade.md"
fi

# Keep curent_state folder in root for now (it's structured already)
# Keep showcase folder in root (it has its own structure)

# Update main README
echo ""
echo "📝 Updating main README.md..."

cat > README.md << 'EOF'
# Konf Platform Documentation

**Last Updated:** October 12, 2025  
**Status:** Active - Documentation Reorganized  

---

## 📚 Quick Navigation

### 🎯 **Strategic Planning**
- **[Enhancement Roadmap](./docs/design/roadmap.md)** ⭐ Future vision (2026-2027)
- **[Grand Plan](./docs/design/grand-plan.md)** - Original platform vision

### 📖 **User Guides**
- **[Memory Best Practices](./docs/user/memory-best-practices.md)** - How to use memory effectively
- **[Showcase Examples](./showcase/)** - Working examples and demos

### 🔧 **Developer Documentation**
- **[Developer Experience](./docs/developer/developer-experience.md)** - Dev improvements
- **[Documentation Updates](./docs/misc/documentation-updates.md)** - Recent doc changes

### 🚀 **Operations**
- **[Infrastructure Setup](./docs/operator/infrastructure.md)** - Complete infra guide
- **[Service Integration](./docs/integration/service-integration.md)** - How services connect

### 🧪 **Integration & Testing**
- **[Integration Testing Guide](./docs/integration/integration-testing-guide.md)** - How to test
- **[Current State](./curent_state/)** - Service status reports

### 🎨 **Design & Planning**
- **[PRDs](./docs/design/prds/)** - Product Requirements Documents
- **[Ideas](./docs/design/ideas/)** - Design explorations
- **[ADRs](./docs/design/adr/)** - Architecture Decision Records

---

## 📁 Documentation Structure

```
ideas-and-docs/
├── README.md                    # This file
├── docs/                        # All documentation
│   ├── user/                    # User-facing docs
│   ├── developer/               # Developer docs
│   ├── operator/                # Ops/deployment docs
│   ├── reference/               # Reference materials
│   ├── design/                  # Design docs, PRDs, ADRs
│   ├── integration/             # Integration guides
│   ├── misc/                    # Uncategorized docs
│   └── archive/                 # Old/deprecated docs
│
├── curent_state/                # Service status (keep as-is)
├── showcase/                    # Examples and demos (keep as-is)
│
├── docker-compose.yml           # Infrastructure config
├── prometheus.yml               # Monitoring config
├── init-databases.sql           # Database setup
└── setup-infrastructure.sh      # Setup script
```

---

## 🎯 The Vision

**Konf Platform will become:**
- 🎯 The most powerful agent development platform
- 🧠 The operating system for AI agents
- 🏆 The AutoGPT/LangGraph/CrewAI killer
- 🌐 The standard for enterprise AI agent deployment

**Read the full vision:** [Enhancement Roadmap](./docs/design/roadmap.md)

---

## 🏆 Key Achievements

### **Technical:**
- ✅ 5-tier memory system operational
- ✅ Sub-20ms memory operations
- ✅ 100% multi-tenant isolation
- ✅ Production-ready infrastructure
- ✅ Comprehensive testing

### **Documentation:**
- ✅ 10+ comprehensive docs
- ✅ All organized by category
- ✅ Real-world examples
- ✅ Best practices documented
- ✅ 18-month enhancement roadmap

### **Architecture:**
- ✅ Protocol-based design
- ✅ Dependency injection
- ✅ Async-first operations
- ✅ Multi-tenant from ground up
- ✅ Full observability

---

## 🚀 Quick Links by Repository

### **Sutra** (Agent Framework)
- Repository: `/home/bert/code/sutra`
- Docs: [sutra/docs/](../sutra/docs/)
- [User Guide](../sutra/docs/USER_GUIDE.md)
- [Examples](../sutra/docs/EXAMPLES.md)

### **Smrti** (Memory System)
- Repository: `/home/bert/code/smrti`
- Docs: [smrti/docs/](../smrti/docs/)
- Status: MVP complete, needs docs reorganization

### **konf-tools** (Tool Execution)
- Repository: `/home/bert/code/konf-tools`
- Docs: Root (needs reorganization)
- [README](../konf-tools/README.md)

### **konf-agents-api** (Agent API)
- Repository: `/home/bert/code/konf-agents-api`
- Docs: Root (needs reorganization)
- [README](../konf-agents-api/README.md)

### **konf-gateway** (API Gateway)
- Repository: `/home/bert/code/konf-gateway`
- Docs: Minimal (needs expansion)
- [README](../konf-gateway/README.md)

---

## 📖 Full Documentation Index

For complete documentation navigation, see **[docs/README.md](./docs/README.md)**

---

## 🤝 Contributing

We're currently reorganizing documentation across all repositories. See:
- [Documentation Organization Plan](./docs/design/documentation-organization-plan.md)

---

## 📞 Support

- Check relevant documentation first
- File issues in respective repositories
- See [Integration Testing Guide](./docs/integration/integration-testing-guide.md) for testing help

---

**Last Updated:** October 12, 2025  
**Maintained by:** Konf Development Team

**🚀 Let's build the future of AI agents! 🚀**
EOF

echo "  ✅ Updated README.md"

echo ""
echo "🎉 Documentation reorganization complete!"
echo ""
echo "📊 Summary:"
echo "  ✅ Created docs/ folder structure"
echo "  ✅ Created README files for all sections"
echo "  ✅ Moved major documents to appropriate locations"
echo "  ✅ Updated main README.md"
echo ""
echo "📁 New structure:"
echo "  docs/"
echo "    ├── user/              (User-facing docs)"
echo "    ├── developer/         (Developer docs)"
echo "    ├── operator/          (Ops/deployment)"
echo "    ├── reference/         (Reference materials)"
echo "    ├── design/            (Design docs, PRDs, ideas)"
echo "    ├── integration/       (Integration guides)"
echo "    ├── misc/              (Uncategorized)"
echo "    └── archive/           (Old docs)"
echo ""
echo "🔍 Review the changes:"
echo "  cd /home/bert/code/ideas-and-docs"
echo "  tree docs/"
echo ""
echo "✅ Next steps:"
echo "  1. Review the new structure"
echo "  2. Move any remaining docs from misc/ to proper locations"
echo "  3. Repeat for other repositories (smrti, konf-tools, etc.)"
EOF
