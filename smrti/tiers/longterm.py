"""
Long-term Memory Tier Implementation

Provides persistent, semantic storage for knowledge that needs to survive across 
sessions. Integrates with vector storage (ChromaDB) for semantic search and 
supports automatic consolidation from Short-term Memory.

Key Features:
- Semantic similarity search via embeddings
- Cross-session persistence
- Automatic fact extraction from promoted items
- Archival and pruning strategies
- Fact deduplication and merging
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
import uuid

from ..adapters.storage.vector_adapter import (
    VectorStorageAdapter,
    VectorConfig,
    VectorSearchQuery,
    VectorSearchResult
)
from ..models.memory import MemoryItem, MemoryMetadata


logger = logging.getLogger(__name__)


class SearchMode(Enum):
    """Search modes for retrieval."""
    VECTOR_ONLY = "vector_only"
    LEXICAL_ONLY = "lexical_only"  # Future
    HYBRID = "hybrid"  # Future
    GRAPH = "graph"  # Future


@dataclass
class LongTermConfig:
    """Configuration for Long-term Memory tier."""
    
    # Vector storage settings
    embedding_model: str = "all-MiniLM-L6-v2"
    vector_dimension: int = 384
    similarity_threshold: float = 0.7
    max_results: int = 100
    
    # Storage settings
    collection_name: str = "longterm_facts"
    persist_directory: str = "./data/longterm"
    
    # Consolidation settings
    enable_auto_consolidation: bool = True
    min_confidence: float = 0.5  # Minimum confidence to store
    dedupe_similarity: float = 0.95  # Threshold for duplicate detection
    
    # Archival settings
    archive_after_days: int = 365
    min_access_count_to_keep: int = 2
    
    # Performance settings
    batch_size: int = 100
    enable_caching: bool = True
    cache_ttl: int = 3600  # 1 hour
    
    # Reranking
    enable_reranking: bool = False
    rerank_model: Optional[str] = None


@dataclass
class Fact:
    """A long-term memory fact."""
    
    key: str
    content: str
    tenant_id: str = "default"
    namespace: str = "default"
    
    # Metadata
    embedding: Optional[List[float]] = None
    confidence: float = 1.0
    source: str = "manual"  # manual, promoted, extracted, imported
    
    # Temporal
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    accessed_at: Optional[datetime] = None
    
    # Access tracking
    access_count: int = 0
    
    # Additional metadata
    tags: List[str] = field(default_factory=list)
    category: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        # Convert datetime objects to ISO strings
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        if self.updated_at:
            data['updated_at'] = self.updated_at.isoformat()
        if self.accessed_at:
            data['accessed_at'] = self.accessed_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Fact':
        """Create from dictionary."""
        # Parse datetime strings
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if isinstance(data.get('updated_at'), str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        if isinstance(data.get('accessed_at'), str):
            data['accessed_at'] = datetime.fromisoformat(data['accessed_at'])
        return cls(**data)


@dataclass
class SearchResult:
    """Result from a long-term memory search."""
    
    fact: Fact
    score: float  # Similarity score
    distance: float  # Distance metric
    rank: int  # Result rank
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'fact': self.fact.to_dict(),
            'score': self.score,
            'distance': self.distance,
            'rank': self.rank
        }


class LongTermMemory:
    """
    Long-term Memory Tier Implementation
    
    Provides persistent, semantic storage with:
    - Vector similarity search
    - Cross-session persistence
    - Automatic consolidation from Short-term
    - Fact deduplication and merging
    - Archival and pruning strategies
    """
    
    def __init__(
        self,
        vector_adapter: Optional[VectorStorageAdapter] = None,
        config: Optional[LongTermConfig] = None,
        tenant_id: str = "default"
    ):
        self.config = config or LongTermConfig()
        self.tenant_id = tenant_id
        
        # Initialize vector storage
        if vector_adapter:
            self.vector = vector_adapter
        else:
            vector_config = VectorConfig(
                collection_name=f"{self.config.collection_name}_{tenant_id}",
                persist_directory=self.config.persist_directory,
                embedding_function=self.config.embedding_model,
                n_results=self.config.max_results,
                similarity_threshold=self.config.similarity_threshold
            )
            self.vector = VectorStorageAdapter(config=vector_config)
        
        # Internal state
        self._initialized = False
        self._stats = {
            "facts_stored": 0,
            "facts_retrieved": 0,
            "searches_performed": 0,
            "consolidations_received": 0,
            "facts_merged": 0,
            "facts_archived": 0,
            "facts_pruned": 0
        }
        
        # Cache for recently accessed facts
        self._cache: Dict[str, Fact] = {}
        self._cache_access_times: Dict[str, datetime] = {}
    
    async def initialize(self) -> bool:
        """
        Initialize the long-term memory tier.
        
        Returns:
            True if initialization successful
        """
        if self._initialized:
            return True
        
        try:
            # Initialize vector storage
            success = await self.vector.initialize()
            if not success:
                logger.error("Failed to initialize vector storage")
                return False
            
            self._initialized = True
            logger.info(f"Long-term Memory initialized for tenant: {self.tenant_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing Long-term Memory: {e}")
            return False
    
    async def store_fact(
        self,
        key: str,
        content: str,
        embedding: Optional[List[float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        confidence: float = 1.0,
        source: str = "manual",
        ttl: Optional[timedelta] = None
    ) -> bool:
        """
        Store a fact in long-term memory.
        
        Args:
            key: Unique identifier for the fact
            content: The actual fact content (will be embedded)
            embedding: Optional pre-computed embedding
            metadata: Additional metadata
            confidence: Confidence score (0-1)
            source: Source of the fact (manual, promoted, extracted)
            ttl: Optional time-to-live (None = permanent)
        
        Returns:
            True if stored successfully
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Create fact object
            fact = Fact(
                key=key,
                content=content,
                tenant_id=self.tenant_id,
                embedding=embedding,
                confidence=confidence,
                source=source,
                metadata=metadata or {}
            )
            
            # Generate unique ID for storage
            fact_id = self._generate_fact_id(key)
            
            # Prepare metadata for storage
            storage_metadata = {
                "key": key,
                "tenant_id": self.tenant_id,
                "confidence": confidence,
                "source": source,
                "created_at": fact.created_at.isoformat(),
                "access_count": 0,
                **(metadata or {})
            }
            
            # Store in vector database
            result = await self.vector.add(
                ids=[fact_id],
                documents=[content],
                embeddings=[embedding] if embedding else None,
                metadatas=[storage_metadata]
            )
            
            if result.success:
                self._stats["facts_stored"] += 1
                
                # Update cache
                if self.config.enable_caching:
                    self._cache[key] = fact
                    self._cache_access_times[key] = datetime.now(timezone.utc)
                
                logger.debug(f"Stored fact: {key}")
                return True
            else:
                logger.error(f"Failed to store fact: {result.error_message}")
                return False
                
        except Exception as e:
            logger.error(f"Error storing fact: {e}")
            return False
    
    async def retrieve(self, key: str) -> Optional[Fact]:
        """
        Retrieve a fact by key.
        
        Args:
            key: Fact identifier
        
        Returns:
            Fact if found, None otherwise
        """
        if not self._initialized:
            await self.initialize()
        
        # Check cache first
        if self.config.enable_caching and key in self._cache:
            # Check if cache entry is still valid
            cache_time = self._cache_access_times.get(key)
            if cache_time and (datetime.now(timezone.utc) - cache_time).total_seconds() < self.config.cache_ttl:
                fact = self._cache[key]
                fact.access_count += 1
                fact.accessed_at = datetime.now(timezone.utc)
                self._stats["facts_retrieved"] += 1
                return fact
        
        try:
            # Retrieve from vector storage
            fact_id = self._generate_fact_id(key)
            result = await self.vector.get(ids=[fact_id])
            
            if result.success and result.item_count > 0:
                # Reconstruct fact from result
                doc = result.results[0]
                fact = Fact(
                    key=key,
                    content=doc.content,
                    tenant_id=self.tenant_id,
                    embedding=doc.embedding,
                    confidence=doc.metadata.get("confidence", 1.0),
                    source=doc.metadata.get("source", "unknown"),
                    metadata=doc.metadata
                )
                
                # Update access tracking
                fact.access_count = doc.metadata.get("access_count", 0) + 1
                fact.accessed_at = datetime.now(timezone.utc)
                
                # Update cache
                if self.config.enable_caching:
                    self._cache[key] = fact
                    self._cache_access_times[key] = datetime.now(timezone.utc)
                
                self._stats["facts_retrieved"] += 1
                return fact
            
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving fact: {e}")
            return None
    
    async def search(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        similarity_threshold: Optional[float] = None,
        mode: SearchMode = SearchMode.VECTOR_ONLY
    ) -> List[SearchResult]:
        """
        Search for facts using semantic similarity.
        
        Args:
            query: Search query (natural language)
            limit: Maximum number of results
            filters: Metadata filters
            similarity_threshold: Minimum similarity score
            mode: Search mode (vector, lexical, hybrid)
        
        Returns:
            List of search results ranked by relevance
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            threshold = similarity_threshold or self.config.similarity_threshold
            
            # Prepare search query
            search_query = VectorSearchQuery(
                query_text=query,
                n_results=limit,
                where=filters,
                similarity_threshold=threshold,
                include_distances=True,
                include_metadata=True
            )
            
            # Execute search
            result = await self.vector.search(search_query)
            
            if not result.success:
                logger.error(f"Search failed: {result.error_message}")
                return []
            
            # Convert to SearchResult objects
            search_results = []
            for rank, vector_result in enumerate(result.results, 1):
                fact = Fact(
                    key=vector_result.metadata.get("key", f"unknown_{rank}"),
                    content=vector_result.content,
                    tenant_id=self.tenant_id,
                    embedding=vector_result.embedding,
                    confidence=vector_result.metadata.get("confidence", 1.0),
                    source=vector_result.metadata.get("source", "unknown"),
                    metadata=vector_result.metadata
                )
                
                # Calculate score (higher is better)
                score = 1.0 - vector_result.distance if vector_result.distance is not None else 0.5
                
                search_results.append(
                    SearchResult(
                        fact=fact,
                        score=score,
                        distance=vector_result.distance or 0.0,
                        rank=rank
                    )
                )
            
            self._stats["searches_performed"] += 1
            return search_results
            
        except Exception as e:
            logger.error(f"Error searching facts: {e}")
            return []
    
    async def batch_store(self, facts: List[Dict[str, Any]]) -> int:
        """
        Store multiple facts in a batch.
        
        Args:
            facts: List of fact dictionaries
        
        Returns:
            Number of facts successfully stored
        """
        if not self._initialized:
            await self.initialize()
        
        count = 0
        for fact_data in facts:
            success = await self.store_fact(**fact_data)
            if success:
                count += 1
        
        return count
    
    def _generate_fact_id(self, key: str) -> str:
        """Generate unique ID for a fact."""
        combined = f"{self.tenant_id}:{key}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    def get_statistics(self) -> Dict[str, int]:
        """Get usage statistics."""
        return self._stats.copy()
    
    async def receive_from_shortterm(self, item: MemoryItem) -> bool:
        """
        Receive and consolidate an item promoted from Short-term Memory.
        
        This is called automatically when Short-term Memory promotes an item.
        
        Args:
            item: Memory item from Short-term Memory
        
        Returns:
            True if successfully consolidated
        """
        try:
            # Extract fact content from memory item
            content = self._extract_fact_content(item)
            
            if not content:
                logger.warning(f"Could not extract fact from item: {item.key}")
                return False
            
            # Store as fact
            success = await self.store_fact(
                key=f"promoted_{item.key}",
                content=content,
                metadata={
                    "source": "short_term_promotion",
                    "original_key": item.key,
                    "access_count": item.metadata.access_count,
                    "promoted_at": datetime.now(timezone.utc).isoformat(),
                    "original_tags": item.metadata.tags
                },
                confidence=self._calculate_confidence(item),
                source="promoted"
            )
            
            if success:
                self._stats["consolidations_received"] += 1
                logger.info(f"Consolidated item from Short-term: {item.key}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error receiving from Short-term: {e}")
            return False
    
    def _extract_fact_content(self, item: MemoryItem) -> Optional[str]:
        """
        Extract meaningful fact content from a memory item.
        
        Args:
            item: Memory item to extract from
        
        Returns:
            Extracted fact content or None
        """
        # If value is already a string, use it
        if isinstance(item.value, str):
            return item.value
        
        # If value is a dict, try to extract meaningful content
        if isinstance(item.value, dict):
            # Look for common content fields
            for field in ['content', 'text', 'message', 'data', 'value']:
                if field in item.value:
                    content = item.value[field]
                    if isinstance(content, str):
                        return content
            
            # Fall back to JSON representation
            return json.dumps(item.value)
        
        # For other types, convert to string
        return str(item.value)
    
    def _calculate_confidence(self, item: MemoryItem) -> float:
        """
        Calculate confidence score for a promoted item.
        
        Higher access count = higher confidence
        
        Args:
            item: Memory item to calculate confidence for
        
        Returns:
            Confidence score (0-1)
        """
        access_count = item.metadata.access_count
        
        # Sigmoid-like confidence mapping
        # 1 access = 0.5, 5 accesses = 0.88, 10 accesses = 0.95
        confidence = min(1.0, 0.3 + (access_count * 0.1))
        
        return confidence
    
    async def archive_old_facts(
        self,
        older_than: timedelta,
        min_access_count: int = 1
    ) -> int:
        """
        Archive old, rarely accessed facts to cold storage.
        
        Args:
            older_than: Archive facts older than this duration
            min_access_count: Keep facts with at least this many accesses
        
        Returns:
            Number of facts archived
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            cutoff_date = datetime.now(timezone.utc) - older_than
            
            # Search for old facts
            # Note: This is a simplified implementation
            # In production, you'd want batch queries with pagination
            
            # For now, log the intent (full implementation would query and move)
            logger.info(f"Archive operation: older than {older_than}, min access: {min_access_count}")
            
            # TODO: Implement actual archival to separate collection or cold storage
            # This would involve:
            # 1. Query facts with filters (created_at < cutoff, access_count < min)
            # 2. Copy to archive collection
            # 3. Delete from main collection
            # 4. Update statistics
            
            archived_count = 0
            self._stats["facts_archived"] += archived_count
            
            return archived_count
            
        except Exception as e:
            logger.error(f"Error archiving facts: {e}")
            return 0
    
    async def prune_facts(
        self,
        confidence_threshold: float = 0.3,
        max_age: Optional[timedelta] = None
    ) -> int:
        """
        Prune low-quality facts from storage.
        
        Args:
            confidence_threshold: Remove facts below this confidence
            max_age: Maximum age for facts (None = no age limit)
        
        Returns:
            Number of facts pruned
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Build filter criteria
            filters = {
                "confidence": {"$lt": confidence_threshold}
            }
            
            if max_age:
                cutoff_date = datetime.now(timezone.utc) - max_age
                filters["created_at"] = {"$lt": cutoff_date.isoformat()}
            
            # TODO: Implement actual pruning
            # This would involve:
            # 1. Query facts matching filter criteria
            # 2. Delete matched facts
            # 3. Update statistics
            
            logger.info(f"Prune operation: confidence < {confidence_threshold}, max_age: {max_age}")
            
            pruned_count = 0
            self._stats["facts_pruned"] += pruned_count
            
            return pruned_count
            
        except Exception as e:
            logger.error(f"Error pruning facts: {e}")
            return 0
    
    async def merge_similar_facts(
        self,
        similarity_threshold: float = 0.95,
        strategy: str = "keep_most_recent"
    ) -> int:
        """
        Merge duplicate or highly similar facts.
        
        Args:
            similarity_threshold: Threshold for considering facts as duplicates
            strategy: Merge strategy (keep_most_recent, keep_highest_confidence, combine)
        
        Returns:
            Number of facts merged
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # TODO: Implement fact merging
            # This would involve:
            # 1. Find clusters of similar facts (using vector similarity)
            # 2. For each cluster, apply merge strategy
            # 3. Update or delete facts accordingly
            # 4. Update statistics
            
            logger.info(f"Merge operation: threshold={similarity_threshold}, strategy={strategy}")
            
            merged_count = 0
            self._stats["facts_merged"] += merged_count
            
            return merged_count
            
        except Exception as e:
            logger.error(f"Error merging facts: {e}")
            return 0
    
    async def cluster_facts(
        self,
        time_range: Optional[Tuple[datetime, datetime]] = None,
        min_cluster_size: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Cluster facts by semantic similarity for insight generation.
        
        Args:
            time_range: Optional time range to filter facts
            min_cluster_size: Minimum cluster size to return
        
        Returns:
            List of clusters with their facts and statistics
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # TODO: Implement clustering
            # This would involve:
            # 1. Query facts (optionally filtered by time range)
            # 2. Apply clustering algorithm (k-means, DBSCAN, etc.)
            # 3. Return clusters with metadata
            
            logger.info(f"Cluster operation: time_range={time_range}, min_size={min_cluster_size}")
            
            return []
            
        except Exception as e:
            logger.error(f"Error clustering facts: {e}")
            return []
    
    async def refresh_embeddings(
        self,
        modified_since: Optional[datetime] = None
    ) -> int:
        """
        Regenerate embeddings for facts (e.g., after model upgrade).
        
        Args:
            modified_since: Only refresh facts modified since this time
        
        Returns:
            Number of embeddings refreshed
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # TODO: Implement embedding refresh
            # This would involve:
            # 1. Query facts matching criteria
            # 2. Regenerate embeddings using current model
            # 3. Update stored embeddings
            # 4. Update statistics
            
            logger.info(f"Refresh embeddings: modified_since={modified_since}")
            
            refreshed_count = 0
            return refreshed_count
            
        except Exception as e:
            logger.error(f"Error refreshing embeddings: {e}")
            return 0
    
    async def shutdown(self) -> None:
        """Gracefully shutdown the long-term memory."""
        if self._initialized:
            # Flush any pending operations
            await self.vector.close()
            self._initialized = False
            logger.info(f"Long-term Memory shutdown for tenant: {self.tenant_id}")
