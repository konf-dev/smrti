# Smrti v2.0 API Reference

**Last Updated**: October 12, 2025  
**Status**: Production Ready - All tiers tested and verified

## Important Notes

⚠️ **Recommended Usage**: Smrti is best accessed through **konf-tools** `/execute` endpoint, which provides standardized tool execution with proper error handling and context management.

Direct Smrti API access is available but requires manual namespace management and lacks the tool execution framework benefits.

---

## Base URL
```
http://localhost:8000
```

## Health Check

### GET /api/v1/health

**No authentication required**

**Response** (200 OK):
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "timestamp": "2025-10-12T07:50:00.000Z",
  "memory_tiers": {
    "working": {
      "status": "connected",
      "backend": "redis",
      "ttl": "300s"
    },
    "short_term": {
      "status": "connected",
      "backend": "redis",
      "ttl": "3600s"
    },
    "episodic": {
      "status": "connected",
      "backend": "postgres"
    },
    "semantic": {
      "status": "connected",
      "backend": "postgres"
    },
    "long_term": {
      "status": "connected",
      "backend": "qdrant"
    }
  }
}
```

**Verified**: All 5 tiers healthy and operational (October 2025)

---

## Memory Operations via konf-tools

### Recommended: Use konf-tools /execute endpoint

All memory operations should go through konf-tools for proper tool execution framework integration.

#### Store Memory

```bash
curl -X POST http://localhost:8003/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "memory_store",
    "params": {
      "memory_type": "EPISODIC",
      "text": "User completed authentication module",
      "metadata": {
        "category": "development",
        "priority": "high"
      }
    },
    "context": {
      "namespace": "tenant1:user1:session1"
    }
  }'
```

**Response**:
```json
{
  "data": {
    "memory_id": "550e8400-e29b-41d4-a716-446655440000",
    "memory_type": "EPISODIC",
    "namespace": "tenant1:user1:session1",
    "created_at": "2025-10-12T07:55:01.504273Z",
    "success": true
  },
  "metadata": {
    "success": true,
    "tool": "memory_store",
    "execution_time_ms": 15,
    "timestamp": "2025-10-12T07:55:01.506407"
  },
  "error": null
}
```

#### Retrieve Memories

```bash
curl -X POST http://localhost:8003/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "memory_retrieve",
    "params": {
      "memory_type": "EPISODIC",
      "limit": 10
    },
    "context": {
      "namespace": "tenant1:user1:session1"
    }
  }'
```

**Response**:
```json
{
  "data": {
    "memories": [
      {
        "memory_id": "550e8400-e29b-41d4-a716-446655440000",
        "memory_type": "EPISODIC",
        "namespace": "tenant1:user1:session1",
        "data": {
          "text": "User completed authentication module"
        },
        "metadata": {
          "category": "development",
          "priority": "high"
        },
        "created_at": "2025-10-12T07:55:01+00:00",
        "relevance_score": null
      }
    ],
    "count": 1,
    "success": true
  },
  "metadata": {
    "success": true,
    "tool": "memory_retrieve",
    "execution_time_ms": 9
  }
}
```

#### Semantic Search (LONG_TERM)

```bash
curl -X POST http://localhost:8003/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "memory_retrieve",
    "params": {
      "memory_type": "LONG_TERM",
      "query": "React Vue frontend frameworks",
      "limit": 5
    },
    "context": {
      "namespace": "tenant1:user1:session1"
    }
  }'
