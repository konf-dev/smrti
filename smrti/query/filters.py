"""
smrti/query/filters.py - Advanced Filtering System

Comprehensive filtering capabilities for importance, complexity, access frequency,
memory tiers, labels, and composite filtering logic.
"""

from __future__ import annotations

import time
import statistics
from typing import Dict, List, Optional, Any, Union, Tuple, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import re

from ..models.base import MemoryItem
from .engine import QueryContext, QueryStats


class FilterOperator(Enum):
    """Logical operators for combining filters."""
    
    AND = "and"
    OR = "or" 
    NOT = "not"
    XOR = "xor"


class ComparisonOperator(Enum):
    """Comparison operators for filter conditions."""
    
    EQUALS = "eq"
    NOT_EQUALS = "ne"
    GREATER_THAN = "gt"
    GREATER_EQUAL = "ge"
    LESS_THAN = "lt"
    LESS_EQUAL = "le"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    MATCHES = "matches"  # Regex matching
    IN = "in"
    NOT_IN = "not_in"


@dataclass
class FilterCondition:
    """A single filter condition."""
    
    field: str
    operator: ComparisonOperator
    value: Any
    case_sensitive: bool = False
    
    def matches(self, item: MemoryItem) -> bool:
        """Check if item matches this condition.
        
        Args:
            item: Memory item to check
            
        Returns:
            True if item matches the condition
        """
        item_value = self._extract_field_value(item, self.field)
        
        if item_value is None:
            return self.operator == ComparisonOperator.NOT_EQUALS
        
        return self._compare_values(item_value, self.value, self.operator)
    
    def _extract_field_value(self, item: MemoryItem, field: str) -> Any:
        """Extract field value from memory item."""
        # Direct attribute access
        if hasattr(item, field):
            return getattr(item, field)
        
        # Metadata access
        if hasattr(item, 'metadata') and isinstance(item.metadata, dict):
            if field in item.metadata:
                return item.metadata[field]
        
        # Nested field access (e.g., "metadata.importance")
        if '.' in field:
            parts = field.split('.')
            current = item
            for part in parts:
                if hasattr(current, part):
                    current = getattr(current, part)
                elif isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return None
            return current
        
        return None
    
    def _compare_values(self, item_value: Any, filter_value: Any, 
                       operator: ComparisonOperator) -> bool:
        """Compare values using the specified operator."""
        try:
            if operator == ComparisonOperator.EQUALS:
                return self._equals_comparison(item_value, filter_value)
            elif operator == ComparisonOperator.NOT_EQUALS:
                return not self._equals_comparison(item_value, filter_value)
            elif operator == ComparisonOperator.GREATER_THAN:
                return self._numeric_comparison(item_value, filter_value, lambda a, b: a > b)
            elif operator == ComparisonOperator.GREATER_EQUAL:
                return self._numeric_comparison(item_value, filter_value, lambda a, b: a >= b)
            elif operator == ComparisonOperator.LESS_THAN:
                return self._numeric_comparison(item_value, filter_value, lambda a, b: a < b)
            elif operator == ComparisonOperator.LESS_EQUAL:
                return self._numeric_comparison(item_value, filter_value, lambda a, b: a <= b)
            elif operator == ComparisonOperator.CONTAINS:
                return self._contains_comparison(item_value, filter_value)
            elif operator == ComparisonOperator.NOT_CONTAINS:
                return not self._contains_comparison(item_value, filter_value)
            elif operator == ComparisonOperator.STARTS_WITH:
                return self._starts_with_comparison(item_value, filter_value)
            elif operator == ComparisonOperator.ENDS_WITH:
                return self._ends_with_comparison(item_value, filter_value)
            elif operator == ComparisonOperator.MATCHES:
                return self._regex_comparison(item_value, filter_value)
            elif operator == ComparisonOperator.IN:
                return self._in_comparison(item_value, filter_value)
            elif operator == ComparisonOperator.NOT_IN:
                return not self._in_comparison(item_value, filter_value)
        except Exception:
            return False
        
        return False
    
    def _equals_comparison(self, item_value: Any, filter_value: Any) -> bool:
        """Perform equality comparison."""
        if isinstance(item_value, str) and isinstance(filter_value, str):
            if not self.case_sensitive:
                return item_value.lower() == filter_value.lower()
        return item_value == filter_value
    
    def _numeric_comparison(self, item_value: Any, filter_value: Any, 
                           comparator: Callable[[float, float], bool]) -> bool:
        """Perform numeric comparison."""
        try:
            item_num = float(item_value)
            filter_num = float(filter_value)
            return comparator(item_num, filter_num)
        except (ValueError, TypeError):
            return False
    
    def _contains_comparison(self, item_value: Any, filter_value: Any) -> bool:
        """Perform contains comparison."""
        item_str = str(item_value)
        filter_str = str(filter_value)
        
        if not self.case_sensitive:
            item_str = item_str.lower()
            filter_str = filter_str.lower()
        
        return filter_str in item_str
    
    def _starts_with_comparison(self, item_value: Any, filter_value: Any) -> bool:
        """Perform starts with comparison."""
        item_str = str(item_value)
        filter_str = str(filter_value)
        
        if not self.case_sensitive:
            item_str = item_str.lower()
            filter_str = filter_str.lower()
        
        return item_str.startswith(filter_str)
    
    def _ends_with_comparison(self, item_value: Any, filter_value: Any) -> bool:
        """Perform ends with comparison."""
        item_str = str(item_value)
        filter_str = str(filter_value)
        
        if not self.case_sensitive:
            item_str = item_str.lower()
            filter_str = filter_str.lower()
        
        return item_str.endswith(filter_str)
    
    def _regex_comparison(self, item_value: Any, filter_value: Any) -> bool:
        """Perform regex comparison."""
        item_str = str(item_value)
        pattern = str(filter_value)
        
        flags = 0 if self.case_sensitive else re.IGNORECASE
        
        try:
            return bool(re.search(pattern, item_str, flags))
        except re.error:
            return False
    
    def _in_comparison(self, item_value: Any, filter_value: Any) -> bool:
        """Perform 'in' comparison."""
        if not isinstance(filter_value, (list, tuple, set)):
            return False
        
        if isinstance(item_value, str) and not self.case_sensitive:
            item_lower = item_value.lower()
            return any(
                item_lower == str(val).lower() 
                for val in filter_value
            )
        
        return item_value in filter_value


