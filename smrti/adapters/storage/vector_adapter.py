"""
smrti/adapters/storage/vector_adapter.py - Vector Storage Adapter

ChromaDB-based storage adapter optimized for Long-term Memory tier with 
semantic search, embedding management, and high-dimensional vector operations.
"""

from __future__ import annotations

import json
import time
import asyncio
import hashlib
from typing import Dict, List, Optional, Any, Union, Set, Tuple
from datetime import datetime, timedelta
import uuid

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    from chromadb import Client, Collection
    from chromadb.api.types import Documents, Embeddings, Metadatas, IDs
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    chromadb = None
    Client = None
    Collection = None

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False
    SentenceTransformer = None
    np = None

try:
    from ...models.base import MemoryItem, MemoryTier
except ImportError:
    # Direct import fallback for testing
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'models'))
    from base import MemoryItem, MemoryTier

# Simple base config class
from pydantic import BaseModel

class BaseConfig(BaseModel):
    """Base configuration class."""
    pass


class VectorConfig(BaseConfig):
    """Configuration for vector storage adapter."""
    
    # ChromaDB settings
    persist_directory: Optional[str] = "./chroma_db"
    collection_name: str = "smrti_vectors"
    embedding_function: str = "all-MiniLM-L6-v2"  # Default sentence transformer model
    
    # Vector search settings
    n_results: int = 10
    similarity_threshold: float = 0.7
    batch_size: int = 100
    
    # Performance settings
    max_batch_size: int = 1000
    enable_caching: bool = True
    cache_size: int = 10000
    
    # Metadata filtering
    enable_metadata_filtering: bool = True
    max_metadata_size: int = 1024  # bytes
    
    # Advanced settings
    distance_metric: str = "cosine"  # cosine, l2, ip
    normalize_embeddings: bool = True
    
    def get_chroma_settings(self) -> Dict[str, Any]:
        """Generate ChromaDB settings."""
        return {
            "persist_directory": self.persist_directory,
            "anonymized_telemetry": False,
            "allow_reset": True,
        }


class VectorSearchQuery(BaseModel):
    """Vector search query specification."""
    
    query_text: Optional[str] = None
    query_embedding: Optional[List[float]] = None
    n_results: int = 10
    where: Optional[Dict[str, Any]] = None  # Metadata filters
    similarity_threshold: Optional[float] = None
    include_distances: bool = True
    include_metadata: bool = True


class VectorSearchResult(BaseModel):
    """Result of a vector search operation."""
    
    id: str
    content: str
    distance: float
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None


class VectorOperationResult(BaseModel):
    """Result of a vector operation."""
    
    success: bool
    operation: str
    item_count: int = 0
    execution_time_ms: float = 0.0
    error_message: Optional[str] = None
    results: List[VectorSearchResult] = []
    
    @classmethod
    def success_result(cls, operation: str, item_count: int = 0, 
                      execution_time_ms: float = 0.0,
                      results: List[VectorSearchResult] = None) -> 'VectorOperationResult':
        """Create a successful operation result."""
        return cls(
            success=True,
            operation=operation,
            item_count=item_count,
            execution_time_ms=execution_time_ms,
            results=results or []
        )
    
    @classmethod
    def error_result(cls, operation: str, error_message: str,
                    execution_time_ms: float = 0.0) -> 'VectorOperationResult':
        """Create an error operation result."""
        return cls(
            success=False,
            operation=operation,
            error_message=error_message,
            execution_time_ms=execution_time_ms,
            results=[]
        )


