"""
smrti/adapters/embedding/sentence_transformers.py - SentenceTransformers embedding provider

Production-ready embedding provider using sentence-transformers with batch processing,
caching, fallback models, and comprehensive error handling.
"""

import asyncio
import hashlib
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

try:
    import sentence_transformers
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False
    # Create a placeholder class for type hints
    class SentenceTransformer:
        pass

import torch
import numpy as np

from smrti.core.base import BaseEmbeddingProvider
from smrti.core.exceptions import (
    EmbeddingError,
    ConfigurationError,
    RetryableError,
    CapacityExceededError
)
from smrti.core.protocols import EmbeddingProvider
from smrti.core.registry import AdapterCapability


class SentenceTransformersProvider(BaseEmbeddingProvider):
    """
    SentenceTransformers-based embedding provider.
    
    Features:
    - Multiple model support with fallback
    - Batch processing for efficiency
    - GPU acceleration when available
    - Embedding caching with LRU eviction
    - Automatic model downloading
    - Performance optimization
    - Comprehensive error handling
    """
    
    # Default models in order of preference (quality vs speed)
    DEFAULT_MODELS = [
        "all-MiniLM-L6-v2",      # Fast, good quality
        "all-mpnet-base-v2",     # Better quality, slower
        "multi-qa-MiniLM-L6-cos-v1",  # Question-answering optimized
        "paraphrase-MiniLM-L6-v2"     # Paraphrase detection
    ]
    
    def __init__(
        self,
        model_name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        if not HAS_SENTENCE_TRANSFORMERS:
            raise ConfigurationError(
                "sentence-transformers package is required but not installed. "
                "Install with: pip install sentence-transformers"
            )
        
        # Determine model to use
        if model_name is None:
            model_name = self.DEFAULT_MODELS[0]
        
        # Initialize with placeholder values - will be set after model loads
        super().__init__(
            name="sentence_transformers",
            model_name=model_name,
            embedding_dim=384,  # Common dimension, will be updated
            max_tokens=512,     # Common max, will be updated
            config=config or {}
        )
        
        # Model configuration
        self._primary_model_name = model_name
        self._fallback_models = self.config.get("fallback_models", self.DEFAULT_MODELS[1:])
        self._device = self._detect_device()
        self._trust_remote_code = self.config.get("trust_remote_code", False)
        
        # Performance configuration
        self._batch_size = self.config.get("batch_size", 32)
        self._max_batch_size = self.config.get("max_batch_size", 128)
        self._num_threads = self.config.get("num_threads", 4)
        self._show_progress_bar = self.config.get("show_progress_bar", False)
        
        # Caching configuration
        self._cache_enabled = self.config.get("cache_enabled", True)
        self._max_cache_size = self.config.get("max_cache_size", 10000)
        self._cache_ttl = self.config.get("cache_ttl", 3600)  # 1 hour
        self._embedding_cache: Dict[str, tuple[List[float], float]] = {}
        
        # Model instances
        self._primary_model: Optional[SentenceTransformer] = None
        self._fallback_model: Optional[SentenceTransformer] = None
        self._executor = ThreadPoolExecutor(max_workers=self._num_threads)
        
        # Statistics
        self._model_load_time = 0.0
        self._fallback_usage_count = 0
        self._batch_count = 0
        self._total_embedding_time = 0.0
        
        self.logger = logging.getLogger(f"smrti.adapters.embedding.{self.name}")
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_model_loaded()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self._cleanup()
    
    def _detect_device(self) -> str:
        """Detect the best available device for model inference."""
        device_preference = self.config.get("device", "auto")
        
        if device_preference != "auto":
            return device_preference
        
        if torch.cuda.is_available():
            return "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"  # Apple Silicon
        else:
            return "cpu"
    
    async def _ensure_model_loaded(self) -> None:
        """Ensure the primary model is loaded and ready."""
        if self._primary_model is not None:
            return
        
        start_time = time.time()
        
        try:
            # Load primary model
            self._primary_model = await self._load_model(self._primary_model_name)
            
            # Update model metadata
            self._embedding_dim = self._primary_model.get_sentence_embedding_dimension()
            self._max_tokens = self._primary_model.max_seq_length
            
            self._model_load_time = time.time() - start_time
            
            self.logger.info(
                f"Loaded primary model {self._primary_model_name} "
                f"(dim={self._embedding_dim}, max_tokens={self._max_tokens}, "
                f"device={self._device}, load_time={self._model_load_time:.2f}s)"
            )
            
        except Exception as e:
            self.logger.error(f"Failed to load primary model {self._primary_model_name}: {e}")
            
            # Try fallback models
            await self._load_fallback_model()
    
    async def _load_model(self, model_name: str) -> SentenceTransformer:
        """Load a specific model asynchronously."""
        def _load_sync():
            return SentenceTransformer(
                model_name,
                device=self._device,
                trust_remote_code=self._trust_remote_code
            )
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, _load_sync)
    
    async def _load_fallback_model(self) -> None:
        """Load a fallback model if primary model fails."""
        for fallback_name in self._fallback_models:
            try:
                self.logger.info(f"Attempting to load fallback model: {fallback_name}")
                
                self._fallback_model = await self._load_model(fallback_name)
                
                # Update metadata for fallback
                self._embedding_dim = self._fallback_model.get_sentence_embedding_dimension()
                self._max_tokens = self._fallback_model.max_seq_length
                
                self.logger.warning(
                    f"Using fallback model {fallback_name} "
                    f"(dim={self._embedding_dim}, max_tokens={self._max_tokens})"
                )
                
                return
                
            except Exception as e:
                self.logger.error(f"Failed to load fallback model {fallback_name}: {e}")
                continue
        
        # If we get here, all models failed
        raise EmbeddingError(
            f"Failed to load primary model {self._primary_model_name} "
            f"and all fallback models: {self._fallback_models}",
            provider="sentence_transformers"
        )
    
    @property
    def model_name(self) -> str:
        """Name of the currently active model."""
        if self._primary_model is not None:
            return self._primary_model_name
        elif self._fallback_model is not None:
            # Find which fallback we're using
            for fallback in self._fallback_models:
                if self._fallback_model.get_model_config().get("name", "").endswith(fallback):
                    return fallback
            return "unknown_fallback"
        else:
            return self._primary_model_name
    
    @property
    def embedding_dim(self) -> int:
        """Dimensionality of generated embeddings."""
        return self._embedding_dim
    
    @property
    def max_tokens(self) -> int:
        """Maximum token length for input text."""
        return self._max_tokens
    
    def _get_active_model(self) -> SentenceTransformer:
        """Get the currently active model."""
        if self._primary_model is not None:
            return self._primary_model
        elif self._fallback_model is not None:
            return self._fallback_model
        else:
            raise EmbeddingError(
                "No embedding model is loaded",
                provider="sentence_transformers"
            )
    
    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text embedding."""
        key_data = f"{self.model_name}:{text}:{self._embedding_dim}"
        return hashlib.sha256(key_data.encode()).hexdigest()
    
    def _get_cached_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding from cache if available and not expired."""
        if not self._cache_enabled:
            return None
        
        cache_key = self._get_cache_key(text)
        
        if cache_key in self._embedding_cache:
            embedding, timestamp = self._embedding_cache[cache_key]
            
            # Check if cache entry is still valid
            if time.time() - timestamp < self._cache_ttl:
                self._cache_hits += 1
                return embedding
            else:
                # Remove expired entry
                del self._embedding_cache[cache_key]
        
        return None
    
    def _cache_embedding(self, text: str, embedding: List[float]) -> None:
        """Cache an embedding with timestamp."""
        if not self._cache_enabled:
            return
        
        cache_key = self._get_cache_key(text)
        current_time = time.time()
        
        # Add to cache
        self._embedding_cache[cache_key] = (embedding, current_time)
        
        # Evict oldest entries if cache is full (simple LRU)
        while len(self._embedding_cache) > self._max_cache_size:
            oldest_key = min(
                self._embedding_cache.keys(),
                key=lambda k: self._embedding_cache[k][1]
            )
            del self._embedding_cache[oldest_key]
    
    async def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for single text.
        
        Args:
            text: Input text to embed
            
        Returns:
            Dense embedding vector
            
        Raises:
            EmbeddingError: If embedding generation fails
        """
        return await self._execute_with_retry(
            "embed_text",
            self._embed_text_impl,
            text
        )
    
    async def _embed_text_impl(self, text: str) -> List[float]:
        """Internal implementation for single text embedding."""
        self._validate_text(text)
        
        # Check cache first
        cached_embedding = self._get_cached_embedding(text)
        if cached_embedding is not None:
            return cached_embedding
        
        # Ensure model is loaded
        await self._ensure_model_loaded()
        
        # Generate embedding
        start_time = time.time()
        
        try:
            model = self._get_active_model()
            
            def _encode_sync():
                return model.encode(
                    [text],
                    batch_size=1,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                    normalize_embeddings=True
                )
            
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(self._executor, _encode_sync)
            
            embedding = embeddings[0].tolist()
            
            # Update statistics
            self._embeddings_generated += 1
            embedding_time = time.time() - start_time
            self._total_embedding_time += embedding_time
            
            # Cache the result
            self._cache_embedding(text, embedding)
            
            return embedding
            
        except Exception as e:
            if self._primary_model is not None and self._fallback_model is None:
                # Try to load and use fallback model
                try:
                    await self._load_fallback_model()
                    self._fallback_usage_count += 1
                    return await self._embed_text_impl(text)  # Recursive retry with fallback
                except Exception:
                    pass
            
            raise EmbeddingError(
                f"Failed to generate embedding for text: {e}",
                provider="sentence_transformers",
                model=self.model_name,
                input_text=text[:100] + "..." if len(text) > 100 else text
            )
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
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
        if not texts:
            return []
        
        if len(texts) > self._max_batch_size:
            raise CapacityExceededError(
                f"Batch size {len(texts)} exceeds maximum {self._max_batch_size}",
                limit_type="batch_size",
                current_value=len(texts),
                limit_value=self._max_batch_size
            )
        
        return await self._execute_with_retry(
            "embed_batch",
            self._embed_batch_impl,
            texts
        )
    
    async def _embed_batch_impl(self, texts: List[str]) -> List[List[float]]:
        """Internal implementation for batch text embedding."""
        # Validate all texts
        for text in texts:
            self._validate_text(text)
        
        # Check cache for all texts
        cached_results = {}
        uncached_texts = []
        uncached_indices = []
        
        for i, text in enumerate(texts):
            cached_embedding = self._get_cached_embedding(text)
            if cached_embedding is not None:
                cached_results[i] = cached_embedding
            else:
                uncached_texts.append(text)
                uncached_indices.append(i)
        
        # If all texts are cached, return cached results
        if not uncached_texts:
            return [cached_results[i] for i in range(len(texts))]
        
        # Ensure model is loaded
        await self._ensure_model_loaded()
        
        # Generate embeddings for uncached texts
        start_time = time.time()
        
        try:
            model = self._get_active_model()
            
            def _encode_batch_sync():
                return model.encode(
                    uncached_texts,
                    batch_size=self._batch_size,
                    show_progress_bar=self._show_progress_bar,
                    convert_to_numpy=True,
                    normalize_embeddings=True
                )
            
            loop = asyncio.get_event_loop()
            new_embeddings = await loop.run_in_executor(self._executor, _encode_batch_sync)
            
            # Convert to list format and cache
            new_embeddings_list = [emb.tolist() for emb in new_embeddings]
            
            for i, (text, embedding) in enumerate(zip(uncached_texts, new_embeddings_list)):
                self._cache_embedding(text, embedding)
                cached_results[uncached_indices[i]] = embedding
            
            # Update statistics
            self._embeddings_generated += len(uncached_texts)
            self._batch_count += 1
            batch_time = time.time() - start_time
            self._total_embedding_time += batch_time
            
            # Return results in original order
            return [cached_results[i] for i in range(len(texts))]
            
        except Exception as e:
            if self._primary_model is not None and self._fallback_model is None:
                # Try to use fallback model
                try:
                    await self._load_fallback_model()
                    self._fallback_usage_count += 1
                    return await self._embed_batch_impl(texts)  # Recursive retry with fallback
                except Exception:
                    pass
            
            raise EmbeddingError(
                f"Failed to generate batch embeddings: {e}",
                provider="sentence_transformers",
                model=self.model_name
            )
    
    async def _perform_health_check(self) -> Dict[str, Any]:
        """Perform embedding provider health check."""
        try:
            # Ensure model is loaded
            await self._ensure_model_loaded()
            
            # Test embedding generation
            test_text = "This is a test embedding."
            start_time = time.time()
            
            await self._embed_text_impl(test_text)
            
            test_duration = time.time() - start_time
            
            return {
                "model_loaded": True,
                "active_model": self.model_name,
                "embedding_dim": self._embedding_dim,
                "max_tokens": self._max_tokens,
                "device": self._device,
                "test_embedding_time": test_duration,
                "cache_size": len(self._embedding_cache),
                "cache_hit_rate": self._cache_hits / max(1, self._embeddings_generated),
                "fallback_usage": self._fallback_usage_count,
                "torch_version": torch.__version__,
                "sentence_transformers_version": sentence_transformers.__version__
            }
            
        except Exception as e:
            return {
                "model_loaded": False,
                "error": str(e),
                "device": self._device
            }
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive embedding provider statistics."""
        base_stats = await super().get_stats()
        
        provider_stats = {
            "primary_model": self._primary_model_name,
            "active_model": self.model_name,
            "fallback_models": self._fallback_models,
            "device": self._device,
            "model_load_time": self._model_load_time,
            "fallback_usage_count": self._fallback_usage_count,
            "batch_count": self._batch_count,
            "total_embedding_time": self._total_embedding_time,
            "average_embedding_time": (
                self._total_embedding_time / max(1, self._embeddings_generated)
            ),
            "cache_enabled": self._cache_enabled,
            "cache_size": len(self._embedding_cache),
            "max_cache_size": self._max_cache_size,
            "cache_ttl": self._cache_ttl,
            "batch_size": self._batch_size,
            "max_batch_size": self._max_batch_size
        }
        
        base_stats.update(provider_stats)
        return base_stats
    
    async def _cleanup(self) -> None:
        """Clean up resources."""
        self._executor.shutdown(wait=False)
        self._embedding_cache.clear()
        
        # Clear model references to free GPU memory
        self._primary_model = None
        self._fallback_model = None
        
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    
    def get_capabilities(self) -> List[AdapterCapability]:
        """Get adapter capabilities."""
        capabilities = [
            AdapterCapability(
                name="text_embedding",
                version="1.0.0",
                description="Generate dense text embeddings using SentenceTransformers"
            ),
            AdapterCapability(
                name="batch_embedding",
                version="1.0.0",
                description="Efficient batch embedding generation"
            ),
            AdapterCapability(
                name="caching",
                version="1.0.0",
                description="LRU embedding cache with TTL"
            ),
            AdapterCapability(
                name="fallback_models",
                version="1.0.0",
                description="Automatic fallback to alternative models"
            )
        ]
        
        if torch.cuda.is_available():
            capabilities.append(AdapterCapability(
                name="gpu_acceleration",
                version="1.0.0",
                description="CUDA GPU acceleration support"
            ))
        
        return capabilities