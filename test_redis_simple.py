#!/usr/bin/env python3
"""
Simple Redis adapter test - isolated from main codebase dependencies.
"""

import asyncio
import json
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

# Mock Redis for testing
class MockRedisClient:
    """Mock Redis client for testing."""
    
    def __init__(self):
        self.data: Dict[str, Any] = {}
        self.sets: Dict[str, set] = {}
        self.expires: Dict[str, float] = {}
    
    async def ping(self):
        return True
    
    async def setex(self, key: str, ttl: int, value: str):
        self.data[key] = value
        self.expires[key] = time.time() + ttl
        return True
    
    async def get(self, key: str):
        if key in self.data:
            if key in self.expires and time.time() > self.expires[key]:
                del self.data[key]
                del self.expires[key]
                return None
            return self.data[key]
        return None
    
    async def delete(self, key: str):
        deleted = 1 if key in self.data else 0
        self.data.pop(key, None)
        self.expires.pop(key, None)
        return deleted
    
    async def sadd(self, key: str, *members):
        if key not in self.sets:
            self.sets[key] = set()
        for member in members:
            self.sets[key].add(member)
        return len(members)
    
    async def srem(self, key: str, *members):
        if key not in self.sets:
            return 0
        removed = 0
        for member in members:
            if member in self.sets[key]:
                self.sets[key].remove(member)
                removed += 1
        return removed
    
    async def smembers(self, key: str):
        return list(self.sets.get(key, set()))
    
    async def info(self):
        return {"connected_clients": 1, "used_memory": 1024}
    
    def pipeline(self):
        return MockPipeline(self)
    
    async def close(self):
        pass


class MockPipeline:
    """Mock Redis pipeline."""
    
    def __init__(self, redis_client: MockRedisClient):
        self.redis_client = redis_client
        self.commands = []
    
    def setex(self, key: str, ttl: int, value: str):
        self.commands.append(('setex', key, ttl, value))
        return self
    
    def sadd(self, key: str, *members):
        self.commands.append(('sadd', key, *members))
        return self
    
    async def execute(self):
        results = []
        for cmd in self.commands:
            if cmd[0] == 'setex':
                result = await self.redis_client.setex(cmd[1], cmd[2], cmd[3])
            elif cmd[0] == 'sadd':
                result = await self.redis_client.sadd(cmd[1], *cmd[2:])
            else:
                result = None
            results.append(result)
        self.commands.clear()
        return results


@dataclass
class RedisConfig:
    """Redis configuration."""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    key_prefix: str = "smrti"
    default_ttl: int = 3600
    
    def get_redis_url(self) -> str:
        """Generate Redis URL."""
        auth = ""
        if self.password:
            auth = f":{self.password}@"
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


@dataclass
class RedisOperationResult:
    """Result of Redis operation."""
    success: bool
    operation: str
    key_count: int
    execution_time_ms: float
    error_message: Optional[str] = None
    
    @classmethod
    def success_result(cls, operation: str, key_count: int, execution_time: float) -> 'RedisOperationResult':
        return cls(True, operation, key_count, execution_time)
    
    @classmethod
    def error_result(cls, operation: str, error: str, execution_time: float) -> 'RedisOperationResult':
        return cls(False, operation, 0, execution_time, error)


