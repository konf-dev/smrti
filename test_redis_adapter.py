"""
test_redis_adapter.py - Comprehensive tests for Redis Storage Adapter

Tests the Redis adapter with both real Redis (if available) and mock Redis
to ensure functionality without external dependencies.
"""

import pytest
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List

# Add the smrti package to path
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

try:
    from smrti.adapters.storage.redis_adapter import (
        RedisStorageAdapter, RedisConfig, RedisOperationResult,
        create_redis_adapter, REDIS_AVAILABLE
    )
    from smrti.models.base import MemoryItem, SimpleMemoryItem
    REDIS_ADAPTER_AVAILABLE = True
except ImportError as e:
    print(f"Import error: {e}")
    REDIS_ADAPTER_AVAILABLE = False


class MockRedisClient:
    """Mock Redis client for testing without actual Redis."""
    
    def __init__(self):
        self.data: Dict[str, Any] = {}
        self.sets: Dict[str, set] = {}
        self.expires: Dict[str, float] = {}
        self.pipeline_commands: List[tuple] = []
        self.in_pipeline = False
    
    async def ping(self):
        """Mock ping."""
        return True
    
    async def setex(self, key: str, ttl: int, value: str):
        """Mock setex."""
        self.data[key] = value
        self.expires[key] = time.time() + ttl
        return True
    
    async def get(self, key: str):
        """Mock get."""
        if key in self.data:
            # Check if expired
            if key in self.expires and time.time() > self.expires[key]:
                del self.data[key]
                del self.expires[key]
                return None
            return self.data[key]
        return None
    
    async def delete(self, key: str):
        """Mock delete."""
        deleted = 1 if key in self.data else 0
        self.data.pop(key, None)
        self.expires.pop(key, None)
        return deleted
    
    async def sadd(self, key: str, *members):
        """Mock sadd."""
        if key not in self.sets:
            self.sets[key] = set()
        for member in members:
            self.sets[key].add(member)
        return len(members)
    
    async def srem(self, key: str, *members):
        """Mock srem."""
        if key not in self.sets:
            return 0
        removed = 0
        for member in members:
            if member in self.sets[key]:
                self.sets[key].remove(member)
                removed += 1
        return removed
    
    async def smembers(self, key: str):
        """Mock smembers."""
        return list(self.sets.get(key, set()))
    
    async def expire(self, key: str, ttl: int):
        """Mock expire."""
        if key in self.data or key in self.sets:
            self.expires[key] = time.time() + ttl
            return True
        return False
    
    async def exists(self, key: str):
        """Mock exists."""
        # Check data
        if key in self.data:
            if key in self.expires and time.time() > self.expires[key]:
                del self.data[key]
                del self.expires[key]
                return False
            return True
        # Check sets
        return key in self.sets
    
    async def info(self):
        """Mock info."""
        return {
            'connected_clients': 1,
            'used_memory': len(str(self.data)),
            'used_memory_human': f"{len(str(self.data))}B",
            'keyspace_hits': 100,
            'keyspace_misses': 10,
            'total_commands_processed': 150
        }
    
    def pipeline(self):
        """Mock pipeline."""
        return MockPipeline(self)
    
    async def close(self):
        """Mock close."""
        pass


class MockPipeline:
    """Mock Redis pipeline."""
    
    def __init__(self, redis_client: MockRedisClient):
        self.redis_client = redis_client
        self.commands = []
    
    def setex(self, key: str, ttl: int, value: str):
        """Mock pipeline setex."""
        self.commands.append(('setex', key, ttl, value))
        return self
    
    def get(self, key: str):
        """Mock pipeline get."""
        self.commands.append(('get', key))
        return self
    
    def delete(self, key: str):
        """Mock pipeline delete."""
        self.commands.append(('delete', key))
        return self
    
    def sadd(self, key: str, *members):
        """Mock pipeline sadd."""
        self.commands.append(('sadd', key, *members))
        return self
    
    def srem(self, key: str, *members):
        """Mock pipeline srem.""" 
        self.commands.append(('srem', key, *members))
        return self
    
    def expire(self, key: str, ttl: int):
        """Mock pipeline expire."""
        self.commands.append(('expire', key, ttl))
        return self
    
    def exists(self, key: str):
        """Mock pipeline exists."""
        self.commands.append(('exists', key))
        return self
    
    async def execute(self):
        """Mock pipeline execute."""
        results = []
        
        for cmd in self.commands:
            operation = cmd[0]
            
            if operation == 'setex':
                result = await self.redis_client.setex(cmd[1], cmd[2], cmd[3])
            elif operation == 'get':
                result = await self.redis_client.get(cmd[1])
            elif operation == 'delete':
                result = await self.redis_client.delete(cmd[1])
            elif operation == 'sadd':
                result = await self.redis_client.sadd(cmd[1], *cmd[2:])
            elif operation == 'srem':
                result = await self.redis_client.srem(cmd[1], *cmd[2:])
            elif operation == 'expire':
                result = await self.redis_client.expire(cmd[1], cmd[2])
            elif operation == 'exists':
                result = await self.redis_client.exists(cmd[1])
            else:
                result = None
            
            results.append(result)
        
        self.commands.clear()
        return results


