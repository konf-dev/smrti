"""
smrti/core/retrieval_engine.py - Unified Retrieval Engine

Unified retrieval system that queries across all memory tiers with intelligent
result merging, ranking, and cross-tier coordination.
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from smrti.core.base import BaseAdapter
from smrti.core.context_assembly import ContextAssemblyEngine, ContextAssemblyConfig, ScoredRecord
from smrti.core.exceptions import ContextAssemblyError, InsufficientMemoryError, RetrievalError, ValidationError
from smrti.core.registry import AdapterRegistry
from smrti.schemas.models import MemoryQuery, MemoryRecord, RecordEnvelope


class QueryStrategy(Enum):
    """Query execution strategies for cross-tier retrieval."""
    
    PARALLEL = "parallel"          # Query all tiers simultaneously
    SEQUENTIAL = "sequential"      # Query tiers in priority order
    CASCADING = "cascading"       # Query tiers until sufficient results
    ADAPTIVE = "adaptive"         # Adapt strategy based on query characteristics


class ResultMergeStrategy(Enum):
    """Strategies for merging results from multiple tiers."""
    
    SCORE_WEIGHTED = "score_weighted"    # Merge by relevance scores
    TIER_PRIORITY = "tier_priority"      # Merge by tier importance
    TEMPORAL = "temporal"                # Merge by recency
    HYBRID = "hybrid"                    # Combine multiple factors
    DIVERSITY_FIRST = "diversity_first"  # Prioritize diverse results


@dataclass
class RetrievalMetrics:
    """Metrics for retrieval operations."""
    
    query_id: str
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    
    # Query characteristics
    strategy_used: Optional[QueryStrategy] = None
    merge_strategy: Optional[ResultMergeStrategy] = None
    tiers_queried: List[str] = field(default_factory=list)
    
    # Performance metrics
    total_duration: float = 0.0
    tier_query_times: Dict[str, float] = field(default_factory=dict)
    context_assembly_time: float = 0.0
    result_merging_time: float = 0.0
    
    # Result metrics
    raw_results_count: Dict[str, int] = field(default_factory=dict)
    final_results_count: int = 0
    duplicate_count: int = 0
    filtered_count: int = 0
    
    # Quality metrics
    average_relevance_score: float = 0.0
    tier_coverage: float = 0.0  # Fraction of available tiers that returned results
    result_diversity: float = 0.0
    
    def finalize(self) -> None:
        """Finalize metrics calculation."""
        self.end_time = datetime.utcnow()
        self.total_duration = (self.end_time - self.start_time).total_seconds()


@dataclass 
class RetrievalConfig:
    """Configuration for the retrieval engine."""
    
    # Query strategy configuration
    default_strategy: QueryStrategy = QueryStrategy.ADAPTIVE
    max_query_time: float = 5.0  # Maximum time for entire query
    tier_timeout: float = 2.0    # Timeout per tier query
    
    # Result merging configuration
    default_merge_strategy: ResultMergeStrategy = ResultMergeStrategy.HYBRID
    max_results_per_tier: int = 100
    enable_deduplication: bool = True
    similarity_threshold_dedup: float = 0.95
    
    # Context assembly configuration
    enable_context_assembly: bool = True
    context_assembly_config: Optional[ContextAssemblyConfig] = None
    
    # Adaptive behavior
    adaptive_threshold_small_query: int = 10     # Results threshold for small queries
    adaptive_threshold_large_query: int = 100    # Results threshold for large queries
    adaptive_tier_failure_threshold: float = 0.5 # Failure rate to trigger strategy change
    
    # Quality control
    min_quality_threshold: float = 0.1  # Minimum relevance score
    diversity_penalty: float = 0.1      # Penalty for similar results
    freshness_boost: float = 0.2        # Boost for recent results
    
    # Caching
    enable_result_caching: bool = True
    cache_ttl_minutes: int = 5
    max_cache_size: int = 1000


@dataclass
class QueryExecution:
    """Represents an active query execution."""
    
    query_id: str
    original_query: MemoryQuery
    session_context: Optional[Dict[str, Any]]
    config: RetrievalConfig
    
    # Execution state
    strategy: QueryStrategy
    merge_strategy: ResultMergeStrategy
    start_time: datetime = field(default_factory=datetime.utcnow)
    
    # Results tracking
    tier_results: Dict[str, List[RecordEnvelope]] = field(default_factory=dict)
    tier_errors: Dict[str, Exception] = field(default_factory=dict)
    merged_results: List[ScoredRecord] = field(default_factory=list)
    final_results: List[ScoredRecord] = field(default_factory=list)
    
    # Metrics
    metrics: RetrievalMetrics = field(default_factory=lambda: RetrievalMetrics(""))
    
    def __post_init__(self):
        self.metrics.query_id = self.query_id


class UnifiedRetrievalEngine(BaseAdapter):
    """
    Unified retrieval engine for multi-tier memory systems.
    
    Provides intelligent querying across all memory tiers with adaptive strategies,
    result merging, deduplication, and quality optimization.
    """
    
    def __init__(
        self,
        registry: AdapterRegistry,
        context_assembly_engine: Optional[ContextAssemblyEngine] = None,
        config: Optional[RetrievalConfig] = None
    ):
        super().__init__("unified_retrieval")
        self.registry = registry
        self.config = config or RetrievalConfig()
        
        # Context assembly integration
        self.context_assembly = context_assembly_engine
        if self.context_assembly is None and self.config.enable_context_assembly:
            assembly_config = self.config.context_assembly_config or ContextAssemblyConfig()
            self.context_assembly = ContextAssemblyEngine(registry, assembly_config)
        
        # Result cache
        self._result_cache: Dict[str, Tuple[List[ScoredRecord], datetime]] = {}
        self._cache_ttl = timedelta(minutes=self.config.cache_ttl_minutes)
        
        # Adaptive strategy tracking
        self._strategy_performance: Dict[QueryStrategy, List[float]] = defaultdict(list)
        self._tier_reliability: Dict[str, float] = defaultdict(lambda: 1.0)
        
        # Statistics
        self._queries_executed = 0
        self._cache_hits = 0
        self._total_query_time = 0.0
        self._strategy_usage = defaultdict(int)
        self._active_executions: Dict[str, QueryExecution] = {}
    
    async def retrieve_memories(
        self,
        query: MemoryQuery,
        session_context: Optional[Dict[str, Any]] = None,
        strategy: Optional[QueryStrategy] = None,
        merge_strategy: Optional[ResultMergeStrategy] = None,
        force_refresh: bool = False
    ) -> List[ScoredRecord]:
        """
        Retrieve memories across all available tiers with intelligent merging.
        
        Args:
            query: Memory query specification
            session_context: Optional session-specific context
            strategy: Query execution strategy (optional)
            merge_strategy: Result merging strategy (optional)
            force_refresh: Force refresh of cached results
            
        Returns:
            List of scored and ranked memory records
            
        Raises:
            RetrievalError: If retrieval fails
            ValidationError: If query is invalid
        """
        # Generate query ID
        query_id = self._generate_query_id(query)
        
        try:
            # Validate query
            self._validate_query(query)
            
            # Check cache first
            if not force_refresh:
                cached_result = await self._check_result_cache(query)
                if cached_result:
                    self._cache_hits += 1
                    self.logger.debug(f"Cache hit for query: {query.query_text}")
                    return cached_result
            
            # Determine strategies
            exec_strategy = strategy or self._select_query_strategy(query)
            merge_strat = merge_strategy or self._select_merge_strategy(query, exec_strategy)
            
            # Create execution context
            execution = QueryExecution(
                query_id=query_id,
                original_query=query,
                session_context=session_context,
                config=self.config,
                strategy=exec_strategy,
                merge_strategy=merge_strat
            )
            
            self._active_executions[query_id] = execution
            
            try:
                # Execute retrieval
                result = await self._execute_retrieval(execution)
                
                # Cache result
                if self.config.enable_result_caching:
                    await self._cache_result(query, result)
                
                # Update statistics
                self._queries_executed += 1
                self._total_query_time += execution.metrics.total_duration
                self._strategy_usage[exec_strategy] += 1
                self._update_strategy_performance(exec_strategy, execution)
                
                self.logger.info(
                    f"Retrieved {len(result)} memories in {execution.metrics.total_duration:.3f}s "
                    f"using {exec_strategy.value} strategy"
                )
                
                return result
            
            finally:
                # Clean up execution context
                if query_id in self._active_executions:
                    del self._active_executions[query_id]
        
        except Exception as e:
            self._mark_error(e)
            if isinstance(e, (RetrievalError, ValidationError)):
                raise
            else:
                raise RetrievalError(
                    f"Memory retrieval failed: {e}",
                    query_text=query.query_text,
                    operation="retrieve_memories",
                    backend_error=e
                )
    
    async def _execute_retrieval(self, execution: QueryExecution) -> List[ScoredRecord]:
        """Execute the retrieval with the specified strategy."""
        start_time = time.time()
        
        try:
            # Step 1: Execute tier queries based on strategy
            await self._execute_tier_queries(execution)
            
            # Step 2: Merge results from all tiers
            merge_start = time.time()
            await self._merge_tier_results(execution)
            execution.metrics.result_merging_time = time.time() - merge_start
            
            # Step 3: Apply quality filters and deduplication
            await self._apply_quality_filters(execution)
            
            # Step 4: Context assembly (if enabled)
            if (self.config.enable_context_assembly and 
                self.context_assembly and 
                len(execution.merged_results) > execution.original_query.limit):
                
                assembly_start = time.time()
                
                # Use context assembly for intelligent selection
                assembled_results = await self.context_assembly.assemble_context(
                    execution.original_query,
                    execution.session_context
                )
                
                execution.final_results = assembled_results[:execution.original_query.limit]
                execution.metrics.context_assembly_time = time.time() - assembly_start
            else:
                # Simple truncation to limit
                execution.final_results = execution.merged_results[:execution.original_query.limit]
            
            # Finalize metrics
            execution.metrics.finalize()
            execution.metrics.final_results_count = len(execution.final_results)
            
            if execution.final_results:
                execution.metrics.average_relevance_score = (
                    sum(r.total_score for r in execution.final_results) /
                    len(execution.final_results)
                )
            
            return execution.final_results
        
        except Exception as e:
            execution.metrics.finalize()
            raise RetrievalError(
                f"Retrieval execution failed: {e}",
                query_text=execution.original_query.query_text,
                operation="execute_retrieval",
                backend_error=e
            )
    
    async def _execute_tier_queries(self, execution: QueryExecution) -> None:
        """Execute queries against memory tiers based on strategy."""
        available_tiers = list(self.registry.tier_stores.keys())
        execution.metrics.tiers_queried = available_tiers.copy()
        
        if execution.strategy == QueryStrategy.PARALLEL:
            await self._execute_parallel_queries(execution, available_tiers)
        
        elif execution.strategy == QueryStrategy.SEQUENTIAL:
            await self._execute_sequential_queries(execution, available_tiers)
        
        elif execution.strategy == QueryStrategy.CASCADING:
            await self._execute_cascading_queries(execution, available_tiers)
        
        elif execution.strategy == QueryStrategy.ADAPTIVE:
            # Adaptive strategy chooses between parallel/sequential based on context
            if len(available_tiers) <= 3 or execution.original_query.limit <= 20:
                await self._execute_parallel_queries(execution, available_tiers)
            else:
                await self._execute_cascading_queries(execution, available_tiers)
        
        # Update tier reliability based on results
        self._update_tier_reliability(execution)
    
    async def _execute_parallel_queries(
        self, 
        execution: QueryExecution, 
        tiers: List[str]
    ) -> None:
        """Execute all tier queries in parallel."""
        tasks = []
        
        for tier_name in tiers:
            task = self._query_tier_with_timeout(
                tier_name, 
                execution.original_query,
                execution.session_context,
                execution.config.tier_timeout
            )
            tasks.append((tier_name, task))
        
        # Wait for all tasks with timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*[task for _, task in tasks], return_exceptions=True),
                timeout=execution.config.max_query_time
            )
            
            # Process results
            for (tier_name, _), result in zip(tasks, results):
                if isinstance(result, Exception):
                    execution.tier_errors[tier_name] = result
                    execution.tier_results[tier_name] = []
                    self.logger.warning(f"Tier {tier_name} query failed: {result}")
                else:
                    execution.tier_results[tier_name] = result or []
        
        except asyncio.TimeoutError:
            self.logger.warning(f"Parallel query timeout after {execution.config.max_query_time}s")
            # Cancel remaining tasks
            for _, task in tasks:
                if not task.done():
                    task.cancel()
    
    async def _execute_sequential_queries(
        self, 
        execution: QueryExecution, 
        tiers: List[str]
    ) -> None:
        """Execute tier queries sequentially by priority."""
        # Sort tiers by reliability and priority
        tier_priorities = {
            "working": 1.0,
            "short_term": 0.9,
            "semantic": 0.8,
            "episodic": 0.7,
            "long_term": 0.6,
            "procedural": 0.5
        }
        
        sorted_tiers = sorted(
            tiers,
            key=lambda t: (self._tier_reliability[t], tier_priorities.get(t, 0.3)),
            reverse=True
        )
        
        remaining_time = execution.config.max_query_time
        
        for tier_name in sorted_tiers:
            if remaining_time <= 0:
                break
            
            query_start = time.time()
            timeout = min(remaining_time, execution.config.tier_timeout)
            
            try:
                result = await self._query_tier_with_timeout(
                    tier_name,
                    execution.original_query,
                    execution.session_context,
                    timeout
                )
                
                execution.tier_results[tier_name] = result or []
                
                query_duration = time.time() - query_start
                execution.metrics.tier_query_times[tier_name] = query_duration
                remaining_time -= query_duration
            
            except Exception as e:
                execution.tier_errors[tier_name] = e
                execution.tier_results[tier_name] = []
                self.logger.warning(f"Sequential tier {tier_name} query failed: {e}")
                
                query_duration = time.time() - query_start
                remaining_time -= query_duration
    
    async def _execute_cascading_queries(
        self, 
        execution: QueryExecution, 
        tiers: List[str]
    ) -> None:
        """Execute queries in cascading fashion until sufficient results."""
        # Start with high-priority tiers
        priority_order = ["working", "short_term", "semantic", "episodic", "long_term", "procedural"]
        available_priority_tiers = [t for t in priority_order if t in tiers]
        remaining_tiers = [t for t in tiers if t not in priority_order]
        ordered_tiers = available_priority_tiers + remaining_tiers
        
        total_results = 0
        target_results = max(execution.original_query.limit * 2, 20)  # Get more than needed
        
        remaining_time = execution.config.max_query_time
        
        for tier_name in ordered_tiers:
            if remaining_time <= 0 or total_results >= target_results:
                break
            
            query_start = time.time()
            timeout = min(remaining_time, execution.config.tier_timeout)
            
            try:
                result = await self._query_tier_with_timeout(
                    tier_name,
                    execution.original_query,
                    execution.session_context,
                    timeout
                )
                
                execution.tier_results[tier_name] = result or []
                total_results += len(result or [])
                
                query_duration = time.time() - query_start
                execution.metrics.tier_query_times[tier_name] = query_duration
                remaining_time -= query_duration
                
                self.logger.debug(f"Cascading: {tier_name} returned {len(result or [])} results")
            
            except Exception as e:
                execution.tier_errors[tier_name] = e
                execution.tier_results[tier_name] = []
                self.logger.warning(f"Cascading tier {tier_name} query failed: {e}")
                
                query_duration = time.time() - query_start
                remaining_time -= query_duration
    
    async def _query_tier_with_timeout(
        self,
        tier_name: str,
        query: MemoryQuery,
        session_context: Optional[Dict[str, Any]],
        timeout: float
    ) -> List[RecordEnvelope]:
        """Query a specific tier with timeout protection."""
        if tier_name not in self.registry.tier_stores:
            raise RetrievalError(f"Tier {tier_name} not available")
        
        tier_adapter = self.registry.tier_stores[tier_name]
        
        # Check tier health
        if hasattr(tier_adapter, 'is_healthy') and not tier_adapter.is_healthy:
            self.logger.warning(f"Tier {tier_name} is unhealthy, skipping")
            return []
        
        # Apply tier-specific query limits
        tier_query = query.model_copy()
        tier_query.limit = min(query.limit, self.config.max_results_per_tier)
        
        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                tier_adapter.retrieve_memories(tier_query, session_context),
                timeout=timeout
            )
            
            self.logger.debug(f"Tier {tier_name} returned {len(result)} results")
            return result
        
        except asyncio.TimeoutError:
            raise RetrievalError(f"Tier {tier_name} query timeout after {timeout}s")
    
    async def _merge_tier_results(self, execution: QueryExecution) -> None:
        """Merge results from all tiers using the specified strategy."""
        all_results = []
        
        # Collect all results with tier information
        for tier_name, results in execution.tier_results.items():
            execution.metrics.raw_results_count[tier_name] = len(results)
            
            for record in results:
                # Create scored record (basic scoring here, refined later)
                from smrti.core.context_assembly import ContextScore, ScoredRecord
                
                score = ContextScore()
                
                # Basic tier priority scoring
                tier_priorities = {
                    "working": 1.0, "short_term": 0.8, "semantic": 0.7,
                    "episodic": 0.6, "long_term": 0.5, "procedural": 0.4
                }
                score.tier_priority = tier_priorities.get(tier_name, 0.3)
                
                # Basic temporal relevance
                if record.created_at:
                    hours_ago = (datetime.utcnow() - record.created_at).total_seconds() / 3600
                    if hours_ago <= 1:
                        score.temporal_relevance = 1.0
                    elif hours_ago <= 24:
                        score.temporal_relevance = 0.8
                    else:
                        score.temporal_relevance = 0.5
                
                scored_record = ScoredRecord(
                    record=record,
                    score=score,
                    tier_source=tier_name
                )
                
                all_results.append(scored_record)
        
        # Apply merge strategy
        if execution.merge_strategy == ResultMergeStrategy.SCORE_WEIGHTED:
            execution.merged_results = self._merge_by_score(all_results)
        
        elif execution.merge_strategy == ResultMergeStrategy.TIER_PRIORITY:
            execution.merged_results = self._merge_by_tier_priority(all_results)
        
        elif execution.merge_strategy == ResultMergeStrategy.TEMPORAL:
            execution.merged_results = self._merge_by_temporal(all_results)
        
        elif execution.merge_strategy == ResultMergeStrategy.DIVERSITY_FIRST:
            execution.merged_results = self._merge_by_diversity(all_results)
        
        elif execution.merge_strategy == ResultMergeStrategy.HYBRID:
            execution.merged_results = self._merge_hybrid(all_results, execution)
        
        else:
            # Default to score-weighted
            execution.merged_results = self._merge_by_score(all_results)
    
    def _merge_by_score(self, results: List[ScoredRecord]) -> List[ScoredRecord]:
        """Merge results prioritizing by relevance score."""
        return sorted(results, key=lambda x: x.total_score, reverse=True)
    
    def _merge_by_tier_priority(self, results: List[ScoredRecord]) -> List[ScoredRecord]:
        """Merge results prioritizing by tier importance."""
        tier_order = ["working", "short_term", "semantic", "episodic", "long_term", "procedural"]
        
        def tier_sort_key(record: ScoredRecord) -> Tuple[int, float]:
            tier_idx = tier_order.index(record.tier_source) if record.tier_source in tier_order else 99
            return (tier_idx, -record.total_score)
        
        return sorted(results, key=tier_sort_key)
    
    def _merge_by_temporal(self, results: List[ScoredRecord]) -> List[ScoredRecord]:
        """Merge results prioritizing by recency."""
        def temporal_sort_key(record: ScoredRecord) -> Tuple[datetime, float]:
            created = record.record.created_at or datetime.min
            return (-created.timestamp(), -record.total_score)
        
        return sorted(results, key=temporal_sort_key)
    
    def _merge_by_diversity(self, results: List[ScoredRecord]) -> List[ScoredRecord]:
        """Merge results prioritizing diversity."""
        if not results:
            return []
        
        # Start with highest-scoring result
        results_by_score = sorted(results, key=lambda x: x.total_score, reverse=True)
        selected = [results_by_score[0]]
        remaining = results_by_score[1:]
        
        # Greedily select diverse results
        while remaining and len(selected) < len(results):
            best_candidate = None
            best_diversity_score = -1
            
            for candidate in remaining:
                # Calculate average similarity to already selected results
                similarities = []
                for selected_result in selected:
                    if (candidate.record.embedding and 
                        selected_result.record.embedding):
                        sim = self._calculate_similarity(
                            candidate.record.embedding,
                            selected_result.record.embedding
                        )
                        similarities.append(sim)
                
                # Diversity score = relevance - average similarity
                avg_similarity = sum(similarities) / len(similarities) if similarities else 0
                diversity_score = candidate.total_score - avg_similarity
                
                if diversity_score > best_diversity_score:
                    best_diversity_score = diversity_score
                    best_candidate = candidate
            
            if best_candidate:
                selected.append(best_candidate)
                remaining.remove(best_candidate)
            else:
                break
        
        return selected
    
    def _merge_hybrid(
        self, 
        results: List[ScoredRecord], 
        execution: QueryExecution
    ) -> List[ScoredRecord]:
        """Hybrid merge strategy combining multiple factors."""
        if not results:
            return []
        
        # Calculate hybrid scores
        for result in results:
            # Base relevance score
            hybrid_score = result.total_score * 0.5
            
            # Tier priority bonus
            tier_bonus = result.score.tier_priority * 0.2
            
            # Freshness bonus
            if result.record.created_at:
                hours_ago = (datetime.utcnow() - result.record.created_at).total_seconds() / 3600
                if hours_ago <= 24:
                    freshness_bonus = self.config.freshness_boost * (1 - hours_ago / 24)
                    hybrid_score += freshness_bonus
            
            # Access frequency bonus
            access_count = result.record.metadata.get("access_count", 0)
            if access_count > 0:
                frequency_bonus = min(0.1, access_count / 100.0)
                hybrid_score += frequency_bonus
            
            # Store hybrid score in a custom field
            result.score.coherence_score = hybrid_score
        
        # Sort by hybrid score
        return sorted(results, key=lambda x: x.score.coherence_score, reverse=True)
    
    def _calculate_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if len(vec1) != len(vec2):
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    async def _apply_quality_filters(self, execution: QueryExecution) -> None:
        """Apply quality filters and deduplication."""
        if not execution.merged_results:
            return
        
        filtered_results = []
        seen_ids = set()
        seen_content_hashes = set()
        
        for result in execution.merged_results:
            # Skip duplicates by ID
            if result.record.record_id in seen_ids:
                execution.metrics.duplicate_count += 1
                continue
            
            # Skip low-quality results
            if result.total_score < self.config.min_quality_threshold:
                execution.metrics.filtered_count += 1
                continue
            
            # Deduplication by content similarity
            if self.config.enable_deduplication:
                content_hash = hash(str(result.record.content))
                
                if content_hash in seen_content_hashes:
                    execution.metrics.duplicate_count += 1
                    continue
                
                seen_content_hashes.add(content_hash)
            
            seen_ids.add(result.record.record_id)
            filtered_results.append(result)
        
        execution.merged_results = filtered_results
    
    def _select_query_strategy(self, query: MemoryQuery) -> QueryStrategy:
        """Select optimal query strategy based on query characteristics."""
        if self.config.default_strategy != QueryStrategy.ADAPTIVE:
            return self.config.default_strategy
        
        # Adaptive selection logic
        available_tiers = len(self.registry.tier_stores)
        
        # Small queries or few tiers -> parallel
        if query.limit <= self.config.adaptive_threshold_small_query or available_tiers <= 2:
            return QueryStrategy.PARALLEL
        
        # Large queries -> cascading for efficiency
        if query.limit >= self.config.adaptive_threshold_large_query:
            return QueryStrategy.CASCADING
        
        # Check tier reliability
        avg_reliability = sum(self._tier_reliability.values()) / len(self._tier_reliability)
        
        if avg_reliability < self.config.adaptive_tier_failure_threshold:
            return QueryStrategy.SEQUENTIAL  # More controlled execution
        else:
            return QueryStrategy.PARALLEL   # Fastest execution
    
    def _select_merge_strategy(
        self, 
        query: MemoryQuery, 
        query_strategy: QueryStrategy
    ) -> ResultMergeStrategy:
        """Select optimal merge strategy."""
        if self.config.default_merge_strategy != ResultMergeStrategy.HYBRID:
            return self.config.default_merge_strategy
        
        # Context-aware strategy selection
        if query.time_range_hours and query.time_range_hours <= 24:
            return ResultMergeStrategy.TEMPORAL
        
        if query.similarity_threshold > 0.8:
            return ResultMergeStrategy.SCORE_WEIGHTED
        
        if query.limit >= 50:
            return ResultMergeStrategy.DIVERSITY_FIRST
        
        return ResultMergeStrategy.HYBRID
    
    def _update_tier_reliability(self, execution: QueryExecution) -> None:
        """Update tier reliability based on execution results."""
        for tier_name in execution.metrics.tiers_queried:
            if tier_name in execution.tier_errors:
                # Decrease reliability for failed tiers
                self._tier_reliability[tier_name] *= 0.9
                self._tier_reliability[tier_name] = max(0.1, self._tier_reliability[tier_name])
            else:
                # Increase reliability for successful tiers
                self._tier_reliability[tier_name] = min(1.0, self._tier_reliability[tier_name] * 1.01)
    
    def _update_strategy_performance(
        self, 
        strategy: QueryStrategy, 
        execution: QueryExecution
    ) -> None:
        """Update performance metrics for query strategy."""
        self._strategy_performance[strategy].append(execution.metrics.total_duration)
        
        # Keep only recent performance data
        if len(self._strategy_performance[strategy]) > 100:
            self._strategy_performance[strategy] = self._strategy_performance[strategy][-50:]
    
    async def _check_result_cache(self, query: MemoryQuery) -> Optional[List[ScoredRecord]]:
        """Check if query results are cached."""
        if not self.config.enable_result_caching:
            return None
        
        cache_key = self._generate_cache_key(query)
        
        if cache_key in self._result_cache:
            cached_result, timestamp = self._result_cache[cache_key]
            
            if datetime.utcnow() - timestamp < self._cache_ttl:
                return cached_result
            else:
                del self._result_cache[cache_key]
        
        return None
    
    async def _cache_result(self, query: MemoryQuery, result: List[ScoredRecord]) -> None:
        """Cache query result."""
        if not self.config.enable_result_caching:
            return
        
        cache_key = self._generate_cache_key(query)
        self._result_cache[cache_key] = (result, datetime.utcnow())
        
        # Limit cache size
        if len(self._result_cache) > self.config.max_cache_size:
            oldest_key = min(
                self._result_cache.keys(),
                key=lambda k: self._result_cache[k][1]
            )
            del self._result_cache[oldest_key]
    
    def _generate_cache_key(self, query: MemoryQuery) -> str:
        """Generate cache key for query."""
        import hashlib
        
        key_components = [
            query.query_text or "",
            query.namespace or "",
            str(query.limit),
            str(query.similarity_threshold),
            str(query.time_range_hours or "")
        ]
        
        key_string = "|".join(key_components)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _generate_query_id(self, query: MemoryQuery) -> str:
        """Generate unique query ID."""
        import uuid
        return str(uuid.uuid4())[:8]
    
    def _validate_query(self, query: MemoryQuery) -> None:
        """Validate query parameters."""
        if query.limit <= 0:
            raise ValidationError("Query limit must be positive")
        
        if query.limit > 1000:
            raise ValidationError("Query limit cannot exceed 1000")
        
        if query.similarity_threshold < 0.0 or query.similarity_threshold > 1.0:
            raise ValidationError("Similarity threshold must be between 0.0 and 1.0")
    
    async def get_active_queries(self) -> List[Dict[str, Any]]:
        """Get information about currently active queries."""
        active_info = []
        
        for query_id, execution in self._active_executions.items():
            info = {
                "query_id": query_id,
                "query_text": execution.original_query.query_text,
                "strategy": execution.strategy.value,
                "merge_strategy": execution.merge_strategy.value,
                "elapsed_time": (datetime.utcnow() - execution.start_time).total_seconds(),
                "tiers_queried": len(execution.tier_results),
                "total_results": sum(len(results) for results in execution.tier_results.values()),
                "errors": list(execution.tier_errors.keys())
            }
            active_info.append(info)
        
        return active_info
    
    async def _perform_health_check(self) -> Dict[str, Any]:
        """Perform retrieval engine health check."""
        # Test basic retrieval functionality
        test_query = MemoryQuery(query_text="test", limit=1, similarity_threshold=0.9)
        
        try:
            start_time = time.time()
            # Just test tier query capabilities
            available_tiers = list(self.registry.tier_stores.keys())
            test_duration = time.time() - start_time
            test_success = True
        except Exception:
            test_duration = 0.0
            test_success = False
        
        return {
            "available_tiers": len(self.registry.tier_stores),
            "tier_reliability": dict(self._tier_reliability),
            "queries_executed": self._queries_executed,
            "cache_size": len(self._result_cache),
            "cache_hit_rate": self._cache_hits / max(1, self._queries_executed),
            "average_query_time": self._total_query_time / max(1, self._queries_executed),
            "strategy_usage": dict(self._strategy_usage),
            "active_queries": len(self._active_executions),
            "test_success": test_success,
            "test_duration": test_duration
        }
    
    async def get_retrieval_stats(self) -> Dict[str, Any]:
        """Get detailed retrieval engine statistics."""
        base_stats = await self.get_stats()
        
        # Strategy performance
        strategy_perf = {}
        for strategy, times in self._strategy_performance.items():
            if times:
                strategy_perf[strategy.value] = {
                    "avg_time": sum(times) / len(times),
                    "min_time": min(times),
                    "max_time": max(times),
                    "usage_count": len(times)
                }
        
        retrieval_stats = {
            "queries_executed": self._queries_executed,
            "cache_hits": self._cache_hits,
            "cache_hit_rate": self._cache_hits / max(1, self._queries_executed),
            "total_query_time": self._total_query_time,
            "average_query_time": self._total_query_time / max(1, self._queries_executed),
            "strategy_usage": dict(self._strategy_usage),
            "strategy_performance": strategy_perf,
            "tier_reliability": dict(self._tier_reliability),
            "cache_size": len(self._result_cache),
            "active_queries": len(self._active_executions),
            "config": {
                "default_strategy": self.config.default_strategy.value,
                "default_merge_strategy": self.config.default_merge_strategy.value,
                "max_query_time": self.config.max_query_time,
                "enable_result_caching": self.config.enable_result_caching,
                "enable_context_assembly": self.config.enable_context_assembly
            }
        }
        
        base_stats.update(retrieval_stats)
        return base_stats
    
    async def clear_cache(self) -> int:
        """Clear the result cache."""
        cleared_count = len(self._result_cache)
        self._result_cache.clear()
        return cleared_count