class BaseFilter(ABC):
    """Abstract base class for all filters."""
    
    @abstractmethod
    async def apply(self, items: List[MemoryItem], context: QueryContext) -> List[MemoryItem]:
        """Apply the filter to a list of memory items.
        
        Args:
            items: Input memory items
            context: Query execution context
            
        Returns:
            Filtered memory items
        """
        pass
    
    def should_apply(self, query_ast: Any) -> bool:
        """Check if this filter should be applied based on query AST.
        
        Args:
            query_ast: Parsed query AST
            
        Returns:
            True if filter should be applied
        """
        # Default implementation - always apply
        return True


class ImportanceFilter(BaseFilter):
    """Filter by memory item importance score."""
    
    def __init__(self, min_importance: Optional[float] = None,
                 max_importance: Optional[float] = None,
                 importance_field: str = "importance"):
        """Initialize importance filter.
        
        Args:
            min_importance: Minimum importance threshold
            max_importance: Maximum importance threshold
            importance_field: Field name containing importance score
        """
        self.min_importance = min_importance
        self.max_importance = max_importance
        self.importance_field = importance_field
    
    async def apply(self, items: List[MemoryItem], context: QueryContext) -> List[MemoryItem]:
        """Apply importance filtering."""
        if self.min_importance is None and self.max_importance is None:
            return items
        
        filtered_items = []
        for item in items:
            importance = self._get_importance(item)
            
            if importance is None:
                # Include items with no importance if we have no minimum
                if self.min_importance is None:
                    filtered_items.append(item)
                continue
            
            # Apply thresholds
            if self.min_importance is not None and importance < self.min_importance:
                continue
            
            if self.max_importance is not None and importance > self.max_importance:
                continue
            
            filtered_items.append(item)
        
        return filtered_items
    
    def _get_importance(self, item: MemoryItem) -> Optional[float]:
        """Extract importance score from memory item."""
        if hasattr(item, self.importance_field):
            value = getattr(item, self.importance_field)
            try:
                return float(value)
            except (ValueError, TypeError):
                return None
        
        # Check metadata
        if hasattr(item, 'metadata') and isinstance(item.metadata, dict):
            value = item.metadata.get(self.importance_field)
            if value is not None:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return None
        
        return None


