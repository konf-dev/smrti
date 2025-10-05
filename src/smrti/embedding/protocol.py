"""Embedding service protocol definition."""

from typing import List, Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """
    Protocol that all embedding providers must implement.
    
    Enables swapping between local models, API providers, etc.
    without changing calling code.
    """
    
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors (one per input text)
            
        Raises:
            EmbeddingError: If embedding generation fails
        """
        ...
    
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
        ...
    
    def get_dimension(self) -> int:
        """
        Get the dimension of embedding vectors.
        
        Returns:
            Vector dimension size
        """
        ...
    
    async def health_check(self) -> dict:
        """
        Check if embedding service is healthy.
        
        Returns:
            Status dictionary with service info
        """
        ...
