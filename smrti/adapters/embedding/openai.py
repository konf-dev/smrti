"""
smrti/adapters/embedding/openai.py - OpenAI embedding provider

OpenAI API-based embedding provider with rate limiting and error handling.
"""

import asyncio
import hashlib
import time
from typing import Any, Dict, List, Optional

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False
    openai = None

from smrti.core.base import BaseEmbeddingProvider
from smrti.core.exceptions import (
    EmbeddingError,
    ConfigurationError,
    RetryableError,
    CapacityExceededError
)
from smrti.core.registry import AdapterCapability


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """
    OpenAI API embedding provider.
    
    Features:
    - Multiple embedding models (text-embedding-ada-002, text-embedding-3-small, etc.)
    - Rate limiting compliance
    - Batch processing
    - Automatic retry with exponential backoff
    - Usage tracking and cost estimation
    """
    
    # Model configurations
    MODEL_CONFIGS = {
        "text-embedding-3-small": {
            "dimension": 1536,
            "max_tokens": 8192,
            "cost_per_1k": 0.00002  # $0.00002 per 1K tokens
        },
        "text-embedding-3-large": {
            "dimension": 3072,
            "max_tokens": 8192,
            "cost_per_1k": 0.00013  # $0.00013 per 1K tokens
        },
        "text-embedding-ada-002": {
            "dimension": 1536,
            "max_tokens": 8192,
            "cost_per_1k": 0.0001   # $0.0001 per 1K tokens
        }
    }
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "text-embedding-3-small",
        config: Optional[Dict[str, Any]] = None
    ):
        if not HAS_OPENAI:
            raise ConfigurationError(
                "openai package is required but not installed. "
                "Install with: pip install openai"
            )
        
        if model_name not in self.MODEL_CONFIGS:
            raise ConfigurationError(
                f"Unsupported OpenAI model: {model_name}. "
                f"Supported models: {list(self.MODEL_CONFIGS.keys())}"
            )
        
        model_config = self.MODEL_CONFIGS[model_name]
        
        super().__init__(
            name="openai",
            model_name=model_name,
            embedding_dim=model_config["dimension"],
            max_tokens=model_config["max_tokens"],
            config=config or {}
        )
        
        # API configuration
        self._api_key = api_key or self.config.get("api_key")
        if not self._api_key:
            raise ConfigurationError(
                "OpenAI API key is required. Set via 'api_key' parameter or OPENAI_API_KEY environment variable"
            )
        
        # Initialize OpenAI client
        self._client = openai.AsyncOpenAI(api_key=self._api_key)
        
        # Rate limiting (OpenAI has rate limits)
        self._requests_per_minute = self.config.get("requests_per_minute", 500)
        self._tokens_per_minute = self.config.get("tokens_per_minute", 150000)
        self._request_times: List[float] = []
        self._token_usage: List[tuple[float, int]] = []  # (timestamp, tokens)
        
        # Batch processing
        self._max_batch_size = self.config.get("max_batch_size", 100)
        self._batch_delay = self.config.get("batch_delay", 0.1)  # Delay between batches
        
        # Cost tracking
        self._cost_per_1k_tokens = model_config["cost_per_1k"]
        self._total_tokens_used = 0
        self._estimated_cost = 0.0
        
        # Statistics
        self._api_calls = 0
        self._api_errors = 0
        self._retry_count = 0
    
    async def _check_rate_limits(self, estimated_tokens: int = 1) -> None:
        """Check and enforce OpenAI rate limits."""
        current_time = time.time()
        
        # Clean old entries (older than 1 minute)
        cutoff_time = current_time - 60
        self._request_times = [t for t in self._request_times if t > cutoff_time]
        self._token_usage = [(t, tokens) for t, tokens in self._token_usage if t > cutoff_time]
        
        # Check requests per minute limit
        if len(self._request_times) >= self._requests_per_minute:
            sleep_time = 60 - (current_time - min(self._request_times))
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
        
        # Check tokens per minute limit
        current_token_usage = sum(tokens for _, tokens in self._token_usage)
        if current_token_usage + estimated_tokens > self._tokens_per_minute:
            sleep_time = 60 - (current_time - min(t for t, _ in self._token_usage))
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
        
        # Record this request
        self._request_times.append(current_time)
        self._token_usage.append((current_time, estimated_tokens))
    
    def _estimate_tokens(self, text: str) -> int:
        """Rough estimation of token count."""
        # OpenAI uses ~4 characters per token on average
        return max(1, len(text) // 4)
    
    def _update_usage_stats(self, tokens_used: int) -> None:
        """Update usage statistics and cost estimation."""
        self._total_tokens_used += tokens_used
        self._estimated_cost += (tokens_used / 1000) * self._cost_per_1k_tokens
    
    async def embed_text(self, text: str) -> List[float]:
        """Generate embedding for single text."""
        return await self._execute_with_retry(
            "embed_text",
            self._embed_text_impl,
            text
        )
    
    async def _embed_text_impl(self, text: str) -> List[float]:
        """Internal implementation for single text embedding."""
        self._validate_text(text)
        
        # Check cache first
        cached_embedding = self._check_cache(text)
        if cached_embedding is not None:
            return cached_embedding
        
        # Estimate tokens and check rate limits
        estimated_tokens = self._estimate_tokens(text)
        await self._check_rate_limits(estimated_tokens)
        
        try:
            self._api_calls += 1
            
            response = await self._client.embeddings.create(
                model=self.model_name,
                input=text
            )
            
            embedding = response.data[0].embedding
            
            # Update statistics
            actual_tokens = response.usage.total_tokens
            self._update_usage_stats(actual_tokens)
            self._embeddings_generated += 1
            
            # Cache the result
            self._cache_embedding(text, embedding)
            
            return embedding
            
        except openai.RateLimitError as e:
            self._api_errors += 1
            raise RetryableError(
                f"OpenAI rate limit exceeded: {e}",
                retry_after_seconds=60
            )
        
        except openai.APIError as e:
            self._api_errors += 1
            if e.status_code in [500, 502, 503, 504]:
                # Server errors are retryable
                raise RetryableError(f"OpenAI API server error: {e}")
            else:
                raise EmbeddingError(
                    f"OpenAI API error: {e}",
                    provider="openai",
                    model=self.model_name,
                    input_text=text[:100] + "..." if len(text) > 100 else text
                )
        
        except Exception as e:
            self._api_errors += 1
            raise EmbeddingError(
                f"Unexpected error generating OpenAI embedding: {e}",
                provider="openai",
                model=self.model_name,
                input_text=text[:100] + "..." if len(text) > 100 else text
            )
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts efficiently."""
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
            cached_embedding = self._check_cache(text)
            if cached_embedding is not None:
                cached_results[i] = cached_embedding
            else:
                uncached_texts.append(text)
                uncached_indices.append(i)
        
        # If all texts are cached, return cached results
        if not uncached_texts:
            return [cached_results[i] for i in range(len(texts))]
        
        # Estimate total tokens and check rate limits
        total_estimated_tokens = sum(self._estimate_tokens(text) for text in uncached_texts)
        await self._check_rate_limits(total_estimated_tokens)
        
        try:
            self._api_calls += 1
            
            response = await self._client.embeddings.create(
                model=self.model_name,
                input=uncached_texts
            )
            
            # Process results
            for i, embedding_data in enumerate(response.data):
                embedding = embedding_data.embedding
                original_index = uncached_indices[i]
                cached_results[original_index] = embedding
                
                # Cache the embedding
                self._cache_embedding(uncached_texts[i], embedding)
            
            # Update statistics
            actual_tokens = response.usage.total_tokens
            self._update_usage_stats(actual_tokens)
            self._embeddings_generated += len(uncached_texts)
            self._batch_operations += 1
            
            # Return results in original order
            return [cached_results[i] for i in range(len(texts))]
            
        except openai.RateLimitError as e:
            self._api_errors += 1
            raise RetryableError(
                f"OpenAI rate limit exceeded: {e}",
                retry_after_seconds=60
            )
        
        except openai.APIError as e:
            self._api_errors += 1
            if e.status_code in [500, 502, 503, 504]:
                raise RetryableError(f"OpenAI API server error: {e}")
            else:
                raise EmbeddingError(
                    f"OpenAI API error: {e}",
                    provider="openai",
                    model=self.model_name
                )
        
        except Exception as e:
            self._api_errors += 1
            raise EmbeddingError(
                f"Unexpected error generating OpenAI batch embeddings: {e}",
                provider="openai",
                model=self.model_name
            )
    
    async def _perform_health_check(self) -> Dict[str, Any]:
        """Perform OpenAI API health check."""
        try:
            # Test with a simple embedding request
            test_text = "Health check test"
            
            start_time = time.time()
            await self._embed_text_impl(test_text)
            test_duration = time.time() - start_time
            
            return {
                "api_accessible": True,
                "model": self.model_name,
                "test_embedding_time": test_duration,
                "total_tokens_used": self._total_tokens_used,
                "estimated_cost": self._estimated_cost,
                "api_calls": self._api_calls,
                "api_errors": self._api_errors,
                "error_rate": self._api_errors / max(1, self._api_calls)
            }
            
        except Exception as e:
            return {
                "api_accessible": False,
                "error": str(e),
                "model": self.model_name
            }
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive OpenAI provider statistics."""
        base_stats = await super().get_stats()
        
        provider_stats = {
            "model": self.model_name,
            "embedding_dimension": self.embedding_dim,
            "api_calls": self._api_calls,
            "api_errors": self._api_errors,
            "error_rate": self._api_errors / max(1, self._api_calls),
            "retry_count": self._retry_count,
            "total_tokens_used": self._total_tokens_used,
            "estimated_cost": self._estimated_cost,
            "cost_per_1k_tokens": self._cost_per_1k_tokens,
            "requests_per_minute_limit": self._requests_per_minute,
            "tokens_per_minute_limit": self._tokens_per_minute,
            "current_rpm_usage": len(self._request_times),
            "current_tpm_usage": sum(tokens for _, tokens in self._token_usage)
        }
        
        base_stats.update(provider_stats)
        return base_stats
    
    def get_capabilities(self) -> List[AdapterCapability]:
        """Get adapter capabilities."""
        return [
            AdapterCapability(
                name="text_embedding",
                version="1.0.0",
                description="Generate dense text embeddings using OpenAI API"
            ),
            AdapterCapability(
                name="batch_embedding",
                version="1.0.0",
                description="Efficient batch embedding generation"
            ),
            AdapterCapability(
                name="rate_limiting",
                version="1.0.0",
                description="Automatic rate limit compliance"
            ),
            AdapterCapability(
                name="cost_tracking",
                version="1.0.0",
                description="Token usage and cost estimation"
            ),
            AdapterCapability(
                name="high_quality",
                version="1.0.0",
                description="State-of-the-art embedding quality"
            )
        ]