class ComplexityFilter(BaseFilter):
    """Filter by content complexity metrics."""
    
    def __init__(self, min_complexity: Optional[float] = None,
                 max_complexity: Optional[float] = None,
                 complexity_metric: str = "length"):
        """Initialize complexity filter.
        
        Args:
            min_complexity: Minimum complexity threshold
            max_complexity: Maximum complexity threshold
            complexity_metric: Complexity metric to use ("length", "words", "sentences")
        """
        self.min_complexity = min_complexity
        self.max_complexity = max_complexity
        self.complexity_metric = complexity_metric
    
    async def apply(self, items: List[MemoryItem], context: QueryContext) -> List[MemoryItem]:
        """Apply complexity filtering."""
        if self.min_complexity is None and self.max_complexity is None:
            return items
        
        filtered_items = []
        for item in items:
            complexity = self._calculate_complexity(item)
            
            if complexity is None:
                # Include items we can't measure if no minimum
                if self.min_complexity is None:
                    filtered_items.append(item)
                continue
            
            # Apply thresholds
            if self.min_complexity is not None and complexity < self.min_complexity:
                continue
            
            if self.max_complexity is not None and complexity > self.max_complexity:
                continue
            
            filtered_items.append(item)
        
        return filtered_items
    
    def _calculate_complexity(self, item: MemoryItem) -> Optional[float]:
        """Calculate complexity metric for memory item."""
        content = self._extract_content(item)
        if not content:
            return None
        
        if self.complexity_metric == "length":
            return float(len(content))
        elif self.complexity_metric == "words":
            words = content.split()
            return float(len(words))
        elif self.complexity_metric == "sentences":
            # Simple sentence counting
            sentences = re.split(r'[.!?]+', content)
            return float(len([s for s in sentences if s.strip()]))
        else:
            return float(len(content))  # Default to length
    
    def _extract_content(self, item: MemoryItem) -> str:
        """Extract content from memory item."""
        if hasattr(item, 'content') and item.content:
            return str(item.content)
        
        # Try other common content fields
        for field in ['text', 'body', 'description', 'summary']:
            if hasattr(item, field):
                value = getattr(item, field)
                if value:
                    return str(value)
        
        return ""


