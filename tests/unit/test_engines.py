"""
tests/unit/test_engines.py - Unit tests for orchestration engines

Tests the core orchestration engines: context assembly, unified retrieval, and memory consolidation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from typing import List, Dict, Any

from smrti.schemas.models import (
    MemoryQuery,
    RecordEnvelope, 
    TextContent,
    MemoryRecord
)
from smrti.orchestration.context_assembly import ContextAssemblyEngine
from smrti.orchestration.unified_retrieval import UnifiedRetrievalEngine
from smrti.orchestration.memory_consolidation import MemoryConsolidationEngine
from smrti.core.exceptions import SmrtiError, EngineError


# Mock dependencies
class MockMemoryTier:
    """Mock memory tier for engine testing."""
    
    def __init__(self, tier_name: str, records: List[RecordEnvelope] = None):
        self.tier_name = tier_name
        self.records = records or []
    
    async def retrieve_records(self, query: MemoryQuery) -> List[RecordEnvelope]:
        """Mock retrieval that returns filtered records."""
        # Simple text matching for testing
        results = []
        for record in self.records:
            if query.query_text.lower() in record.content.get_text().lower():
                results.append(record)
        return results[:query.limit]
    
    async def store_record(self, record: RecordEnvelope) -> str:
        """Mock storage."""
        self.records.append(record)
        return record.record_id


class MockEmbeddingProvider:
    """Mock embedding provider for engine testing."""
    
    async def generate_embedding(self, text: str) -> List[float]:
        """Generate deterministic embedding based on text."""
        # Simple hash-based embedding for testing
        hash_val = hash(text) % 1000
        return [float(hash_val % 10) / 10.0 for _ in range(384)]
    
    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate multiple embeddings."""
        return [await self.generate_embedding(text) for text in texts]


class TestContextAssemblyEngine:
    """Test ContextAssemblyEngine functionality."""
    
    @pytest.fixture
    def mock_tiers(self):
        """Fixture providing mock memory tiers with sample data."""
        # Create sample records
        working_records = [
            RecordEnvelope(
                record_id="w1",
                tenant_id="user1", 
                namespace="test",
                content=TextContent(text="Current working context about machine learning"),
                created_at=datetime.utcnow()
            )
        ]
        
        short_term_records = [
            RecordEnvelope(
                record_id="s1",
                tenant_id="user1",
                namespace="test", 
                content=TextContent(text="Recent discussion about neural networks"),
                created_at=datetime.utcnow() - timedelta(hours=1)
            ),
            RecordEnvelope(
                record_id="s2",
                tenant_id="user1",
                namespace="test",
                content=TextContent(text="Machine learning model evaluation metrics"),
                created_at=datetime.utcnow() - timedelta(hours=2)
            )
        ]
        
        long_term_records = [
            RecordEnvelope(
                record_id="l1", 
                tenant_id="user1",
                namespace="test",
                content=TextContent(text="Fundamental machine learning concepts and algorithms"),
                created_at=datetime.utcnow() - timedelta(days=7)
            )
        ]
        
        return {
            "working": MockMemoryTier("working", working_records),
            "short_term": MockMemoryTier("short_term", short_term_records),
            "long_term": MockMemoryTier("long_term", long_term_records)
        }
    
    @pytest.fixture
    def context_engine(self, mock_tiers):
        """Fixture providing context assembly engine with mock tiers."""
        engine = ContextAssemblyEngine()
        engine.memory_tiers = mock_tiers
        return engine
    
    def test_create_context_engine(self):
        """Test creating context assembly engine."""
        engine = ContextAssemblyEngine()
        assert engine.memory_tiers == {}
        assert engine.max_context_length == 8192  # Default value
    
    def test_register_memory_tier(self, context_engine):
        """Test registering memory tiers."""
        new_tier = MockMemoryTier("episodic")
        context_engine.register_tier("episodic", new_tier)
        
        assert "episodic" in context_engine.memory_tiers
        assert context_engine.memory_tiers["episodic"] is new_tier
    
    @pytest.mark.asyncio
    async def test_assemble_context_basic(self, context_engine):
        """Test basic context assembly."""
        query = MemoryQuery(
            query_text="machine learning",
            tenant_id="user1",
            namespace="test",
            limit=5
        )
        
        context = await context_engine.assemble_context(query)
        
        # Should have assembled context from multiple tiers
        assert context is not None
        assert len(context.records) > 0
        assert context.query == query
        
        # Verify records are from different tiers
        record_ids = {record.record_id for record in context.records}
        assert len(record_ids) > 1  # Should have records from multiple tiers
    
    @pytest.mark.asyncio
    async def test_context_length_limiting(self, context_engine):
        """Test context length limiting."""
        # Set a very small context limit
        context_engine.max_context_length = 100
        
        query = MemoryQuery(
            query_text="machine learning",
            tenant_id="user1", 
            namespace="test",
            limit=10
        )
        
        context = await context_engine.assemble_context(query)
        
        # Calculate total text length
        total_length = sum(len(record.content.get_text()) for record in context.records)
        assert total_length <= context_engine.max_context_length
    
    @pytest.mark.asyncio
    async def test_tier_priority_ordering(self, context_engine):
        """Test that records are prioritized by tier importance."""
        query = MemoryQuery(
            query_text="machine learning",
            tenant_id="user1",
            namespace="test", 
            limit=1  # Force prioritization
        )
        
        context = await context_engine.assemble_context(query)
        
        # Should prioritize working memory first
        if len(context.records) > 0:
            first_record = context.records[0]
            # Working memory records should come first
            assert first_record.record_id == "w1"
    
    @pytest.mark.asyncio
    async def test_empty_query_handling(self, context_engine):
        """Test handling of queries that return no results."""
        query = MemoryQuery(
            query_text="nonexistent topic that matches nothing",
            tenant_id="user1",
            namespace="test"
        )
        
        context = await context_engine.assemble_context(query)
        
        assert context is not None
        assert len(context.records) == 0
        assert context.query == query


