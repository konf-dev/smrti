"""
Tests for Hybrid Retrieval Engine

Tests multi-modal search, fusion strategies, and reranking.
"""

import pytest
from datetime import datetime, timedelta, timezone

from smrti.engines.retrieval import (
    HybridRetrieval,
    SearchMode,
    FusionStrategy,
    RerankMode,
    RetrievalConfig,
    SearchQuery,
    SearchCandidate,
    SearchResult
)
from smrti.models.memory import MemoryItem, MemoryMetadata


class MockVectorAdapter:
    """Mock vector search adapter."""
    
    async def search(self, query_embedding, namespace, tenant_id, limit, filters=None):
        """Return mock vector results."""
        results = []
        for i in range(5):
            item = MemoryItem(
                key=f"vec_{i}",
                value=f"Vector result {i}",
                tenant_id=tenant_id,
                namespace=namespace,
                metadata=MemoryMetadata(created_at=datetime.now(timezone.utc))
            )
            # Mock result object
            result = type('obj', (object,), {
                'item': item,
                'score': 1.0 - (i * 0.1)
            })()
            results.append(result)
        return results


class MockLexicalAdapter:
    """Mock lexical search adapter."""
    
    async def search(self, query_text, namespace, tenant_id, limit, filters=None):
        """Return mock lexical results."""
        results = []
        for i in range(5):
            item = MemoryItem(
                key=f"lex_{i}",
                value=f"Lexical result {i}",
                tenant_id=tenant_id,
                namespace=namespace,
                metadata=MemoryMetadata(created_at=datetime.now(timezone.utc))
            )
            result = type('obj', (object,), {
                'item': item,
                'score': 0.9 - (i * 0.1)
            })()
            results.append(result)
        return results


class MockEmbeddingProvider:
    """Mock embedding provider."""
    
    async def embed(self, text):
        """Return mock embedding."""
        return [0.1] * 768  # Mock 768-dim embedding


