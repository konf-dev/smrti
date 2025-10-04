"""
smrti/memory/tiers/short_term.py - Short-term Memory Tier

Short-term memory for recent information with moderate retention.
Bridge between working memory and long-term storage.
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
    ShortTermMemoryConfig
)


class ShortTermMemory(BaseMemoryTier):
    """
    Short-term Memory Tier - Recent information with moderate retention.
    
    Characteristics:
    - Moderate retention (minutes to hours)
    - Medium capacity (hundreds of items)
    - Redis storage with longer TTL
    - Access pattern tracking
    - Consolidation to long-term memory
    - Importance scoring
    
    Use cases:
    - Recent conversation history
    - Session-spanning context
    - Frequently referenced information
    - Preparation for long-term consolidation
    - Inter-session state persistence
    """
    
    def __init__(
        self,
        adapter_registry: AdapterRegistry,
        config: Optional[ShortTermMemoryConfig] = None
    ):
        super().__init__(
            tier_name="short_term",
            adapter_registry=adapter_registry,
            config=config
        )
        
        # Short-term memory configuration
        self._default_ttl = timedelta(hours=config.retention_hours if config else 24)
        self._max_capacity = config.max_items if config else 500
        self._consolidation_interval = timedelta(hours=config.consolidation_interval_hours if config else 6)
        
        # Access pattern tracking
        self._access_histories: Dict[str, List[datetime]] = {}
        self._importance_scores: Dict[str, float] = {}
        self._session_associations: Dict[str, Set[str]] = {}  # session_id -> record_ids
        
        # Consolidation tracking
        self._last_consolidation = datetime.utcnow()
        self._consolidation_candidates: Set[str] = set()
        
        # Configuration
        self._importance_decay_rate = config.importance_decay_rate if config else 0.1
        self._consolidation_threshold = config.consolidation_threshold if config else 0.8
        self._min_consolidation_age = timedelta(hours=config.min_consolidation_age_hours if config else 1)
        self._enable_importance_tracking = config.enable_importance_tracking if config else True
        
    async def initialize(self) -> None:
        """Initialize short-term memory tier with Redis adapter."""
        # Get Redis adapter for short-term memory
        adapter = await self._adapter_registry.get_adapter(
            tier_name="short_term",
            required_capabilities=["ttl_support", "atomic_operations"]
        )
        
        if not adapter:
            raise MemoryError(
                "No suitable adapter found for short-term memory tier",
                tier="short_term",
                operation="initialize"
            )
        
        self._storage = adapter
        await super().initialize()
        
        # Start background consolidation task
        asyncio.create_task(self._periodic_consolidation())
        
        self.logger.info(
            f"Short-term memory initialized (max_capacity={self._max_capacity}, "
            f"default_ttl={self._default_ttl.total_seconds()}s)"
        )
    
    async def store(
        self, 
        record: RecordEnvelope,
        importance: float = 0.5,
        session_id: Optional[str] = None,
        access_history: Optional[List[datetime]] = None,
        ttl: Optional[timedelta] = None
    ) -> str:
        """
        Store information in short-term memory with importance scoring.
        
        Args:
            record: Memory record to store
            importance: Importance level (0.0-1.0)
            session_id: Optional session association
            access_history: Previous access history from working memory
            ttl: Time-to-live override
            
        Returns:
            Record ID of stored memory
        """
        # Set short-term memory tier
        record.tier = "short_term"
        
        # Use default TTL if not specified
        effective_ttl = ttl or self._default_ttl
        
        # Store in adapter with TTL
        record_id = await self._storage.store(record, effective_ttl)
        
        # Track importance and access history
        if self._enable_importance_tracking:
            self._importance_scores[record_id] = importance
            
            if access_history:
                self._access_histories[record_id] = access_history.copy()
            else:
                self._access_histories[record_id] = [datetime.utcnow()]
        
        # Track session association
        if session_id:
            if session_id not in self._session_associations:
                self._session_associations[session_id] = set()
            self._session_associations[session_id].add(record_id)
        
        # Check if this should be a consolidation candidate
        if importance >= self._consolidation_threshold:
            self._consolidation_candidates.add(record_id)
        
        self.logger.debug(
            f"Stored record {record_id} in short-term memory "
            f"(importance={importance}, ttl={effective_ttl.total_seconds()}s)"
        )
        
        return record_id
    
    async def retrieve(
        self, 
        record_id: str,
        update_access: bool = True
    ) -> Optional[RecordEnvelope]:
        """Retrieve a specific record from short-term memory."""
        record = await self._storage.retrieve(record_id)
        
        if record and update_access:
            self._track_access(record_id)
            
            # Boost importance for frequently accessed items
            if record_id in self._importance_scores:
                current_importance = self._importance_scores[record_id]
                boost = min(0.1, 1.0 - current_importance)  # Diminishing returns
                self._importance_scores[record_id] = min(1.0, current_importance + boost)
                
                # Add to consolidation candidates if importance is high enough
                if self._importance_scores[record_id] >= self._consolidation_threshold:
                    self._consolidation_candidates.add(record_id)
        
        return record
    
    async def query(
        self,
        query: MemoryQuery,
        session_id: Optional[str] = None,
        importance_boost: bool = True
    ) -> List[RecordEnvelope]:
        """
        Query short-term memory with importance boosting.
        
        Args:
            query: Memory query parameters
            session_id: Optional session to focus search
            importance_boost: Whether to boost results by importance
            
        Returns:
            List of matching records, sorted by relevance and importance
        """
        # Query the storage adapter
        results = await self._storage.query(query)
        
        # Apply session filtering if specified
        if session_id and session_id in self._session_associations:
            session_records = self._session_associations[session_id]
            results = [r for r in results if r.record_id in session_records]
        
        # Apply importance boosting
        if importance_boost and self._enable_importance_tracking:
            for record in results:
                if record.record_id in self._importance_scores:
                    importance = self._importance_scores[record.record_id]
                    # Apply importance boost with decay over time
                    age_hours = (datetime.utcnow() - record.created_at).total_seconds() / 3600
                    decayed_importance = importance * (1.0 - self._importance_decay_rate * age_hours)
                    record.relevance_score *= (1.0 + decayed_importance)
        
        # Sort by enhanced relevance score
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        
        # Track access for all returned records
        for record in results:
            self._track_access(record.record_id)
        
        return results
    
    async def get_session_memories(
        self,
        session_id: str,
        max_items: int = 50,
        min_importance: float = 0.0
    ) -> List[RecordEnvelope]:
        """Get all memories associated with a specific session."""
        if session_id not in self._session_associations:
            return []
        
        record_ids = list(self._session_associations[session_id])
        
        # Filter by importance if specified
        if min_importance > 0.0 and self._enable_importance_tracking:
            record_ids = [
                rid for rid in record_ids
                if self._importance_scores.get(rid, 0.0) >= min_importance
            ]
        
        # Sort by importance and recency
        record_ids.sort(
            key=lambda rid: (
                self._importance_scores.get(rid, 0.0),
                len(self._access_histories.get(rid, [])),
                -hash(rid)  # Stable sort for consistent ordering
            ),
            reverse=True
        )
        
        # Retrieve records (limit to max_items)
        records = []
        for record_id in record_ids[:max_items]:
            record = await self.retrieve(record_id, update_access=False)
            if record:
                records.append(record)
        
        return records
    
    async def update_importance(
        self, 
        record_id: str, 
        new_importance: float
    ) -> bool:
        """Update the importance score of a record."""
        if not self._enable_importance_tracking:
            return False
        
        # Validate importance range
        new_importance = max(0.0, min(1.0, new_importance))
        self._importance_scores[record_id] = new_importance
        
        # Update consolidation candidate status
        if new_importance >= self._consolidation_threshold:
            self._consolidation_candidates.add(record_id)
        else:
            self._consolidation_candidates.discard(record_id)
        
        # Also update in storage if supported
        if hasattr(self._storage, 'update_relevance'):
            await self._storage.update_relevance(record_id, new_importance)
        
        return True
    
    async def expire_session(self, session_id: str) -> int:
        """Expire all records in a specific session."""
        if session_id not in self._session_associations:
            return 0
        
        record_ids = list(self._session_associations[session_id])
        expired_count = 0
        
        for record_id in record_ids:
            if await self._storage.delete(record_id):
                expired_count += 1
                # Clean up tracking
                self._cleanup_record_tracking(record_id)
        
        # Remove session
        del self._session_associations[session_id]
        
        self.logger.info(f"Expired session {session_id}: {expired_count} records")
        return expired_count
    
    async def consolidate_to_long_term(
        self,
        force_consolidation: bool = False,
        max_candidates: int = 50
    ) -> List[str]:
        """
        Consolidate important records to long-term memory.
        
        Args:
            force_consolidation: Whether to ignore normal thresholds
            max_candidates: Maximum number of records to consolidate
            
        Returns:
            List of record IDs that were consolidated
        """
        candidates = []
        
        # Get consolidation candidates
        candidate_records = list(self._consolidation_candidates)
        
        if not force_consolidation:
            # Filter by age and importance
            min_age = datetime.utcnow() - self._min_consolidation_age
            candidate_records = [
                record_id for record_id in candidate_records
                if record_id in self._importance_scores
                and self._importance_scores[record_id] >= self._consolidation_threshold
            ]
            
            # Check age requirement
            aged_candidates = []
            for record_id in candidate_records:
                record = await self.retrieve(record_id, update_access=False)
                if record and record.created_at <= min_age:
                    aged_candidates.append(record_id)
            
            candidate_records = aged_candidates
        
        # Limit to max_candidates
        candidate_records = candidate_records[:max_candidates]
        
        # Get long-term memory tier for consolidation
        long_term_tier = await self._adapter_registry.get_tier("long_term")
        if not long_term_tier:
            self.logger.warning("Long-term memory tier not available for consolidation")
            return []
        
        consolidated = []
        
        for record_id in candidate_records:
            try:
                record = await self.retrieve(record_id, update_access=False)
                if not record:
                    continue
                
                importance = self._importance_scores.get(record_id, 0.5)
                access_history = self._access_histories.get(record_id, [])
                
                # Store in long-term memory
                await long_term_tier.store(
                    record,
                    importance_score=importance,
                    access_frequency=len(access_history),
                    source_tier="short_term"
                )
                
                # Remove from short-term memory
                await self._storage.delete(record.record_id)
                self._cleanup_record_tracking(record_id)
                
                consolidated.append(record_id)
                
                self.logger.debug(
                    f"Consolidated record {record_id} to long-term "
                    f"(importance={importance}, accesses={len(access_history)})"
                )
                
            except Exception as e:
                self.logger.error(f"Failed to consolidate record {record_id}: {e}")
        
        if consolidated:
            self.logger.info(f"Consolidated {len(consolidated)} records to long-term memory")
        
        return consolidated
    
    def _track_access(self, record_id: str) -> None:
        """Track access patterns for a record."""
        now = datetime.utcnow()
        
        if record_id not in self._access_histories:
            self._access_histories[record_id] = []
        
        self._access_histories[record_id].append(now)
        
        # Keep only recent access times (last 24 hours)
        cutoff = now - timedelta(hours=24)
        self._access_histories[record_id] = [
            access_time for access_time in self._access_histories[record_id]
            if access_time > cutoff
        ]
    
    def _cleanup_record_tracking(self, record_id: str) -> None:
        """Clean up tracking data for a record."""
        self._importance_scores.pop(record_id, None)
        self._access_histories.pop(record_id, None)
        self._consolidation_candidates.discard(record_id)
        
        # Remove from session associations
        for session_id, record_ids in self._session_associations.items():
            record_ids.discard(record_id)
    
    async def _periodic_consolidation(self) -> None:
        """Periodic consolidation of important items to long-term memory."""
        while True:
            try:
                await asyncio.sleep(self._consolidation_interval.total_seconds())
                
                now = datetime.utcnow()
                if now - self._last_consolidation < self._consolidation_interval:
                    continue
                
                # Clean up expired records from storage
                if hasattr(self._storage, 'cleanup_expired'):
                    expired_count = await self._storage.cleanup_expired()
                    if expired_count > 0:
                        self.logger.info(f"Cleaned up {expired_count} expired records")
                
                # Clean up stale tracking data
                stale_records = []
                for record_id in list(self._importance_scores.keys()):
                    record = await self._storage.retrieve(record_id)
                    if not record:
                        stale_records.append(record_id)
                
                for record_id in stale_records:
                    self._cleanup_record_tracking(record_id)
                
                # Clean up empty sessions
                empty_sessions = [
                    session_id for session_id, record_ids in self._session_associations.items()
                    if not record_ids
                ]
                for session_id in empty_sessions:
                    del self._session_associations[session_id]
                
                # Perform consolidation
                consolidated = await self.consolidate_to_long_term()
                
                self._last_consolidation = now
                
            except Exception as e:
                self.logger.error(f"Error during short-term memory consolidation: {e}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get short-term memory statistics."""
        base_stats = await super().get_stats()
        
        # Calculate current metrics
        total_records = len(self._importance_scores)
        active_sessions = len(self._session_associations)
        consolidation_candidates = len(self._consolidation_candidates)
        
        # Importance distribution
        importances = list(self._importance_scores.values()) if self._enable_importance_tracking else []
        avg_importance = sum(importances) / len(importances) if importances else 0.0
        high_importance_count = len([i for i in importances if i > self._consolidation_threshold])
        
        # Access pattern analysis
        total_accesses = sum(len(accesses) for accesses in self._access_histories.values())
        avg_accesses = total_accesses / max(1, total_records)
        
        short_term_stats = {
            "tier_name": "short_term",
            "total_records": total_records,
            "capacity_utilization": total_records / self._max_capacity,
            "active_sessions": active_sessions,
            "consolidation_candidates": consolidation_candidates,
            "average_importance": avg_importance,
            "high_importance_records": high_importance_count,
            "total_accesses": total_accesses,
            "average_accesses_per_record": avg_accesses,
            "default_ttl_hours": self._default_ttl.total_seconds() / 3600,
            "consolidation_interval_hours": self._consolidation_interval.total_seconds() / 3600,
            "last_consolidation": self._last_consolidation.isoformat(),
            "consolidation_threshold": self._consolidation_threshold,
            "importance_tracking_enabled": self._enable_importance_tracking
        }
        
        base_stats.update(short_term_stats)
        return base_stats
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check for short-term memory tier."""
        health = await super().health_check()
        
        # Short-term memory specific health metrics
        capacity_usage = len(self._importance_scores) / self._max_capacity
        health_status = "healthy"
        
        if capacity_usage > 0.8:
            health_status = "warning"
        elif capacity_usage > 0.9:
            health_status = "critical"
        
        # Check consolidation health
        consolidation_health = (datetime.utcnow() - self._last_consolidation) < self._consolidation_interval * 2
        
        short_term_health = {
            "capacity_usage": capacity_usage,
            "health_status": health_status,
            "active_sessions": len(self._session_associations),
            "tracked_records": len(self._importance_scores),
            "consolidation_candidates": len(self._consolidation_candidates),
            "consolidation_running": consolidation_health
        }
        
        health.update(short_term_health)
        return health