"""
smrti/memory/tiers/long_term.py - Long-term Memory Tier

Long-term memory for persistent information storage with vector similarity search.
Optimized for semantic retrieval and knowledge persistence.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Union

from smrti.core.base import BaseMemoryTier
from smrti.core.exceptions import MemoryError, ValidationError
from smrti.core.protocols import TierStore, VectorStore, EmbeddingProvider
from smrti.core.registry import AdapterRegistry
from smrti.schemas.models import (
    MemoryQuery,
    RecordEnvelope,
    ConversationTurn,
    KnowledgeRecord,
    LongTermMemoryConfig
)


class LongTermMemory(BaseMemoryTier):
    """
    Long-term Memory Tier - Persistent information storage with semantic search.
    
    Characteristics:
    - Long retention (days to months, potentially indefinite)
    - Large capacity (thousands to millions of items)
    - Vector storage for semantic similarity
    - Embedding-based retrieval
    - Knowledge organization and clustering
    - Cross-reference and relationship tracking
    
    Use cases:
    - Learned facts and knowledge
    - Important conversation history
    - Reference information
    - Semantic knowledge base
    - Pattern recognition data
    - Educational content
    """
    
    def __init__(
        self,
        adapter_registry: AdapterRegistry,
        config: Optional[LongTermMemoryConfig] = None
    ):
        super().__init__(
            tier_name="long_term",
            adapter_registry=adapter_registry,
            config=config
        )
        
        # Long-term memory configuration
        self._default_retention = timedelta(days=config.retention_days if config else 365)
        self._similarity_threshold = config.similarity_threshold if config else 0.7
        self._max_similar_results = config.max_similar_results if config else 20
        self._embedding_dim = config.embedding_dimension if config else 768
        
        # Knowledge organization
        self._knowledge_clusters: Dict[str, Set[str]] = {}  # cluster_id -> record_ids
        self._cluster_centroids: Dict[str, List[float]] = {}  # cluster_id -> embedding
        self._record_clusters: Dict[str, str] = {}  # record_id -> cluster_id
        
        # Embedding and retrieval
        self._embedding_provider: Optional[EmbeddingProvider] = None
        self._enable_auto_clustering = config.enable_auto_clustering if config else True
        self._cluster_similarity_threshold = config.cluster_similarity_threshold if config else 0.8
        self._max_cluster_size = config.max_cluster_size if config else 100
        
        # Performance optimization
        self._embedding_cache: Dict[str, List[float]] = {}
        self._last_clustering = datetime.utcnow()
        self._clustering_interval = timedelta(hours=config.clustering_interval_hours if config else 24)
    
    async def initialize(self) -> None:
        """Initialize long-term memory tier with vector storage and embedding provider."""
        # Get vector storage adapter for long-term memory
        adapter = await self._adapter_registry.get_adapter(
            tier_name="long_term",
            required_capabilities=["vector_similarity", "metadata_filtering"]
        )
        
        if not adapter:
            raise MemoryError(
                "No suitable vector storage adapter found for long-term memory tier",
                tier="long_term",
                operation="initialize"
            )
        
        self._storage = adapter
        
        # Get embedding provider
        self._embedding_provider = await self._adapter_registry.get_embedding_provider()
        if not self._embedding_provider:
            self.logger.warning("No embedding provider available - similarity search will be limited")
        
        await super().initialize()
        
        # Start background clustering task
        if self._enable_auto_clustering:
            asyncio.create_task(self._periodic_clustering())
        
        self.logger.info(
            f"Long-term memory initialized (similarity_threshold={self._similarity_threshold}, "
            f"embedding_dim={self._embedding_dim})"
        )
    
    async def store(
        self, 
        record: RecordEnvelope,
        importance_score: float = 0.5,
        access_frequency: int = 1,
        source_tier: Optional[str] = None,
        force_embedding: bool = False
    ) -> str:
        """
        Store information in long-term memory with semantic embedding.
        
        Args:
            record: Memory record to store
            importance_score: Importance level (0.0-1.0)
            access_frequency: Number of previous accesses
            source_tier: Source memory tier (for tracking consolidation)
            force_embedding: Whether to force embedding generation
            
        Returns:
            Record ID of stored memory
        """
        # Set long-term memory tier
        record.tier = "long_term"
        
        # Generate or retrieve embedding
        if not record.embedding or force_embedding:
            if self._embedding_provider:
                content_text = self._extract_text_content(record)
                record.embedding = await self._embedding_provider.embed_text(content_text)
                self._embedding_cache[record.record_id] = record.embedding
            else:
                self.logger.warning(f"No embedding generated for record {record.record_id}")
        
        # Update relevance score based on importance and access frequency
        record.relevance_score = max(record.relevance_score, importance_score)
        record.access_count = max(record.access_count, access_frequency)
        
        # Add source tier metadata
        if source_tier:
            record.metadata = record.metadata or {}
            record.metadata["source_tier"] = source_tier
            record.metadata["consolidation_time"] = datetime.utcnow().isoformat()
        
        # Store in vector storage
        record_id = await self._storage.store(record, self._default_retention)
        
        # Update clustering if enabled
        if self._enable_auto_clustering and record.embedding:
            await self._update_clustering(record_id, record.embedding)
        
        self.logger.debug(
            f"Stored record {record_id} in long-term memory "
            f"(importance={importance_score}, embedding_dim={len(record.embedding) if record.embedding else 0})"
        )
        
        return record_id
    
    async def retrieve(
        self, 
        record_id: str,
        include_similar: bool = False,
        max_similar: int = 5
    ) -> Optional[RecordEnvelope]:
        """
        Retrieve a specific record from long-term memory.
        
        Args:
            record_id: ID of record to retrieve
            include_similar: Whether to include similar records
            max_similar: Maximum number of similar records to include
            
        Returns:
            Record with optional similar records in metadata
        """
        record = await self._storage.retrieve(record_id)
        
        if record and include_similar and record.embedding:
            # Find similar records
            similar_records = await self.find_similar(
                record.embedding, 
                max_results=max_similar,
                exclude_ids=[record_id]
            )
            
            # Add similar record IDs to metadata
            if similar_records:
                record.metadata = record.metadata or {}
                record.metadata["similar_records"] = [r.record_id for r in similar_records]
        
        return record
    
    async def query(
        self,
        query: MemoryQuery,
        use_semantic_search: bool = True,
        similarity_threshold: Optional[float] = None
    ) -> List[RecordEnvelope]:
        """
        Query long-term memory with semantic similarity search.
        
        Args:
            query: Memory query parameters
            use_semantic_search: Whether to use embedding-based search
            similarity_threshold: Minimum similarity score (overrides default)
            
        Returns:
            List of matching records, sorted by relevance and similarity
        """
        results = []
        
        if use_semantic_search and query.query_text and self._embedding_provider:
            # Generate query embedding
            query_embedding = await self._embedding_provider.embed_text(query.query_text)
            
            # Perform similarity search
            similarity_results = await self.find_similar(
                query_embedding,
                max_results=query.limit,
                similarity_threshold=similarity_threshold or self._similarity_threshold,
                metadata_filter={
                    "tenant_id": query.tenant_id,
                    "namespace": query.namespace
                } if query.tenant_id or query.namespace else None
            )
            
            results.extend(similarity_results)
        
        # Also perform traditional query if no semantic results or as fallback
        if not results or not use_semantic_search:
            traditional_results = await self._storage.query(query)
            
            # Merge results, avoiding duplicates
            existing_ids = {r.record_id for r in results}
            for record in traditional_results:
                if record.record_id not in existing_ids:
                    results.append(record)
        
        # Sort by relevance score
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        
        return results[:query.limit]
    
    async def find_similar(
        self,
        query_embedding: List[float],
        max_results: int = 10,
        similarity_threshold: Optional[float] = None,
        exclude_ids: Optional[List[str]] = None,
        metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[RecordEnvelope]:
        """
        Find records similar to the given embedding.
        
        Args:
            query_embedding: Embedding to search for
            max_results: Maximum number of results
            similarity_threshold: Minimum similarity score
            exclude_ids: Record IDs to exclude from results
            metadata_filter: Optional metadata filtering
            
        Returns:
            List of similar records sorted by similarity
        """
        if not isinstance(self._storage, VectorStore):
            self.logger.warning("Storage adapter does not support vector similarity search")
            return []
        
        # Use default threshold if not specified
        threshold = similarity_threshold or self._similarity_threshold
        
        try:
            # Perform vector similarity search
            similar_records = await self._storage.similarity_search(
                query_embedding=query_embedding,
                max_results=max_results,
                similarity_threshold=threshold,
                metadata_filter=metadata_filter
            )
            
            # Filter out excluded IDs
            if exclude_ids:
                similar_records = [
                    record for record in similar_records
                    if record.record_id not in exclude_ids
                ]
            
            return similar_records
            
        except Exception as e:
            self.logger.error(f"Error during similarity search: {e}")
            return []
    
    async def find_by_cluster(
        self,
        cluster_id: str,
        max_results: int = 50
    ) -> List[RecordEnvelope]:
        """Get all records in a specific knowledge cluster."""
        if cluster_id not in self._knowledge_clusters:
            return []
        
        record_ids = list(self._knowledge_clusters[cluster_id])
        
        # Retrieve records
        records = []
        for record_id in record_ids[:max_results]:
            record = await self._storage.retrieve(record_id)
            if record:
                records.append(record)
        
        # Sort by relevance score
        records.sort(key=lambda r: r.relevance_score, reverse=True)
        
        return records
    
    async def get_knowledge_clusters(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all knowledge clusters."""
        clusters = {}
        
        for cluster_id, record_ids in self._knowledge_clusters.items():
            # Calculate cluster statistics
            record_count = len(record_ids)
            centroid = self._cluster_centroids.get(cluster_id)
            
            # Sample some records to determine cluster topics
            sample_records = []
            for record_id in list(record_ids)[:5]:  # Sample up to 5 records
                record = await self._storage.retrieve(record_id)
                if record:
                    sample_records.append({
                        "record_id": record.record_id,
                        "content_preview": str(record.content)[:100] + "...",
                        "relevance_score": record.relevance_score
                    })
            
            clusters[cluster_id] = {
                "record_count": record_count,
                "has_centroid": centroid is not None,
                "sample_records": sample_records
            }
        
        return clusters
    
    def _extract_text_content(self, record: RecordEnvelope) -> str:
        """Extract text content from a record for embedding."""
        content_parts = []
        
        # Extract content based on record type
        content = record.content
        
        if hasattr(content, 'text'):
            content_parts.append(content.text)
        elif hasattr(content, 'message'):
            content_parts.append(content.message)
        elif hasattr(content, 'description'):
            content_parts.append(content.description)
        elif isinstance(content, dict):
            # Extract text from dictionary content
            for key, value in content.items():
                if isinstance(value, str) and len(value) > 10:  # Meaningful text
                    content_parts.append(f"{key}: {value}")
        else:
            content_parts.append(str(content))
        
        # Add tags and source
        if record.tags:
            content_parts.append("Tags: " + ", ".join(record.tags))
        
        if record.source:
            content_parts.append(f"Source: {record.source}")
        
        return "\n".join(content_parts)
    
    async def _update_clustering(self, record_id: str, embedding: List[float]) -> None:
        """Update knowledge clusters when a new record is added."""
        if not self._enable_auto_clustering:
            return
        
        try:
            # Find the most similar cluster
            best_cluster_id = None
            best_similarity = 0.0
            
            for cluster_id, centroid in self._cluster_centroids.items():
                similarity = self._cosine_similarity(embedding, centroid)
                if similarity > best_similarity and similarity >= self._cluster_similarity_threshold:
                    best_similarity = similarity
                    best_cluster_id = cluster_id
            
            if best_cluster_id:
                # Add to existing cluster
                self._knowledge_clusters[best_cluster_id].add(record_id)
                self._record_clusters[record_id] = best_cluster_id
                
                # Update cluster centroid
                await self._update_cluster_centroid(best_cluster_id)
                
            else:
                # Create new cluster if we don't have too many
                if len(self._knowledge_clusters) < 1000:  # Arbitrary limit
                    new_cluster_id = f"cluster_{len(self._knowledge_clusters)}"
                    self._knowledge_clusters[new_cluster_id] = {record_id}
                    self._cluster_centroids[new_cluster_id] = embedding.copy()
                    self._record_clusters[record_id] = new_cluster_id
                    
                    self.logger.debug(f"Created new knowledge cluster {new_cluster_id}")
        
        except Exception as e:
            self.logger.error(f"Error updating clustering for record {record_id}: {e}")
    
    async def _update_cluster_centroid(self, cluster_id: str) -> None:
        """Update the centroid of a knowledge cluster."""
        if cluster_id not in self._knowledge_clusters:
            return
        
        record_ids = list(self._knowledge_clusters[cluster_id])
        embeddings = []
        
        # Collect embeddings from cluster records
        for record_id in record_ids:
            if record_id in self._embedding_cache:
                embeddings.append(self._embedding_cache[record_id])
            else:
                # Try to get embedding from stored record
                record = await self._storage.retrieve(record_id)
                if record and record.embedding:
                    embeddings.append(record.embedding)
                    self._embedding_cache[record_id] = record.embedding
        
        if embeddings:
            # Calculate new centroid as average of embeddings
            centroid = [
                sum(emb[i] for emb in embeddings) / len(embeddings)
                for i in range(len(embeddings[0]))
            ]
            self._cluster_centroids[cluster_id] = centroid
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if len(a) != len(b):
            return 0.0
        
        dot_product = sum(x * y for x, y in zip(a, b))
        magnitude_a = sum(x * x for x in a) ** 0.5
        magnitude_b = sum(x * x for x in b) ** 0.5
        
        if magnitude_a == 0.0 or magnitude_b == 0.0:
            return 0.0
        
        return dot_product / (magnitude_a * magnitude_b)
    
    async def _periodic_clustering(self) -> None:
        """Periodic re-clustering and optimization of knowledge clusters."""
        while True:
            try:
                await asyncio.sleep(self._clustering_interval.total_seconds())
                
                now = datetime.utcnow()
                if now - self._last_clustering < self._clustering_interval:
                    continue
                
                # Clean up empty clusters
                empty_clusters = [
                    cluster_id for cluster_id, record_ids in self._knowledge_clusters.items()
                    if not record_ids
                ]
                
                for cluster_id in empty_clusters:
                    del self._knowledge_clusters[cluster_id]
                    self._cluster_centroids.pop(cluster_id, None)
                
                # Split overly large clusters
                large_clusters = [
                    cluster_id for cluster_id, record_ids in self._knowledge_clusters.items()
                    if len(record_ids) > self._max_cluster_size
                ]
                
                for cluster_id in large_clusters:
                    await self._split_cluster(cluster_id)
                
                # Update all cluster centroids
                for cluster_id in self._knowledge_clusters:
                    await self._update_cluster_centroid(cluster_id)
                
                self._last_clustering = now
                
                self.logger.info(
                    f"Completed clustering update: {len(self._knowledge_clusters)} clusters, "
                    f"split {len(large_clusters)} large clusters"
                )
                
            except Exception as e:
                self.logger.error(f"Error during periodic clustering: {e}")
    
    async def _split_cluster(self, cluster_id: str) -> None:
        """Split a large cluster into smaller ones using k-means-like approach."""
        if cluster_id not in self._knowledge_clusters:
            return
        
        record_ids = list(self._knowledge_clusters[cluster_id])
        embeddings = []
        valid_record_ids = []
        
        # Collect embeddings
        for record_id in record_ids:
            if record_id in self._embedding_cache:
                embeddings.append(self._embedding_cache[record_id])
                valid_record_ids.append(record_id)
            else:
                record = await self._storage.retrieve(record_id)
                if record and record.embedding:
                    embeddings.append(record.embedding)
                    valid_record_ids.append(record_id)
                    self._embedding_cache[record_id] = record.embedding
        
        if len(embeddings) < 4:  # Not enough data to split meaningfully
            return
        
        # Simple 2-way clustering based on similarity to current centroid
        centroid = self._cluster_centroids[cluster_id]
        
        # Split into two groups based on similarity to centroid
        group1, group2 = [], []
        for i, embedding in enumerate(embeddings):
            similarity = self._cosine_similarity(embedding, centroid)
            if similarity > 0.8:  # High similarity
                group1.append(valid_record_ids[i])
            else:
                group2.append(valid_record_ids[i])
        
        if len(group1) > 0 and len(group2) > 0:
            # Update original cluster with group1
            self._knowledge_clusters[cluster_id] = set(group1)
            
            # Create new cluster with group2
            new_cluster_id = f"{cluster_id}_split_{datetime.utcnow().timestamp()}"
            self._knowledge_clusters[new_cluster_id] = set(group2)
            
            # Update record cluster mappings
            for record_id in group2:
                self._record_clusters[record_id] = new_cluster_id
            
            # Update centroids
            await self._update_cluster_centroid(cluster_id)
            await self._update_cluster_centroid(new_cluster_id)
            
            self.logger.debug(
                f"Split cluster {cluster_id} into {len(group1)} and {len(group2)} records"
            )
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get long-term memory statistics."""
        base_stats = await super().get_stats()
        
        # Clustering statistics
        total_clusters = len(self._knowledge_clusters)
        total_clustered_records = sum(len(records) for records in self._knowledge_clusters.values())
        avg_cluster_size = total_clustered_records / max(1, total_clusters)
        
        # Embedding statistics
        cached_embeddings = len(self._embedding_cache)
        
        long_term_stats = {
            "tier_name": "long_term",
            "similarity_threshold": self._similarity_threshold,
            "embedding_dimension": self._embedding_dim,
            "knowledge_clusters": total_clusters,
            "clustered_records": total_clustered_records,
            "average_cluster_size": avg_cluster_size,
            "cached_embeddings": cached_embeddings,
            "auto_clustering_enabled": self._enable_auto_clustering,
            "clustering_interval_hours": self._clustering_interval.total_seconds() / 3600,
            "last_clustering": self._last_clustering.isoformat(),
            "max_cluster_size": self._max_cluster_size,
            "cluster_similarity_threshold": self._cluster_similarity_threshold
        }
        
        base_stats.update(long_term_stats)
        return base_stats
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check for long-term memory tier."""
        health = await super().health_check()
        
        # Long-term memory specific health metrics
        embedding_provider_available = self._embedding_provider is not None
        clustering_health = (datetime.utcnow() - self._last_clustering) < self._clustering_interval * 2
        
        # Check cluster health
        total_clusters = len(self._knowledge_clusters)
        oversized_clusters = len([
            cluster_id for cluster_id, records in self._knowledge_clusters.items()
            if len(records) > self._max_cluster_size * 1.5
        ])
        
        cluster_health_status = "healthy"
        if oversized_clusters > total_clusters * 0.1:  # More than 10% oversized
            cluster_health_status = "warning"
        
        long_term_health = {
            "embedding_provider_available": embedding_provider_available,
            "clustering_enabled": self._enable_auto_clustering,
            "clustering_running": clustering_health,
            "cluster_health_status": cluster_health_status,
            "total_clusters": total_clusters,
            "oversized_clusters": oversized_clusters,
            "embedding_cache_size": len(self._embedding_cache)
        }
        
        health.update(long_term_health)
        return health