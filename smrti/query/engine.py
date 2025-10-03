"""
smrti/query/engine.py - Core Query Engine

Main query orchestration engine that coordinates semantic search, temporal filtering,
importance ranking, and complex query processing for the Smrti memory system.
"""

from __future__ import annotations

import time
import asyncio
from typing import Dict, List, Optional, Any, Union, Tuple, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import threading
from concurrent.futures import ThreadPoolExecutor, Future

from ..models.base import MemoryItem
from ..models.tiers import MemoryTier


@dataclass
class QueryStats:
    """Statistics about query execution."""
    
    query_id: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    
    # Search metrics
    total_items_searched: int = 0
    items_filtered: int = 0
    items_ranked: int = 0
    items_returned: int = 0
    
    # Performance metrics
    semantic_search_ms: float = 0.0
    temporal_filter_ms: float = 0.0
    importance_filter_ms: float = 0.0
    ranking_ms: float = 0.0
    
    # Cache metrics
    cache_hits: int = 0
    cache_misses: int = 0
    
    # Error information
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def complete(self) -> None:
        """Mark the query as completed and calculate duration."""
        if self.end_time is None:
            self.end_time = time.time()
            self.duration_ms = (self.end_time - self.start_time) * 1000
    
    def add_error(self, error: str) -> None:
        """Add an error to the stats."""
        self.errors.append(error)
    
    def add_warning(self, warning: str) -> None:
        """Add a warning to the stats."""
        self.warnings.append(warning)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            'query_id': self.query_id,
            'duration_ms': self.duration_ms,
            'performance': {
                'total_items_searched': self.total_items_searched,
                'items_filtered': self.items_filtered,
                'items_ranked': self.items_ranked,
                'items_returned': self.items_returned,
                'semantic_search_ms': self.semantic_search_ms,
                'temporal_filter_ms': self.temporal_filter_ms,
                'importance_filter_ms': self.importance_filter_ms,
                'ranking_ms': self.ranking_ms
            },
            'cache': {
                'hits': self.cache_hits,
                'misses': self.cache_misses,
                'hit_rate': self.cache_hits / max(1, self.cache_hits + self.cache_misses)
            },
            'issues': {
                'errors': self.errors,
                'warnings': self.warnings
            }
        }


@dataclass 
class QueryContext:
    """Context information for query execution."""
    
    query_id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    
    # Query options
    max_results: int = 100
    timeout_seconds: float = 30.0
    include_stats: bool = True
    
    # Caching options
    use_cache: bool = True
    cache_ttl_seconds: int = 300  # 5 minutes
    
    # Processing options
    parallel_processing: bool = True
    max_workers: int = 4
    
    # Debug options
    debug_mode: bool = False
    trace_execution: bool = False
    
    def with_timeout(self, timeout: float) -> QueryContext:
        """Create a copy with modified timeout."""
        ctx = QueryContext(**self.__dict__)
        ctx.timeout_seconds = timeout
        return ctx
    
    def with_max_results(self, max_results: int) -> QueryContext:
        """Create a copy with modified max results."""
        ctx = QueryContext(**self.__dict__)
        ctx.max_results = max_results
        return ctx


