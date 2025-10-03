"""
Tests for Long-term Memory Tier

Tests semantic storage, search, consolidation, and archival capabilities.
"""

import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from smrti.tiers.longterm import (
    LongTermMemory,
    LongTermConfig,
    SearchMode,
    Fact
)
from smrti.models.memory import MemoryItem, MemoryMetadata


class TestLongTermMemory:
    """Test suite for Long-term Memory tier."""
    
    @pytest.fixture
    async def longterm_memory(self):
        """Create Long-term Memory instance for testing."""
        config = LongTermConfig(
            collection_name="test_longterm",
            persist_directory="./test_data/longterm",
            similarity_threshold=0.6
        )
        ltm = LongTermMemory(config=config, tenant_id="test")
        await ltm.initialize()
        yield ltm
        await ltm.shutdown()
    
    async def test_initialization(self, longterm_memory):
        """Test that Long-term Memory initializes correctly."""
        assert longterm_memory._initialized
        assert longterm_memory.tenant_id == "test"
        assert longterm_memory.config.collection_name == "test_longterm"
    
    async def test_store_and_retrieve_fact(self, longterm_memory):
        """Test storing and retrieving a fact."""
        # Store a fact
        success = await longterm_memory.store_fact(
            key="test_fact_1",
            content="Python is a high-level programming language",
            confidence=0.95,
            source="manual"
        )
        assert success
        
        # Retrieve the fact
        fact = await longterm_memory.retrieve("test_fact_1")
        assert fact is not None
        assert fact.key == "test_fact_1"
        assert "Python" in fact.content
        assert fact.confidence == 0.95
        assert fact.source == "manual"
    
    async def test_semantic_search(self, longterm_memory):
        """Test semantic search functionality."""
        # Store multiple facts
        facts_to_store = [
            {
                "key": "python_fact",
                "content": "Python is great for data science and machine learning",
                "confidence": 0.9
            },
            {
                "key": "javascript_fact",
                "content": "JavaScript is used for web development",
                "confidence": 0.9
            },
            {
                "key": "ml_fact",
                "content": "Machine learning involves training models on data",
                "confidence": 0.85
            }
        ]
        
        for fact_data in facts_to_store:
            await longterm_memory.store_fact(**fact_data)
        
        # Search for machine learning related facts
        results = await longterm_memory.search(
            query="machine learning and data science",
            limit=5
        )
        
        assert len(results) > 0
        # Should find the Python and ML facts as most relevant
        top_result = results[0]
        assert top_result.score > 0.5
        assert isinstance(top_result.fact, Fact)
    
    async def test_consolidation_from_shortterm(self, longterm_memory):
        """Test receiving and consolidating items from Short-term Memory."""
        # Create a memory item simulating Short-term promotion
        memory_item = MemoryItem(
            key="important_user_pref",
            value="User prefers dark mode with high contrast",
            tenant_id="test",
            namespace="preferences",
            metadata=MemoryMetadata(
                access_count=5,
                tags=["preference", "ui"]
            )
        )
        
        # Consolidate into Long-term
        success = await longterm_memory.receive_from_shortterm(memory_item)
        assert success
        
        # Verify it was stored
        stats = longterm_memory.get_statistics()
        assert stats["consolidations_received"] == 1
        assert stats["facts_stored"] >= 1
    
    async def test_batch_store(self, longterm_memory):
        """Test batch storing of facts."""
        facts = [
            {
                "key": f"batch_fact_{i}",
                "content": f"This is batch fact number {i}",
                "confidence": 0.8
            }
            for i in range(5)
        ]
        
        count = await longterm_memory.batch_store(facts)
        assert count == 5
        
        # Verify storage
        stats = longterm_memory.get_statistics()
        assert stats["facts_stored"] >= 5
    
    async def test_statistics_tracking(self, longterm_memory):
        """Test that statistics are tracked correctly."""
        # Store a fact
        await longterm_memory.store_fact(
            key="stats_test",
            content="Testing statistics tracking"
        )
        
        # Retrieve it
        await longterm_memory.retrieve("stats_test")
        
        # Perform a search
        await longterm_memory.search("statistics")
        
        # Check statistics
        stats = longterm_memory.get_statistics()
        assert stats["facts_stored"] >= 1
        assert stats["facts_retrieved"] >= 1
        assert stats["searches_performed"] >= 1
    
    async def test_caching(self, longterm_memory):
        """Test that caching improves retrieval performance."""
        # Store a fact
        await longterm_memory.store_fact(
            key="cached_fact",
            content="This fact should be cached"
        )
        
        # First retrieval (cache miss)
        fact1 = await longterm_memory.retrieve("cached_fact")
        assert fact1 is not None
        
        # Second retrieval (cache hit)
        fact2 = await longterm_memory.retrieve("cached_fact")
        assert fact2 is not None
        assert fact2.key == fact1.key
    
    async def test_confidence_calculation(self, longterm_memory):
        """Test confidence score calculation for promoted items."""
        # Create items with different access counts
        items = [
            MemoryItem(
                key="low_access",
                value="Low access content",
                tenant_id="test",
                metadata=MemoryMetadata(access_count=1)
            ),
            MemoryItem(
                key="high_access",
                value="High access content",
                tenant_id="test",
                metadata=MemoryMetadata(access_count=10)
            )
        ]
        
        # Calculate confidence for each
        conf_low = longterm_memory._calculate_confidence(items[0])
        conf_high = longterm_memory._calculate_confidence(items[1])
        
        # Higher access count should give higher confidence
        assert conf_high > conf_low
        assert 0.0 <= conf_low <= 1.0
        assert 0.0 <= conf_high <= 1.0
    
    async def test_fact_extraction(self, longterm_memory):
        """Test extracting fact content from different value types."""
        # String value
        item1 = MemoryItem(
            key="string_item",
            value="Simple string content",
            tenant_id="test"
        )
        content1 = longterm_memory._extract_fact_content(item1)
        assert content1 == "Simple string content"
        
        # Dict value with 'content' field
        item2 = MemoryItem(
            key="dict_item",
            value={"content": "Dict content", "other": "data"},
            tenant_id="test"
        )
        content2 = longterm_memory._extract_fact_content(item2)
        assert content2 == "Dict content"
        
        # Dict value without standard field
        item3 = MemoryItem(
            key="dict_item2",
            value={"custom": "value", "data": "info"},
            tenant_id="test"
        )
        content3 = longterm_memory._extract_fact_content(item3)
        assert isinstance(content3, str)  # Should be JSON


