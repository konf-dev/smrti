"""
smrti/query/temporal.py - Temporal Query Filtering

Advanced time-based filtering for memory items including absolute dates,
relative time periods, and complex temporal logic.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Union, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import re

from ..models.base import MemoryItem
from .engine import QueryContext, QueryStats


class TemporalOperator(Enum):
    """Temporal comparison operators."""
    
    BEFORE = "before"
    AFTER = "after"
    BETWEEN = "between"
    DURING = "during"
    SINCE = "since"
    UNTIL = "until"
    EXACTLY = "exactly"
    WITHIN = "within"
    AGO = "ago"


class RelativeTime(Enum):
    """Relative time units."""
    
    SECONDS = "seconds"
    MINUTES = "minutes" 
    HOURS = "hours"
    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"
    YEARS = "years"


@dataclass
class TimeRange:
    """Represents a time range for filtering."""
    
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    # Relative time specification
    relative_amount: Optional[int] = None
    relative_unit: Optional[RelativeTime] = None
    relative_from: Optional[datetime] = None  # Default is now
    
    # Special time references
    is_open_ended: bool = False
    include_future: bool = False
    
    def __post_init__(self):
        """Process relative time specifications."""
        if self.relative_amount is not None and self.relative_unit is not None:
            self._calculate_relative_range()
    
    def _calculate_relative_range(self) -> None:
        """Calculate absolute time range from relative specification."""
        if self.relative_from is None:
            self.relative_from = datetime.now(timezone.utc)
        
        # Calculate time delta
        if self.relative_unit == RelativeTime.SECONDS:
            delta = timedelta(seconds=self.relative_amount)
        elif self.relative_unit == RelativeTime.MINUTES:
            delta = timedelta(minutes=self.relative_amount)
        elif self.relative_unit == RelativeTime.HOURS:
            delta = timedelta(hours=self.relative_amount)
        elif self.relative_unit == RelativeTime.DAYS:
            delta = timedelta(days=self.relative_amount)
        elif self.relative_unit == RelativeTime.WEEKS:
            delta = timedelta(weeks=self.relative_amount)
        elif self.relative_unit == RelativeTime.MONTHS:
            delta = timedelta(days=self.relative_amount * 30)  # Approximate
        elif self.relative_unit == RelativeTime.YEARS:
            delta = timedelta(days=self.relative_amount * 365)  # Approximate
        else:
            delta = timedelta(0)
        
        # Set range based on relative specification
        if self.start_time is None:
            self.start_time = self.relative_from - delta
        if self.end_time is None:
            self.end_time = self.relative_from
    
    def contains(self, timestamp: datetime) -> bool:
        """Check if timestamp falls within this range.
        
        Args:
            timestamp: Timestamp to check
            
        Returns:
            True if timestamp is within range
        """
        if self.start_time and timestamp < self.start_time:
            return False
        
        if self.end_time and timestamp > self.end_time:
            return False
        
        return True
    
    def overlaps(self, other: TimeRange) -> bool:
        """Check if this range overlaps with another.
        
        Args:
            other: Another time range
            
        Returns:
            True if ranges overlap
        """
        if self.start_time and other.end_time and self.start_time > other.end_time:
            return False
        
        if self.end_time and other.start_time and self.end_time < other.start_time:
            return False
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert time range to dictionary."""
        return {
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'relative': {
                'amount': self.relative_amount,
                'unit': self.relative_unit.value if self.relative_unit else None,
                'from': self.relative_from.isoformat() if self.relative_from else None
            },
            'flags': {
                'is_open_ended': self.is_open_ended,
                'include_future': self.include_future
            }
        }