@dataclass
class QueryResult:
    """Result from a query execution."""
    
    query_id: str
    items: List[MemoryItem]
    total_matches: int
    stats: Optional[QueryStats] = None
    
    # Result metadata
    has_more: bool = False
    next_cursor: Optional[str] = None
    
    # Ranking information
    ranking_scores: Dict[str, float] = field(default_factory=dict)
    ranking_explanations: Dict[str, List[str]] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize derived fields."""
        if self.stats:
            self.stats.items_returned = len(self.items)
    
    @property
    def execution_time_ms(self) -> Optional[float]:
        """Get execution time in milliseconds."""
        return self.stats.duration_ms if self.stats else None
    
    def get_score(self, item_id: str) -> Optional[float]:
        """Get ranking score for an item."""
        return self.ranking_scores.get(item_id)
    
    def get_explanation(self, item_id: str) -> List[str]:
        """Get ranking explanation for an item."""
        return self.ranking_explanations.get(item_id, [])
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            'query_id': self.query_id,
            'items': [item.to_dict() for item in self.items],
            'total_matches': self.total_matches,
            'has_more': self.has_more,
            'next_cursor': self.next_cursor,
            'stats': self.stats.to_dict() if self.stats else None,
            'ranking_info': {
                'scores': self.ranking_scores,
                'explanations': self.ranking_explanations
            }
        }


class QueryExecutor(ABC):
    """Abstract base class for query execution components."""
    
    @abstractmethod
    async def execute(self, items: List[MemoryItem], context: QueryContext, 
                     stats: QueryStats) -> List[MemoryItem]:
        """Execute this component of the query pipeline.
        
        Args:
            items: Input memory items
            context: Query execution context
            stats: Statistics object to update
            
        Returns:
            Processed memory items
        """
        pass


class QueryEngine:
    """Main query engine that orchestrates all query operations."""
    
    def __init__(self):
        """Initialize the query engine."""
        # Component references (will be set during initialization)
        self.semantic_engine = None
        self.temporal_filter = None
        self.filters = {}
        self.ranking_engine = None
        self.parser = None
        
        # Query cache
        self._query_cache: Dict[str, Tuple[QueryResult, float]] = {}
        self._cache_lock = threading.Lock()
        
        # Execution tracking
        self._active_queries: Dict[str, Future] = {}
        self._executor = ThreadPoolExecutor(max_workers=8)
        
        # Metrics
        self._query_count = 0
        self._total_execution_time = 0.0
        
    def register_semantic_engine(self, engine) -> None:
        """Register the semantic search engine."""
        self.semantic_engine = engine
        
    def register_temporal_filter(self, filter_obj) -> None:
        """Register the temporal filter."""
        self.temporal_filter = filter_obj
        
    def register_filter(self, name: str, filter_obj) -> None:
        """Register a named filter."""
        self.filters[name] = filter_obj
        
    def register_ranking_engine(self, engine) -> None:
        """Register the ranking engine."""
        self.ranking_engine = engine
        
    def register_parser(self, parser) -> None:
        """Register the query parser."""
        self.parser = parser
    
    async def execute_query(self, query: str, memory_tiers: List[MemoryTier], 
                           context: Optional[QueryContext] = None) -> QueryResult:
        """Execute a complete query across memory tiers.
        
        Args:
            query: Query string to execute
            memory_tiers: Memory tiers to search
            context: Query execution context
            
        Returns:
            Query execution result
        """
        if context is None:
            context = QueryContext(query_id=f"query_{int(time.time() * 1000)}")
        
        # Initialize statistics
        stats = QueryStats(
            query_id=context.query_id,
            start_time=time.time()
        )
        
        try:
            # Check cache first
            if context.use_cache:
                cached_result = self._get_cached_result(query, context)
                if cached_result:
                    stats.cache_hits += 1
                    stats.complete()
                    cached_result.stats = stats
                    return cached_result
                else:
                    stats.cache_misses += 1
            
            # Parse query if parser is available
            parsed_query = None
            if self.parser:
                try:
                    parsed_query = self.parser.parse(query)
                except Exception as e:
                    stats.add_error(f"Query parsing failed: {str(e)}")
            
            # Collect all items from memory tiers
            all_items = []
            for tier in memory_tiers:
                tier_items = await self._get_tier_items(tier)
                all_items.extend(tier_items)
            
            stats.total_items_searched = len(all_items)
            
            # Execute query pipeline
            result_items = await self._execute_pipeline(
                query, all_items, parsed_query, context, stats
            )
            
            # Create result
            result = QueryResult(
                query_id=context.query_id,
                items=result_items[:context.max_results],
                total_matches=len(result_items),
                has_more=len(result_items) > context.max_results,
                stats=stats
            )
            
            # Cache result if appropriate
            if context.use_cache and not stats.errors:
                self._cache_result(query, result, context)
            
            stats.complete()
            self._update_metrics(stats)
            
            return result
            
        except asyncio.TimeoutError:
            stats.add_error("Query execution timed out")
            stats.complete()
            return QueryResult(
                query_id=context.query_id,
                items=[],
                total_matches=0,
                stats=stats
            )
        except Exception as e:
            stats.add_error(f"Query execution failed: {str(e)}")
            stats.complete()
            return QueryResult(
                query_id=context.query_id,
                items=[],
                total_matches=0,
                stats=stats
            )
    
    async def _execute_pipeline(self, query: str, items: List[MemoryItem], 
                               parsed_query, context: QueryContext, 
                               stats: QueryStats) -> List[MemoryItem]:
        """Execute the complete query pipeline.
        
        Args:
            query: Original query string
            items: Input memory items
            parsed_query: Parsed query AST (if available)
            context: Query execution context
            stats: Statistics object
            
        Returns:
            Processed and ranked items
        """
        current_items = items
        
        # 1. Semantic search filtering
        if self.semantic_engine and query.strip():
            start_time = time.time()
            try:
                current_items = await self.semantic_engine.search(
                    query, current_items, context.max_results * 2  # Get more for ranking
                )
                stats.semantic_search_ms = (time.time() - start_time) * 1000
                stats.items_filtered += len(items) - len(current_items)
            except Exception as e:
                stats.add_error(f"Semantic search failed: {str(e)}")
        
        # 2. Apply temporal filters
        if self.temporal_filter and parsed_query:
            start_time = time.time()
            try:
                current_items = await self.temporal_filter.apply(
                    current_items, parsed_query, context
                )
                stats.temporal_filter_ms = (time.time() - start_time) * 1000
            except Exception as e:
                stats.add_error(f"Temporal filtering failed: {str(e)}")
        
        # 3. Apply other filters
        if parsed_query and self.filters:
            start_time = time.time()
            try:
                current_items = await self._apply_filters(
                    current_items, parsed_query, context
                )
                stats.importance_filter_ms = (time.time() - start_time) * 1000
            except Exception as e:
                stats.add_error(f"Filter application failed: {str(e)}")
        
        # 4. Rank results
        if self.ranking_engine and current_items:
            start_time = time.time()
            try:
                current_items = await self.ranking_engine.rank(
                    current_items, query, context
                )
                stats.ranking_ms = (time.time() - start_time) * 1000
                stats.items_ranked = len(current_items)
            except Exception as e:
                stats.add_error(f"Ranking failed: {str(e)}")
        
        return current_items
    
    async def _get_tier_items(self, tier: MemoryTier) -> List[MemoryItem]:
        """Get all items from a memory tier.
        
        Args:
            tier: Memory tier to query
            
        Returns:
            List of memory items from the tier
        """
        try:
            # This would interface with the actual memory tier implementation
            # For now, return a placeholder implementation
            return getattr(tier, 'items', [])
        except Exception:
            return []
    
    async def _apply_filters(self, items: List[MemoryItem], parsed_query, 
                           context: QueryContext) -> List[MemoryItem]:
        """Apply configured filters to items.
        
        Args:
            items: Input memory items
            parsed_query: Parsed query AST
            context: Query execution context
            
        Returns:
            Filtered memory items
        """
        current_items = items
        
        # Apply each registered filter
        for filter_name, filter_obj in self.filters.items():
            try:
                if hasattr(filter_obj, 'should_apply'):
                    if not filter_obj.should_apply(parsed_query):
                        continue
                
                current_items = await filter_obj.apply(current_items, context)
            except Exception as e:
                # Log error but continue with other filters
                continue
        
        return current_items
    
    def _get_cached_result(self, query: str, context: QueryContext) -> Optional[QueryResult]:
        """Get cached query result if available and valid.
        
        Args:
            query: Query string
            context: Query execution context
            
        Returns:
            Cached result or None
        """
        cache_key = self._make_cache_key(query, context)
        
        with self._cache_lock:
            if cache_key in self._query_cache:
                result, timestamp = self._query_cache[cache_key]
                
                # Check if cache entry is still valid
                if time.time() - timestamp < context.cache_ttl_seconds:
                    # Create a copy with new query ID
                    cached_result = QueryResult(
                        query_id=context.query_id,
                        items=result.items,
                        total_matches=result.total_matches,
                        has_more=result.has_more,
                        ranking_scores=result.ranking_scores.copy(),
                        ranking_explanations=result.ranking_explanations.copy()
                    )
                    return cached_result
                else:
                    # Remove expired entry
                    del self._query_cache[cache_key]
        
        return None
    
    def _cache_result(self, query: str, result: QueryResult, context: QueryContext) -> None:
        """Cache a query result.
        
        Args:
            query: Query string
            result: Query result to cache
            context: Query execution context
        """
        cache_key = self._make_cache_key(query, context)
        
        with self._cache_lock:
            self._query_cache[cache_key] = (result, time.time())
            
            # Clean up old cache entries if cache gets too large
            if len(self._query_cache) > 1000:
                self._cleanup_cache()
    
    def _make_cache_key(self, query: str, context: QueryContext) -> str:
        """Create a cache key for a query.
        
        Args:
            query: Query string
            context: Query execution context
            
        Returns:
            Cache key string
        """
        # Include relevant context parameters in the key
        key_parts = [
            query,
            str(context.max_results),
            str(context.user_id or ""),
            # Add other relevant context parameters as needed
        ]
        return "|".join(key_parts)
    
    def _cleanup_cache(self) -> None:
        """Clean up expired cache entries."""
        current_time = time.time()
        expired_keys = []
        
        for key, (result, timestamp) in self._query_cache.items():
            if current_time - timestamp > 3600:  # 1 hour max age
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._query_cache[key]
    
    def _update_metrics(self, stats: QueryStats) -> None:
        """Update engine metrics.
        
        Args:
            stats: Query statistics
        """
        self._query_count += 1
        if stats.duration_ms:
            self._total_execution_time += stats.duration_ms
    
    def get_engine_stats(self) -> Dict[str, Any]:
        """Get engine performance statistics.
        
        Returns:
            Dictionary with engine statistics
        """
        avg_execution_time = (
            self._total_execution_time / max(1, self._query_count)
        )
        
        return {
            'total_queries': self._query_count,
            'total_execution_time_ms': self._total_execution_time,
            'average_execution_time_ms': avg_execution_time,
            'active_queries': len(self._active_queries),
            'cache_size': len(self._query_cache),
            'registered_components': {
                'semantic_engine': self.semantic_engine is not None,
                'temporal_filter': self.temporal_filter is not None,
                'filters': len(self.filters),
                'ranking_engine': self.ranking_engine is not None,
                'parser': self.parser is not None
            }
        }
    
    async def shutdown(self) -> None:
        """Shutdown the query engine and clean up resources."""
        # Cancel active queries
        for future in self._active_queries.values():
            future.cancel()
        
        # Shutdown executor
        self._executor.shutdown(wait=True)
        
        # Clear cache
        with self._cache_lock:
            self._query_cache.clear()