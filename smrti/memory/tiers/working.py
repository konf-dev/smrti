"""
smrti/memory/tiers/working.py - Working Memory Tier

Working memory for immediate, temporary information with very short retention
and high-speed access. Optimized for current context and active processing.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Union

from smrti.core.base import BaseMemoryTier
from smrti.core.exceptions import MemoryError, ValidationError
from smrti.core.protocols import TierStore
from smrti.core.registry import AdapterRegistry
from smrti.schemas.models import (
    MemoryQuery,
    RecordEnvelope,
    # ConversationTurn,  # TODO: Add back when defined
    ContextRecord,
    WorkingMemoryConfig
)


class WorkingMemory(BaseMemoryTier):
    """
    Working Memory Tier - Immediate, temporary information storage.
    
    Characteristics:
    - Very short retention (seconds to minutes)
    - High-speed access and updates
    - Limited capacity (few dozen items)
    - Volatile storage (Redis with short TTL)
    - Context-aware organization
    - Real-time updates
    
    Use cases:
    - Current conversation context
    - Active task variables
    - Immediate user input processing
    - Temporary computation results
    - Current session state
    """
    
    def __init__(
        self,
        adapter_registry: AdapterRegistry,
        config: Optional[WorkingMemoryConfig] = None
    ):
        super().__init__(
            tier_name="working",
            adapter_registry=adapter_registry,
            config=config
        )
        
        # Working memory configuration
        self._default_ttl = timedelta(minutes=config.retention_minutes if config else 5)
        self._max_capacity = config.max_items if config else 50
        self._cleanup_interval = timedelta(minutes=config.cleanup_interval_minutes if config else 1)
        
        # Context management
        self._active_contexts: Dict[str, Set[str]] = {}  # session_id -> record_ids
        self._context_priorities: Dict[str, float] = {}  # record_id -> priority
        
        # Performance tracking
        self._access_patterns: Dict[str, List[datetime]] = {}
        self._last_cleanup = datetime.utcnow()
        
        # Working memory specific settings
        self._enable_context_awareness = config.enable_context_awareness if config else True
        self._auto_expire_inactive = config.auto_expire_inactive if config else True
        self._priority_threshold = config.priority_threshold if config else 0.1
        
    async def initialize(self) -> None:
        """Initialize working memory tier with Redis adapter."""
        # Get Redis adapter for working memory
        adapter = await self._adapter_registry.get_adapter(
            tier_name="working",
            required_capabilities=["ttl_support", "atomic_operations"]
        )
        
        if not adapter:
            raise MemoryError(
                "No suitable adapter found for working memory tier",
                tier="working",
                operation="initialize"
            )
        
        self._storage = adapter
        await super().initialize()
        
        # Start background cleanup task
        asyncio.create_task(self._periodic_cleanup())
        
        self.logger.info(
            f"Working memory initialized (max_capacity={self._max_capacity}, "
            f"default_ttl={self._default_ttl.total_seconds()}s)"
        )
    
    async def store(
        self, 
        record: RecordEnvelope,
        priority: float = 0.5,
        context_id: Optional[str] = None,
        ttl: Optional[timedelta] = None
    ) -> str:
        """
        Store information in working memory with priority and context.
        
        Args:
            record: Memory record to store
            priority: Priority level (0.0-1.0, higher = more important)
            context_id: Optional context identifier for grouping
            ttl: Time-to-live override (defaults to tier default)
            
        Returns:
            Record ID of stored memory
        """
        # Validate capacity before storing
        if await self._is_at_capacity():
            await self._evict_lowest_priority_items(1)
        
        # Set working memory tier
        record.tier = "working"
        
        # Use default TTL if not specified
        effective_ttl = ttl or self._default_ttl
        
        # Store in adapter with TTL
        record_id = await self._storage.store(record, effective_ttl)
        
        # Track context association
        if context_id:
            if context_id not in self._active_contexts:
                self._active_contexts[context_id] = set()
            self._active_contexts[context_id].add(record_id)
        
        # Track priority
        self._context_priorities[record_id] = priority
        
        # Track access pattern
        self._track_access(record_id)
        
        self.logger.debug(
            f"Stored record {record_id} in working memory "
            f"(priority={priority}, ttl={effective_ttl.total_seconds()}s)"
        )
        
        return record_id
    
    async def retrieve(
        self, 
        record_id: str,
        update_access: bool = True
    ) -> Optional[RecordEnvelope]:
        """Retrieve a specific record from working memory."""
        record = await self._storage.retrieve(record_id)
        
        if record and update_access:
            self._track_access(record_id)
            
            # Boost priority for frequently accessed items
            if record_id in self._context_priorities:
                current_priority = self._context_priorities[record_id]
                self._context_priorities[record_id] = min(1.0, current_priority + 0.05)
        
        return record
    
    async def query(
        self,
        query: MemoryQuery,
        context_id: Optional[str] = None,
        priority_boost: bool = True
    ) -> List[RecordEnvelope]:
        """
        Query working memory with context awareness.
        
        Args:
            query: Memory query parameters
            context_id: Optional context to focus search
            priority_boost: Whether to boost results by priority
            
        Returns:
            List of matching records, sorted by relevance and priority
        """
        # Query the storage adapter
        results = await self._storage.query(query)
        
        # Apply context filtering if specified
        if context_id and context_id in self._active_contexts:
            context_records = self._active_contexts[context_id]
            results = [r for r in results if r.record_id in context_records]
        
        # Apply priority boosting
        if priority_boost:
            for record in results:
                if record.record_id in self._context_priorities:
                    priority = self._context_priorities[record.record_id]
                    record.relevance_score *= (1.0 + priority)
        
        # Sort by enhanced relevance score
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        
        # Track access for all returned records
        for record in results:
            self._track_access(record.record_id)
        
        return results
    
    async def get_active_context(
        self, 
        context_id: str,
        max_items: int = 20
    ) -> List[RecordEnvelope]:
        """Get all records in an active context, sorted by priority."""
        if context_id not in self._active_contexts:
            return []
        
        record_ids = list(self._active_contexts[context_id])
        
        # Sort by priority
        record_ids.sort(
            key=lambda rid: self._context_priorities.get(rid, 0.0),
            reverse=True
        )
        
        # Retrieve records (limit to max_items)
        records = []
        for record_id in record_ids[:max_items]:
            record = await self.retrieve(record_id, update_access=False)
            if record:
                records.append(record)
        
        return records
    
    async def update_priority(
        self, 
        record_id: str, 
        new_priority: float
    ) -> bool:
        """Update the priority of a record in working memory."""
        if record_id not in self._context_priorities:
            return False
        
        # Validate priority range
        new_priority = max(0.0, min(1.0, new_priority))
        self._context_priorities[record_id] = new_priority
        
        # Also update in storage if supported
        if hasattr(self._storage, 'update_relevance'):
            await self._storage.update_relevance(record_id, new_priority)
        
        return True
    
    async def expire_context(self, context_id: str) -> int:
        """Expire all records in a specific context."""
        if context_id not in self._active_contexts:
            return 0
        
        record_ids = list(self._active_contexts[context_id])
        expired_count = 0
        
        for record_id in record_ids:
            if await self._storage.delete(record_id):
                expired_count += 1
                # Clean up tracking
                self._context_priorities.pop(record_id, None)
                self._access_patterns.pop(record_id, None)
        
        # Remove context
        del self._active_contexts[context_id]
        
        self.logger.info(f"Expired context {context_id}: {expired_count} records")
        return expired_count
    
    async def consolidate_to_short_term(
        self, 
        min_access_count: int = 3,
        min_priority: float = 0.7
    ) -> List[str]:
        """
        Consolidate frequently accessed or high-priority items to short-term memory.
        
        Returns list of record IDs that were consolidated.
        """
        candidates = []
        
        # Find consolidation candidates
        for record_id, priority in self._context_priorities.items():
            access_count = len(self._access_patterns.get(record_id, []))
            
            if access_count >= min_access_count or priority >= min_priority:
                record = await self.retrieve(record_id, update_access=False)
                if record:
                    candidates.append((record, priority, access_count))
        
        # Get short-term memory tier for consolidation
        short_term_tier = await self._adapter_registry.get_tier("short_term")
        if not short_term_tier:
            self.logger.warning("Short-term memory tier not available for consolidation")
            return []
        
        consolidated = []
        
        for record, priority, access_count in candidates:
            try:
                # Store in short-term memory with extended TTL
                await short_term_tier.store(
                    record, 
                    priority=priority,
                    access_history=self._access_patterns.get(record.record_id, [])
                )
                
                # Remove from working memory
                await self._storage.delete(record.record_id)
                self._cleanup_record_tracking(record.record_id)
                
                consolidated.append(record.record_id)
                
                self.logger.debug(
                    f"Consolidated record {record.record_id} to short-term "
                    f"(priority={priority}, access_count={access_count})"
                )
                
            except Exception as e:
                self.logger.error(f"Failed to consolidate record {record.record_id}: {e}")
        
        if consolidated:
            self.logger.info(f"Consolidated {len(consolidated)} records to short-term memory")
        
        return consolidated
    
    def _track_access(self, record_id: str) -> None:
        """Track access patterns for a record."""
        now = datetime.utcnow()
        
        if record_id not in self._access_patterns:
            self._access_patterns[record_id] = []
        
        self._access_patterns[record_id].append(now)
        
        # Keep only recent access times (last hour)
        cutoff = now - timedelta(hours=1)
        self._access_patterns[record_id] = [
            access_time for access_time in self._access_patterns[record_id]
            if access_time > cutoff
        ]
    
    async def _is_at_capacity(self) -> bool:
        """Check if working memory is at capacity."""
        # This is a simplified check - in production you might query the storage
        return len(self._context_priorities) >= self._max_capacity
    
    async def _evict_lowest_priority_items(self, count: int = 1) -> int:
        """Evict the lowest priority items to make space."""
        if not self._context_priorities:
            return 0
        
        # Sort by priority (lowest first)
        sorted_items = sorted(
            self._context_priorities.items(),
            key=lambda x: (x[1], len(self._access_patterns.get(x[0], [])))
        )
        
        evicted = 0
        for record_id, _ in sorted_items[:count]:
            if await self._storage.delete(record_id):
                self._cleanup_record_tracking(record_id)
                evicted += 1
        
        if evicted > 0:
            self.logger.info(f"Evicted {evicted} lowest priority items from working memory")
        
        return evicted
    
    def _cleanup_record_tracking(self, record_id: str) -> None:
        """Clean up tracking data for a record."""
        self._context_priorities.pop(record_id, None)
        self._access_patterns.pop(record_id, None)
        
        # Remove from active contexts
        for context_id, record_ids in self._active_contexts.items():
            record_ids.discard(record_id)
    
    async def _periodic_cleanup(self) -> None:
        """Periodic cleanup of expired items and stale tracking data."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval.total_seconds())
                
                now = datetime.utcnow()
                if now - self._last_cleanup < self._cleanup_interval:
                    continue
                
                # Clean up expired records from storage
                if hasattr(self._storage, 'cleanup_expired'):
                    expired_count = await self._storage.cleanup_expired()
                    if expired_count > 0:
                        self.logger.info(f"Cleaned up {expired_count} expired records")
                
                # Clean up stale tracking data
                stale_records = []
                for record_id in list(self._context_priorities.keys()):
                    record = await self._storage.retrieve(record_id)
                    if not record:
                        stale_records.append(record_id)
                
                for record_id in stale_records:
                    self._cleanup_record_tracking(record_id)
                
                # Clean up empty contexts
                empty_contexts = [
                    context_id for context_id, record_ids in self._active_contexts.items()
                    if not record_ids
                ]
                for context_id in empty_contexts:
                    del self._active_contexts[context_id]
                
                # Consolidate high-priority items if enabled
                if self._auto_expire_inactive and self._enable_context_awareness:
                    await self.consolidate_to_short_term()
                
                self._last_cleanup = now
                
            except Exception as e:
                self.logger.error(f"Error during working memory cleanup: {e}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get working memory statistics."""
        base_stats = await super().get_stats()
        
        # Calculate current metrics
        total_records = len(self._context_priorities)
        active_contexts = len(self._active_contexts)
        total_accesses = sum(len(accesses) for accesses in self._access_patterns.values())
        
        # Priority distribution
        priorities = list(self._context_priorities.values())
        avg_priority = sum(priorities) / len(priorities) if priorities else 0.0
        high_priority_count = len([p for p in priorities if p > 0.7])
        
        working_stats = {
            "tier_name": "working",
            "total_records": total_records,
            "capacity_utilization": total_records / self._max_capacity,
            "active_contexts": active_contexts,
            "total_accesses": total_accesses,
            "average_priority": avg_priority,
            "high_priority_records": high_priority_count,
            "default_ttl_seconds": self._default_ttl.total_seconds(),
            "cleanup_interval_seconds": self._cleanup_interval.total_seconds(),
            "last_cleanup": self._last_cleanup.isoformat(),
            "context_awareness_enabled": self._enable_context_awareness,
            "auto_expire_enabled": self._auto_expire_inactive
        }
        
        base_stats.update(working_stats)
        return base_stats
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check for working memory tier."""
        health = await super().health_check()
        
        # Working memory specific health metrics
        capacity_usage = len(self._context_priorities) / self._max_capacity
        health_status = "healthy"
        
        if capacity_usage > 0.9:
            health_status = "warning"
        elif capacity_usage > 0.95:
            health_status = "critical"
        
        working_health = {
            "capacity_usage": capacity_usage,
            "health_status": health_status,
            "active_contexts": len(self._active_contexts),
            "tracked_records": len(self._context_priorities),
            "cleanup_running": (datetime.utcnow() - self._last_cleanup) < self._cleanup_interval * 2
        }
        
        health.update(working_health)
        return health