@dataclass
class TemporalQuery:
    """Temporal query specification."""
    
    operator: TemporalOperator
    time_range: TimeRange
    
    # Field specifications
    timestamp_field: str = "created_at"  # Field to compare against
    secondary_fields: List[str] = field(default_factory=list)  # Additional time fields
    
    # Matching options
    strict_matching: bool = True  # Require exact field match
    fuzzy_matching: bool = False  # Allow approximate matches
    
    # Timezone handling
    default_timezone: timezone = timezone.utc
    assume_local_time: bool = False
    
    def matches_item(self, item: MemoryItem) -> bool:
        """Check if an item matches this temporal query.
        
        Args:
            item: Memory item to check
            
        Returns:
            True if item matches the temporal criteria
        """
        # Extract timestamp from item
        item_timestamp = self._extract_timestamp(item)
        if item_timestamp is None:
            return not self.strict_matching
        
        # Apply operator-specific logic
        if self.operator == TemporalOperator.BEFORE:
            return self._check_before(item_timestamp)
        elif self.operator == TemporalOperator.AFTER:
            return self._check_after(item_timestamp)
        elif self.operator == TemporalOperator.BETWEEN:
            return self._check_between(item_timestamp)
        elif self.operator == TemporalOperator.DURING:
            return self._check_during(item_timestamp)
        elif self.operator == TemporalOperator.SINCE:
            return self._check_since(item_timestamp)
        elif self.operator == TemporalOperator.UNTIL:
            return self._check_until(item_timestamp)
        elif self.operator == TemporalOperator.EXACTLY:
            return self._check_exactly(item_timestamp)
        elif self.operator == TemporalOperator.WITHIN:
            return self._check_within(item_timestamp)
        elif self.operator == TemporalOperator.AGO:
            return self._check_ago(item_timestamp)
        
        return False
    
    def _extract_timestamp(self, item: MemoryItem) -> Optional[datetime]:
        """Extract timestamp from memory item.
        
        Args:
            item: Memory item
            
        Returns:
            Extracted timestamp or None
        """
        # Try primary timestamp field
        timestamp = self._get_field_value(item, self.timestamp_field)
        if timestamp:
            return self._parse_timestamp(timestamp)
        
        # Try secondary fields
        for field_name in self.secondary_fields:
            timestamp = self._get_field_value(item, field_name)
            if timestamp:
                return self._parse_timestamp(timestamp)
        
        # Try common timestamp fields
        common_fields = [
            'timestamp', 'created_at', 'updated_at', 'modified_at',
            'date_created', 'date_modified', 'last_accessed'
        ]
        
        for field_name in common_fields:
            timestamp = self._get_field_value(item, field_name)
            if timestamp:
                return self._parse_timestamp(timestamp)
        
        return None
    
    def _get_field_value(self, item: MemoryItem, field_name: str) -> Any:
        """Get field value from memory item.
        
        Args:
            item: Memory item
            field_name: Field name to extract
            
        Returns:
            Field value or None
        """
        # Direct attribute access
        if hasattr(item, field_name):
            return getattr(item, field_name)
        
        # Metadata access
        if hasattr(item, 'metadata') and isinstance(item.metadata, dict):
            return item.metadata.get(field_name)
        
        # Try nested field access (e.g., "metadata.created_at")
        if '.' in field_name:
            parts = field_name.split('.')
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
    
    def _parse_timestamp(self, value: Any) -> Optional[datetime]:
        """Parse various timestamp formats.
        
        Args:
            value: Timestamp value to parse
            
        Returns:
            Parsed datetime or None
        """
        if isinstance(value, datetime):
            return value
        
        if isinstance(value, (int, float)):
            # Assume Unix timestamp
            try:
                return datetime.fromtimestamp(value, tz=self.default_timezone)
            except (ValueError, OSError):
                return None
        
        if isinstance(value, str):
            # Try various string formats
            formats = [
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%dT%H:%M:%SZ',
                '%Y-%m-%dT%H:%M:%S.%f',
                '%Y-%m-%dT%H:%M:%S.%fZ',
                '%Y-%m-%d',
                '%m/%d/%Y',
                '%m/%d/%Y %H:%M:%S'
            ]
            
            for fmt in formats:
                try:
                    dt = datetime.strptime(value, fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=self.default_timezone)
                    return dt
                except ValueError:
                    continue
        
        return None
    
    def _check_before(self, timestamp: datetime) -> bool:
        """Check BEFORE operator."""
        if self.time_range.end_time:
            return timestamp < self.time_range.end_time
        return False
    
    def _check_after(self, timestamp: datetime) -> bool:
        """Check AFTER operator."""
        if self.time_range.start_time:
            return timestamp > self.time_range.start_time
        return False
    
    def _check_between(self, timestamp: datetime) -> bool:
        """Check BETWEEN operator."""
        return self.time_range.contains(timestamp)
    
    def _check_during(self, timestamp: datetime) -> bool:
        """Check DURING operator (same as BETWEEN)."""
        return self._check_between(timestamp)
    
    def _check_since(self, timestamp: datetime) -> bool:
        """Check SINCE operator (same as AFTER)."""
        return self._check_after(timestamp)
    
    def _check_until(self, timestamp: datetime) -> bool:
        """Check UNTIL operator (same as BEFORE)."""
        return self._check_before(timestamp)
    
    def _check_exactly(self, timestamp: datetime) -> bool:
        """Check EXACTLY operator."""
        if self.time_range.start_time and self.time_range.end_time:
            # Allow some tolerance for exact matches
            tolerance = timedelta(seconds=1)
            target = self.time_range.start_time
            return abs(timestamp - target) <= tolerance
        return False
    
    def _check_within(self, timestamp: datetime) -> bool:
        """Check WITHIN operator."""
        now = datetime.now(timezone.utc)
        if self.time_range.relative_amount and self.time_range.relative_unit:
            # Create range from now backward
            range_copy = TimeRange(
                relative_amount=self.time_range.relative_amount,
                relative_unit=self.time_range.relative_unit,
                relative_from=now
            )
            return range_copy.contains(timestamp)
        return False
    
    def _check_ago(self, timestamp: datetime) -> bool:
        """Check AGO operator."""
        return self._check_within(timestamp)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert temporal query to dictionary."""
        return {
            'operator': self.operator.value,
            'time_range': self.time_range.to_dict(),
            'fields': {
                'primary': self.timestamp_field,
                'secondary': self.secondary_fields
            },
            'options': {
                'strict_matching': self.strict_matching,
                'fuzzy_matching': self.fuzzy_matching,
                'default_timezone': str(self.default_timezone),
                'assume_local_time': self.assume_local_time
            }
        }


class TemporalQueryParser:
    """Parser for natural language temporal expressions."""
    
    def __init__(self):
        """Initialize the temporal query parser."""
        self._relative_patterns = {
            r'(\d+)\s*(second|seconds|sec|secs?)\s*ago': (RelativeTime.SECONDS, TemporalOperator.AGO),
            r'(\d+)\s*(minute|minutes|min|mins?)\s*ago': (RelativeTime.MINUTES, TemporalOperator.AGO),
            r'(\d+)\s*(hour|hours|hr|hrs?)\s*ago': (RelativeTime.HOURS, TemporalOperator.AGO),
            r'(\d+)\s*(day|days)\s*ago': (RelativeTime.DAYS, TemporalOperator.AGO),
            r'(\d+)\s*(week|weeks)\s*ago': (RelativeTime.WEEKS, TemporalOperator.AGO),
            r'(\d+)\s*(month|months)\s*ago': (RelativeTime.MONTHS, TemporalOperator.AGO),
            r'(\d+)\s*(year|years)\s*ago': (RelativeTime.YEARS, TemporalOperator.AGO),
            
            r'last\s*(\d+)\s*(second|seconds|sec|secs?)': (RelativeTime.SECONDS, TemporalOperator.WITHIN),
            r'last\s*(\d+)\s*(minute|minutes|min|mins?)': (RelativeTime.MINUTES, TemporalOperator.WITHIN),
            r'last\s*(\d+)\s*(hour|hours|hr|hrs?)': (RelativeTime.HOURS, TemporalOperator.WITHIN),
            r'last\s*(\d+)\s*(day|days)': (RelativeTime.DAYS, TemporalOperator.WITHIN),
            r'last\s*(\d+)\s*(week|weeks)': (RelativeTime.WEEKS, TemporalOperator.WITHIN),
            r'last\s*(\d+)\s*(month|months)': (RelativeTime.MONTHS, TemporalOperator.WITHIN),
            r'last\s*(\d+)\s*(year|years)': (RelativeTime.YEARS, TemporalOperator.WITHIN),
        }
        
        self._absolute_patterns = {
            r'before\s+(\d{4}-\d{2}-\d{2})': TemporalOperator.BEFORE,
            r'after\s+(\d{4}-\d{2}-\d{2})': TemporalOperator.AFTER,
            r'on\s+(\d{4}-\d{2}-\d{2})': TemporalOperator.EXACTLY,
            r'since\s+(\d{4}-\d{2}-\d{2})': TemporalOperator.SINCE,
            r'until\s+(\d{4}-\d{2}-\d{2})': TemporalOperator.UNTIL,
        }
        
        self._special_expressions = {
            'today': self._parse_today,
            'yesterday': self._parse_yesterday,
            'this week': self._parse_this_week,
            'last week': self._parse_last_week,
            'this month': self._parse_this_month,
            'last month': self._parse_last_month,
            'this year': self._parse_this_year,
            'last year': self._parse_last_year,
        }
    
    def parse(self, expression: str) -> Optional[TemporalQuery]:
        """Parse a temporal expression into a query.
        
        Args:
            expression: Natural language temporal expression
            
        Returns:
            Parsed temporal query or None
        """
        expression = expression.lower().strip()
        
        # Try special expressions first
        for pattern, parser in self._special_expressions.items():
            if pattern in expression:
                return parser()
        
        # Try relative patterns
        for pattern, (unit, operator) in self._relative_patterns.items():
            match = re.search(pattern, expression, re.IGNORECASE)
            if match:
                amount = int(match.group(1))
                return TemporalQuery(
                    operator=operator,
                    time_range=TimeRange(
                        relative_amount=amount,
                        relative_unit=unit
                    )
                )
        
        # Try absolute patterns
        for pattern, operator in self._absolute_patterns.items():
            match = re.search(pattern, expression, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    date_obj = date_obj.replace(tzinfo=timezone.utc)
                    
                    if operator == TemporalOperator.EXACTLY:
                        # For exact dates, use the whole day
                        start_time = date_obj
                        end_time = date_obj + timedelta(days=1)
                        time_range = TimeRange(start_time=start_time, end_time=end_time)
                    elif operator in (TemporalOperator.BEFORE, TemporalOperator.UNTIL):
                        time_range = TimeRange(end_time=date_obj)
                    else:  # AFTER, SINCE
                        time_range = TimeRange(start_time=date_obj)
                    
                    return TemporalQuery(operator=operator, time_range=time_range)
                except ValueError:
                    continue
        
        return None
    
    def _parse_today(self) -> TemporalQuery:
        """Parse 'today' expression."""
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        
        return TemporalQuery(
            operator=TemporalOperator.BETWEEN,
            time_range=TimeRange(start_time=start_of_day, end_time=end_of_day)
        )
    
    def _parse_yesterday(self) -> TemporalQuery:
        """Parse 'yesterday' expression."""
        now = datetime.now(timezone.utc)
        start_of_yesterday = (now - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_of_yesterday = start_of_yesterday + timedelta(days=1)
        
        return TemporalQuery(
            operator=TemporalOperator.BETWEEN,
            time_range=TimeRange(start_time=start_of_yesterday, end_time=end_of_yesterday)
        )
    
    def _parse_this_week(self) -> TemporalQuery:
        """Parse 'this week' expression."""
        now = datetime.now(timezone.utc)
        start_of_week = now - timedelta(days=now.weekday())
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_week = start_of_week + timedelta(weeks=1)
        
        return TemporalQuery(
            operator=TemporalOperator.BETWEEN,
            time_range=TimeRange(start_time=start_of_week, end_time=end_of_week)
        )
    
    def _parse_last_week(self) -> TemporalQuery:
        """Parse 'last week' expression."""
        now = datetime.now(timezone.utc)
        start_of_this_week = now - timedelta(days=now.weekday())
        start_of_last_week = start_of_this_week - timedelta(weeks=1)
        start_of_last_week = start_of_last_week.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_of_last_week = start_of_last_week + timedelta(weeks=1)
        
        return TemporalQuery(
            operator=TemporalOperator.BETWEEN,
            time_range=TimeRange(start_time=start_of_last_week, end_time=end_of_last_week)
        )
    
    def _parse_this_month(self) -> TemporalQuery:
        """Parse 'this month' expression."""
        now = datetime.now(timezone.utc)
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Calculate end of month
        if now.month == 12:
            end_of_month = start_of_month.replace(year=now.year + 1, month=1)
        else:
            end_of_month = start_of_month.replace(month=now.month + 1)
        
        return TemporalQuery(
            operator=TemporalOperator.BETWEEN,
            time_range=TimeRange(start_time=start_of_month, end_time=end_of_month)
        )
    
    def _parse_last_month(self) -> TemporalQuery:
        """Parse 'last month' expression."""
        now = datetime.now(timezone.utc)
        
        # Calculate start of last month
        if now.month == 1:
            start_of_last_month = now.replace(
                year=now.year - 1, month=12, day=1,
                hour=0, minute=0, second=0, microsecond=0
            )
        else:
            start_of_last_month = now.replace(
                month=now.month - 1, day=1,
                hour=0, minute=0, second=0, microsecond=0
            )
        
        # End of last month is start of this month
        start_of_this_month = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        
        return TemporalQuery(
            operator=TemporalOperator.BETWEEN,
            time_range=TimeRange(
                start_time=start_of_last_month,
                end_time=start_of_this_month
            )
        )
    
    def _parse_this_year(self) -> TemporalQuery:
        """Parse 'this year' expression."""
        now = datetime.now(timezone.utc)
        start_of_year = now.replace(
            month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        end_of_year = start_of_year.replace(year=now.year + 1)
        
        return TemporalQuery(
            operator=TemporalOperator.BETWEEN,
            time_range=TimeRange(start_time=start_of_year, end_time=end_of_year)
        )
    
    def _parse_last_year(self) -> TemporalQuery:
        """Parse 'last year' expression."""
        now = datetime.now(timezone.utc)
        start_of_last_year = now.replace(
            year=now.year - 1, month=1, day=1,
            hour=0, minute=0, second=0, microsecond=0
        )
        end_of_last_year = start_of_last_year.replace(year=now.year)
        
        return TemporalQuery(
            operator=TemporalOperator.BETWEEN,
            time_range=TimeRange(
                start_time=start_of_last_year,
                end_time=end_of_last_year
            )
        )


class TemporalFilter:
    """Main temporal filtering system."""
    
    def __init__(self):
        """Initialize temporal filter."""
        self.parser = TemporalQueryParser()
        self._filter_count = 0
        self._total_filter_time = 0.0
    
    async def apply(self, items: List[MemoryItem], query_expression: Any,
                   context: QueryContext) -> List[MemoryItem]:
        """Apply temporal filtering to memory items.
        
        Args:
            items: Memory items to filter
            query_expression: Parsed query expression (may contain temporal info)
            context: Query execution context
            
        Returns:
            Filtered memory items
        """
        start_time = time.time()
        
        try:
            # Extract temporal queries from expression
            temporal_queries = self._extract_temporal_queries(query_expression)
            
            if not temporal_queries:
                return items
            
            # Apply each temporal filter
            filtered_items = items
            for temporal_query in temporal_queries:
                filtered_items = [
                    item for item in filtered_items
                    if temporal_query.matches_item(item)
                ]
            
            self._update_filter_stats(time.time() - start_time)
            return filtered_items
            
        except Exception as e:
            self._update_filter_stats(time.time() - start_time)
            return items  # Return original items on error
    
    def parse_temporal_expression(self, expression: str) -> Optional[TemporalQuery]:
        """Parse a temporal expression.
        
        Args:
            expression: Temporal expression string
            
        Returns:
            Parsed temporal query or None
        """
        return self.parser.parse(expression)
    
    def _extract_temporal_queries(self, query_expression: Any) -> List[TemporalQuery]:
        """Extract temporal queries from a parsed query expression.
        
        Args:
            query_expression: Parsed query AST or string
            
        Returns:
            List of temporal queries
        """
        # This would be implemented based on the actual query AST structure
        # For now, return empty list as placeholder
        return []
    
    def _update_filter_stats(self, execution_time: float) -> None:
        """Update filter statistics."""
        self._filter_count += 1
        self._total_filter_time += execution_time
    
    def get_filter_stats(self) -> Dict[str, Any]:
        """Get temporal filter statistics."""
        avg_filter_time = (
            self._total_filter_time / max(1, self._filter_count)
        )
        
        return {
            'total_filters': self._filter_count,
            'total_filter_time': self._total_filter_time,
            'average_filter_time': avg_filter_time,
            'supported_operators': [op.value for op in TemporalOperator],
            'supported_units': [unit.value for unit in RelativeTime]
        }