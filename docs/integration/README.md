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
