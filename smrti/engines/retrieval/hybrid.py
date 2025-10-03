"""
Hybrid Retrieval Engine - Multi-Modal Search

Combines multiple retrieval modalities for high-precision search:
- Vector similarity (semantic)
- Lexical search (BM25-style)
- Temporal filtering
- Graph traversal
- Fusion strategies

Based on PRD Section 7: Query & Retrieval Strategies
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple, Callable
from collections import defaultdict
import math

from ...models.memory import MemoryItem


logger = logging.getLogger(__name__)


class SearchMode(Enum):
    """Search modality modes."""
    VECTOR_ONLY = "vector"
    LEXICAL_ONLY = "lexical"
    TEMPORAL_ONLY = "temporal"
    GRAPH_ONLY = "graph"
    HYBRID = "hybrid"  # Combines all available modalities


class FusionStrategy(Enum):
    """Strategies for fusing multi-modal results."""
    WEIGHTED = "weighted"  # Weighted sum of normalized scores
    RRF = "rrf"  # Reciprocal Rank Fusion
    CASCADE = "cascade"  # Sequential filtering
    VOTING = "voting"  # Majority voting across modalities


class RerankMode(Enum):
    """Re-ranking modes."""
    DISABLED = "disabled"
    LIGHTWEIGHT = "lightweight"  # Fast cross-encoder
    HIGH_FIDELITY = "high_fidelity"  # Slow but accurate


@dataclass
class RetrievalConfig:
    """Configuration for hybrid retrieval."""
    
    # Search modes
    default_search_mode: SearchMode = SearchMode.HYBRID
    fusion_strategy: FusionStrategy = FusionStrategy.WEIGHTED
    rerank_mode: RerankMode = RerankMode.DISABLED
    
    # Fusion weights (must sum to ≤ 1.0)
    weight_vector: float = 0.45
    weight_lexical: float = 0.20
    weight_graph: float = 0.15
    weight_temporal: float = 0.10
    weight_recency: float = 0.10
    
    # Retrieval limits
    max_candidates_per_modality: int = 100
    final_top_k: int = 20
    rerank_top_n: int = 30
    
    # Performance
    enable_caching: bool = True
    cache_ttl_seconds: int = 300  # 5 minutes
    parallel_retrieval: bool = True
    timeout_seconds: float = 5.0
    
    # Query expansion
    enable_expansion: bool = True
    max_expansions: int = 5
    expansion_similarity_threshold: float = 0.85
    
    # Temporal
    recency_decay_days: float = 30.0
    
    def validate(self) -> None:
        """Validate configuration."""
        total_weight = (
            self.weight_vector +
            self.weight_lexical +
            self.weight_graph +
            self.weight_temporal +
            self.weight_recency
        )
        if total_weight > 1.0:
            logger.warning(
                f"Fusion weights sum to {total_weight:.2f} > 1.0, "
                f"will normalize"
            )


@dataclass
class SearchQuery:
    """Search query specification."""
    
    query_text: str
    tenant_id: str
    namespace: str = "default"
    
    # Filters
    user_id: Optional[str] = None
    time_range: Optional[Tuple[datetime, datetime]] = None
    tags: Optional[List[str]] = None
    filters: Optional[Dict[str, Any]] = None
    
    # Retrieval parameters
    limit: int = 20
    search_mode: Optional[SearchMode] = None
    
    # Embedding (can be pre-computed)
    query_embedding: Optional[List[float]] = None
    
    def to_cache_key(self) -> str:
        """Generate cache key for this query."""
        import hashlib
        
        key_parts = [
            self.query_text,
            self.tenant_id,
            self.namespace,
            str(self.user_id or ""),
            str(self.time_range or ""),
            str(sorted(self.tags or [])),
            str(self.limit)
        ]
        key_str = "|".join(key_parts)
        return hashlib.md5(key_str.encode()).hexdigest()


@dataclass
class SearchCandidate:
    """Single search result candidate."""
    
    item: MemoryItem
    scores: Dict[str, float] = field(default_factory=dict)  # Modality scores
    combined_score: float = 0.0
    rank: int = 0
    
    # Provenance
    source_modality: str = ""
    retrieval_timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass
class SearchResult:
    """Search result with metadata."""
    
    candidates: List[SearchCandidate]
    query: SearchQuery
    
    # Performance metrics
    retrieval_time_ms: float = 0.0
    fusion_time_ms: float = 0.0
    rerank_time_ms: float = 0.0
    total_time_ms: float = 0.0
    
    # Statistics
    modality_counts: Dict[str, int] = field(default_factory=dict)
    cache_hit: bool = False
    
    # Debug info
    fusion_strategy: str = ""
    rerank_applied: bool = False


class HybridRetrieval:
    """
    Hybrid Retrieval Engine
    
    Multi-modal search combining:
    - Vector similarity (semantic)
    - Lexical search (keyword/BM25)
    - Temporal filtering
    - Graph traversal
    - Fusion and re-ranking
    """
    
    def __init__(
        self,
        config: Optional[RetrievalConfig] = None,
        vector_adapter = None,
        lexical_adapter = None,
        graph_adapter = None,
        temporal_adapter = None,
        embedding_provider = None,
        reranker = None
    ):
        self.config = config or RetrievalConfig()
        self.config.validate()
        
        # Adapters
        self.vector_adapter = vector_adapter
        self.lexical_adapter = lexical_adapter
        self.graph_adapter = graph_adapter
        self.temporal_adapter = temporal_adapter
        self.embedding_provider = embedding_provider
        self.reranker = reranker
        
        # Cache
        self._cache: Dict[str, SearchResult] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        
        # Statistics
        self._stats = {
            "searches_performed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "vector_searches": 0,
            "lexical_searches": 0,
            "graph_searches": 0,
            "temporal_searches": 0,
            "reranks_performed": 0,
            "avg_retrieval_time_ms": 0.0
        }
        
        logger.info("HybridRetrieval engine initialized")
    
    async def search(
        self,
        query: SearchQuery,
        search_mode: Optional[SearchMode] = None,
        fusion_strategy: Optional[FusionStrategy] = None
    ) -> SearchResult:
        """
        Execute hybrid search.
        
        Args:
            query: Search query specification
            search_mode: Override default search mode
            fusion_strategy: Override default fusion strategy
        
        Returns:
            SearchResult with ranked candidates
        """
        start_time = time.time()
        self._stats["searches_performed"] += 1
        
        # Check cache
        if self.config.enable_caching:
            cache_key = query.to_cache_key()
            cached = self._get_cached(cache_key)
            if cached:
                self._stats["cache_hits"] += 1
                cached.cache_hit = True
                return cached
            self._stats["cache_misses"] += 1
        
        # Determine search mode
        mode = search_mode or query.search_mode or self.config.default_search_mode
        fusion = fusion_strategy or self.config.fusion_strategy
        
        # Execute retrieval
        retrieval_start = time.time()
        candidates = await self._retrieve_candidates(query, mode)
        retrieval_time = (time.time() - retrieval_start) * 1000
        
        # Fusion
        fusion_start = time.time()
        ranked = self._fuse_and_rank(candidates, fusion)
        fusion_time = (time.time() - fusion_start) * 1000
        
        # Re-ranking (optional)
        rerank_time = 0.0
        rerank_applied = False
        if self.config.rerank_mode != RerankMode.DISABLED and self.reranker:
            if len(ranked) >= self.config.rerank_top_n:
                rerank_start = time.time()
                ranked = await self._rerank_candidates(query, ranked)
                rerank_time = (time.time() - rerank_start) * 1000
                rerank_applied = True
                self._stats["reranks_performed"] += 1
        
        # Limit results
        ranked = ranked[:query.limit]
        
        # Build result
        total_time = (time.time() - start_time) * 1000
        result = SearchResult(
            candidates=ranked,
            query=query,
            retrieval_time_ms=retrieval_time,
            fusion_time_ms=fusion_time,
            rerank_time_ms=rerank_time,
            total_time_ms=total_time,
            modality_counts=self._count_modalities(candidates),
            fusion_strategy=fusion.value,
            rerank_applied=rerank_applied
        )
        
        # Update stats
        self._update_avg_time(total_time)
        
        # Cache result
        if self.config.enable_caching:
            self._set_cached(cache_key, result)
        
        logger.debug(
            f"Search completed: {len(ranked)} results in {total_time:.1f}ms "
            f"(retrieval={retrieval_time:.1f}ms, fusion={fusion_time:.1f}ms, "
            f"rerank={rerank_time:.1f}ms)"
        )
        
        return result
    
    async def _retrieve_candidates(
        self,
        query: SearchQuery,
        mode: SearchMode
    ) -> List[SearchCandidate]:
        """Retrieve candidates from all applicable modalities."""
        
        # Prepare query embedding if needed
        if mode in [SearchMode.VECTOR_ONLY, SearchMode.HYBRID]:
            if not query.query_embedding and self.embedding_provider:
                query.query_embedding = await self.embedding_provider.embed(
                    query.query_text
                )
        
        # Execute searches in parallel or sequentially
        if self.config.parallel_retrieval:
            tasks = []
            
            if mode in [SearchMode.VECTOR_ONLY, SearchMode.HYBRID]:
                if self.vector_adapter:
                    tasks.append(self._search_vector(query))
            
            if mode in [SearchMode.LEXICAL_ONLY, SearchMode.HYBRID]:
                if self.lexical_adapter:
                    tasks.append(self._search_lexical(query))
            
            if mode in [SearchMode.TEMPORAL_ONLY, SearchMode.HYBRID]:
                if self.temporal_adapter:
                    tasks.append(self._search_temporal(query))
            
            if mode in [SearchMode.GRAPH_ONLY, SearchMode.HYBRID]:
                if self.graph_adapter:
                    tasks.append(self._search_graph(query))
            
            # Execute all searches
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Merge results
                all_candidates = []
                for result in results:
                    if isinstance(result, Exception):
                        logger.error(f"Search failed: {result}")
                        continue
                    if result:
                        all_candidates.extend(result)
                
                return all_candidates
        else:
            # Sequential execution
            all_candidates = []
            
            if mode in [SearchMode.VECTOR_ONLY, SearchMode.HYBRID]:
                if self.vector_adapter:
                    candidates = await self._search_vector(query)
                    all_candidates.extend(candidates)
            
            if mode in [SearchMode.LEXICAL_ONLY, SearchMode.HYBRID]:
                if self.lexical_adapter:
                    candidates = await self._search_lexical(query)
                    all_candidates.extend(candidates)
            
            if mode in [SearchMode.TEMPORAL_ONLY, SearchMode.HYBRID]:
                if self.temporal_adapter:
                    candidates = await self._search_temporal(query)
                    all_candidates.extend(candidates)
            
            if mode in [SearchMode.GRAPH_ONLY, SearchMode.HYBRID]:
                if self.graph_adapter:
                    candidates = await self._search_graph(query)
                    all_candidates.extend(candidates)
            
            return all_candidates
        
        return []
    
    async def _search_vector(self, query: SearchQuery) -> List[SearchCandidate]:
        """Execute vector similarity search."""
        if not self.vector_adapter or not query.query_embedding:
            return []
        
        self._stats["vector_searches"] += 1
        
        try:
            # Search vector store
            results = await self.vector_adapter.search(
                query_embedding=query.query_embedding,
                namespace=query.namespace,
                tenant_id=query.tenant_id,
                limit=self.config.max_candidates_per_modality,
                filters=query.filters
            )
            
            # Convert to candidates
            candidates = []
            for result in results:
                candidate = SearchCandidate(
                    item=result.item if hasattr(result, 'item') else result,
                    scores={"vector": result.score if hasattr(result, 'score') else 1.0},
                    source_modality="vector"
                )
                candidates.append(candidate)
            
            logger.debug(f"Vector search returned {len(candidates)} candidates")
            return candidates
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    async def _search_lexical(self, query: SearchQuery) -> List[SearchCandidate]:
        """Execute lexical/BM25 search."""
        if not self.lexical_adapter:
            return []
        
        self._stats["lexical_searches"] += 1
        
        try:
            results = await self.lexical_adapter.search(
                query_text=query.query_text,
                namespace=query.namespace,
                tenant_id=query.tenant_id,
                limit=self.config.max_candidates_per_modality,
                filters=query.filters
            )
            
            candidates = []
            for result in results:
                candidate = SearchCandidate(
                    item=result.item if hasattr(result, 'item') else result,
                    scores={"lexical": result.score if hasattr(result, 'score') else 1.0},
                    source_modality="lexical"
                )
                candidates.append(candidate)
            
            logger.debug(f"Lexical search returned {len(candidates)} candidates")
            return candidates
            
        except Exception as e:
            logger.error(f"Lexical search failed: {e}")
            return []
    
    async def _search_temporal(self, query: SearchQuery) -> List[SearchCandidate]:
        """Execute temporal search."""
        if not self.temporal_adapter:
            return []
        
        self._stats["temporal_searches"] += 1
        
        try:
            results = await self.temporal_adapter.search(
                query_text=query.query_text,
                time_range=query.time_range,
                namespace=query.namespace,
                tenant_id=query.tenant_id,
                limit=self.config.max_candidates_per_modality,
                filters=query.filters
            )
            
            candidates = []
            for result in results:
                # Calculate temporal score (recency)
                temporal_score = self._calculate_recency_score(
                    result.timestamp if hasattr(result, 'timestamp') else datetime.now(timezone.utc)
                )
                
                candidate = SearchCandidate(
                    item=result.item if hasattr(result, 'item') else result,
                    scores={"temporal": temporal_score},
                    source_modality="temporal"
                )
                candidates.append(candidate)
            
            logger.debug(f"Temporal search returned {len(candidates)} candidates")
            return candidates
            
        except Exception as e:
            logger.error(f"Temporal search failed: {e}")
            return []
    
    async def _search_graph(self, query: SearchQuery) -> List[SearchCandidate]:
        """Execute graph traversal search."""
        if not self.graph_adapter:
            return []
        
        self._stats["graph_searches"] += 1
        
        try:
            results = await self.graph_adapter.search(
                query_text=query.query_text,
                namespace=query.namespace,
                tenant_id=query.tenant_id,
                limit=self.config.max_candidates_per_modality,
                filters=query.filters
            )
            
            candidates = []
            for result in results:
                candidate = SearchCandidate(
                    item=result.item if hasattr(result, 'item') else result,
                    scores={"graph": result.score if hasattr(result, 'score') else 1.0},
                    source_modality="graph"
                )
                candidates.append(candidate)
            
            logger.debug(f"Graph search returned {len(candidates)} candidates")
            return candidates
            
        except Exception as e:
            logger.error(f"Graph search failed: {e}")
            return []
    
    def _fuse_and_rank(
        self,
        candidates: List[SearchCandidate],
        strategy: FusionStrategy
    ) -> List[SearchCandidate]:
        """Fuse multi-modal scores and rank candidates."""
        
        if not candidates:
            return []
        
        if strategy == FusionStrategy.WEIGHTED:
            return self._fusion_weighted(candidates)
        elif strategy == FusionStrategy.RRF:
            return self._fusion_rrf(candidates)
        elif strategy == FusionStrategy.CASCADE:
            return self._fusion_cascade(candidates)
        elif strategy == FusionStrategy.VOTING:
            return self._fusion_voting(candidates)
        else:
            logger.warning(f"Unknown fusion strategy: {strategy}, using weighted")
            return self._fusion_weighted(candidates)
    
    def _fusion_weighted(
        self,
        candidates: List[SearchCandidate]
    ) -> List[SearchCandidate]:
        """Weighted fusion strategy."""
        
        # Normalize scores per modality
        self._normalize_scores(candidates)
        
        # Calculate combined scores
        for candidate in candidates:
            score = 0.0
            
            score += candidate.scores.get("vector", 0.0) * self.config.weight_vector
            score += candidate.scores.get("lexical", 0.0) * self.config.weight_lexical
            score += candidate.scores.get("graph", 0.0) * self.config.weight_graph
            score += candidate.scores.get("temporal", 0.0) * self.config.weight_temporal
            
            # Add recency boost
            if hasattr(candidate.item, 'metadata') and candidate.item.metadata:
                recency = self._calculate_recency_score(
                    candidate.item.metadata.created_at
                )
                score += recency * self.config.weight_recency
            
            candidate.combined_score = score
        
        # Sort by combined score
        candidates.sort(key=lambda c: c.combined_score, reverse=True)
        
        # Assign ranks
        for i, candidate in enumerate(candidates):
            candidate.rank = i + 1
        
        return candidates
    
    def _fusion_rrf(
        self,
        candidates: List[SearchCandidate],
        k: int = 60
    ) -> List[SearchCandidate]:
        """Reciprocal Rank Fusion (RRF)."""
        
        # Group by modality and rank
        modality_rankings: Dict[str, List[SearchCandidate]] = defaultdict(list)
        for candidate in candidates:
            modality_rankings[candidate.source_modality].append(candidate)
        
        # Sort each modality's candidates by score
        for modality, cands in modality_rankings.items():
            cands.sort(
                key=lambda c: c.scores.get(modality, 0.0),
                reverse=True
            )
        
        # Calculate RRF scores
        rrf_scores: Dict[str, float] = defaultdict(float)
        
        for modality, cands in modality_rankings.items():
            for rank, candidate in enumerate(cands, start=1):
                # RRF formula: 1 / (k + rank)
                rrf_scores[candidate.item.key] += 1.0 / (k + rank)
        
        # Assign RRF scores
        for candidate in candidates:
            candidate.combined_score = rrf_scores.get(candidate.item.key, 0.0)
        
        # Sort by RRF score
        candidates.sort(key=lambda c: c.combined_score, reverse=True)
        
        # Assign ranks
        for i, candidate in enumerate(candidates):
            candidate.rank = i + 1
        
        return candidates
    
    def _fusion_cascade(
        self,
        candidates: List[SearchCandidate]
    ) -> List[SearchCandidate]:
        """Cascade fusion - sequential filtering."""
        
        # Start with vector results (highest precision)
        filtered = [c for c in candidates if "vector" in c.scores]
        
        # Add lexical if vector is sparse
        if len(filtered) < self.config.final_top_k:
            lexical = [c for c in candidates if "lexical" in c.scores]
            filtered.extend(lexical)
        
        # Add temporal if still sparse
        if len(filtered) < self.config.final_top_k:
            temporal = [c for c in candidates if "temporal" in c.scores]
            filtered.extend(temporal)
        
        # Add graph as fallback
        if len(filtered) < self.config.final_top_k:
            graph = [c for c in candidates if "graph" in c.scores]
            filtered.extend(graph)
        
        # Deduplicate
        seen = set()
        unique = []
        for candidate in filtered:
            if candidate.item.key not in seen:
                seen.add(candidate.item.key)
                unique.append(candidate)
        
        # Calculate combined scores for sorting
        for candidate in unique:
            candidate.combined_score = max(candidate.scores.values())
        
        unique.sort(key=lambda c: c.combined_score, reverse=True)
        
        for i, candidate in enumerate(unique):
            candidate.rank = i + 1
        
        return unique
    
    def _fusion_voting(
        self,
        candidates: List[SearchCandidate]
    ) -> List[SearchCandidate]:
        """Voting fusion - items appearing in multiple modalities ranked higher."""
        
        # Count appearances per item
        item_votes: Dict[str, int] = defaultdict(int)
        item_scores: Dict[str, float] = defaultdict(float)
        item_candidate: Dict[str, SearchCandidate] = {}
        
        for candidate in candidates:
            key = candidate.item.key
            item_votes[key] += 1
            item_scores[key] += max(candidate.scores.values())
            item_candidate[key] = candidate
        
        # Calculate combined score: votes + average score
        for key, candidate in item_candidate.items():
            votes = item_votes[key]
            avg_score = item_scores[key] / votes
            candidate.combined_score = votes + avg_score
        
        # Get unique candidates and sort
        unique_candidates = list(item_candidate.values())
        unique_candidates.sort(key=lambda c: c.combined_score, reverse=True)
        
        for i, candidate in enumerate(unique_candidates):
            candidate.rank = i + 1
        
        return unique_candidates
    
    def _normalize_scores(self, candidates: List[SearchCandidate]) -> None:
        """Min-max normalize scores per modality."""
        
        # Group by modality
        modality_scores: Dict[str, List[float]] = defaultdict(list)
        
        for candidate in candidates:
            for modality, score in candidate.scores.items():
                modality_scores[modality].append(score)
        
        # Calculate min-max per modality
        modality_ranges: Dict[str, Tuple[float, float]] = {}
        for modality, scores in modality_scores.items():
            if scores:
                modality_ranges[modality] = (min(scores), max(scores))
        
        # Normalize
        for candidate in candidates:
            for modality, score in candidate.scores.items():
                min_score, max_score = modality_ranges.get(modality, (0.0, 1.0))
                if max_score > min_score:
                    normalized = (score - min_score) / (max_score - min_score)
                else:
                    normalized = 1.0 if score > 0 else 0.0
                candidate.scores[modality] = normalized
    
    def _calculate_recency_score(self, timestamp: datetime) -> float:
        """Calculate recency score (0-1) based on age."""
        now = datetime.now(timezone.utc)
        age_days = (now - timestamp).total_seconds() / 86400.0
        
        # Exponential decay
        decay = math.exp(-age_days / self.config.recency_decay_days)
        return decay
    
    async def _rerank_candidates(
        self,
        query: SearchQuery,
        candidates: List[SearchCandidate]
    ) -> List[SearchCandidate]:
        """Re-rank top candidates using cross-encoder."""
        
        if not self.reranker:
            return candidates
        
        # Take top N for reranking
        to_rerank = candidates[:self.config.rerank_top_n]
        rest = candidates[self.config.rerank_top_n:]
        
        try:
            # Prepare pairs for reranking
            pairs = [
                (query.query_text, self._extract_text(c.item))
                for c in to_rerank
            ]
            
            # Get reranking scores
            rerank_scores = await self.reranker.score(pairs)
            
            # Update scores
            for candidate, score in zip(to_rerank, rerank_scores):
                candidate.scores["rerank"] = score
                candidate.combined_score = score
            
            # Re-sort
            to_rerank.sort(key=lambda c: c.combined_score, reverse=True)
            
            # Reassign ranks
            for i, candidate in enumerate(to_rerank):
                candidate.rank = i + 1
            
            # Append rest
            for i, candidate in enumerate(rest, start=len(to_rerank) + 1):
                candidate.rank = i
            
            return to_rerank + rest
            
        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            return candidates
    
    def _extract_text(self, item: MemoryItem) -> str:
        """Extract text from memory item for reranking."""
        if isinstance(item.value, str):
            return item.value
        elif isinstance(item.value, dict):
            return item.value.get("content", str(item.value))
        else:
            return str(item.value)
    
    def _count_modalities(
        self,
        candidates: List[SearchCandidate]
    ) -> Dict[str, int]:
        """Count candidates per modality."""
        counts = defaultdict(int)
        for candidate in candidates:
            counts[candidate.source_modality] += 1
        return dict(counts)
    
    def _get_cached(self, key: str) -> Optional[SearchResult]:
        """Get cached search result."""
        if key not in self._cache:
            return None
        
        timestamp = self._cache_timestamps.get(key)
        if not timestamp:
            return None
        
        age = (datetime.now(timezone.utc) - timestamp).total_seconds()
        if age > self.config.cache_ttl_seconds:
            # Expired
            del self._cache[key]
            del self._cache_timestamps[key]
            return None
        
        return self._cache[key]
    
    def _set_cached(self, key: str, result: SearchResult) -> None:
        """Cache search result."""
        self._cache[key] = result
        self._cache_timestamps[key] = datetime.now(timezone.utc)
    
    def _update_avg_time(self, time_ms: float) -> None:
        """Update average retrieval time."""
        count = self._stats["searches_performed"]
        current_avg = self._stats["avg_retrieval_time_ms"]
        
        # Running average
        new_avg = ((current_avg * (count - 1)) + time_ms) / count
        self._stats["avg_retrieval_time_ms"] = new_avg
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get retrieval statistics."""
        return self._stats.copy()
    
    def clear_cache(self) -> None:
        """Clear all caches."""
        self._cache.clear()
        self._cache_timestamps.clear()
        logger.info("Cache cleared")
