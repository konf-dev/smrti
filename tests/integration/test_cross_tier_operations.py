"""
tests/integration/test_cross_tier_operations.py - Integration tests for cross-tier operations

Tests the integration between different memory tiers and their coordinated behavior.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any

from smrti.schemas.models import (
    MemoryQuery,
    RecordEnvelope,
    TextContent,
    MemoryRecord
)
from smrti.memory.tiers import (
    WorkingMemoryTier,
    ShortTermMemoryTier, 
    LongTermMemoryTier,
    EpisodicMemoryTier,
    SemanticMemoryTier
)
from smrti.orchestration.context_assembly import ContextAssemblyEngine
from smrti.orchestration.unified_retrieval import UnifiedRetrievalEngine
from smrti.orchestration.memory_consolidation import MemoryConsolidationEngine
from tests.mocks.adapters import (
    MockTierStore,
    MockRedisAdapter,
    MockChromaDBAdapter,
    MockPostgreSQLAdapter,
    MockNeo4jAdapter,
    MockElasticsearchAdapter,
    MockEmbeddingProvider
)


class TestCrossTierMemoryOperations:
    """Test cross-tier memory operations and data flow."""
    
    @pytest.fixture
    async def memory_tiers(self):
        """Fixture providing configured memory tiers with mock adapters."""
        # Create mock adapters
        redis_adapter = MockRedisAdapter()
        chroma_adapter = MockChromaDBAdapter()
        postgres_adapter = MockPostgreSQLAdapter()
        neo4j_adapter = MockNeo4jAdapter()
        elasticsearch_adapter = MockElasticsearchAdapter()
        embedding_provider = MockEmbeddingProvider()
        
        # Initialize adapters
        await redis_adapter.initialize()
        await chroma_adapter.initialize()
        await postgres_adapter.initialize()
        await neo4j_adapter.initialize()
        await elasticsearch_adapter.initialize()
        
        # Create memory tiers
        working = WorkingMemoryTier(
            tier_store=redis_adapter,
            embedding_provider=embedding_provider
        )
        
        short_term = ShortTermMemoryTier(
            tier_store=redis_adapter,
            embedding_provider=embedding_provider
        )
        
        long_term = LongTermMemoryTier(
            tier_store=chroma_adapter,
            embedding_provider=embedding_provider
        )
        
        episodic = EpisodicMemoryTier(
            tier_store=postgres_adapter,
            embedding_provider=embedding_provider
        )
        
        semantic = SemanticMemoryTier(
            tier_store=neo4j_adapter,
            embedding_provider=embedding_provider
        )
        
        tiers = {
            "working": working,
            "short_term": short_term,
            "long_term": long_term,
            "episodic": episodic,
            "semantic": semantic
        }
        
        # Initialize all tiers
        for tier in tiers.values():
            await tier.initialize()
        
        yield tiers
        
        # Cleanup
        for tier in tiers.values():
            await tier.cleanup()
        
        await redis_adapter.cleanup()
        await chroma_adapter.cleanup()
        await postgres_adapter.cleanup()
        await neo4j_adapter.cleanup()
        await elasticsearch_adapter.cleanup()
    
    @pytest.mark.asyncio
    async def test_memory_promotion_workflow(self, memory_tiers):
        """Test promotion of memories from working to long-term storage."""
        working = memory_tiers["working"]
        short_term = memory_tiers["short_term"]
        long_term = memory_tiers["long_term"]
        
        # Store record in working memory
        record = RecordEnvelope(
            record_id="promotion_test",
            tenant_id="user1",
            namespace="test",
            content=TextContent(text="Important information to be promoted"),
            metadata={"importance": 0.9, "category": "critical"}
        )
        
        record_id = await working.store_record(record)
        assert record_id == "promotion_test"
        
        # Verify it's in working memory
        query = MemoryQuery(
            query_text="important information",
            tenant_id="user1",
            namespace="test"
        )
        
        working_results = await working.retrieve_records(query)
        assert len(working_results) == 1
        assert working_results[0].record_id == "promotion_test"
        
        # Simulate promotion to short-term
        promoted_record = working_results[0]
        promoted_record.metadata["promoted_from"] = "working"
        promoted_record.metadata["promotion_timestamp"] = datetime.utcnow().isoformat()
        
        await short_term.store_record(promoted_record)
        
        # Verify it's now in short-term memory
        short_term_results = await short_term.retrieve_records(query)
        assert len(short_term_results) == 1
        assert short_term_results[0].metadata["promoted_from"] == "working"
        
        # Further promote to long-term memory
        long_term_record = short_term_results[0]
        long_term_record.metadata["promoted_from"] = "short_term"
        
        await long_term.store_record(long_term_record)
        
        # Verify final promotion
        long_term_results = await long_term.retrieve_records(query)
        assert len(long_term_results) == 1
        assert long_term_results[0].metadata["promoted_from"] == "short_term"
    
    @pytest.mark.asyncio
    async def test_cross_tier_retrieval(self, memory_tiers):
        """Test retrieval across multiple memory tiers."""
        # Store related records in different tiers
        records = [
            (memory_tiers["working"], "Machine learning is powerful", "ml_working"),
            (memory_tiers["short_term"], "Neural networks are ML models", "ml_short"),
            (memory_tiers["long_term"], "Deep learning uses neural networks", "ml_long"),
            (memory_tiers["episodic"], "Learned ML at university in 2020", "ml_episodic"),
            (memory_tiers["semantic"], "AI encompasses machine learning", "ml_semantic")
        ]
        
        for tier, text, record_id in records:
            record = RecordEnvelope(
                record_id=record_id,
                tenant_id="user1",
                namespace="test",
                content=TextContent(text=text),
                metadata={"topic": "machine_learning"}
            )
            await tier.store_record(record)
        
        # Query each tier
        query = MemoryQuery(
            query_text="machine learning",
            tenant_id="user1",
            namespace="test",
            limit=5
        )
        
        all_results = []
        for tier_name, tier in memory_tiers.items():
            results = await tier.retrieve_records(query)
            for result in results:
                result.metadata["source_tier"] = tier_name
                all_results.append(result)
        
        # Should have results from all tiers
        source_tiers = {result.metadata["source_tier"] for result in all_results}
        assert len(source_tiers) == 5  # All memory tiers
        
        # Each tier should contribute at least one result
        for tier_name in memory_tiers.keys():
            tier_results = [r for r in all_results if r.metadata["source_tier"] == tier_name]
            assert len(tier_results) >= 1, f"No results from {tier_name}"
    
    @pytest.mark.asyncio
    async def test_contextual_relationships(self, memory_tiers):
        """Test that related memories are properly linked across tiers."""
        episodic = memory_tiers["episodic"]
        semantic = memory_tiers["semantic"]
        
        # Store episodic memory (specific event)
        episodic_record = RecordEnvelope(
            record_id="meeting_2024_01_15",
            tenant_id="user1",
            namespace="test",
            content=TextContent(text="Team meeting discussed project Alpha on January 15, 2024"),
            metadata={
                "event_type": "meeting",
                "date": "2024-01-15",
                "participants": ["Alice", "Bob", "Charlie"],
                "project": "Alpha"
            }
        )
        await episodic.store_record(episodic_record)
        
        # Store related semantic memory (general concept)
        semantic_record = RecordEnvelope(
            record_id="project_alpha_concept",
            tenant_id="user1",
            namespace="test",
            content=TextContent(text="Project Alpha: Machine learning initiative for customer analytics"),
            metadata={
                "concept_type": "project",
                "domain": "machine_learning",
                "status": "active",
                "related_events": ["meeting_2024_01_15"]
            }
        )
        await semantic.store_record(semantic_record)
        
        # Query for project information
        project_query = MemoryQuery(
            query_text="project Alpha",
            tenant_id="user1",
            namespace="test"
        )
        
        # Should find both episodic and semantic memories
        episodic_results = await episodic.retrieve_records(project_query)
        semantic_results = await semantic.retrieve_records(project_query)
        
        assert len(episodic_results) >= 1
        assert len(semantic_results) >= 1
        
        # Verify relationship linkage
        semantic_result = semantic_results[0]
        assert "meeting_2024_01_15" in semantic_result.metadata.get("related_events", [])
    
    @pytest.mark.asyncio
    async def test_temporal_memory_patterns(self, memory_tiers):
        """Test temporal patterns across memory tiers."""
        working = memory_tiers["working"]
        episodic = memory_tiers["episodic"]
        
        base_time = datetime.utcnow()
        
        # Create a sequence of related memories with timestamps
        memories = [
            ("Started learning Python", base_time - timedelta(days=30)),
            ("Completed first Python script", base_time - timedelta(days=25)),
            ("Built web scraper with Python", base_time - timedelta(days=20)),
            ("Working on Python ML project", base_time - timedelta(hours=2)),
            ("Currently debugging Python code", base_time)
        ]
        
        # Store older memories in episodic tier
        for i, (text, timestamp) in enumerate(memories[:-2]):
            record = RecordEnvelope(
                record_id=f"python_learning_{i}",
                tenant_id="user1", 
                namespace="test",
                content=TextContent(text=text),
                created_at=timestamp,
                metadata={
                    "skill": "python",
                    "learning_stage": i + 1,
                    "timestamp": timestamp.isoformat()
                }
            )
            await episodic.store_record(record)
        
        # Store recent memories in working memory
        for i, (text, timestamp) in enumerate(memories[-2:], start=3):
            record = RecordEnvelope(
                record_id=f"python_recent_{i}",
                tenant_id="user1",
                namespace="test",
                content=TextContent(text=text),
                created_at=timestamp,
                metadata={
                    "skill": "python",
                    "learning_stage": i + 1,
                    "timestamp": timestamp.isoformat()
                }
            )
            await working.store_record(record)
        
        # Query for Python-related memories
        python_query = MemoryQuery(
            query_text="Python",
            tenant_id="user1",
            namespace="test",
            time_range_hours=24 * 35  # Cover all memories
        )
        
        # Get results from both tiers
        episodic_results = await episodic.retrieve_records(python_query)
        working_results = await working.retrieve_records(python_query)
        
        # Verify temporal distribution
        assert len(episodic_results) >= 3  # Older memories
        assert len(working_results) >= 2   # Recent memories
        
        # Verify learning progression metadata
        all_results = episodic_results + working_results
        learning_stages = [r.metadata.get("learning_stage", 0) for r in all_results]
        assert max(learning_stages) == 5  # Full progression captured


class TestIntegratedEngineOperations:
    """Test integrated operations using orchestration engines."""
    
    @pytest.fixture
    async def integrated_system(self):
        """Fixture providing fully integrated memory system."""
        # Create mock adapters
        adapters = {
            "redis": MockRedisAdapter(),
            "chroma": MockChromaDBAdapter(),
            "postgres": MockPostgreSQLAdapter(),
            "neo4j": MockNeo4jAdapter(),
            "elasticsearch": MockElasticsearchAdapter()
        }
        
        embedding_provider = MockEmbeddingProvider()
        
        # Initialize adapters
        for adapter in adapters.values():
            await adapter.initialize()
        
        # Create memory tiers
        memory_tiers = {
            "working": WorkingMemoryTier(
                tier_store=adapters["redis"],
                embedding_provider=embedding_provider
            ),
            "short_term": ShortTermMemoryTier(
                tier_store=adapters["redis"],
                embedding_provider=embedding_provider
            ),
            "long_term": LongTermMemoryTier(
                tier_store=adapters["chroma"],
                embedding_provider=embedding_provider
            ),
            "episodic": EpisodicMemoryTier(
                tier_store=adapters["postgres"],
                embedding_provider=embedding_provider
            ),
            "semantic": SemanticMemoryTier(
                tier_store=adapters["neo4j"],
                embedding_provider=embedding_provider
            )
        }
        
        # Initialize tiers
        for tier in memory_tiers.values():
            await tier.initialize()
        
        # Create orchestration engines
        context_engine = ContextAssemblyEngine()
        for name, tier in memory_tiers.items():
            context_engine.register_tier(name, tier)
        
        retrieval_engine = UnifiedRetrievalEngine()
        for name, adapter in adapters.items():
            retrieval_engine.register_adapter(name, adapter)
        retrieval_engine.embedding_provider = embedding_provider
        
        consolidation_engine = MemoryConsolidationEngine()
        consolidation_engine.embedding_provider = embedding_provider
        
        system = {
            "adapters": adapters,
            "tiers": memory_tiers,
            "engines": {
                "context": context_engine,
                "retrieval": retrieval_engine,
                "consolidation": consolidation_engine
            },
            "embedding_provider": embedding_provider
        }
        
        yield system
        
        # Cleanup
        for tier in memory_tiers.values():
            await tier.cleanup()
        for adapter in adapters.values():
            await adapter.cleanup()
    
    @pytest.mark.asyncio
    async def test_end_to_end_memory_workflow(self, integrated_system):
        """Test complete end-to-end memory workflow."""
        tiers = integrated_system["tiers"]
        engines = integrated_system["engines"]
        
        # 1. Store initial memories across different tiers
        memories = [
            ("working", "Currently working on neural network optimization"),
            ("short_term", "Yesterday learned about gradient descent"),
            ("long_term", "Deep learning fundamentals from last month"),
            ("episodic", "First neural network course taken in 2023"),
            ("semantic", "Neural networks are computational models inspired by brain")
        ]
        
        for tier_name, text in memories:
            record = RecordEnvelope(
                record_id=f"{tier_name}_nn_memory",
                tenant_id="user1",
                namespace="ml_learning",
                content=TextContent(text=text),
                metadata={"topic": "neural_networks", "domain": "machine_learning"}
            )
            await tiers[tier_name].store_record(record)
        
        # 2. Test unified retrieval across all tiers
        query = MemoryQuery(
            query_text="neural networks",
            tenant_id="user1",
            namespace="ml_learning",
            limit=10
        )
        
        retrieval_results = await engines["retrieval"].unified_search(query)
        assert len(retrieval_results) >= 5  # Should find all stored memories
        
        # 3. Test context assembly from retrieval results
        context = await engines["context"].assemble_context(query)
        assert context is not None
        assert len(context.records) > 0
        
        # Context should prioritize by tier importance
        context_text = " ".join(record.content.get_text() for record in context.records[:3])
        assert "currently working" in context_text.lower()  # Working memory prioritized
        
        # 4. Test memory consolidation
        all_records = []
        for tier in tiers.values():
            tier_results = await tier.retrieve_records(query)
            all_records.extend(tier_results)
        
        consolidation_result = await engines["consolidation"].consolidate_records(
            all_records,
            consolidation_strategy="merge_similar"
        )
        
        assert consolidation_result["original_count"] >= 5
        assert consolidation_result["final_count"] <= consolidation_result["original_count"]
        assert len(consolidation_result["consolidated_records"]) > 0
    
    @pytest.mark.asyncio
    async def test_adaptive_tier_selection(self, integrated_system):
        """Test adaptive selection of appropriate memory tiers."""
        tiers = integrated_system["tiers"]
        
        # Test different query types that should target different tiers
        test_scenarios = [
            {
                "query": "what am I working on right now",
                "expected_tier": "working",
                "record_text": "Currently debugging the authentication system",
                "tier_preference": ["working", "short_term"]
            },
            {
                "query": "remember my meeting last week",
                "expected_tier": "episodic",
                "record_text": "Weekly team meeting discussed Q1 planning",
                "tier_preference": ["episodic", "short_term"]
            },
            {
                "query": "what is machine learning",
                "expected_tier": "semantic",
                "record_text": "Machine learning is a subset of AI that learns from data",
                "tier_preference": ["semantic", "long_term"]
            },
            {
                "query": "learned yesterday about",
                "expected_tier": "short_term",
                "record_text": "Yesterday studied reinforcement learning algorithms",
                "tier_preference": ["short_term", "working"]
            }
        ]
        
        for scenario in test_scenarios:
            # Store record in expected tier
            record = RecordEnvelope(
                record_id=f"adaptive_test_{scenario['expected_tier']}",
                tenant_id="user1",
                namespace="test",
                content=TextContent(text=scenario["record_text"]),
                metadata={"test_scenario": True}
            )
            
            await tiers[scenario["expected_tier"]].store_record(record)
            
            # Query and verify retrieval
            query = MemoryQuery(
                query_text=scenario["query"],
                tenant_id="user1",
                namespace="test"
            )
            
            # Test each preferred tier
            found_in_preferred = False
            for preferred_tier in scenario["tier_preference"]:
                results = await tiers[preferred_tier].retrieve_records(query)
                if len(results) > 0:
                    found_in_preferred = True
                    break
            
            assert found_in_preferred, f"Query '{scenario['query']}' not found in preferred tiers"
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, integrated_system):
        """Test concurrent memory operations across tiers."""
        tiers = integrated_system["tiers"]
        
        # Create concurrent store operations
        async def store_memory(tier_name, tier, index):
            record = RecordEnvelope(
                record_id=f"concurrent_test_{tier_name}_{index}",
                tenant_id="user1",
                namespace="concurrent_test",
                content=TextContent(text=f"Concurrent operation {index} in {tier_name}"),
                metadata={"operation_index": index, "tier": tier_name}
            )
            return await tier.store_record(record)
        
        # Launch concurrent operations across all tiers
        tasks = []
        for i in range(3):  # 3 operations per tier
            for tier_name, tier in tiers.items():
                task = store_memory(tier_name, tier, i)
                tasks.append(task)
        
        # Wait for all operations to complete
        results = await asyncio.gather(*tasks)
        assert len(results) == 15  # 5 tiers × 3 operations
        
        # Verify all operations succeeded
        for result in results:
            assert result is not None
        
        # Test concurrent retrieval
        query = MemoryQuery(
            query_text="concurrent operation",
            tenant_id="user1",
            namespace="concurrent_test",
            limit=20
        )
        
        async def retrieve_from_tier(tier):
            return await tier.retrieve_records(query)
        
        # Concurrent retrieval from all tiers
        retrieval_tasks = [retrieve_from_tier(tier) for tier in tiers.values()]
        retrieval_results = await asyncio.gather(*retrieval_tasks)
        
        # Verify retrieval results
        total_retrieved = sum(len(results) for results in retrieval_results)
        assert total_retrieved >= 15  # Should retrieve all stored records
    
    @pytest.mark.asyncio
    async def test_system_resilience(self, integrated_system):
        """Test system resilience under error conditions."""
        tiers = integrated_system["tiers"]
        engines = integrated_system["engines"]
        
        # Test retrieval when some tiers are unavailable
        working_tier = tiers["working"]
        
        # Store a record in working memory
        record = RecordEnvelope(
            record_id="resilience_test",
            tenant_id="user1",
            namespace="test",
            content=TextContent(text="System resilience test record"),
            metadata={"test": "resilience"}
        )
        await working_tier.store_record(record)
        
        # Simulate partial system failure by removing some tiers
        available_tiers = {"working": tiers["working"]}
        
        # Create a limited context engine
        limited_context_engine = ContextAssemblyEngine()
        limited_context_engine.register_tier("working", available_tiers["working"])
        
        # Query should still work with reduced tiers
        query = MemoryQuery(
            query_text="resilience test",
            tenant_id="user1",
            namespace="test"
        )
        
        context = await limited_context_engine.assemble_context(query)
        assert context is not None
        assert len(context.records) >= 1
        
        # Verify the system can continue operating
        assert context.records[0].record_id == "resilience_test"


@pytest.fixture
async def sample_cross_tier_data():
    """Fixture providing sample data for cross-tier testing."""
    base_time = datetime.utcnow()
    
    return {
        "working_memories": [
            {
                "text": "Currently implementing user authentication",
                "metadata": {"priority": "high", "project": "webapp"}
            },
            {
                "text": "Debugging database connection issue",
                "metadata": {"priority": "urgent", "component": "backend"}
            }
        ],
        "episodic_memories": [
            {
                "text": "Team standup meeting on project status",
                "timestamp": base_time - timedelta(hours=2),
                "metadata": {"event_type": "meeting", "participants": 5}
            },
            {
                "text": "Code review session with senior developer",
                "timestamp": base_time - timedelta(days=1),
                "metadata": {"event_type": "review", "outcome": "approved"}
            }
        ],
        "semantic_memories": [
            {
                "text": "Authentication systems secure user access",
                "metadata": {"concept": "security", "domain": "software_engineering"}
            },
            {
                "text": "Databases store and retrieve structured information",
                "metadata": {"concept": "data_storage", "domain": "computer_science"}
            }
        ]
    }


class TestCrossTierIntegrationFixtures:
    """Test cross-tier integration using fixtures."""
    
    def test_sample_data_structure(self, sample_cross_tier_data):
        """Test that sample cross-tier data fixture is properly structured."""
        data = sample_cross_tier_data
        
        assert "working_memories" in data
        assert "episodic_memories" in data
        assert "semantic_memories" in data
        
        assert len(data["working_memories"]) >= 2
        assert len(data["episodic_memories"]) >= 2
        assert len(data["semantic_memories"]) >= 2
        
        # Verify structure of working memories
        for memory in data["working_memories"]:
            assert "text" in memory
            assert "metadata" in memory
        
        # Verify structure of episodic memories
        for memory in data["episodic_memories"]:
            assert "text" in memory
            assert "timestamp" in memory
            assert "metadata" in memory
        
        # Verify structure of semantic memories
        for memory in data["semantic_memories"]:
            assert "text" in memory
            assert "metadata" in memory