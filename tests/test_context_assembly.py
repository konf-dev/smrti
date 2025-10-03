"""
Tests for Context Assembly Engine

Tests token budgeting, section allocation, and reduction strategies.
"""

import pytest
from datetime import datetime, timezone

from smrti.engines.context import (
    ContextAssembly,
    AssemblyConfig,
    AssemblyStrategy,
    SectionPriority,
    ReductionStrategy,
    AssembledContext,
    ContextSection,
    ProvenanceRecord
)
from smrti.models.memory import MemoryItem, MemoryMetadata


class TestContextAssembly:
    """Test suite for Context Assembly engine."""
    
    @pytest.fixture
    def config(self):
        """Create assembly config for testing."""
        return AssemblyConfig(
            default_token_budget=1000,
            allocation_working=0.10,
            allocation_semantic=0.30,
            allocation_episodic=0.30,
            allocation_summaries=0.20,
            allocation_patterns=0.10
        )
    
    @pytest.fixture
    def assembly_engine(self, config):
        """Create assembly engine for testing."""
        return ContextAssembly(config=config)
    
    def test_initialization(self, assembly_engine, config):
        """Test assembly engine initialization."""
        assert assembly_engine.config == config
        assert assembly_engine._stats["contexts_assembled"] == 0
    
    async def test_basic_assembly(self, assembly_engine):
        """Test basic context assembly."""
        context = await assembly_engine.assemble(
            user_id="test_user",
            query="test query",
            token_budget=1000
        )
        
        assert isinstance(context, AssembledContext)
        assert context.user_id == "test_user"
        assert context.query == "test query"
        assert context.token_budget == 1000
        assert len(context.sections) > 0
    
    async def test_section_creation(self, assembly_engine):
        """Test section creation and allocation."""
        context = await assembly_engine.assemble(
            user_id="test",
            query="test",
            token_budget=1000
        )
        
        # Should have all standard sections
        section_names = [s.name for s in context.sections]
        assert "working" in section_names
        assert "semantic_facts" in section_names
        assert "episodic_recent" in section_names
        assert "summaries" in section_names
        assert "patterns" in section_names
    
    async def test_token_allocation(self, assembly_engine):
        """Test token allocation to sections."""
        budget = 1000
        context = await assembly_engine.assemble(
            user_id="test",
            query="test",
            token_budget=budget
        )
        
        # Check allocations sum to roughly the budget
        total_allocated = sum(s.allocated_tokens for s in context.sections)
        assert 0.9 * budget <= total_allocated <= 1.1 * budget
    
    def test_section_priority(self):
        """Test section priority levels."""
        section_high = ContextSection(
            name="test",
            priority=SectionPriority.HIGH,
            allocated_tokens=100
        )
        
        section_low = ContextSection(
            name="test2",
            priority=SectionPriority.LOW,
            allocated_tokens=100
        )
        
        assert section_high.priority == SectionPriority.HIGH
        assert section_low.priority == SectionPriority.LOW
    
    def test_section_budget_checking(self):
        """Test section budget checking."""
        section = ContextSection(
            name="test",
            priority=SectionPriority.MEDIUM,
            allocated_tokens=100
        )
        
        section.current_tokens = 50
        assert not section.is_over_budget()
        
        section.current_tokens = 150
        assert section.is_over_budget()
    
    async def test_assembly_strategies(self, assembly_engine):
        """Test different assembly strategies."""
        strategies = [
            AssemblyStrategy.PRIORITY_WEIGHTED,
            AssemblyStrategy.RECENCY_BIASED,
            AssemblyStrategy.RELEVANCE_OPTIMIZED,
            AssemblyStrategy.BALANCED
        ]
        
        for strategy in strategies:
            context = await assembly_engine.assemble(
                user_id="test",
                query="test",
                token_budget=1000,
                strategy=strategy
            )
            
            assert context.assembly_strategy == strategy.value
    
    async def test_budget_constraints(self, assembly_engine):
        """Test that assembly respects budget constraints."""
        budget = 500
        context = await assembly_engine.assemble(
            user_id="test",
            query="test",
            token_budget=budget
        )
        
        # Estimated tokens should be close to or under budget
        assert context.estimated_tokens <= budget * 1.1  # 10% tolerance
    
    async def test_min_max_budget(self, assembly_engine):
        """Test min/max budget enforcement."""
        # Test min budget
        context_min = await assembly_engine.assemble(
            user_id="test",
            query="test",
            token_budget=100  # Below min
        )
        assert context_min.token_budget >= assembly_engine.config.min_token_budget
        
        # Test max budget
        context_max = await assembly_engine.assemble(
            user_id="test",
            query="test",
            token_budget=100000  # Above max
        )
        assert context_max.token_budget <= assembly_engine.config.max_token_budget
    
    async def test_caching(self, assembly_engine):
        """Test context caching."""
        # First assembly
        context1 = await assembly_engine.assemble(
            user_id="test",
            query="test query",
            token_budget=1000
        )
        
        # Second assembly (should be cached)
        context2 = await assembly_engine.assemble(
            user_id="test",
            query="test query",
            token_budget=1000
        )
        
        # Should get cache hit
        stats = assembly_engine.get_statistics()
        assert stats["cache_hits"] >= 1
    
    async def test_statistics_tracking(self, assembly_engine):
        """Test statistics tracking."""
        await assembly_engine.assemble(
            user_id="test",
            query="test1",
            token_budget=1000
        )
        
        await assembly_engine.assemble(
            user_id="test",
            query="test2",
            token_budget=1000
        )
        
        stats = assembly_engine.get_statistics()
        assert stats["contexts_assembled"] >= 2
        assert stats["avg_assembly_time_ms"] > 0
    
    def test_provenance_record(self):
        """Test provenance record creation."""
        provenance = ProvenanceRecord(
            record_id="test_123",
            tier="long_term",
            source_type="FACT",
            original_tokens=100,
            current_tokens=100,
            relevance_score=0.9,
            selection_reason="top_k"
        )
        
        assert provenance.record_id == "test_123"
        assert provenance.tier == "long_term"
        assert provenance.reduction_ratio() == 1.0
    
    def test_provenance_transformations(self):
        """Test provenance transformation tracking."""
        provenance = ProvenanceRecord(
            record_id="test",
            tier="episodic",
            source_type="EVENT",
            original_tokens=200,
            current_tokens=200,
            relevance_score=0.8,
            selection_reason="high_importance"
        )
        
        # Add transformation
        provenance.add_transformation(
            "summarize",
            model="gpt-4",
            reduction_ratio=0.5
        )
        provenance.current_tokens = 100
        
        assert len(provenance.transformations) == 1
        assert provenance.transformations[0]["type"] == "summarize"
        assert provenance.reduction_ratio() == 0.5
    
    async def test_section_override(self, assembly_engine):
        """Test section configuration override."""
        sections_config = {
            "semantic_facts": {
                "allocated_tokens": 500,
                "priority": "required"
            }
        }
        
        context = await assembly_engine.assemble(
            user_id="test",
            query="test",
            token_budget=1000,
            sections_config=sections_config
        )
        
        semantic_section = context.get_section("semantic_facts")
        assert semantic_section is not None
        assert semantic_section.allocated_tokens == 500
    
    def test_context_to_dict(self):
        """Test context serialization."""
        context = AssembledContext(
            user_id="test",
            query="test query",
            token_budget=1000,
            estimated_tokens=800,
            assembly_strategy="balanced",
            reductions_applied=2
        )
        
        data = context.to_dict()
        assert data["user_id"] == "test"
        assert data["query"] == "test query"
        assert data["token_budget"] == 1000
        assert data["estimated_tokens"] == 800
        assert data["reductions_applied"] == 2
    
    def test_config_validation(self):
        """Test configuration validation."""
        config = AssemblyConfig(
            allocation_working=0.2,
            allocation_semantic=0.3,
            allocation_episodic=0.3,
            allocation_summaries=0.2,
            allocation_patterns=0.1,
            allocation_slack=0.0
        )
        
        # Should validate without error (sums to 1.1, within tolerance)
        config.validate()
    
    async def test_token_estimation(self, assembly_engine):
        """Test token estimation for items."""
        item = MemoryItem(
            key="test",
            value="This is a test value with some content",
            tenant_id="test",
            namespace="test"
        )
        
        tokens = assembly_engine._estimate_item_tokens(item)
        assert tokens > 0
    
    def test_cache_key_generation(self, assembly_engine):
        """Test cache key generation."""
        key1 = assembly_engine._generate_cache_key("user1", "query1", 1000)
        key2 = assembly_engine._generate_cache_key("user1", "query1", 1000)
        key3 = assembly_engine._generate_cache_key("user2", "query1", 1000)
        
        # Same inputs should produce same key
        assert key1 == key2
        # Different inputs should produce different keys
        assert key1 != key3
    
    def test_cache_clearing(self, assembly_engine):
        """Test cache clearing."""
        # Add to cache manually
        assembly_engine._cache["test"] = None
        assert len(assembly_engine._cache) > 0
        
        # Clear cache
        assembly_engine.clear_cache()
        assert len(assembly_engine._cache) == 0


