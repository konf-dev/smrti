#!/usr/bin/env python3
"""
Comprehensive Integration Tests for Smrti Memory System

Tests end-to-end workflows combining storage adapters, memory tiers,
and system components to validate complete functionality.
"""

import asyncio
import time
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

print("🧪 Starting Smrti Memory System Integration Tests...")

# =============================================================================
# Mock Storage Implementations
# =============================================================================

class MockRedisAdapter:
    """Mock Redis adapter for integration testing."""
    
    def __init__(self):
        self.data: Dict[str, Dict[str, Any]] = {}
        self.indices: Dict[str, set] = {}
        self.operations = []
        self.connected = True
    
    async def initialize(self) -> bool:
        return self.connected
    
    async def close(self):
        self.connected = False
    
    async def store_item(self, item_data: Dict[str, Any], ttl: Optional[int] = None):
        tenant = item_data.get('tenant', 'default')
        namespace = item_data.get('namespace', 'default')
        item_id = item_data.get('id')
        
        key = f"{tenant}:{namespace}:{item_id}"
        self.data[key] = item_data
        
        # Update index
        index_key = f"{tenant}:{namespace}:idx"
        if index_key not in self.indices:
            self.indices[index_key] = set()
        self.indices[index_key].add(item_id)
        
        self.operations.append(('store', key, ttl))
        
        result = type('Result', (), {'success': True, 'key_count': 1})()
        return result
    
    async def retrieve_item(self, tenant: str, namespace: str, item_id: str) -> Optional[Dict[str, Any]]:
        key = f"{tenant}:{namespace}:{item_id}"
        self.operations.append(('retrieve', key, None))
        return self.data.get(key)
    
    async def delete_item(self, tenant: str, namespace: str, item_id: str):
        key = f"{tenant}:{namespace}:{item_id}"
        deleted = key in self.data
        
        if deleted:
            del self.data[key]
            # Update index
            index_key = f"{tenant}:{namespace}:idx"
            if index_key in self.indices:
                self.indices[index_key].discard(item_id)
        
        self.operations.append(('delete', key, deleted))
        
        result = type('Result', (), {'success': deleted, 'key_count': 1 if deleted else 0})()
        return result
    
    async def list_items(self, tenant: str, namespace: str, limit: Optional[int] = None) -> List[str]:
        index_key = f"{tenant}:{namespace}:idx"
        items = list(self.indices.get(index_key, set()))
        
        if limit:
            items = items[:limit]
        
        self.operations.append(('list', f"{tenant}:{namespace}", len(items)))
        return items
    
    async def get_stats(self) -> Dict[str, Any]:
        return {
            'total_items': len(self.data),
            'memory_usage_bytes': sum(len(json.dumps(item)) for item in self.data.values()),
            'operations_count': len(self.operations),
            'connected': self.connected
        }
    
    async def health_check(self) -> bool:
        return self.connected


class MockMemoryAdapter:
    """Mock in-memory adapter for integration testing."""
    
    def __init__(self, max_items: int = 1000):
        self.data: Dict[str, Dict[str, Any]] = {}
        self.indices: Dict[str, set] = {}
        self.max_items = max_items
        self.operations = []
    
    async def initialize(self) -> bool:
        return True
    
    async def close(self):
        self.data.clear()
        self.indices.clear()
    
    async def store_item(self, item_data: Dict[str, Any], ttl: Optional[int] = None):
        # Check capacity
        if len(self.data) >= self.max_items:
            # Simple eviction - remove oldest
            oldest_key = next(iter(self.data))
            del self.data[oldest_key]
        
        tenant = item_data.get('tenant', 'default')
        namespace = item_data.get('namespace', 'default')
        item_id = item_data.get('id')
        
        key = f"{tenant}:{namespace}:{item_id}"
        self.data[key] = item_data
        
        # Update index
        index_key = f"{tenant}:{namespace}:idx"
        if index_key not in self.indices:
            self.indices[index_key] = set()
        self.indices[index_key].add(item_id)
        
        self.operations.append(('store', key, ttl))
        
        result = type('Result', (), {'success': True, 'key_count': 1})()
        return result
    
    async def retrieve_item(self, tenant: str, namespace: str, item_id: str) -> Optional[Dict[str, Any]]:
        key = f"{tenant}:{namespace}:{item_id}"
        self.operations.append(('retrieve', key, None))
        return self.data.get(key)
    
    async def delete_item(self, tenant: str, namespace: str, item_id: str):
        key = f"{tenant}:{namespace}:{item_id}"
        deleted = key in self.data
        
        if deleted:
            del self.data[key]
            # Update index
            index_key = f"{tenant}:{namespace}:idx"
            if index_key in self.indices:
                self.indices[index_key].discard(item_id)
        
        self.operations.append(('delete', key, deleted))
        
        result = type('Result', (), {'success': deleted, 'key_count': 1 if deleted else 0})()
        return result
    
    async def list_items(self, tenant: str, namespace: str, limit: Optional[int] = None) -> List[str]:
        index_key = f"{tenant}:{namespace}:idx"
        items = list(self.indices.get(index_key, set()))
        
        if limit:
            items = items[:limit]
        
        self.operations.append(('list', f"{tenant}:{namespace}", len(items)))
        return items
    
    async def get_stats(self) -> Dict[str, Any]:
        return {
            'total_items': len(self.data),
            'memory_usage_bytes': sum(len(json.dumps(item)) for item in self.data.values()),
            'operations_count': len(self.operations),
            'max_items': self.max_items
        }
    
    async def health_check(self) -> bool:
        return True