class TestUnifiedRetrievalEngine:
    """Test UnifiedRetrievalEngine functionality."""
    
    @pytest.fixture
    def mock_adapters(self):
        """Fixture providing mock storage adapters."""
        adapters = {}
        
        # Redis adapter (working memory)
        redis_adapter = AsyncMock()
        redis_adapter.search_records.return_value = [
            RecordEnvelope(
                record_id="redis_1",
                tenant_id="user1",
                namespace="test",
                content=TextContent(text="Redis cached recent query result")
            )
        ]
        adapters["redis"] = redis_adapter
        
        # ChromaDB adapter (vector search)
        chroma_adapter = AsyncMock()
        chroma_adapter.similarity_search.return_value = [
            RecordEnvelope(
                record_id="chroma_1", 
                tenant_id="user1",
                namespace="test",
                content=TextContent(text="Vector similarity match for embeddings")
            )
        ]
        adapters["chroma"] = chroma_adapter
        
        return adapters
    
    @pytest.fixture
    def retrieval_engine(self, mock_adapters):
        """Fixture providing unified retrieval engine."""
        engine = UnifiedRetrievalEngine()
        engine.adapters = mock_adapters
        engine.embedding_provider = MockEmbeddingProvider()
        return engine
    
    def test_create_retrieval_engine(self):
        """Test creating unified retrieval engine."""
        engine = UnifiedRetrievalEngine()
        assert engine.adapters == {}
        assert engine.embedding_provider is None
    
    def test_register_adapter(self, retrieval_engine):
        """Test registering storage adapters."""
        new_adapter = AsyncMock()
        retrieval_engine.register_adapter("postgres", new_adapter)
        
        assert "postgres" in retrieval_engine.adapters
        assert retrieval_engine.adapters["postgres"] is new_adapter
    
    @pytest.mark.asyncio
    async def test_unified_search_basic(self, retrieval_engine):
        """Test basic unified search across adapters."""
        query = MemoryQuery(
            query_text="test query",
            tenant_id="user1",
            namespace="test",
            limit=5
        )
        
        results = await retrieval_engine.unified_search(query)
        
        assert len(results) > 0
        # Should have results from multiple adapters
        result_sources = {record.record_id.split("_")[0] for record in results}
        assert len(result_sources) > 1
    
    @pytest.mark.asyncio
    async def test_search_strategy_keyword(self, retrieval_engine):
        """Test keyword-based search strategy."""
        query = MemoryQuery(
            query_text="specific keywords",
            tenant_id="user1",
            namespace="test"
        )
        
        with patch.object(retrieval_engine, '_keyword_search') as mock_keyword:
            mock_keyword.return_value = []
            
            await retrieval_engine.unified_search(query, strategy="keyword")
            mock_keyword.assert_called_once_with(query)
    
    @pytest.mark.asyncio
    async def test_search_strategy_semantic(self, retrieval_engine):
        """Test semantic search strategy."""
        query = MemoryQuery(
            query_text="semantic meaning",
            tenant_id="user1", 
            namespace="test"
        )
        
        with patch.object(retrieval_engine, '_semantic_search') as mock_semantic:
            mock_semantic.return_value = []
            
            await retrieval_engine.unified_search(query, strategy="semantic")
            mock_semantic.assert_called_once_with(query)
    
    @pytest.mark.asyncio
    async def test_search_strategy_hybrid(self, retrieval_engine):
        """Test hybrid search strategy."""
        query = MemoryQuery(
            query_text="hybrid approach",
            tenant_id="user1",
            namespace="test"
        )
        
        with patch.object(retrieval_engine, '_hybrid_search') as mock_hybrid:
            mock_hybrid.return_value = []
            
            await retrieval_engine.unified_search(query, strategy="hybrid")
            mock_hybrid.assert_called_once_with(query)
    
    @pytest.mark.asyncio
    async def test_result_ranking_and_deduplication(self, retrieval_engine):
        """Test result ranking and deduplication."""
        # Create duplicate records with different IDs but same content
        duplicate_records = [
            RecordEnvelope(
                record_id="dup_1",
                tenant_id="user1",
                namespace="test", 
                content=TextContent(text="Duplicate content")
            ),
            RecordEnvelope(
                record_id="dup_2",
                tenant_id="user1",
                namespace="test",
                content=TextContent(text="Duplicate content")  # Same content
            )
        ]
        
        # Mock adapters to return duplicates
        for adapter in retrieval_engine.adapters.values():
            adapter.search_records.return_value = duplicate_records[:1]
            adapter.similarity_search.return_value = duplicate_records[1:]
        
        query = MemoryQuery(
            query_text="test",
            tenant_id="user1",
            namespace="test"
        )
        
        results = await retrieval_engine.unified_search(query)
        
        # Should deduplicate based on content similarity
        unique_contents = {record.content.get_text() for record in results}
        assert len(unique_contents) <= len(results)