@pytest.mark.asyncio
class TestReductionStrategies:
    """Test reduction strategy logic."""
    
    @pytest.fixture
    def assembly_engine(self):
        """Create assembly engine for testing."""
        config = AssemblyConfig(
            default_token_budget=1000,
            max_reduction_cycles=3
        )
        return ContextAssembly(config=config)
    
    async def test_generic_reduction(self, assembly_engine):
        """Test generic section reduction."""
        section = ContextSection(
            name="test",
            priority=SectionPriority.MEDIUM,
            allocated_tokens=100
        )
        
        # Add items
        for i in range(5):
            item = MemoryItem(
                key=f"item_{i}",
                value=f"Content {i}",
                tenant_id="test",
                namespace="test"
            )
            section.items.append(item)
        
        initial_count = len(section.items)
        
        # Apply generic reduction
        reduced = assembly_engine._reduce_generic(section)
        
        assert reduced
        assert len(section.items) == initial_count - 1
    
    async def test_semantic_reduction(self, assembly_engine):
        """Test semantic facts reduction."""
        section = ContextSection(
            name="semantic_facts",
            priority=SectionPriority.HIGH,
            allocated_tokens=100
        )
        
        # Add items with relevance scores
        for i in range(3):
            item = MemoryItem(
                key=f"fact_{i}",
                value=f"Fact {i}",
                tenant_id="test",
                namespace="test"
            )
            section.items.append(item)
            section.relevance_scores.append(0.9 - (i * 0.1))
        
        initial_count = len(section.items)
        
        # Apply semantic reduction
        reduced = await assembly_engine._reduce_semantic(section)
        
        assert reduced
        assert len(section.items) == initial_count - 1
    
    async def test_patterns_reduction(self, assembly_engine):
        """Test patterns section reduction."""
        section = ContextSection(
            name="patterns",
            priority=SectionPriority.LOW,
            allocated_tokens=50
        )
        
        # Add items
        for i in range(3):
            item = MemoryItem(
                key=f"pattern_{i}",
                value=f"Pattern {i}",
                tenant_id="test",
                namespace="test"
            )
            section.items.append(item)
        
        # Apply patterns reduction (should remove all)
        reduced = await assembly_engine._reduce_patterns(section)
        
        assert reduced
        assert len(section.items) == 0


@pytest.mark.asyncio
class TestAssembledContext:
    """Test AssembledContext functionality."""
    
    def test_get_section(self):
        """Test getting section by name."""
        context = AssembledContext(
            user_id="test",
            query="test",
            token_budget=1000
        )
        
        section = ContextSection(
            name="test_section",
            priority=SectionPriority.HIGH,
            allocated_tokens=100
        )
        context.sections.append(section)
        
        retrieved = context.get_section("test_section")
        assert retrieved is not None
        assert retrieved.name == "test_section"
        
        missing = context.get_section("nonexistent")
        assert missing is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
