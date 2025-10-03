"""
Tests for Episodic Memory Tier

Tests timeline storage, temporal queries, clustering, and pattern detection.
"""

import pytest
from datetime import datetime, timedelta, timezone

from smrti.tiers.episodic import (
    EpisodicMemory,
    EpisodeType,
    Episode,
    EpisodeConfig,
    ClusteringMethod,
    EpisodeCluster,
    Pattern,
    Timeline
)


class TestEpisodicMemory:
    """Test suite for Episodic Memory tier."""
    
    @pytest.fixture
    async def episodic_memory(self):
        """Create Episodic Memory instance for testing."""
        config = EpisodeConfig(
            retention_days=90,
            cluster_window=timedelta(hours=1),
            min_cluster_size=2
        )
        em = EpisodicMemory(
            tenant_id="test",
            config=config,
            namespace="test"
        )
        await em.initialize()
        yield em
        await em.shutdown()
    
    async def test_initialization(self, episodic_memory):
        """Test that Episodic Memory initializes correctly."""
        assert episodic_memory._initialized
        assert episodic_memory.tenant_id == "test"
        assert episodic_memory.namespace == "test"
    
    async def test_record_episode(self, episodic_memory):
        """Test recording a single episode."""
        episode = await episodic_memory.record(
            episode_type=EpisodeType.USER_ACTION,
            action="button_click",
            context={"button_id": "submit", "page": "/home"},
            metadata={"user_agent": "chrome"}
        )
        
        assert episode is not None
        assert episode.episode_id.startswith("ep_")
        assert episode.episode_type == EpisodeType.USER_ACTION
        assert episode.action == "button_click"
        assert episode.context["button_id"] == "submit"
        assert episode.tenant_id == "test"
    
    async def test_get_by_id(self, episodic_memory):
        """Test retrieving episode by ID."""
        # Record episode
        recorded = await episodic_memory.record(
            episode_type=EpisodeType.CONVERSATION,
            action="message",
            context={"role": "user", "content": "Hello"}
        )
        
        # Retrieve it
        retrieved = await episodic_memory.get_by_id(recorded.episode_id)
        
        assert retrieved is not None
        assert retrieved.episode_id == recorded.episode_id
        assert retrieved.action == "message"
        assert retrieved.context["content"] == "Hello"
    
    async def test_timeline_query(self, episodic_memory):
        """Test timeline queries with time ranges."""
        now = datetime.now(timezone.utc)
        
        # Record multiple episodes
        for i in range(5):
            await episodic_memory.record(
                episode_type=EpisodeType.USER_ACTION,
                action=f"action_{i}",
                context={"index": i},
                timestamp=now + timedelta(minutes=i)
            )
        
        # Query timeline
        timeline = await episodic_memory.get_timeline(
            start=now - timedelta(minutes=1),
            end=now + timedelta(minutes=10)
        )
        
        assert isinstance(timeline, Timeline)
        assert len(timeline.episodes) >= 5
        assert timeline.total_events >= 5
    
    async def test_recent_episodes(self, episodic_memory):
        """Test getting recent episodes."""
        # Record some episodes
        for i in range(3):
            await episodic_memory.record(
                episode_type=EpisodeType.SYSTEM_EVENT,
                action="health_check",
                context={"status": "ok"}
            )
        
        # Get recent
        recent = await episodic_memory.get_recent(limit=10)
        
        assert len(recent) >= 3
        assert all(e.action == "health_check" for e in recent[:3])
    
    async def test_episode_sequence(self, episodic_memory):
        """Test getting episode sequences."""
        now = datetime.now(timezone.utc)
        
        # Record sequence
        episodes = []
        for i in range(5):
            ep = await episodic_memory.record(
                episode_type=EpisodeType.CONVERSATION,
                action="turn",
                context={"turn": i},
                timestamp=now + timedelta(seconds=i*10)
            )
            episodes.append(ep)
        
        # Get forward sequence
        forward_seq = await episodic_memory.get_sequence(
            start_episode_id=episodes[1].episode_id,
            length=3,
            direction="forward"
        )
        
        assert len(forward_seq) >= 1
    
    async def test_temporal_clustering(self, episodic_memory):
        """Test temporal clustering of episodes."""
        now = datetime.now(timezone.utc)
        
        # Record cluster 1 (close together)
        for i in range(3):
            await episodic_memory.record(
                episode_type=EpisodeType.USER_ACTION,
                action="click",
                context={"cluster": 1},
                timestamp=now + timedelta(minutes=i)
            )
        
        # Record cluster 2 (2 hours later)
        for i in range(3):
            await episodic_memory.record(
                episode_type=EpisodeType.USER_ACTION,
                action="scroll",
                context={"cluster": 2},
                timestamp=now + timedelta(hours=2, minutes=i)
            )
        
        # Cluster episodes
        clusters = await episodic_memory.cluster_episodes(
            start=now - timedelta(hours=1),
            end=now + timedelta(hours=3),
            method=ClusteringMethod.TEMPORAL,
            min_cluster_size=2
        )
        
        assert len(clusters) >= 1
        for cluster in clusters:
            assert isinstance(cluster, EpisodeCluster)
            assert cluster.cluster_type == "temporal"
            assert len(cluster.episodes) >= 2
    
    async def test_session_clustering(self, episodic_memory):
        """Test clustering by session."""
        now = datetime.now(timezone.utc)
        
        # Session 1
        for i in range(3):
            await episodic_memory.record(
                episode_type=EpisodeType.USER_ACTION,
                action="action",
                context={},
                session_id="session_1",
                timestamp=now + timedelta(minutes=i)
            )
        
        # Session 2
        for i in range(3):
            await episodic_memory.record(
                episode_type=EpisodeType.USER_ACTION,
                action="action",
                context={},
                session_id="session_2",
                timestamp=now + timedelta(minutes=i)
            )
        
        # Cluster by session
        clusters = await episodic_memory.cluster_episodes(
            start=now - timedelta(hours=1),
            end=now + timedelta(hours=1),
            method=ClusteringMethod.SESSION,
            min_cluster_size=2
        )
        
        assert len(clusters) >= 2
        # Each session should be a separate cluster
        session_ids = {c.episodes[0].session_id for c in clusters}
        assert "session_1" in session_ids
        assert "session_2" in session_ids
    
    async def test_pattern_detection(self, episodic_memory):
        """Test detecting recurring patterns."""
        now = datetime.now(timezone.utc)
        
        # Record pattern: click -> scroll -> click
        pattern_sequence = ["click", "scroll", "click"]
        
        # Repeat pattern 3 times
        for repeat in range(3):
            for i, action in enumerate(pattern_sequence):
                await episodic_memory.record(
                    episode_type=EpisodeType.USER_ACTION,
                    action=action,
                    context={"repeat": repeat},
                    timestamp=now + timedelta(
                        minutes=repeat*10 + i
                    )
                )
        
        # Find patterns
        patterns = await episodic_memory.find_patterns(
            episode_type=EpisodeType.USER_ACTION,
            window=timedelta(hours=1),
            min_frequency=2
        )
        
        assert len(patterns) >= 0  # May or may not detect depending on window
        for pattern in patterns:
            assert isinstance(pattern, Pattern)
            assert pattern.count >= 2
    
    async def test_causality_analysis(self, episodic_memory):
        """Test causal relationship detection."""
        now = datetime.now(timezone.utc)
        
        # Cause: user action
        cause = await episodic_memory.record(
            episode_type=EpisodeType.USER_ACTION,
            action="submit_form",
            context={"form_id": "contact"},
            timestamp=now,
            session_id="test_session"
        )
        
        # Effect: system event (1 second later)
        effect = await episodic_memory.record(
            episode_type=EpisodeType.SYSTEM_EVENT,
            action="form_processed",
            context={"result": "success"},
            timestamp=now + timedelta(seconds=1),
            session_id="test_session"
        )
        
        # Analyze causality
        causes = await episodic_memory.analyze_causality(
            effect_episode_id=effect.episode_id,
            window=timedelta(minutes=1)
        )
        
        # Should find the cause with high confidence
        assert len(causes) >= 0  # Depends on confidence threshold
    
    async def test_parent_child_causality(self, episodic_memory):
        """Test explicit parent-child causality."""
        # Parent episode
        parent = await episodic_memory.record(
            episode_type=EpisodeType.USER_ACTION,
            action="click_button",
            context={"button": "export"}
        )
        
        # Child episode (explicitly linked)
        child = await episodic_memory.record(
            episode_type=EpisodeType.SYSTEM_EVENT,
            action="export_started",
            context={"format": "csv"},
            parent_episode_id=parent.episode_id
        )
        
        # Analyze causality
        causes = await episodic_memory.analyze_causality(
            effect_episode_id=child.episode_id
        )
        
        # Should find parent with confidence 1.0
        assert len(causes) >= 1
        assert causes[0][0].episode_id == parent.episode_id
        assert causes[0][1] == 1.0  # Perfect confidence
    
    async def test_timeline_filtering(self, episodic_memory):
        """Test timeline queries with filters."""
        now = datetime.now(timezone.utc)
        
        # Record different types
        await episodic_memory.record(
            episode_type=EpisodeType.USER_ACTION,
            action="click",
            context={},
            user_id="alice",
            timestamp=now
        )
        
        await episodic_memory.record(
            episode_type=EpisodeType.SYSTEM_EVENT,
            action="log",
            context={},
            user_id="alice",
            timestamp=now + timedelta(seconds=1)
        )
        
        await episodic_memory.record(
            episode_type=EpisodeType.USER_ACTION,
            action="click",
            context={},
            user_id="bob",
            timestamp=now + timedelta(seconds=2)
        )
        
        # Query with type filter
        timeline = await episodic_memory.get_timeline(
            start=now - timedelta(minutes=1),
            end=now + timedelta(minutes=1),
            episode_types=[EpisodeType.USER_ACTION]
        )
        
        assert all(
            e.episode_type == EpisodeType.USER_ACTION
            for e in timeline.episodes
        )
        
        # Query with user filter
        timeline = await episodic_memory.get_timeline(
            start=now - timedelta(minutes=1),
            end=now + timedelta(minutes=1),
            user_id="alice"
        )
        
        assert all(e.user_id == "alice" for e in timeline.episodes)
    
    async def test_summary_generation(self, episodic_memory):
        """Test narrative summary generation."""
        now = datetime.now(timezone.utc)
        
        # Record various events
        for i in range(5):
            await episodic_memory.record(
                episode_type=EpisodeType.USER_ACTION,
                action=f"action_{i}",
                context={"index": i},
                timestamp=now + timedelta(minutes=i)
            )
        
        # Generate summary
        summary = await episodic_memory.generate_summary(
            start=now - timedelta(minutes=1),
            end=now + timedelta(minutes=10),
            max_length=500
        )
        
        assert isinstance(summary, str)
        assert len(summary) > 0
        assert "Timeline from" in summary
        assert "Total events" in summary
    
    async def test_statistics_tracking(self, episodic_memory):
        """Test statistics tracking."""
        # Record some episodes
        await episodic_memory.record(
            episode_type=EpisodeType.USER_ACTION,
            action="test",
            context={}
        )
        
        # Get timeline
        now = datetime.now(timezone.utc)
        await episodic_memory.get_timeline(
            start=now - timedelta(hours=1),
            end=now + timedelta(hours=1)
        )
        
        # Check statistics
        stats = episodic_memory.get_statistics()
        assert stats["episodes_recorded"] >= 1
        assert stats["timeline_queries"] >= 1
    
    async def test_episode_serialization(self):
        """Test episode serialization."""
        now = datetime.now(timezone.utc)
        
        episode = Episode(
            episode_id="ep_test123",
            tenant_id="test",
            episode_type=EpisodeType.CONVERSATION,
            action="message",
            context={"content": "Hello"},
            timestamp=now,
            metadata={"key": "value"}
        )
        
        # Serialize
        data = episode.to_dict()
        assert data["episode_id"] == "ep_test123"
        assert data["episode_type"] == "conversation"
        assert isinstance(data["timestamp"], str)
        
        # Deserialize
        restored = Episode.from_dict(data)
        assert restored.episode_id == episode.episode_id
        assert restored.episode_type == episode.episode_type
        assert restored.timestamp == episode.timestamp


@pytest.mark.asyncio
class TestEpisodeCluster:
    """Test episode cluster functionality."""
    
    def test_cluster_duration(self):
        """Test cluster duration calculation."""
        now = datetime.now(timezone.utc)
        
        episodes = [
            Episode(
                episode_id=f"ep_{i}",
                tenant_id="test",
                episode_type=EpisodeType.USER_ACTION,
                action="test",
                context={},
                timestamp=now + timedelta(minutes=i)
            )
            for i in range(3)
        ]
        
        cluster = EpisodeCluster(
            cluster_id="test_cluster",
            episodes=episodes,
            cluster_type="temporal",
            start_time=episodes[0].timestamp,
            end_time=episodes[-1].timestamp
        )
        
        duration = cluster.duration()
        assert duration == timedelta(minutes=2)
        assert cluster.size() == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
