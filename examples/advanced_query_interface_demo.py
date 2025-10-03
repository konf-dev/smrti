"""
examples/advanced_query_interface_demo.py - Advanced Query Interface Examples

Comprehensive demonstration of Smrti's advanced query capabilities including
semantic search, temporal filtering, importance ranking, and natural language processing.
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Import Smrti components
from smrti.models.base import MemoryItem
from smrti.query import (
    QueryEngine, QueryContext, QueryParser, QueryAST,
    SemanticSearchEngine, TemporalFilter, 
    ImportanceFilter, ComplexityFilter, LabelFilter,
    RankingEngine, CompositeRanker, RankingMethod
)


class MockMemoryItem(MemoryItem):
    """Mock memory item for demonstration."""
    
    def __init__(self, id: str, content: str, title: str = "", 
                 importance: float = 0.5, labels: List[str] = None,
                 created_at: float = None, access_count: int = 0):
        super().__init__()
        self.id = id
        self.content = content
        self.title = title
        self.importance = importance
        self.labels = labels or []
        self.created_at = created_at or time.time()
        self.access_count = access_count
        self.metadata = {
            'importance': importance,
            'labels': labels or [],
            'tier': 'hot' if importance > 0.7 else 'warm' if importance > 0.3 else 'cold'
        }


def create_sample_memories() -> List[MemoryItem]:
    """Create sample memory items for demonstration."""
    base_time = time.time()
    day_seconds = 24 * 60 * 60
    
    memories = [
        MockMemoryItem(
            id="mem_001",
            content="Python machine learning tutorial with scikit-learn and pandas for data analysis",
            title="Machine Learning with Python",
            importance=0.9,
            labels=["programming", "machine-learning", "python", "tutorial"],
            created_at=base_time - 2 * day_seconds,  # 2 days ago
            access_count=15
        ),
        MockMemoryItem(
            id="mem_002", 
            content="JavaScript async/await patterns and promises for modern web development",
            title="Async JavaScript Patterns",
            importance=0.7,
            labels=["programming", "javascript", "async", "web-development"],
            created_at=base_time - 5 * day_seconds,  # 5 days ago
            access_count=8
        ),
        MockMemoryItem(
            id="mem_003",
            content="Docker containerization best practices and deployment strategies",
            title="Docker Best Practices",
            importance=0.8,
            labels=["devops", "docker", "deployment", "containers"],
            created_at=base_time - 1 * day_seconds,  # 1 day ago
            access_count=12
        ),
        MockMemoryItem(
            id="mem_004",
            content="React hooks useState and useEffect for component state management",
            title="React Hooks Guide", 
            importance=0.6,
            labels=["programming", "react", "frontend", "hooks"],
            created_at=base_time - 3 * day_seconds,  # 3 days ago
            access_count=6
        ),
        MockMemoryItem(
            id="mem_005",
            content="Database indexing strategies for PostgreSQL query optimization",
            title="PostgreSQL Indexing",
            importance=0.5,
            labels=["database", "postgresql", "optimization", "indexing"],
            created_at=base_time - 7 * day_seconds,  # 1 week ago
            access_count=4
        ),
        MockMemoryItem(
            id="mem_006",
            content="Git branching strategies and collaborative development workflows",
            title="Git Workflow Strategies",
            importance=0.4,
            labels=["git", "version-control", "collaboration", "workflow"],
            created_at=base_time - 10 * day_seconds,  # 10 days ago
            access_count=3
        ),
        MockMemoryItem(
            id="mem_007",
            content="Advanced Python decorators and metaclasses for framework development",
            title="Advanced Python Concepts",
            importance=0.8,
            labels=["programming", "python", "advanced", "decorators"],
            created_at=base_time - 4 * day_seconds,  # 4 days ago
            access_count=7
        ),
        MockMemoryItem(
            id="mem_008",
            content="Kubernetes deployment and service mesh architecture with Istio",
            title="Kubernetes with Istio",
            importance=0.9,
            labels=["devops", "kubernetes", "service-mesh", "istio"],
            created_at=base_time - 6 * day_seconds,  # 6 days ago
            access_count=10
        ),
        MockMemoryItem(
            id="mem_009",
            content="Vue.js component composition and reactivity system fundamentals",
            title="Vue.js Reactivity",
            importance=0.3,
            labels=["programming", "vue", "frontend", "reactivity"],
            created_at=base_time - 8 * day_seconds,  # 8 days ago
            access_count=2
        ),
        MockMemoryItem(
            id="mem_010",
            content="REST API design principles and GraphQL query optimization techniques",
            title="API Design Patterns",
            importance=0.7,
            labels=["api", "rest", "graphql", "design"],
            created_at=base_time - 9 * day_seconds,  # 9 days ago
            access_count=5
        )
    ]
    
    return memories


class QueryInterfaceDemo:
    """Demonstration of advanced query interface capabilities."""
    
    def __init__(self):
        """Initialize query interface demo."""
        self.memories = create_sample_memories()
        self.query_engine = QueryEngine()
        self.query_parser = QueryParser()
        self.semantic_engine = SemanticSearchEngine()
        self.ranking_engine = RankingEngine()
        
        print("🧠 Advanced Query Interface Demo")
        print("=" * 50)
        print(f"Loaded {len(self.memories)} sample memories")
        print()
    
    async def run_all_demos(self):
        """Run all demonstration scenarios."""
        await self.demo_natural_language_queries()
        await self.demo_structured_queries()
        await self.demo_semantic_search()
        await self.demo_temporal_filtering()
        await self.demo_importance_filtering()
        await self.demo_complex_filtering()
        await self.demo_ranking_algorithms()
        await self.demo_composite_queries()
        await self.demo_query_suggestions()
        
        # Show statistics
        self.show_statistics()
    
    async def demo_natural_language_queries(self):
        """Demonstrate natural language query parsing."""
        print("🗣️  Natural Language Query Parsing")
        print("-" * 40)
        
        natural_queries = [
            "recent Python tutorials",
            "most relevant machine learning content",
            "important programming resources since last week",
            "show first 3 Docker deployment guides",
            "what is React hooks",
            "how to optimize database queries", 
            "JavaScript or Python programming guides",
            "not frontend development topics"
        ]
        
        for query in natural_queries:
            print(f"\nQuery: '{query}'")
            ast = self.query_parser.parse_query(query)
            
            print(f"  Type: {ast.query_type.value}")
            print(f"  Confidence: {ast.parse_confidence:.2f}")
            
            if ast.semantic_terms:
                print(f"  Terms: {', '.join(ast.semantic_terms)}")
            
            if ast.temporal_expressions:
                print(f"  Temporal: {', '.join(ast.temporal_expressions)}")
            
            if ast.ranking_method:
                print(f"  Ranking: {ast.ranking_method}")
            
            if ast.limit:
                print(f"  Limit: {ast.limit}")
            
            if ast.boolean_logic != "AND":
                print(f"  Logic: {ast.boolean_logic}")
            
            # Execute the query
            context = QueryContext(
                query_text=query,
                query_ast=ast,
                limit=ast.limit or 5
            )
            
            results = await self.query_engine.execute_query(self.memories, context)
            print(f"  Results: {len(results.items)} items found")
            
            for i, item in enumerate(results.items[:2]):  # Show first 2
                print(f"    {i+1}. {item.title} (score: {getattr(item, 'score', 0.5):.2f})")
        
        print()
    
    async def demo_structured_queries(self):
        """Demonstrate structured query formats."""
        print("📊 Structured Query Formats")
        print("-" * 40)
        
        structured_queries = [
            # JSON format
            '{"terms": ["python", "machine learning"], "ranking": "importance", "limit": 3}',
            
            # Dictionary format
            "{'semantic': ['docker', 'deployment'], 'filters': {'importance': {'min': 0.6}}}",
            
            # Mixed format with temporal
            '{"search": "programming tutorial", "temporal": "last 5 days", "sort": "recency"}'
        ]
        
        for query in structured_queries:
            print(f"\nStructured Query:")
            print(f"  {query}")
            
            ast = self.query_parser.parse_query(query)
            print(f"  Parsed Type: {ast.query_type.value}")
            print(f"  Confidence: {ast.parse_confidence:.2f}")
            
            context = QueryContext(
                query_text=query,
                query_ast=ast,
                limit=ast.limit or 3
            )
            
            results = await self.query_engine.execute_query(self.memories, context)
            print(f"  Results: {len(results.items)} items")
            
            for item in results.items:
                print(f"    - {item.title}")
        
        print()
    
    async def demo_semantic_search(self):
        """Demonstrate semantic search capabilities."""
        print("🔍 Semantic Search Engine")
        print("-" * 40)
        
        search_queries = [
            "container deployment automation",
            "frontend component state",
            "database performance tuning",
            "asynchronous programming patterns"
        ]
        
        for query in search_queries:
            print(f"\nSemantic Search: '{query}'")
            
            results = await self.semantic_engine.search(
                query=query,
                items=self.memories,
                limit=3
            )
            
            print(f"  Found {len(results)} semantically similar items:")
            
            for result in results:
                print(f"    - {result.item.title}")
                print(f"      Similarity: {result.similarity_score:.3f}")
                print(f"      Content: {result.item.content[:50]}...")
        
        print()
    
    async def demo_temporal_filtering(self):
        """Demonstrate temporal filtering."""
        print("⏰ Temporal Filtering")
        print("-" * 40)
        
        temporal_filter = TemporalFilter()
        
        temporal_expressions = [
            "last 3 days",
            "since last week", 
            "before yesterday",
            "between 2 days ago and today"
        ]
        
        for expression in temporal_expressions:
            print(f"\nTemporal Filter: '{expression}'")
            
            filtered_items = await temporal_filter.apply(
                items=self.memories,
                time_expression=expression
            )
            
            print(f"  Items matching temporal criteria: {len(filtered_items)}")
            
            for item in filtered_items[:3]:  # Show first 3
                days_ago = (time.time() - item.created_at) / (24 * 60 * 60)
                print(f"    - {item.title} ({days_ago:.1f} days ago)")
        
        print()
    
    async def demo_importance_filtering(self):
        """Demonstrate importance-based filtering."""
        print("⭐ Importance Filtering")
        print("-" * 40)
        
        importance_filters = [
            ImportanceFilter(min_importance=0.8),  # High importance
            ImportanceFilter(min_importance=0.5, max_importance=0.7),  # Medium
            ImportanceFilter(max_importance=0.4)  # Low importance
        ]
        
        filter_names = ["High Importance (≥0.8)", "Medium Importance (0.5-0.7)", "Low Importance (≤0.4)"]
        
        for filter_obj, name in zip(importance_filters, filter_names):
            print(f"\n{name}:")
            
            context = QueryContext()
            filtered_items = await filter_obj.apply(self.memories, context)
            
            print(f"  Items found: {len(filtered_items)}")
            
            for item in filtered_items:
                print(f"    - {item.title} (importance: {item.importance:.1f})")
        
        print()
    
    async def demo_complex_filtering(self):
        """Demonstrate complex filtering combinations."""
        print("🔧 Complex Filtering")
        print("-" * 40)
        
        # Complexity filter
        print("\nComplexity Filter (>100 characters):")
        complexity_filter = ComplexityFilter(min_complexity=100, complexity_metric="length")
        context = QueryContext()
        
        filtered_items = await complexity_filter.apply(self.memories, context)
        print(f"  Items with complex content: {len(filtered_items)}")
        
        for item in filtered_items[:3]:
            print(f"    - {item.title} ({len(item.content)} chars)")
        
        # Label filter
        print("\nLabel Filter (programming content):")
        label_filter = LabelFilter(required_labels=["programming"])
        
        filtered_items = await label_filter.apply(self.memories, context)
        print(f"  Programming-related items: {len(filtered_items)}")
        
        for item in filtered_items[:3]:
            print(f"    - {item.title}")
            print(f"      Labels: {', '.join(item.labels)}")
        
        print()
    
    async def demo_ranking_algorithms(self):
        """Demonstrate different ranking algorithms."""
        print("🏆 Ranking Algorithms")
        print("-" * 40)
        
        # Test different ranking methods
        ranking_methods = [
            ("importance", "Importance-based ranking"),
            ("recency", "Recency-based ranking"), 
            ("frequency", "Access frequency ranking"),
            ("composite", "Composite ranking")
        ]
        
        for method, description in ranking_methods:
            print(f"\n{description}:")
            
            context = QueryContext(
                query_text="programming tutorial",
                limit=5
            )
            
            ranked_items = await self.ranking_engine.rank_items(
                items=self.memories,
                context=context,
                method=method
            )
            
            print("  Top results:")
            for ranked_item in ranked_items:
                print(f"    {ranked_item.rank}. {ranked_item.item.title}")
                print(f"       Score: {ranked_item.score.total_score:.3f}")
                print(f"       Explanation: {ranked_item.explanation}")
        
        print()
    
    async def demo_composite_queries(self):
        """Demonstrate complex composite queries."""
        print("🧩 Composite Queries")
        print("-" * 40)
        
        complex_queries = [
            "important Python tutorials from last week",
            "recent Docker guides with high access frequency",
            "programming content longer than 50 words sorted by importance"
        ]
        
        for query in complex_queries:
            print(f"\nComposite Query: '{query}'")
            
            # Parse and execute the complex query
            ast = self.query_parser.parse_query(query)
            
            context = QueryContext(
                query_text=query,
                query_ast=ast,
                limit=3
            )
            
            results = await self.query_engine.execute_query(self.memories, context)
            
            print(f"  Query components:")
            print(f"    - Terms: {', '.join(ast.semantic_terms)}")
            if ast.temporal_expressions:
                print(f"    - Temporal: {', '.join(ast.temporal_expressions)}")
            if ast.filters:
                print(f"    - Filters: {len(ast.filters)} applied")
            if ast.ranking_method:
                print(f"    - Ranking: {ast.ranking_method}")
            
            print(f"  Results ({len(results.items)} items):")
            for item in results.items:
                print(f"    - {item.title}")
        
        print()
    
    async def demo_query_suggestions(self):
        """Demonstrate query suggestion system."""
        print("💡 Query Suggestions")
        print("-" * 40)
        
        problematic_queries = [
            "find stuff",  # Too vague
            "python javascript react vue angular node",  # Too many terms
            "when was docker created",  # Needs temporal
            "best tutorial ever"  # Needs ranking
        ]
        
        for query in problematic_queries:
            print(f"\nQuery: '{query}'")
            ast = self.query_parser.parse_query(query)
            
            suggestions = self.query_parser.suggest_query_improvements(query, ast)
            
            print(f"  Confidence: {ast.parse_confidence:.2f}")
            if suggestions:
                print("  Suggestions:")
                for suggestion in suggestions:
                    print(f"    - {suggestion}")
            else:
                print("  No suggestions needed - query looks good!")
        
        print()
    
    def show_statistics(self):
        """Show query engine statistics."""
        print("📈 Query Engine Statistics")
        print("-" * 40)
        
        # Parser statistics
        parse_stats = self.query_parser.get_parse_stats()
        print("\nQuery Parser:")
        for stat, value in parse_stats.items():
            print(f"  {stat.replace('_', ' ').title()}: {value}")
        
        # Ranking statistics
        ranking_stats = self.ranking_engine.get_ranking_stats()
        print("\nRanking Engine:")
        for ranker, stats in ranking_stats.items():
            if stats['applications'] > 0:
                avg_time = stats['total_time'] / stats['applications']
                print(f"  {ranker.title()}:")
                print(f"    Applications: {stats['applications']}")
                print(f"    Average Time: {avg_time:.3f}s")
                print(f"    Items Ranked: {stats['items_ranked']}")
        
        print()


def main():
    """Run the advanced query interface demonstration."""
    print("🚀 Starting Advanced Query Interface Demo...")
    print()
    
    demo = QueryInterfaceDemo()
    
    # Run the demonstration
    try:
        asyncio.run(demo.run_all_demos())
        print("✅ Demo completed successfully!")
        
    except KeyboardInterrupt:
        print("\n⏹️  Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()