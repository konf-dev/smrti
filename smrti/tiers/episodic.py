"""
Episodic Memory Tier - Temporal Event Sequences

Stores temporally ordered sequences of events enabling:
- Timeline reconstruction
- Causal reasoning  
- Pattern detection
- Event clustering
- Narrative generation

Based on PRD Section 4.6: Episodic Memory
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Any, Set, Tuple
from collections import defaultdict, Counter
import hashlib

from ..models.memory import MemoryItem, MemoryMetadata
from ..adapters.storage import RedisAdapter


logger = logging.getLogger(__name__)


class EpisodeType(Enum):
    """Types of episodes that can be recorded."""
    CONVERSATION = "conversation"
    USER_ACTION = "user_action"
    SYSTEM_EVENT = "system_event"
    STATE_CHANGE = "state_change"
    ERROR = "error"
    MILESTONE = "milestone"
    CUSTOM = "custom"


class ClusteringMethod(Enum):
    """Methods for clustering episodes."""
    TEMPORAL = "temporal"  # Time-based windows
    SEMANTIC = "semantic"  # Semantic similarity
    TOPIC = "topic"  # Topic coherence
    SESSION = "session"  # Session boundaries
    HYBRID = "hybrid"  # Combined approach


@dataclass
class EpisodeConfig:
    """Configuration for Episodic Memory tier."""
    
    # Storage
    backend: str = "postgres"  # postgres, timescaledb, elasticsearch
    table_name: str = "episodes"
    index_embeddings: bool = False  # Enable semantic search
    
    # Retention
    retention_days: int = 90
    archive_after_days: int = 30
    summarize_after_days: int = 7
    
    # Clustering
    cluster_window: timedelta = timedelta(hours=1)
    min_cluster_size: int = 3
    session_timeout: timedelta = timedelta(minutes=30)
    
    # Performance
    batch_size: int = 100
    max_sequence_length: int = 1000
    enable_caching: bool = True
    cache_ttl: int = 600  # 10 minutes
    
    # Analysis
    pattern_min_frequency: int = 2
    causality_window: timedelta = timedelta(minutes=5)
    confidence_threshold: float = 0.7


@dataclass
class Episode:
    """Single episode/event in the timeline."""
    
    episode_id: str
    tenant_id: str
    episode_type: EpisodeType
    action: str
    context: Dict[str, Any]
    timestamp: datetime
    
    # Optional fields
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    namespace: Optional[str] = None
    
    # Relationships
    parent_episode_id: Optional[str] = None
    cluster_id: Optional[str] = None
    
    # Computed fields
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        data = asdict(self)
        data['episode_type'] = self.episode_type.value
        data['timestamp'] = self.timestamp.isoformat()
        data['created_at'] = self.created_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Episode':
        """Create from dictionary."""
        data = data.copy()
        data['episode_type'] = EpisodeType(data['episode_type'])
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)


@dataclass
class EpisodeCluster:
    """Group of related episodes."""
    
    cluster_id: str
    episodes: List[Episode]
    cluster_type: str  # temporal, semantic, session
    start_time: datetime
    end_time: datetime
    
    # Cluster metadata
    dominant_type: Optional[EpisodeType] = None
    summary: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    confidence: float = 1.0
    
    def duration(self) -> timedelta:
        """Duration of this cluster."""
        return self.end_time - self.start_time
    
    def size(self) -> int:
        """Number of episodes in cluster."""
        return len(self.episodes)


@dataclass
class Pattern:
    """Recurring pattern in episode sequences."""
    
    pattern_id: str
    sequence: List[str]  # Action sequence
    count: int
    confidence: float
    examples: List[List[str]]  # Episode ID sequences
    
    first_seen: datetime
    last_seen: datetime
    avg_duration: Optional[timedelta] = None


@dataclass
class Timeline:
    """Reconstructed timeline with metadata."""
    
    episodes: List[Episode]
    start_time: datetime
    end_time: datetime
    
    # Statistics
    total_events: int = 0
    event_types: Dict[str, int] = field(default_factory=dict)
    clusters: List[EpisodeCluster] = field(default_factory=list)
    
    # Narrative
    summary: Optional[str] = None
    key_moments: List[Episode] = field(default_factory=list)


class EpisodicMemory:
    """
    Episodic Memory Tier - Temporal Event Sequences
    
    Manages temporally ordered event sequences with:
    - Timeline storage and retrieval
    - Episode clustering
    - Pattern detection
    - Causal analysis
    - Narrative generation
    """
    
    def __init__(
        self,
        tenant_id: str,
        storage_adapter: Optional[RedisAdapter] = None,
        config: Optional[EpisodeConfig] = None,
        namespace: str = "default"
    ):
        self.tenant_id = tenant_id
        self.namespace = namespace
        self.config = config or EpisodeConfig()
        self.storage = storage_adapter
        
        self._initialized = False
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        
        # Statistics
        self._stats = {
            "episodes_recorded": 0,
            "episodes_retrieved": 0,
            "timeline_queries": 0,
            "clusters_created": 0,
            "patterns_detected": 0,
            "summaries_generated": 0
        }
        
        logger.info(
            f"EpisodicMemory initialized for tenant={tenant_id}, "
            f"namespace={namespace}"
        )
    
    async def initialize(self) -> None:
        """Initialize episodic memory storage."""
        if self._initialized:
            return
        
        logger.info("Initializing Episodic Memory tier...")
        
        # Initialize storage if provided
        if self.storage:
            await self.storage.initialize()
        
        # Create schema/tables if needed
        await self._ensure_schema()
        
        self._initialized = True
        logger.info("Episodic Memory tier initialized successfully")
    
    async def shutdown(self) -> None:
        """Clean shutdown."""
        logger.info("Shutting down Episodic Memory tier...")
        
        if self.storage:
            await self.storage.close()
        
        self._cache.clear()
        self._cache_timestamps.clear()
        self._initialized = False
    
    async def record(
        self,
        episode_type: EpisodeType,
        action: str,
        context: Dict[str, Any],
        timestamp: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        parent_episode_id: Optional[str] = None,
        embedding: Optional[List[float]] = None
    ) -> Episode:
        """
        Record a new episode.
        
        Args:
            episode_type: Type of episode
            action: Action/event name
            context: Event context data
            timestamp: Event timestamp (defaults to now)
            metadata: Additional metadata
            session_id: Session identifier
            user_id: User identifier
            parent_episode_id: Parent episode for causality
            embedding: Optional embedding for semantic search
        
        Returns:
            Created Episode object
        """
        if not self._initialized:
            await self.initialize()
        
        timestamp = timestamp or datetime.now(timezone.utc)
        metadata = metadata or {}
        
        # Generate episode ID
        episode_id = self._generate_episode_id(
            episode_type, action, timestamp
        )
        
        # Create episode
        episode = Episode(
            episode_id=episode_id,
            tenant_id=self.tenant_id,
            episode_type=episode_type,
            action=action,
            context=context,
            timestamp=timestamp,
            metadata=metadata,
            embedding=embedding,
            session_id=session_id,
            user_id=user_id,
            namespace=self.namespace,
            parent_episode_id=parent_episode_id
        )
        
        # Store episode
        await self._store_episode(episode)
        
        self._stats["episodes_recorded"] += 1
        
        logger.debug(
            f"Recorded episode: type={episode_type.value}, "
            f"action={action}, id={episode_id}"
        )
        
        return episode
    
    async def get_by_id(self, episode_id: str) -> Optional[Episode]:
        """Get episode by ID."""
        if not self._initialized:
            await self.initialize()
        
        # Check cache
        cache_key = f"episode:{episode_id}"
        if self._is_cached(cache_key):
            return self._cache[cache_key]
        
        # Retrieve from storage
        episode = await self._retrieve_episode(episode_id)
        
        if episode:
            self._cache_set(cache_key, episode)
            self._stats["episodes_retrieved"] += 1
        
        return episode
    
    async def get_timeline(
        self,
        start: datetime,
        end: datetime,
        episode_types: Optional[List[EpisodeType]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None
    ) -> Timeline:
        """
        Get timeline of episodes in time range.
        
        Args:
            start: Start timestamp
            end: End timestamp
            episode_types: Filter by episode types
            user_id: Filter by user
            session_id: Filter by session
            filters: Additional filters
            limit: Maximum episodes to return
        
        Returns:
            Timeline object with episodes and metadata
        """
        if not self._initialized:
            await self.initialize()
        
        self._stats["timeline_queries"] += 1
        
        # Build query
        query_filters = {
            "tenant_id": self.tenant_id,
            "namespace": self.namespace,
            "timestamp_gte": start,
            "timestamp_lte": end
        }
        
        if episode_types:
            query_filters["episode_type_in"] = [t.value for t in episode_types]
        if user_id:
            query_filters["user_id"] = user_id
        if session_id:
            query_filters["session_id"] = session_id
        if filters:
            query_filters.update(filters)
        
        # Retrieve episodes
        episodes = await self._query_episodes(query_filters, limit=limit)
        
        # Build timeline
        timeline = Timeline(
            episodes=episodes,
            start_time=start,
            end_time=end,
            total_events=len(episodes)
        )
        
        # Calculate statistics
        episode_type_counts = Counter(e.episode_type for e in episodes)
        timeline.event_types = {
            et.value: count for et, count in episode_type_counts.items()
        }
        
        logger.debug(
            f"Retrieved timeline: {len(episodes)} episodes "
            f"from {start} to {end}"
        )
        
        return timeline
    
    async def get_recent(
        self,
        limit: int = 50,
        episode_types: Optional[List[EpisodeType]] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Episode]:
        """Get recent episodes."""
        if not self._initialized:
            await self.initialize()
        
        now = datetime.now(timezone.utc)
        lookback = now - timedelta(days=30)  # Look back 30 days
        
        timeline = await self.get_timeline(
            start=lookback,
            end=now,
            episode_types=episode_types,
            filters=filters,
            limit=limit
        )
        
        return timeline.episodes
    
    async def get_sequence(
        self,
        start_episode_id: str,
        length: int = 10,
        direction: str = "forward"
    ) -> List[Episode]:
        """
        Get sequence of episodes starting from a given episode.
        
        Args:
            start_episode_id: Starting episode ID
            length: Number of episodes to retrieve
            direction: "forward" or "backward" in time
        
        Returns:
            List of episodes in sequence
        """
        if not self._initialized:
            await self.initialize()
        
        # Get starting episode
        start_episode = await self.get_by_id(start_episode_id)
        if not start_episode:
            return []
        
        # Build query based on direction
        if direction == "forward":
            query_filters = {
                "tenant_id": self.tenant_id,
                "namespace": self.namespace,
                "timestamp_gte": start_episode.timestamp
            }
            order = "asc"
        else:
            query_filters = {
                "tenant_id": self.tenant_id,
                "namespace": self.namespace,
                "timestamp_lte": start_episode.timestamp
            }
            order = "desc"
        
        episodes = await self._query_episodes(
            query_filters,
            limit=length,
            order_by="timestamp",
            order=order
        )
        
        return episodes
    
    async def find_patterns(
        self,
        episode_type: Optional[EpisodeType] = None,
        window: Optional[timedelta] = None,
        min_frequency: Optional[int] = None
    ) -> List[Pattern]:
        """
        Find recurring patterns in episode sequences.
        
        Args:
            episode_type: Filter by episode type
            window: Time window for pattern search
            min_frequency: Minimum pattern frequency
        
        Returns:
            List of detected patterns
        """
        if not self._initialized:
            await self.initialize()
        
        window = window or self.config.cluster_window
        min_frequency = min_frequency or self.config.pattern_min_frequency
        
        # Get recent episodes
        now = datetime.now(timezone.utc)
        start = now - window
        
        timeline = await self.get_timeline(
            start=start,
            end=now,
            episode_types=[episode_type] if episode_type else None
        )
        
        # Extract action sequences
        sequences = self._extract_sequences(timeline.episodes)
        
        # Find frequent patterns
        patterns = self._detect_patterns(sequences, min_frequency)
        
        self._stats["patterns_detected"] += len(patterns)
        
        logger.debug(f"Found {len(patterns)} patterns in {len(timeline.episodes)} episodes")
        
        return patterns
    
    async def analyze_causality(
        self,
        effect_episode_id: str,
        window: Optional[timedelta] = None
    ) -> List[Tuple[Episode, float]]:
        """
        Analyze potential causes for an episode.
        
        Args:
            effect_episode_id: Episode to find causes for
            window: Time window to search for causes
        
        Returns:
            List of (episode, confidence) tuples
        """
        if not self._initialized:
            await self.initialize()
        
        window = window or self.config.causality_window
        
        # Get effect episode
        effect = await self.get_by_id(effect_episode_id)
        if not effect:
            return []
        
        # Check if parent is explicitly set
        if effect.parent_episode_id:
            parent = await self.get_by_id(effect.parent_episode_id)
            if parent:
                return [(parent, 1.0)]
        
        # Find potential causes in temporal window
        start = effect.timestamp - window
        timeline = await self.get_timeline(
            start=start,
            end=effect.timestamp
        )
        
        # Calculate causality scores
        causes = []
        for episode in timeline.episodes:
            if episode.episode_id == effect_episode_id:
                continue
            
            confidence = self._calculate_causality_confidence(episode, effect)
            if confidence >= self.config.confidence_threshold:
                causes.append((episode, confidence))
        
        # Sort by confidence
        causes.sort(key=lambda x: x[1], reverse=True)
        
        return causes
    
    async def cluster_episodes(
        self,
        start: datetime,
        end: datetime,
        method: ClusteringMethod = ClusteringMethod.TEMPORAL,
        min_cluster_size: Optional[int] = None
    ) -> List[EpisodeCluster]:
        """
        Cluster episodes by various methods.
        
        Args:
            start: Start timestamp
            end: End timestamp
            method: Clustering method
            min_cluster_size: Minimum cluster size
        
        Returns:
            List of episode clusters
        """
        if not self._initialized:
            await self.initialize()
        
        min_cluster_size = min_cluster_size or self.config.min_cluster_size
        
        # Get episodes
        timeline = await self.get_timeline(start=start, end=end)
        
        # Cluster based on method
        if method == ClusteringMethod.TEMPORAL:
            clusters = self._cluster_temporal(
                timeline.episodes,
                self.config.cluster_window,
                min_cluster_size
            )
        elif method == ClusteringMethod.SESSION:
            clusters = self._cluster_by_session(
                timeline.episodes,
                self.config.session_timeout,
                min_cluster_size
            )
        elif method == ClusteringMethod.SEMANTIC:
            clusters = await self._cluster_semantic(
                timeline.episodes,
                min_cluster_size
            )
        elif method == ClusteringMethod.TOPIC:
            clusters = self._cluster_by_topic(
                timeline.episodes,
                min_cluster_size
            )
        else:  # HYBRID
            clusters = await self._cluster_hybrid(
                timeline.episodes,
                min_cluster_size
            )
        
        self._stats["clusters_created"] += len(clusters)
        
        logger.debug(
            f"Created {len(clusters)} clusters using {method.value} method"
        )
        
        return clusters
    
    async def generate_summary(
        self,
        start: datetime,
        end: datetime,
        max_length: int = 500
    ) -> str:
        """
        Generate narrative summary of timeline.
        
        Args:
            start: Start timestamp
            end: End timestamp
            max_length: Maximum summary length
        
        Returns:
            Summary text
        """
        if not self._initialized:
            await self.initialize()
        
        # Get timeline
        timeline = await self.get_timeline(start=start, end=end)
        
        # Generate summary
        summary = self._generate_narrative_summary(timeline, max_length)
        
        self._stats["summaries_generated"] += 1
        
        return summary
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get episodic memory statistics."""
        return self._stats.copy()
    
    # Private methods
    
    async def _ensure_schema(self) -> None:
        """Ensure database schema exists."""
        # This would create tables/indices in actual storage backend
        # For now, just a placeholder
        pass
    
    def _generate_episode_id(
        self,
        episode_type: EpisodeType,
        action: str,
        timestamp: datetime
    ) -> str:
        """Generate unique episode ID."""
        content = f"{self.tenant_id}:{episode_type.value}:{action}:{timestamp.isoformat()}"
        hash_bytes = hashlib.sha256(content.encode()).digest()
        return f"ep_{hash_bytes.hex()[:16]}"
    
    async def _store_episode(self, episode: Episode) -> None:
        """Store episode in backend."""
        if not self.storage:
            # In-memory fallback
            cache_key = f"episode:{episode.episode_id}"
            self._cache[cache_key] = episode
            return
        
        # Store in backend
        await self.storage.set(
            key=episode.episode_id,
            value=episode.to_dict(),
            namespace=f"episodes:{self.namespace}",
            tenant_id=self.tenant_id
        )
    
    async def _retrieve_episode(self, episode_id: str) -> Optional[Episode]:
        """Retrieve episode from backend."""
        if not self.storage:
            # In-memory fallback
            cache_key = f"episode:{episode_id}"
            return self._cache.get(cache_key)
        
        # Retrieve from backend
        data = await self.storage.get(
            key=episode_id,
            namespace=f"episodes:{self.namespace}",
            tenant_id=self.tenant_id
        )
        
        if data:
            return Episode.from_dict(data)
        return None
    
    async def _query_episodes(
        self,
        filters: Dict[str, Any],
        limit: Optional[int] = None,
        order_by: str = "timestamp",
        order: str = "desc"
    ) -> List[Episode]:
        """Query episodes with filters."""
        # This would use proper SQL/NoSQL query in production
        # For now, simple in-memory filtering
        
        if not self.storage:
            # In-memory: filter cached episodes
            all_episodes = [
                v for k, v in self._cache.items()
                if k.startswith("episode:") and isinstance(v, Episode)
            ]
            
            # Apply filters
            filtered = self._apply_filters(all_episodes, filters)
            
            # Sort
            reverse = (order == "desc")
            if order_by == "timestamp":
                filtered.sort(key=lambda e: e.timestamp, reverse=reverse)
            
            # Limit
            if limit:
                filtered = filtered[:limit]
            
            return filtered
        
        # In production, this would be a proper database query
        # For now, placeholder that returns empty list
        logger.warning("Storage adapter query not fully implemented")
        return []
    
    def _apply_filters(
        self,
        episodes: List[Episode],
        filters: Dict[str, Any]
    ) -> List[Episode]:
        """Apply filters to episode list."""
        filtered = episodes
        
        for key, value in filters.items():
            if key == "tenant_id":
                filtered = [e for e in filtered if e.tenant_id == value]
            elif key == "namespace":
                filtered = [e for e in filtered if e.namespace == value]
            elif key == "episode_type_in":
                types = [EpisodeType(t) for t in value]
                filtered = [e for e in filtered if e.episode_type in types]
            elif key == "user_id":
                filtered = [e for e in filtered if e.user_id == value]
            elif key == "session_id":
                filtered = [e for e in filtered if e.session_id == value]
            elif key == "timestamp_gte":
                filtered = [e for e in filtered if e.timestamp >= value]
            elif key == "timestamp_lte":
                filtered = [e for e in filtered if e.timestamp <= value]
        
        return filtered
    
    def _extract_sequences(
        self,
        episodes: List[Episode],
        window_size: int = 5
    ) -> List[List[str]]:
        """Extract action sequences from episodes."""
        if len(episodes) < window_size:
            return []
        
        sequences = []
        for i in range(len(episodes) - window_size + 1):
            window = episodes[i:i + window_size]
            sequence = [e.action for e in window]
            sequences.append(sequence)
        
        return sequences
    
    def _detect_patterns(
        self,
        sequences: List[List[str]],
        min_frequency: int
    ) -> List[Pattern]:
        """Detect frequent patterns in sequences."""
        # Count sequence frequencies
        sequence_counts = Counter(tuple(seq) for seq in sequences)
        
        # Filter by minimum frequency
        patterns = []
        now = datetime.now(timezone.utc)
        
        for sequence, count in sequence_counts.items():
            if count >= min_frequency:
                pattern_id = hashlib.md5(str(sequence).encode()).hexdigest()[:16]
                pattern = Pattern(
                    pattern_id=f"pat_{pattern_id}",
                    sequence=list(sequence),
                    count=count,
                    confidence=count / len(sequences) if sequences else 0,
                    examples=[],  # Would track actual episode IDs in production
                    first_seen=now,
                    last_seen=now
                )
                patterns.append(pattern)
        
        return patterns
    
    def _calculate_causality_confidence(
        self,
        cause: Episode,
        effect: Episode
    ) -> float:
        """Calculate causality confidence score."""
        # Temporal proximity
        time_diff = (effect.timestamp - cause.timestamp).total_seconds()
        if time_diff <= 0:
            return 0.0
        
        # Decay with time
        temporal_score = max(0, 1.0 - (time_diff / 300))  # 5 minute window
        
        # Same session boost
        session_boost = 0.2 if cause.session_id == effect.session_id else 0
        
        # Same user boost
        user_boost = 0.1 if cause.user_id == effect.user_id else 0
        
        # Type correlation (errors often follow actions)
        type_boost = 0.0
        if effect.episode_type == EpisodeType.ERROR:
            if cause.episode_type == EpisodeType.USER_ACTION:
                type_boost = 0.3
        
        confidence = min(1.0, temporal_score + session_boost + user_boost + type_boost)
        return confidence
    
    def _cluster_temporal(
        self,
        episodes: List[Episode],
        window: timedelta,
        min_size: int
    ) -> List[EpisodeCluster]:
        """Cluster episodes by temporal proximity."""
        if not episodes:
            return []
        
        # Sort by timestamp
        sorted_episodes = sorted(episodes, key=lambda e: e.timestamp)
        
        clusters = []
        current_cluster = [sorted_episodes[0]]
        cluster_start = sorted_episodes[0].timestamp
        
        for episode in sorted_episodes[1:]:
            # Check if within window
            if episode.timestamp - current_cluster[-1].timestamp <= window:
                current_cluster.append(episode)
            else:
                # Finalize current cluster
                if len(current_cluster) >= min_size:
                    cluster_id = f"tc_{hashlib.md5(str(cluster_start).encode()).hexdigest()[:12]}"
                    clusters.append(EpisodeCluster(
                        cluster_id=cluster_id,
                        episodes=current_cluster,
                        cluster_type="temporal",
                        start_time=current_cluster[0].timestamp,
                        end_time=current_cluster[-1].timestamp
                    ))
                
                # Start new cluster
                current_cluster = [episode]
                cluster_start = episode.timestamp
        
        # Finalize last cluster
        if len(current_cluster) >= min_size:
            cluster_id = f"tc_{hashlib.md5(str(cluster_start).encode()).hexdigest()[:12]}"
            clusters.append(EpisodeCluster(
                cluster_id=cluster_id,
                episodes=current_cluster,
                cluster_type="temporal",
                start_time=current_cluster[0].timestamp,
                end_time=current_cluster[-1].timestamp
            ))
        
        return clusters
    
    def _cluster_by_session(
        self,
        episodes: List[Episode],
        timeout: timedelta,
        min_size: int
    ) -> List[EpisodeCluster]:
        """Cluster episodes by session boundaries."""
        # Group by session_id
        session_groups: Dict[str, List[Episode]] = defaultdict(list)
        
        for episode in episodes:
            session_id = episode.session_id or "unknown"
            session_groups[session_id].append(episode)
        
        clusters = []
        for session_id, session_episodes in session_groups.items():
            if len(session_episodes) >= min_size:
                session_episodes.sort(key=lambda e: e.timestamp)
                cluster_id = f"sc_{hashlib.md5(session_id.encode()).hexdigest()[:12]}"
                clusters.append(EpisodeCluster(
                    cluster_id=cluster_id,
                    episodes=session_episodes,
                    cluster_type="session",
                    start_time=session_episodes[0].timestamp,
                    end_time=session_episodes[-1].timestamp
                ))
        
        return clusters
    
    async def _cluster_semantic(
        self,
        episodes: List[Episode],
        min_size: int
    ) -> List[EpisodeCluster]:
        """Cluster episodes by semantic similarity."""
        # Would use embeddings and similarity clustering in production
        # For now, return empty list
        logger.warning("Semantic clustering not fully implemented")
        return []
    
    def _cluster_by_topic(
        self,
        episodes: List[Episode],
        min_size: int
    ) -> List[EpisodeCluster]:
        """Cluster episodes by topic/action type."""
        # Group by action
        action_groups: Dict[str, List[Episode]] = defaultdict(list)
        
        for episode in episodes:
            action_groups[episode.action].append(episode)
        
        clusters = []
        for action, action_episodes in action_groups.items():
            if len(action_episodes) >= min_size:
                action_episodes.sort(key=lambda e: e.timestamp)
                cluster_id = f"tc_{hashlib.md5(action.encode()).hexdigest()[:12]}"
                clusters.append(EpisodeCluster(
                    cluster_id=cluster_id,
                    episodes=action_episodes,
                    cluster_type="topic",
                    start_time=action_episodes[0].timestamp,
                    end_time=action_episodes[-1].timestamp,
                    tags=[action]
                ))
        
        return clusters
    
    async def _cluster_hybrid(
        self,
        episodes: List[Episode],
        min_size: int
    ) -> List[EpisodeCluster]:
        """Combine multiple clustering methods."""
        # Get clusters from different methods
        temporal_clusters = self._cluster_temporal(
            episodes,
            self.config.cluster_window,
            min_size
        )
        
        session_clusters = self._cluster_by_session(
            episodes,
            self.config.session_timeout,
            min_size
        )
        
        # Merge and deduplicate
        # In production, would use more sophisticated merging
        all_clusters = temporal_clusters + session_clusters
        
        return all_clusters
    
    def _generate_narrative_summary(
        self,
        timeline: Timeline,
        max_length: int
    ) -> str:
        """Generate narrative summary of timeline."""
        if not timeline.episodes:
            return "No events in this period."
        
        # Calculate statistics
        total = timeline.total_events
        types = timeline.event_types
        start = timeline.start_time.strftime("%Y-%m-%d %H:%M")
        end = timeline.end_time.strftime("%Y-%m-%d %H:%M")
        
        # Build summary
        summary_parts = [
            f"Timeline from {start} to {end}:",
            f"Total events: {total}"
        ]
        
        if types:
            type_summary = ", ".join(
                f"{count} {type_name}"
                for type_name, count in sorted(
                    types.items(),
                    key=lambda x: x[1],
                    reverse=True
                )
            )
            summary_parts.append(f"Event types: {type_summary}")
        
        # Add key moments
        if timeline.episodes:
            key_actions = [e.action for e in timeline.episodes[:5]]
            summary_parts.append(f"Key actions: {', '.join(key_actions)}")
        
        summary = "\n".join(summary_parts)
        
        # Truncate if needed
        if len(summary) > max_length:
            summary = summary[:max_length-3] + "..."
        
        return summary
    
    def _is_cached(self, key: str) -> bool:
        """Check if key is in cache and not expired."""
        if not self.config.enable_caching:
            return False
        
        if key not in self._cache:
            return False
        
        timestamp = self._cache_timestamps.get(key)
        if not timestamp:
            return False
        
        age = (datetime.now(timezone.utc) - timestamp).total_seconds()
        return age < self.config.cache_ttl
    
    def _cache_set(self, key: str, value: Any) -> None:
        """Set cache entry."""
        if not self.config.enable_caching:
            return
        
        self._cache[key] = value
        self._cache_timestamps[key] = datetime.now(timezone.utc)
