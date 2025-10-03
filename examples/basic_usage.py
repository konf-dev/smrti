#!/usr/bin/env python3
"""
examples/basic_usage.py - Basic Smrti Usage Examples

Demonstrates basic usage patterns of the Smrti intelligent memory system.
"""

import asyncio
import logging
from typing import List

# Import the main Smrti API
from smrti import Smrti, SmrtiConfig, QueryStrategy, ResultMergeStrategy

# Setup logging to see what's happening
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')


async def basic_example():
    """Basic usage example with auto-initialization."""
    print("🧠 Basic Smrti Usage Example")
    print("=" * 50)
    
    # Create configuration (uses defaults for all storage backends)
    config = SmrtiConfig(
        # Use default configurations for Redis, ChromaDB, etc.
        # In production, you'd configure actual connection details
        default_tenant_id="example_user",
        auto_start_consolidation=True,
        log_level="INFO"
    )
    
    # Create and initialize the Smrti system
    async with Smrti(config) as smrti:
        print("✅ Smrti system initialized successfully!")
        
        # Store some memories with different importance levels
        print("\n📝 Storing memories...")
        
        # High importance memory (goes to working memory)
        important_id = await smrti.store_memory(
            content="I need to remember to call the client about the project deadline tomorrow",
            importance=0.9,
            metadata={"category": "urgent", "type": "task"}
        )
        
        # Medium importance memory (goes to short-term memory)
        medium_id = await smrti.store_memory(
            content="Machine learning algorithms can be categorized into supervised and unsupervised learning",
            importance=0.6,
            metadata={"category": "learning", "subject": "ML"}
        )
        
        # Lower importance memory (goes to long-term memory)
        general_id = await smrti.store_memory(
            content="Coffee was invented in Ethiopia and spread through the Arab world",
            importance=0.4,
            metadata={"category": "trivia", "topic": "history"}
        )
        
        print(f"   • Stored urgent task: {important_id[:8]}...")
        print(f"   • Stored ML concept: {medium_id[:8]}...")
        print(f"   • Stored coffee fact: {general_id[:8]}...")
        
        # Search for memories
        print("\n🔍 Searching memories...")
        
        # Search for project-related memories
        project_results = await smrti.search_memories(
            "project deadline client",
            limit=5,
            similarity_threshold=0.1
        )
        print(f"   • Found {len(project_results)} memories about 'project deadline'")
        for result in project_results:
            print(f"     - Score: {result.total_score:.2f}, Tier: {result.tier_source}")
            print(f"       Content: {str(result.record.content)[:80]}...")
        
        # Search for learning-related memories
        learning_results = await smrti.search_memories(
            "machine learning algorithms",
            limit=5
        )
        print(f"\n   • Found {len(learning_results)} memories about 'machine learning'")
        for result in learning_results:
            print(f"     - Score: {result.total_score:.2f}, Tier: {result.tier_source}")
        
        # Get system statistics
        print("\n📊 System Statistics:")
        stats = await smrti.get_system_stats()
        
        print(f"   • Total operations: {stats['system']['total_operations']}")
        print(f"   • Success rate: {stats['system']['success_rate']:.1%}")
        print(f"   • Available tiers: {', '.join(stats['registry']['available_tiers'])}")
        print(f"   • Embedding providers: {', '.join(stats['registry']['available_embedders'])}")
        
        print("\n✨ Basic example completed!")


async def session_example():
    """Example using session-based memory management."""
    print("\n🎯 Session-Based Usage Example")
    print("=" * 50)
    
    config = SmrtiConfig(log_level="INFO")
    
    async with Smrti(config) as smrti:
        print("✅ Smrti system initialized!")
        
        # Create a session for a specific learning context
        async with smrti.session(namespace="python_learning") as session:
            print("\n📚 Learning session started...")
            
            # Store learning memories in session context
            await session.store_memory(
                "Python dictionaries are key-value data structures",
                importance=0.8,
                metadata={"lesson": "data_structures"}
            )
            
            await session.store_memory(
                "List comprehensions provide a concise way to create lists",
                importance=0.7,
                metadata={"lesson": "syntax"}
            )
            
            await session.store_memory(
                "The 'with' statement is used for context management",
                importance=0.6,
                metadata={"lesson": "control_flow"}
            )
            
            print("   • Stored 3 Python learning concepts")
            
            # Search within the session context
            results = await session.search_memories("data structures")
            print(f"   • Found {len(results)} memories about data structures in this session")
            
            # Search across all sessions
            all_results = await smrti.search_memories(
                "Python dictionaries",
                namespace="python_learning"
            )
            print(f"   • Found {len(all_results)} total memories about Python dictionaries")
        
        print("   • Learning session completed!")