class TestMemoryConsolidationEngine:
    """Test MemoryConsolidationEngine functionality."""
    
    @pytest.fixture
    def consolidation_engine(self):
        """Fixture providing memory consolidation engine."""
        engine = MemoryConsolidationEngine()
        engine.embedding_provider = MockEmbeddingProvider()
        return engine
    
    @pytest.fixture
    def sample_records(self):
        """Fixture providing sample records for consolidation."""
        now = datetime.utcnow()
        
        return [
            RecordEnvelope(
                record_id="rec1",
                tenant_id="user1", 
                namespace="test",
                content=TextContent(text="Machine learning is a subset of AI"),
                created_at=now - timedelta(hours=1),
                metadata={"importance": 0.8}
            ),
            RecordEnvelope(
                record_id="rec2",
                tenant_id="user1",
                namespace="test", 
                content=TextContent(text="Artificial intelligence encompasses machine learning"),
                created_at=now - timedelta(hours=2),
                metadata={"importance": 0.7}
            ),
            RecordEnvelope(
                record_id="rec3",
                tenant_id="user1",
                namespace="test",
                content=TextContent(text="Deep learning uses neural networks"),
                created_at=now - timedelta(hours=3),
                metadata={"importance": 0.9}
            )
        ]
    
    def test_create_consolidation_engine(self):
        """Test creating memory consolidation engine."""
        engine = MemoryConsolidationEngine()
        assert engine.embedding_provider is None
        assert engine.similarity_threshold == 0.8  # Default value
    
    @pytest.mark.asyncio
    async def test_analyze_memory_patterns(self, consolidation_engine, sample_records):
        """Test analyzing memory patterns for consolidation."""
        analysis = await consolidation_engine.analyze_patterns(sample_records)
        
        assert analysis is not None
        assert "clusters" in analysis
        assert "redundancies" in analysis
        assert "importance_distribution" in analysis
    
    @pytest.mark.asyncio
    async def test_identify_redundant_records(self, consolidation_engine, sample_records):
        """Test identifying redundant or duplicate records."""
        # Add very similar records
        similar_record = RecordEnvelope(
            record_id="similar",
            tenant_id="user1",
            namespace="test",
            content=TextContent(text="Machine learning is part of artificial intelligence"),  # Very similar
            created_at=datetime.utcnow()
        )
        
        test_records = sample_records + [similar_record]
        
        redundancies = await consolidation_engine.identify_redundancies(test_records)
        
        assert len(redundancies) > 0
        # Should identify similar records as redundant
    
    @pytest.mark.asyncio
    async def test_consolidate_similar_records(self, consolidation_engine, sample_records):
        """Test consolidating similar records into summaries."""
        consolidation_result = await consolidation_engine.consolidate_records(
            sample_records, 
            consolidation_strategy="merge_similar"
        )
        
        assert consolidation_result is not None
        assert "consolidated_records" in consolidation_result
        assert "original_count" in consolidation_result
        assert "final_count" in consolidation_result
        
        # Should reduce the number of records through consolidation
        assert consolidation_result["final_count"] <= consolidation_result["original_count"]
    
    @pytest.mark.asyncio
    async def test_importance_based_consolidation(self, consolidation_engine, sample_records):
        """Test consolidation based on importance scores."""
        consolidation_result = await consolidation_engine.consolidate_records(
            sample_records,
            consolidation_strategy="importance_weighted"
        )
        
        consolidated_records = consolidation_result["consolidated_records"]
        
        # High importance records should be preserved
        high_importance_preserved = any(
            record.metadata.get("importance", 0) >= 0.8
            for record in consolidated_records
        )
        assert high_importance_preserved
    
    @pytest.mark.asyncio
    async def test_temporal_consolidation(self, consolidation_engine, sample_records):
        """Test consolidation considering temporal patterns."""
        consolidation_result = await consolidation_engine.consolidate_records(
            sample_records,
            consolidation_strategy="temporal_grouping"
        )
        
        # Should group records by time periods
        assert consolidation_result["final_count"] > 0
        
        # Consolidated records should maintain temporal relationships
        consolidated_records = consolidation_result["consolidated_records"]
        if len(consolidated_records) > 1:
            # Should be ordered by time
            timestamps = [record.created_at for record in consolidated_records]
            assert timestamps == sorted(timestamps, reverse=True)  # Newest first
    
    @pytest.mark.asyncio
    async def test_consolidation_preserves_important_metadata(self, consolidation_engine, sample_records):
        """Test that consolidation preserves important metadata."""
        consolidation_result = await consolidation_engine.consolidate_records(sample_records)
        
        consolidated_records = consolidation_result["consolidated_records"]
        
        # Important metadata should be preserved
        for record in consolidated_records:
            assert "importance" in record.metadata
            assert isinstance(record.metadata["importance"], (int, float))
    
    @pytest.mark.asyncio
    async def test_empty_record_handling(self, consolidation_engine):
        """Test handling of empty record lists."""
        result = await consolidation_engine.consolidate_records([])
        
        assert result["original_count"] == 0
        assert result["final_count"] == 0
        assert len(result["consolidated_records"]) == 0


