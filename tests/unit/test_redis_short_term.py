"""Unit tests for Redis Short-Term memory adapter."""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

import fakeredis.aioredis

from smrti.storage.adapters.redis_short_term import RedisShortTermAdapter
from smrti.core.exceptions import StorageError


@pytest.fixture
async def redis_client():
    """Create a fake Redis client for testing."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=False)
    yield client
    await client.flushall()
    await client.aclose()


@pytest.fixture
def adapter(redis_client):
    """Create a RedisShortTermAdapter for testing."""
    return RedisShortTermAdapter(redis_client, ttl=3600)


@pytest.mark.unit
@pytest.mark.asyncio
class TestRedisShortTermAdapter:
    """Test suite for Redis Short-Term memory adapter."""

    async def test_store_and_get(self, adapter):
        """Test basic store and get flow."""
        memory_id = uuid4()
        namespace = "test:user:123"
        data = {"text": "Session summary"}
        metadata = {"session_id": "abc123"}

        # Store
        result = await adapter.store(memory_id, namespace, data, None, metadata)
        assert result == memory_id

        # Get
        retrieved = await adapter.get(memory_id, namespace)
        assert retrieved is not None
        assert retrieved["memory_id"] == str(memory_id)
        assert retrieved["namespace"] == namespace
        assert retrieved["data"]["text"] == "Session summary"
        assert retrieved["metadata"]["session_id"] == "abc123"
        assert retrieved["memory_type"] == "SHORT_TERM"

    async def test_store_requires_text_field(self, adapter):
        """Test that data must contain 'text' field."""
        memory_id = uuid4()
        namespace = "test:user:123"
        data = {"content": "This is missing 'text' field"}
        
        with pytest.raises(StorageError, match="text"):
            await adapter.store(memory_id, namespace, data, None, {})

    async def test_get_nonexistent_memory(self, adapter):
        """Test getting a memory that doesn't exist."""
        memory_id = uuid4()
        namespace = "test:user:123"
        
        result = await adapter.get(memory_id, namespace)
        assert result is None

    async def test_namespace_isolation_on_get(self, adapter):
        """Test that get respects namespace isolation."""
        memory_id = uuid4()
        namespace_a = "test:user:alice"
        namespace_b = "test:user:bob"
        data = {"text": "Secret message"}

        # Store in namespace A
        await adapter.store(memory_id, namespace_a, data, None, {})

        # Try to get from namespace B - should return None
        result = await adapter.get(memory_id, namespace_b)
        assert result is None

        # Get from namespace A - should work
        result = await adapter.get(memory_id, namespace_a)
        assert result is not None

    async def test_retrieve_empty_namespace(self, adapter):
        """Test retrieving from empty namespace."""
        namespace = "test:user:empty"
        
        results = await adapter.retrieve(namespace, None, None, 10)
        assert results == []

    async def test_retrieve_multiple_memories(self, adapter):
        """Test retrieving multiple memories."""
        namespace = "test:user:123"
        
        # Store multiple memories
        memory_ids = []
        for i in range(5):
            memory_id = uuid4()
            data = {"text": f"Summary {i}"}
            await adapter.store(memory_id, namespace, data, None, {})
            memory_ids.append(memory_id)

        # Retrieve all
        results = await adapter.retrieve(namespace, None, None, 10)
        assert len(results) == 5
        
        # Verify all memories are present
        retrieved_ids = {r["memory_id"] for r in results}
        expected_ids = {str(mid) for mid in memory_ids}
        assert retrieved_ids == expected_ids

    async def test_retrieve_with_text_query(self, adapter):
        """Test text search in retrieve."""
        namespace = "test:user:123"
        
        # Store memories
        await adapter.store(uuid4(), namespace, {"text": "Meeting summary"}, None, {})
        await adapter.store(uuid4(), namespace, {"text": "Code review notes"}, None, {})
        await adapter.store(uuid4(), namespace, {"text": "Meeting agenda"}, None, {})

        # Search for "Meeting"
        results = await adapter.retrieve(namespace, "Meeting", None, 10)
        assert len(results) == 2
        assert all("Meeting" in r["data"]["text"] for r in results)

    async def test_retrieve_with_limit(self, adapter):
        """Test limit parameter in retrieve."""
        namespace = "test:user:123"
        
        # Store 10 memories
        for i in range(10):
            await adapter.store(uuid4(), namespace, {"text": f"Memory {i}"}, None, {})

        # Retrieve with limit=3
        results = await adapter.retrieve(namespace, None, None, limit=3)
        assert len(results) == 3

    async def test_retrieve_time_ordered(self, adapter):
        """Test that retrieve returns memories in time order (newest first)."""
        namespace = "test:user:123"
        
        # Store memories with small delays
        for i in range(3):
            memory_id = uuid4()
            data = {"text": f"Memory {i}"}
            await adapter.store(memory_id, namespace, data, None, {})
            # Small delay to ensure different timestamps
            import asyncio
            await asyncio.sleep(0.01)

        # Retrieve
        results = await adapter.retrieve(namespace, None, None, 10)
        
        # Should be in reverse order (newest first)
        assert results[0]["data"]["text"] == "Memory 2"
        assert results[1]["data"]["text"] == "Memory 1"
        assert results[2]["data"]["text"] == "Memory 0"

    async def test_sorted_set_index_used(self, adapter, redis_client):
        """Test that sorted set index is created and used correctly."""
        namespace = "test:user:123"
        memory_id = uuid4()
        data = {"text": "Test memory"}

        # Store
        await adapter.store(memory_id, namespace, data, None, {})

        # Check that sorted set index exists
        index_key = f"short_term_index:{namespace}"
        score = await redis_client.zscore(index_key.encode(), str(memory_id).encode())
        
        assert score is not None
        # Score should be a timestamp (large number)
        assert score > 1700000000  # After 2023

    async def test_delete_existing_memory(self, adapter):
        """Test deleting an existing memory."""
        memory_id = uuid4()
        namespace = "test:user:123"
        data = {"text": "To be deleted"}

        # Store
        await adapter.store(memory_id, namespace, data, None, {})
        
        # Verify it exists
        assert await adapter.get(memory_id, namespace) is not None

        # Delete
        deleted = await adapter.delete(memory_id, namespace)
        assert deleted is True

        # Verify it's gone
        assert await adapter.get(memory_id, namespace) is None

    async def test_delete_removes_from_index(self, adapter, redis_client):
        """Test that delete removes memory from sorted set index."""
        memory_id = uuid4()
        namespace = "test:user:123"
        data = {"text": "To be deleted"}

        # Store
        await adapter.store(memory_id, namespace, data, None, {})
        
        # Verify in index
        index_key = f"short_term_index:{namespace}"
        score = await redis_client.zscore(index_key.encode(), str(memory_id).encode())
        assert score is not None

        # Delete
        await adapter.delete(memory_id, namespace)

        # Verify removed from index
        score = await redis_client.zscore(index_key.encode(), str(memory_id).encode())
        assert score is None

    async def test_delete_nonexistent_memory(self, adapter):
        """Test deleting a memory that doesn't exist."""
        memory_id = uuid4()
        namespace = "test:user:123"

        deleted = await adapter.delete(memory_id, namespace)
        assert deleted is False

    async def test_delete_wrong_namespace(self, adapter):
        """Test that delete respects namespace isolation."""
        memory_id = uuid4()
        namespace_a = "test:user:alice"
        namespace_b = "test:user:bob"
        data = {"text": "Secret"}

        # Store in namespace A
        await adapter.store(memory_id, namespace_a, data, None, {})

        # Try to delete from namespace B
        deleted = await adapter.delete(memory_id, namespace_b)
        assert deleted is False

        # Verify still exists in namespace A
        assert await adapter.get(memory_id, namespace_a) is not None

    async def test_health_check_success(self, adapter):
        """Test health check when Redis is available."""
        health = await adapter.health_check()
        
        assert health["status"] == "connected"
        assert health["backend"] == "Redis"
        assert health["memory_type"] == "SHORT_TERM"
        assert "latency_ms" in health
        assert health["ttl_seconds"] == 3600

    async def test_multiple_namespaces_isolated(self, adapter):
        """Comprehensive test for multi-tenant isolation."""
        # Create memories in different namespaces
        alice_id = uuid4()
        bob_id = uuid4()
        
        await adapter.store(
            alice_id,
            "tenant:1:user:alice",
            {"text": "Alice's session"},
            None,
            {}
        )
        
        await adapter.store(
            bob_id,
            "tenant:1:user:bob",
            {"text": "Bob's session"},
            None,
            {}
        )

        # Alice should only see her memory
        alice_memories = await adapter.retrieve("tenant:1:user:alice", None, None, 10)
        assert len(alice_memories) == 1
        assert alice_memories[0]["data"]["text"] == "Alice's session"
        assert "Bob" not in alice_memories[0]["data"]["text"]

        # Bob should only see his memory
        bob_memories = await adapter.retrieve("tenant:1:user:bob", None, None, 10)
        assert len(bob_memories) == 1
        assert bob_memories[0]["data"]["text"] == "Bob's session"
        assert "Alice" not in bob_memories[0]["data"]["text"]

    async def test_index_namespace_isolation(self, adapter, redis_client):
        """Test that sorted set indexes are isolated per namespace."""
        namespace_a = "test:user:alice"
        namespace_b = "test:user:bob"
        
        alice_id = uuid4()
        bob_id = uuid4()
        
        # Store in both namespaces
        await adapter.store(alice_id, namespace_a, {"text": "Alice"}, None, {})
        await adapter.store(bob_id, namespace_b, {"text": "Bob"}, None, {})

        # Check indexes are separate
        alice_index = f"short_term_index:{namespace_a}".encode()
        bob_index = f"short_term_index:{namespace_b}".encode()
        
        alice_count = await redis_client.zcard(alice_index)
        bob_count = await redis_client.zcard(bob_index)
        
        assert alice_count == 1
        assert bob_count == 1
        
        # Alice's index should only contain alice_id
        alice_members = await redis_client.zrange(alice_index, 0, -1)
        assert alice_members == [str(alice_id).encode()]
        
        # Bob's index should only contain bob_id
        bob_members = await redis_client.zrange(bob_index, 0, -1)
        assert bob_members == [str(bob_id).encode()]
