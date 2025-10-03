#!/usr/bin/env python3
"""
Simple Memory adapter test - isolated from main codebase dependencies.
"""

import asyncio
import time
from typing import Dict, Any, List

# Add the smrti package to path
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

# Import directly from the file
from smrti.adapters.storage.memory_adapter import MemoryStorageAdapter, MemoryConfig, MemoryOperationResult


async def test_memory_adapter():
    """Run Memory adapter tests."""
    print("🧪 Testing In-Memory Storage Adapter...")
    
    # Test configuration
    config = MemoryConfig(
        default_ttl=60,
        max_items_per_namespace=100,
        cleanup_interval=10,
        key_prefix="test_smrti"
    )
    
    print("✅ Config created")
    
    # Test storage ID generation
    storage_id = config.get_storage_id()
    expected = "memory://test_smrti"
    assert storage_id == expected, f"Expected {expected}, got {storage_id}"
    print("✅ Storage ID generation test passed")
    
    # Create adapter
    adapter = MemoryStorageAdapter(config)
    
    # Initialize
    success = await adapter.initialize()
    assert success, "Adapter initialization failed"
    print("✅ Adapter initialization test passed")
    
    # Test health check
    healthy = await adapter.health_check()
    assert healthy, "Health check failed"
    print("✅ Health check test passed")
    
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
    result = await adapter.store_item(test_item, ttl=300)
    assert result.success, f"Store failed: {result.error_message}"
    assert result.key_count == 1
    assert result.execution_time_ms >= 0
    assert result.memory_usage_bytes > 0
    print("✅ Single item storage test passed")
    
    # Retrieve item
    retrieved = await adapter.retrieve_item('test_tenant', 'test_namespace', 'test_item_1')
    assert retrieved is not None, "Item not retrieved"
    assert retrieved['id'] == test_item['id']
    assert retrieved['content'] == test_item['content']
    print("✅ Item retrieval test passed")
    
    # Store multiple items
    items = []
    for i in range(5):
        item = {
            'id': f'test_item_{i+2}',
            'tenant': 'test_tenant',
            'namespace': 'test_namespace', 
            'content': f'Content for item {i+2}',
            'metadata': {'index': i+2},
            'timestamp': time.time()
        }
        items.append(item)
    
    # Batch store
    batch_result = await adapter.store_items_batch(items)
    assert batch_result.success, f"Batch store failed: {batch_result.error_message}"
    assert batch_result.key_count == 5
    print("✅ Batch item storage test passed")
    
    # Batch retrieve
    item_ids = [item['id'] for item in items]
    retrieved_batch = await adapter.retrieve_items_batch('test_tenant', 'test_namespace', item_ids)
    assert len(retrieved_batch) == 5, f"Expected 5 items, got {len(retrieved_batch)}"
    for item in items:
        assert item['id'] in retrieved_batch
        assert retrieved_batch[item['id']]['content'] == item['content']
    print("✅ Batch item retrieval test passed")
    
    # List items
    item_ids_list = await adapter.list_items('test_tenant', 'test_namespace')
    assert len(item_ids_list) == 6, f"Expected 6 items, got {len(item_ids_list)}"  # 1 original + 5 batch
    expected_ids = {'test_item_1', 'test_item_2', 'test_item_3', 'test_item_4', 'test_item_5', 'test_item_6'}
    assert set(item_ids_list) == expected_ids
    print("✅ Item listing test passed")
    
    # Test listing with limit
    limited_ids = await adapter.list_items('test_tenant', 'test_namespace', limit=3)
    assert len(limited_ids) == 3, f"Expected 3 items, got {len(limited_ids)}"
    print("✅ Limited item listing test passed")
    
    # Delete item
    delete_result = await adapter.delete_item('test_tenant', 'test_namespace', 'test_item_1')
    assert delete_result.success, f"Delete failed: {delete_result.error_message}"
    assert delete_result.key_count == 1
    
    # Verify deletion
    deleted_item = await adapter.retrieve_item('test_tenant', 'test_namespace', 'test_item_1')
    assert deleted_item is None, "Item should be deleted"
    print("✅ Item deletion test passed")
    
    # Test TTL expiration (simulate)
    short_ttl_item = {
        'id': 'short_ttl_item',
        'tenant': 'test_tenant',
        'namespace': 'test_namespace',
        'content': 'This will expire quickly',
        'timestamp': time.time()
    }
    
    # Store with very short TTL (1 second)
    await adapter.store_item(short_ttl_item, ttl=1)
    
    # Should exist immediately
    exists = await adapter.retrieve_item('test_tenant', 'test_namespace', 'short_ttl_item')
    assert exists is not None, "Item should exist"
    
    # Wait for expiration
    await asyncio.sleep(1.5)
    
    # Should be expired now
    expired = await adapter.retrieve_item('test_tenant', 'test_namespace', 'short_ttl_item')
    assert expired is None, "Item should be expired"
    print("✅ TTL expiration test passed")
    
    # Test cleanup
    cleanup_result = await adapter.cleanup_expired('test_tenant', 'test_namespace')
    assert cleanup_result.success, f"Cleanup failed: {cleanup_result.error_message}"
    print("✅ Cleanup test passed")
    
    # Get statistics
    stats = await adapter.get_stats()
    assert 'operations_count' in stats
    assert stats['operations_count'] > 0
    assert 'success_rate' in stats
    assert stats['success_rate'] >= 0.0
    assert 'memory_usage_bytes' in stats
    assert stats['memory_usage_bytes'] > 0
    assert 'total_items' in stats
    assert 'namespace_stats' in stats
    print("✅ Statistics test passed")
    
    # Test operation results
    success_result = MemoryOperationResult.success_result("test_op", 5, 123.45, 1024)
    assert success_result.success
    assert success_result.operation == "test_op"
    assert success_result.key_count == 5
    assert success_result.memory_usage_bytes == 1024
    
    error_result = MemoryOperationResult.error_result("test_op", "error", 67.89)
    assert not error_result.success
    assert error_result.error_message == "error"
    print("✅ Operation result test passed")
    
    # Test namespace limits
    limited_config = MemoryConfig(max_items_per_namespace=2)
    limited_adapter = MemoryStorageAdapter(limited_config)
    await limited_adapter.initialize()
    
    # Should be able to store up to limit
    for i in range(2):
        item = {'id': f'limit_item_{i}', 'tenant': 'limit', 'namespace': 'test', 'content': 'test'}
        result = await limited_adapter.store_item(item)
        assert result.success, f"Should be able to store item {i}"
    
    # Should fail when exceeding limit
    overflow_item = {'id': 'overflow_item', 'tenant': 'limit', 'namespace': 'test', 'content': 'test'}
    overflow_result = await limited_adapter.store_item(overflow_item)
    assert not overflow_result.success, "Should fail when exceeding namespace limit"
    assert "limit exceeded" in overflow_result.error_message.lower()
    
    await limited_adapter.close()
    print("✅ Namespace limit test passed")
    
    # Close adapter
    await adapter.close()
    print("✅ Connection cleanup test passed")
    
    print("\n🎉 All In-Memory Storage Adapter tests passed!")
    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_memory_adapter())
        print("\n✨ Memory adapter testing completed successfully!")
        exit(0)
    except Exception as e:
        print(f"\n❌ Tests failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)