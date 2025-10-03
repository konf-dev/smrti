"""
smrti/query/ranking.py - Intelligent Ranking and Scoring System

Advanced ranking algorithms for memory items based on relevance, importance,
recency, access patterns, and composite scoring mechanisms.
"""

from __future__ import annotations

import time
import math
from typing import Dict, List, Optional, Any, Union, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import statistics

from ..models.base import MemoryItem
from .engine import QueryContext, QueryStats


class RankingMethod(Enum):
    """Available ranking methods."""
    
    RELEVANCE = "relevance"
    IMPORTANCE = "importance"
    RECENCY = "recency"
    ACCESS_FREQUENCY = "access_frequency"
    COMPOSITE = "composite"
    CUSTOM = "custom"


class SortOrder(Enum):
    """Sort order options."""
    
    ASCENDING = "asc"
    DESCENDING = "desc"


@dataclass
class RankingScore:
    """Score components for a ranked item."""
    
    total_score: float
    relevance_score: float = 0.0
    importance_score: float = 0.0
    recency_score: float = 0.0
    frequency_score: float = 0.0
    custom_scores: Dict[str, float] = field(default_factory=dict)
    
    def __post_init__(self):
        """Ensure scores are within valid range [0, 1]."""
        self.total_score = max(0.0, min(1.0, self.total_score))
        self.relevance_score = max(0.0, min(1.0, self.relevance_score))
        self.importance_score = max(0.0, min(1.0, self.importance_score))
        self.recency_score = max(0.0, min(1.0, self.recency_score))
        self.frequency_score = max(0.0, min(1.0, self.frequency_score))


@dataclass
class RankedItem:
    """Memory item with ranking information."""
    
    item: MemoryItem
    score: RankingScore
    rank: int = 0
    explanation: str = ""
    
    def __lt__(self, other: 'RankedItem') -> bool:
        """Support sorting by total score."""
        return self.score.total_score < other.score.total_score


class BaseRanker(ABC):
    """Abstract base class for ranking algorithms."""
    
    @abstractmethod
    async def rank(self, items: List[MemoryItem], context: QueryContext) -> List[RankedItem]:
        """Rank a list of memory items.
        
        Args:
            items: Memory items to rank
            context: Query execution context
            
        Returns:
            List of ranked items in descending score order
        """
        pass
    
    def should_apply(self, query_ast: Any) -> bool:
        """Check if this ranker should be applied based on query AST.
        
        Args:
            query_ast: Parsed query AST
            
        Returns:
            True if ranker should be applied
        """
        return True