class AccessFrequencyFilter(BaseFilter):
    """Filter by access frequency patterns."""
    
    def __init__(self, min_access_count: Optional[int] = None,
                 max_access_count: Optional[int] = None,
                 min_access_frequency: Optional[float] = None,
                 max_access_frequency: Optional[float] = None):
        """Initialize access frequency filter.
        
        Args:
            min_access_count: Minimum total access count
            max_access_count: Maximum total access count
            min_access_frequency: Minimum access frequency (accesses per day)
            max_access_frequency: Maximum access frequency (accesses per day)
        """
        self.min_access_count = min_access_count
        self.max_access_count = max_access_count
        self.min_access_frequency = min_access_frequency
        self.max_access_frequency = max_access_frequency
    
    async def apply(self, items: List[MemoryItem], context: QueryContext) -> List[MemoryItem]:
        """Apply access frequency filtering."""
        filtered_items = []
        
        for item in items:
            # Check access count
            if (self.min_access_count is not None or 
                self.max_access_count is not None):
                
                access_count = self._get_access_count(item)
                if access_count is not None:
                    if (self.min_access_count is not None and 
                        access_count < self.min_access_count):
                        continue
                    
                    if (self.max_access_count is not None and 
                        access_count > self.max_access_count):
                        continue
            
            # Check access frequency
            if (self.min_access_frequency is not None or 
                self.max_access_frequency is not None):
                
                frequency = self._calculate_access_frequency(item)
                if frequency is not None:
                    if (self.min_access_frequency is not None and 
                        frequency < self.min_access_frequency):
                        continue
                    
                    if (self.max_access_frequency is not None and 
                        frequency > self.max_access_frequency):
                        continue
            
            filtered_items.append(item)
        
        return filtered_items
    
    def _get_access_count(self, item: MemoryItem) -> Optional[int]:
        """Get access count from memory item."""
        for field in ['access_count', 'hits', 'views', 'visits']:
            if hasattr(item, field):
                try:
                    return int(getattr(item, field))
                except (ValueError, TypeError):
                    continue
            
            # Check metadata
            if hasattr(item, 'metadata') and isinstance(item.metadata, dict):
                value = item.metadata.get(field)
                if value is not None:
                    try:
                        return int(value)
                    except (ValueError, TypeError):
                        continue
        
        return None
    
    def _calculate_access_frequency(self, item: MemoryItem) -> Optional[float]:
        """Calculate access frequency (accesses per day)."""
        access_count = self._get_access_count(item)
        if access_count is None:
            return None
        
        # Get creation time to calculate age
        creation_time = None
        for field in ['created_at', 'timestamp', 'date_created']:
            if hasattr(item, field):
                creation_time = getattr(item, field)
                break
        
        if creation_time is None:
            return None
        
        # Calculate age in days
        try:
            if isinstance(creation_time, (int, float)):
                age_seconds = time.time() - creation_time
            else:
                # Assume datetime object
                age_seconds = (time.time() - creation_time.timestamp())
            
            age_days = max(1, age_seconds / 86400)  # At least 1 day
            return access_count / age_days
            
        except Exception:
            return None


class TierFilter(BaseFilter):
    """Filter by memory tier."""
    
    def __init__(self, allowed_tiers: List[str], 
                 tier_field: str = "tier"):
        """Initialize tier filter.
        
        Args:
            allowed_tiers: List of allowed tier names
            tier_field: Field name containing tier information
        """
        self.allowed_tiers = set(allowed_tiers)
        self.tier_field = tier_field
    
    async def apply(self, items: List[MemoryItem], context: QueryContext) -> List[MemoryItem]:
        """Apply tier filtering."""
        filtered_items = []
        
        for item in items:
            tier = self._get_tier(item)
            if tier is None or tier in self.allowed_tiers:
                filtered_items.append(item)
        
        return filtered_items
    
    def _get_tier(self, item: MemoryItem) -> Optional[str]:
        """Get tier from memory item."""
        if hasattr(item, self.tier_field):
            return str(getattr(item, self.tier_field))
        
        # Check metadata
        if hasattr(item, 'metadata') and isinstance(item.metadata, dict):
            value = item.metadata.get(self.tier_field)
            if value is not None:
                return str(value)
        
        return None