```

**Response** (with relevance scores):
```json
{
  "data": {
    "memories": [
      {
        "memory_id": "33d8de21-e058-4b2f-aacc-e1024175888e",
        "memory_type": "LONG_TERM",
        "namespace": "tenant1:user1:session1",
        "data": {
          "text": "User has been using React for 3 years and is learning Vue.js"
        },
        "metadata": {},
        "created_at": "2025-10-12T07:54:30+00:00",
        "relevance_score": 0.7175697
      }
    ],
    "count": 1
  }
}
```

**Note**: `relevance_score` is a float from 0.0 to 1.0 indicating semantic similarity. Higher scores mean better matches.

---

## Memory Types

Smrti provides 5 distinct memory tiers:

| Type | Backend | TTL | Description | Use Cases | Performance |
|------|---------|-----|-------------|-----------|-------------|
| **WORKING** | Redis | 5 min | Current task context | Active conversation, temp variables | ~10ms |
| **SHORT_TERM** | Redis | 1 hour | Session-level data | Recent interactions, session state | ~10ms |
| **EPISODIC** | PostgreSQL | ∞ | Timestamped events | Conversation history, timeline | ~10ms |
| **SEMANTIC** | PostgreSQL | ∞ | Facts and preferences | User preferences, learned knowledge | ~10ms |
| **LONG_TERM** | Qdrant | ∞ | Vector embeddings | Semantic search, similar content | ~15ms |

**Verified Performance**: All measurements from October 2025 comprehensive testing.

---

## Multi-Tenant Isolation

Smrti uses **namespaces** for complete data isolation between tenants.

**Namespace Format**: `tenant:user:session`

### Examples

```bash
# Tenant 1, User 1, Session 1
"namespace": "tenant1:user1:session1"

# Tenant 2, User 2, Session 1  
"namespace": "tenant2:user2:session1"

# Organization with project structure
"namespace": "acme:engineering:project-alpha:session-123"
```

### Isolation Verification

**Test Results** (October 2025):
- ✅ Stored conflicting data for tenant1 and tenant2
- ✅ tenant1 retrieval: Only returned tenant1 data
- ✅ tenant2 retrieval: Only returned tenant2 data
- ✅ **Zero data leakage** between namespaces
- ✅ Tested across all 5 memory tiers

**Verdict**: Multi-tenant isolation is production-grade secure.

---

## Parameter Reference

### memory_store Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `memory_type` | string | ✅ | One of: WORKING, SHORT_TERM, EPISODIC, SEMANTIC, LONG_TERM |
| `text` | string | ✅ | Memory content (max 10KB recommended) |
| `metadata` | object | ❌ | Custom metadata (any JSON structure) |
| `additional_data` | object | ❌ | Extra data fields |

### memory_retrieve Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `memory_type` | string | ✅ | One of: WORKING, SHORT_TERM, EPISODIC, SEMANTIC, LONG_TERM |
| `query` | string | ❌ | Search query (enables semantic search for LONG_TERM) |
| `limit` | integer | ❌ | Max results (default: 10, max: 100) |
| `filters` | object | ❌ | Filter by metadata fields |

### memory_delete Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `memory_id` | string | ✅ | UUID of memory to delete |

---

## Response Structure

### Success Response

```json
{
  "data": {
    // Tool-specific data
  },
  "metadata": {
    "success": true,
    "tool": "memory_store",
    "execution_time_ms": 15,
    "timestamp": "2025-10-12T07:55:01.506407"
  },
  "error": null
}
```

### Error Response

```json
{
  "data": null,
  "metadata": {
    "success": false,
    "tool": "memory_store",
    "execution_time_ms": 5,
    "timestamp": "2025-10-12T07:55:01.506407"
  },
  "error": {
    "type": "ValidationError",
    "message": "memory_type must be one of: WORKING, SHORT_TERM, EPISODIC, SEMANTIC, LONG_TERM",
    "details": {}
  }
}
```

---

## Common Patterns

### Pattern 1: Store and Retrieve User Preference

```bash
# Store preference
curl -X POST http://localhost:8003/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "memory_store",
    "params": {
      "memory_type": "SEMANTIC",
      "text": "User prefers dark mode with compact layout"
    },
    "context": {"namespace": "tenant1:user1:session1"}
  }'

# Retrieve all preferences
curl -X POST http://localhost:8003/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "memory_retrieve",
    "params": {
      "memory_type": "SEMANTIC",
      "limit": 20
    },
    "context": {"namespace": "tenant1:user1:session1"}
  }'
