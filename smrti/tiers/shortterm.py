"""
Short-term Memory Tier Implementation

Bridges Working Memory and Long-term Memory with intelligent consolidation,
TTL-based aging, and automatic promotion strategies.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
import json
import logging
from dataclasses import dataclass
from enum import Enum

from ..adapters.storage.redis import RedisAdapter
from ..adapters.storage.memory_adapter import MemoryAdapter
from ..models.memory import MemoryItem, MemoryMetadata, AccessPattern


logger = logging.getLogger(__name__)


class ConsolidationStrategy(Enum):
    """Strategies for consolidating memories."""
    ACCESS_FREQUENCY = "access_frequency"
    RECENCY_WEIGHTED = "recency_weighted" 
    SEMANTIC_CLUSTERING = "semantic_clustering"
    TEMPORAL_BATCHING = "temporal_batching"


@dataclass
class ConsolidationConfig:
    """Configuration for consolidation behavior."""
    strategy: ConsolidationStrategy = ConsolidationStrategy.RECENCY_WEIGHTED
    promotion_threshold: int = 5  # Access count threshold
    consolidation_window: timedelta = timedelta(hours=1)
    max_items_per_batch: int = 100
    semantic_similarity_threshold: float = 0.85
    temporal_batch_size: timedelta = timedelta(minutes=15)


@dataclass 
class PromotionCandidate:
    """Candidate for promotion to Long-term Memory."""
    item: MemoryItem
    score: float
    reason: str
    consolidation_group: Optional[str] = None


class ShortTermMemory:
    """
    Short-term Memory Tier Implementation
    
    Bridges Working Memory and Long-term Memory with:
    - TTL-based aging and cleanup
    - Intelligent consolidation strategies  
    - Automatic promotion based on access patterns
    - Batch processing for efficiency
    - Tenant isolation
    """
    
    def __init__(
        self,
        redis_adapter: Optional[RedisAdapter] = None,
        memory_adapter: Optional[MemoryAdapter] = None,
        config: Optional[ConsolidationConfig] = None,
        tenant_id: str = "default"
    ):
        self.redis = redis_adapter
        self.memory = memory_adapter or MemoryAdapter(tenant_id=tenant_id)
        self.config = config or ConsolidationConfig()
        self.tenant_id = tenant_id
        
        # Internal state
        self._consolidation_lock = asyncio.Lock()
        self._promotion_callbacks: List[callable] = []
        self._stats = {
            "items_stored": 0,
            "items_promoted": 0,
            "consolidations_run": 0,
            "cache_hits": 0,
            "cache_misses": 0
        }
        
        # Background task for consolidation
        self._consolidation_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
    
    async def start(self) -> None:
        """Start background consolidation task."""
        if self._consolidation_task is None:
            self._consolidation_task = asyncio.create_task(self._consolidation_loop())
            logger.info(f"Short-term memory started for tenant {self.tenant_id}")
    
    async def stop(self) -> None:
        """Stop background tasks and cleanup."""
        self._shutdown_event.set()
        if self._consolidation_task:
            self._consolidation_task.cancel()
            try:
                await self._consolidation_task
            except asyncio.CancelledError:
                pass
        logger.info(f"Short-term memory stopped for tenant {self.tenant_id}")
    
    def register_promotion_callback(self, callback: callable) -> None:
        """Register callback for when items are promoted."""
        self._promotion_callbacks.append(callback)
    
    async def store(
        self,
        key: str,
        value: Any,
        metadata: Optional[MemoryMetadata] = None,
        ttl: Optional[timedelta] = None
    ) -> bool:
        """
        Store item in short-term memory with TTL.
        
        Args:
            key: Unique identifier
            value: Value to store
            metadata: Optional metadata
            ttl: Time to live (default: 6 hours)
            
        Returns:
            True if stored successfully
        """
        if ttl is None:
            ttl = timedelta(hours=6)  # Default STM retention
            
        # Create memory item
        now = datetime.now(timezone.utc)
        item = MemoryItem(
            key=key,
            value=value,
            metadata=metadata or MemoryMetadata(),
            created_at=now,
            accessed_at=now,
            expires_at=now + ttl
        )
        
        # Try Redis first, fallback to memory
        try:
            if self.redis:
                success = await self.redis.store(key, item.model_dump(), ttl=ttl)
                if success:
                    self._stats["items_stored"] += 1
                    return True
        except Exception as e:
            logger.warning(f"Redis storage failed, using memory fallback: {e}")
        
        # Fallback to memory adapter
        await self.memory.store(key, item.model_dump(), ttl=ttl)
        self._stats["items_stored"] += 1
        return True
    
    async def retrieve(self, key: str) -> Optional[MemoryItem]:
        """
        Retrieve item from short-term memory and update access pattern.
        
        Args:
            key: Item identifier
            
        Returns:
            MemoryItem if found, None otherwise
        """
        # Try Redis first
        try:
            if self.redis:
                data = await self.redis.retrieve(key)
                if data:
                    item = MemoryItem(**data)
                    await self._update_access_pattern(item)
                    self._stats["cache_hits"] += 1
                    return item
        except Exception as e:
            logger.warning(f"Redis retrieval failed, trying memory fallback: {e}")
        
        # Try memory adapter
        data = await self.memory.retrieve(key)
        if data:
            item = MemoryItem(**data)
            await self._update_access_pattern(item)
            self._stats["cache_hits"] += 1
            return item
            
        self._stats["cache_misses"] += 1
        return None
    
    async def batch_retrieve(self, keys: List[str]) -> Dict[str, MemoryItem]:
        """Retrieve multiple items efficiently."""
        results = {}
        
        # Try Redis batch operation first
        try:
            if self.redis:
                redis_results = await self.redis.batch_retrieve(keys)
                for key, data in redis_results.items():
                    if data:
                        item = MemoryItem(**data)
                        await self._update_access_pattern(item)
                        results[key] = item
                        self._stats["cache_hits"] += 1
                        
                # Remove found keys from remaining list
                remaining_keys = [k for k in keys if k not in results]
        except Exception as e:
            logger.warning(f"Redis batch retrieval failed: {e}")
            remaining_keys = keys
        
        # Try memory adapter for remaining keys
        for key in remaining_keys:
            data = await self.memory.retrieve(key)
            if data:
                item = MemoryItem(**data)
                await self._update_access_pattern(item)
                results[key] = item
                self._stats["cache_hits"] += 1
            else:
                self._stats["cache_misses"] += 1
        
        return results
    
    async def delete(self, key: str) -> bool:
        """Delete item from short-term memory."""
        success = False
        
        # Delete from Redis
        try:
            if self.redis:
                success = await self.redis.delete(key) or success
        except Exception as e:
            logger.warning(f"Redis deletion failed: {e}")
        
        # Delete from memory
        success = await self.memory.delete(key) or success
        
        return success
    
    async def list_keys(self, pattern: Optional[str] = None) -> List[str]:
        """List all keys in short-term memory."""
        keys = set()
        
        # Get Redis keys
        try:
            if self.redis:
                redis_keys = await self.redis.list_keys(pattern)
                keys.update(redis_keys)
        except Exception as e:
            logger.warning(f"Redis key listing failed: {e}")
        
        # Get memory keys
        memory_keys = await self.memory.list_keys(pattern)
        keys.update(memory_keys)
        
        return sorted(keys)
    
    async def cleanup_expired(self) -> int:
        """Remove expired items and return count of cleaned items."""
        cleaned_count = 0
        
        # Cleanup Redis (automatic TTL)
        try:
            if self.redis:
                # Redis handles TTL automatically, but we can check stats
                pass
        except Exception:
            pass
        
        # Cleanup memory adapter
        cleaned_count += await self.memory.cleanup_expired()
        
        return cleaned_count
    
    async def run_consolidation(self) -> Dict[str, Any]:
        """
        Run consolidation process to identify promotion candidates.
        
        Returns:
            Consolidation results and statistics
        """
        async with self._consolidation_lock:
            logger.info(f"Running consolidation for tenant {self.tenant_id}")
            
            # Get all items for analysis
            all_keys = await self.list_keys()
            if not all_keys:
                return {"candidates": [], "strategy": self.config.strategy.value}
            
            # Retrieve items in batches
            items = []
            for i in range(0, len(all_keys), self.config.max_items_per_batch):
                batch_keys = all_keys[i:i + self.config.max_items_per_batch]
                batch_items = await self.batch_retrieve(batch_keys)
                items.extend(batch_items.values())
            
            # Run consolidation strategy
            candidates = await self._identify_promotion_candidates(items)
            
            # Process promotions
            promoted_count = 0
            for candidate in candidates:
                if await self._promote_to_longterm(candidate):
                    promoted_count += 1
            
            self._stats["consolidations_run"] += 1
            self._stats["items_promoted"] += promoted_count
            
            result = {
                "candidates": len(candidates),
                "promoted": promoted_count,
                "strategy": self.config.strategy.value,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            logger.info(f"Consolidation completed: {result}")
            return result
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics."""
        redis_stats = {}
        memory_stats = await self.memory.get_statistics()
        
        try:
            if self.redis:
                redis_stats = await self.redis.get_statistics()
        except Exception:
            pass
        
        return {
            "shortterm_stats": self._stats.copy(),
            "redis_stats": redis_stats,
            "memory_stats": memory_stats,
            "config": {
                "strategy": self.config.strategy.value,
                "promotion_threshold": self.config.promotion_threshold,
                "consolidation_window": self.config.consolidation_window.total_seconds()
            }
        }
    
    # Private methods
    
    async def _update_access_pattern(self, item: MemoryItem) -> None:
        """Update access patterns for consolidation analysis."""
        now = datetime.now(timezone.utc)
        
        # Update access metadata
        if not item.metadata.access_patterns:
            item.metadata.access_patterns = []
        
        # Add new access pattern
        access_pattern = AccessPattern(
            timestamp=now,
            access_type="retrieval",
            context_size=len(str(item.value)) if item.value else 0
        )
        item.metadata.access_patterns.append(access_pattern)
        
        # Keep only recent access patterns (last 24 hours)
        cutoff = now - timedelta(hours=24)
        item.metadata.access_patterns = [
            p for p in item.metadata.access_patterns 
            if p.timestamp > cutoff
        ]
        
        # Update item
        item.accessed_at = now
        item.metadata.access_count += 1
        
        # Store updated item
        await self.store(item.key, item.value, item.metadata)
    
    async def _identify_promotion_candidates(
        self, 
        items: List[MemoryItem]
    ) -> List[PromotionCandidate]:
        """Identify items that should be promoted to Long-term Memory."""
        candidates = []
        now = datetime.now(timezone.utc)
        
        for item in items:
            score = 0.0
            reasons = []
            
            # Access frequency score
            access_count = item.metadata.access_count
            if access_count >= self.config.promotion_threshold:
                score += access_count * 0.3
                reasons.append(f"high_access_count({access_count})")
            
            # Recency score
            age_hours = (now - item.created_at).total_seconds() / 3600
            if age_hours > 1:  # Items older than 1 hour
                recency_score = min(age_hours / 24, 1.0)  # Normalize to 24 hours
                score += recency_score * 0.4
                reasons.append(f"age_score({recency_score:.2f})")
            
            # Access pattern score
            if item.metadata.access_patterns:
                pattern_diversity = len(set(p.access_type for p in item.metadata.access_patterns))
                score += pattern_diversity * 0.2
                reasons.append(f"pattern_diversity({pattern_diversity})")
            
            # Size-based scoring (larger items get priority)
            value_size = len(str(item.value)) if item.value else 0
            if value_size > 100:  # Items larger than 100 chars
                size_score = min(value_size / 1000, 1.0)  # Normalize to 1KB
                score += size_score * 0.1
                reasons.append(f"size_score({size_score:.2f})")
            
            # Create candidate if score is high enough
            if score > 0.5:  # Promotion threshold
                candidate = PromotionCandidate(
                    item=item,
                    score=score,
                    reason=", ".join(reasons)
                )
                candidates.append(candidate)
        
        # Sort by score (highest first)
        candidates.sort(key=lambda c: c.score, reverse=True)
        
        # Limit to max batch size
        return candidates[:self.config.max_items_per_batch]
    
    async def _promote_to_longterm(self, candidate: PromotionCandidate) -> bool:
        """Promote candidate to Long-term Memory."""
        try:
            # Call registered promotion callbacks
            for callback in self._promotion_callbacks:
                await callback(candidate.item, candidate.score, candidate.reason)
            
            # Remove from short-term memory after successful promotion
            await self.delete(candidate.item.key)
            
            logger.debug(
                f"Promoted item {candidate.item.key} to long-term memory "
                f"(score: {candidate.score:.2f}, reason: {candidate.reason})"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to promote item {candidate.item.key}: {e}")
            return False
    
    async def _consolidation_loop(self) -> None:
        """Background consolidation task."""
        while not self._shutdown_event.is_set():
            try:
                # Wait for consolidation window
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.config.consolidation_window.total_seconds()
                )
                break  # Shutdown requested
                
            except asyncio.TimeoutError:
                # Run consolidation
                try:
                    await self.run_consolidation()
                    await self.cleanup_expired()
                except Exception as e:
                    logger.error(f"Consolidation error: {e}")
                    
        logger.info("Consolidation loop terminated")