"""Unit tests for Redis Working memory adapter."""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

import fakeredis.aioredis

from smrti.storage.adapters.redis_working import RedisWorkingAdapter
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
    """Create a RedisWorkingAdapter for testing."""
    return RedisWorkingAdapter(redis_client, ttl=300)


@pytest.mark.unit
@pytest.mark.asyncio
class TestRedisWorkingAdapter:
    """Test suite for Redis Working memory adapter."""

    async def test_store_and_get(self, adapter):
        """Test basic store and get flow."""
        memory_id = uuid4()
        namespace = "test:user:123"
        data = {"text": "Remember to buy milk"}
        metadata = {"priority": "high"}

        # Store
        result = await adapter.store(memory_id, namespace, data, None, metadata)
        assert result == memory_id

        # Get
        retrieved = await adapter.get(memory_id, namespace)
        assert retrieved is not None
        assert retrieved["memory_id"] == str(memory_id)
        assert retrieved["namespace"] == namespace
        assert retrieved["data"]["text"] == "Remember to buy milk"
        assert retrieved["metadata"]["priority"] == "high"
        assert retrieved["memory_type"] == "WORKING"

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

    async def test_namespace_isolation(self, adapter):
        """Test that namespaces are isolated."""
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
            data = {"text": f"Task {i}"}
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
        await adapter.store(uuid4(), namespace, {"text": "Buy groceries"}, None, {})
        await adapter.store(uuid4(), namespace, {"text": "Call dentist"}, None, {})
        await adapter.store(uuid4(), namespace, {"text": "Buy tickets"}, None, {})

        # Search for "Buy"
        results = await adapter.retrieve(namespace, "Buy", None, 10)
        assert len(results) == 2
        assert all("Buy" in r["data"]["text"] for r in results)

    async def test_retrieve_with_limit(self, adapter):
        """Test limit parameter in retrieve."""
        namespace = "test:user:123"
        
        # Store 10 memories
        for i in range(10):
            await adapter.store(uuid4(), namespace, {"text": f"Memory {i}"}, None, {})

        # Retrieve with limit=3
        results = await adapter.retrieve(namespace, None, None, limit=3)
        assert len(results) == 3

    async def test_retrieve_sorted_by_time(self, adapter):
        """Test that retrieve returns memories sorted by time (newest first)."""
        namespace = "test:user:123"
        memory_ids = []
        
        # Store memories in sequence
        for i in range(3):
            memory_id = uuid4()
            data = {"text": f"Memory {i}"}
            await adapter.store(memory_id, namespace, data, None, {})
            memory_ids.append(str(memory_id))
            # Small delay to ensure different timestamps
            import asyncio
            await asyncio.sleep(0.01)

        # Retrieve
        results = await adapter.retrieve(namespace, None, None, 10)
        
        # Should be in reverse order (newest first)
        assert results[0]["data"]["text"] == "Memory 2"
        assert results[1]["data"]["text"] == "Memory 1"
        assert results[2]["data"]["text"] == "Memory 0"

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
        assert health["memory_type"] == "WORKING"
        assert "latency_ms" in health
        assert health["ttl_seconds"] == 300

    async def test_multiple_namespaces_isolated(self, adapter):
        """Comprehensive test for multi-tenant isolation."""
        # Create memories in different namespaces
        alice_id = uuid4()
        bob_id = uuid4()
        
        await adapter.store(
            alice_id,
            "tenant:1:user:alice",
            {"text": "Alice's secret"},
            None,
            {}
        )
        
        await adapter.store(
            bob_id,
            "tenant:1:user:bob",
            {"text": "Bob's secret"},
            None,
            {}
        )

        # Alice should only see her memory
        alice_memories = await adapter.retrieve("tenant:1:user:alice", None, None, 10)
        assert len(alice_memories) == 1
        assert alice_memories[0]["data"]["text"] == "Alice's secret"
        assert "Bob" not in alice_memories[0]["data"]["text"]

        # Bob should only see his memory
        bob_memories = await adapter.retrieve("tenant:1:user:bob", None, None, 10)
        assert len(bob_memories) == 1
        assert bob_memories[0]["data"]["text"] == "Bob's secret"
        assert "Alice" not in bob_memories[0]["data"]["text"]
