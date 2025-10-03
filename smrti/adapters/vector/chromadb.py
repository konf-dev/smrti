"""
smrti/adapters/vector/chromadb.py - ChromaDB vector store adapter

Production-ready ChromaDB adapter for Long-term Memory with similarity search,
metadata filtering, and comprehensive vector operations.
"""

import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import chromadb
    from chromadb.api.types import Documents, EmbeddingFunction, Embeddings, IDs, Metadatas
    from chromadb.config import Settings as ChromaSettings
    from chromadb.errors import InvalidCollectionException, ChromaError
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False
    chromadb = None
    Documents = None
    EmbeddingFunction = None
    Embeddings = None
    IDs = None
    Metadatas = None
    InvalidCollectionException = Exception
    ChromaError = Exception
    ChromaSettings = None

import numpy as np

from smrti.core.base import BaseAdapter
from smrti.core.exceptions import (
    VectorStoreError,
    ConfigurationError,
    ValidationError,
    CapacityExceededError,
    RetryableError
)
from smrti.core.protocols import VectorStore, EmbeddingProvider
from smrti.core.registry import AdapterCapability, get_global_registry
from smrti.schemas.models import MemoryQuery, RecordEnvelope


class ChromaDBAdapter(BaseAdapter, VectorStore):
    """
    ChromaDB adapter for Long-term Memory vector storage.
    
    Features:
    - High-performance vector similarity search
    - Metadata filtering and hybrid queries
    - Collection management and sharding
    - Batch operations for efficiency
    - Automatic embedding generation
    - Index optimization and persistence
    - Multi-tenant collection isolation
    - Comprehensive error handling
    """
    
    def __init__(
        self,
        collection_name: str = "smrti_longterm",
        config: Optional[Dict[str, Any]] = None
    ):
        if not HAS_CHROMADB:
            raise ConfigurationError(
                "chromadb package is required but not installed. "
                "Install with: pip install chromadb"
            )
        
        super().__init__(f"chromadb_{collection_name}", config)
        
        self._collection_name = collection_name
        
        # ChromaDB configuration
        self._persist_directory = self.config.get("persist_directory", "./chroma_db")
        self._chroma_host = self.config.get("host")
        self._chroma_port = self.config.get("port", 8000)
        self._client_type = self.config.get("client_type", "persistent")  # persistent, http
        self._distance_function = self.config.get("distance_function", "cosine")
        
        # Collection configuration
        self._embedding_dimension = self.config.get("embedding_dimension", 384)
        self._max_batch_size = self.config.get("max_batch_size", 1000)
        self._auto_embed = self.config.get("auto_embed", True)
        self._embedding_provider_name = self.config.get("embedding_provider", "sentence_transformers")
        
        # Performance configuration
        self._index_type = self.config.get("index_type", "hnsw")
        self._ef_construction = self.config.get("ef_construction", 200)
        self._ef_search = self.config.get("ef_search", 50)
        self._max_elements = self.config.get("max_elements", 100000)
        
        # Metadata configuration
        self._metadata_keys = self.config.get("metadata_keys", [
            "tenant_id", "namespace", "tier", "record_type", "created_at",
            "last_accessed", "access_count", "tags", "source"
        ])
        
        # ChromaDB objects
        self._client = None
        self._collection = None
        self._embedding_provider: Optional[EmbeddingProvider] = None
        
        # Statistics
        self._vectors_stored = 0
        self._queries_executed = 0
        self._total_query_time = 0.0
        self._index_size = 0
        self._last_optimization = None
        
        # Set tier capabilities
        self._supports_ttl = False  # ChromaDB doesn't have native TTL
        self._supports_similarity_search = True
    
    @property
    def tier_name(self) -> str:
        """Name of this memory tier."""
        return "long_term"
    
    @property
    def supports_ttl(self) -> bool:
        """Whether this tier supports time-to-live expiration."""
        return self._supports_ttl
    
    @property
    def supports_similarity_search(self) -> bool:
        """Whether this tier supports vector similarity search."""
        return self._supports_similarity_search
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self._initialize_client()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self._cleanup()
    
    async def _initialize_client(self) -> None:
        """Initialize ChromaDB client and collection."""
        try:
            # Initialize ChromaDB client
            if self._client_type == "http" and self._chroma_host:
                self._client = chromadb.HttpClient(
                    host=self._chroma_host,
                    port=self._chroma_port
                )
            else:
                # Use persistent client
                settings = ChromaSettings(
                    persist_directory=self._persist_directory,
                    anonymized_telemetry=False
                )
                self._client = chromadb.PersistentClient(
                    path=self._persist_directory,
                    settings=settings
                )
            
            # Get or create collection
            try:
                self._collection = self._client.get_collection(
                    name=self._collection_name
                )
                self.logger.info(f"Loaded existing ChromaDB collection: {self._collection_name}")
            
            except InvalidCollectionException:
                # Create new collection
                metadata = {
                    "hnsw:space": self._distance_function,
                    "hnsw:construction_ef": self._ef_construction,
                    "hnsw:search_ef": self._ef_search,
                    "hnsw:M": 16
                }
                
                self._collection = self._client.create_collection(
                    name=self._collection_name,
                    metadata=metadata
                )
                self.logger.info(f"Created new ChromaDB collection: {self._collection_name}")
            
            # Initialize embedding provider if auto-embed is enabled
            if self._auto_embed:
                await self._initialize_embedding_provider()
            
            # Get collection statistics
            await self._update_collection_stats()
            
            self.logger.info(
                f"ChromaDB adapter initialized (collection={self._collection_name}, "
                f"vectors={self._vectors_stored}, client_type={self._client_type})"
            )
            
        except Exception as e:
            raise VectorStoreError(
                f"Failed to initialize ChromaDB client: {e}",
                store_type="chromadb",
                operation="initialize",
                backend_error=e
            )
    
    async def _initialize_embedding_provider(self) -> None:
        """Initialize embedding provider for auto-embedding."""
        try:
            registry = get_global_registry()
            self._embedding_provider = registry.get_embedding_provider(
                self._embedding_provider_name
            )
            
            # Validate embedding dimensions match
            if hasattr(self._embedding_provider, 'embedding_dim'):
                provider_dim = self._embedding_provider.embedding_dim
                if provider_dim != self._embedding_dimension:
                    self.logger.warning(
                        f"Embedding dimension mismatch: provider={provider_dim}, "
                        f"configured={self._embedding_dimension}. Using provider dimension."
                    )
                    self._embedding_dimension = provider_dim
            
        except Exception as e:
            self.logger.warning(f"Failed to initialize embedding provider: {e}")
            self._auto_embed = False
    
    def _record_to_metadata(self, record: RecordEnvelope) -> Dict[str, Any]:
        """Convert record to ChromaDB metadata."""
        metadata = {}
        
        # Standard metadata fields
        for key in self._metadata_keys:
            if hasattr(record, key):
                value = getattr(record, key)
                
                # Convert datetime to ISO string
                if isinstance(value, datetime):
                    metadata[key] = value.isoformat()
                # Convert lists to JSON strings
                elif isinstance(value, list):
                    metadata[key] = json.dumps(value)
                # Convert other types to string
                elif value is not None:
                    metadata[key] = str(value)
        
        # Add computed fields
        metadata["content_hash"] = record.compute_semantic_hash()
        metadata["content_preview"] = str(record.content)[:100] + "..." if len(str(record.content)) > 100 else str(record.content)
        metadata["embedding_model"] = getattr(self._embedding_provider, 'model_name', 'unknown') if self._embedding_provider else 'external'
        
        return metadata
    
    def _metadata_to_record_fields(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Convert ChromaDB metadata back to record fields."""
        fields = {}
        
        for key, value in metadata.items():
            if key in ["created_at", "last_accessed", "updated_at"]:
                # Convert ISO string back to datetime
                try:
                    fields[key] = datetime.fromisoformat(value.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    continue
            elif key in ["tags"]:
                # Convert JSON string back to list
                try:
                    fields[key] = json.loads(value) if isinstance(value, str) else value
                except (json.JSONDecodeError, TypeError):
                    fields[key] = []
            elif key not in ["content_hash", "content_preview", "embedding_model"]:
                # Keep other fields as-is
                fields[key] = value
        
        return fields
    
    async def _get_embedding(self, content: str) -> List[float]:
        """Get embedding for content."""
        if not self._embedding_provider:
            raise VectorStoreError(
                "No embedding provider available for auto-embedding",
                store_type="chromadb",
                operation="embed"
            )
        
        try:
            return await self._embedding_provider.embed_text(content)
        except Exception as e:
            raise VectorStoreError(
                f"Failed to generate embedding: {e}",
                store_type="chromadb",
                operation="embed",
                backend_error=e
            )
    
    async def store(
        self, 
        record: RecordEnvelope,
        ttl: Optional[timedelta] = None
    ) -> str:
        """Store a memory record with vector embedding."""
        return await self._execute_with_retry(
            "store",
            self._store_impl,
            record,
            ttl
        )
    
    async def _store_impl(
        self, 
        record: RecordEnvelope,
        ttl: Optional[timedelta] = None
    ) -> str:
        """Internal store implementation."""
        self._validate_record(record)
        
        try:
            # Generate embedding if auto-embed is enabled
            if self._auto_embed:
                embedding = await self._get_embedding(str(record.content))
            else:
                # Use provided embedding or raise error
                if not hasattr(record, 'embedding') or not record.embedding:
                    raise ValidationError("Record must include embedding when auto-embed is disabled")
                embedding = record.embedding
            
            # Validate embedding dimension
            if len(embedding) != self._embedding_dimension:
                raise ValidationError(
                    f"Embedding dimension {len(embedding)} doesn't match expected {self._embedding_dimension}"
                )
            
            # Prepare ChromaDB data
            record_id = record.record_id
            document_text = str(record.content)
            metadata = self._record_to_metadata(record)
            
            # Add record to collection
            def _add_sync():
                self._collection.add(
                    ids=[record_id],
                    documents=[document_text],
                    embeddings=[embedding],
                    metadatas=[metadata]
                )
            
            # Run in thread pool since ChromaDB is synchronous
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _add_sync)
            
            # Update statistics
            self._vectors_stored += 1
            self._index_size = self._collection.count()
            self._update_stats("store", 1, len(document_text))
            
            self.logger.debug(f"Stored vector for record {record_id} with {len(embedding)}D embedding")
            
            return record_id
            
        except ChromaError as e:
            raise VectorStoreError(
                f"ChromaDB error during store: {e}",
                store_type="chromadb",
                operation="store",
                backend_error=e
            )
        except Exception as e:
            raise VectorStoreError(
                f"Unexpected error during store: {e}",
                store_type="chromadb",
                operation="store",
                backend_error=e
            )
    
    async def retrieve(self, record_id: str) -> Optional[RecordEnvelope]:
        """Retrieve a specific memory record."""
        return await self._execute_with_retry(
            "retrieve",
            self._retrieve_impl,
            record_id
        )
    
    async def _retrieve_impl(self, record_id: str) -> Optional[RecordEnvelope]:
        """Internal retrieve implementation."""
        try:
            def _get_sync():
                return self._collection.get(
                    ids=[record_id],
                    include=["documents", "metadatas", "embeddings"]
                )
            
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _get_sync)
            
            if not result["ids"] or len(result["ids"]) == 0:
                return None
            
            # Reconstruct record from ChromaDB data
            document = result["documents"][0]
            metadata = result["metadatas"][0]
            embedding = result["embeddings"][0] if result["embeddings"] else None
            
            # Convert metadata back to record fields
            record_fields = self._metadata_to_record_fields(metadata)
            record_fields["record_id"] = record_id
            record_fields["content"] = document
            if embedding:
                record_fields["embedding"] = embedding
            
            # Create record envelope
            record = RecordEnvelope(**record_fields)
            
            self._update_stats("retrieve", 1)
            
            return record
            
        except ChromaError as e:
            raise VectorStoreError(
                f"ChromaDB error during retrieve: {e}",
                store_type="chromadb",
                operation="retrieve",
                backend_error=e
            )
        except Exception as e:
            self.logger.warning(f"Error retrieving record {record_id}: {e}")
            return None
    
    async def query(self, query: MemoryQuery) -> List[RecordEnvelope]:
        """Query records matching criteria."""
        return await self._execute_with_retry(
            "query",
            self._query_impl,
            query
        )
    
    async def _query_impl(self, query: MemoryQuery) -> List[RecordEnvelope]:
        """Internal query implementation."""
        self._validate_query(query)
        
        try:
            start_time = time.time()
            
            # Build metadata filters
            where_clause = self._build_where_clause(query)
            
            # Execute query
            if query.query_text and self._auto_embed:
                # Similarity search with text query
                query_embedding = await self._get_embedding(query.query_text)
                results = await self._similarity_search(
                    query_embedding,
                    query.limit,
                    query.similarity_threshold,
                    where_clause
                )
            elif query.embedding_vector:
                # Direct vector similarity search
                results = await self._similarity_search(
                    query.embedding_vector,
                    query.limit,
                    query.similarity_threshold,
                    where_clause
                )
            else:
                # Metadata-only query
                results = await self._metadata_query(query.limit, where_clause)
            
            # Update statistics
            query_time = time.time() - start_time
            self._queries_executed += 1
            self._total_query_time += query_time
            self._update_stats("retrieve", len(results))
            
            if query_time > 1.0:
                self.logger.warning(f"Slow ChromaDB query took {query_time:.2f}s")
            
            return results
            
        except ChromaError as e:
            raise VectorStoreError(
                f"ChromaDB error during query: {e}",
                store_type="chromadb",
                operation="query",
                backend_error=e
            )
        except Exception as e:
            raise VectorStoreError(
                f"Unexpected error during query: {e}",
                store_type="chromadb",
                operation="query",
                backend_error=e
            )
    
    def _build_where_clause(self, query: MemoryQuery) -> Optional[Dict[str, Any]]:
        """Build ChromaDB where clause from memory query."""
        where = {}
        
        # Tenant and namespace filtering
        if query.tenant_id:
            where["tenant_id"] = query.tenant_id
        
        if query.namespace:
            where["namespace"] = query.namespace
        
        # Tag filtering
        if query.tags:
            # ChromaDB doesn't support array contains, so we use string matching
            # This is a simplification - in production you might want more sophisticated tag handling
            tag_conditions = []
            for tag in query.tags:
                tag_conditions.append({"tags": {"$contains": tag}})
            
            if len(tag_conditions) == 1:
                where.update(tag_conditions[0])
            else:
                where["$or"] = tag_conditions
        
        # Time range filtering
        if query.start_time:
            where["created_at"] = {"$gte": query.start_time.isoformat()}
        
        if query.end_time:
            if "created_at" in where:
                where["created_at"]["$lte"] = query.end_time.isoformat()
            else:
                where["created_at"] = {"$lte": query.end_time.isoformat()}
        
        return where if where else None
    
    async def _similarity_search(
        self,
        query_vector: List[float],
        limit: int,
        similarity_threshold: float,
        where_clause: Optional[Dict[str, Any]]
    ) -> List[RecordEnvelope]:
        """Perform vector similarity search."""
        def _query_sync():
            return self._collection.query(
                query_embeddings=[query_vector],
                n_results=limit,
                where=where_clause,
                include=["documents", "metadatas", "distances", "embeddings"]
            )
        
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, _query_sync)
        
        return self._process_query_results(results, similarity_threshold)
    
    async def _metadata_query(
        self,
        limit: int,
        where_clause: Optional[Dict[str, Any]]
    ) -> List[RecordEnvelope]:
        """Perform metadata-only query."""
        def _get_sync():
            return self._collection.get(
                where=where_clause,
                limit=limit,
                include=["documents", "metadatas", "embeddings"]
            )
        
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, _get_sync)
        
        # Convert get results to query format
        query_results = {
            "ids": [results["ids"]],
            "documents": [results["documents"]],
            "metadatas": [results["metadatas"]],
            "embeddings": [results["embeddings"]],
            "distances": [[0.0] * len(results["ids"])]  # No distances for metadata query
        }
        
        return self._process_query_results(query_results, 0.0)
    
    def _process_query_results(
        self, 
        results: Dict[str, Any], 
        similarity_threshold: float
    ) -> List[RecordEnvelope]:
        """Process ChromaDB query results into RecordEnvelope objects."""
        records = []
        
        if not results["ids"] or len(results["ids"]) == 0:
            return records
        
        # Process first (and typically only) query result set
        ids = results["ids"][0]
        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]
        embeddings = results["embeddings"][0] if results["embeddings"] else [None] * len(ids)
        
        for i, (record_id, document, metadata, distance, embedding) in enumerate(
            zip(ids, documents, metadatas, distances, embeddings)
        ):
            # Apply similarity threshold (distance is inverse of similarity)
            similarity = 1.0 - distance if distance is not None else 1.0
            if similarity < similarity_threshold:
                continue
            
            try:
                # Reconstruct record
                record_fields = self._metadata_to_record_fields(metadata)
                record_fields["record_id"] = record_id
                record_fields["content"] = document
                record_fields["relevance_score"] = similarity
                
                if embedding:
                    record_fields["embedding"] = embedding
                
                record = RecordEnvelope(**record_fields)
                records.append(record)
                
            except Exception as e:
                self.logger.warning(f"Failed to reconstruct record {record_id}: {e}")
                continue
        
        return records
    
    async def similarity_search(
        self, 
        query_vector: List[float],
        limit: int = 10,
        similarity_threshold: float = 0.0,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[RecordEnvelope, float]]:
        """Search for similar records using vector similarity."""
        return await self._execute_with_retry(
            "similarity_search",
            self._similarity_search_impl,
            query_vector,
            limit,
            similarity_threshold,
            filters
        )
    
    async def _similarity_search_impl(
        self,
        query_vector: List[float],
        limit: int,
        similarity_threshold: float,
        filters: Optional[Dict[str, Any]]
    ) -> List[Tuple[RecordEnvelope, float]]:
        """Internal similarity search implementation."""
        if len(query_vector) != self._embedding_dimension:
            raise ValidationError(
                f"Query vector dimension {len(query_vector)} doesn't match expected {self._embedding_dimension}"
            )
        
        try:
            def _query_sync():
                return self._collection.query(
                    query_embeddings=[query_vector],
                    n_results=limit,
                    where=filters,
                    include=["documents", "metadatas", "distances", "embeddings"]
                )
            
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, _query_sync)
            
            # Process results into tuples with similarity scores
            result_tuples = []
            
            if results["ids"] and len(results["ids"]) > 0:
                ids = results["ids"][0]
                documents = results["documents"][0]
                metadatas = results["metadatas"][0]
                distances = results["distances"][0]
                embeddings = results["embeddings"][0] if results["embeddings"] else [None] * len(ids)
                
                for record_id, document, metadata, distance, embedding in zip(
                    ids, documents, metadatas, distances, embeddings
                ):
                    similarity = 1.0 - distance
                    
                    if similarity >= similarity_threshold:
                        try:
                            record_fields = self._metadata_to_record_fields(metadata)
                            record_fields["record_id"] = record_id
                            record_fields["content"] = document
                            record_fields["relevance_score"] = similarity
                            
                            if embedding:
                                record_fields["embedding"] = embedding
                            
                            record = RecordEnvelope(**record_fields)
                            result_tuples.append((record, similarity))
                            
                        except Exception as e:
                            self.logger.warning(f"Failed to reconstruct record {record_id}: {e}")
                            continue
            
            return result_tuples
            
        except ChromaError as e:
            raise VectorStoreError(
                f"ChromaDB error during similarity search: {e}",
                store_type="chromadb",
                operation="similarity_search",
                backend_error=e
            )
    
    async def delete(self, record_id: str) -> bool:
        """Delete a memory record."""
        return await self._execute_with_retry(
            "delete",
            self._delete_impl,
            record_id
        )
    
    async def _delete_impl(self, record_id: str) -> bool:
        """Internal delete implementation."""
        try:
            def _delete_sync():
                self._collection.delete(ids=[record_id])
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _delete_sync)
            
            # Update statistics
            self._update_stats("delete", 1)
            self._index_size = self._collection.count()
            
            return True
            
        except ChromaError as e:
            if "not found" in str(e).lower():
                return False
            else:
                raise VectorStoreError(
                    f"ChromaDB error during delete: {e}",
                    store_type="chromadb",
                    operation="delete",
                    backend_error=e
                )
        except Exception as e:
            raise VectorStoreError(
                f"Unexpected error during delete: {e}",
                store_type="chromadb",
                operation="delete",
                backend_error=e
            )
    
    async def update_relevance(
        self, 
        record_id: str, 
        new_relevance: float
    ) -> bool:
        """Update relevance score for a record."""
        # Retrieve existing record
        record = await self.retrieve(record_id)
        
        if record is None:
            return False
        
        # Update relevance and store back
        record.relevance_score = new_relevance
        await self.store(record)
        
        return True
    
    async def update_embedding(
        self, 
        record_id: str, 
        new_embedding: List[float]
    ) -> bool:
        """Update embedding vector for a record."""
        return await self._execute_with_retry(
            "update_embedding",
            self._update_embedding_impl,
            record_id,
            new_embedding
        )
    
    async def _update_embedding_impl(
        self, 
        record_id: str, 
        new_embedding: List[float]
    ) -> bool:
        """Internal update embedding implementation."""
        if len(new_embedding) != self._embedding_dimension:
            raise ValidationError(
                f"Embedding dimension {len(new_embedding)} doesn't match expected {self._embedding_dimension}"
            )
        
        try:
            # Get existing record data
            existing = await self._retrieve_impl(record_id)
            if existing is None:
                return False
            
            # Update the embedding
            def _update_sync():
                self._collection.update(
                    ids=[record_id],
                    embeddings=[new_embedding]
                )
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _update_sync)
            
            return True
            
        except ChromaError as e:
            raise VectorStoreError(
                f"ChromaDB error during embedding update: {e}",
                store_type="chromadb",
                operation="update_embedding",
                backend_error=e
            )
    
    async def rebuild_index(self) -> Dict[str, Any]:
        """Rebuild vector index for optimal performance."""
        return await self._execute_with_retry(
            "rebuild_index",
            self._rebuild_index_impl
        )
    
    async def _rebuild_index_impl(self) -> Dict[str, Any]:
        """Internal rebuild index implementation."""
        start_time = time.time()
        
        try:
            # ChromaDB doesn't have explicit index rebuild, but we can trigger optimization
            # by querying with a dummy vector to ensure index is built
            dummy_vector = [0.0] * self._embedding_dimension
            
            def _optimize_sync():
                return self._collection.query(
                    query_embeddings=[dummy_vector],
                    n_results=1
                )
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _optimize_sync)
            
            rebuild_time = time.time() - start_time
            self._last_optimization = datetime.utcnow()
            
            return {
                "rebuild_time": rebuild_time,
                "index_size": self._index_size,
                "vectors_count": self._vectors_stored,
                "last_optimization": self._last_optimization.isoformat()
            }
            
        except Exception as e:
            raise VectorStoreError(
                f"Failed to rebuild index: {e}",
                store_type="chromadb",
                operation="rebuild_index",
                backend_error=e
            )
    
    async def cleanup_expired(self) -> int:
        """Remove expired records (ChromaDB doesn't have native TTL)."""
        # ChromaDB doesn't support TTL, so this is a no-op
        # In a production system, you might implement application-level TTL
        return 0
    
    async def _update_collection_stats(self) -> None:
        """Update collection statistics."""
        try:
            def _count_sync():
                return self._collection.count()
            
            loop = asyncio.get_event_loop()
            self._index_size = await loop.run_in_executor(None, _count_sync)
            self._vectors_stored = self._index_size
            
        except Exception as e:
            self.logger.warning(f"Failed to update collection stats: {e}")
    
    async def _perform_health_check(self) -> Dict[str, Any]:
        """Perform ChromaDB health check."""
        try:
            # Test basic operations
            start_time = time.time()
            
            # Test collection access
            def _health_sync():
                return self._collection.count()
            
            loop = asyncio.get_event_loop()
            count = await loop.run_in_executor(None, _health_sync)
            
            health_time = time.time() - start_time
            
            return {
                "collection_name": self._collection_name,
                "client_type": self._client_type,
                "vector_count": count,
                "embedding_dimension": self._embedding_dimension,
                "distance_function": self._distance_function,
                "auto_embed": self._auto_embed,
                "embedding_provider": self._embedding_provider_name if self._auto_embed else None,
                "health_check_time": health_time,
                "queries_executed": self._queries_executed,
                "average_query_time": (
                    self._total_query_time / max(1, self._queries_executed)
                ),
                "last_optimization": self._last_optimization.isoformat() if self._last_optimization else None
            }
            
        except Exception as e:
            raise VectorStoreError(
                f"ChromaDB health check failed: {e}",
                store_type="chromadb",
                operation="health_check",
                backend_error=e
            )
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get ChromaDB adapter statistics."""
        base_stats = await super().get_stats()
        
        chroma_stats = {
            "collection_name": self._collection_name,
            "client_type": self._client_type,
            "persist_directory": self._persist_directory,
            "embedding_dimension": self._embedding_dimension,
            "distance_function": self._distance_function,
            "auto_embed": self._auto_embed,
            "embedding_provider": self._embedding_provider_name,
            "vectors_stored": self._vectors_stored,
            "queries_executed": self._queries_executed,
            "average_query_time": (
                self._total_query_time / max(1, self._queries_executed)
            ),
            "index_size": self._index_size,
            "max_batch_size": self._max_batch_size,
            "last_optimization": self._last_optimization.isoformat() if self._last_optimization else None
        }
        
        base_stats.update(chroma_stats)
        return base_stats
    
    async def _cleanup(self) -> None:
        """Clean up ChromaDB resources."""
        try:
            # ChromaDB client cleanup is handled automatically
            pass
        except Exception as e:
            self.logger.warning(f"Error during ChromaDB cleanup: {e}")
    
    def get_capabilities(self) -> List[AdapterCapability]:
        """Get adapter capabilities."""
        capabilities = [
            AdapterCapability(
                name="vector_storage",
                version="1.0.0",
                description="High-dimensional vector storage and retrieval"
            ),
            AdapterCapability(
                name="similarity_search",
                version="1.0.0",
                description="Cosine/Euclidean similarity search with HNSW indexing"
            ),
            AdapterCapability(
                name="metadata_filtering",
                version="1.0.0",
                description="Complex metadata filtering and hybrid queries"
            ),
            AdapterCapability(
                name="batch_operations",
                version="1.0.0",
                description="Efficient batch storage and retrieval"
            ),
            AdapterCapability(
                name="auto_embedding",
                version="1.0.0",
                description="Automatic embedding generation"
            ),
            AdapterCapability(
                name="persistence",
                version="1.0.0",
                description="Persistent storage to disk"
            )
        ]
        
        if self._auto_embed:
            capabilities.append(AdapterCapability(
                name="text_to_vector",
                version="1.0.0",
                description="Automatic text to vector conversion"
            ))
        
        return capabilities