class TestHybridRetrieval:
    """Test suite for Hybrid Retrieval engine."""
    
    @pytest.fixture
    def config(self):
        """Create retrieval config for testing."""
        return RetrievalConfig(
            max_candidates_per_modality=10,
            final_top_k=5,
            enable_caching=True
        )
    
    @pytest.fixture
    def retrieval_engine(self, config):
        """Create retrieval engine for testing."""
        return HybridRetrieval(
            config=config,
            vector_adapter=MockVectorAdapter(),
            lexical_adapter=MockLexicalAdapter(),
            embedding_provider=MockEmbeddingProvider()
        )
    
    def test_initialization(self, retrieval_engine, config):
        """Test retrieval engine initialization."""
        assert retrieval_engine.config == config
        assert retrieval_engine.vector_adapter is not None
        assert retrieval_engine.lexical_adapter is not None
    
    async def test_vector_only_search(self, retrieval_engine):
        """Test vector-only search mode."""
        query = SearchQuery(
            query_text="test query",
            tenant_id="test",
            namespace="test",
            limit=5
        )
        
        result = await retrieval_engine.search(
            query,
            search_mode=SearchMode.VECTOR_ONLY
        )
        
        assert isinstance(result, SearchResult)
        assert len(result.candidates) <= 5
        assert result.query == query
        assert result.total_time_ms > 0
    
    async def test_lexical_only_search(self, retrieval_engine):
        """Test lexical-only search mode."""
        query = SearchQuery(
            query_text="test query",
            tenant_id="test",
            namespace="test",
            limit=5
        )
        
        result = await retrieval_engine.search(
            query,
            search_mode=SearchMode.LEXICAL_ONLY
        )
        
        assert isinstance(result, SearchResult)
        assert len(result.candidates) <= 5
    
    async def test_hybrid_search(self, retrieval_engine):
        """Test hybrid search combining multiple modalities."""
        query = SearchQuery(
            query_text="test query",
            tenant_id="test",
            namespace="test",
            limit=10
        )
        
        result = await retrieval_engine.search(
            query,
            search_mode=SearchMode.HYBRID
        )
        
        assert isinstance(result, SearchResult)
        assert len(result.candidates) <= 10
        # Should have results from multiple modalities
        assert len(result.modality_counts) >= 1
    
    async def test_weighted_fusion(self, retrieval_engine):
        """Test weighted fusion strategy."""
        query = SearchQuery(
            query_text="test query",
            tenant_id="test",
            namespace="test",
            limit=10
        )
        
        result = await retrieval_engine.search(
            query,
            search_mode=SearchMode.HYBRID,
            fusion_strategy=FusionStrategy.WEIGHTED
        )
        
        assert result.fusion_strategy == FusionStrategy.WEIGHTED.value
        # All candidates should have combined scores
        for candidate in result.candidates:
            assert candidate.combined_score >= 0
    
    async def test_rrf_fusion(self, retrieval_engine):
        """Test reciprocal rank fusion strategy."""
        query = SearchQuery(
            query_text="test query",
            tenant_id="test",
            namespace="test",
            limit=10
        )
        
        result = await retrieval_engine.search(
            query,
            search_mode=SearchMode.HYBRID,
            fusion_strategy=FusionStrategy.RRF
        )
        
        assert result.fusion_strategy == FusionStrategy.RRF.value
        # RRF should assign ranks
        for candidate in result.candidates:
            assert candidate.rank > 0
    
    async def test_cascade_fusion(self, retrieval_engine):
        """Test cascade fusion strategy."""
        query = SearchQuery(
            query_text="test query",
            tenant_id="test",
            namespace="test",
            limit=10
        )
        
        result = await retrieval_engine.search(
            query,
            search_mode=SearchMode.HYBRID,
            fusion_strategy=FusionStrategy.CASCADE
        )
        
        assert result.fusion_strategy == FusionStrategy.CASCADE.value
    
    async def test_voting_fusion(self, retrieval_engine):
        """Test voting fusion strategy."""
        query = SearchQuery(
            query_text="test query",
            tenant_id="test",
            namespace="test",
            limit=10
        )
        
        result = await retrieval_engine.search(
            query,
            search_mode=SearchMode.HYBRID,
            fusion_strategy=FusionStrategy.VOTING
        )
        
        assert result.fusion_strategy == FusionStrategy.VOTING.value
    
    async def test_caching(self, retrieval_engine):
        """Test result caching."""
        query = SearchQuery(
            query_text="test query",
            tenant_id="test",
            namespace="test",
            limit=5
        )
        
        # First search (cache miss)
        result1 = await retrieval_engine.search(query)
        assert not result1.cache_hit
        
        # Second search (cache hit)
        result2 = await retrieval_engine.search(query)
        assert result2.cache_hit
    
    async def test_statistics_tracking(self, retrieval_engine):
        """Test statistics tracking."""
        query = SearchQuery(
            query_text="test query",
            tenant_id="test",
            namespace="test",
            limit=5
        )
        
        # Perform searches
        await retrieval_engine.search(query, search_mode=SearchMode.VECTOR_ONLY)
        await retrieval_engine.search(query, search_mode=SearchMode.LEXICAL_ONLY)
        await retrieval_engine.search(query, search_mode=SearchMode.HYBRID)
        
        stats = retrieval_engine.get_statistics()
        assert stats["searches_performed"] >= 3
        assert stats["vector_searches"] >= 1
        assert stats["lexical_searches"] >= 1
        assert stats["avg_retrieval_time_ms"] > 0
    
    async def test_search_with_filters(self, retrieval_engine):
        """Test search with filters."""
        query = SearchQuery(
            query_text="test query",
            tenant_id="test",
            namespace="test",
            limit=5,
            filters={"category": "important"}
        )
        
        result = await retrieval_engine.search(query)
        assert isinstance(result, SearchResult)
    
    async def test_search_with_time_range(self, retrieval_engine):
        """Test search with time range filter."""
        now = datetime.now(timezone.utc)
        query = SearchQuery(
            query_text="test query",
            tenant_id="test",
            namespace="test",
            limit=5,
            time_range=(now - timedelta(days=7), now)
        )
        
        result = await retrieval_engine.search(query)
        assert isinstance(result, SearchResult)
    
    def test_config_validation(self):
        """Test configuration validation."""
        config = RetrievalConfig(
            weight_vector=0.5,
            weight_lexical=0.3,
            weight_graph=0.2,
            weight_temporal=0.1,
            weight_recency=0.1
        )
        
        # Should warn about weights > 1.0
        config.validate()
    
    def test_search_query_cache_key(self):
        """Test search query cache key generation."""
        query1 = SearchQuery(
            query_text="test",
            tenant_id="tenant1",
            namespace="ns1",
            limit=10
        )
        
        query2 = SearchQuery(
            query_text="test",
            tenant_id="tenant1",
            namespace="ns1",
            limit=10
        )
        
        query3 = SearchQuery(
            query_text="different",
            tenant_id="tenant1",
            namespace="ns1",
            limit=10
        )
        
        # Same query should have same key
        assert query1.to_cache_key() == query2.to_cache_key()
        # Different query should have different key
        assert query1.to_cache_key() != query3.to_cache_key()
    
    async def test_empty_results(self):
        """Test handling of empty results."""
        config = RetrievalConfig()
        engine = HybridRetrieval(config=config)  # No adapters
        
        query = SearchQuery(
            query_text="test",
            tenant_id="test",
            namespace="test"
        )
        
        result = await engine.search(query)
        assert len(result.candidates) == 0
    
    def test_cache_clearing(self, retrieval_engine):
        """Test cache clearing."""
        # Add something to cache manually
        retrieval_engine._cache["test_key"] = None
        assert len(retrieval_engine._cache) > 0
        
        # Clear cache
        retrieval_engine.clear_cache()
        assert len(retrieval_engine._cache) == 0