class VectorStorageAdapter:
    """ChromaDB-based vector storage adapter for semantic search."""
    
    def __init__(self, config: VectorConfig):
        """Initialize vector storage adapter.
        
        Args:
            config: Vector storage configuration
            
        Raises:
            ImportError: If required packages not available
            ValueError: If configuration invalid
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "chromadb package required for VectorStorageAdapter. "
                "Install with: pip install chromadb"
            )
        
        if not EMBEDDING_AVAILABLE:
            raise ImportError(
                "sentence-transformers and numpy required for VectorStorageAdapter. "
                "Install with: pip install sentence-transformers numpy"
            )
        
        self.config = config
        self.chroma_client: Optional[Any] = None  # ChromaDB Client
        self.collection: Optional[Any] = None  # ChromaDB Collection
        self.embedding_model: Optional[Any] = None  # SentenceTransformer model
        
        # Performance tracking
        self._operations_count = 0
        self._total_operation_time = 0.0
        self._error_count = 0
        
        # Caching
        self._embedding_cache: Dict[str, List[float]] = {}
        self._cache_hits = 0
        self._cache_misses = 0
        
        # Item tracking
        self._stored_items: Set[str] = set()
        
    async def initialize(self) -> None:
        """Initialize ChromaDB connection and embedding model."""
        try:
            # Initialize ChromaDB client
            chroma_settings = ChromaSettings(**self.config.get_chroma_settings())
            self.chroma_client = chromadb.PersistentClient(
                path=self.config.persist_directory,
                settings=chroma_settings
            )
            
            # Get or create collection
            try:
                self.collection = self.chroma_client.get_collection(
                    name=self.config.collection_name
                )
            except Exception:
                # Collection doesn't exist, create it
                self.collection = self.chroma_client.create_collection(
                    name=self.config.collection_name,
                    metadata={
                        "description": "Smrti Long-term Memory storage",
                        "embedding_model": self.config.embedding_function,
                        "distance_metric": self.config.distance_metric
                    }
                )
            
            # Initialize embedding model
            await self._initialize_embedding_model()
            
            print(f"Vector storage initialized with collection: {self.config.collection_name}")
            
        except Exception as e:
            self._error_count += 1
            raise RuntimeError(f"Failed to initialize vector storage: {str(e)}")
    
    async def _initialize_embedding_model(self) -> None:
        """Initialize the sentence transformer model."""
        try:
            # Load in a separate thread to avoid blocking
            loop = asyncio.get_event_loop()
            self.embedding_model = await loop.run_in_executor(
                None, 
                SentenceTransformer, 
                self.config.embedding_function
            )
            print(f"Embedding model loaded: {self.config.embedding_function}")
            
        except Exception as e:
            raise RuntimeError(f"Failed to load embedding model: {str(e)}")
    
    async def close(self) -> None:
        """Close vector storage connections."""
        try:
            if self.chroma_client:
                # ChromaDB handles cleanup automatically
                self.chroma_client = None
            
            self.collection = None
            self.embedding_model = None
            
            # Clear caches
            self._embedding_cache.clear()
            self._stored_items.clear()
            
            print("Vector storage closed successfully")
            
        except Exception as e:
            print(f"Error closing vector storage: {str(e)}")
    
    def _generate_cache_key(self, text: str) -> str:
        """Generate cache key for embedding."""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]
    
    async def _get_embedding(self, text: str) -> List[float]:
        """Get embedding for text with caching."""
        if not self.embedding_model:
            raise RuntimeError("Embedding model not initialized")
        
        # Check cache first
        if self.config.enable_caching:
            cache_key = self._generate_cache_key(text)
            if cache_key in self._embedding_cache:
                self._cache_hits += 1
                return self._embedding_cache[cache_key]
            self._cache_misses += 1
        
        # Generate embedding
        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(
            None,
            self.embedding_model.encode,
            text
        )
        
        # Convert to list and normalize if configured
        embedding_list = embedding.tolist()
        if self.config.normalize_embeddings and np:
            norm = np.linalg.norm(embedding_list)
            if norm > 0:
                embedding_list = (embedding / norm).tolist()
        
        # Cache the result
        if self.config.enable_caching:
            if len(self._embedding_cache) < self.config.cache_size:
                self._embedding_cache[cache_key] = embedding_list
        
        return embedding_list
    
    async def _get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for batch of texts."""
        if not self.embedding_model:
            raise RuntimeError("Embedding model not initialized")
        
        embeddings = []
        uncached_texts = []
        uncached_indices = []
        
        # Check cache for each text
        for i, text in enumerate(texts):
            if self.config.enable_caching:
                cache_key = self._generate_cache_key(text)
                if cache_key in self._embedding_cache:
                    embeddings.append(self._embedding_cache[cache_key])
                    self._cache_hits += 1
                    continue
            
            embeddings.append(None)  # Placeholder
            uncached_texts.append(text)
            uncached_indices.append(i)
            self._cache_misses += 1
        
        # Generate embeddings for uncached texts
        if uncached_texts:
            loop = asyncio.get_event_loop()
            batch_embeddings = await loop.run_in_executor(
                None,
                self.embedding_model.encode,
                uncached_texts
            )
            
            # Process and cache results
            for j, embedding in enumerate(batch_embeddings):
                embedding_list = embedding.tolist()
                
                # Normalize if configured
                if self.config.normalize_embeddings and np:
                    norm = np.linalg.norm(embedding_list)
                    if norm > 0:
                        embedding_list = (embedding / norm).tolist()
                
                # Store in results
                idx = uncached_indices[j]
                embeddings[idx] = embedding_list
                
                # Cache the result
                if self.config.enable_caching and len(self._embedding_cache) < self.config.cache_size:
                    cache_key = self._generate_cache_key(uncached_texts[j])
                    self._embedding_cache[cache_key] = embedding_list
        
        return embeddings
    
    def _prepare_item_for_storage(self, item: MemoryItem) -> Tuple[str, str, Dict[str, Any]]:
        """Prepare memory item for vector storage."""
        # Generate unique ID with tenant/namespace prefix
        item_id = f"{item.get_tenant()}:{item.get_namespace()}:{item.get_id()}"
        
        # Prepare content
        content = item.get_content() or ""
        
        # Prepare metadata
        metadata = {
            "tenant": item.get_tenant(),
            "namespace": item.get_namespace(),
            "original_id": item.get_id(),
            "timestamp": item.get_timestamp(),
            "tier": item.get_tier().value if item.get_tier() else MemoryTier.LONG_TERM.value,
            **item.get_metadata()
        }
        
        # Ensure metadata is JSON serializable and within size limits
        try:
            metadata_json = json.dumps(metadata)
            if len(metadata_json.encode('utf-8')) > self.config.max_metadata_size:
                # Truncate metadata if too large
                metadata = {
                    "tenant": metadata["tenant"],
                    "namespace": metadata["namespace"],
                    "original_id": metadata["original_id"],
                    "timestamp": metadata["timestamp"],
                    "tier": metadata["tier"]
                }
        except (TypeError, ValueError):
            # Fallback to minimal metadata
            metadata = {
                "tenant": item.get_tenant(),
                "namespace": item.get_namespace(),
                "original_id": item.get_id(),
                "timestamp": item.get_timestamp(),
                "tier": item.get_tier().value if item.get_tier() else MemoryTier.LONG_TERM.value
            }
        
        return item_id, content, metadata
    
    async def store_item(self, item: MemoryItem) -> VectorOperationResult:
        """Store a single memory item in vector storage.
        
        Args:
            item: Memory item to store
            
        Returns:
            VectorOperationResult with operation status
        """
        start_time = time.time()
        
        try:
            if not self.collection:
                return VectorOperationResult.error_result(
                    "store_item", 
                    "Vector storage not initialized"
                )
            
            # Prepare item for storage
            item_id, content, metadata = self._prepare_item_for_storage(item)
            
            # Generate embedding
            embedding = await self._get_embedding(content)
            
            # Store in ChromaDB
            self.collection.upsert(
                ids=[item_id],
                documents=[content],
                embeddings=[embedding],
                metadatas=[metadata]
            )
            
            self._stored_items.add(item_id)
            self._operations_count += 1
            
            execution_time = (time.time() - start_time) * 1000
            self._total_operation_time += execution_time
            
            return VectorOperationResult.success_result(
                "store_item",
                item_count=1,
                execution_time_ms=execution_time
            )
            
        except Exception as e:
            self._error_count += 1
            execution_time = (time.time() - start_time) * 1000
            return VectorOperationResult.error_result(
                "store_item",
                f"Failed to store item: {str(e)}",
                execution_time_ms=execution_time
            )
    
    async def store_items_batch(self, items: List[MemoryItem]) -> VectorOperationResult:
        """Store multiple memory items in batch.
        
        Args:
            items: List of memory items to store
            
        Returns:
            VectorOperationResult with operation status
        """
        start_time = time.time()
        
        try:
            if not self.collection:
                return VectorOperationResult.error_result(
                    "store_items_batch", 
                    "Vector storage not initialized"
                )
            
            if not items:
                return VectorOperationResult.success_result(
                    "store_items_batch",
                    item_count=0,
                    execution_time_ms=0.0
                )
            
            # Process items in batches
            batch_size = min(self.config.max_batch_size, len(items))
            total_stored = 0
            
            for i in range(0, len(items), batch_size):
                batch = items[i:i + batch_size]
                
                # Prepare batch data
                ids = []
                documents = []
                metadatas = []
                
                for item in batch:
                    item_id, content, metadata = self._prepare_item_for_storage(item)
                    ids.append(item_id)
                    documents.append(content)
                    metadatas.append(metadata)
                
                # Generate embeddings for batch
                embeddings = await self._get_embeddings_batch(documents)
                
                # Store batch in ChromaDB
                self.collection.upsert(
                    ids=ids,
                    documents=documents,
                    embeddings=embeddings,
                    metadatas=metadatas
                )
                
                # Update tracking
                for item_id in ids:
                    self._stored_items.add(item_id)
                
                total_stored += len(batch)
            
            self._operations_count += 1
            execution_time = (time.time() - start_time) * 1000
            self._total_operation_time += execution_time
            
            return VectorOperationResult.success_result(
                "store_items_batch",
                item_count=total_stored,
                execution_time_ms=execution_time
            )
            
        except Exception as e:
            self._error_count += 1
            execution_time = (time.time() - start_time) * 1000
            return VectorOperationResult.error_result(
                "store_items_batch",
                f"Failed to store items batch: {str(e)}",
                execution_time_ms=execution_time
            )
    
    async def search_similar(self, query: VectorSearchQuery) -> VectorOperationResult:
        """Search for similar items using vector similarity.
        
        Args:
            query: Vector search query specification
            
        Returns:
            VectorOperationResult with search results
        """
        start_time = time.time()
        
        try:
            if not self.collection:
                return VectorOperationResult.error_result(
                    "search_similar", 
                    "Vector storage not initialized"
                )
            
            # Determine query embedding
            query_embedding = query.query_embedding
            if not query_embedding and query.query_text:
                query_embedding = await self._get_embedding(query.query_text)
            elif not query_embedding:
                return VectorOperationResult.error_result(
                    "search_similar",
                    "Either query_text or query_embedding must be provided"
                )
            
            # Perform search
            search_results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=query.n_results,
                where=query.where,
                include=["documents", "metadatas", "distances"]
            )
            
            # Process results
            results = []
            if (search_results["ids"] and search_results["ids"][0] and 
                search_results["distances"] and search_results["distances"][0]):
                
                for i in range(len(search_results["ids"][0])):
                    distance = search_results["distances"][0][i]
                    
                    # Apply similarity threshold if specified
                    if query.similarity_threshold is not None:
                        if distance > (1.0 - query.similarity_threshold):  # Convert to distance threshold
                            continue
                    
                    result = VectorSearchResult(
                        id=search_results["ids"][0][i],
                        content=search_results["documents"][0][i] if search_results["documents"] else "",
                        distance=distance,
                        metadata=search_results["metadatas"][0][i] if search_results["metadatas"] else {}
                    )
                    results.append(result)
            
            self._operations_count += 1
            execution_time = (time.time() - start_time) * 1000
            self._total_operation_time += execution_time
            
            return VectorOperationResult.success_result(
                "search_similar",
                item_count=len(results),
                execution_time_ms=execution_time,
                results=results
            )
            
        except Exception as e:
            self._error_count += 1
            execution_time = (time.time() - start_time) * 1000
            return VectorOperationResult.error_result(
                "search_similar",
                f"Failed to search similar items: {str(e)}",
                execution_time_ms=execution_time
            )
    
    async def retrieve_item(self, tenant: str, namespace: str, item_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific item by ID.
        
        Args:
            tenant: Tenant identifier
            namespace: Namespace identifier  
            item_id: Item identifier
            
        Returns:
            Item data if found, None otherwise
        """
        try:
            if not self.collection:
                return None
            
            # Construct full ID
            full_id = f"{tenant}:{namespace}:{item_id}"
            
            # Get item from collection
            results = self.collection.get(
                ids=[full_id],
                include=["documents", "metadatas", "embeddings"]
            )
            
            if results["ids"] and results["ids"]:
                return {
                    "id": item_id,
                    "content": results["documents"][0] if results["documents"] else "",
                    "metadata": results["metadatas"][0] if results["metadatas"] else {},
                    "embedding": results["embeddings"][0] if results["embeddings"] else None
                }
            
            return None
            
        except Exception as e:
            print(f"Error retrieving item {item_id}: {str(e)}")
            return None
    
    async def delete_item(self, tenant: str, namespace: str, item_id: str) -> VectorOperationResult:
        """Delete an item from vector storage.
        
        Args:
            tenant: Tenant identifier
            namespace: Namespace identifier
            item_id: Item identifier
            
        Returns:
            VectorOperationResult with operation status
        """
        start_time = time.time()
        
        try:
            if not self.collection:
                return VectorOperationResult.error_result(
                    "delete_item", 
                    "Vector storage not initialized"
                )
            
            # Construct full ID
            full_id = f"{tenant}:{namespace}:{item_id}"
            
            # Delete from collection
            self.collection.delete(ids=[full_id])
            
            # Update tracking
            self._stored_items.discard(full_id)
            self._operations_count += 1
            
            execution_time = (time.time() - start_time) * 1000
            self._total_operation_time += execution_time
            
            return VectorOperationResult.success_result(
                "delete_item",
                item_count=1,
                execution_time_ms=execution_time
            )
            
        except Exception as e:
            self._error_count += 1
            execution_time = (time.time() - start_time) * 1000
            return VectorOperationResult.error_result(
                "delete_item",
                f"Failed to delete item: {str(e)}",
                execution_time_ms=execution_time
            )
    
    async def list_items(self, tenant: str, namespace: str, 
                        limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """List items for a tenant/namespace.
        
        Args:
            tenant: Tenant identifier
            namespace: Namespace identifier
            limit: Maximum number of items to return
            offset: Number of items to skip
            
        Returns:
            List of items matching criteria
        """
        try:
            if not self.collection:
                return []
            
            # Query with metadata filters
            where = {
                "tenant": tenant,
                "namespace": namespace
            }
            
            results = self.collection.get(
                where=where,
                limit=limit,
                offset=offset,
                include=["documents", "metadatas"]
            )
            
            items = []
            if results["ids"]:
                for i in range(len(results["ids"])):
                    items.append({
                        "id": results["metadatas"][i].get("original_id") if results["metadatas"] else results["ids"][i],
                        "content": results["documents"][i] if results["documents"] else "",
                        "metadata": results["metadatas"][i] if results["metadatas"] else {}
                    })
            
            return items
            
        except Exception as e:
            print(f"Error listing items for {tenant}:{namespace}: {str(e)}")
            return []
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get adapter statistics.
        
        Returns:
            Dictionary containing performance and usage statistics
        """
        try:
            # Get collection stats if available
            collection_count = 0
            if self.collection:
                try:
                    collection_count = self.collection.count()
                except:
                    collection_count = len(self._stored_items)
            
            avg_operation_time = (
                self._total_operation_time / max(1, self._operations_count)
            )
            
            cache_hit_rate = 0.0
            total_cache_ops = self._cache_hits + self._cache_misses
            if total_cache_ops > 0:
                cache_hit_rate = self._cache_hits / total_cache_ops
            
            return {
                "adapter_type": "vector",
                "backend": "chromadb",
                "collection_name": self.config.collection_name,
                "total_items": collection_count,
                "operations_count": self._operations_count,
                "error_count": self._error_count,
                "avg_operation_time_ms": round(avg_operation_time, 2),
                "total_operation_time_ms": round(self._total_operation_time, 2),
                "embedding_model": self.config.embedding_function,
                "cache_enabled": self.config.enable_caching,
                "cache_size": len(self._embedding_cache),
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
                "cache_hit_rate": round(cache_hit_rate, 3),
                "stored_items_tracked": len(self._stored_items),
                "distance_metric": self.config.distance_metric,
                "normalize_embeddings": self.config.normalize_embeddings,
            }
            
        except Exception as e:
            return {
                "adapter_type": "vector",
                "error": f"Failed to get stats: {str(e)}"
            }
    
    async def health_check(self) -> bool:
        """Check if vector storage is healthy and responsive.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            if not self.chroma_client or not self.collection:
                return False
            
            # Try a simple operation
            test_result = self.collection.count()
            return isinstance(test_result, int) and test_result >= 0
            
        except Exception:
            return False