"""
smrti.adapters - Storage, retrieval, embedding, graph, and lexical adapters

Collection of adapter implementations for different storage backends,
embedding providers, and specialized services.
"""

from .embedding import (
    SentenceTransformersProvider,
    OpenAIEmbeddingProvider,
)

from .storage import (
    RedisAdapter,
)

from .vector import (
    ChromaDBAdapter,
)

from .database import (
    PostgreSQLAdapter,
)

from .graph import (
    Neo4jAdapter,
)

from .search import (
    ElasticsearchAdapter,
)

__all__ = [
    # Embedding providers
    "SentenceTransformersProvider",
    "OpenAIEmbeddingProvider",
    
    # Storage adapters
    "RedisAdapter",
    
    # Vector store adapters
    "ChromaDBAdapter",
    
    # Database adapters
    "PostgreSQLAdapter",
    
    # Graph adapters
    "Neo4jAdapter",
    
    # Search adapters
    "ElasticsearchAdapter",
]