class SimpleRedisAdapter:
    """Simplified Redis adapter for testing."""
    
    def __init__(self, config: RedisConfig):
        self.config = config
        self.redis_client: Optional[MockRedisClient] = None
        self._operations_count = 0
        self._error_count = 0
        self._total_time_ms = 0.0
    
    def _make_key(self, tenant: str, namespace: str, key_type: str, item_id: str) -> str:
        """Generate Redis key."""
        return f"{self.config.key_prefix}:{tenant}:{namespace}:{key_type}:{item_id}"
    
    def _make_index_key(self, tenant: str, namespace: str, index_name: str) -> str:
        """Generate index key."""
        return f"{self.config.key_prefix}:{tenant}:{namespace}:idx:{index_name}"
    
    async def initialize(self) -> bool:
        """Initialize Redis connection."""
        try:
            self.redis_client = MockRedisClient()
            await self.redis_client.ping()
            return True
        except Exception as e:
            print(f"Redis initialization failed: {e}")
            return False
    
    async def store_item(self, item_data: Dict[str, Any], ttl: Optional[int] = None) -> RedisOperationResult:
        """Store single item."""
        start_time = time.time()
        
        try:
            if not self.redis_client:
                return RedisOperationResult.error_result("store_item", "No Redis client", 0.0)
            
            tenant = item_data.get('tenant', 'default')
            namespace = item_data.get('namespace', 'default')
            item_id = item_data.get('id', 'unknown')
            
            key = self._make_key(tenant, namespace, "item", item_id)
            index_key = self._make_index_key(tenant, namespace, "items")
            
            ttl = ttl or self.config.default_ttl
            
            # Store item and update index
            pipeline = self.redis_client.pipeline()
            pipeline.setex(key, ttl, json.dumps(item_data))
            pipeline.sadd(index_key, item_id)
            
            await pipeline.execute()
            
            execution_time = (time.time() - start_time) * 1000
            self._operations_count += 1
            self._total_time_ms += execution_time
            
            return RedisOperationResult.success_result("store_item", 1, execution_time)
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            self._error_count += 1
            return RedisOperationResult.error_result("store_item", str(e), execution_time)
    
    async def retrieve_item(self, tenant: str, namespace: str, item_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve single item."""
        try:
            if not self.redis_client:
                return None
            
            key = self._make_key(tenant, namespace, "item", item_id)
            data = await self.redis_client.get(key)
            
            if data:
                return json.loads(data)
            return None
            
        except Exception as e:
            print(f"Retrieve error: {e}")
            return None
    
    async def list_items(self, tenant: str, namespace: str) -> List[str]:
        """List all item IDs."""
        try:
            if not self.redis_client:
                return []
            
            index_key = self._make_index_key(tenant, namespace, "items")
            return await self.redis_client.smembers(index_key)
            
        except Exception as e:
            print(f"List error: {e}")
            return []
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get adapter statistics."""
        avg_time = self._total_time_ms / max(self._operations_count, 1)
        success_rate = 1.0 - (self._error_count / max(self._operations_count, 1))
        
        redis_info = {}
        if self.redis_client:
            redis_info = await self.redis_client.info()
        
        return {
            'operations_count': self._operations_count,
            'error_count': self._error_count,
            'average_operation_time_ms': avg_time,
            'success_rate': success_rate,
            'redis_info': redis_info,
            'config': {
                'host': self.config.host,
                'port': self.config.port,
                'db': self.config.db,
                'key_prefix': self.config.key_prefix
            }
        }
    
    async def close(self):
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None


async def test_redis_adapter():
    """Run Redis adapter tests."""
    print("🧪 Testing Simple Redis Storage Adapter...")
    
    # Test configuration
    config = RedisConfig(
        host="localhost", 
        port=6379, 
        db=15, 
        key_prefix="test_smrti"
    )
    
    print("✅ Config created")
    
    # Test URL generation
    url = config.get_redis_url()
    expected = "redis://localhost:6379/15"
    assert url == expected, f"Expected {expected}, got {url}"
    print("✅ URL generation test passed")
    
    # Create adapter
    adapter = SimpleRedisAdapter(config)
    
    # Initialize
    success = await adapter.initialize()
    assert success, "Adapter initialization failed"
    print("✅ Adapter initialization test passed")
    
    # Test data
    test_item = {
        'id': 'test_item_1',
        'tenant': 'test_tenant',
        'namespace': 'test_namespace',
        'content': 'This is test content',
        'metadata': {'priority': 'high', 'test': True},
        'timestamp': time.time()
    }
    
    # Store item
    result = await adapter.store_item(test_item, ttl=600)
    assert result.success, f"Store failed: {result.error_message}"
    assert result.key_count == 1
    assert result.execution_time_ms > 0
    print("✅ Single item storage test passed")
    
    # Retrieve item
    retrieved = await adapter.retrieve_item('test_tenant', 'test_namespace', 'test_item_1')
    assert retrieved is not None, "Item not retrieved"
    assert retrieved['id'] == test_item['id']
    assert retrieved['content'] == test_item['content']
    print("✅ Item retrieval test passed")
    
    # Store multiple items
    items = []
    for i in range(3):
        item = {
            'id': f'test_item_{i+2}',
            'tenant': 'test_tenant',
            'namespace': 'test_namespace',
            'content': f'Content for item {i+2}',
            'metadata': {'index': i+2},
            'timestamp': time.time()
        }
        result = await adapter.store_item(item)
        assert result.success
        items.append(item)
    
    print("✅ Multiple item storage test passed")
    
    # List items
    item_ids = await adapter.list_items('test_tenant', 'test_namespace')
    assert len(item_ids) == 4, f"Expected 4 items, got {len(item_ids)}"
    expected_ids = {'test_item_1', 'test_item_2', 'test_item_3', 'test_item_4'}
    assert set(item_ids) == expected_ids
    print("✅ Item listing test passed")
    
    # Get statistics
    stats = await adapter.get_stats()
    assert 'operations_count' in stats
    assert stats['operations_count'] >= 4  # At least 4 store operations
    assert 'success_rate' in stats
    assert stats['success_rate'] > 0.0
    print("✅ Statistics test passed")
    
    # Test operation results
    success_result = RedisOperationResult.success_result("test_op", 5, 123.45)
    assert success_result.success
    assert success_result.operation == "test_op"
    assert success_result.key_count == 5
    
    error_result = RedisOperationResult.error_result("test_op", "error", 67.89)
    assert not error_result.success
    assert error_result.error_message == "error"
    print("✅ Operation result test passed")
    
    # Close connection
    await adapter.close()
    print("✅ Connection cleanup test passed")
    
    print("\n🎉 All Redis Storage Adapter tests passed!")
    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_redis_adapter())
        print("\n✨ Redis adapter testing completed successfully!")
        exit(0)
    except Exception as e:
        print(f"\n❌ Tests failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)