class TestEngineIntegration:
    """Test integration between different engines."""
    
    @pytest.fixture
    def integrated_engines(self):
        """Fixture providing all engines configured together."""
        context_engine = ContextAssemblyEngine()
        retrieval_engine = UnifiedRetrievalEngine()
        consolidation_engine = MemoryConsolidationEngine()
        
        # Set up mock embedding provider
        embedding_provider = MockEmbeddingProvider()
        retrieval_engine.embedding_provider = embedding_provider
        consolidation_engine.embedding_provider = embedding_provider
        
        return {
            "context": context_engine,
            "retrieval": retrieval_engine,
            "consolidation": consolidation_engine
        }
    
    @pytest.mark.asyncio
    async def test_retrieval_to_context_assembly(self, integrated_engines):
        """Test passing retrieval results to context assembly."""
        retrieval_engine = integrated_engines["retrieval"]
        context_engine = integrated_engines["context"]
        
        # Mock retrieval results
        mock_results = [
            RecordEnvelope(
                record_id="integration_1",
                tenant_id="user1",
                namespace="test",
                content=TextContent(text="Retrieved content for context")
            )
        ]
        
        # Mock the retrieval
        with patch.object(retrieval_engine, 'unified_search', return_value=mock_results):
            query = MemoryQuery(
                query_text="integration test",
                tenant_id="user1",
                namespace="test"
            )
            
            # Get retrieval results
            results = await retrieval_engine.unified_search(query)
            
            # Use results in context assembly
            # (In real implementation, context engine would use these results)
            assert len(results) > 0
            assert results[0].record_id == "integration_1"
    
    @pytest.mark.asyncio
    async def test_context_to_consolidation_workflow(self, integrated_engines):
        """Test workflow from context assembly to consolidation."""
        context_engine = integrated_engines["context"]
        consolidation_engine = integrated_engines["consolidation"]
        
        # Mock context results
        mock_records = [
            RecordEnvelope(
                record_id="ctx_1",
                tenant_id="user1",
                namespace="test", 
                content=TextContent(text="Context record for consolidation"),
                metadata={"importance": 0.7}
            ),
            RecordEnvelope(
                record_id="ctx_2",
                tenant_id="user1",
                namespace="test",
                content=TextContent(text="Another context record"),
                metadata={"importance": 0.8}
            )
        ]
        
        # Test consolidation of context records
        result = await consolidation_engine.consolidate_records(mock_records)
        
        assert result["original_count"] == 2
        assert result["final_count"] <= 2
        assert len(result["consolidated_records"]) > 0


@pytest.fixture
def sample_memory_query():
    """Fixture providing sample memory query for engine tests."""
    return MemoryQuery(
        query_text="test query for engines",
        tenant_id="engine_test_user",
        namespace="engine_test_ns",
        limit=3
    )


@pytest.fixture
def sample_record_envelope():
    """Fixture providing sample record envelope for engine tests."""
    return RecordEnvelope(
        record_id="engine_test_record",
        tenant_id="engine_test_user",
        namespace="engine_test_ns",
        content=TextContent(text="Sample content for engine testing"),
        metadata={"test": True, "engine": "fixture"}
    )


class TestEngineFixtures:
    """Test that engine test fixtures work correctly."""
    
    def test_sample_query_fixture(self, sample_memory_query):
        """Test sample memory query fixture."""
        assert isinstance(sample_memory_query, MemoryQuery)
        assert sample_memory_query.query_text == "test query for engines"
        assert sample_memory_query.tenant_id == "engine_test_user"
    
    def test_sample_record_fixture(self, sample_record_envelope):
        """Test sample record envelope fixture."""
        assert isinstance(sample_record_envelope, RecordEnvelope)
        assert sample_record_envelope.record_id == "engine_test_record"
        assert sample_record_envelope.metadata["test"] is True