"""
Context Assembly - Adaptive Prompt Construction

Intelligently assembles context for LLM prompts with:
- Token budget management
- Priority-based section allocation
- Reduction strategies (summarization, clustering, pruning)
- Provenance tracking
- Multiple assembly strategies

Based on PRD Section 6: Context Assembly
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from collections import defaultdict
import hashlib

from ...models.memory import MemoryItem


logger = logging.getLogger(__name__)


class SectionPriority(Enum):
    """Priority levels for context sections."""
    REQUIRED = "required"  # Never reduced
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReductionStrategy(Enum):
    """Strategies for reducing context size."""
    SUMMARIZE = "summarize"  # Compress with summarization
    CLUSTER = "cluster"  # Merge similar items
    TRUNCATE = "truncate"  # Cut to limit
    DROP_LOWEST = "drop_lowest"  # Remove low-relevance items
    REMOVE_SECTION = "remove_section"  # Remove entire section


class AssemblyStrategy(Enum):
    """Context assembly strategies."""
    PRIORITY_WEIGHTED = "priority_weighted"  # Strict priority order
    RECENCY_BIASED = "recency_biased"  # Favor recent items
    RELEVANCE_OPTIMIZED = "relevance_optimized"  # Maximize relevance
    BALANCED = "balanced"  # Balance all factors


@dataclass
class AssemblyConfig:
    """Configuration for context assembly."""
    
    # Token budgeting
    default_token_budget: int = 8000
    min_token_budget: int = 500
    max_token_budget: int = 32000
    
    # Section allocation (fractions, must sum to ≤ 1.0)
    allocation_working: float = 0.10
    allocation_semantic: float = 0.25
    allocation_episodic: float = 0.25
    allocation_summaries: float = 0.20
    allocation_patterns: float = 0.10
    allocation_slack: float = 0.10
    
    # Reduction
    max_reduction_cycles: int = 5
    reduction_threshold: float = 1.05  # Trigger reduction at 105% budget
    
    # Token counting
    chars_per_token: float = 4.0  # Heuristic for fast estimation
    use_precise_counting: bool = False  # Use tiktoken (slower)
    
    # Assembly
    default_strategy: AssemblyStrategy = AssemblyStrategy.BALANCED
    enable_provenance: bool = True
    enable_caching: bool = True
    cache_ttl_seconds: int = 300  # 5 minutes
    
    def validate(self) -> None:
        """Validate configuration."""
        total = (
            self.allocation_working +
            self.allocation_semantic +
            self.allocation_episodic +
            self.allocation_summaries +
            self.allocation_patterns +
            self.allocation_slack
        )
        if abs(total - 1.0) > 0.01:
            logger.warning(
                f"Section allocations sum to {total:.2f}, expected 1.0"
            )


@dataclass
class ProvenanceRecord:
    """Provenance for a context fragment."""
    
    record_id: str
    tier: str  # working, short_term, long_term, episodic, semantic
    source_type: str  # FACT, EVENT, SUMMARY, PATTERN, WORKING
    
    original_tokens: int
    current_tokens: int
    
    relevance_score: float
    selection_reason: str  # top_k, explicit, high_importance, boosted
    
    transformations: List[Dict[str, Any]] = field(default_factory=list)
    
    def add_transformation(
        self,
        transform_type: str,
        **kwargs
    ) -> None:
        """Add a transformation record."""
        self.transformations.append({
            "type": transform_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **kwargs
        })
    
    def reduction_ratio(self) -> float:
        """Calculate total reduction ratio."""
        if self.original_tokens == 0:
            return 0.0
        return self.current_tokens / self.original_tokens


@dataclass
class ContextSection:
    """Single section of assembled context."""
    
    name: str
    priority: SectionPriority
    items: List[MemoryItem] = field(default_factory=list)
    
    # Token allocation
    allocated_tokens: int = 0
    current_tokens: int = 0
    
    # Provenance
    provenance_records: List[ProvenanceRecord] = field(default_factory=list)
    
    # Metadata
    relevance_scores: List[float] = field(default_factory=list)
    
    def is_over_budget(self) -> bool:
        """Check if section exceeds allocation."""
        return self.current_tokens > self.allocated_tokens
    
    def budget_usage(self) -> float:
        """Calculate budget usage ratio."""
        if self.allocated_tokens == 0:
            return 0.0
        return self.current_tokens / self.allocated_tokens


@dataclass
class AssembledContext:
    """Assembled context with metadata."""
    
    user_id: str
    query: str
    token_budget: int
    
    sections: List[ContextSection] = field(default_factory=list)
    
    # Token statistics
    estimated_tokens: int = 0
    actual_tokens: Optional[int] = None
    
    # Assembly metadata
    generated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    assembly_strategy: str = ""
    reductions_applied: int = 0
    discarded_items: int = 0
    
    # Performance
    assembly_time_ms: float = 0.0
    
    # Provenance
    all_provenance: List[ProvenanceRecord] = field(default_factory=list)
    
    # Version
    version: int = 1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "user_id": self.user_id,
            "query": self.query,
            "token_budget": self.token_budget,
            "estimated_tokens": self.estimated_tokens,
            "actual_tokens": self.actual_tokens,
            "sections": [
                {
                    "name": s.name,
                    "priority": s.priority.value,
                    "item_count": len(s.items),
                    "current_tokens": s.current_tokens,
                    "allocated_tokens": s.allocated_tokens
                }
                for s in self.sections
            ],
            "generated_at": self.generated_at.isoformat(),
            "assembly_strategy": self.assembly_strategy,
            "reductions_applied": self.reductions_applied,
            "discarded_items": self.discarded_items,
            "assembly_time_ms": self.assembly_time_ms,
            "version": self.version
        }
    
    def get_section(self, name: str) -> Optional[ContextSection]:
        """Get section by name."""
        for section in self.sections:
            if section.name == name:
                return section
        return None


class ContextAssembly:
    """
    Context Assembly Engine
    
    Adaptively constructs LLM context under token budget constraints:
    - Priority-based section allocation
    - Intelligent reduction strategies
    - Provenance tracking
    - Multiple assembly modes
    """
    
    def __init__(
        self,
        config: Optional[AssemblyConfig] = None,
        retrieval_engine = None,
        token_counter = None,
        summarizer = None
    ):
        self.config = config or AssemblyConfig()
        self.config.validate()
        
        self.retrieval_engine = retrieval_engine
        self.token_counter = token_counter
        self.summarizer = summarizer
        
        # Cache
        self._cache: Dict[str, AssembledContext] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        
        # Statistics
        self._stats = {
            "contexts_assembled": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "total_reductions": 0,
            "avg_assembly_time_ms": 0.0,
            "avg_token_utilization": 0.0
        }
        
        logger.info("ContextAssembly engine initialized")
    
    async def assemble(
        self,
        user_id: str,
        query: str,
        token_budget: Optional[int] = None,
        strategy: Optional[AssemblyStrategy] = None,
        sections_config: Optional[Dict[str, Any]] = None
    ) -> AssembledContext:
        """
        Assemble context for LLM prompt.
        
        Args:
            user_id: User identifier
            query: Query text
            token_budget: Token budget (uses default if None)
            strategy: Assembly strategy
            sections_config: Override section configuration
        
        Returns:
            AssembledContext with structured sections
        """
        start_time = time.time()
        self._stats["contexts_assembled"] += 1
        
        # Set budget
        budget = token_budget or self.config.default_token_budget
        budget = max(self.config.min_token_budget, 
                    min(budget, self.config.max_token_budget))
        
        # Check cache
        if self.config.enable_caching:
            cache_key = self._generate_cache_key(user_id, query, budget)
            cached = self._get_cached(cache_key)
            if cached:
                self._stats["cache_hits"] += 1
                return cached
            self._stats["cache_misses"] += 1
        
        # Determine strategy
        strat = strategy or self.config.default_strategy
        
        # Create initial sections
        sections = self._create_sections(budget, sections_config)
        
        # Retrieve content for each section
        await self._populate_sections(sections, user_id, query, strat)
        
        # Initial token counting
        self._count_tokens(sections)
        
        # Apply reductions if over budget
        total_tokens = sum(s.current_tokens for s in sections)
        reductions_applied = 0
        
        if total_tokens > budget * self.config.reduction_threshold:
            reductions_applied = await self._apply_reductions(
                sections,
                budget,
                strat
            )
        
        # Build assembled context
        context = AssembledContext(
            user_id=user_id,
            query=query,
            token_budget=budget,
            sections=sections,
            estimated_tokens=sum(s.current_tokens for s in sections),
            assembly_strategy=strat.value,
            reductions_applied=reductions_applied,
            assembly_time_ms=(time.time() - start_time) * 1000
        )
        
        # Collect provenance
        if self.config.enable_provenance:
            for section in sections:
                context.all_provenance.extend(section.provenance_records)
        
        # Update statistics
        self._update_stats(context)
        
        # Cache result
        if self.config.enable_caching:
            self._set_cached(cache_key, context)
        
        logger.debug(
            f"Context assembled: {context.estimated_tokens}/{budget} tokens, "
            f"{len(context.sections)} sections, "
            f"{reductions_applied} reductions in {context.assembly_time_ms:.1f}ms"
        )
        
        return context
    
    def _create_sections(
        self,
        budget: int,
        sections_config: Optional[Dict[str, Any]] = None
    ) -> List[ContextSection]:
        """Create initial section structure."""
        
        sections_config = sections_config or {}
        
        sections = [
            ContextSection(
                name="working",
                priority=SectionPriority.REQUIRED,
                allocated_tokens=int(budget * self.config.allocation_working)
            ),
            ContextSection(
                name="semantic_facts",
                priority=SectionPriority.HIGH,
                allocated_tokens=int(budget * self.config.allocation_semantic)
            ),
            ContextSection(
                name="episodic_recent",
                priority=SectionPriority.HIGH,
                allocated_tokens=int(budget * self.config.allocation_episodic)
            ),
            ContextSection(
                name="summaries",
                priority=SectionPriority.MEDIUM,
                allocated_tokens=int(budget * self.config.allocation_summaries)
            ),
            ContextSection(
                name="patterns",
                priority=SectionPriority.LOW,
                allocated_tokens=int(budget * self.config.allocation_patterns)
            )
        ]
        
        # Apply config overrides
        for section in sections:
            if section.name in sections_config:
                override = sections_config[section.name]
                if "allocated_tokens" in override:
                    section.allocated_tokens = override["allocated_tokens"]
                if "priority" in override:
                    section.priority = SectionPriority(override["priority"])
        
        return sections
    
    async def _populate_sections(
        self,
        sections: List[ContextSection],
        user_id: str,
        query: str,
        strategy: AssemblyStrategy
    ) -> None:
        """Populate sections with retrieved content."""
        
        # For now, create placeholder logic
        # In production, this would call retrieval engine
        
        if not self.retrieval_engine:
            logger.warning("No retrieval engine configured")
            return
        
        # Parallel retrieval for each section
        tasks = []
        for section in sections:
            task = self._retrieve_for_section(section, user_id, query, strategy)
            tasks.append(task)
        
        await asyncio.gather(*tasks)
    
    async def _retrieve_for_section(
        self,
        section: ContextSection,
        user_id: str,
        query: str,
        strategy: AssemblyStrategy
    ) -> None:
        """Retrieve content for a specific section."""
        
        # This is a placeholder
        # In production, would call appropriate retrieval methods
        
        # For now, just log
        logger.debug(f"Retrieving content for section: {section.name}")
    
    def _count_tokens(self, sections: List[ContextSection]) -> None:
        """Count tokens in all sections."""
        
        for section in sections:
            total = 0
            for item in section.items:
                tokens = self._estimate_item_tokens(item)
                total += tokens
            section.current_tokens = total
    
    def _estimate_item_tokens(self, item: MemoryItem) -> int:
        """Estimate tokens for a memory item."""
        
        if self.token_counter and self.config.use_precise_counting:
            # Use precise counter if available
            text = self._extract_text(item)
            return self.token_counter.count(text)
        else:
            # Use heuristic
            text = self._extract_text(item)
            return int(len(text) / self.config.chars_per_token)
    
    def _extract_text(self, item: MemoryItem) -> str:
        """Extract text from memory item."""
        if isinstance(item.value, str):
            return item.value
        elif isinstance(item.value, dict):
            return item.value.get("content", str(item.value))
        else:
            return str(item.value)
    
    async def _apply_reductions(
        self,
        sections: List[ContextSection],
        budget: int,
        strategy: AssemblyStrategy
    ) -> int:
        """Apply reduction strategies to fit budget."""
        
        reductions_applied = 0
        
        for cycle in range(self.config.max_reduction_cycles):
            total_tokens = sum(s.current_tokens for s in sections)
            
            if total_tokens <= budget:
                break  # Within budget
            
            # Apply reduction strategy
            reduced = await self._apply_reduction_cycle(
                sections,
                budget,
                strategy
            )
            
            if reduced:
                reductions_applied += 1
            else:
                # No more reductions possible
                break
        
        # Final fallback if still over budget
        total_tokens = sum(s.current_tokens for s in sections)
        if total_tokens > budget:
            self._apply_fallback_reduction(sections, budget)
            reductions_applied += 1
        
        return reductions_applied
    
    async def _apply_reduction_cycle(
        self,
        sections: List[ContextSection],
        budget: int,
        strategy: AssemblyStrategy
    ) -> bool:
        """Apply one cycle of reductions."""
        
        # Sort sections by priority (low priority first)
        priority_order = [
            SectionPriority.LOW,
            SectionPriority.MEDIUM,
            SectionPriority.HIGH,
            SectionPriority.REQUIRED
        ]
        
        for priority in priority_order:
            priority_sections = [
                s for s in sections
                if s.priority == priority and s.is_over_budget()
            ]
            
            for section in priority_sections:
                # Try different reduction strategies
                if await self._reduce_section(section, budget, strategy):
                    return True
        
        return False
    
    async def _reduce_section(
        self,
        section: ContextSection,
        budget: int,
        strategy: AssemblyStrategy
    ) -> bool:
        """Reduce a single section."""
        
        if not section.items:
            return False
        
        # Choose reduction strategy based on section type
        if section.name == "episodic_recent":
            return await self._reduce_episodic(section)
        elif section.name == "semantic_facts":
            return await self._reduce_semantic(section)
        elif section.name == "summaries":
            return await self._reduce_summaries(section)
        elif section.name == "patterns":
            return await self._reduce_patterns(section)
        else:
            return self._reduce_generic(section)
    
    async def _reduce_episodic(self, section: ContextSection) -> bool:
        """Reduce episodic section by summarization."""
        
        if len(section.items) == 0:
            return False
        
        # Summarize if summarizer available
        if self.summarizer:
            # Combine items and summarize
            combined_text = "\n".join(
                self._extract_text(item) for item in section.items
            )
            
            summary = await self.summarizer.summarize(
                combined_text,
                max_length=section.allocated_tokens
            )
            
            # Replace with summary (placeholder)
            # In production, would create summary item
            logger.debug(f"Summarized episodic section")
            return True
        else:
            # Fallback: remove oldest items
            section.items = section.items[1:]
            self._count_tokens([section])
            return True
    
    async def _reduce_semantic(self, section: ContextSection) -> bool:
        """Reduce semantic facts by clustering."""
        
        if len(section.items) <= 1:
            return False
        
        # Drop lowest relevance item
        if section.relevance_scores:
            min_idx = section.relevance_scores.index(
                min(section.relevance_scores)
            )
            section.items.pop(min_idx)
            section.relevance_scores.pop(min_idx)
            self._count_tokens([section])
            return True
        else:
            # Remove last item
            section.items.pop()
            self._count_tokens([section])
            return True
    
    async def _reduce_summaries(self, section: ContextSection) -> bool:
        """Reduce summaries section."""
        
        if len(section.items) == 0:
            return False
        
        # Remove one summary
        section.items.pop()
        self._count_tokens([section])
        return True
    
    async def _reduce_patterns(self, section: ContextSection) -> bool:
        """Reduce patterns section."""
        
        if len(section.items) == 0:
            return False
        
        # Remove entire patterns section if LOW priority
        section.items.clear()
        self._count_tokens([section])
        return True
    
    def _reduce_generic(self, section: ContextSection) -> bool:
        """Generic reduction - remove last item."""
        
        if len(section.items) == 0:
            return False
        
        section.items.pop()
        self._count_tokens([section])
        return True
    
    def _apply_fallback_reduction(
        self,
        sections: List[ContextSection],
        budget: int
    ) -> None:
        """Fallback: keep only essential content."""
        
        # Keep only REQUIRED sections
        for section in sections:
            if section.priority != SectionPriority.REQUIRED:
                section.items.clear()
                section.current_tokens = 0
        
        # If still over budget, truncate REQUIRED sections
        total = sum(s.current_tokens for s in sections)
        if total > budget:
            for section in sections:
                if section.priority == SectionPriority.REQUIRED:
                    # Keep only first few items
                    target_tokens = section.allocated_tokens
                    while section.current_tokens > target_tokens and section.items:
                        section.items.pop()
                        self._count_tokens([section])
    
    def _generate_cache_key(
        self,
        user_id: str,
        query: str,
        budget: int
    ) -> str:
        """Generate cache key."""
        key_str = f"{user_id}|{query}|{budget}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _get_cached(self, key: str) -> Optional[AssembledContext]:
        """Get cached context."""
        if key not in self._cache:
            return None
        
        timestamp = self._cache_timestamps.get(key)
        if not timestamp:
            return None
        
        age = (datetime.now(timezone.utc) - timestamp).total_seconds()
        if age > self.config.cache_ttl_seconds:
            del self._cache[key]
            del self._cache_timestamps[key]
            return None
        
        return self._cache[key]
    
    def _set_cached(self, key: str, context: AssembledContext) -> None:
        """Cache context."""
        self._cache[key] = context
        self._cache_timestamps[key] = datetime.now(timezone.utc)
    
    def _update_stats(self, context: AssembledContext) -> None:
        """Update statistics."""
        count = self._stats["contexts_assembled"]
        
        # Update average assembly time
        current_avg = self._stats["avg_assembly_time_ms"]
        new_avg = ((current_avg * (count - 1)) + context.assembly_time_ms) / count
        self._stats["avg_assembly_time_ms"] = new_avg
        
        # Update average token utilization
        utilization = context.estimated_tokens / context.token_budget
        current_util = self._stats["avg_token_utilization"]
        new_util = ((current_util * (count - 1)) + utilization) / count
        self._stats["avg_token_utilization"] = new_util
        
        # Update reductions
        self._stats["total_reductions"] += context.reductions_applied
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get assembly statistics."""
        return self._stats.copy()
    
    def clear_cache(self) -> None:
        """Clear all caches."""
        self._cache.clear()
        self._cache_timestamps.clear()
        logger.info("Cache cleared")