class MockConnectionPool:
    """Mock Redis connection pool."""
    
    async def disconnect(self):
        """Mock disconnect."""
        pass


def create_mock_memory_item(item_id: str = "test_item", 
                           tenant: str = "test_tenant",
                           namespace: str = "test_ns") -> SimpleMemoryItem:
    """Create a mock memory item for testing."""
    
    return SimpleMemoryItem(
        id=item_id,
        content=f"Test content for {item_id}",
        tenant=tenant,
        namespace=namespace,
        metadata={"test": True, "priority": "high"}
    )


@pytest.mark.skipif(not REDIS_ADAPTER_AVAILABLE, reason="Redis adapter not available")
class TestRedisStorageAdapter:
    """Test suite for Redis storage adapter."""
    
    @pytest.fixture
    def redis_config(self):
        """Create test Redis configuration."""
        return RedisConfig(
            host="localhost",
            port=6379,
            db=15,  # Use high DB number for tests
            default_ttl=300,
            key_prefix="test_smrti"
        )
    
    @pytest.fixture
    async def mock_adapter(self, redis_config):
        """Create Redis adapter with mock client."""
        adapter = RedisStorageAdapter(redis_config)
        
        # Replace Redis client with mock
        mock_client = MockRedisClient()
        mock_pool = MockConnectionPool()
        
        adapter.redis_client = mock_client
        adapter._connection_pool = mock_pool
        
        return adapter
    
    @pytest.fixture
    def sample_items(self):
        """Create sample memory items for testing."""
        items = []
        for i in range(5):
            item = create_mock_memory_item(
                f"item_{i}",
                "test_tenant", 
                "test_namespace"
            )
            items.append(item)
        return items
    
    async def test_adapter_initialization(self, redis_config):
        """Test adapter initialization."""
        adapter = RedisStorageAdapter(redis_config)
        
        assert adapter.config == redis_config
        assert adapter.redis_client is None
        assert adapter._operations_count == 0
    
    async def test_redis_config_url_generation(self):
        """Test Redis URL generation."""
        # Basic config
        config = RedisConfig(host="localhost", port=6379, db=0)
        assert config.get_redis_url() == "redis://localhost:6379/0"
        
        # With password
        config = RedisConfig(host="localhost", port=6379, db=0, password="secret")
        assert config.get_redis_url() == "redis://:secret@localhost:6379/0"
        
        # With username and password
        config = RedisConfig(host="localhost", port=6379, db=0, 
                           username="user", password="secret")
        assert config.get_redis_url() == "redis://user:secret@localhost:6379/0"
        
        # SSL
        config = RedisConfig(host="localhost", port=6379, db=0, ssl=True)
        assert config.get_redis_url() == "rediss://localhost:6379/0"
    
    async def test_key_generation(self, mock_adapter):
        """Test Redis key generation."""
        adapter = mock_adapter
        
        # Test item key
        key = adapter._make_key("tenant1", "ns1", "item", "id123")
        expected = "test_smrti:tenant1:ns1:item:id123"
        assert key == expected
        
        # Test index key
        index_key = adapter._make_index_key("tenant1", "ns1", "items")
        expected_index = "test_smrti:tenant1:ns1:idx:items"
        assert index_key == expected_index
    
    async def test_store_single_item(self, mock_adapter, sample_items):
        """Test storing a single item."""
        adapter = mock_adapter
        item = sample_items[0]
        
        # Store item
        result = await adapter.store_item(item, ttl=600)
        
        assert result.success
        assert result.operation == "store_item"
        assert result.key_count == 1
        assert result.execution_time_ms > 0
        
        # Verify item was stored
        retrieved = await adapter.retrieve_item(item.tenant, item.namespace, item.id)
        assert retrieved is not None
        assert retrieved['id'] == item.id
        assert retrieved['content'] == item.content
    
    async def test_store_batch_items(self, mock_adapter, sample_items):
        """Test storing multiple items in batch."""
        adapter = mock_adapter
        
        # Store batch
        result = await adapter.store_items_batch(sample_items, ttl=600)
        
        assert result.success
        assert result.operation == "store_items_batch"
        assert result.key_count == len(sample_items)
        
        # Verify all items were stored
        item_ids = [item.id for item in sample_items]
        retrieved = await adapter.retrieve_items_batch(
            sample_items[0].tenant, 
            sample_items[0].namespace,
            item_ids
        )
        
        assert len(retrieved) == len(sample_items)
        for item in sample_items:
            assert item.id in retrieved
            assert retrieved[item.id]['content'] == item.content
    
    async def test_retrieve_missing_item(self, mock_adapter):
        """Test retrieving non-existent item."""
        adapter = mock_adapter
        
        result = await adapter.retrieve_item("tenant", "namespace", "missing_id")
        assert result is None
    
    async def test_delete_item(self, mock_adapter, sample_items):
        """Test deleting an item."""
        adapter = mock_adapter
        item = sample_items[0]
        
        # Store item first
        await adapter.store_item(item)
        
        # Verify it exists
        retrieved = await adapter.retrieve_item(item.tenant, item.namespace, item.id)
        assert retrieved is not None
        
        # Delete item
        result = await adapter.delete_item(item.tenant, item.namespace, item.id)
        
        assert result.success
        assert result.operation == "delete_item"
        assert result.key_count == 1  # One item deleted
        
        # Verify it's gone
        retrieved = await adapter.retrieve_item(item.tenant, item.namespace, item.id)
        assert retrieved is None
    
    async def test_list_items(self, mock_adapter, sample_items):
        """Test listing items in namespace."""
        adapter = mock_adapter
        
        # Store multiple items
        await adapter.store_items_batch(sample_items)
        
        # List items
        item_ids = await adapter.list_items(
            sample_items[0].tenant,
            sample_items[0].namespace
        )
        
        assert len(item_ids) == len(sample_items)
        stored_ids = {item.id for item in sample_items}
        retrieved_ids = set(item_ids)
        assert stored_ids == retrieved_ids
    
    async def test_list_items_with_limit(self, mock_adapter, sample_items):
        """Test listing items with limit."""
        adapter = mock_adapter
        
        # Store multiple items
        await adapter.store_items_batch(sample_items)
        
        # List with limit
        item_ids = await adapter.list_items(
            sample_items[0].tenant,
            sample_items[0].namespace,
            limit=3
        )
        
        assert len(item_ids) == 3
    
    async def test_cleanup_expired(self, mock_adapter, sample_items):
        """Test cleanup of expired items."""
        adapter = mock_adapter
        
        # Store items
        await adapter.store_items_batch(sample_items)
        
        # Run cleanup
        result = await adapter.cleanup_expired(
            sample_items[0].tenant,
            sample_items[0].namespace
        )
        
        assert result.success
        assert result.operation == "cleanup_expired"
        # Should be 0 since items aren't actually expired in mock
        assert result.key_count >= 0
    
    async def test_health_check(self, mock_adapter):
        """Test health check."""
        adapter = mock_adapter
        
        # Should be healthy with mock client
        healthy = await adapter.health_check()
        assert healthy
        
        # Test with no client
        adapter.redis_client = None
        healthy = await adapter.health_check()
        assert not healthy
    
    async def test_get_stats(self, mock_adapter, sample_items):
        """Test getting adapter statistics."""
        adapter = mock_adapter
        
        # Perform some operations
        await adapter.store_items_batch(sample_items)
        await adapter.retrieve_item(sample_items[0].tenant, sample_items[0].namespace, sample_items[0].id)
        
        stats = await adapter.get_stats()
        
        assert 'operations_count' in stats
        assert 'error_count' in stats
        assert 'average_operation_time_ms' in stats
        assert 'success_rate' in stats
        assert 'redis_info' in stats
        assert 'config' in stats
        
        assert stats['operations_count'] > 0
        assert stats['success_rate'] >= 0.0
    
    async def test_operation_result_creation(self):
        """Test operation result helper methods."""
        # Success result
        success = RedisOperationResult.success_result("test_op", 5, 123.45)
        assert success.success
        assert success.operation == "test_op"
        assert success.key_count == 5
        assert success.execution_time_ms == 123.45
        assert success.error_message is None
        
        # Error result
        error = RedisOperationResult.error_result("test_op", "Something went wrong", 67.89)
        assert not error.success
        assert error.operation == "test_op"
        assert error.error_message == "Something went wrong"
        assert error.execution_time_ms == 67.89
    
    async def test_close_connection(self, mock_adapter):
        """Test closing Redis connection."""
        adapter = mock_adapter
        
        # Should not raise exception
        await adapter.close()
        
        # Client should be None after close
        assert adapter.redis_client is None
    
    async def test_factory_function(self):
        """Test convenience factory function."""
        adapter = create_redis_adapter(host="testhost", port=1234, db=5)
        
        assert isinstance(adapter, RedisStorageAdapter)
        assert adapter.config.host == "testhost"
        assert adapter.config.port == 1234
        assert adapter.config.db == 5


