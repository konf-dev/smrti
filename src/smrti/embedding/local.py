"""Local embedding provider using sentence-transformers."""

import asyncio
import time
from functools import lru_cache
from typing import Dict, List, Any
import hashlib

from sentence_transformers import SentenceTransformer
import torch

from smrti.core.exceptions import EmbeddingError
from smrti.core.logging import get_logger
from smrti.core.metrics import (
    embedding_generations_total,
    embedding_generation_duration_seconds,
    embedding_cache_hits_total,
    embedding_cache_misses_total,
)

logger = get_logger(__name__)


class LocalEmbeddingProvider:
    """
    Local embedding provider using sentence-transformers.
    
    Features:
    - Downloads and loads models at startup
    - CPU/GPU support (auto-detected)
    - LRU cache for repeated texts
    - Batch processing for efficiency
    - Prometheus metrics
    
    Default model: all-MiniLM-L6-v2 (384 dimensions, 80MB)
    """
    
    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        cache_size: int = 10000,
        device: str = "auto"
    ):
        """
        Initialize local embedding provider.
        
        Args:
            model_name: HuggingFace model identifier
            cache_size: Maximum number of cached embeddings
            device: Device to use ('auto', 'cpu', 'cuda', 'mps')
        """
        self.model_name = model_name
        self.cache_size = cache_size
        self._model = None
        self._dimension = None
        
        # Determine device
        if device == "auto":
            if torch.cuda.is_available():
                self.device = "cuda"
            elif torch.backends.mps.is_available():
                self.device = "mps"
            else:
                self.device = "cpu"
        else:
            self.device = device
        
        logger.info(
            "local_embedding_provider_initialized",
            model_name=model_name,
            device=self.device,
            cache_size=cache_size
        )
        
        # Initialize cache statistics
        self._cache_hits = 0
        self._cache_misses = 0
        
    def _get_model(self) -> SentenceTransformer:
        """Lazy load the model."""
        if self._model is None:
            logger.info(
                "loading_embedding_model",
                model_name=self.model_name,
                device=self.device
            )
            start_time = time.time()
            
            try:
                self._model = SentenceTransformer(self.model_name, device=self.device)
                self._dimension = self._model.get_sentence_embedding_dimension()
                
                duration = time.time() - start_time
                logger.info(
                    "embedding_model_loaded",
                    model_name=self.model_name,
                    dimension=self._dimension,
                    duration_s=round(duration, 2)
                )
            except Exception as e:
                logger.error(
                    "embedding_model_load_failed",
                    model_name=self.model_name,
                    error=str(e)
                )
                raise EmbeddingError(f"Failed to load model {self.model_name}: {e}") from e
        
        return self._model
    
    def _hash_text(self, text: str) -> str:
        """Generate cache key from text."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]
    
    @lru_cache(maxsize=10000)
    def _get_cached_embedding(self, text_hash: str, text: str) -> tuple:
        """
        Get embedding from cache or compute it.
        
        Note: We pass text_hash for cache key and text for computation.
        The LRU cache uses text_hash as the key.
        """
        self._cache_misses += 1
        embedding_cache_misses_total.labels(provider="local").inc()
        
        model = self._get_model()
        
        # Compute embedding synchronously
        embedding = model.encode(text, convert_to_numpy=True)
        return tuple(embedding.tolist())
    
    async def embed_single(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text string to embed
            
        Returns:
            Embedding vector
            
        Raises:
            EmbeddingError: If embedding generation fails
        """
        start_time = time.time()
        
        try:
            if not text or not text.strip():
                raise EmbeddingError("Text cannot be empty")
            
            # Check cache
            text_hash = self._hash_text(text)
            
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            embedding_tuple = await loop.run_in_executor(
                None,
                self._get_cached_embedding,
                text_hash,
                text
            )
            
            embedding = list(embedding_tuple)
            
            duration = time.time() - start_time
            
            # Update metrics
            embedding_generations_total.labels(
                provider="local",
                status="success"
            ).inc()
            
            embedding_generation_duration_seconds.labels(
                provider="local"
            ).observe(duration)
            
            logger.debug(
                "embedding_generated",
                text_length=len(text),
                dimension=len(embedding),
                duration_ms=round(duration * 1000, 2)
            )
            
            return embedding
            
        except EmbeddingError:
            raise
        except Exception as e:
            embedding_generations_total.labels(
                provider="local",
                status="error"
            ).inc()
            
            logger.error(
                "embedding_generation_failed",
                text_length=len(text) if text else 0,
                error=str(e)
            )
            raise EmbeddingError(f"Failed to generate embedding: {e}") from e
    
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors
            
        Raises:
            EmbeddingError: If embedding generation fails
        """
        start_time = time.time()
        
        try:
            if not texts:
                return []
            
            # Validate all texts
            for i, text in enumerate(texts):
                if not text or not text.strip():
                    raise EmbeddingError(f"Text at index {i} cannot be empty")
            
            # Check which texts are cached
            cached_embeddings = {}
            uncached_texts = []
            uncached_indices = []
            
            for i, text in enumerate(texts):
                text_hash = self._hash_text(text)
                
                # Try to get from cache info (check if cached without computing)
                try:
                    # Check if in LRU cache by calling with same args
                    embedding_tuple = self._get_cached_embedding.__wrapped__(
                        self, text_hash, text
                    )
                    cached_embeddings[i] = list(embedding_tuple)
                    self._cache_hits += 1
                    embedding_cache_hits_total.labels(provider="local").inc()
                except:
                    uncached_texts.append(text)
                    uncached_indices.append(i)
            
            # Compute uncached embeddings in batch
            if uncached_texts:
                model = self._get_model()
                
                # Run in thread pool
                loop = asyncio.get_event_loop()
                embeddings_array = await loop.run_in_executor(
                    None,
                    lambda: model.encode(uncached_texts, convert_to_numpy=True)
                )
                
                # Convert to list and cache
                for idx, text_idx in enumerate(uncached_indices):
                    text = texts[text_idx]
                    text_hash = self._hash_text(text)
                    embedding = embeddings_array[idx].tolist()
                    
                    # Cache it
                    self._get_cached_embedding(text_hash, text)
                    cached_embeddings[text_idx] = embedding
            
            # Reconstruct in original order
            result = [cached_embeddings[i] for i in range(len(texts))]
            
            duration = time.time() - start_time
            
            # Update metrics
            embedding_generations_total.labels(
                provider="local",
                status="success"
            ).inc()
            
            embedding_generation_duration_seconds.labels(
                provider="local"
            ).observe(duration)
            
            logger.info(
                "batch_embeddings_generated",
                batch_size=len(texts),
                cached_count=len(cached_embeddings) - len(uncached_texts),
                computed_count=len(uncached_texts),
                duration_ms=round(duration * 1000, 2)
            )
            
            return result
            
        except EmbeddingError:
            raise
        except Exception as e:
            embedding_generations_total.labels(
                provider="local",
                status="error"
            ).inc()
            
            logger.error(
                "batch_embedding_generation_failed",
                batch_size=len(texts) if texts else 0,
                error=str(e)
            )
            raise EmbeddingError(f"Failed to generate batch embeddings: {e}") from e
    
    def get_dimension(self) -> int:
        """
        Get the dimension of embedding vectors.
        
        Returns:
            Vector dimension size
        """
        if self._dimension is None:
            # Load model to get dimension
            self._get_model()
        
        return self._dimension
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check if embedding service is healthy.
        
        Returns:
            Status dictionary with service info
        """
        try:
            # Test with a simple embedding
            test_text = "Health check test"
            start_time = time.time()
            
            embedding = await self.embed_single(test_text)
            latency = (time.time() - start_time) * 1000
            
            return {
                "status": "healthy",
                "provider": "local",
                "model": self.model_name,
                "device": self.device,
                "dimension": len(embedding),
                "latency_ms": round(latency, 2),
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
                "cache_size": self.cache_size
            }
            
        except Exception as e:
            logger.error("embedding_health_check_failed", error=str(e))
            return {
                "status": "unhealthy",
                "provider": "local",
                "model": self.model_name,
                "error": str(e)
            }
