"""
smrti/core/protocols.py - Protocol interfaces for Smrti components

Defines the complete protocol interface hierarchy following the PRD specification.
These protocols enable adapter swappability and capability negotiation.
"""

from abc import abstractmethod
from datetime import datetime, timedelta
from typing import Any, AsyncIterator, Protocol, runtime_checkable

from smrti.schemas.models import (
    ConversationTurn,
    ContextSection,
    EventRecord,
    FactRecord,
    MemoryQuery,
    RecordEnvelope,
    SmrtiContext
)


@runtime_checkable
class EmbeddingProvider(Protocol):
    """
    Embedding generation protocol.
    
    Providers must implement text-to-vector embedding generation
    with consistent dimensionality and semantic meaning.
    """
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the embedding model being used."""
        ...
    
    @property
    @abstractmethod
    def embedding_dim(self) -> int:
        """Dimensionality of generated embeddings."""
        ...
    
    @property
    @abstractmethod
    def max_tokens(self) -> int:
        """Maximum token length for input text."""
        ...
    
    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        """
        Generate embedding for single text.
        
        Args:
            text: Input text to embed
            
        Returns:
            Dense embedding vector
            
        Raises:
            EmbeddingError: If embedding generation fails
        """
        ...
    
    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts efficiently.
        
        Args:
            texts: List of input texts
            
        Returns:
            List of embedding vectors in same order as inputs
            
        Raises:
            EmbeddingError: If any embedding fails
            CapacityExceededError: If batch size exceeds limits
        """
        ...
    
    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """
        Check provider health and return status information.
        
        Returns:
            Status dictionary with health metrics
        """
        ...


@runtime_checkable
class TierStore(Protocol):
    """
    Base protocol for memory tier storage.
    
    All memory tiers implement this interface to provide
    standardized storage and retrieval operations.
    """
    
    @property
    @abstractmethod
    def tier_name(self) -> str:
        """Name of this memory tier."""
        ...
    
    @property
    @abstractmethod
    def supports_ttl(self) -> bool:
        """Whether this tier supports time-to-live expiration."""
        ...
    
    @property
    @abstractmethod
    def supports_similarity_search(self) -> bool:
        """Whether this tier supports vector similarity search."""
        ...
    
    @abstractmethod
    async def store(
        self, 
        record: RecordEnvelope,
        ttl: timedelta | None = None
    ) -> str:
        """
        Store a memory record.
        
        Args:
            record: Memory record to store
            ttl: Optional time-to-live for automatic expiration
            
        Returns:
            Storage identifier for the record
            
        Raises:
            ValidationError: If record is invalid
            AdapterError: If storage operation fails
        """
        ...
    
    @abstractmethod
    async def retrieve(self, record_id: str) -> RecordEnvelope | None:
        """
        Retrieve a specific memory record.
        
        Args:
            record_id: Identifier of record to retrieve
            
        Returns:
            Memory record if found, None otherwise
            
        Raises:
            AdapterError: If retrieval operation fails
        """
        ...
    
    @abstractmethod
    async def query(self, query: MemoryQuery) -> list[RecordEnvelope]:
        """
        Query records matching criteria.
        
        Args:
            query: Query specification with filters and limits
            
        Returns:
            List of matching records ordered by relevance
            
        Raises:
            ValidationError: If query is malformed
            AdapterError: If query execution fails
        """
        ...
    
    @abstractmethod
    async def delete(self, record_id: str) -> bool:
        """
        Delete a memory record.
        
        Args:
            record_id: Identifier of record to delete
            
        Returns:
            True if record was deleted, False if not found
            
        Raises:
            AdapterError: If deletion fails
        """
        ...
    
    @abstractmethod
    async def update_relevance(
        self, 
        record_id: str, 
        new_relevance: float
    ) -> bool:
        """
        Update relevance score for a record.
        
        Args:
            record_id: Record identifier
            new_relevance: New relevance score
            
        Returns:
            True if updated, False if not found
            
        Raises:
            ValidationError: If relevance score is invalid
            AdapterError: If update fails
        """
        ...
    
    @abstractmethod
    async def cleanup_expired(self) -> int:
        """
        Remove expired records (if TTL is supported).
        
        Returns:
            Number of records cleaned up
            
        Raises:
            AdapterError: If cleanup fails
        """
        ...
    
    @abstractmethod
    async def get_stats(self) -> dict[str, Any]:
        """
        Get tier statistics and health information.
        
        Returns:
            Dictionary with tier metrics
        """
        ...


