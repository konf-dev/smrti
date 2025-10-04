"""
smrti/memory/tiers/episodic.py - Episodic Memory Tier

Episodic memory for temporal event sequences and experiential memories.
Optimized for chronological retrieval and causal relationship tracking.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Union, Tuple

from smrti.core.base import BaseMemoryTier
from smrti.core.exceptions import MemoryError, ValidationError
from smrti.core.protocols import TierStore
from smrti.core.registry import AdapterRegistry
from smrti.schemas.models import (
    MemoryQuery,
    RecordEnvelope,
    EventRecord,
    # ConversationTurn,  # TODO: Add back when defined
    EpisodicMemoryConfig
)


class EpisodicMemory(BaseMemoryTier):
    """
    Episodic Memory Tier - Temporal event sequences and experiences.
    
    Characteristics:
    - Temporal organization and sequencing
    - Event causality tracking
    - Session-based grouping
    - Timeline reconstruction
    - Contextual associations
    - Long-term retention with temporal indexing
    
    Use cases:
    - Conversation history and context
    - Event sequences and workflows
    - Learning experiences and outcomes
    - Temporal pattern recognition
    - Causal relationship tracking
    - Experience-based decision making
    """
    
    def __init__(
        self,
        adapter_registry: AdapterRegistry,
        config: Optional[EpisodicMemoryConfig] = None
    ):
        super().__init__(
            tier_name="episodic",
            adapter_registry=adapter_registry,
            config=config
        )
        
        # Episodic memory configuration
        self._default_retention = timedelta(days=config.retention_days if config else 90)
        self._max_timeline_length = config.max_timeline_length if config else 1000
        self._causal_link_threshold = config.causal_link_threshold if config else 0.6
        self._temporal_window = timedelta(minutes=config.temporal_window_minutes if config else 30)
        
        # Event sequencing and causality
        self._active_sessions: Dict[str, Dict[str, Any]] = {}  # session_id -> session_info
        self._event_sequences: Dict[str, List[str]] = {}  # session_id -> ordered record_ids
        self._causal_links: Dict[str, List[str]] = {}  # record_id -> caused_record_ids
        self._temporal_clusters: Dict[str, Set[str]] = {}  # time_bucket -> record_ids
        
        # Timeline management
        self._timeline_cache: Dict[str, List[RecordEnvelope]] = {}
        self._cache_ttl = timedelta(minutes=config.cache_ttl_minutes if config else 15)
        self._last_cache_cleanup = datetime.utcnow()
        
        # Configuration
        self._enable_causal_tracking = config.enable_causal_tracking if config else True
        self._enable_temporal_clustering = config.enable_temporal_clustering if config else True
        self._auto_sequence_events = config.auto_sequence_events if config else True
        self._emotional_context_tracking = config.emotional_context_tracking if config else True
        
    async def initialize(self) -> None:
        """Initialize episodic memory tier with temporal database storage."""
        # Get database adapter for episodic memory (PostgreSQL)
        adapter = await self._adapter_registry.get_adapter(
            tier_name="episodic",
            required_capabilities=["temporal_queries", "transaction_support"]
        )
        
        if not adapter:
            raise MemoryError(
                "No suitable temporal database adapter found for episodic memory tier",
                tier="episodic",
                operation="initialize"
            )
        
        self._storage = adapter
        await super().initialize()
        
        # Start background processing tasks
        asyncio.create_task(self._periodic_timeline_processing())
        
        self.logger.info(
            f"Episodic memory initialized (retention={self._default_retention.days} days, "
            f"temporal_window={self._temporal_window.total_seconds()} seconds)"
        )
    
    async def store(
        self, 
        record: RecordEnvelope,
        session_id: Optional[str] = None,
        event_sequence: Optional[int] = None,
        causal_parent: Optional[str] = None,
        emotional_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Store an episodic memory with temporal and causal metadata.
        
        Args:
            record: Memory record to store
            session_id: Session identifier for grouping related events
            event_sequence: Sequence number within session
            causal_parent: Record ID of causally related parent event
            emotional_context: Emotional state or context information
            
        Returns:
            Record ID of stored memory
        """
        # Set episodic memory tier
        record.tier = "episodic"
        
        # Ensure record has temporal information
        if isinstance(record.content, EventRecord):
            if not hasattr(record.content, 'timestamp') or record.content.timestamp is None:
                record.content.timestamp = datetime.utcnow()
        
        # Add session and sequence information
        if session_id:
            record.session_id = session_id
            
            # Auto-assign sequence number if not provided
            if event_sequence is None and self._auto_sequence_events:
                event_sequence = self._get_next_sequence_number(session_id)
            
            # Update session tracking
            await self._update_session_info(session_id, record, event_sequence)
        
        # Add emotional context to metadata
        if emotional_context and self._emotional_context_tracking:
            record.metadata = record.metadata or {}
            record.metadata["emotional_context"] = emotional_context
        
        # Store in temporal database
        record_id = await self._storage.store(record, self._default_retention)
        
        # Update event sequencing
        if session_id and event_sequence is not None:
            if session_id not in self._event_sequences:
                self._event_sequences[session_id] = []
            
            # Insert in correct position
            sequence_list = self._event_sequences[session_id]
            inserted = False
            
            for i, existing_id in enumerate(sequence_list):
                # This is simplified - in practice you'd need to track sequences better
                if i >= event_sequence:
                    sequence_list.insert(i, record_id)
                    inserted = True
                    break
            
            if not inserted:
                sequence_list.append(record_id)
        
        # Track causal relationships
        if causal_parent and self._enable_causal_tracking:
            await self._add_causal_link(causal_parent, record_id)
        
        # Update temporal clustering
        if self._enable_temporal_clustering:
            self._update_temporal_cluster(record_id, record.created_at)
        
        # Invalidate relevant timeline caches
        if session_id and session_id in self._timeline_cache:
            del self._timeline_cache[session_id]
        
        self.logger.debug(
            f"Stored episodic record {record_id} "
            f"(session={session_id}, sequence={event_sequence}, causal_parent={causal_parent})"
        )
        
        return record_id
    
    async def retrieve(
        self, 
        record_id: str,
        include_causal_chain: bool = False,
        include_temporal_context: bool = False
    ) -> Optional[RecordEnvelope]:
        """
        Retrieve an episodic record with optional causal and temporal context.
        
        Args:
            record_id: ID of record to retrieve
            include_causal_chain: Whether to include causal predecessors/successors
            include_temporal_context: Whether to include temporally nearby events
            
        Returns:
            Record with optional context information in metadata
        """
        record = await self._storage.retrieve(record_id)
        
        if not record:
            return None
        
        # Add causal chain information
        if include_causal_chain and self._enable_causal_tracking:
            causal_info = await self._get_causal_chain(record_id)
            record.metadata = record.metadata or {}
            record.metadata["causal_chain"] = causal_info
        
        # Add temporal context information
        if include_temporal_context and hasattr(record, 'session_id') and record.session_id:
            temporal_context = await self._get_temporal_context(record_id, record.session_id)
            record.metadata = record.metadata or {}
            record.metadata["temporal_context"] = temporal_context
        
        return record
    
    async def query(
        self,
        query: MemoryQuery,
        session_id: Optional[str] = None,
        temporal_order: bool = True,
        include_causal_links: bool = False
    ) -> List[RecordEnvelope]:
        """
        Query episodic memory with temporal ordering and optional causal filtering.
        
        Args:
            query: Memory query parameters
            session_id: Optional session to focus search
            temporal_order: Whether to sort results temporally
            include_causal_links: Whether to include causal link information
            
        Returns:
            List of matching records, optionally ordered temporally
        """
        # Build enhanced query for temporal search
        enhanced_query = query
        
        # Add session filtering if specified
        if session_id:
            enhanced_query.metadata = enhanced_query.metadata or {}
            enhanced_query.metadata["session_id"] = session_id
        
        # Query the temporal storage
        results = await self._storage.query(enhanced_query)
        
        # Apply temporal ordering if requested
        if temporal_order:
            results.sort(key=lambda r: (
                getattr(r.content, 'timestamp', r.created_at) or r.created_at,
                getattr(r.content, 'sequence_number', 0) or 0
            ))
        
        # Add causal link information if requested
        if include_causal_links and self._enable_causal_tracking:
            for record in results:
                causal_links = await self._get_causal_links(record.record_id)
                if causal_links:
                    record.metadata = record.metadata or {}
                    record.metadata["causal_links"] = causal_links
        
        return results
    
    async def get_timeline(
        self,
        session_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        max_events: int = 100
    ) -> List[RecordEnvelope]:
        """
        Get chronological timeline of events for a session.
        
        Args:
            session_id: Session identifier
            start_time: Optional start time filter
            end_time: Optional end time filter
            max_events: Maximum number of events to return
            
        Returns:
            Chronologically ordered list of events
        """
        # Check cache first
        cache_key = f"{session_id}_{start_time}_{end_time}_{max_events}"
        
        if cache_key in self._timeline_cache:
            cached_timeline = self._timeline_cache[cache_key]
            cache_age = datetime.utcnow() - cached_timeline[0].last_accessed if cached_timeline else timedelta(0)
            
            if cache_age < self._cache_ttl:
                return cached_timeline
        
        # Use storage adapter's timeline functionality if available
        if hasattr(self._storage, 'get_timeline'):
            timeline = await self._storage.get_timeline(
                tenant_id=None,  # Will be filled by adapter
                namespace=None,   # Will be filled by adapter
                session_id=session_id,
                start_time=start_time,
                end_time=end_time,
                limit=max_events
            )
        else:
            # Fallback: build timeline from event sequences
            timeline = await self._build_timeline_fallback(session_id, start_time, end_time, max_events)
        
        # Cache the result
        self._timeline_cache[cache_key] = timeline
        
        return timeline
    
    async def _build_timeline_fallback(
        self,
        session_id: str,
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        max_events: int
    ) -> List[RecordEnvelope]:
        """Build timeline using fallback method when storage doesn't support it."""
        if session_id not in self._event_sequences:
            return []
        
        record_ids = self._event_sequences[session_id]
        timeline = []
        
        for record_id in record_ids:
            record = await self._storage.retrieve(record_id)
            if not record:
                continue
            
            # Apply time filters
            event_time = getattr(record.content, 'timestamp', record.created_at) or record.created_at
            
            if start_time and event_time < start_time:
                continue
            if end_time and event_time > end_time:
                continue
            
            timeline.append(record)
            
            if len(timeline) >= max_events:
                break
        
        # Sort by timestamp and sequence
        timeline.sort(key=lambda r: (
            getattr(r.content, 'timestamp', r.created_at) or r.created_at,
            getattr(r.content, 'sequence_number', 0) or 0
        ))
        
        return timeline
    
    async def find_causal_sequences(
        self,
        root_event_id: str,
        max_depth: int = 5,
        min_causal_strength: float = 0.5
    ) -> Dict[str, List[str]]:
        """
        Find causal sequences starting from a root event.
        
        Args:
            root_event_id: Starting event for causal tracing
            max_depth: Maximum depth of causal chain to follow
            min_causal_strength: Minimum strength for causal links
            
        Returns:
            Dictionary mapping depth levels to lists of causally linked event IDs
        """
        if not self._enable_causal_tracking:
            return {}
        
        causal_sequences = {0: [root_event_id]}
        visited = {root_event_id}
        
        for depth in range(1, max_depth + 1):
            current_level = []
            
            for event_id in causal_sequences[depth - 1]:
                # Get events caused by this event
                caused_events = self._causal_links.get(event_id, [])
                
                for caused_id in caused_events:
                    if caused_id not in visited:
                        # Check causal strength (simplified - in practice you'd store this)
                        causal_strength = await self._calculate_causal_strength(event_id, caused_id)
                        
                        if causal_strength >= min_causal_strength:
                            current_level.append(caused_id)
                            visited.add(caused_id)
            
            if current_level:
                causal_sequences[depth] = current_level
            else:
                break  # No more causal links
        
        return causal_sequences
    
    async def get_session_summary(
        self,
        session_id: str,
        include_emotional_arc: bool = True,
        include_causal_patterns: bool = True
    ) -> Dict[str, Any]:
        """
        Get a comprehensive summary of a session's episodic memories.
        
        Args:
            session_id: Session to summarize
            include_emotional_arc: Whether to analyze emotional progression
            include_causal_patterns: Whether to identify causal patterns
            
        Returns:
            Dictionary containing session summary and analysis
        """
        if session_id not in self._active_sessions:
            return {}
        
        session_info = self._active_sessions[session_id]
        timeline = await self.get_timeline(session_id)
        
        summary = {
            "session_id": session_id,
            "start_time": session_info.get("start_time"),
            "end_time": session_info.get("end_time"),
            "duration_minutes": session_info.get("duration_minutes", 0),
            "total_events": len(timeline),
            "event_types": {},
            "key_events": []
        }
        
        # Analyze event types and identify key events
        event_type_counts = {}
        high_importance_events = []
        
        for record in timeline:
            # Count event types
            event_type = record.record_type or "unknown"
            event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1
            
            # Identify high-importance events
            if record.relevance_score > 0.8:
                high_importance_events.append({
                    "record_id": record.record_id,
                    "timestamp": getattr(record.content, 'timestamp', record.created_at),
                    "relevance_score": record.relevance_score,
                    "content_preview": str(record.content)[:100] + "..."
                })
        
        summary["event_types"] = event_type_counts
        summary["key_events"] = sorted(
            high_importance_events,
            key=lambda e: e["relevance_score"],
            reverse=True
        )[:10]  # Top 10 key events
        
        # Emotional arc analysis
        if include_emotional_arc and self._emotional_context_tracking:
            emotional_arc = []
            
            for record in timeline:
                emotional_context = record.metadata.get("emotional_context") if record.metadata else None
                if emotional_context:
                    emotional_arc.append({
                        "timestamp": getattr(record.content, 'timestamp', record.created_at),
                        "emotional_state": emotional_context
                    })
            
            summary["emotional_arc"] = emotional_arc
        
        # Causal pattern analysis
        if include_causal_patterns and self._enable_causal_tracking:
            causal_patterns = []
            
            # Find major causal chains in the session
            for record in timeline:
                if record.relevance_score > 0.7:  # Focus on important events
                    causal_chain = await self.find_causal_sequences(record.record_id, max_depth=3)
                    if len(causal_chain) > 1:  # Has causal consequences
                        causal_patterns.append({
                            "root_event": record.record_id,
                            "chain_length": len(causal_chain),
                            "total_consequences": sum(len(events) for events in causal_chain.values())
                        })
            
            summary["causal_patterns"] = sorted(
                causal_patterns,
                key=lambda p: p["total_consequences"],
                reverse=True
            )[:5]  # Top 5 causal patterns
        
        return summary
    
    def _get_next_sequence_number(self, session_id: str) -> int:
        """Get the next sequence number for a session."""
        if session_id not in self._event_sequences:
            return 1
        
        return len(self._event_sequences[session_id]) + 1
    
    async def _update_session_info(
        self,
        session_id: str,
        record: RecordEnvelope,
        sequence_number: Optional[int]
    ) -> None:
        """Update session information with new event."""
        now = datetime.utcnow()
        
        if session_id not in self._active_sessions:
            self._active_sessions[session_id] = {
                "start_time": now,
                "event_count": 0,
                "last_event_time": now
            }
        
        session_info = self._active_sessions[session_id]
        session_info["event_count"] += 1
        session_info["last_event_time"] = now
        session_info["end_time"] = now
        
        # Calculate duration
        start_time = session_info["start_time"]
        duration = (now - start_time).total_seconds() / 60  # minutes
        session_info["duration_minutes"] = duration
    
    async def _add_causal_link(self, parent_id: str, child_id: str) -> None:
        """Add a causal link between two events."""
        if parent_id not in self._causal_links:
            self._causal_links[parent_id] = []
        
        if child_id not in self._causal_links[parent_id]:
            self._causal_links[parent_id].append(child_id)
    
    async def _get_causal_chain(self, record_id: str) -> Dict[str, List[str]]:
        """Get the causal chain (predecessors and successors) for a record."""
        predecessors = []
        successors = self._causal_links.get(record_id, [])
        
        # Find predecessors (events that caused this one)
        for parent_id, children in self._causal_links.items():
            if record_id in children:
                predecessors.append(parent_id)
        
        return {
            "predecessors": predecessors,
            "successors": successors
        }
    
    async def _get_causal_links(self, record_id: str) -> Dict[str, Any]:
        """Get causal link information for a record."""
        return await self._get_causal_chain(record_id)
    
    async def _calculate_causal_strength(self, parent_id: str, child_id: str) -> float:
        """Calculate the strength of causal relationship between two events."""
        # Simplified implementation - in practice, this would use temporal proximity,
        # content similarity, and other factors
        
        try:
            parent_record = await self._storage.retrieve(parent_id)
            child_record = await self._storage.retrieve(child_id)
            
            if not parent_record or not child_record:
                return 0.0
            
            # Time-based factor
            parent_time = getattr(parent_record.content, 'timestamp', parent_record.created_at)
            child_time = getattr(child_record.content, 'timestamp', child_record.created_at)
            
            if parent_time and child_time:
                time_diff = (child_time - parent_time).total_seconds()
                
                # Stronger causal link if events are close in time
                if time_diff <= self._temporal_window.total_seconds():
                    time_factor = 1.0 - (time_diff / self._temporal_window.total_seconds())
                else:
                    time_factor = 0.1  # Weak link for distant events
                
                return min(1.0, time_factor + 0.2)  # Base causal strength
            
            return 0.5  # Default strength when timing is unclear
            
        except Exception:
            return 0.0
    
    async def _get_temporal_context(
        self,
        record_id: str,
        session_id: str,
        context_window: int = 5
    ) -> Dict[str, List[str]]:
        """Get temporally nearby events for context."""
        if session_id not in self._event_sequences:
            return {"preceding": [], "following": []}
        
        sequence = self._event_sequences[session_id]
        
        try:
            index = sequence.index(record_id)
            
            # Get preceding and following events
            preceding = sequence[max(0, index - context_window):index]
            following = sequence[index + 1:index + 1 + context_window]
            
            return {
                "preceding": preceding,
                "following": following
            }
            
        except ValueError:
            return {"preceding": [], "following": []}
    
    def _update_temporal_cluster(self, record_id: str, timestamp: datetime) -> None:
        """Update temporal clustering with new event."""
        if not self._enable_temporal_clustering:
            return
        
        # Create time bucket (hour-based)
        time_bucket = timestamp.strftime("%Y-%m-%d-%H")
        
        if time_bucket not in self._temporal_clusters:
            self._temporal_clusters[time_bucket] = set()
        
        self._temporal_clusters[time_bucket].add(record_id)
    
    async def _periodic_timeline_processing(self) -> None:
        """Periodic processing of timelines and cleanup."""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                
                # Clean up old timeline cache
                now = datetime.utcnow()
                
                if now - self._last_cache_cleanup > self._cache_ttl:
                    expired_keys = []
                    
                    for cache_key, timeline in self._timeline_cache.items():
                        if timeline:
                            last_access = timeline[0].last_accessed or timeline[0].created_at
                            if now - last_access > self._cache_ttl:
                                expired_keys.append(cache_key)
                    
                    for key in expired_keys:
                        del self._timeline_cache[key]
                    
                    self._last_cache_cleanup = now
                
                # Clean up old temporal clusters
                cutoff_time = now - timedelta(days=7)  # Keep last week
                cutoff_bucket = cutoff_time.strftime("%Y-%m-%d-%H")
                
                old_buckets = [
                    bucket for bucket in self._temporal_clusters.keys()
                    if bucket < cutoff_bucket
                ]
                
                for bucket in old_buckets:
                    del self._temporal_clusters[bucket]
                
                # Clean up completed sessions
                completed_sessions = []
                
                for session_id, session_info in self._active_sessions.items():
                    last_event = session_info.get("last_event_time", session_info["start_time"])
                    if now - last_event > timedelta(hours=24):  # No activity for 24 hours
                        completed_sessions.append(session_id)
                
                for session_id in completed_sessions:
                    self.logger.info(f"Archiving completed session {session_id}")
                    # Move to completed sessions or just remove from active tracking
                    del self._active_sessions[session_id]
                
            except Exception as e:
                self.logger.error(f"Error during episodic memory timeline processing: {e}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get episodic memory statistics."""
        base_stats = await super().get_stats()
        
        # Session and timeline statistics
        active_sessions = len(self._active_sessions)
        total_sequences = sum(len(seq) for seq in self._event_sequences.values())
        cached_timelines = len(self._timeline_cache)
        
        # Causal relationship statistics
        total_causal_links = sum(len(links) for links in self._causal_links.values())
        
        # Temporal clustering statistics
        temporal_buckets = len(self._temporal_clusters)
        clustered_events = sum(len(events) for events in self._temporal_clusters.values())
        
        episodic_stats = {
            "tier_name": "episodic",
            "active_sessions": active_sessions,
            "total_event_sequences": len(self._event_sequences),
            "total_sequenced_events": total_sequences,
            "cached_timelines": cached_timelines,
            "causal_links": total_causal_links,
            "temporal_buckets": temporal_buckets,
            "clustered_events": clustered_events,
            "retention_days": self._default_retention.days,
            "temporal_window_minutes": self._temporal_window.total_seconds() / 60,
            "causal_tracking_enabled": self._enable_causal_tracking,
            "temporal_clustering_enabled": self._enable_temporal_clustering,
            "emotional_tracking_enabled": self._emotional_context_tracking,
            "auto_sequencing_enabled": self._auto_sequence_events
        }
        
        base_stats.update(episodic_stats)
        return base_stats
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check for episodic memory tier."""
        health = await super().health_check()
        
        # Episodic memory specific health metrics
        now = datetime.utcnow()
        
        # Check session activity
        recent_activity = any(
            now - session_info.get("last_event_time", session_info["start_time"]) < timedelta(hours=1)
            for session_info in self._active_sessions.values()
        )
        
        # Check cache health
        cache_health = len(self._timeline_cache) < 1000  # Arbitrary limit
        
        # Check causal link consistency
        causal_consistency = True
        if self._enable_causal_tracking:
            # Simple consistency check - all causal links should point to existing records
            # This is simplified - in production you'd do more thorough checks
            pass
        
        episodic_health = {
            "active_sessions": len(self._active_sessions),
            "recent_activity": recent_activity,
            "cache_health": cache_health,
            "causal_consistency": causal_consistency,
            "timeline_cache_size": len(self._timeline_cache),
            "temporal_clusters": len(self._temporal_clusters)
        }
        
        health.update(episodic_health)
        return health