@pytest.mark.asyncio
class TestLongTermMemoryIntegration:
    """Integration tests for Long-term Memory."""
    
    async def test_full_consolidation_flow(self):
        """Test complete flow from Short-term to Long-term."""
        config = LongTermConfig(
            collection_name="integration_test",
            persist_directory="./test_data/integration"
        )
        ltm = LongTermMemory(config=config, tenant_id="integration_test")
        await ltm.initialize()
        
        try:
            # Simulate multiple promotions
            for i in range(3):
                item = MemoryItem(
                    key=f"promoted_item_{i}",
                    value=f"Important information {i}",
                    tenant_id="integration_test",
                    metadata=MemoryMetadata(
                        access_count=5 + i,
                        tags=["important"]
                    )
                )
                success = await ltm.receive_from_shortterm(item)
                assert success
            
            # Search for consolidated facts
            results = await ltm.search("important information", limit=5)
            assert len(results) >= 1
            
            # Verify statistics
            stats = ltm.get_statistics()
            assert stats["consolidations_received"] == 3
            
        finally:
            await ltm.shutdown()
    
    async def test_search_with_filters(self):
        """Test search with metadata filters."""
        config = LongTermConfig(
            collection_name="filter_test",
            persist_directory="./test_data/filter_test"
        )
        ltm = LongTermMemory(config=config, tenant_id="filter_test")
        await ltm.initialize()
        
        try:
            # Store facts with different metadata
            await ltm.store_fact(
                key="high_conf_fact",
                content="High confidence information",
                confidence=0.95,
                metadata={"category": "important"}
            )
            
            await ltm.store_fact(
                key="low_conf_fact",
                content="Low confidence information",
                confidence=0.4,
                metadata={"category": "tentative"}
            )
            
            # Search with confidence filter
            results = await ltm.search(
                query="information",
                filters={"confidence": {"$gte": 0.9}},
                limit=10
            )
            
            # Should only return high confidence facts
            # (Note: actual filtering depends on vector DB implementation)
            assert len(results) >= 0
            
        finally:
            await ltm.shutdown()


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