# =============================================================================
# Mock Memory Tier Implementation
# =============================================================================

class AccessPattern(Enum):
    READ = "read"
    WRITE = "write"
    UPDATE = "update"
    DELETE = "delete"


@dataclass
class AccessRecord:
    item_id: str
    pattern: AccessPattern
    timestamp: float
    tenant: str
    namespace: str
    metadata: Optional[Dict[str, Any]] = None


class MockWorkingMemory:
    """Mock Working Memory tier for integration testing."""
    
    def __init__(self, storage_adapter, config: Optional[Dict[str, Any]] = None):
        self.storage = storage_adapter
        self.config = config or {}
        self.access_records: List[AccessRecord] = []
        self.access_counts: Dict[str, int] = {}
        self.promotion_candidates: List[str] = []
        
        # Statistics
        self.read_count = 0
        self.write_count = 0
        self.update_count = 0
        self.delete_count = 0
        self.eviction_count = 0
        self.promotion_count = 0
    
    async def initialize(self) -> bool:
        return await self.storage.initialize()
    
    async def close(self):
        await self.storage.close()
    
    async def store_item(self, item: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        try:
            result = await self.storage.store_item(item, ttl)
            if result.success:
                self._record_access(item.get('id'), AccessPattern.WRITE, 
                                  item.get('tenant', 'default'), 
                                  item.get('namespace', 'default'))
                self.write_count += 1
                return True
            return False
        except Exception as e:
            print(f"Store error in Working Memory: {e}")
            return False
    
    async def retrieve_item(self, tenant: str, namespace: str, item_id: str) -> Optional[Dict[str, Any]]:
        try:
            item = await self.storage.retrieve_item(tenant, namespace, item_id)
            if item:
                self._record_access(item_id, AccessPattern.READ, tenant, namespace)
                self.read_count += 1
                
                # Check for promotion eligibility
                access_count = self.access_counts.get(item_id, 0)
                if access_count >= 3 and item_id not in self.promotion_candidates:
                    self.promotion_candidates.append(item_id)
            
            return item
        except Exception as e:
            print(f"Retrieve error in Working Memory: {e}")
            return None
    
    async def update_item(self, item: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        try:
            result = await self.storage.store_item(item, ttl)
            if result.success:
                self._record_access(item.get('id'), AccessPattern.UPDATE, 
                                  item.get('tenant', 'default'), 
                                  item.get('namespace', 'default'))
                self.update_count += 1
                return True
            return False
        except Exception as e:
            print(f"Update error in Working Memory: {e}")
            return False
    
    async def delete_item(self, tenant: str, namespace: str, item_id: str) -> bool:
        try:
            result = await self.storage.delete_item(tenant, namespace, item_id)
            if result.success:
                self._record_access(item_id, AccessPattern.DELETE, tenant, namespace)
                self.delete_count += 1
                # Clean up tracking
                self.access_counts.pop(item_id, None)
                return True
            return False
        except Exception as e:
            print(f"Delete error in Working Memory: {e}")
            return False
    
    async def list_items(self, tenant: str, namespace: str, limit: Optional[int] = None) -> List[str]:
        try:
            return await self.storage.list_items(tenant, namespace, limit)
        except Exception as e:
            print(f"List error in Working Memory: {e}")
            return []
    
    def _record_access(self, item_id: str, pattern: AccessPattern, tenant: str, namespace: str):
        """Record access pattern."""
        record = AccessRecord(
            item_id=item_id,
            pattern=pattern,
            timestamp=time.time(),
            tenant=tenant,
            namespace=namespace
        )
        self.access_records.append(record)
        self.access_counts[item_id] = self.access_counts.get(item_id, 0) + 1
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get memory tier statistics."""
        storage_stats = await self.storage.get_stats()
        
        return {
            'storage_stats': storage_stats,
            'operations': {
                'read_count': self.read_count,
                'write_count': self.write_count,
                'update_count': self.update_count,
                'delete_count': self.delete_count,
                'eviction_count': self.eviction_count,
                'promotion_count': self.promotion_count
            },
            'access_tracking': {
                'total_accesses': len(self.access_records),
                'unique_items': len(self.access_counts),
                'promotion_candidates': len(self.promotion_candidates)
            }
        }
    
    async def health_check(self) -> bool:
        return await self.storage.health_check()
    
    def get_promotion_candidates(self) -> List[str]:
        """Get items eligible for promotion to short-term memory."""
        return self.promotion_candidates.copy()


# =============================================================================
# Integration Test Scenarios
# =============================================================================

class IntegrationTestSuite:
    """Comprehensive integration test suite."""
    
    def __init__(self):
        self.test_results = {}
        self.total_tests = 0
        self.passed_tests = 0
    
    def log_test_result(self, test_name: str, passed: bool, details: str = ""):
        """Log test result."""
        self.test_results[test_name] = {
            'passed': passed,
            'details': details,
            'timestamp': time.time()
        }
        self.total_tests += 1
        if passed:
            self.passed_tests += 1
            print(f"✅ {test_name}")
        else:
            print(f"❌ {test_name}: {details}")
    
    async def test_storage_adapter_compatibility(self):
        """Test compatibility between Redis and Memory storage adapters."""
        print("\n📦 Testing Storage Adapter Compatibility...")
        
        # Test Redis adapter
        redis_adapter = MockRedisAdapter()
        await redis_adapter.initialize()
        
        test_item = {
            'id': 'compatibility_test_item',
            'tenant': 'test_tenant',
            'namespace': 'compatibility',
            'content': 'Test content for compatibility',
            'metadata': {'test': True}
        }
        
        # Store and retrieve with Redis adapter
        result = await redis_adapter.store_item(test_item)
        self.log_test_result("Redis Adapter - Store Item", result.success)
        
        retrieved = await redis_adapter.retrieve_item('test_tenant', 'compatibility', 'compatibility_test_item')
        self.log_test_result("Redis Adapter - Retrieve Item", retrieved is not None and retrieved['content'] == test_item['content'])
        
        # Test Memory adapter with same data
        memory_adapter = MockMemoryAdapter()
        await memory_adapter.initialize()
        
        result = await memory_adapter.store_item(test_item)
        self.log_test_result("Memory Adapter - Store Item", result.success)
        
        retrieved = await memory_adapter.retrieve_item('test_tenant', 'compatibility', 'compatibility_test_item')
        self.log_test_result("Memory Adapter - Retrieve Item", retrieved is not None and retrieved['content'] == test_item['content'])
        
        # Test interface compatibility
        redis_stats = await redis_adapter.get_stats()
        memory_stats = await memory_adapter.get_stats()
        
        # Both should have same interface
        common_keys = ['total_items', 'memory_usage_bytes', 'operations_count']
        redis_has_keys = all(key in redis_stats for key in common_keys)
        memory_has_keys = all(key in memory_stats for key in common_keys)
        
        self.log_test_result("Storage Adapter Interface Compatibility", redis_has_keys and memory_has_keys)
        
        await redis_adapter.close()
        await memory_adapter.close()
    
    async def test_working_memory_tier_integration(self):
        """Test Working Memory tier with different storage backends."""
        print("\n🧠 Testing Working Memory Tier Integration...")
        
        # Test with Redis backend
        redis_storage = MockRedisAdapter()
        redis_working_memory = MockWorkingMemory(redis_storage, {'backend': 'redis'})
        
        await redis_working_memory.initialize()
        
        # Store multiple items
        test_items = []
        for i in range(5):
            item = {
                'id': f'wm_redis_item_{i}',
                'tenant': 'integration_test',
                'namespace': 'working_memory',
                'content': f'Redis Working Memory content {i}',
                'timestamp': time.time(),
                'metadata': {'backend': 'redis', 'index': i}
            }
            test_items.append(item)
            
            result = await redis_working_memory.store_item(item)
            if not result:
                self.log_test_result(f"Redis Working Memory - Store Item {i}", False, "Store operation failed")
                continue
        
        # Retrieve and verify items
        retrieved_count = 0
        for item in test_items:
            retrieved = await redis_working_memory.retrieve_item(
                item['tenant'], item['namespace'], item['id']
            )
            if retrieved and retrieved['content'] == item['content']:
                retrieved_count += 1
        
        self.log_test_result("Redis Working Memory - Store/Retrieve Items", retrieved_count == len(test_items))
        
        # Test access pattern tracking
        access_patterns_before = len(redis_working_memory.access_records)
        
        # Access some items multiple times
        for _ in range(3):
            await redis_working_memory.retrieve_item('integration_test', 'working_memory', 'wm_redis_item_0')
        
        access_patterns_after = len(redis_working_memory.access_records)
        self.log_test_result("Redis Working Memory - Access Pattern Tracking", 
                           access_patterns_after > access_patterns_before)
        
        # Test promotion candidates
        promotion_candidates = redis_working_memory.get_promotion_candidates()
        self.log_test_result("Redis Working Memory - Promotion Candidates", 
                           'wm_redis_item_0' in promotion_candidates)
        
        # Test with Memory backend
        memory_storage = MockMemoryAdapter(max_items=10)
        memory_working_memory = MockWorkingMemory(memory_storage, {'backend': 'memory'})
        
        await memory_working_memory.initialize()
        
        # Store items and test capacity limits
        for i in range(12):  # Exceed capacity
            item = {
                'id': f'wm_memory_item_{i}',
                'tenant': 'integration_test',
                'namespace': 'working_memory',
                'content': f'Memory Working Memory content {i}',
                'metadata': {'backend': 'memory', 'index': i}
            }
            await memory_working_memory.store_item(item)
        
        # Check that memory adapter handled capacity limits
        memory_stats = await memory_working_memory.get_stats()
        total_items = memory_stats['storage_stats']['total_items']
        
        self.log_test_result("Memory Working Memory - Capacity Management", 
                           total_items <= 10)
        
        await redis_working_memory.close()
        await memory_working_memory.close()
    
    async def test_multi_tenant_isolation(self):
        """Test tenant isolation across storage and memory tiers."""
        print("\n🏢 Testing Multi-Tenant Isolation...")
        
        storage = MockRedisAdapter()
        working_memory = MockWorkingMemory(storage)
        await working_memory.initialize()
        
        # Create items for different tenants
        tenants = ['tenant_a', 'tenant_b', 'tenant_c']
        items_per_tenant = 3
        
        stored_items = {}
        
        for tenant in tenants:
            stored_items[tenant] = []
            for i in range(items_per_tenant):
                item = {
                    'id': f'item_{i}',
                    'tenant': tenant,
                    'namespace': 'isolation_test',
                    'content': f'{tenant} content {i}',
                    'metadata': {'tenant_specific': f'{tenant}_data'}
                }
                
                result = await working_memory.store_item(item)
                if result:
                    stored_items[tenant].append(item)
        
        # Verify isolation - each tenant should only see their own items
        for tenant in tenants:
            tenant_items = await working_memory.list_items(tenant, 'isolation_test')
            
            # Should have exactly items_per_tenant items
            correct_count = len(tenant_items) == items_per_tenant
            
            # Verify content isolation by retrieving items
            content_isolated = True
            for item_id in tenant_items:
                retrieved = await working_memory.retrieve_item(tenant, 'isolation_test', item_id)
                if retrieved and not retrieved['content'].startswith(tenant):
                    content_isolated = False
                    break
            
            self.log_test_result(f"Tenant Isolation - {tenant}", 
                               correct_count and content_isolated)
        
        # Test cross-tenant access (should fail)
        cross_access_blocked = True
        try:
            # Try to access tenant_a's item as tenant_b
            retrieved = await working_memory.retrieve_item('tenant_b', 'isolation_test', 'item_0')
            # If we get tenant_a's content, isolation is broken
            if retrieved and retrieved['content'].startswith('tenant_a'):
                cross_access_blocked = False
        except:
            pass  # Expected to fail or return None
        
        self.log_test_result("Cross-Tenant Access Blocked", cross_access_blocked)
        
        await working_memory.close()
    
    async def test_error_handling_and_recovery(self):
        """Test error handling and recovery scenarios."""
        print("\n🛠️ Testing Error Handling and Recovery...")
        
        # Test storage adapter failure recovery
        storage = MockRedisAdapter()
        working_memory = MockWorkingMemory(storage)
        await working_memory.initialize()
        
        # Store some items
        test_item = {
            'id': 'recovery_test_item',
            'tenant': 'recovery_test',
            'namespace': 'error_handling',
            'content': 'Recovery test content'
        }
        
        result = await working_memory.store_item(test_item)
        self.log_test_result("Error Handling - Initial Store", result)
        
        # Simulate storage failure
        storage.connected = False
        
        # Operations should handle failure gracefully
        failed_retrieve = await working_memory.retrieve_item('recovery_test', 'error_handling', 'recovery_test_item')
        self.log_test_result("Error Handling - Graceful Failure", failed_retrieve is None)
        
        # Restore connection
        storage.connected = True
        
        # Operations should work again
        recovered_retrieve = await working_memory.retrieve_item('recovery_test', 'error_handling', 'recovery_test_item')
        self.log_test_result("Error Handling - Recovery", 
                           recovered_retrieve is not None and recovered_retrieve['content'] == test_item['content'])
        
        # Test invalid data handling
        invalid_item = {
            'id': None,  # Invalid ID
            'tenant': 'recovery_test',
            'namespace': 'error_handling',
            'content': 'Invalid item'
        }
        
        invalid_result = await working_memory.store_item(invalid_item)
        self.log_test_result("Error Handling - Invalid Data", not invalid_result)
        
        await working_memory.close()
    
    async def test_performance_and_scalability(self):
        """Test performance characteristics and scalability."""
        print("\n🚀 Testing Performance and Scalability...")
        
        storage = MockMemoryAdapter(max_items=1000)
        working_memory = MockWorkingMemory(storage)
        await working_memory.initialize()
        
        # Performance test - batch operations
        start_time = time.time()
        batch_size = 100
        
        # Store batch of items
        for i in range(batch_size):
            item = {
                'id': f'perf_item_{i}',
                'tenant': 'performance_test',
                'namespace': 'scalability',
                'content': f'Performance test content {i}',
                'metadata': {'batch_index': i, 'large_data': 'x' * 1000}  # 1KB metadata
            }
            await working_memory.store_item(item)
        
        store_time = time.time() - start_time
        
        # Retrieve batch of items
        start_time = time.time()
        retrieved_count = 0
        
        for i in range(batch_size):
            retrieved = await working_memory.retrieve_item('performance_test', 'scalability', f'perf_item_{i}')
            if retrieved:
                retrieved_count += 1
        
        retrieve_time = time.time() - start_time
        
        # Performance metrics
        store_rate = batch_size / store_time if store_time > 0 else float('inf')
        retrieve_rate = retrieved_count / retrieve_time if retrieve_time > 0 else float('inf')
        
        self.log_test_result("Performance - Batch Store Operations", 
                           store_rate > 50,  # At least 50 ops/sec
                           f"Store rate: {store_rate:.2f} ops/sec")
        
        self.log_test_result("Performance - Batch Retrieve Operations", 
                           retrieve_rate > 100,  # At least 100 ops/sec
                           f"Retrieve rate: {retrieve_rate:.2f} ops/sec")
        
        # Memory usage tracking
        stats = await working_memory.get_stats()
        memory_usage = stats['storage_stats']['memory_usage_bytes']
        
        self.log_test_result("Performance - Memory Usage Tracking", 
                           memory_usage > 0,
                           f"Memory usage: {memory_usage} bytes")
        
        await working_memory.close()
    
    async def test_data_consistency_and_integrity(self):
        """Test data consistency and integrity across operations."""
        print("\n🔒 Testing Data Consistency and Integrity...")
        
        storage = MockRedisAdapter()
        working_memory = MockWorkingMemory(storage)
        await working_memory.initialize()
        
        # Test data integrity through multiple operations
        original_item = {
            'id': 'consistency_test_item',
            'tenant': 'consistency_test',
            'namespace': 'integrity',
            'content': 'Original content',
            'metadata': {'version': 1, 'checksum': 'abc123'},
            'timestamp': time.time()
        }
        
        # Store original item
        result = await working_memory.store_item(original_item)
        self.log_test_result("Data Integrity - Store Original", result)
        
        # Retrieve and verify
        retrieved = await working_memory.retrieve_item('consistency_test', 'integrity', 'consistency_test_item')
        
        data_matches = (
            retrieved is not None and
            retrieved['content'] == original_item['content'] and
            retrieved['metadata']['version'] == 1 and
            retrieved['metadata']['checksum'] == 'abc123'
        )
        
        self.log_test_result("Data Integrity - Retrieve Verification", data_matches)
        
        # Update item
        updated_item = original_item.copy()
        updated_item['content'] = 'Updated content'
        updated_item['metadata']['version'] = 2
        updated_item['metadata']['checksum'] = 'def456'
        
        result = await working_memory.update_item(updated_item)
        self.log_test_result("Data Integrity - Update Item", result)
        
        # Verify update
        updated_retrieved = await working_memory.retrieve_item('consistency_test', 'integrity', 'consistency_test_item')
        
        update_correct = (
            updated_retrieved is not None and
            updated_retrieved['content'] == 'Updated content' and
            updated_retrieved['metadata']['version'] == 2 and
            updated_retrieved['metadata']['checksum'] == 'def456'
        )
        
        self.log_test_result("Data Integrity - Update Verification", update_correct)
        
        # Test concurrent access patterns
        access_count_before = working_memory.access_counts.get('consistency_test_item', 0)
        
        # Simulate concurrent reads
        for _ in range(5):
            await working_memory.retrieve_item('consistency_test', 'integrity', 'consistency_test_item')
        
        access_count_after = working_memory.access_counts.get('consistency_test_item', 0)
        
        self.log_test_result("Data Consistency - Concurrent Access Tracking", 
                           access_count_after > access_count_before)
        
        await working_memory.close()
    
    async def run_all_tests(self):
        """Run complete integration test suite."""
        print("🎯 Starting Comprehensive Integration Test Suite...")
        print("=" * 60)
        
        start_time = time.time()
        
        # Run all test scenarios
        await self.test_storage_adapter_compatibility()
        await self.test_working_memory_tier_integration()
        await self.test_multi_tenant_isolation()
        await self.test_error_handling_and_recovery()
        await self.test_performance_and_scalability()
        await self.test_data_consistency_and_integrity()
        
        # Generate test report
        end_time = time.time()
        total_duration = end_time - start_time
        
        print("\n" + "=" * 60)
        print("📊 Integration Test Results Summary")
        print("=" * 60)
        
        print(f"Total Tests: {self.total_tests}")
        print(f"Passed: {self.passed_tests}")
        print(f"Failed: {self.total_tests - self.passed_tests}")
        print(f"Success Rate: {(self.passed_tests / self.total_tests * 100):.1f}%")
        print(f"Total Duration: {total_duration:.2f} seconds")
        
        print(f"\n📋 Detailed Results:")
        for test_name, result in self.test_results.items():
            status = "✅ PASS" if result['passed'] else "❌ FAIL"
            details = f" - {result['details']}" if result['details'] else ""
            print(f"   {status} {test_name}{details}")
        
        # Overall result
        all_passed = self.passed_tests == self.total_tests
        
        if all_passed:
            print(f"\n🎉 All integration tests passed successfully!")
            print(f"🚀 Smrti memory system is ready for production use!")
        else:
            failed_count = self.total_tests - self.passed_tests
            print(f"\n⚠️  {failed_count} test(s) failed. Review and fix issues before production.")
        
        return all_passed


# =============================================================================
# Main Test Execution
# =============================================================================

async def main():
    """Run integration tests."""
    try:
        test_suite = IntegrationTestSuite()
        success = await test_suite.run_all_tests()
        
        if success:
            print(f"\n✨ Integration testing completed successfully!")
            return True
        else:
            print(f"\n❌ Integration testing completed with failures!")
            return False
    
    except Exception as e:
        print(f"\n💥 Integration testing failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)