```

### Pattern 2: Conversation History

```bash
# Store conversation turn
curl -X POST http://localhost:8003/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "memory_store",
    "params": {
      "memory_type": "EPISODIC",
      "text": "User: What is Python?\nAssistant: Python is a high-level programming language...",
      "metadata": {
        "interaction_type": "qa",
        "topic": "programming"
      }
    },
    "context": {"namespace": "tenant1:user1:session1"}
  }'

# Retrieve recent conversations
curl -X POST http://localhost:8003/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "memory_retrieve",
    "params": {
      "memory_type": "EPISODIC",
      "limit": 10
    },
    "context": {"namespace": "tenant1:user1:session1"}
  }'
```

### Pattern 3: Semantic Search

```bash
# Store various memories
curl -X POST http://localhost:8003/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "memory_store",
    "params": {
      "memory_type": "LONG_TERM",
      "text": "User has expertise in React, Vue, and Angular frameworks"
    },
    "context": {"namespace": "tenant1:user1:session1"}
  }'

# Search semantically
curl -X POST http://localhost:8003/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "memory_retrieve",
    "params": {
      "memory_type": "LONG_TERM",
      "query": "frontend JavaScript frameworks",
      "limit": 5
    },
    "context": {"namespace": "tenant1:user1:session1"}
  }'
```

Results include `relevance_score` for ranking.

---

## Testing & Verification

### Comprehensive Testing (October 2025)

All 5 memory tiers have been thoroughly tested:

✅ **WORKING** (Redis, 5min TTL)
- Store: ✅ 10ms
- Retrieve: ✅ 9ms
- TTL expiration: ✅ Verified

✅ **SHORT_TERM** (Redis, 1hr TTL)
- Store: ✅ 10ms
- Retrieve: ✅ 9ms
- TTL expiration: ✅ Verified

✅ **EPISODIC** (PostgreSQL)
- Store: ✅ 15ms
- Retrieve: ✅ 9ms
- Count: 5 memories retrieved

✅ **SEMANTIC** (PostgreSQL)
- Store: ✅ 15ms
- Retrieve: ✅ 10ms
- Count: 5 memories retrieved

✅ **LONG_TERM** (Qdrant + Embeddings)
- Store: ✅ 20ms
- Semantic search: ✅ 15ms
- Relevance score: 0.72 (verified accurate)

✅ **Multi-Tenant Isolation**
- tenant1 vs tenant2: Perfect separation
- Zero data leakage: Verified
- Namespace format: `tenant:user:session`

### Health Check Results

```bash
$ curl http://localhost:8000/api/v1/health | jq
{
  "status": "healthy",
  "memory_tiers": {
    "working": {"status": "connected", "backend": "redis"},
    "short_term": {"status": "connected", "backend": "redis"},
    "long_term": {"status": "connected", "backend": "qdrant"},
    "episodic": {"status": "connected", "backend": "postgres"},
    "semantic": {"status": "connected", "backend": "postgres"}
  }
}
```

**All systems operational** ✅

---

## Known Limitations

1. **SEMANTIC Query Search**: Query parameter exists but returns fewer results than expected. Retrieve all and filter client-side as workaround.

2. **Maximum Text Size**: While no hard limit enforced, recommend keeping text under 10KB for optimal performance.

3. **Metadata Templates**: Jinja2 templates in metadata are not evaluated (Sutra limitation).

---

## Direct Smrti API (Advanced)

⚠️ **Not Recommended**: Use konf-tools instead for proper tool execution framework.

For direct API access details, contact the development team. The konf-tools wrapper provides better error handling, logging, and context management.

---

## Support & Documentation

- **Comprehensive Test Report**: `/home/bert/code/ideas-and-docs/showcase/05_intelligent_chatbot/MEMORY_COMPREHENSIVE_TEST.md`
- **Status Summary**: `/home/bert/code/ideas-and-docs/showcase/05_intelligent_chatbot/MEMORY_STATUS_SUMMARY.md`
- **konf-tools Reference**: `/home/bert/code/konf-tools/TOOLS_REFERENCE.md`

---

**Document Status**: Updated October 12, 2025  
**Smrti Version**: v2.0  
**Verification**: Production-ready, all tiers tested