@runtime_checkable
class VectorStore(TierStore, Protocol):
    """
    Vector similarity search protocol for Long-Term Memory.
    
    Extends TierStore with vector-specific operations for
    semantic similarity search and embedding management.
    """
    
    @abstractmethod
    async def similarity_search(
        self, 
        query_vector: list[float],
        limit: int = 10,
        similarity_threshold: float = 0.0,
        filters: dict[str, Any] | None = None
    ) -> list[tuple[RecordEnvelope, float]]:
        """
        Search for similar records using vector similarity.
        
        Args:
            query_vector: Query embedding vector
            limit: Maximum number of results
            similarity_threshold: Minimum similarity score
            filters: Optional metadata filters
            
        Returns:
            List of (record, similarity_score) tuples ordered by similarity
            
        Raises:
            ValidationError: If query vector is invalid
            VectorStoreError: If search fails
        """
        ...
    
    @abstractmethod
    async def update_embedding(
        self, 
        record_id: str, 
        new_embedding: list[float]
    ) -> bool:
        """
        Update embedding vector for a record.
        
        Args:
            record_id: Record identifier
            new_embedding: New embedding vector
            
        Returns:
            True if updated, False if not found
            
        Raises:
            ValidationError: If embedding is invalid
            VectorStoreError: If update fails
        """
        ...
    
    @abstractmethod
    async def rebuild_index(self) -> dict[str, Any]:
        """
        Rebuild vector index for optimal performance.
        
        Returns:
            Rebuild statistics and performance metrics
            
        Raises:
            VectorStoreError: If rebuild fails
        """
        ...


@runtime_checkable
class GraphStore(TierStore, Protocol):
    """
    Graph storage protocol for Semantic Memory.
    
    Extends TierStore with graph-specific operations for
    entity relationships and semantic networks.
    """
    
    @abstractmethod
    async def add_entity(
        self, 
        entity_id: str, 
        properties: dict[str, Any]
    ) -> bool:
        """
        Add or update an entity node.
        
        Args:
            entity_id: Unique entity identifier
            properties: Entity attributes
            
        Returns:
            True if entity was added/updated
            
        Raises:
            ValidationError: If entity data is invalid
            GraphStoreError: If operation fails
        """
        ...
    
    @abstractmethod
    async def add_relationship(
        self, 
        from_entity: str, 
        to_entity: str,
        relationship_type: str,
        properties: dict[str, Any] | None = None
    ) -> bool:
        """
        Add relationship between entities.
        
        Args:
            from_entity: Source entity ID
            to_entity: Target entity ID
            relationship_type: Type of relationship
            properties: Optional relationship attributes
            
        Returns:
            True if relationship was added
            
        Raises:
            ValidationError: If relationship data is invalid
            GraphStoreError: If operation fails
        """
        ...
    
    @abstractmethod
    async def find_connected(
        self, 
        entity_id: str,
        relationship_types: list[str] | None = None,
        max_depth: int = 2,
        limit: int = 50
    ) -> list[dict[str, Any]]:
        """
        Find entities connected to given entity.
        
        Args:
            entity_id: Starting entity ID
            relationship_types: Filter by relationship types
            max_depth: Maximum traversal depth
            limit: Maximum results to return
            
        Returns:
            List of connected entity information
            
        Raises:
            GraphStoreError: If traversal fails
        """
        ...
    
    @abstractmethod
    async def shortest_path(
        self, 
        from_entity: str, 
        to_entity: str,
        max_depth: int = 6
    ) -> list[dict[str, Any]] | None:
        """
        Find shortest path between two entities.
        
        Args:
            from_entity: Starting entity ID
            to_entity: Target entity ID
            max_depth: Maximum path length
            
        Returns:
            Path as list of nodes and edges, or None if no path
            
        Raises:
            GraphStoreError: If pathfinding fails
        """
        ...
    
    @abstractmethod
    async def entity_exists(self, entity_id: str) -> bool:
        """
        Check if entity exists in graph.
        
        Args:
            entity_id: Entity identifier to check
            
        Returns:
            True if entity exists
        """
        ...


