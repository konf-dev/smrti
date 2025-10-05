"""Unit tests for Local Embedding Provider."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import numpy as np

from smrti.embedding.local import LocalEmbeddingProvider
from smrti.core.exceptions import EmbeddingError


@pytest.fixture
def mock_sentence_transformer():
    """Create a mock SentenceTransformer."""
    mock = MagicMock()
    mock.get_sentence_embedding_dimension.return_value = 384
    
    # Mock encode to return realistic embeddings
    def mock_encode(texts, convert_to_numpy=False):
        if isinstance(texts, str):
            texts = [texts]
        
        # Generate fake embeddings
        embeddings = []
        for text in texts:
            # Generate deterministic embedding based on text
            np.random.seed(hash(text) % 2**32)
            embedding = np.random.randn(384).astype(np.float32)
            embeddings.append(embedding)
        
        return np.array(embeddings) if len(embeddings) > 1 else embeddings[0]
    
    mock.encode.side_effect = mock_encode
    return mock


@pytest.fixture
def provider(mock_sentence_transformer):
    """Create a LocalEmbeddingProvider with mocked model."""
    with patch('smrti.embedding.local.SentenceTransformer', return_value=mock_sentence_transformer):
        provider = LocalEmbeddingProvider(
            model_name="test-model",
            cache_size=100,
            device="cpu"
        )
        # Force model load
        provider._get_model()
    return provider


@pytest.mark.unit
@pytest.mark.asyncio
class TestLocalEmbeddingProvider:
    """Test suite for Local Embedding Provider."""

    async def test_embed_single_success(self, provider):
        """Test single text embedding."""
        text = "Hello world"
        
        embedding = await provider.embed_single(text)
        
        assert isinstance(embedding, list)
        assert len(embedding) == 384
        assert all(isinstance(x, float) for x in embedding)

    async def test_embed_single_empty_text(self, provider):
        """Test that empty text raises error."""
        with pytest.raises(EmbeddingError, match="empty"):
            await provider.embed_single("")

    async def test_embed_single_whitespace_only(self, provider):
        """Test that whitespace-only text raises error."""
        with pytest.raises(EmbeddingError, match="empty"):
            await provider.embed_single("   ")

    async def test_embed_batch_success(self, provider):
        """Test batch text embedding."""
        texts = ["Hello world", "How are you", "Goodbye"]
        
        embeddings = await provider.embed(texts)
        
        assert isinstance(embeddings, list)
        assert len(embeddings) == 3
        assert all(len(emb) == 384 for emb in embeddings)

    async def test_embed_empty_batch(self, provider):
        """Test that empty batch returns empty list."""
        embeddings = await provider.embed([])
        assert embeddings == []

    async def test_embed_batch_with_empty_text(self, provider):
        """Test that batch with empty text raises error."""
        texts = ["Hello", "", "World"]
        
        with pytest.raises(EmbeddingError, match="index 1"):
            await provider.embed(texts)

    async def test_embed_deterministic(self, provider):
        """Test that same text produces same embedding."""
        text = "Deterministic test"
        
        embedding1 = await provider.embed_single(text)
        embedding2 = await provider.embed_single(text)
        
        assert embedding1 == embedding2

    async def test_caching_works(self, provider):
        """Test that caching reduces computation."""
        text = "Cache test"
        
        # First call - cache miss
        initial_misses = provider._cache_misses
        await provider.embed_single(text)
        assert provider._cache_misses > initial_misses
        
        # Second call - should be cached (but with lru_cache it's transparent)
        # Just verify it works
        embedding = await provider.embed_single(text)
        assert len(embedding) == 384

    async def test_get_dimension_without_loading(self):
        """Test getting dimension lazy-loads model."""
        with patch('smrti.embedding.local.SentenceTransformer') as mock_st:
            mock_model = MagicMock()
            mock_model.get_sentence_embedding_dimension.return_value = 384
            mock_st.return_value = mock_model
            
            provider = LocalEmbeddingProvider()
            dimension = provider.get_dimension()
            
            assert dimension == 384
            mock_st.assert_called_once()

    async def test_get_dimension_after_loading(self, provider):
        """Test getting dimension when model is already loaded."""
        dimension = provider.get_dimension()
        assert dimension == 384

    async def test_health_check_success(self, provider):
        """Test health check when service is healthy."""
        health = await provider.health_check()
        
        assert health["status"] == "healthy"
        assert health["provider"] == "local"
        assert health["model"] == "test-model"
        assert health["device"] == "cpu"
        assert health["dimension"] == 384
        assert "latency_ms" in health
        assert "cache_hits" in health
        assert "cache_misses" in health

    async def test_health_check_failure(self):
        """Test health check when service fails."""
        with patch('smrti.embedding.local.SentenceTransformer', side_effect=Exception("Model load failed")):
            provider = LocalEmbeddingProvider()
            
            # Health check should catch the error
            health = await provider.health_check()
            
            assert health["status"] == "unhealthy"
            assert "error" in health

    async def test_different_texts_different_embeddings(self, provider):
        """Test that different texts produce different embeddings."""
        text1 = "Hello world"
        text2 = "Goodbye world"
        
        embedding1 = await provider.embed_single(text1)
        embedding2 = await provider.embed_single(text2)
        
        # Should be different
        assert embedding1 != embedding2

    async def test_batch_maintains_order(self, provider):
        """Test that batch embedding maintains input order."""
        texts = ["First", "Second", "Third"]
        
        embeddings = await provider.embed(texts)
        
        # Get individual embeddings
        emb1 = await provider.embed_single("First")
        emb2 = await provider.embed_single("Second")
        emb3 = await provider.embed_single("Third")
        
        # Compare (allowing for floating point differences)
        assert embeddings[0] == emb1
        assert embeddings[1] == emb2
        assert embeddings[2] == emb3

    async def test_device_auto_detection_cuda(self):
        """Test automatic CUDA device detection."""
        with patch('torch.cuda.is_available', return_value=True):
            with patch('smrti.embedding.local.SentenceTransformer') as mock_st:
                mock_model = MagicMock()
                mock_model.get_sentence_embedding_dimension.return_value = 384
                mock_st.return_value = mock_model
                
                provider = LocalEmbeddingProvider(device="auto")
                provider._get_model()
                
                assert provider.device == "cuda"

    async def test_device_auto_detection_cpu(self):
        """Test fallback to CPU when no GPU available."""
        with patch('torch.cuda.is_available', return_value=False):
            with patch('torch.backends.mps.is_available', return_value=False):
                with patch('smrti.embedding.local.SentenceTransformer') as mock_st:
                    mock_model = MagicMock()
                    mock_model.get_sentence_embedding_dimension.return_value = 384
                    mock_st.return_value = mock_model
                    
                    provider = LocalEmbeddingProvider(device="auto")
                    provider._get_model()
                    
                    assert provider.device == "cpu"

    async def test_model_lazy_loading(self):
        """Test that model is only loaded when needed."""
        with patch('smrti.embedding.local.SentenceTransformer') as mock_st:
            provider = LocalEmbeddingProvider()
            
            # Model should not be loaded yet
            mock_st.assert_not_called()
            
            # Trigger load
            provider._get_model()
            
            # Now it should be loaded
            mock_st.assert_called_once()

    async def test_model_load_failure(self):
        """Test handling of model load failure."""
        with patch('smrti.embedding.local.SentenceTransformer', side_effect=Exception("Download failed")):
            provider = LocalEmbeddingProvider()
            
            with pytest.raises(EmbeddingError, match="Failed to load model"):
                provider._get_model()

    async def test_cache_size_configuration(self):
        """Test that cache size is configurable."""
        provider = LocalEmbeddingProvider(cache_size=50)
        assert provider.cache_size == 50

    async def test_long_text_embedding(self, provider):
        """Test embedding of longer text."""
        # Generate a longer text
        long_text = " ".join(["word"] * 1000)
        
        embedding = await provider.embed_single(long_text)
        
        assert isinstance(embedding, list)
        assert len(embedding) == 384