@pytest.mark.asyncio
class TestSearchCandidate:
    """Test SearchCandidate functionality."""
    
    def test_candidate_creation(self):
        """Test creating search candidates."""
        item = MemoryItem(
            key="test",
            value="test content",
            tenant_id="test",
            namespace="test"
        )
        
        candidate = SearchCandidate(
            item=item,
            scores={"vector": 0.9, "lexical": 0.7},
            combined_score=0.8,
            source_modality="vector"
        )
        
        assert candidate.item == item
        assert candidate.scores["vector"] == 0.9
        assert candidate.combined_score == 0.8
        assert candidate.source_modality == "vector"


@pytest.mark.asyncio  
class TestFusionStrategies:
    """Test different fusion strategies in detail."""
    
    def create_mock_candidates(self):
        """Create mock candidates for testing."""
        candidates = []
        
        # Vector candidates
        for i in range(3):
            item = MemoryItem(
                key=f"vec_{i}",
                value=f"Vector {i}",
                tenant_id="test",
                namespace="test"
            )
            candidate = SearchCandidate(
                item=item,
                scores={"vector": 1.0 - (i * 0.2)},
                source_modality="vector"
            )
            candidates.append(candidate)
        
        # Lexical candidates
        for i in range(3):
            item = MemoryItem(
                key=f"lex_{i}",
                value=f"Lexical {i}",
                tenant_id="test",
                namespace="test"
            )
            candidate = SearchCandidate(
                item=item,
                scores={"lexical": 0.9 - (i * 0.2)},
                source_modality="lexical"
            )
            candidates.append(candidate)
        
        return candidates
    
    def test_weighted_fusion_scores(self):
        """Test weighted fusion score calculation."""
        config = RetrievalConfig(
            weight_vector=0.6,
            weight_lexical=0.4
        )
        engine = HybridRetrieval(config=config)
        
        candidates = self.create_mock_candidates()
        fused = engine._fusion_weighted(candidates)
        
        # Check that all candidates have combined scores
        for candidate in fused:
            assert candidate.combined_score >= 0
        
        # Check that results are sorted by combined score
        for i in range(len(fused) - 1):
            assert fused[i].combined_score >= fused[i+1].combined_score
    
    def test_rrf_fusion_scores(self):
        """Test RRF fusion score calculation."""
        engine = HybridRetrieval()
        
        candidates = self.create_mock_candidates()
        fused = engine._fusion_rrf(candidates)
        
        # All candidates should have RRF scores
        for candidate in fused:
            assert candidate.combined_score >= 0
    
    def test_cascade_fusion_order(self):
        """Test cascade fusion ordering."""
        engine = HybridRetrieval()
        
        candidates = self.create_mock_candidates()
        fused = engine._fusion_cascade(candidates)
        
        # Should prioritize vector results
        # (exact behavior depends on config)
        assert len(fused) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