@runtime_checkable
class LexicalIndex(Protocol):
    """
    Full-text search protocol for lexical queries.
    
    Provides traditional text search capabilities for
    exact matches, phrase search, and fuzzy matching.
    """
    
    @property
    @abstractmethod
    def index_name(self) -> str:
        """Name of the lexical index."""
        ...
    
    @abstractmethod
    async def index_record(self, record: RecordEnvelope) -> bool:
        """
        Add record to full-text index.
        
        Args:
            record: Memory record to index
            
        Returns:
            True if record was indexed
            
        Raises:
            ValidationError: If record cannot be indexed
            LexicalIndexError: If indexing fails
        """
        ...
    
    @abstractmethod
    async def search_text(
        self, 
        query_text: str,
        limit: int = 20,
        fuzzy: bool = False,
        highlight: bool = False
    ) -> list[tuple[RecordEnvelope, float]]:
        """
        Search records by text content.
        
        Args:
            query_text: Search query string
            limit: Maximum results to return
            fuzzy: Enable fuzzy matching
            highlight: Include highlighted excerpts
            
        Returns:
            List of (record, score) tuples ordered by relevance
            
        Raises:
            ValidationError: If query is malformed
            LexicalIndexError: If search fails
        """
        ...
    
    @abstractmethod
    async def phrase_search(
        self, 
        phrase: str,
        limit: int = 20,
        slop: int = 0
    ) -> list[tuple[RecordEnvelope, float]]:
        """
        Search for exact phrases with optional word distance.
        
        Args:
            phrase: Exact phrase to search for
            limit: Maximum results
            slop: Allowed word distance in phrase
            
        Returns:
            List of matching records with scores
            
        Raises:
            LexicalIndexError: If search fails
        """
        ...
    
    @abstractmethod
    async def remove_record(self, record_id: str) -> bool:
        """
        Remove record from index.
        
        Args:
            record_id: Record identifier
            
        Returns:
            True if record was removed
            
        Raises:
            LexicalIndexError: If removal fails
        """
        ...
    
    @abstractmethod
    async def optimize_index(self) -> dict[str, Any]:
        """
        Optimize index for better performance.
        
        Returns:
            Optimization statistics
            
        Raises:
            LexicalIndexError: If optimization fails
        """
        ...


@runtime_checkable
class ContextAssembler(Protocol):
    """
    Context assembly and prioritization protocol.
    
    Combines memory from multiple tiers into coherent context
    within token budget constraints.
    """
    
    @abstractmethod
    async def assemble_context(
        self, 
        query: MemoryQuery,
        tier_results: dict[str, list[RecordEnvelope]]
    ) -> SmrtiContext:
        """
        Assemble unified context from tier results.
        
        Args:
            query: Original memory query
            tier_results: Results from each memory tier
            
        Returns:
            Assembled context with prioritized sections
            
        Raises:
            TokenBudgetExceededError: If content exceeds budget
            ContextAssemblyError: If assembly fails
        """
        ...
    
    @abstractmethod
    async def prioritize_items(
        self, 
        items: list[RecordEnvelope],
        query: MemoryQuery
    ) -> list[RecordEnvelope]:
        """
        Sort items by relevance to query.
        
        Args:
            items: Memory items to prioritize
            query: Reference query for relevance
            
        Returns:
            Items sorted by priority/relevance
        """
        ...
    
    @abstractmethod
    async def estimate_tokens(self, items: list[RecordEnvelope]) -> int:
        """
        Estimate token count for memory items.
        
        Args:
            items: Memory items to estimate
            
        Returns:
            Estimated total token count
        """
        ...


@runtime_checkable
class LifecycleManager(Protocol):
    """
    Memory lifecycle management protocol.
    
    Handles consolidation, summarization, and cleanup
    operations across memory tiers.
    """
    
    @abstractmethod
    async def consolidate_session(self, session_id: str) -> dict[str, Any]:
        """
        Consolidate working memory items from a session.
        
        Args:
            session_id: Session to consolidate
            
        Returns:
            Consolidation statistics and results
            
        Raises:
            ConsolidationError: If consolidation fails
        """
        ...
    
    @abstractmethod
    async def summarize_conversation(
        self, 
        turns: list[ConversationTurn]
    ) -> str:
        """
        Generate summary of conversation turns.
        
        Args:
            turns: Conversation turns to summarize
            
        Returns:
            Natural language summary
            
        Raises:
            SummarizationError: If summarization fails
        """
        ...
    
    @abstractmethod
    async def deduplicate_memories(
        self, 
        tier_name: str,
        similarity_threshold: float = 0.95
    ) -> int:
        """
        Remove duplicate memories from a tier.
        
        Args:
            tier_name: Memory tier to deduplicate
            similarity_threshold: Similarity threshold for duplicates
            
        Returns:
            Number of duplicates removed
            
        Raises:
            DeduplicationError: If deduplication fails
        """
        ...
    
    @abstractmethod
    async def archive_old_memories(
        self, 
        cutoff_date: datetime,
        target_tier: str | None = None
    ) -> int:
        """
        Archive memories older than cutoff date.
        
        Args:
            cutoff_date: Age threshold for archival
            target_tier: Destination tier (or delete if None)
            
        Returns:
            Number of memories archived
            
        Raises:
            LifecycleError: If archival fails
        """
        ...


