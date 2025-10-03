"""
tests/integration/test_end_to_end_scenarios.py - End-to-end integration tests

Tests complete workflows using the full Smrti system from the main API.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any

from smrti.api import Smrti, SmrtiConfig, SmrtiSession
from smrti.schemas.models import MemoryQuery, TextContent
from tests.mocks.adapters import (
    MockRedisAdapter,
    MockChromaDBAdapter,
    MockPostgreSQLAdapter,
    MockNeo4jAdapter,
    MockElasticsearchAdapter,
    MockEmbeddingProvider
)


class TestFullSystemWorkflows:
    """Test complete system workflows using the main API."""
    
    @pytest.fixture
    async def smrti_system(self):
        """Fixture providing fully configured Smrti system with mock adapters."""
        # Create mock adapters
        adapters = {
            "redis": MockRedisAdapter(),
            "chroma": MockChromaDBAdapter(), 
            "postgres": MockPostgreSQLAdapter(),
            "neo4j": MockNeo4jAdapter(),
            "elasticsearch": MockElasticsearchAdapter()
        }
        
        embedding_provider = MockEmbeddingProvider()
        
        # Initialize all adapters
        for adapter in adapters.values():
            await adapter.initialize()
        
        # Create system configuration
        config = SmrtiConfig(
            # Adapter configurations would go here in real implementation
            # For testing, we'll inject mocks directly
        )
        
        # Create Smrti system
        smrti = Smrti(config)
        
        # Inject mock components (in real implementation these would be configured)
        smrti._adapters = adapters
        smrti._embedding_provider = embedding_provider
        
        # Initialize the system
        await smrti.initialize()
        
        yield smrti
        
        # Cleanup
        await smrti.cleanup()
    
    @pytest.mark.asyncio
    async def test_basic_memory_lifecycle(self, smrti_system):
        """Test basic memory storage and retrieval lifecycle."""
        smrti = smrti_system
        
        # 1. Store memories of different types
        memories = [
            ("I need to finish the project report by Friday", "task"),
            ("Had a great meeting with the client yesterday", "event"),  
            ("Machine learning models require training data", "knowledge"),
            ("Python is a programming language", "fact"),
            ("Remember to call mom this weekend", "reminder")
        ]
        
        stored_ids = []
        for text, memory_type in memories:
            record_id = await smrti.store_memory(
                text=text,
                tenant_id="test_user",
                namespace="personal",
                metadata={"type": memory_type, "test": True}
            )
            stored_ids.append(record_id)
        
        assert len(stored_ids) == 5
        assert all(record_id is not None for record_id in stored_ids)
        
        # 2. Test retrieval with different queries
        queries = [
            "project report",
            "client meeting", 
            "machine learning",
            "programming language",
            "call mom"
        ]
        
        for query_text in queries:
            results = await smrti.retrieve_memories(
                query_text=query_text,
                tenant_id="test_user",
                namespace="personal"
            )
            assert len(results) >= 1, f"No results for query: {query_text}"
            
            # Verify result contains relevant text
            found_relevant = any(
                query_text.lower() in result.content.get_text().lower()
                for result in results
            )
            assert found_relevant, f"No relevant results for: {query_text}"
    
    @pytest.mark.asyncio
    async def test_session_based_operations(self, smrti_system):
        """Test session-based memory operations with context."""
        smrti = smrti_system
        
        # Create a session for conversation context
        async with smrti.create_session(
            tenant_id="conversation_user",
            namespace="chat_session",
            session_metadata={"type": "conversation", "started_at": datetime.utcnow().isoformat()}
        ) as session:
            
            # Simulate a conversation with memory accumulation
            conversation = [
                "Hi, I'm working on a machine learning project",
                "It's about predicting customer behavior",
                "I'm using Python and scikit-learn",
                "The dataset has about 10,000 customer records",
                "I'm having trouble with feature selection"
            ]
            
            # Store each part of the conversation
            for i, text in enumerate(conversation):
                await session.add_memory(
                    text=text,
                    metadata={
                        "turn": i + 1,
                        "conversation_part": "setup" if i < 3 else "problem"
                    }
                )
            
            # Test contextual retrieval within session
            context = await session.get_context("feature selection help")
            
            # Should include relevant conversation history
            assert len(context) > 0
            context_text = " ".join(record.content.get_text() for record in context)
            assert "machine learning" in context_text.lower()
            assert "customer behavior" in context_text.lower()
            assert "feature selection" in context_text.lower()
            
            # Test that session context is maintained
            recent_context = await session.get_recent_context(limit=3)
            assert len(recent_context) <= 3
            
            # Most recent should be about feature selection
            if recent_context:
                latest = recent_context[0]
                assert "feature selection" in latest.content.get_text().lower()
    
    @pytest.mark.asyncio
    async def test_multi_user_isolation(self, smrti_system):
        """Test that memories are properly isolated between users/tenants."""
        smrti = smrti_system
        
        # Store memories for different users
        users = ["alice", "bob", "charlie"]
        user_memories = {
            "alice": ["Alice's secret project plan", "Alice's personal notes"],
            "bob": ["Bob's meeting summary", "Bob's code review comments"],
            "charlie": ["Charlie's research findings", "Charlie's experiment results"]
        }
        
        # Store memories for each user
        for user, memories in user_memories.items():
            for text in memories:
                await smrti.store_memory(
                    text=text,
                    tenant_id=user,
                    namespace="work",
                    metadata={"owner": user}
                )
        
        # Test that each user can only access their own memories
        for user in users:
            results = await smrti.retrieve_memories(
                query_text="project plan notes summary findings",  # Broad query
                tenant_id=user,
                namespace="work"
            )
            
            # Should only get results for this user
            for result in results:
                assert user in result.content.get_text().lower()
                assert result.metadata["owner"] == user
            
            # Should not get results for other users
            other_users = [u for u in users if u != user]
            for other_user in other_users:
                user_text_found = any(
                    other_user in result.content.get_text().lower()
                    for result in results
                )
                assert not user_text_found, f"User {user} accessed {other_user}'s memories"
    
    @pytest.mark.asyncio
    async def test_namespace_organization(self, smrti_system):
        """Test memory organization using namespaces."""
        smrti = smrti_system
        
        # Store memories in different namespaces
        namespaces = {
            "work": [
                "Quarterly business review scheduled for next week",
                "New employee onboarding process improvements",
                "Client project deadline moved to end of month"
            ],
            "personal": [
                "Dentist appointment scheduled for Thursday",
                "Mom's birthday is next month - need to buy gift",
                "Weekend hiking trip planned with friends"
            ],
            "learning": [
                "Completed machine learning course module 3",
                "Practice problems for data structures and algorithms",
                "Read research paper on neural network architectures"
            ]
        }
        
        # Store all memories
        for namespace, memories in namespaces.items():
            for text in memories:
                await smrti.store_memory(
                    text=text,
                    tenant_id="namespace_test_user",
                    namespace=namespace,
                    metadata={"category": namespace}
                )
        
        # Test namespace isolation
        for namespace in namespaces.keys():
            results = await smrti.retrieve_memories(
                query_text="scheduled appointment course",  # Cross-cutting query
                tenant_id="namespace_test_user",
                namespace=namespace
            )
            
            # Should only get results from this namespace
            for result in results:
                assert result.namespace == namespace
                assert result.metadata["category"] == namespace
            
            # Verify content matches expected namespace
            result_texts = [result.content.get_text() for result in results]
            namespace_keywords = {
                "work": ["business", "employee", "client"],
                "personal": ["dentist", "birthday", "hiking"],
                "learning": ["course", "algorithms", "research"]
            }
            
            found_keywords = []
            for text in result_texts:
                for keyword in namespace_keywords[namespace]:
                    if keyword in text.lower():
                        found_keywords.append(keyword)
            
            assert len(found_keywords) > 0, f"No namespace-specific content found in {namespace}"
    
    @pytest.mark.asyncio
    async def test_memory_consolidation_workflow(self, smrti_system):
        """Test memory consolidation in a realistic workflow."""
        smrti = smrti_system
        
        # Simulate learning process with many related memories
        learning_sequence = [
            "Started learning Python programming basics",
            "Learned about Python variables and data types", 
            "Practiced Python loops and conditionals",
            "Built first Python script to calculate fibonacci numbers",
            "Learned about Python functions and modules",
            "Created a simple calculator program in Python",
            "Studied Python object-oriented programming concepts",
            "Built a class-based inventory management system",
            "Learned about Python file handling and I/O",
            "Created data processing script for CSV files"
        ]
        
        # Store memories over time (simulate gradual learning)
        base_time = datetime.utcnow() - timedelta(days=10)
        stored_ids = []
        
        for i, text in enumerate(learning_sequence):
            timestamp = base_time + timedelta(days=i)
            record_id = await smrti.store_memory(
                text=text,
                tenant_id="learner",
                namespace="programming_journey",
                metadata={
                    "sequence": i + 1,
                    "topic": "python_learning",
                    "learning_day": i + 1
                }
            )
            stored_ids.append(record_id)
        
        # Query for all Python learning memories
        all_memories = await smrti.retrieve_memories(
            query_text="Python learning programming",
            tenant_id="learner",
            namespace="programming_journey",
            limit=20
        )
        
        # Should retrieve most/all of the stored memories
        assert len(all_memories) >= 8, "Should retrieve most learning memories"
        
        # Test consolidation (if available in the system)
        if hasattr(smrti, 'consolidate_memories'):
            consolidated = await smrti.consolidate_memories(
                tenant_id="learner",
                namespace="programming_journey",
                topic="python_learning"
            )
            
            # Consolidation should reduce redundancy while preserving key information
            assert consolidated is not None
            assert len(consolidated.get("consolidated_records", [])) > 0
    
    @pytest.mark.asyncio
    async def test_system_health_and_monitoring(self, smrti_system):
        """Test system health monitoring and status reporting."""
        smrti = smrti_system
        
        # Test health check
        health = await smrti.health_check()
        assert health is not None
        assert "status" in health
        assert health["status"] in ["healthy", "degraded", "unhealthy"]
        
        # Test component status
        if "components" in health:
            components = health["components"]
            
            # Should have status for key components
            expected_components = ["memory_tiers", "adapters", "engines"]
            for component in expected_components:
                if component in components:
                    assert "status" in components[component]
        
        # Test metrics (if available)
        if hasattr(smrti, 'get_metrics'):
            metrics = await smrti.get_metrics()
            assert metrics is not None
            
            # Should include basic operational metrics
            expected_metrics = ["total_memories", "active_sessions", "response_time"]
            available_metrics = set(metrics.keys()) if isinstance(metrics, dict) else set()
            
            # At least some metrics should be available
            assert len(available_metrics) > 0
    
    @pytest.mark.asyncio
    async def test_concurrent_user_sessions(self, smrti_system):
        """Test concurrent operations with multiple user sessions."""
        smrti = smrti_system
        
        async def user_workflow(user_id, session_count):
            """Simulate a user workflow with memory operations."""
            memories_stored = 0
            
            for session_num in range(session_count):
                async with smrti.create_session(
                    tenant_id=user_id,
                    namespace=f"session_{session_num}",
                    session_metadata={"session_id": session_num}
                ) as session:
                    
                    # Store some memories in this session
                    for i in range(3):
                        text = f"{user_id} session {session_num} memory {i}"
                        await session.add_memory(
                            text=text,
                            metadata={"session": session_num, "memory": i}
                        )
                        memories_stored += 1
                    
                    # Retrieve memories
                    context = await session.get_context(f"{user_id} memory")
                    assert len(context) >= 1
            
            return memories_stored
        
        # Run concurrent user workflows
        users = ["user1", "user2", "user3", "user4"]
        tasks = [user_workflow(user_id, 2) for user_id in users]  # 2 sessions per user
        
        results = await asyncio.gather(*tasks)
        
        # Verify all workflows completed successfully
        assert len(results) == 4
        assert all(count > 0 for count in results)
        
        # Verify total memories stored
        total_expected = sum(results)
        assert total_expected == 4 * 2 * 3  # 4 users × 2 sessions × 3 memories
    
    @pytest.mark.asyncio
    async def test_error_recovery_scenarios(self, smrti_system):
        """Test system behavior under error conditions."""
        smrti = smrti_system
        
        # Test graceful handling of invalid inputs
        
        # 1. Empty query
        results = await smrti.retrieve_memories(
            query_text="",
            tenant_id="test_user",
            namespace="test"
        )
        assert isinstance(results, list)  # Should return empty list, not error
        
        # 2. Very long query
        long_query = "test " * 1000  # Very long query
        results = await smrti.retrieve_memories(
            query_text=long_query,
            tenant_id="test_user", 
            namespace="test"
        )
        assert isinstance(results, list)  # Should handle gracefully
        
        # 3. Special characters in tenant ID
        special_tenant = "user@domain.com/special#chars"
        record_id = await smrti.store_memory(
            text="Memory with special tenant ID",
            tenant_id=special_tenant,
            namespace="test",
            metadata={"test": True}
        )
        assert record_id is not None
        
        # 4. Retrieve with same special tenant ID
        results = await smrti.retrieve_memories(
            query_text="special tenant",
            tenant_id=special_tenant,
            namespace="test"
        )
        assert len(results) >= 1
        
        # 5. Test system remains operational after errors
        normal_id = await smrti.store_memory(
            text="Normal operation after error handling",
            tenant_id="normal_user",
            namespace="test",
            metadata={"post_error": True}
        )
        assert normal_id is not None


class TestRealWorldScenarios:
    """Test realistic user scenarios and workflows."""
    
    @pytest.mark.asyncio
    async def test_research_assistant_scenario(self, smrti_system):
        """Test scenario: Using Smrti as a research assistant."""
        smrti = smrti_system
        
        # Research workflow: collecting and organizing information
        research_notes = [
            "Climate change affects global temperature patterns significantly",
            "Carbon dioxide levels have increased by 40% since pre-industrial times", 
            "Renewable energy adoption is growing rapidly worldwide",
            "Solar panel efficiency has improved dramatically in recent years",
            "Wind power capacity doubled in the last decade globally",
            "Electric vehicle sales are accelerating in major markets",
            "Battery technology improvements enable better energy storage",
            "Government policies play crucial role in clean energy transition"
        ]
        
        # Store research notes
        for i, note in enumerate(research_notes):
            await smrti.store_memory(
                text=note,
                tenant_id="researcher",
                namespace="climate_research",
                metadata={
                    "note_id": i + 1,
                    "research_area": "climate_change" if i < 2 else "renewable_energy",
                    "source_type": "literature_review"
                }
            )
        
        # Research queries
        queries = [
            "carbon dioxide levels climate change",
            "solar wind renewable energy growth", 
            "electric vehicles battery technology",
            "government policies clean energy"
        ]
        
        for query in queries:
            results = await smrti.retrieve_memories(
                query_text=query,
                tenant_id="researcher", 
                namespace="climate_research",
                limit=5
            )
            
            assert len(results) >= 1, f"No results found for research query: {query}"
            
            # Results should be relevant to the query topic
            combined_text = " ".join(result.content.get_text() for result in results)
            query_words = query.split()
            
            matches = sum(1 for word in query_words if word.lower() in combined_text.lower())
            assert matches >= 1, f"Research results not relevant to query: {query}"
    
    @pytest.mark.asyncio
    async def test_project_management_scenario(self, smrti_system):
        """Test scenario: Project management and tracking."""
        smrti = smrti_system
        
        # Project timeline with different types of information
        project_events = [
            ("Project Alpha kickoff meeting completed", "milestone"),
            ("Requirements gathering phase started", "phase"),
            ("Technical architecture design in progress", "task"),
            ("Database schema design completed", "deliverable"),
            ("API endpoints specification drafted", "deliverable"), 
            ("Frontend mockups under review", "task"),
            ("Sprint 1 planning meeting scheduled", "meeting"),
            ("User story prioritization completed", "task"),
            ("Development environment setup completed", "milestone"),
            ("First code commit pushed to repository", "milestone")
        ]
        
        # Store project information with proper categorization
        for text, event_type in project_events:
            await smrti.store_memory(
                text=text,
                tenant_id="project_manager",
                namespace="project_alpha",
                metadata={
                    "event_type": event_type,
                    "project": "alpha",
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
        
        # Project management queries
        management_queries = [
            ("What milestones have been completed?", "milestone"),
            ("What tasks are in progress?", "task"), 
            ("What deliverables are ready?", "deliverable"),
            ("When is the next meeting?", "meeting")
        ]
        
        for query_text, expected_type in management_queries:
            results = await smrti.retrieve_memories(
                query_text=query_text,
                tenant_id="project_manager",
                namespace="project_alpha"
            )
            
            assert len(results) >= 1, f"No results for PM query: {query_text}"
            
            # Check if results contain expected event types
            event_types = [result.metadata.get("event_type") for result in results]
            if expected_type in ["milestone", "deliverable"]:
                # Should find specific types for these queries
                assert expected_type in event_types or any(
                    expected_type in result.content.get_text().lower()
                    for result in results
                )
    
    @pytest.mark.asyncio  
    async def test_personal_assistant_scenario(self, smrti_system):
        """Test scenario: Personal assistant for daily tasks and reminders."""
        smrti = smrti_system
        
        # Personal information and tasks
        personal_items = [
            ("Doctor appointment scheduled for Thursday at 2 PM", "appointment"),
            ("Grocery list: milk, bread, eggs, chicken, vegetables", "shopping"),
            ("Call insurance company about policy renewal", "task"),
            ("Mom's birthday next month - need to plan celebration", "reminder"),
            ("Car maintenance due next week - oil change needed", "maintenance"),
            ("Book club meeting this Saturday to discuss current novel", "social"),
            ("Gym membership expires end of month - need to renew", "personal"),
            ("Password for work laptop expires in 5 days", "security"),
            ("Flight booking confirmation for vacation trip", "travel"),
            ("Prescription refill needed for blood pressure medication", "health")
        ]
        
        # Store personal information
        for text, category in personal_items:
            await smrti.store_memory(
                text=text,
                tenant_id="personal_user",
                namespace="daily_life",
                metadata={
                    "category": category,
                    "priority": "high" if category in ["health", "security"] else "normal",
                    "date_added": datetime.utcnow().isoformat()
                }
            )
        
        # Personal assistant queries
        personal_queries = [
            "What appointments do I have this week?",
            "What do I need to buy at the grocery store?",
            "What tasks do I need to complete?",
            "Are there any important reminders?",
            "What health-related items need attention?"
        ]
        
        for query in personal_queries:
            results = await smrti.retrieve_memories(
                query_text=query,
                tenant_id="personal_user",
                namespace="daily_life"
            )
            
            assert len(results) >= 1, f"No results for personal query: {query}"
            
            # Verify relevance
            result_text = " ".join(result.content.get_text() for result in results)
            
            # Check query-specific expectations
            if "appointment" in query.lower():
                assert any(word in result_text.lower() for word in ["appointment", "scheduled", "meeting"])
            elif "grocery" in query.lower() or "buy" in query.lower():
                assert "grocery" in result_text.lower() or "milk" in result_text.lower()
            elif "health" in query.lower():
                assert any(word in result_text.lower() for word in ["doctor", "prescription", "medication"])


@pytest.fixture
def sample_user_data():
    """Fixture providing sample user data for end-to-end testing."""
    return {
        "users": {
            "alice": {
                "work_memories": [
                    "Alice is leading the backend API development",
                    "Alice completed the user authentication system",
                    "Alice is mentoring junior developers on code quality"
                ],
                "personal_memories": [
                    "Alice enjoys hiking on weekends",
                    "Alice is learning Spanish in her free time", 
                    "Alice has a cat named Whiskers"
                ]
            },
            "bob": {
                "work_memories": [
                    "Bob is responsible for frontend user interface",
                    "Bob implemented the responsive design system",
                    "Bob is coordinating with the design team"
                ],
                "personal_memories": [
                    "Bob plays guitar and writes music",
                    "Bob is training for a marathon next year",
                    "Bob volunteers at local animal shelter"
                ]
            }
        }
    }


class TestEndToEndFixtures:
    """Test end-to-end functionality using sample data fixtures."""
    
    @pytest.mark.asyncio
    async def test_sample_user_workflows(self, smrti_system, sample_user_data):
        """Test workflows using sample user data."""
        smrti = smrti_system
        users_data = sample_user_data["users"]
        
        # Store memories for all users
        for user_name, user_data in users_data.items():
            # Store work memories
            for memory in user_data["work_memories"]:
                await smrti.store_memory(
                    text=memory,
                    tenant_id=user_name,
                    namespace="work",
                    metadata={"type": "work", "user": user_name}
                )
            
            # Store personal memories
            for memory in user_data["personal_memories"]:
                await smrti.store_memory(
                    text=memory,
                    tenant_id=user_name,
                    namespace="personal",
                    metadata={"type": "personal", "user": user_name}
                )
        
        # Test user-specific retrieval
        for user_name in users_data.keys():
            # Work-related query
            work_results = await smrti.retrieve_memories(
                query_text="development API system",
                tenant_id=user_name,
                namespace="work"
            )
            
            # Should get work-related results for this user
            assert len(work_results) >= 1
            for result in work_results:
                assert result.metadata["user"] == user_name
                assert result.metadata["type"] == "work"
            
            # Personal query
            personal_results = await smrti.retrieve_memories(
                query_text="hobby interest activity",
                tenant_id=user_name,
                namespace="personal"
            )
            
            # Should get personal results for this user
            assert len(personal_results) >= 1
            for result in personal_results:
                assert result.metadata["user"] == user_name
                assert result.metadata["type"] == "personal"
    
    def test_sample_data_structure(self, sample_user_data):
        """Test that sample user data fixture is properly structured."""
        assert "users" in sample_user_data
        users = sample_user_data["users"]
        
        assert "alice" in users
        assert "bob" in users
        
        for user_name, user_data in users.items():
            assert "work_memories" in user_data
            assert "personal_memories" in user_data
            assert len(user_data["work_memories"]) >= 3
            assert len(user_data["personal_memories"]) >= 3