class LabelFilter(BaseFilter):
    """Filter by labels/tags."""
    
    def __init__(self, required_labels: Optional[List[str]] = None,
                 forbidden_labels: Optional[List[str]] = None,
                 label_field: str = "labels",
                 match_mode: str = "any"):
        """Initialize label filter.
        
        Args:
            required_labels: Labels that must be present
            forbidden_labels: Labels that must not be present
            label_field: Field name containing labels
            match_mode: "any" or "all" for required labels
        """
        self.required_labels = set(required_labels or [])
        self.forbidden_labels = set(forbidden_labels or [])
        self.label_field = label_field
        self.match_mode = match_mode
    
    async def apply(self, items: List[MemoryItem], context: QueryContext) -> List[MemoryItem]:
        """Apply label filtering."""
        filtered_items = []
        
        for item in items:
            item_labels = self._get_labels(item)
            
            # Check forbidden labels
            if self.forbidden_labels and item_labels:
                if self.forbidden_labels.intersection(item_labels):
                    continue
            
            # Check required labels
            if self.required_labels:
                if not item_labels:
                    continue
                
                if self.match_mode == "all":
                    if not self.required_labels.issubset(item_labels):
                        continue
                else:  # "any"
                    if not self.required_labels.intersection(item_labels):
                        continue
            
            filtered_items.append(item)
        
        return filtered_items
    
    def _get_labels(self, item: MemoryItem) -> Set[str]:
        """Get labels from memory item."""
        labels = set()
        
        # Try direct attribute access
        if hasattr(item, self.label_field):
            value = getattr(item, self.label_field)
            labels.update(self._parse_labels(value))
        
        # Try common label fields
        for field in ['labels', 'tags', 'categories']:
            if hasattr(item, field):
                value = getattr(item, field)
                labels.update(self._parse_labels(value))
        
        # Try metadata
        if hasattr(item, 'metadata') and isinstance(item.metadata, dict):
            for field in ['labels', 'tags', 'categories']:
                value = item.metadata.get(field)
                if value is not None:
                    labels.update(self._parse_labels(value))
        
        return labels
    
    def _parse_labels(self, value: Any) -> Set[str]:
        """Parse labels from various formats."""
        if isinstance(value, (list, tuple)):
            return {str(label).strip() for label in value}
        elif isinstance(value, str):
            # Split by common delimiters
            labels = re.split(r'[,;|\n\t]+', value)
            return {label.strip() for label in labels if label.strip()}
        elif isinstance(value, set):
            return {str(label) for label in value}
        else:
            return set()


class CompositeFilter(BaseFilter):
    """Combine multiple filters with logical operators."""
    
    def __init__(self, filters: List[BaseFilter], operator: FilterOperator = FilterOperator.AND):
        """Initialize composite filter.
        
        Args:
            filters: List of filters to combine
            operator: Logical operator to use
        """
        self.filters = filters
        self.operator = operator
    
    async def apply(self, items: List[MemoryItem], context: QueryContext) -> List[MemoryItem]:
        """Apply composite filtering."""
        if not self.filters:
            return items
        
        if self.operator == FilterOperator.AND:
            return await self._apply_and(items, context)
        elif self.operator == FilterOperator.OR:
            return await self._apply_or(items, context)
        elif self.operator == FilterOperator.NOT:
            return await self._apply_not(items, context)
        elif self.operator == FilterOperator.XOR:
            return await self._apply_xor(items, context)
        
        return items
    
    async def _apply_and(self, items: List[MemoryItem], context: QueryContext) -> List[MemoryItem]:
        """Apply AND logic (all filters must pass)."""
        current_items = items
        
        for filter_obj in self.filters:
            current_items = await filter_obj.apply(current_items, context)
            
            # Short-circuit if no items left
            if not current_items:
                break
        
        return current_items
    
    async def _apply_or(self, items: List[MemoryItem], context: QueryContext) -> List[MemoryItem]:
        """Apply OR logic (any filter must pass)."""
        all_results = set()
        
        for filter_obj in self.filters:
            filtered_items = await filter_obj.apply(items, context)
            
            # Add item IDs to results (assuming items have unique IDs)
            for item in filtered_items:
                item_id = getattr(item, 'id', id(item))
                all_results.add((item_id, item))
        
        # Return unique items
        return [item for _, item in all_results]
    
    async def _apply_not(self, items: List[MemoryItem], context: QueryContext) -> List[MemoryItem]:
        """Apply NOT logic (exclude items that pass first filter)."""
        if not self.filters:
            return items
        
        # Apply first filter and exclude those results
        filtered_items = await self.filters[0].apply(items, context)
        filtered_ids = {getattr(item, 'id', id(item)) for item in filtered_items}
        
        # Return items not in filtered results
        return [
            item for item in items
            if getattr(item, 'id', id(item)) not in filtered_ids
        ]
    
    async def _apply_xor(self, items: List[MemoryItem], context: QueryContext) -> List[MemoryItem]:
        """Apply XOR logic (exactly one filter must pass)."""
        if len(self.filters) != 2:
            # XOR only works with exactly 2 filters
            return items
        
        # Apply both filters
        results1 = await self.filters[0].apply(items, context)
        results2 = await self.filters[1].apply(items, context)
        
        # Get item IDs
        ids1 = {getattr(item, 'id', id(item)) for item in results1}
        ids2 = {getattr(item, 'id', id(item)) for item in results2}
        
        # XOR: items in one set but not both
        xor_ids = ids1.symmetric_difference(ids2)
        
        # Return items with XOR IDs
        result_items = []
        for item in items:
            item_id = getattr(item, 'id', id(item))
            if item_id in xor_ids:
                result_items.append(item)
        
        return result_items