@runtime_checkable
class SmrtiProvider(Protocol):
    """
    Main Smrti system protocol interface.
    
    This is the primary interface that client applications
    use to interact with the Smrti memory system.
    """
    
    @abstractmethod
    async def store_memory(
        self, 
        content: str | ConversationTurn | EventRecord | FactRecord,
        tenant: str,
        namespace: str,
        tags: list[str] | None = None,
        priority: int = 0
    ) -> str:
        """
        Store new memory item.
        
        Args:
            content: Memory content to store
            tenant: Tenant identifier
            namespace: Namespace within tenant
            tags: Optional semantic tags
            priority: Storage priority (higher = more important)
            
        Returns:
            Record ID of stored memory
            
        Raises:
            ValidationError: If content is invalid
            NamespaceViolationError: If tenant/namespace unauthorized
            SmrtiError: For other storage failures
        """
        ...
    
    @abstractmethod
    async def retrieve_context(
        self, 
        query: str | MemoryQuery,
        tenant: str,
        namespace: str
    ) -> SmrtiContext:
        """
        Retrieve contextual memories for query.
        
        Args:
            query: Query string or structured query
            tenant: Tenant identifier
            namespace: Namespace within tenant
            
        Returns:
            Assembled context from all relevant memory tiers
            
        Raises:
            ValidationError: If query is invalid
            NamespaceViolationError: If unauthorized
            PartialDegradationError: If some tiers fail but context available
            SmrtiError: For other retrieval failures
        """
        ...
    
    @abstractmethod
    async def stream_context(
        self, 
        query: str | MemoryQuery,
        tenant: str,
        namespace: str
    ) -> AsyncIterator[ContextSection]:
        """
        Stream context sections as they become available.
        
        Args:
            query: Query string or structured query
            tenant: Tenant identifier  
            namespace: Namespace within tenant
            
        Yields:
            Context sections from different memory tiers
            
        Raises:
            ValidationError: If query is invalid
            NamespaceViolationError: If unauthorized
            SmrtiError: For streaming failures
        """
        ...
    
    @abstractmethod
    async def delete_memory(
        self, 
        record_id: str,
        tenant: str,
        namespace: str
    ) -> bool:
        """
        Delete specific memory record.
        
        Args:
            record_id: Record to delete
            tenant: Tenant identifier
            namespace: Namespace within tenant
            
        Returns:
            True if record was deleted
            
        Raises:
            NamespaceViolationError: If unauthorized
            SmrtiError: For deletion failures
        """
        ...
    
    @abstractmethod
    async def get_memory_stats(
        self, 
        tenant: str,
        namespace: str | None = None
    ) -> dict[str, Any]:
        """
        Get memory statistics for tenant/namespace.
        
        Args:
            tenant: Tenant identifier
            namespace: Optional namespace filter
            
        Returns:
            Statistics dictionary with tier breakdowns
            
        Raises:
            NamespaceViolationError: If unauthorized
        """
        ...
    
    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """
        Check system health across all components.
        
        Returns:
            Health status for all adapters and tiers
        """
        ...


@runtime_checkable 
class AdapterRegistry(Protocol):
    """
    Adapter registration and discovery protocol.
    
    Manages available adapters and capability negotiation
    for pluggable storage backends.
    """
    
    @abstractmethod
    def register_embedding_provider(
        self, 
        name: str, 
        provider: EmbeddingProvider
    ) -> None:
        """Register an embedding provider."""
        ...
    
    @abstractmethod
    def register_tier_store(
        self, 
        tier_name: str, 
        store: TierStore
    ) -> None:
        """Register a tier storage adapter."""
        ...
    
    @abstractmethod
    def register_vector_store(
        self, 
        name: str, 
        store: VectorStore
    ) -> None:
        """Register a vector storage adapter."""
        ...
    
    @abstractmethod
    def register_graph_store(
        self, 
        name: str, 
        store: GraphStore
    ) -> None:
        """Register a graph storage adapter."""
        ...
    
    @abstractmethod
    def register_lexical_index(
        self, 
        name: str, 
        index: LexicalIndex
    ) -> None:
        """Register a lexical index adapter."""
        ...
    
    @abstractmethod
    def get_embedding_provider(self, name: str) -> EmbeddingProvider:
        """Get registered embedding provider."""
        ...
    
    @abstractmethod
    def get_tier_store(self, tier_name: str) -> TierStore:
        """Get registered tier store."""
        ...
    
    @abstractmethod
    def get_vector_store(self, name: str) -> VectorStore:
        """Get registered vector store."""
        ...
    
    @abstractmethod
    def get_graph_store(self, name: str) -> GraphStore:
        """Get registered graph store."""
        ...
    
    @abstractmethod
    def get_lexical_index(self, name: str) -> LexicalIndex:
        """Get registered lexical index."""
        ...
    
    @abstractmethod
    def list_capabilities(self) -> dict[str, list[str]]:
        """
        List available adapters by capability type.
        
        Returns:
            Dictionary mapping capability types to adapter names
        """
        ...
    
    @abstractmethod
    def check_requirements(
        self, 
        requirements: dict[str, Any]
    ) -> dict[str, bool]:
        """
        Check if system meets capability requirements.
        
        Args:
            requirements: Required capabilities and versions
            
        Returns:
            Dictionary indicating which requirements are met
        """
        ...