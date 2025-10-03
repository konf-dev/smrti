"""
smrti/query/semantic.py - Semantic Search Engine

Advanced semantic search capabilities using embeddings, similarity matching,
and intelligent content analysis for the Smrti memory system.
"""

from __future__ import annotations

import time
import asyncio
import hashlib
from typing import Dict, List, Optional, Any, Union, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import threading
import numpy as np
from collections import defaultdict

from ..models.base import MemoryItem
from .engine import QueryContext, QueryStats


class SimilarityMetric(Enum):
    """Similarity metrics for semantic search."""
    
    COSINE = "cosine"
    EUCLIDEAN = "euclidean"
    MANHATTAN = "manhattan"
    DOT_PRODUCT = "dot_product"
    JACCARD = "jaccard"


class EmbeddingModel(Enum):
    """Embedding models for semantic representation."""
    
    TFIDF = "tfidf"
    WORD2VEC = "word2vec"
    FASTTEXT = "fasttext"
    BERT = "bert"
    SENTENCE_TRANSFORMER = "sentence_transformer"
    OPENAI = "openai"
    CUSTOM = "custom"


@dataclass
class SemanticQuery:
    """Semantic search query specification."""
    
    text: str
    embedding_model: EmbeddingModel = EmbeddingModel.TFIDF
    similarity_metric: SimilarityMetric = SimilarityMetric.COSINE
    
    # Search parameters
    min_similarity: float = 0.1
    max_results: int = 100
    boost_exact_matches: bool = True
    boost_factor: float = 1.5
    
    # Content analysis options
    analyze_content: bool = True
    analyze_metadata: bool = True
    analyze_tags: bool = True
    
    # Filtering options
    content_types: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert query to dictionary."""
        return {
            'text': self.text,
            'embedding_model': self.embedding_model.value,
            'similarity_metric': self.similarity_metric.value,
            'parameters': {
                'min_similarity': self.min_similarity,
                'max_results': self.max_results,
                'boost_exact_matches': self.boost_exact_matches,
                'boost_factor': self.boost_factor
            },
            'analysis': {
                'analyze_content': self.analyze_content,
                'analyze_metadata': self.analyze_metadata,
                'analyze_tags': self.analyze_tags
            },
            'filters': {
                'content_types': self.content_types,
                'languages': self.languages
            }
        }


@dataclass
class SemanticResult:
    """Result from semantic search."""
    
    item: MemoryItem
    similarity_score: float
    embedding_vector: Optional[np.ndarray] = None
    
    # Match details
    exact_matches: List[str] = field(default_factory=list)
    partial_matches: List[str] = field(default_factory=list)
    semantic_matches: List[str] = field(default_factory=list)
    
    # Analysis details
    content_score: float = 0.0
    metadata_score: float = 0.0
    tags_score: float = 0.0
    
    def __post_init__(self):
        """Calculate composite scores."""
        # Boost score for exact matches
        if self.exact_matches:
            self.similarity_score *= 1.5
    
    @property
    def total_score(self) -> float:
        """Get the total weighted score."""
        return (
            self.similarity_score * 0.6 +
            self.content_score * 0.2 +
            self.metadata_score * 0.1 +
            self.tags_score * 0.1
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            'item_id': self.item.id if hasattr(self.item, 'id') else str(hash(str(self.item))),
            'similarity_score': self.similarity_score,
            'total_score': self.total_score,
            'matches': {
                'exact': self.exact_matches,
                'partial': self.partial_matches,
                'semantic': self.semantic_matches
            },
            'component_scores': {
                'content': self.content_score,
                'metadata': self.metadata_score,
                'tags': self.tags_score
            }
        }


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""
    
    @abstractmethod
    async def generate_embedding(self, text: str) -> np.ndarray:
        """Generate embedding vector for text.
        
        Args:
            text: Input text
            
        Returns:
            Embedding vector as numpy array
        """
        pass
    
    @abstractmethod
    def get_dimension(self) -> int:
        """Get the embedding vector dimension."""
        pass
    
    @abstractmethod
    def batch_generate_embeddings(self, texts: List[str]) -> List[np.ndarray]:
        """Generate embeddings for multiple texts efficiently.
        
        Args:
            texts: List of input texts
            
        Returns:
            List of embedding vectors
        """
        pass


class TFIDFEmbeddingProvider(EmbeddingProvider):
    """TF-IDF based embedding provider."""
    
    def __init__(self, max_features: int = 10000, min_df: float = 0.01, max_df: float = 0.95):
        """Initialize TF-IDF provider.
        
        Args:
            max_features: Maximum number of features
            min_df: Minimum document frequency
            max_df: Maximum document frequency
        """
        self.max_features = max_features
        self.min_df = min_df
        self.max_df = max_df
        self.vectorizer = None
        self._fitted = False
        
    async def generate_embedding(self, text: str) -> np.ndarray:
        """Generate TF-IDF embedding for text."""
        if not self._fitted:
            # For single text, create a minimal vectorizer
            from sklearn.feature_extraction.text import TfidfVectorizer
            self.vectorizer = TfidfVectorizer(
                max_features=min(1000, self.max_features),
                stop_words='english',
                lowercase=True
            )
            # Fit on the single text (not ideal, but works for demo)
            self.vectorizer.fit([text])
            self._fitted = True
        
        vector = self.vectorizer.transform([text])
        return vector.toarray()[0]
    
    def get_dimension(self) -> int:
        """Get embedding dimension."""
        if self.vectorizer:
            return len(self.vectorizer.get_feature_names_out())
        return self.max_features
    
    def batch_generate_embeddings(self, texts: List[str]) -> List[np.ndarray]:
        """Generate TF-IDF embeddings for multiple texts."""
        if not texts:
            return []
        
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            
            # Create and fit vectorizer
            self.vectorizer = TfidfVectorizer(
                max_features=self.max_features,
                min_df=self.min_df,
                max_df=self.max_df,
                stop_words='english',
                lowercase=True
            )
            
            vectors = self.vectorizer.fit_transform(texts)
            self._fitted = True
            
            return [vectors[i].toarray()[0] for i in range(len(texts))]
            
        except ImportError:
            # Fallback to simple word counting if sklearn not available
            return self._simple_word_embeddings(texts)
    
    def _simple_word_embeddings(self, texts: List[str]) -> List[np.ndarray]:
        """Simple word-based embeddings as fallback."""
        # Build vocabulary
        vocab = set()
        for text in texts:
            words = text.lower().split()
            vocab.update(words)
        
        vocab_list = sorted(list(vocab))[:self.max_features]
        vocab_index = {word: i for i, word in enumerate(vocab_list)}
        
        embeddings = []
        for text in texts:
            vector = np.zeros(len(vocab_list))
            words = text.lower().split()
            word_count = len(words)
            
            # Count word frequencies
            for word in words:
                if word in vocab_index:
                    vector[vocab_index[word]] += 1.0 / word_count
            
            embeddings.append(vector)
        
        return embeddings


class SemanticSearchEngine:
    """Main semantic search engine."""
    
    def __init__(self, default_embedding_model: EmbeddingModel = EmbeddingModel.TFIDF):
        """Initialize semantic search engine.
        
        Args:
            default_embedding_model: Default embedding model to use
        """
        self.default_embedding_model = default_embedding_model
        
        # Embedding providers
        self.embedding_providers: Dict[EmbeddingModel, EmbeddingProvider] = {
            EmbeddingModel.TFIDF: TFIDFEmbeddingProvider()
        }
        
        # Embedding cache
        self._embedding_cache: Dict[str, Tuple[np.ndarray, float]] = {}
        self._cache_lock = threading.Lock()
        
        # Search statistics
        self._search_count = 0
        self._total_search_time = 0.0
        self._cache_hits = 0
        self._cache_misses = 0
    
    def register_embedding_provider(self, model: EmbeddingModel, provider: EmbeddingProvider) -> None:
        """Register an embedding provider.
        
        Args:
            model: Embedding model type
            provider: Provider implementation
        """
        self.embedding_providers[model] = provider
    
    async def search(self, query: str, items: List[MemoryItem], 
                    max_results: Optional[int] = None,
                    embedding_model: Optional[EmbeddingModel] = None,
                    similarity_metric: SimilarityMetric = SimilarityMetric.COSINE,
                    min_similarity: float = 0.1) -> List[MemoryItem]:
        """Perform semantic search on memory items.
        
        Args:
            query: Search query text
            items: Memory items to search
            max_results: Maximum number of results
            embedding_model: Embedding model to use
            similarity_metric: Similarity metric
            min_similarity: Minimum similarity threshold
            
        Returns:
            Ranked list of matching memory items
        """
        start_time = time.time()
        
        try:
            # Use default model if not specified
            if embedding_model is None:
                embedding_model = self.default_embedding_model
            
            # Get embedding provider
            provider = self.embedding_providers.get(embedding_model)
            if not provider:
                raise ValueError(f"No provider for embedding model: {embedding_model}")
            
            # Generate query embedding
            query_embedding = await self._get_or_generate_embedding(query, provider)
            
            # Generate embeddings for all items
            item_texts = []
            for item in items:
                text = self._extract_searchable_text(item)
                item_texts.append(text)
            
            item_embeddings = await self._get_or_generate_batch_embeddings(item_texts, provider)
            
            # Calculate similarities
            similarities = []
            for i, item in enumerate(items):
                if i < len(item_embeddings):
                    similarity = self._calculate_similarity(
                        query_embedding, item_embeddings[i], similarity_metric
                    )
                    
                    if similarity >= min_similarity:
                        similarities.append((item, similarity))
            
            # Sort by similarity score
            similarities.sort(key=lambda x: x[1], reverse=True)
            
            # Apply max results limit
            if max_results:
                similarities = similarities[:max_results]
            
            # Extract items
            result_items = [item for item, score in similarities]
            
            # Update statistics
            self._update_search_stats(time.time() - start_time)
            
            return result_items
            
        except Exception as e:
            # Return empty results on error
            self._update_search_stats(time.time() - start_time)
            return []
    
    async def search_detailed(self, semantic_query: SemanticQuery, 
                            items: List[MemoryItem]) -> List[SemanticResult]:
        """Perform detailed semantic search with full result information.
        
        Args:
            semantic_query: Detailed search specification
            items: Memory items to search
            
        Returns:
            List of detailed semantic results
        """
        start_time = time.time()
        
        try:
            # Get embedding provider
            provider = self.embedding_providers.get(semantic_query.embedding_model)
            if not provider:
                raise ValueError(f"No provider for embedding model: {semantic_query.embedding_model}")
            
            # Generate query embedding
            query_embedding = await self._get_or_generate_embedding(
                semantic_query.text, provider
            )
            
            # Process each item
            results = []
            for item in items:
                result = await self._analyze_item_similarity(
                    item, semantic_query, query_embedding, provider
                )
                
                if result and result.similarity_score >= semantic_query.min_similarity:
                    results.append(result)
            
            # Sort by total score
            results.sort(key=lambda x: x.total_score, reverse=True)
            
            # Apply max results limit
            if semantic_query.max_results:
                results = results[:semantic_query.max_results]
            
            self._update_search_stats(time.time() - start_time)
            return results
            
        except Exception as e:
            self._update_search_stats(time.time() - start_time)
            return []
    
    async def _analyze_item_similarity(self, item: MemoryItem, query: SemanticQuery,
                                     query_embedding: np.ndarray, 
                                     provider: EmbeddingProvider) -> Optional[SemanticResult]:
        """Analyze similarity between an item and query.
        
        Args:
            item: Memory item to analyze
            query: Semantic query specification
            query_embedding: Query embedding vector
            provider: Embedding provider
            
        Returns:
            Detailed semantic result or None
        """
        # Extract searchable text
        item_text = self._extract_searchable_text(item)
        if not item_text.strip():
            return None
        
        # Generate item embedding
        item_embedding = await self._get_or_generate_embedding(item_text, provider)
        
        # Calculate similarity
        similarity = self._calculate_similarity(
            query_embedding, item_embedding, query.similarity_metric
        )
        
        # Create result object
        result = SemanticResult(
            item=item,
            similarity_score=similarity,
            embedding_vector=item_embedding
        )
        
        # Analyze exact and partial matches
        query_words = set(query.text.lower().split())
        item_words = set(item_text.lower().split())
        
        # Find exact matches
        exact_matches = query_words.intersection(item_words)
        result.exact_matches = list(exact_matches)
        
        # Find partial matches (words that contain query words or vice versa)
        partial_matches = set()
        for q_word in query_words:
            for i_word in item_words:
                if q_word in i_word or i_word in q_word:
                    if q_word != i_word:  # Not exact match
                        partial_matches.add(f"{q_word}~{i_word}")
        result.partial_matches = list(partial_matches)
        
        # Component-specific analysis
        if query.analyze_content:
            result.content_score = self._analyze_content_similarity(
                query.text, self._extract_content(item)
            )
        
        if query.analyze_metadata:
            result.metadata_score = self._analyze_metadata_similarity(
                query.text, self._extract_metadata(item)
            )
        
        if query.analyze_tags:
            result.tags_score = self._analyze_tags_similarity(
                query.text, self._extract_tags(item)
            )
        
        return result
    
    def _extract_searchable_text(self, item: MemoryItem) -> str:
        """Extract searchable text from a memory item.
        
        Args:
            item: Memory item
            
        Returns:
            Searchable text content
        """
        parts = []
        
        # Add content if available
        if hasattr(item, 'content') and item.content:
            parts.append(str(item.content))
        
        # Add title or name if available
        if hasattr(item, 'title') and item.title:
            parts.append(str(item.title))
        elif hasattr(item, 'name') and item.name:
            parts.append(str(item.name))
        
        # Add description if available
        if hasattr(item, 'description') and item.description:
            parts.append(str(item.description))
        
        # Add tags if available
        if hasattr(item, 'tags') and item.tags:
            if isinstance(item.tags, (list, tuple)):
                parts.extend(str(tag) for tag in item.tags)
            else:
                parts.append(str(item.tags))
        
        # Add metadata values if available
        if hasattr(item, 'metadata') and item.metadata:
            if isinstance(item.metadata, dict):
                for value in item.metadata.values():
                    if isinstance(value, str):
                        parts.append(value)
        
        return " ".join(parts).strip()
    
    def _extract_content(self, item: MemoryItem) -> str:
        """Extract main content from memory item."""
        if hasattr(item, 'content') and item.content:
            return str(item.content)
        return ""
    
    def _extract_metadata(self, item: MemoryItem) -> str:
        """Extract metadata text from memory item."""
        parts = []
        if hasattr(item, 'metadata') and item.metadata:
            if isinstance(item.metadata, dict):
                for key, value in item.metadata.items():
                    parts.append(f"{key}: {value}")
        return " ".join(parts)
    
    def _extract_tags(self, item: MemoryItem) -> str:
        """Extract tags from memory item."""
        if hasattr(item, 'tags') and item.tags:
            if isinstance(item.tags, (list, tuple)):
                return " ".join(str(tag) for tag in item.tags)
            else:
                return str(item.tags)
        return ""
    
    def _analyze_content_similarity(self, query: str, content: str) -> float:
        """Analyze content similarity score."""
        if not content:
            return 0.0
        
        query_words = set(query.lower().split())
        content_words = set(content.lower().split())
        
        if not query_words or not content_words:
            return 0.0
        
        # Jaccard similarity
        intersection = query_words.intersection(content_words)
        union = query_words.union(content_words)
        
        return len(intersection) / len(union) if union else 0.0
    
    def _analyze_metadata_similarity(self, query: str, metadata: str) -> float:
        """Analyze metadata similarity score."""
        return self._analyze_content_similarity(query, metadata)
    
    def _analyze_tags_similarity(self, query: str, tags: str) -> float:
        """Analyze tags similarity score."""
        return self._analyze_content_similarity(query, tags)
    
    async def _get_or_generate_embedding(self, text: str, provider: EmbeddingProvider) -> np.ndarray:
        """Get embedding from cache or generate new one.
        
        Args:
            text: Text to embed
            provider: Embedding provider
            
        Returns:
            Embedding vector
        """
        # Create cache key
        cache_key = hashlib.md5(f"{text}:{type(provider).__name__}".encode()).hexdigest()
        
        with self._cache_lock:
            if cache_key in self._embedding_cache:
                embedding, timestamp = self._embedding_cache[cache_key]
                # Cache embeddings for 1 hour
                if time.time() - timestamp < 3600:
                    self._cache_hits += 1
                    return embedding
                else:
                    del self._embedding_cache[cache_key]
        
        # Generate new embedding
        embedding = await provider.generate_embedding(text)
        
        # Cache the result
        with self._cache_lock:
            self._embedding_cache[cache_key] = (embedding, time.time())
            self._cache_misses += 1
        
        return embedding
    
    async def _get_or_generate_batch_embeddings(self, texts: List[str], 
                                               provider: EmbeddingProvider) -> List[np.ndarray]:
        """Get batch embeddings efficiently.
        
        Args:
            texts: List of texts to embed
            provider: Embedding provider
            
        Returns:
            List of embedding vectors
        """
        # For now, use batch generation directly
        # In a real implementation, you'd check cache for each text
        try:
            embeddings = provider.batch_generate_embeddings(texts)
            return embeddings
        except Exception:
            # Fallback to individual generation
            embeddings = []
            for text in texts:
                try:
                    embedding = await provider.generate_embedding(text)
                    embeddings.append(embedding)
                except Exception:
                    # Use zero vector as fallback
                    embeddings.append(np.zeros(provider.get_dimension()))
            return embeddings
    
    def _calculate_similarity(self, vec1: np.ndarray, vec2: np.ndarray, 
                            metric: SimilarityMetric) -> float:
        """Calculate similarity between two vectors.
        
        Args:
            vec1: First vector
            vec2: Second vector
            metric: Similarity metric to use
            
        Returns:
            Similarity score
        """
        try:
            if metric == SimilarityMetric.COSINE:
                return self._cosine_similarity(vec1, vec2)
            elif metric == SimilarityMetric.EUCLIDEAN:
                return self._euclidean_similarity(vec1, vec2)
            elif metric == SimilarityMetric.MANHATTAN:
                return self._manhattan_similarity(vec1, vec2)
            elif metric == SimilarityMetric.DOT_PRODUCT:
                return self._dot_product_similarity(vec1, vec2)
            else:
                return self._cosine_similarity(vec1, vec2)
        except Exception:
            return 0.0
    
    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate cosine similarity."""
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def _euclidean_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate Euclidean similarity (1 / (1 + distance))."""
        distance = np.linalg.norm(vec1 - vec2)
        return 1.0 / (1.0 + distance)
    
    def _manhattan_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate Manhattan similarity (1 / (1 + distance))."""
        distance = np.sum(np.abs(vec1 - vec2))
        return 1.0 / (1.0 + distance)
    
    def _dot_product_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate normalized dot product similarity."""
        return np.dot(vec1, vec2) / (len(vec1) ** 0.5)
    
    def _update_search_stats(self, execution_time: float) -> None:
        """Update search statistics."""
        self._search_count += 1
        self._total_search_time += execution_time
    
    def get_search_stats(self) -> Dict[str, Any]:
        """Get search engine statistics."""
        avg_search_time = (
            self._total_search_time / max(1, self._search_count)
        )
        
        cache_total = self._cache_hits + self._cache_misses
        cache_hit_rate = self._cache_hits / max(1, cache_total)
        
        return {
            'total_searches': self._search_count,
            'total_search_time': self._total_search_time,
            'average_search_time': avg_search_time,
            'cache_stats': {
                'hits': self._cache_hits,
                'misses': self._cache_misses,
                'hit_rate': cache_hit_rate,
                'cache_size': len(self._embedding_cache)
            },
            'providers': {
                model.value: type(provider).__name__
                for model, provider in self.embedding_providers.items()
            }
        }
    
    def clear_cache(self) -> None:
        """Clear the embedding cache."""
        with self._cache_lock:
            self._embedding_cache.clear()