async def advanced_retrieval_example():
    """Example demonstrating advanced retrieval strategies."""
    print("\n🚀 Advanced Retrieval Example")
    print("=" * 50)
    
    config = SmrtiConfig(log_level="INFO")
    
    async with Smrti(config) as smrti:
        print("✅ Smrti system initialized!")
        
        # Store diverse memories
        print("\n📝 Storing diverse memories...")
        
        memories = [
            ("Artificial intelligence will transform healthcare", 0.8, {"domain": "AI", "sector": "healthcare"}),
            ("Machine learning models require large datasets", 0.7, {"domain": "AI", "topic": "data"}), 
            ("Neural networks mimic biological brain structures", 0.6, {"domain": "AI", "topic": "architecture"}),
            ("Data privacy is crucial in AI applications", 0.9, {"domain": "AI", "aspect": "ethics"}),
            ("Python is popular for AI development", 0.5, {"domain": "programming", "topic": "languages"})
        ]
        
        for content, importance, metadata in memories:
            await smrti.store_memory(content, importance=importance, metadata=metadata)
        
        print(f"   • Stored {len(memories)} diverse memories")
        
        # Test different query strategies
        print("\n🔍 Testing different retrieval strategies...")
        
        query_text = "artificial intelligence healthcare"
        
        # Parallel strategy (fast, queries all tiers simultaneously)
        parallel_results = await smrti.retrieve_memories(
            query_text,
            limit=10,
            strategy=QueryStrategy.PARALLEL,
            merge_strategy=ResultMergeStrategy.SCORE_WEIGHTED
        )
        print(f"   • Parallel strategy: {len(parallel_results)} results")
        
        # Cascading strategy (efficient, stops when enough results found)
        cascading_results = await smrti.retrieve_memories(
            query_text,
            limit=10,
            strategy=QueryStrategy.CASCADING,
            merge_strategy=ResultMergeStrategy.DIVERSITY_FIRST
        )
        print(f"   • Cascading strategy: {len(cascading_results)} results")
        
        # Show top result details
        if parallel_results:
            top_result = parallel_results[0]
            print(f"\n🏆 Top result (score: {top_result.total_score:.3f}):")
            print(f"   • Content: {top_result.record.content}")
            print(f"   • From tier: {top_result.tier_source}")
            print(f"   • Metadata: {top_result.record.metadata}")


async def consolidation_example():
    """Example demonstrating memory consolidation."""
    print("\n🔄 Memory Consolidation Example")
    print("=" * 50)
    
    config = SmrtiConfig(
        consolidation_config=None,  # Use defaults
        auto_start_consolidation=True,
        log_level="INFO"
    )
    
    async with Smrti(config) as smrti:
        print("✅ Smrti system with consolidation initialized!")
        
        # Store many memories to trigger consolidation
        print("\n📝 Storing many memories to demonstrate consolidation...")
        
        for i in range(20):
            await smrti.store_memory(
                f"This is test memory number {i+1} with some content to fill the tiers",
                importance=0.3 + (i % 5) * 0.1,  # Varying importance
                metadata={"batch": "consolidation_test", "index": i}
            )
        
        print("   • Stored 20 test memories")
        
        # Force consolidation to see it in action
        print("\n🔄 Forcing memory consolidation...")
        consolidation_result = await smrti.force_consolidation()
        
        print(f"   • Consolidation completed:")
        print(f"     - Plans executed: {consolidation_result['plans_executed']}")
        print(f"     - Records processed: {consolidation_result['records_processed']}")
        print(f"     - Duration: {consolidation_result['duration']:.2f}s")
        
        # Check system stats after consolidation
        stats = await smrti.get_system_stats()
        if 'consolidation' in stats:
            cons_stats = stats['consolidation']
            print(f"   • Total consolidations performed: {cons_stats.get('consolidations_performed', 0)}")
            print(f"   • Records consolidated: {cons_stats.get('records_consolidated', 0)}")


async def health_monitoring_example():
    """Example demonstrating health monitoring."""
    print("\n🏥 Health Monitoring Example")
    print("=" * 50)
    
    config = SmrtiConfig(
        enable_health_monitoring=True,
        log_level="INFO"
    )
    
    async with Smrti(config) as smrti:
        print("✅ Smrti system with health monitoring initialized!")
        
        # Check system health
        print("\n❤️ Checking system health...")
        health = await smrti.get_health_status()
        
        print(f"   • Overall status: {health['status']}")
        print(f"   • Timestamp: {health['timestamp']}")
        
        if 'components' in health:
            print("   • Component health:")
            for component, status in health['components'].items():
                print(f"     - {component}: {status.get('status', 'unknown')}")
        
        if 'tiers' in health:
            print("   • Memory tier health:")
            for tier, status in health['tiers'].items():
                print(f"     - {tier}: {status.get('status', 'unknown')}")
        
        # Get detailed statistics
        print("\n📈 Detailed system statistics...")
        stats = await smrti.get_system_stats()
        
        print("   • System overview:")
        sys_stats = stats['system']
        print(f"     - Operations: {sys_stats['total_operations']}")
        print(f"     - Success rate: {sys_stats['success_rate']:.1%}")
        print(f"     - Active sessions: {sys_stats['active_sessions']}")
        
        reg_stats = stats['registry']
        print(f"     - Available tiers: {reg_stats['available_tiers']}")
        print(f"     - Embedding providers: {reg_stats['available_embedders']}")


async def main():
    """Run all examples."""
    print("🧠 Smrti Intelligent Memory System - Usage Examples")
    print("=" * 60)
    print("This demonstrates the complete Smrti system in action!")
    print("Note: This example uses default configurations.")
    print("In production, configure actual Redis, ChromaDB, etc. connections.")
    print("=" * 60)
    
    try:
        # Run basic example
        await basic_example()
        
        # Run session example
        await session_example()
        
        # Run advanced retrieval example
        await advanced_retrieval_example()
        
        # Run consolidation example
        await consolidation_example()
        
        # Run health monitoring example
        await health_monitoring_example()
        
        print("\n🎉 All examples completed successfully!")
        print("\nNext steps:")
        print("• Configure actual storage backends (Redis, ChromaDB, PostgreSQL, Neo4j, Elasticsearch)")
        print("• Set up OpenAI API key for advanced embedding capabilities")
        print("• Explore custom consolidation rules and retrieval strategies")
        print("• Implement custom content types and memory tier configurations")
        
    except Exception as e:
        print(f"\n❌ Example failed: {e}")
        print("\nThis is expected if storage backends are not configured.")
        print("The examples show how the system would work with proper setup.")


if __name__ == "__main__":
    asyncio.run(main())