class RelevanceRanker(BaseRanker):
    """Rank by relevance to query terms."""
    
    def __init__(self, boost_exact_matches: bool = True,
                 boost_title_matches: bool = True,
                 decay_function: str = "linear"):
        """Initialize relevance ranker.
        
        Args:
            boost_exact_matches: Give higher scores to exact term matches
            boost_title_matches: Give higher scores to title matches
            decay_function: Score decay function ("linear", "exponential", "logarithmic")
        """
        self.boost_exact_matches = boost_exact_matches
        self.boost_title_matches = boost_title_matches
        self.decay_function = decay_function
    
    async def rank(self, items: List[MemoryItem], context: QueryContext) -> List[RankedItem]:
        """Rank items by relevance."""
        ranked_items = []
        query_terms = self._extract_query_terms(context)
        
        if not query_terms:
            # No query terms - assign equal relevance
            for item in items:
                score = RankingScore(
                    total_score=0.5,
                    relevance_score=0.5
                )
                ranked_items.append(RankedItem(
                    item=item,
                    score=score,
                    explanation="No query terms for relevance scoring"
                ))
        else:
            # Calculate relevance scores
            for item in items:
                relevance_score = self._calculate_relevance_score(item, query_terms)
                score = RankingScore(
                    total_score=relevance_score,
                    relevance_score=relevance_score
                )
                
                ranked_items.append(RankedItem(
                    item=item,
                    score=score,
                    explanation=f"Relevance score: {relevance_score:.3f}"
                ))
        
        # Sort by total score (descending)
        ranked_items.sort(key=lambda x: x.score.total_score, reverse=True)
        
        # Assign ranks
        for i, ranked_item in enumerate(ranked_items):
            ranked_item.rank = i + 1
        
        return ranked_items
    
    def _extract_query_terms(self, context: QueryContext) -> List[str]:
        """Extract query terms from context."""
        query_text = getattr(context, 'query_text', '')
        if not query_text:
            return []
        
        # Simple tokenization - split by whitespace and punctuation
        import re
        terms = re.findall(r'\b\w+\b', query_text.lower())
        return [term for term in terms if len(term) > 2]  # Filter short words
    
    def _calculate_relevance_score(self, item: MemoryItem, query_terms: List[str]) -> float:
        """Calculate relevance score for an item."""
        if not query_terms:
            return 0.0
        
        # Extract searchable text from item
        searchable_text = self._extract_searchable_text(item).lower()
        title_text = self._extract_title_text(item).lower()
        
        if not searchable_text:
            return 0.0
        
        # Count term matches
        total_matches = 0
        exact_matches = 0
        title_matches = 0
        
        for term in query_terms:
            # Count occurrences in content
            content_count = searchable_text.count(term)
            total_matches += content_count
            
            # Check for exact matches (word boundaries)
            import re
            exact_pattern = r'\b' + re.escape(term) + r'\b'
            if re.search(exact_pattern, searchable_text):
                exact_matches += 1
            
            # Check title matches
            if title_text and term in title_text:
                title_matches += 1
        
        # Calculate base score
        base_score = min(1.0, total_matches / (len(query_terms) * 5))  # Normalize
        
        # Apply boosts
        if self.boost_exact_matches and exact_matches > 0:
            exact_boost = min(0.3, exact_matches / len(query_terms) * 0.3)
            base_score += exact_boost
        
        if self.boost_title_matches and title_matches > 0:
            title_boost = min(0.2, title_matches / len(query_terms) * 0.2)
            base_score += title_boost
        
        return min(1.0, base_score)
    
    def _extract_searchable_text(self, item: MemoryItem) -> str:
        """Extract searchable text from memory item."""
        text_parts = []
        
        # Try common content fields
        for field in ['content', 'text', 'body', 'description', 'summary']:
            if hasattr(item, field):
                value = getattr(item, field)
                if value:
                    text_parts.append(str(value))
        
        # Include metadata text
        if hasattr(item, 'metadata') and isinstance(item.metadata, dict):
            for key, value in item.metadata.items():
                if isinstance(value, str) and len(value) > 10:
                    text_parts.append(value)
        
        return ' '.join(text_parts)
    
    def _extract_title_text(self, item: MemoryItem) -> str:
        """Extract title text from memory item."""
        for field in ['title', 'name', 'subject', 'header']:
            if hasattr(item, field):
                value = getattr(item, field)
                if value:
                    return str(value)
        
        return ""


class ImportanceRanker(BaseRanker):
    """Rank by importance score."""
    
    def __init__(self, importance_field: str = "importance",
                 default_importance: float = 0.5):
        """Initialize importance ranker.
        
        Args:
            importance_field: Field containing importance score
            default_importance: Default importance for items without scores
        """
        self.importance_field = importance_field
        self.default_importance = default_importance
    
    async def rank(self, items: List[MemoryItem], context: QueryContext) -> List[RankedItem]:
        """Rank items by importance."""
        ranked_items = []
        
        for item in items:
            importance_score = self._get_importance_score(item)
            score = RankingScore(
                total_score=importance_score,
                importance_score=importance_score
            )
            
            ranked_items.append(RankedItem(
                item=item,
                score=score,
                explanation=f"Importance score: {importance_score:.3f}"
            ))
        
        # Sort by importance (descending)
        ranked_items.sort(key=lambda x: x.score.total_score, reverse=True)
        
        # Assign ranks
        for i, ranked_item in enumerate(ranked_items):
            ranked_item.rank = i + 1
        
        return ranked_items
    
    def _get_importance_score(self, item: MemoryItem) -> float:
        """Get importance score from memory item."""
        # Try direct attribute
        if hasattr(item, self.importance_field):
            value = getattr(item, self.importance_field)
            try:
                return max(0.0, min(1.0, float(value)))
            except (ValueError, TypeError):
                pass
        
        # Try metadata
        if hasattr(item, 'metadata') and isinstance(item.metadata, dict):
            value = item.metadata.get(self.importance_field)
            if value is not None:
                try:
                    return max(0.0, min(1.0, float(value)))
                except (ValueError, TypeError):
                    pass
        
        return self.default_importance