class ConditionFilter(BaseFilter):
    """Filter using condition-based logic."""
    
    def __init__(self, conditions: List[FilterCondition], 
                 operator: FilterOperator = FilterOperator.AND):
        """Initialize condition filter.
        
        Args:
            conditions: List of filter conditions
            operator: Logical operator for combining conditions
        """
        self.conditions = conditions
        self.operator = operator
    
    async def apply(self, items: List[MemoryItem], context: QueryContext) -> List[MemoryItem]:
        """Apply condition-based filtering."""
        if not self.conditions:
            return items
        
        filtered_items = []
        
        for item in items:
            if self._item_matches_conditions(item):
                filtered_items.append(item)
        
        return filtered_items
    
    def _item_matches_conditions(self, item: MemoryItem) -> bool:
        """Check if item matches all conditions based on operator."""
        if not self.conditions:
            return True
        
        if self.operator == FilterOperator.AND:
            return all(condition.matches(item) for condition in self.conditions)
        elif self.operator == FilterOperator.OR:
            return any(condition.matches(item) for condition in self.conditions)
        elif self.operator == FilterOperator.NOT:
            # NOT of first condition
            return not self.conditions[0].matches(item)
        elif self.operator == FilterOperator.XOR:
            # XOR of all conditions
            match_count = sum(1 for condition in self.conditions if condition.matches(item))
            return match_count % 2 == 1
        
        return False


class FilterRegistry:
    """Registry for managing available filters."""
    
    def __init__(self):
        """Initialize filter registry."""
        self.filters: Dict[str, BaseFilter] = {}
        self._filter_stats: Dict[str, Dict[str, Any]] = {}
    
    def register_filter(self, name: str, filter_obj: BaseFilter) -> None:
        """Register a named filter.
        
        Args:
            name: Filter name
            filter_obj: Filter implementation
        """
        self.filters[name] = filter_obj
        self._filter_stats[name] = {
            'applications': 0,
            'total_time': 0.0,
            'items_filtered': 0
        }
    
    def get_filter(self, name: str) -> Optional[BaseFilter]:
        """Get a registered filter by name.
        
        Args:
            name: Filter name
            
        Returns:
            Filter object or None
        """
        return self.filters.get(name)
    
    def list_filters(self) -> List[str]:
        """Get list of registered filter names."""
        return list(self.filters.keys())
    
    async def apply_filter(self, name: str, items: List[MemoryItem], 
                          context: QueryContext) -> List[MemoryItem]:
        """Apply a named filter with statistics tracking.
        
        Args:
            name: Filter name
            items: Input memory items
            context: Query execution context
            
        Returns:
            Filtered memory items
        """
        filter_obj = self.get_filter(name)
        if not filter_obj:
            return items
        
        start_time = time.time()
        input_count = len(items)
        
        try:
            result_items = await filter_obj.apply(items, context)
            
            # Update statistics
            execution_time = time.time() - start_time
            self._update_filter_stats(name, execution_time, input_count, len(result_items))
            
            return result_items
            
        except Exception as e:
            # Return original items on error
            execution_time = time.time() - start_time
            self._update_filter_stats(name, execution_time, input_count, input_count)
            return items
    
    def _update_filter_stats(self, name: str, execution_time: float,
                           input_count: int, output_count: int) -> None:
        """Update filter statistics."""
        if name in self._filter_stats:
            stats = self._filter_stats[name]
            stats['applications'] += 1
            stats['total_time'] += execution_time
            stats['items_filtered'] += (input_count - output_count)
    
    def get_filter_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all registered filters."""
        return self._filter_stats.copy()