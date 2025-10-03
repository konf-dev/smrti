"""
smrti/core/context_assembly.py - Context Assembly Engine

Intelligent assembly of context from multiple memory tiers with relevance scoring,
conflict resolution, and coherence optimization.
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from smrti.core.base import BaseAdapter
from smrti.core.exceptions import ContextAssemblyError, InsufficientMemoryError, ValidationError
from smrti.core.registry import AdapterRegistry
from smrti.schemas.models import MemoryQuery, MemoryRecord, RecordEnvelope


@dataclass
class ContextScore:
    """Relevance scoring for memory records in context assembly."""
    
    # Primary relevance metrics
    semantic_similarity: float = 0.0  # Similarity to query
    temporal_relevance: float = 0.0   # Recency and temporal context
    access_frequency: float = 0.0     # How often accessed
    tier_priority: float = 0.0        # Priority based on memory tier
    
    # Secondary metrics
    coherence_score: float = 0.0      # How well it fits with other context
    completeness_score: float = 0.0  # Information completeness
    authority_score: float = 0.0     # Source authority/confidence
    
    # Penalty factors
    redundancy_penalty: float = 0.0  # Penalty for duplicate information
    age_penalty: float = 0.0         # Penalty for old information
    conflict_penalty: float = 0.0    # Penalty for conflicting information
    
    @property
    def total_score(self) -> float:
        """Calculate total weighted score."""
        primary = (
            self.semantic_similarity * 0.35 +
            self.temporal_relevance * 0.25 +
            self.access_frequency * 0.20 +
            self.tier_priority * 0.20
        )
        
        secondary = (
            self.coherence_score * 0.30 +
            self.completeness_score * 0.35 +
            self.authority_score * 0.35
        ) * 0.3  # Secondary metrics weighted at 30%
        
        penalties = (
            self.redundancy_penalty +
            self.age_penalty +
            self.conflict_penalty
        )
        
        return max(0.0, primary + secondary - penalties)


@dataclass
class ScoredRecord:
    """Memory record with calculated relevance score."""
    
    record: RecordEnvelope
    score: ContextScore
    tier_source: str
    retrieval_time: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def total_score(self) -> float:
        """Get the total relevance score."""
        return self.score.total_score


@dataclass
class ContextAssemblyConfig:
    """Configuration for context assembly engine."""
    
    # Assembly parameters
    max_context_size: int = 4000  # Maximum tokens in assembled context
    target_context_size: int = 2000  # Target context size
    min_relevance_threshold: float = 0.1  # Minimum score to include
    
    # Tier query limits
    working_memory_limit: int = 50
    short_term_limit: int = 100
    long_term_limit: int = 200
    episodic_limit: int = 150
    semantic_limit: int = 100
    procedural_limit: int = 50
    
    # Diversity parameters
    max_records_per_tier: int = 10  # Max records from any single tier
    diversity_threshold: float = 0.8  # Similarity threshold for diversity
    temporal_window_hours: int = 24  # Hours for temporal grouping
    
    # Quality parameters
    coherence_weight: float = 0.3  # Weight for coherence in final selection
    novelty_weight: float = 0.2    # Weight for novel information
    authority_weight: float = 0.1  # Weight for authoritative sources
    
    # Performance parameters
    max_assembly_time: float = 2.0  # Maximum assembly time in seconds
    parallel_tier_queries: bool = True  # Query tiers in parallel
    enable_caching: bool = True  # Cache assembly results


class ContextAssemblyEngine(BaseAdapter):
    """
    Intelligent context assembly engine for multi-tier memory systems.
    
    Orchestrates retrieval from multiple memory tiers and assembles
    coherent, relevant context with conflict resolution and optimization.
    """
    
    def __init__(
        self,
        registry: AdapterRegistry,
        config: ContextAssemblyConfig | None = None
    ):
        super().__init__("context_assembly")
        self.registry = registry
        self.config = config or ContextAssemblyConfig()
        
        # Tier priority mapping (higher = more important)
        self.tier_priorities = {
            "working": 1.0,      # Most immediate context
            "short_term": 0.8,   # Recent relevant context
            "semantic": 0.7,     # Conceptual knowledge
            "episodic": 0.6,     # Experience-based context
            "long_term": 0.5,    # General knowledge
            "procedural": 0.4    # Skills and procedures
        }
        
        # Context assembly cache
        self._assembly_cache: Dict[str, Tuple[List[ScoredRecord], datetime]] = {}
        self._cache_ttl = timedelta(minutes=5)
        
        # Statistics
        self._assemblies_performed = 0
        self._cache_hits = 0
        self._total_assembly_time = 0.0
        self._average_context_size = 0.0
    
    async def assemble_context(
        self,
        query: MemoryQuery,
        session_context: Optional[Dict[str, Any]] = None,
        force_refresh: bool = False
    ) -> List[ScoredRecord]:
        """
        Assemble intelligent context from multiple memory tiers.
        
        Args:
            query: Memory query for context assembly
            session_context: Optional session-specific context
            force_refresh: Force refresh of cached results
            
        Returns:
            List of scored and ranked memory records
            
        Raises:
            ContextAssemblyError: If assembly fails
            InsufficientMemoryError: If insufficient relevant memories found
        """
        start_time = time.time()
        
        try:
            # Check cache first (unless force refresh)
            if not force_refresh:
                cached_result = await self._check_assembly_cache(query)
                if cached_result:
                    self._cache_hits += 1
                    self.logger.debug(f"Cache hit for query: {query.query_text}")
                    return cached_result
            
            # Step 1: Retrieve memories from all available tiers
            tier_memories = await self._retrieve_from_tiers(query, session_context)
            
            if not any(tier_memories.values()):
                raise InsufficientMemoryError(
                    f"No relevant memories found for query: {query.query_text}",
                    query_text=query.query_text,
                    tiers_queried=list(tier_memories.keys())
                )
            
            # Step 2: Score all retrieved memories
            scored_memories = await self._score_memories(
                tier_memories, query, session_context
            )
            
            # Step 3: Apply diversity and coherence filtering
            filtered_memories = await self._apply_diversity_filter(scored_memories)
            
            # Step 4: Resolve conflicts between memories
            resolved_memories = await self._resolve_conflicts(filtered_memories)
            
            # Step 5: Optimize final context selection
            final_context = await self._optimize_context_selection(
                resolved_memories, query
            )
            
            # Step 6: Cache result
            if self.config.enable_caching:
                await self._cache_assembly_result(query, final_context)
            
            # Update statistics
            assembly_time = time.time() - start_time
            self._assemblies_performed += 1
            self._total_assembly_time += assembly_time
            
            context_size = sum(len(str(record.record)) for record in final_context)
            self._average_context_size = (
                (self._average_context_size * (self._assemblies_performed - 1) + context_size) 
                / self._assemblies_performed
            )
            
            self.logger.info(
                f"Assembled context with {len(final_context)} records "
                f"in {assembly_time:.3f}s (size: {context_size} chars)"
            )
            
            return final_context
        
        except Exception as e:
            self._mark_error(e)
            if isinstance(e, (ContextAssemblyError, InsufficientMemoryError)):
                raise
            else:
                raise ContextAssemblyError(
                    f"Context assembly failed: {e}",
                    query_text=query.query_text,
                    assembly_stage="execution",
                    backend_error=e
                )
    
    async def _retrieve_from_tiers(
        self,
        query: MemoryQuery,
        session_context: Optional[Dict[str, Any]]
    ) -> Dict[str, List[RecordEnvelope]]:
        """Retrieve memories from all available memory tiers."""
        tier_memories = {}
        
        # Define tier-specific query configurations
        tier_configs = {
            "working": {"limit": self.config.working_memory_limit, "priority": True},
            "short_term": {"limit": self.config.short_term_limit, "priority": True},
            "long_term": {"limit": self.config.long_term_limit, "priority": False},
            "episodic": {"limit": self.config.episodic_limit, "priority": False},
            "semantic": {"limit": self.config.semantic_limit, "priority": False},
            "procedural": {"limit": self.config.procedural_limit, "priority": False}
        }
        
        # Query tiers in parallel or sequentially
        if self.config.parallel_tier_queries:
            # Parallel retrieval
            tasks = []
            for tier_name, config in tier_configs.items():
                if tier_name in self.registry.tier_stores:
                    tier_query = self._adapt_query_for_tier(query, tier_name, config)
                    task = self._query_tier_safe(tier_name, tier_query, session_context)
                    tasks.append((tier_name, task))
            
            # Wait for all results
            for tier_name, task in tasks:
                try:
                    memories = await task
                    tier_memories[tier_name] = memories
                except Exception as e:
                    self.logger.warning(f"Failed to query tier {tier_name}: {e}")
                    tier_memories[tier_name] = []
        else:
            # Sequential retrieval (prioritize important tiers first)
            priority_tiers = [name for name, config in tier_configs.items() 
                            if config["priority"]]
            other_tiers = [name for name, config in tier_configs.items() 
                          if not config["priority"]]
            
            for tier_name in priority_tiers + other_tiers:
                if tier_name in self.registry.tier_stores:
                    try:
                        config = tier_configs[tier_name]
                        tier_query = self._adapt_query_for_tier(query, tier_name, config)
                        memories = await self._query_tier_safe(
                            tier_name, tier_query, session_context
                        )
                        tier_memories[tier_name] = memories
                    except Exception as e:
                        self.logger.warning(f"Failed to query tier {tier_name}: {e}")
                        tier_memories[tier_name] = []
        
        return tier_memories
    
    def _adapt_query_for_tier(
        self,
        base_query: MemoryQuery,
        tier_name: str,
        config: Dict[str, Any]
    ) -> MemoryQuery:
        """Adapt the base query for a specific tier's capabilities."""
        # Create tier-specific query
        tier_query = base_query.model_copy()
        tier_query.limit = min(base_query.limit, config["limit"])
        
        # Adjust query parameters based on tier characteristics
        if tier_name == "working":
            # Working memory: focus on immediate context
            tier_query.time_range_hours = min(tier_query.time_range_hours or 1, 1)
            tier_query.similarity_threshold = max(tier_query.similarity_threshold, 0.3)
        
        elif tier_name == "short_term":
            # Short-term: recent relevant memories
            tier_query.time_range_hours = min(tier_query.time_range_hours or 24, 24)
            tier_query.similarity_threshold = max(tier_query.similarity_threshold, 0.2)
        
        elif tier_name == "long_term":
            # Long-term: semantic similarity focus
            tier_query.similarity_threshold = max(tier_query.similarity_threshold, 0.15)
        
        elif tier_name == "episodic":
            # Episodic: temporal and experiential context
            if not tier_query.time_range_hours:
                tier_query.time_range_hours = 72  # 3 days default
        
        elif tier_name == "semantic":
            # Semantic: conceptual relationships
            tier_query.similarity_threshold = max(tier_query.similarity_threshold, 0.1)
        
        return tier_query
    
    async def _query_tier_safe(
        self,
        tier_name: str,
        query: MemoryQuery,
        session_context: Optional[Dict[str, Any]]
    ) -> List[RecordEnvelope]:
        """Safely query a memory tier with error handling."""
        try:
            tier_adapter = self.registry.tier_stores[tier_name]
            
            # Check if tier is healthy before querying
            if hasattr(tier_adapter, 'is_healthy') and not tier_adapter.is_healthy:
                self.logger.warning(f"Tier {tier_name} is unhealthy, skipping")
                return []
            
            # Query the tier
            memories = await tier_adapter.retrieve_memories(query, session_context)
            
            self.logger.debug(
                f"Retrieved {len(memories)} memories from tier {tier_name}"
            )
            
            return memories
        
        except Exception as e:
            self.logger.warning(f"Error querying tier {tier_name}: {e}")
            return []
    
    async def _score_memories(
        self,
        tier_memories: Dict[str, List[RecordEnvelope]],
        query: MemoryQuery,
        session_context: Optional[Dict[str, Any]]
    ) -> List[ScoredRecord]:
        """Score all retrieved memories for relevance."""
        scored_memories = []
        
        # Get query embedding for similarity scoring
        query_embedding = None
        if hasattr(query, 'embedding') and query.embedding:
            query_embedding = query.embedding
        elif query.query_text and self.registry.embedding_providers:
            try:
                # Use first available embedding provider
                provider = next(iter(self.registry.embedding_providers.values()))
                query_embedding = await provider.embed_text(query.query_text)
            except Exception as e:
                self.logger.warning(f"Failed to generate query embedding: {e}")
        
        # Score memories from each tier
        for tier_name, memories in tier_memories.items():
            tier_priority = self.tier_priorities.get(tier_name, 0.3)
            
            for memory in memories:
                score = await self._calculate_memory_score(
                    memory, query, query_embedding, tier_priority, session_context
                )
                
                scored_record = ScoredRecord(
                    record=memory,
                    score=score,
                    tier_source=tier_name
                )
                
                # Only include if above minimum threshold
                if scored_record.total_score >= self.config.min_relevance_threshold:
                    scored_memories.append(scored_record)
        
        # Sort by total score (descending)
        scored_memories.sort(key=lambda x: x.total_score, reverse=True)
        
        return scored_memories
    
    async def _calculate_memory_score(
        self,
        memory: RecordEnvelope,
        query: MemoryQuery,
        query_embedding: Optional[List[float]],
        tier_priority: float,
        session_context: Optional[Dict[str, Any]]
    ) -> ContextScore:
        """Calculate comprehensive relevance score for a memory."""
        score = ContextScore()
        
        # Tier priority score
        score.tier_priority = tier_priority
        
        # Semantic similarity (if embeddings available)
        if query_embedding and memory.embedding:
            try:
                # Calculate cosine similarity
                similarity = self._cosine_similarity(query_embedding, memory.embedding)
                score.semantic_similarity = max(0.0, similarity)
            except Exception as e:
                self.logger.debug(f"Error calculating similarity: {e}")
        
        # Temporal relevance
        if memory.created_at:
            hours_ago = (datetime.utcnow() - memory.created_at).total_seconds() / 3600
            if hours_ago <= 1:
                score.temporal_relevance = 1.0
            elif hours_ago <= 24:
                score.temporal_relevance = 0.8
            elif hours_ago <= 168:  # 1 week
                score.temporal_relevance = 0.5
            else:
                score.temporal_relevance = 0.2
        
        # Access frequency (from metadata)
        access_count = memory.metadata.get("access_count", 0)
        if access_count > 10:
            score.access_frequency = 1.0
        elif access_count > 5:
            score.access_frequency = 0.7
        elif access_count > 1:
            score.access_frequency = 0.5
        else:
            score.access_frequency = 0.2
        
        # Authority score (from confidence or source)
        confidence = memory.metadata.get("confidence", 0.5)
        source_authority = memory.metadata.get("source_authority", 0.5)
        score.authority_score = (confidence + source_authority) / 2
        
        # Completeness score (based on content richness)
        content_length = len(str(memory.content))
        if content_length > 500:
            score.completeness_score = 1.0
        elif content_length > 200:
            score.completeness_score = 0.8
        elif content_length > 50:
            score.completeness_score = 0.6
        else:
            score.completeness_score = 0.3
        
        # Age penalty for very old memories
        if memory.created_at:
            days_ago = (datetime.utcnow() - memory.created_at).days
            if days_ago > 30:
                score.age_penalty = min(0.3, days_ago / 365.0)
        
        return score
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if len(vec1) != len(vec2):
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    async def _apply_diversity_filter(
        self, 
        scored_memories: List[ScoredRecord]
    ) -> List[ScoredRecord]:
        """Apply diversity filtering to avoid redundant information."""
        if len(scored_memories) <= self.config.max_records_per_tier:
            return scored_memories
        
        filtered_memories = []
        tier_counts = defaultdict(int)
        
        # Track seen content for diversity
        seen_content_hashes = set()
        
        for memory in scored_memories:
            # Limit per tier
            if tier_counts[memory.tier_source] >= self.config.max_records_per_tier:
                continue
            
            # Check for content diversity
            content_hash = hash(str(memory.record.content))
            if content_hash in seen_content_hashes:
                # Apply redundancy penalty
                memory.score.redundancy_penalty += 0.2
                if memory.total_score < self.config.min_relevance_threshold:
                    continue
            
            seen_content_hashes.add(content_hash)
            tier_counts[memory.tier_source] += 1
            filtered_memories.append(memory)
        
        return filtered_memories
    
    async def _resolve_conflicts(
        self, 
        memories: List[ScoredRecord]
    ) -> List[ScoredRecord]:
        """Resolve conflicts between memories."""
        # Group memories by topic/entity for conflict detection
        topic_groups = defaultdict(list)
        
        for memory in memories:
            # Extract key topics/entities from memory
            topics = self._extract_topics(memory.record)
            for topic in topics:
                topic_groups[topic].append(memory)
        
        # Detect and resolve conflicts within topic groups
        resolved_memories = []
        processed_ids = set()
        
        for memory in memories:
            if memory.record.record_id in processed_ids:
                continue
            
            # Find potential conflicts
            conflicts = self._find_conflicts(memory, memories)
            
            if conflicts:
                # Choose the highest-scoring non-conflicting memory
                best_memory = max([memory] + conflicts, key=lambda m: m.total_score)
                
                # Apply conflict penalty to others
                for conflict in conflicts:
                    if conflict != best_memory:
                        conflict.score.conflict_penalty += 0.1
                        processed_ids.add(conflict.record.record_id)
                
                resolved_memories.append(best_memory)
                processed_ids.add(best_memory.record.record_id)
            else:
                resolved_memories.append(memory)
                processed_ids.add(memory.record.record_id)
        
        return resolved_memories
    
    def _extract_topics(self, record: RecordEnvelope) -> List[str]:
        """Extract key topics/entities from a memory record."""
        # Simple topic extraction (can be enhanced with NLP)
        topics = []
        
        # From namespace and tags
        if record.namespace:
            topics.append(record.namespace.lower())
        
        if hasattr(record.metadata, 'tags') and record.metadata.get('tags'):
            topics.extend([tag.lower() for tag in record.metadata['tags']])
        
        # From content keywords (simple keyword extraction)
        content_text = str(record.content).lower()
        
        # Extract potential entities/topics (simple heuristic)
        import re
        
        # Look for capitalized words (potential entities)
        entities = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', str(record.content))
        topics.extend([entity.lower() for entity in entities[:5]])  # Limit to 5
        
        return list(set(topics))
    
    def _find_conflicts(
        self, 
        memory: ScoredRecord, 
        all_memories: List[ScoredRecord]
    ) -> List[ScoredRecord]:
        """Find memories that might conflict with the given memory."""
        conflicts = []
        
        memory_topics = set(self._extract_topics(memory.record))
        
        for other in all_memories:
            if other.record.record_id == memory.record.record_id:
                continue
            
            other_topics = set(self._extract_topics(other.record))
            
            # Check for topic overlap
            if memory_topics & other_topics:  # Intersection
                # Check for potential factual conflicts (heuristic)
                if self._might_conflict(memory.record, other.record):
                    conflicts.append(other)
        
        return conflicts
    
    def _might_conflict(self, record1: RecordEnvelope, record2: RecordEnvelope) -> bool:
        """Heuristic to determine if two records might contain conflicting information."""
        # Simple conflict detection based on contradictory keywords
        conflict_patterns = [
            ("is", "is not"),
            ("true", "false"),
            ("yes", "no"),
            ("correct", "incorrect"),
            ("valid", "invalid")
        ]
        
        content1 = str(record1.content).lower()
        content2 = str(record2.content).lower()
        
        for pos_word, neg_word in conflict_patterns:
            if pos_word in content1 and neg_word in content2:
                return True
            if neg_word in content1 and pos_word in content2:
                return True
        
        return False
    
    async def _optimize_context_selection(
        self, 
        memories: List[ScoredRecord],
        query: MemoryQuery
    ) -> List[ScoredRecord]:
        """Optimize final context selection for coherence and size."""
        if not memories:
            return []
        
        # Calculate coherence scores between memories
        for i, memory1 in enumerate(memories):
            coherence_sum = 0.0
            coherence_count = 0
            
            for j, memory2 in enumerate(memories):
                if i != j and memory1.record.embedding and memory2.record.embedding:
                    similarity = self._cosine_similarity(
                        memory1.record.embedding,
                        memory2.record.embedding
                    )
                    coherence_sum += similarity
                    coherence_count += 1
            
            if coherence_count > 0:
                memory1.score.coherence_score = coherence_sum / coherence_count
        
        # Select memories within size constraints
        selected_memories = []
        current_size = 0
        
        # Re-sort by total score after coherence updates
        memories.sort(key=lambda x: x.total_score, reverse=True)
        
        for memory in memories:
            memory_size = len(str(memory.record.content))
            
            # Check if adding this memory would exceed limits
            if (current_size + memory_size <= self.config.max_context_size and
                len(selected_memories) < query.limit):
                
                selected_memories.append(memory)
                current_size += memory_size
                
                # Check if we've reached target size
                if current_size >= self.config.target_context_size:
                    break
        
        return selected_memories
    
    async def _check_assembly_cache(
        self, 
        query: MemoryQuery
    ) -> Optional[List[ScoredRecord]]:
        """Check if context assembly is cached."""
        if not self.config.enable_caching:
            return None
        
        cache_key = self._generate_cache_key(query)
        
        if cache_key in self._assembly_cache:
            cached_result, timestamp = self._assembly_cache[cache_key]
            
            # Check if cache is still valid
            if datetime.utcnow() - timestamp < self._cache_ttl:
                return cached_result
            else:
                # Remove expired cache entry
                del self._assembly_cache[cache_key]
        
        return None
    
    async def _cache_assembly_result(
        self, 
        query: MemoryQuery,
        result: List[ScoredRecord]
    ) -> None:
        """Cache context assembly result."""
        if not self.config.enable_caching:
            return
        
        cache_key = self._generate_cache_key(query)
        self._assembly_cache[cache_key] = (result, datetime.utcnow())
        
        # Limit cache size
        max_cache_entries = 100
        if len(self._assembly_cache) > max_cache_entries:
            # Remove oldest entries
            oldest_key = min(
                self._assembly_cache.keys(),
                key=lambda k: self._assembly_cache[k][1]
            )
            del self._assembly_cache[oldest_key]
    
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
    
    async def _perform_health_check(self) -> Dict[str, Any]:
        """Perform context assembly engine health check."""
        # Check registry availability
        available_tiers = len(self.registry.tier_stores)
        available_embedders = len(self.registry.embedding_providers)
        
        # Test a simple assembly operation
        test_query = MemoryQuery(
            query_text="test",
            limit=1,
            similarity_threshold=0.9
        )
        
        try:
            start_time = time.time()
            await self._retrieve_from_tiers(test_query, None)
            test_duration = time.time() - start_time
            test_success = True
        except Exception as e:
            test_duration = 0.0
            test_success = False
            self.logger.debug(f"Health check test failed: {e}")
        
        return {
            "available_tiers": available_tiers,
            "available_embedding_providers": available_embedders,
            "assemblies_performed": self._assemblies_performed,
            "cache_size": len(self._assembly_cache),
            "cache_hit_rate": self._cache_hits / max(1, self._assemblies_performed),
            "average_assembly_time": self._total_assembly_time / max(1, self._assemblies_performed),
            "average_context_size": self._average_context_size,
            "test_assembly_success": test_success,
            "test_assembly_duration": test_duration
        }
    
    async def get_assembly_stats(self) -> Dict[str, Any]:
        """Get detailed context assembly statistics."""
        base_stats = await self.get_stats()
        
        assembly_stats = {
            "assemblies_performed": self._assemblies_performed,
            "cache_hits": self._cache_hits,
            "cache_hit_rate": self._cache_hits / max(1, self._assemblies_performed),
            "total_assembly_time": self._total_assembly_time,
            "average_assembly_time": self._total_assembly_time / max(1, self._assemblies_performed),
            "average_context_size": self._average_context_size,
            "cache_size": len(self._assembly_cache),
            "config": {
                "max_context_size": self.config.max_context_size,
                "target_context_size": self.config.target_context_size,
                "min_relevance_threshold": self.config.min_relevance_threshold,
                "parallel_tier_queries": self.config.parallel_tier_queries,
                "enable_caching": self.config.enable_caching
            }
        }
        
        base_stats.update(assembly_stats)
        return base_stats
    
    async def clear_cache(self) -> int:
        """Clear the assembly cache and return number of entries cleared."""
        cleared_count = len(self._assembly_cache)
        self._assembly_cache.clear()
        return cleared_count