class RecencyRanker(BaseRanker):
    """Rank by recency (newer items first)."""
    
    def __init__(self, time_field: str = "timestamp",
                 decay_days: float = 30.0,
                 decay_function: str = "exponential"):
        """Initialize recency ranker.
        
        Args:
            time_field: Field containing timestamp
            decay_days: Days over which to apply decay
            decay_function: Decay function ("linear", "exponential", "logarithmic")
        """
        self.time_field = time_field
        self.decay_days = decay_days
        self.decay_function = decay_function
    
    async def rank(self, items: List[MemoryItem], context: QueryContext) -> List[RankedItem]:
        """Rank items by recency."""
        ranked_items = []
        current_time = time.time()
        
        for item in items:
            recency_score = self._calculate_recency_score(item, current_time)
            score = RankingScore(
                total_score=recency_score,
                recency_score=recency_score
            )
            
            ranked_items.append(RankedItem(
                item=item,
                score=score,
                explanation=f"Recency score: {recency_score:.3f}"
            ))
        
        # Sort by recency (descending)
        ranked_items.sort(key=lambda x: x.score.total_score, reverse=True)
        
        # Assign ranks
        for i, ranked_item in enumerate(ranked_items):
            ranked_item.rank = i + 1
        
        return ranked_items
    
    def _calculate_recency_score(self, item: MemoryItem, current_time: float) -> float:
        """Calculate recency score for an item."""
        item_time = self._get_item_timestamp(item)
        if item_time is None:
            return 0.5  # Default for items without timestamps
        
        # Calculate age in days
        age_seconds = current_time - item_time
        age_days = age_seconds / 86400.0
        
        if age_days <= 0:
            return 1.0  # Future items get max score
        
        # Apply decay function
        if self.decay_function == "linear":
            score = max(0.0, 1.0 - (age_days / self.decay_days))
        elif self.decay_function == "exponential":
            decay_rate = math.log(0.1) / self.decay_days  # 10% remaining after decay_days
            score = math.exp(decay_rate * age_days)
        elif self.decay_function == "logarithmic":
            score = max(0.0, 1.0 - math.log(age_days + 1) / math.log(self.decay_days + 1))
        else:
            score = 1.0 / (1.0 + age_days / self.decay_days)  # Hyperbolic decay
        
        return max(0.0, min(1.0, score))
    
    def _get_item_timestamp(self, item: MemoryItem) -> Optional[float]:
        """Get timestamp from memory item."""
        # Try common timestamp fields
        for field in [self.time_field, 'created_at', 'timestamp', 'date', 'time']:
            if hasattr(item, field):
                value = getattr(item, field)
                if value is not None:
                    try:
                        if isinstance(value, (int, float)):
                            return float(value)
                        elif hasattr(value, 'timestamp'):
                            return value.timestamp()
                        else:
                            return float(value)
                    except (ValueError, TypeError):
                        continue
        
        # Try metadata
        if hasattr(item, 'metadata') and isinstance(item.metadata, dict):
            for field in ['timestamp', 'created_at', 'date', 'time']:
                value = item.metadata.get(field)
                if value is not None:
                    try:
                        if isinstance(value, (int, float)):
                            return float(value)
                        elif hasattr(value, 'timestamp'):
                            return value.timestamp()
                        else:
                            return float(value)
                    except (ValueError, TypeError):
                        continue
        
        return None


