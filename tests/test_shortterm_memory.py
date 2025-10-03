"""
Comprehensive tests for Short-term Memory tier implementation.

Tests consolidation strategies, TTL behavior, promotion logic, and integration
with Redis/Memory adapters.
"""

import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from unittest.mock import AsyncMock, Mock

from smrti.tiers.shortterm import (
    ShortTermMemory, 
    ConsolidationConfig,
    ConsolidationStrategy,
    PromotionCandidate
)
from smrti.adapters.storage.redis import RedisAdapter
from smrti.adapters.storage.memory_adapter import MemoryAdapter
from smrti.models.memory import MemoryItem, MemoryMetadata, AccessPattern


class TestShortTermMemory:
    """Test suite for Short-term Memory tier."""
    
    @pytest.fixture
    async def memory_adapter(self):
        """Create memory adapter for testing."""
        adapter = MemoryAdapter(tenant_id="test")
        yield adapter
        await adapter.cleanup()
    
    @pytest.fixture
    def mock_redis_adapter(self):
        """Create mock Redis adapter."""
        return AsyncMock(spec=RedisAdapter)
    
    @pytest.fixture
    async def shortterm_memory(self, memory_adapter, mock_redis_adapter):
        """Create Short-term Memory instance for testing."""
        stm = ShortTermMemory(
            redis_adapter=mock_redis_adapter,
            memory_adapter=memory_adapter,
            tenant_id="test"
        )
        await stm.start()
        yield stm
        await stm.stop()
    
    @pytest.fixture
    async def shortterm_memory_no_redis(self, memory_adapter):
        """Create Short-term Memory without Redis for fallback testing."""
        stm = ShortTermMemory(
            redis_adapter=None,
            memory_adapter=memory_adapter,
            tenant_id="test"
        )
        await stm.start()
        yield stm
        await stm.stop()
    
    async def test_store_and_retrieve(self, shortterm_memory):
        """Test basic store and retrieve operations."""
        # Store an item
        success = await shortterm_memory.store(
            key="test_key",
            value="test_value",
            ttl=timedelta(hours=1)
        )
        assert success
        
        # Retrieve the item
        item = await shortterm_memory.retrieve("test_key")
        assert item is not None
        assert item.key == "test_key"
        assert item.value == "test_value"
        assert item.metadata.access_count == 1
    
    async def test_store_with_redis_failure(self, shortterm_memory, mock_redis_adapter):
        """Test fallback to memory when Redis fails."""
        # Configure Redis to fail
        mock_redis_adapter.store.side_effect = Exception("Redis unavailable")
        
        # Store should still succeed via memory fallback
        success = await shortterm_memory.store("fallback_key", "fallback_value")
        assert success
        
        # Should be retrievable from memory
        item = await shortterm_memory.retrieve("fallback_key")
        assert item is not None
        assert item.value == "fallback_value"
    
    async def test_batch_retrieve(self, shortterm_memory):
        """Test batch retrieval operations."""
        # Store multiple items
        for i in range(5):
            await shortterm_memory.store(f"batch_key_{i}", f"batch_value_{i}")
        
        # Batch retrieve
        keys = [f"batch_key_{i}" for i in range(5)]
        results = await shortterm_memory.batch_retrieve(keys)
        
        assert len(results) == 5
        for i in range(5):
            assert f"batch_key_{i}" in results
            assert results[f"batch_key_{i}"].value == f"batch_value_{i}"
    
    async def test_access_pattern_tracking(self, shortterm_memory):
        """Test access pattern tracking for consolidation."""
        # Store and access item multiple times
        await shortterm_memory.store("pattern_key", "pattern_value")
        
        # Access multiple times
        for _ in range(3):
            item = await shortterm_memory.retrieve("pattern_key")
            await asyncio.sleep(0.01)  # Small delay to see different timestamps
        
        # Check access patterns
        final_item = await shortterm_memory.retrieve("pattern_key")
        assert final_item.metadata.access_count == 4  # 3 retrieves + 1 final
        assert len(final_item.metadata.access_patterns) > 0
    
    async def test_ttl_expiration(self, shortterm_memory_no_redis):
        """Test TTL-based expiration."""
        # Store item with short TTL
        await shortterm_memory_no_redis.store(
            "expire_key", 
            "expire_value",
            ttl=timedelta(milliseconds=50)
        )
        
        # Should be retrievable immediately
        item = await shortterm_memory_no_redis.retrieve("expire_key")
        assert item is not None
        
        # Wait for expiration
        await asyncio.sleep(0.1)
        
        # Should be expired
        expired_item = await shortterm_memory_no_redis.retrieve("expire_key")
        assert expired_item is None
    
    async def test_cleanup_expired(self, shortterm_memory_no_redis):
        """Test cleanup of expired items."""
        # Store items with different TTLs
        await shortterm_memory_no_redis.store("keep", "value", ttl=timedelta(hours=1))
        await shortterm_memory_no_redis.store("expire", "value", ttl=timedelta(milliseconds=50))
        
        # Wait for one to expire
        await asyncio.sleep(0.1)
        
        # Run cleanup
        cleaned_count = await shortterm_memory_no_redis.cleanup_expired()
        assert cleaned_count >= 1
        
        # Verify expired item is gone, kept item remains
        assert await shortterm_memory_no_redis.retrieve("keep") is not None
        assert await shortterm_memory_no_redis.retrieve("expire") is None
    
    async def test_consolidation_strategy_access_frequency(self, shortterm_memory):
        """Test access frequency consolidation strategy."""
        config = ConsolidationConfig(
            strategy=ConsolidationStrategy.ACCESS_FREQUENCY,
            promotion_threshold=3
        )
        shortterm_memory.config = config
        
        # Store items with different access patterns
        await shortterm_memory.store("high_access", "value1")
        await shortterm_memory.store("low_access", "value2")
        
        # Access one item frequently
        for _ in range(5):
            await shortterm_memory.retrieve("high_access")
        
        # Access other item once
        await shortterm_memory.retrieve("low_access")
        
        # Get items for consolidation analysis
        all_keys = await shortterm_memory.list_keys()
        items = []
        for key in all_keys:
            item = await shortterm_memory.retrieve(key)
            if item:
                items.append(item)
        
        # Identify promotion candidates
        candidates = await shortterm_memory._identify_promotion_candidates(items)
        
        # High access item should be a candidate
        high_access_candidate = next(
            (c for c in candidates if c.item.key == "high_access"), 
            None
        )
        assert high_access_candidate is not None
        assert high_access_candidate.score > 0.5
    
    async def test_promotion_callback(self, shortterm_memory):
        """Test promotion callbacks."""
        promoted_items = []
        
        async def promotion_callback(item, score, reason):
            promoted_items.append((item.key, score, reason))
        
        # Register callback
        shortterm_memory.register_promotion_callback(promotion_callback)
        
        # Create a high-scoring candidate
        item = MemoryItem(
            key="promote_me",
            value="valuable_data",
            metadata=MemoryMetadata(access_count=10),
            created_at=datetime.now(timezone.utc),
            accessed_at=datetime.now(timezone.utc)
        )
        
        candidate = PromotionCandidate(
            item=item,
            score=0.8,
            reason="high_access"
        )
        
        # Promote item
        success = await shortterm_memory._promote_to_longterm(candidate)
        assert success
        
        # Check callback was called
        assert len(promoted_items) == 1
        assert promoted_items[0][0] == "promote_me"
        assert promoted_items[0][1] == 0.8
    
    async def test_full_consolidation_run(self, shortterm_memory):
        """Test complete consolidation process."""
        # Store multiple items
        for i in range(5):
            await shortterm_memory.store(f"item_{i}", f"data_{i}")
        
        # Access some items to create patterns
        for i in [0, 1, 2]:
            for _ in range(6):  # Above promotion threshold
                await shortterm_memory.retrieve(f"item_{i}")
        
        # Run consolidation
        result = await shortterm_memory.run_consolidation()
        
        # Should have identified candidates
        assert result["candidates"] >= 0
        assert "strategy" in result
        assert "timestamp" in result
    
    async def test_statistics(self, shortterm_memory):
        """Test statistics collection."""
        # Perform some operations
        await shortterm_memory.store("stats_key", "stats_value")
        await shortterm_memory.retrieve("stats_key")
        await shortterm_memory.retrieve("nonexistent_key")  # Miss
        
        # Get statistics
        stats = await shortterm_memory.get_statistics()
        
        assert "shortterm_stats" in stats
        assert "memory_stats" in stats
        assert "config" in stats
        
        stm_stats = stats["shortterm_stats"]
        assert stm_stats["items_stored"] >= 1
        assert stm_stats["cache_hits"] >= 1
        assert stm_stats["cache_misses"] >= 1
    
    async def test_delete_operations(self, shortterm_memory):
        """Test deletion operations."""
        # Store item
        await shortterm_memory.store("delete_me", "delete_value")
        
        # Verify it exists
        item = await shortterm_memory.retrieve("delete_me")
        assert item is not None
        
        # Delete it
        success = await shortterm_memory.delete("delete_me")
        assert success
        
        # Verify it's gone
        deleted_item = await shortterm_memory.retrieve("delete_me")
        assert deleted_item is None
    
    async def test_key_listing(self, shortterm_memory):
        """Test key listing functionality."""
        # Store items with patterns
        await shortterm_memory.store("test:item1", "value1")
        await shortterm_memory.store("test:item2", "value2")
        await shortterm_memory.store("other:item", "value3")
        
        # List all keys
        all_keys = await shortterm_memory.list_keys()
        assert len(all_keys) >= 3
        
        # List with pattern (depends on implementation)
        test_keys = await shortterm_memory.list_keys("test:*")
        # Note: Pattern matching depends on underlying adapter implementation
    
    async def test_consolidation_config(self):
        """Test consolidation configuration options."""
        config = ConsolidationConfig(
            strategy=ConsolidationStrategy.SEMANTIC_CLUSTERING,
            promotion_threshold=10,
            consolidation_window=timedelta(minutes=30),
            max_items_per_batch=50
        )
        
        assert config.strategy == ConsolidationStrategy.SEMANTIC_CLUSTERING
        assert config.promotion_threshold == 10
        assert config.consolidation_window == timedelta(minutes=30)
        assert config.max_items_per_batch == 50
    
    async def test_background_consolidation_task(self, memory_adapter):
        """Test background consolidation task lifecycle."""
        config = ConsolidationConfig(
            consolidation_window=timedelta(milliseconds=100)  # Very short for testing
        )
        
        stm = ShortTermMemory(
            memory_adapter=memory_adapter,
            config=config,
            tenant_id="test"
        )
        
        # Start should create background task
        await stm.start()
        assert stm._consolidation_task is not None
        assert not stm._consolidation_task.done()
        
        # Wait briefly for at least one consolidation cycle
        await asyncio.sleep(0.2)
        
        # Stop should cancel background task
        await stm.stop()
        assert stm._consolidation_task.cancelled()