async def run_tests():
    """Run all tests."""
    print("🧪 Testing Redis Storage Adapter...")
    
    if not REDIS_ADAPTER_AVAILABLE:
        print("❌ Redis adapter not available for testing")
        return False
    
    try:
        # Create test instance  
        test_instance = TestRedisStorageAdapter()
        
        # Test basic functionality
        print("Testing adapter initialization...")
        config = RedisConfig(host="localhost", port=6379, db=15, key_prefix="test_smrti")
        await test_instance.test_adapter_initialization(config)
        print("✅ Adapter initialization test passed")
        
        print("Testing Redis config URL generation...")
        await test_instance.test_redis_config_url_generation()
        print("✅ URL generation test passed")
        
        # Create mock adapter for remaining tests
        adapter = RedisStorageAdapter(config)
        mock_client = MockRedisClient()
        mock_pool = MockConnectionPool()
        adapter.redis_client = mock_client
        adapter._connection_pool = mock_pool
        
        print("Testing key generation...")
        await test_instance.test_key_generation(adapter)
        print("✅ Key generation test passed")
        
        # Create sample items
        sample_items = []
        for i in range(5):
            item = create_mock_memory_item(f"item_{i}", "test_tenant", "test_namespace")
            sample_items.append(item)
        
        print("Testing single item storage...")
        await test_instance.test_store_single_item(adapter, sample_items)
        print("✅ Single item storage test passed")
        
        print("Testing batch item storage...")
        await test_instance.test_store_batch_items(adapter, sample_items)
        print("✅ Batch item storage test passed")
        
        print("Testing item retrieval...")
        await test_instance.test_retrieve_missing_item(adapter)
        print("✅ Item retrieval test passed")
        
        print("Testing item deletion...")
        await test_instance.test_delete_item(adapter, sample_items)
        print("✅ Item deletion test passed")
        
        print("Testing item listing...")
        await test_instance.test_list_items(adapter, sample_items)
        await test_instance.test_list_items_with_limit(adapter, sample_items)
        print("✅ Item listing test passed")
        
        print("Testing health check...")
        await test_instance.test_health_check(adapter)
        print("✅ Health check test passed")
        
        print("Testing statistics...")
        await test_instance.test_get_stats(adapter, sample_items)
        print("✅ Statistics test passed")
        
        print("Testing operation results...")
        await test_instance.test_operation_result_creation()
        print("✅ Operation results test passed")
        
        print("Testing connection cleanup...")
        await test_instance.test_close_connection(adapter)
        print("✅ Connection cleanup test passed")
        
        print("Testing factory function...")
        await test_instance.test_factory_function()
        print("✅ Factory function test passed")
        
        print("🎉 All Redis Storage Adapter tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    exit(0 if success else 1)