class AccessFrequencyRanker(BaseRanker):
    """Rank by access frequency patterns."""
    
    def __init__(self, access_field: str = "access_count",
                 normalize_by_age: bool = True):
        """Initialize access frequency ranker.
        
        Args:
            access_field: Field containing access count
            normalize_by_age: Whether to normalize by item age
        """
        self.access_field = access_field
        self.normalize_by_age = normalize_by_age
    
    async def rank(self, items: List[MemoryItem], context: QueryContext) -> List[RankedItem]:
        """Rank items by access frequency."""
        ranked_items = []
        access_scores = []
        
        # Calculate access scores for all items
        for item in items:
            frequency_score = self._calculate_frequency_score(item)
            access_scores.append(frequency_score)
        
        # Normalize scores
        if access_scores:
            max_score = max(access_scores)
            if max_score > 0:
                access_scores = [score / max_score for score in access_scores]
        
        # Create ranked items
        for item, frequency_score in zip(items, access_scores):
            score = RankingScore(
                total_score=frequency_score,
                frequency_score=frequency_score
            )
            
            ranked_items.append(RankedItem(
                item=item,
                score=score,
                explanation=f"Access frequency score: {frequency_score:.3f}"
            ))
        
        # Sort by frequency (descending)
        ranked_items.sort(key=lambda x: x.score.total_score, reverse=True)
        
        # Assign ranks
        for i, ranked_item in enumerate(ranked_items):
            ranked_item.rank = i + 1
        
        return ranked_items
    
    def _calculate_frequency_score(self, item: MemoryItem) -> float:
        """Calculate access frequency score."""
        access_count = self._get_access_count(item)
        if access_count is None or access_count == 0:
            return 0.0
        
        if not self.normalize_by_age:
            return float(access_count)
        
        # Get item age for normalization
        item_age = self._get_item_age_days(item)
        if item_age is None or item_age <= 0:
            return float(access_count)
        
        # Calculate accesses per day
        frequency = access_count / max(1.0, item_age)
        return frequency
    
    def _get_access_count(self, item: MemoryItem) -> Optional[int]:
        """Get access count from memory item."""
        # Try direct field access
        for field in [self.access_field, 'access_count', 'hits', 'views', 'visits']:
            if hasattr(item, field):
                value = getattr(item, field)
                if value is not None:
                    try:
                        return int(value)
                    except (ValueError, TypeError):
                        continue
        
        # Try metadata
        if hasattr(item, 'metadata') and isinstance(item.metadata, dict):
            for field in ['access_count', 'hits', 'views', 'visits']:
                value = item.metadata.get(field)
                if value is not None:
                    try:
                        return int(value)
                    except (ValueError, TypeError):
                        continue
        
        return None
    
    def _get_item_age_days(self, item: MemoryItem) -> Optional[float]:
        """Get item age in days."""
        current_time = time.time()
        
        # Try timestamp fields
        for field in ['created_at', 'timestamp', 'date', 'time']:
            if hasattr(item, field):
                value = getattr(item, field)
                if value is not None:
                    try:
                        if isinstance(value, (int, float)):
                            age_seconds = current_time - float(value)
                            return age_seconds / 86400.0
                        elif hasattr(value, 'timestamp'):
                            age_seconds = current_time - value.timestamp()
                            return age_seconds / 86400.0
                    except (ValueError, TypeError):
                        continue
        
        return None


