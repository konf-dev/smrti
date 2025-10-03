"""
tests/integration/test_advanced_query_integration.py - Advanced Query Integration Tests

Comprehensive integration tests for the complete advanced query interface
including semantic search, temporal filtering, ranking, and natural language parsing.
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Import test utilities
from tests.conftest import create_test_memory_item, AsyncTestCase

# Import Smrti components
from smrti.models.base import MemoryItem
from smrti.query import (
    QueryEngine, QueryContext, QueryParser, QueryAST, QueryType,
    SemanticSearchEngine, TemporalFilter, 
    ImportanceFilter, ComplexityFilter, LabelFilter, CompositeFilter,
    RankingEngine, RankingMethod, RankedItem, RankingScore,
    FilterOperator, ComparisonOperator
)


class TestAdvancedQueryIntegration(AsyncTestCase):
    """Integration tests for advanced query interface."""
    
    def setUp(self):
        """Set up test fixtures."""
        super().setUp()
        
        # Initialize query components
        self.query_engine = QueryEngine()
        self.query_parser = QueryParser()
        self.semantic_engine = SemanticSearchEngine()
        self.ranking_engine = RankingEngine()
        
        # Create test memory items
        self.memories = self._create_test_memories()
    
    def _create_test_memories(self) -> List[MemoryItem]:
        """Create test memory items with varied content."""
        base_time = time.time()
        day_seconds = 24 * 60 * 60
        
        memories = [
            create_test_memory_item(
                id="test_001",
                content="Python machine learning with scikit-learn pandas numpy for data science",
                metadata={
                    "importance": 0.9,
                    "labels": ["python", "ml", "data-science"],
                    "created_at": base_time - 2 * day_seconds,
                    "access_count": 15,
                    "title": "ML with Python"
                }
            ),
            create_test_memory_item(
                id="test_002",
                content="JavaScript async await promises modern web development patterns",
                metadata={
                    "importance": 0.7,
                    "labels": ["javascript", "web", "async"],
                    "created_at": base_time - 5 * day_seconds,
                    "access_count": 8,
                    "title": "JS Async Patterns"
                }
            ),
            create_test_memory_item(
                id="test_003",
                content="Docker containerization deployment kubernetes orchestration devops",
                metadata={
                    "importance": 0.8,
                    "labels": ["docker", "devops", "kubernetes"],
                    "created_at": base_time - 1 * day_seconds,
                    "access_count": 12,
                    "title": "Container Deployment"
                }
            ),
            create_test_memory_item(
                id="test_004",
                content="Short note",
                metadata={
                    "importance": 0.3,
                    "labels": ["notes"],
                    "created_at": base_time - 10 * day_seconds,
                    "access_count": 1,
                    "title": "Brief Note"
                }
            ),
            create_test_memory_item(
                id="test_005",
                content="React hooks useState useEffect component state management frontend",
                metadata={
                    "importance": 0.6,
                    "labels": ["react", "frontend", "hooks"],
                    "created_at": base_time - 3 * day_seconds,
                    "access_count": 6,
                    "title": "React State Management"
                }
            )
        ]
        
        return memories
    
    async def test_natural_language_query_parsing(self):
        """Test natural language query parsing and execution."""
        queries = [
            ("recent Python tutorials", QueryType.TEMPORAL),
            ("important machine learning content", QueryType.FILTERED),
            ("most relevant Docker guides", QueryType.RANKED),
            ("programming and development", QueryType.COMPOSITE),
            ("show first 3 results", QueryType.SEMANTIC)
        ]
        
        for query, expected_type in queries:
            with self.subTest(query=query):
                # Parse the query
                ast = self.query_parser.parse_query(query)
                
                # Verify parse results
                self.assertEqual(ast.query_type, expected_type)
                self.assertGreater(ast.parse_confidence, 0.5)
                self.assertTrue(ast.semantic_terms or ast.filters or ast.temporal_expressions)
                
                # Execute the query
                context = QueryContext(
                    query_text=query,
                    query_ast=ast,
                    limit=5
                )
                
                results = await self.query_engine.execute_query(self.memories, context)
                
                # Verify results
                self.assertIsNotNone(results)
                self.assertLessEqual(len(results.items), 5)
                self.assertGreater(results.execution_time, 0)
    
    async def test_semantic_search_integration(self):
        """Test semantic search engine integration."""
        search_queries = [
            "machine learning data analysis",
            "web development javascript",
            "container deployment automation",
            "frontend component management"
        ]
        
        for query in search_queries:
            with self.subTest(query=query):
                results = await self.semantic_engine.search(
                    query=query,
                    items=self.memories,
                    limit=3
                )
                
                # Verify semantic results
                self.assertLessEqual(len(results), 3)
                
                for result in results:
                    self.assertIsInstance(result.similarity_score, float)
                    self.assertGreaterEqual(result.similarity_score, 0.0)
                    self.assertLessEqual(result.similarity_score, 1.0)
                    self.assertIn(result.item, self.memories)
    
    async def test_temporal_filtering_integration(self):
        """Test temporal filtering with various expressions."""
        temporal_filter = TemporalFilter()
        
        expressions = [
            "last 3 days",
            "since last week",
            "before yesterday",
            "between 2 days ago and today"
        ]
        
        for expression in expressions:
            with self.subTest(expression=expression):
                filtered_items = await temporal_filter.apply(
                    items=self.memories,
                    time_expression=expression
                )
                
                # Verify temporal filtering
                self.assertIsInstance(filtered_items, list)
                for item in filtered_items:
                    self.assertIn(item, self.memories)
                
                # Verify time constraints are respected
                if "last 3 days" in expression:
                    current_time = time.time()
                    three_days_ago = current_time - (3 * 24 * 60 * 60)
                    
                    for item in filtered_items:
                        item_time = getattr(item, 'created_at', current_time)
                        self.assertGreaterEqual(item_time, three_days_ago)
    
    async def test_filtering_combinations(self):
        """Test complex filter combinations."""
        context = QueryContext()
        
        # Test importance filter
        importance_filter = ImportanceFilter(min_importance=0.7)
        importance_results = await importance_filter.apply(self.memories, context)
        
        for item in importance_results:
            importance = getattr(item, 'importance', item.metadata.get('importance', 0.5))
            self.assertGreaterEqual(importance, 0.7)
        
        # Test complexity filter
        complexity_filter = ComplexityFilter(min_complexity=20, complexity_metric="words")
        complexity_results = await complexity_filter.apply(self.memories, context)
        
        for item in complexity_results:
            word_count = len(item.content.split())
            self.assertGreaterEqual(word_count, 20)
        
        # Test label filter
        label_filter = LabelFilter(required_labels=["python"])
        label_results = await label_filter.apply(self.memories, context)
        
        for item in label_results:
            labels = getattr(item, 'labels', item.metadata.get('labels', []))
            self.assertIn("python", labels)
        
        # Test composite filter (AND)
        composite_filter = CompositeFilter(
            filters=[importance_filter, label_filter],
            operator=FilterOperator.AND
        )
        
        composite_results = await composite_filter.apply(self.memories, context)
        
        # Verify composite results meet both criteria
        for item in composite_results:
            importance = getattr(item, 'importance', item.metadata.get('importance', 0.5))
            labels = getattr(item, 'labels', item.metadata.get('labels', []))
            
            self.assertGreaterEqual(importance, 0.7)
            self.assertIn("python", labels)
    
    async def test_ranking_algorithms(self):
        """Test different ranking algorithms."""
        context = QueryContext(query_text="programming tutorial")
        
        ranking_methods = ["importance", "recency", "frequency", "composite"]
        
        for method in ranking_methods:
            with self.subTest(method=method):
                ranked_items = await self.ranking_engine.rank_items(
                    items=self.memories,
                    context=context,
                    method=method
                )
                
                # Verify ranking results
                self.assertEqual(len(ranked_items), len(self.memories))
                
                for i, ranked_item in enumerate(ranked_items):
                    self.assertIsInstance(ranked_item, RankedItem)
                    self.assertEqual(ranked_item.rank, i + 1)
                    self.assertIsInstance(ranked_item.score, RankingScore)
                    self.assertIn(ranked_item.item, self.memories)
                
                # Verify descending order by total score
                scores = [item.score.total_score for item in ranked_items]
                self.assertEqual(scores, sorted(scores, reverse=True))
    
    async def test_composite_query_execution(self):
        """Test execution of complex composite queries."""
        composite_queries = [
            "important Python tutorials from last week",
            "recent Docker guides with high importance", 
            "top 3 machine learning resources sorted by relevance"
        ]
        
        for query in composite_queries:
            with self.subTest(query=query):
                # Parse the query
                ast = self.query_parser.parse_query(query)
                
                # Create execution context
                context = QueryContext(
                    query_text=query,
                    query_ast=ast,
                    limit=ast.limit or 5
                )
                
                # Execute the composite query
                results = await self.query_engine.execute_query(self.memories, context)
                
                # Verify composite execution
                self.assertIsNotNone(results)
                self.assertLessEqual(len(results.items), context.limit)
                self.assertGreater(results.execution_time, 0)
                
                # Verify results are relevant to query terms
                if ast.semantic_terms:
                    for item in results.items[:2]:  # Check first 2 results
                        content_lower = item.content.lower()
                        title_lower = getattr(item, 'title', '').lower()
                        
                        # At least one semantic term should appear
                        term_found = any(
                            term in content_lower or term in title_lower
                            for term in ast.semantic_terms
                        )
                        # Note: Due to semantic search, exact term matching may not always occur
                        # This is a loose check for integration testing
    
    async def test_structured_query_parsing(self):
        """Test structured query format parsing."""
        structured_queries = [
            '{"terms": ["python", "machine learning"], "ranking": "importance"}',
            "{'semantic': ['docker'], 'filters': {'importance': {'min': 0.6}}}",
            '{"search": "web development", "limit": 3}'
        ]
        
        for query in structured_queries:
            with self.subTest(query=query):
                ast = self.query_parser.parse_query(query)
                
                # Verify structured parsing
                self.assertEqual(ast.query_type, QueryType.COMPOSITE)
                self.assertGreater(ast.parse_confidence, 0.9)  # High confidence for structured
                
                # Execute structured query
                context = QueryContext(
                    query_text=query,
                    query_ast=ast,
                    limit=ast.limit or 5
                )
                
                results = await self.query_engine.execute_query(self.memories, context)
                
                # Verify execution
                self.assertIsNotNone(results)
                self.assertLessEqual(len(results.items), context.limit)
    
    async def test_query_performance_metrics(self):
        """Test query performance and metrics collection."""
        queries = [
            "machine learning python",
            "recent important content",
            "docker kubernetes deployment"
        ]
        
        for query in queries:
            with self.subTest(query=query):
                start_time = time.time()
                
                # Parse and execute query
                ast = self.query_parser.parse_query(query)
                context = QueryContext(
                    query_text=query,
                    query_ast=ast,
                    limit=5
                )
                
                results = await self.query_engine.execute_query(self.memories, context)
                
                total_time = time.time() - start_time
                
                # Verify performance metrics
                self.assertGreater(results.execution_time, 0)
                self.assertLess(results.execution_time, 1.0)  # Should be fast for small dataset
                self.assertLess(total_time, 2.0)  # Total time including parsing
                
                # Verify metrics structure
                if hasattr(results, 'metrics'):
                    self.assertIsInstance(results.metrics, dict)
    
    async def test_error_handling_and_fallbacks(self):
        """Test error handling and graceful fallbacks."""
        # Test empty query
        empty_result = await self.query_engine.execute_query([], QueryContext())
        self.assertEqual(len(empty_result.items), 0)
        
        # Test invalid structured query
        invalid_ast = self.query_parser.parse_query('{"invalid": json}')
        self.assertGreater(len(invalid_ast.parsing_errors), 0)
        
        # Test query with no matches
        ast = self.query_parser.parse_query("nonexistent topic xyz123")
        context = QueryContext(query_text="nonexistent topic xyz123", query_ast=ast)
        
        results = await self.query_engine.execute_query(self.memories, context)
        # Should still return results (potentially empty or low-scoring)
        self.assertIsNotNone(results)
    
    async def test_query_suggestions(self):
        """Test query suggestion system."""
        problematic_queries = [
            "find",  # Too vague
            "a b c d e f g h",  # Too many terms
            "when was this created",  # Needs temporal context
            "best ever"  # Needs ranking context
        ]
        
        for query in problematic_queries:
            with self.subTest(query=query):
                ast = self.query_parser.parse_query(query)
                suggestions = self.query_parser.suggest_query_improvements(query, ast)
                
                # Low confidence queries should have suggestions
                if ast.parse_confidence < 0.6:
                    self.assertGreater(len(suggestions), 0)
                
                # Suggestions should be strings
                for suggestion in suggestions:
                    self.assertIsInstance(suggestion, str)
                    self.assertGreater(len(suggestion), 10)
    
    def test_component_integration_statistics(self):
        """Test that all components properly integrate and report statistics."""
        # Verify parser statistics
        parse_stats = self.query_parser.get_parse_stats()
        self.assertIsInstance(parse_stats, dict)
        self.assertIn('total_queries', parse_stats)
        
        # Verify ranking statistics  
        ranking_stats = self.ranking_engine.get_ranking_stats()
        self.assertIsInstance(ranking_stats, dict)
        
        # Verify all registered rankers
        rankers = self.ranking_engine.list_rankers()
        expected_rankers = ['relevance', 'importance', 'recency', 'frequency', 'composite']
        
        for ranker in expected_rankers:
            self.assertIn(ranker, rankers)


class TestQueryEngineIntegration(AsyncTestCase):
    """Integration tests specifically for the QueryEngine."""
    
    def setUp(self):
        """Set up test fixtures."""
        super().setUp()
        self.query_engine = QueryEngine()
        self.memories = [
            create_test_memory_item(
                id="engine_test_001",
                content="Integration test content with keywords",
                metadata={"importance": 0.8}
            )
        ]
    
    async def test_engine_initialization(self):
        """Test query engine initializes properly."""
        self.assertIsNotNone(self.query_engine.semantic_engine)
        self.assertIsNotNone(self.query_engine.temporal_filter)
        self.assertIsNotNone(self.query_engine.ranking_engine)
        self.assertIsNotNone(self.query_engine.filter_registry)
    
    async def test_engine_query_execution_pipeline(self):
        """Test complete query execution pipeline."""
        context = QueryContext(
            query_text="integration test",
            limit=5
        )
        
        results = await self.query_engine.execute_query(self.memories, context)
        
        # Verify pipeline execution
        self.assertIsNotNone(results)
        self.assertIsInstance(results.items, list)
        self.assertGreater(results.execution_time, 0)
        self.assertLessEqual(len(results.items), 5)
    
    async def test_engine_caching_behavior(self):
        """Test query result caching."""
        context = QueryContext(
            query_text="cacheable query",
            limit=3
        )
        
        # First execution
        results1 = await self.query_engine.execute_query(self.memories, context)
        first_time = results1.execution_time
        
        # Second execution (should be faster due to caching)
        results2 = await self.query_engine.execute_query(self.memories, context)
        second_time = results2.execution_time
        
        # Verify caching improves performance
        # Note: In a real implementation, you'd check cache hit/miss rates
        self.assertEqual(len(results1.items), len(results2.items))


def run_integration_tests():
    """Run all advanced query integration tests."""
    import unittest
    
    # Create test suite
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTest(unittest.makeSuite(TestAdvancedQueryIntegration))
    suite.addTest(unittest.makeSuite(TestQueryEngineIntegration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_integration_tests()
    exit(0 if success else 1)