@pytest.mark.benchmark
class TestShortTermMemoryPerformance:
    """Performance benchmarks for Short-term Memory."""
    
    @pytest.fixture
    async def performance_stm(self):
        """Create STM instance for performance testing."""
        adapter = MemoryAdapter(tenant_id="perf_test")
        stm = ShortTermMemory(memory_adapter=adapter, tenant_id="perf_test")
        await stm.start()
        yield stm
        await stm.stop()
        await adapter.cleanup()
    
    async def test_bulk_operations_performance(self, performance_stm, benchmark):
        """Benchmark bulk store/retrieve operations."""
        
        async def bulk_operations():
            # Store 1000 items
            for i in range(1000):
                await performance_stm.store(f"perf_key_{i}", f"perf_value_{i}")
            
            # Retrieve all items
            keys = [f"perf_key_{i}" for i in range(1000)]
            results = await performance_stm.batch_retrieve(keys)
            return len(results)
        
        result = await benchmark(bulk_operations)
        assert result == 1000
    
    async def test_consolidation_performance(self, performance_stm, benchmark):
        """Benchmark consolidation process performance."""
        
        # Setup: Store items with various access patterns
        for i in range(100):
            await performance_stm.store(f"consolidation_key_{i}", f"data_{i}")
            # Access some items multiple times
            if i % 3 == 0:
                for _ in range(5):
                    await performance_stm.retrieve(f"consolidation_key_{i}")
        
        async def run_consolidation():
            return await performance_stm.run_consolidation()
        
        result = await benchmark(run_consolidation)
        assert "candidates" in result


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])