class CompositeRanker(BaseRanker):
    """Combine multiple ranking algorithms with weights."""
    
    def __init__(self, rankers: Dict[str, BaseRanker],
                 weights: Dict[str, float],
                 normalization: str = "minmax"):
        """Initialize composite ranker.
        
        Args:
            rankers: Dictionary of named rankers
            weights: Weights for each ranker (should sum to 1.0)
            normalization: Score normalization method ("minmax", "zscore", "none")
        """
        self.rankers = rankers
        self.weights = weights
        self.normalization = normalization
        
        # Normalize weights to sum to 1.0
        total_weight = sum(weights.values())
        if total_weight > 0:
            self.weights = {k: v / total_weight for k, v in weights.items()}
    
    async def rank(self, items: List[MemoryItem], context: QueryContext) -> List[RankedItem]:
        """Rank items using composite scoring."""
        if not items:
            return []
        
        # Get rankings from all rankers
        ranker_results = {}
        for name, ranker in self.rankers.items():
            if name in self.weights:
                ranker_results[name] = await ranker.rank(items, context)
        
        # Extract scores for normalization
        all_scores = {}
        for name, ranked_items in ranker_results.items():
            scores = [ri.score.total_score for ri in ranked_items]
            all_scores[name] = self._normalize_scores(scores)
        
        # Calculate composite scores
        composite_items = []
        for i, item in enumerate(items):
            total_score = 0.0
            score_components = {}
            explanations = []
            
            # Aggregate scores from all rankers
            for name, weight in self.weights.items():
                if name in all_scores and i < len(all_scores[name]):
                    ranker_score = all_scores[name][i]
                    weighted_score = ranker_score * weight
                    total_score += weighted_score
                    score_components[name] = ranker_score
                    explanations.append(f"{name}: {ranker_score:.3f} (×{weight:.2f})")
            
            # Create composite score
            composite_score = RankingScore(total_score=total_score)
            
            # Set individual score components
            if 'relevance' in score_components:
                composite_score.relevance_score = score_components['relevance']
            if 'importance' in score_components:
                composite_score.importance_score = score_components['importance']
            if 'recency' in score_components:
                composite_score.recency_score = score_components['recency']
            if 'frequency' in score_components:
                composite_score.frequency_score = score_components['frequency']
            
            # Add custom scores
            for name, score in score_components.items():
                if name not in ['relevance', 'importance', 'recency', 'frequency']:
                    composite_score.custom_scores[name] = score
            
            composite_items.append(RankedItem(
                item=item,
                score=composite_score,
                explanation=f"Composite: {total_score:.3f} = " + " + ".join(explanations)
            ))
        
        # Sort by composite score (descending)
        composite_items.sort(key=lambda x: x.score.total_score, reverse=True)
        
        # Assign ranks
        for i, ranked_item in enumerate(composite_items):
            ranked_item.rank = i + 1
        
        return composite_items
    
    def _normalize_scores(self, scores: List[float]) -> List[float]:
        """Normalize scores using specified method."""
        if not scores or self.normalization == "none":
            return scores
        
        if self.normalization == "minmax":
            min_score = min(scores)
            max_score = max(scores)
            if max_score > min_score:
                return [(s - min_score) / (max_score - min_score) for s in scores]
            else:
                return [1.0] * len(scores)
        
        elif self.normalization == "zscore":
            if len(scores) > 1:
                mean_score = statistics.mean(scores)
                std_score = statistics.stdev(scores)
                if std_score > 0:
                    normalized = [(s - mean_score) / std_score for s in scores]
                    # Convert to 0-1 range using sigmoid
                    return [1.0 / (1.0 + math.exp(-s)) for s in normalized]
            return [0.5] * len(scores)
        
        return scores


class RankingEngine:
    """Main ranking engine that coordinates different ranking algorithms."""
    
    def __init__(self):
        """Initialize ranking engine."""
        self.rankers: Dict[str, BaseRanker] = {}
        self.default_ranker = "composite"
        self._ranking_stats: Dict[str, Dict[str, Any]] = {}
        
        # Register default rankers
        self._register_default_rankers()
    
    def _register_default_rankers(self) -> None:
        """Register default ranking algorithms."""
        # Individual rankers
        self.register_ranker("relevance", RelevanceRanker())
        self.register_ranker("importance", ImportanceRanker())
        self.register_ranker("recency", RecencyRanker())
        self.register_ranker("frequency", AccessFrequencyRanker())
        
        # Composite ranker with balanced weights
        composite_rankers = {
            "relevance": RelevanceRanker(),
            "importance": ImportanceRanker(),
            "recency": RecencyRanker(decay_days=7.0),  # Shorter decay for composite
            "frequency": AccessFrequencyRanker()
        }
        composite_weights = {
            "relevance": 0.4,
            "importance": 0.3,
            "recency": 0.2,
            "frequency": 0.1
        }
        
        self.register_ranker("composite", CompositeRanker(
            rankers=composite_rankers,
            weights=composite_weights
        ))
    
    def register_ranker(self, name: str, ranker: BaseRanker) -> None:
        """Register a named ranker.
        
        Args:
            name: Ranker name
            ranker: Ranker implementation
        """
        self.rankers[name] = ranker
        self._ranking_stats[name] = {
            'applications': 0,
            'total_time': 0.0,
            'items_ranked': 0
        }
    
    def get_ranker(self, name: str) -> Optional[BaseRanker]:
        """Get a registered ranker by name.
        
        Args:
            name: Ranker name
            
        Returns:
            Ranker object or None
        """
        return self.rankers.get(name)
    
    def list_rankers(self) -> List[str]:
        """Get list of registered ranker names."""
        return list(self.rankers.keys())
    
    async def rank_items(self, items: List[MemoryItem], context: QueryContext,
                        method: str = None, limit: Optional[int] = None) -> List[RankedItem]:
        """Rank memory items using specified method.
        
        Args:
            items: Memory items to rank
            context: Query execution context
            method: Ranking method to use (default: self.default_ranker)
            limit: Maximum number of items to return
            
        Returns:
            List of ranked items
        """
        if not items:
            return []
        
        # Use default ranker if not specified
        ranker_name = method or self.default_ranker
        ranker = self.get_ranker(ranker_name)
        
        if not ranker:
            # Fallback to first available ranker
            if self.rankers:
                ranker_name = next(iter(self.rankers.keys()))
                ranker = self.rankers[ranker_name]
            else:
                # No rankers available - return items with default scores
                return [
                    RankedItem(
                        item=item,
                        score=RankingScore(total_score=0.5),
                        rank=i + 1,
                        explanation="No rankers available"
                    )
                    for i, item in enumerate(items[:limit] if limit else items)
                ]
        
        # Apply ranking with statistics tracking
        start_time = time.time()
        
        try:
            ranked_items = await ranker.rank(items, context)
            
            # Apply limit if specified
            if limit and len(ranked_items) > limit:
                ranked_items = ranked_items[:limit]
                # Update ranks after truncation
                for i, item in enumerate(ranked_items):
                    item.rank = i + 1
            
            # Update statistics
            execution_time = time.time() - start_time
            self._update_ranking_stats(ranker_name, execution_time, len(items))
            
            return ranked_items
            
        except Exception as e:
            # Return items with default scores on error
            execution_time = time.time() - start_time
            self._update_ranking_stats(ranker_name, execution_time, len(items))
            
            return [
                RankedItem(
                    item=item,
                    score=RankingScore(total_score=0.5),
                    rank=i + 1,
                    explanation=f"Ranking error: {str(e)}"
                )
                for i, item in enumerate(items[:limit] if limit else items)
            ]
    
    def _update_ranking_stats(self, ranker_name: str, execution_time: float,
                            item_count: int) -> None:
        """Update ranking statistics."""
        if ranker_name in self._ranking_stats:
            stats = self._ranking_stats[ranker_name]
            stats['applications'] += 1
            stats['total_time'] += execution_time
            stats['items_ranked'] += item_count
    
    def get_ranking_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all registered rankers."""
        return self._ranking_stats.copy()
    
    def set_default_ranker(self, name: str) -> bool:
        """Set the default ranking method.
        
        Args:
            name: Name of ranker to use as default
            
        Returns:
            True if ranker exists and was set as default
        """
        if name in self.rankers:
            self.default_ranker = name
            return True
        return False