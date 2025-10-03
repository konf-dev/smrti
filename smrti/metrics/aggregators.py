"""
smrti/metrics/aggregators.py - Metrics aggregation and analysis

Implements various aggregation strategies for processing collected metrics,
including time series analysis, statistical summaries, and performance analytics.
"""

from __future__ import annotations

import time
import statistics
from typing import Dict, List, Optional, Any, Callable, Tuple, Union
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum
import numpy as np
from datetime import datetime, timedelta

from .collectors import MetricPoint, MetricType, MetricLevel


class AggregationFunction(Enum):
    """Supported aggregation functions."""
    
    SUM = "sum"
    AVERAGE = "average"
    MIN = "min"
    MAX = "max"
    COUNT = "count"
    PERCENTILE_50 = "p50"
    PERCENTILE_95 = "p95"
    PERCENTILE_99 = "p99"
    STDDEV = "stddev"
    RATE = "rate"


class TimePeriod(str, Enum):
    """Time periods for aggregation."""
    MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    HOUR = "1h"
    DAY = "1d"
    WEEK = "1w"
    MONTH = "1M"


@dataclass
class AggregatedMetric:
    """An aggregated metric with time window information."""
    
    name: str
    value: Union[int, float]
    aggregation_function: AggregationFunction
    period: TimePeriod
    start_time: float
    end_time: float
    sample_count: int
    labels: Dict[str, str] = field(default_factory=dict)
    
    @property
    def duration_seconds(self) -> float:
        """Duration of the aggregation window in seconds."""
        return self.end_time - self.start_time
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'name': self.name,
            'value': self.value,
            'function': self.aggregation_function.value,
            'period': self.period.value,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'duration_seconds': self.duration_seconds,
            'sample_count': self.sample_count,
            'labels': self.labels
        }


@dataclass
class TimeSeriesPoint:
    """Single point in a time series."""
    
    timestamp: float
    value: Union[int, float]
    labels: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'timestamp': self.timestamp,
            'value': self.value,
            'labels': self.labels
        }


@dataclass
class StatisticalSummary:
    """Statistical summary of a metric."""
    
    metric_name: str
    sample_count: int
    sum_value: float
    min_value: float
    max_value: float
    mean: float
    median: float
    std_dev: float
    percentile_95: float
    percentile_99: float
    start_time: float
    end_time: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'metric_name': self.metric_name,
            'sample_count': self.sample_count,
            'sum': self.sum_value,
            'min': self.min_value,
            'max': self.max_value,
            'mean': self.mean,
            'median': self.median,
            'std_dev': self.std_dev,
            'p95': self.percentile_95,
            'p99': self.percentile_99,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'duration': self.end_time - self.start_time
        }


class MetricsAggregator:
    """Base class for metrics aggregation."""
    
    def __init__(self, max_retention_hours: int = 72):
        """Initialize the aggregator.
        
        Args:
            max_retention_hours: Maximum hours to retain raw data
        """
        self.max_retention_hours = max_retention_hours
        self.raw_metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))
        self.aggregated_metrics: Dict[str, List[AggregatedMetric]] = defaultdict(list)
        
    def add_metric(self, metric: MetricPoint) -> None:
        """Add a new metric point for aggregation.
        
        Args:
            metric: Metric point to add
        """
        self.raw_metrics[metric.name].append(metric)
        self._cleanup_old_data()
    
    def add_metrics(self, metrics: List[MetricPoint]) -> None:
        """Add multiple metric points.
        
        Args:
            metrics: List of metric points to add
        """
        for metric in metrics:
            self.add_metric(metric)
    
    def _cleanup_old_data(self) -> None:
        """Remove data older than retention period."""
        cutoff_time = time.time() - (self.max_retention_hours * 3600)
        
        for metric_name, points in self.raw_metrics.items():
            # Remove old points
            while points and points[0].timestamp < cutoff_time:
                points.popleft()
    
    def get_raw_data(self, metric_name: str, 
                    start_time: Optional[float] = None,
                    end_time: Optional[float] = None) -> List[MetricPoint]:
        """Get raw metric data for a time range.
        
        Args:
            metric_name: Name of the metric
            start_time: Start timestamp (defaults to 1 hour ago)
            end_time: End timestamp (defaults to now)
            
        Returns:
            List of metric points in the time range
        """
        if start_time is None:
            start_time = time.time() - 3600  # 1 hour ago
        if end_time is None:
            end_time = time.time()
        
        points = self.raw_metrics.get(metric_name, [])
        return [p for p in points if start_time <= p.timestamp <= end_time]


class TimeSeriesAggregator(MetricsAggregator):
    """Aggregator for time series analysis."""
    
    def __init__(self, max_retention_hours: int = 72):
        """Initialize the time series aggregator."""
        super().__init__(max_retention_hours)
        self.time_series: Dict[str, Dict[TimePeriod, List[TimeSeriesPoint]]] = defaultdict(
            lambda: defaultdict(list)
        )
    
    def aggregate_time_series(self, 
                            metric_name: str,
                            period: TimePeriod,
                            function: AggregationFunction = AggregationFunction.AVERAGE,
                            start_time: Optional[float] = None,
                            end_time: Optional[float] = None) -> List[TimeSeriesPoint]:
        """Aggregate metric data into time series.
        
        Args:
            metric_name: Name of the metric
            period: Aggregation time period
            function: Aggregation function to apply
            start_time: Start timestamp
            end_time: End timestamp
            
        Returns:
            List of aggregated time series points
        """
        raw_data = self.get_raw_data(metric_name, start_time, end_time)
        if not raw_data:
            return []
        
        # Get period duration in seconds
        period_seconds = self._get_period_seconds(period)
        
        # Group data by time buckets
        buckets: Dict[int, List[float]] = defaultdict(list)
        
        for point in raw_data:
            bucket = int(point.timestamp // period_seconds)
            buckets[bucket].append(point.value)
        
        # Aggregate each bucket
        time_series = []
        for bucket, values in buckets.items():
            bucket_time = bucket * period_seconds
            aggregated_value = self._apply_aggregation_function(values, function)
            
            time_series.append(TimeSeriesPoint(
                timestamp=bucket_time,
                value=aggregated_value
            ))
        
        # Sort by timestamp
        time_series.sort(key=lambda x: x.timestamp)
        
        # Cache the result
        self.time_series[metric_name][period] = time_series
        
        return time_series
    
    def get_trend(self, metric_name: str,
                 period: TimePeriod = TimePeriod.HOUR,
                 lookback_hours: int = 24) -> Dict[str, Any]:
        """Calculate trend information for a metric.
        
        Args:
            metric_name: Name of the metric
            period: Aggregation period
            lookback_hours: Hours to look back for trend analysis
            
        Returns:
            Dictionary with trend information
        """
        end_time = time.time()
        start_time = end_time - (lookback_hours * 3600)
        
        time_series = self.aggregate_time_series(
            metric_name, period, AggregationFunction.AVG, start_time, end_time
        )
        
        if len(time_series) < 2:
            return {
                'trend': 'insufficient_data',
                'direction': 'unknown',
                'change_percent': 0.0,
                'data_points': len(time_series)
            }
        
        # Calculate trend
        values = [point.value for point in time_series]
        timestamps = [point.timestamp for point in time_series]
        
        # Simple linear regression for trend
        n = len(values)
        x_mean = sum(range(n)) / n
        y_mean = sum(values) / n
        
        numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        
        slope = numerator / denominator if denominator != 0 else 0
        
        # Determine trend direction
        if abs(slope) < 0.01:  # Threshold for "stable"
            direction = 'stable'
            trend = 'stable'
        elif slope > 0:
            direction = 'increasing'
            trend = 'upward'
        else:
            direction = 'decreasing'
            trend = 'downward'
        
        # Calculate percentage change
        first_value = values[0]
        last_value = values[-1]
        change_percent = ((last_value - first_value) / first_value * 100) if first_value != 0 else 0
        
        return {
            'trend': trend,
            'direction': direction,
            'slope': slope,
            'change_percent': change_percent,
            'first_value': first_value,
            'last_value': last_value,
            'data_points': len(time_series),
            'period': period.value,
            'lookback_hours': lookback_hours
        }
    
    def _get_period_seconds(self, period: TimePeriod) -> int:
        """Get the duration of an aggregation period in seconds."""
        period_map = {
            TimePeriod.MINUTE: 60,
            TimePeriod.FIVE_MINUTES: 300,
            TimePeriod.FIFTEEN_MINUTES: 900,
            TimePeriod.HOUR: 3600,
            TimePeriod.DAY: 86400,
            TimePeriod.WEEK: 604800,
            TimePeriod.MONTH: 2592000  # 30 days
        }
        return period_map.get(period, 3600)  # Default to 1 hour
    
    def _apply_aggregation_function(self, values: List[float], 
                                  function: AggregationFunction) -> float:
        """Apply aggregation function to a list of values."""
        if not values:
            return 0.0
        
        if function == AggregationFunction.SUM:
            return sum(values)
        elif function == AggregationFunction.AVERAGE:
            return sum(values) / len(values)
        elif function == AggregationFunction.MIN:
            return min(values)
        elif function == AggregationFunction.MAX:
            return max(values)
        elif function == AggregationFunction.COUNT:
            return len(values)
        elif function == AggregationFunction.MEDIAN:
            return statistics.median(values)
        elif function == AggregationFunction.PERCENTILE_95:
            return np.percentile(values, 95) if len(values) > 1 else values[0]
        elif function == AggregationFunction.PERCENTILE_99:
            return np.percentile(values, 99) if len(values) > 1 else values[0]
        elif function == AggregationFunction.STDDEV:
            return statistics.stdev(values) if len(values) > 1 else 0.0
        elif function == AggregationFunction.RATE:
            # Calculate rate per second
            if len(values) < 2:
                return 0.0
            return (values[-1] - values[0]) / len(values)
        else:
            return sum(values) / len(values)  # Default to average


class StatisticalAggregator(MetricsAggregator):
    """Aggregator for statistical analysis."""
    
    def calculate_summary(self, metric_name: str,
                         start_time: Optional[float] = None,
                         end_time: Optional[float] = None) -> Optional[StatisticalSummary]:
        """Calculate statistical summary for a metric.
        
        Args:
            metric_name: Name of the metric
            start_time: Start timestamp
            end_time: End timestamp
            
        Returns:
            Statistical summary or None if insufficient data
        """
        raw_data = self.get_raw_data(metric_name, start_time, end_time)
        if not raw_data:
            return None
        
        values = [point.value for point in raw_data]
        timestamps = [point.timestamp for point in raw_data]
        
        if not values:
            return None
        
        # Calculate statistics
        try:
            summary = StatisticalSummary(
                metric_name=metric_name,
                sample_count=len(values),
                sum_value=sum(values),
                min_value=min(values),
                max_value=max(values),
                mean=statistics.mean(values),
                median=statistics.median(values),
                std_dev=statistics.stdev(values) if len(values) > 1 else 0.0,
                percentile_95=np.percentile(values, 95) if len(values) > 1 else values[0],
                percentile_99=np.percentile(values, 99) if len(values) > 1 else values[0],
                start_time=min(timestamps),
                end_time=max(timestamps)
            )
            return summary
            
        except Exception as e:
            print(f"Error calculating statistics for {metric_name}: {e}")
            return None
    
    def detect_anomalies(self, metric_name: str,
                        threshold_std_devs: float = 2.0,
                        lookback_hours: int = 24) -> List[Dict[str, Any]]:
        """Detect anomalies in metric data using statistical methods.
        
        Args:
            metric_name: Name of the metric
            threshold_std_devs: Number of standard deviations for anomaly threshold
            lookback_hours: Hours to look back for baseline calculation
            
        Returns:
            List of detected anomalies
        """
        end_time = time.time()
        start_time = end_time - (lookback_hours * 3600)
        
        raw_data = self.get_raw_data(metric_name, start_time, end_time)
        if len(raw_data) < 10:  # Need minimum data for anomaly detection
            return []
        
        values = [point.value for point in raw_data]
        timestamps = [point.timestamp for point in raw_data]
        
        # Calculate baseline statistics
        mean_value = statistics.mean(values)
        std_dev = statistics.stdev(values) if len(values) > 1 else 0.0
        
        if std_dev == 0:
            return []  # No variance, no anomalies
        
        # Detect anomalies
        anomalies = []
        threshold = threshold_std_devs * std_dev
        
        for i, (timestamp, value) in enumerate(zip(timestamps, values)):
            deviation = abs(value - mean_value)
            
            if deviation > threshold:
                anomaly_type = 'spike' if value > mean_value else 'dip'
                severity = min(deviation / threshold, 5.0)  # Cap at 5x threshold
                
                anomalies.append({
                    'timestamp': timestamp,
                    'value': value,
                    'expected_value': mean_value,
                    'deviation': deviation,
                    'threshold': threshold,
                    'severity': severity,
                    'type': anomaly_type,
                    'std_devs': deviation / std_dev if std_dev > 0 else 0
                })
        
        return anomalies
    
    def calculate_correlation(self, metric1_name: str, metric2_name: str,
                            start_time: Optional[float] = None,
                            end_time: Optional[float] = None) -> Optional[float]:
        """Calculate correlation between two metrics.
        
        Args:
            metric1_name: Name of first metric
            metric2_name: Name of second metric
            start_time: Start timestamp
            end_time: End timestamp
            
        Returns:
            Correlation coefficient or None if insufficient data
        """
        data1 = self.get_raw_data(metric1_name, start_time, end_time)
        data2 = self.get_raw_data(metric2_name, start_time, end_time)
        
        if len(data1) < 2 or len(data2) < 2:
            return None
        
        # Align data points by timestamp (simple approach)
        timestamps1 = {point.timestamp: point.value for point in data1}
        timestamps2 = {point.timestamp: point.value for point in data2}
        
        # Find common timestamps
        common_timestamps = set(timestamps1.keys()) & set(timestamps2.keys())
        
        if len(common_timestamps) < 2:
            return None
        
        values1 = [timestamps1[ts] for ts in common_timestamps]
        values2 = [timestamps2[ts] for ts in common_timestamps]
        
        # Calculate Pearson correlation
        try:
            correlation = np.corrcoef(values1, values2)[0, 1]
            return correlation if not np.isnan(correlation) else None
        except Exception:
            return None


class PerformanceAggregator(MetricsAggregator):
    """Aggregator focused on performance analysis."""
    
    def calculate_percentiles(self, metric_name: str,
                            percentiles: List[float] = [50, 90, 95, 99],
                            start_time: Optional[float] = None,
                            end_time: Optional[float] = None) -> Dict[str, float]:
        """Calculate percentiles for a metric.
        
        Args:
            metric_name: Name of the metric
            percentiles: List of percentile values to calculate
            start_time: Start timestamp
            end_time: End timestamp
            
        Returns:
            Dictionary mapping percentile to value
        """
        raw_data = self.get_raw_data(metric_name, start_time, end_time)
        if not raw_data:
            return {}
        
        values = [point.value for point in raw_data]
        if not values:
            return {}
        
        result = {}
        for percentile in percentiles:
            try:
                result[f'p{percentile}'] = np.percentile(values, percentile)
            except Exception as e:
                print(f"Error calculating {percentile}th percentile: {e}")
                result[f'p{percentile}'] = 0.0
        
        return result
    
    def calculate_sla_compliance(self, metric_name: str,
                               threshold: float,
                               comparison: str = "less_than",
                               start_time: Optional[float] = None,
                               end_time: Optional[float] = None) -> Dict[str, Any]:
        """Calculate SLA compliance for a metric.
        
        Args:
            metric_name: Name of the metric
            threshold: SLA threshold value
            comparison: Comparison type ("less_than", "greater_than", "equal")
            start_time: Start timestamp
            end_time: End timestamp
            
        Returns:
            Dictionary with SLA compliance information
        """
        raw_data = self.get_raw_data(metric_name, start_time, end_time)
        if not raw_data:
            return {
                'compliance_percentage': 0.0,
                'total_samples': 0,
                'compliant_samples': 0,
                'violations': 0
            }
        
        total_samples = len(raw_data)
        compliant_samples = 0
        violations = []
        
        for point in raw_data:
            is_compliant = False
            
            if comparison == "less_than":
                is_compliant = point.value < threshold
            elif comparison == "greater_than":
                is_compliant = point.value > threshold
            elif comparison == "equal":
                is_compliant = abs(point.value - threshold) < 0.001
            elif comparison == "less_equal":
                is_compliant = point.value <= threshold
            elif comparison == "greater_equal":
                is_compliant = point.value >= threshold
            
            if is_compliant:
                compliant_samples += 1
            else:
                violations.append({
                    'timestamp': point.timestamp,
                    'value': point.value,
                    'threshold': threshold,
                    'violation_amount': abs(point.value - threshold)
                })
        
        compliance_percentage = (compliant_samples / total_samples * 100) if total_samples > 0 else 0.0
        
        return {
            'compliance_percentage': compliance_percentage,
            'total_samples': total_samples,
            'compliant_samples': compliant_samples,
            'violations': len(violations),
            'violation_details': violations[-10:],  # Last 10 violations
            'threshold': threshold,
            'comparison': comparison
        }
    
    def calculate_availability(self, metric_name: str,
                             healthy_threshold: float,
                             start_time: Optional[float] = None,
                             end_time: Optional[float] = None) -> Dict[str, Any]:
        """Calculate availability/uptime for a health metric.
        
        Args:
            metric_name: Name of the health metric
            healthy_threshold: Threshold for considering system healthy
            start_time: Start timestamp
            end_time: End timestamp
            
        Returns:
            Dictionary with availability information
        """
        raw_data = self.get_raw_data(metric_name, start_time, end_time)
        if not raw_data:
            return {
                'availability_percentage': 0.0,
                'uptime_seconds': 0.0,
                'downtime_seconds': 0.0,
                'total_time_seconds': 0.0,
                'outages': []
            }
        
        if not start_time:
            start_time = raw_data[0].timestamp
        if not end_time:
            end_time = raw_data[-1].timestamp
        
        total_time = end_time - start_time
        
        # Identify healthy/unhealthy periods
        healthy_periods = []
        unhealthy_periods = []
        current_period_start = start_time
        current_state = None
        
        for point in raw_data:
            is_healthy = point.value >= healthy_threshold
            
            if current_state is None:
                current_state = is_healthy
                current_period_start = point.timestamp
            elif current_state != is_healthy:
                # State change
                period_end = point.timestamp
                
                if current_state:
                    healthy_periods.append((current_period_start, period_end))
                else:
                    unhealthy_periods.append((current_period_start, period_end))
                
                current_state = is_healthy
                current_period_start = point.timestamp
        
        # Handle final period
        if current_state is not None:
            if current_state:
                healthy_periods.append((current_period_start, end_time))
            else:
                unhealthy_periods.append((current_period_start, end_time))
        
        # Calculate totals
        uptime_seconds = sum(end - start for start, end in healthy_periods)
        downtime_seconds = sum(end - start for start, end in unhealthy_periods)
        
        availability_percentage = (uptime_seconds / total_time * 100) if total_time > 0 else 0.0
        
        # Format outages
        outages = [
            {
                'start_time': start,
                'end_time': end,
                'duration_seconds': end - start,
                'duration_minutes': (end - start) / 60
            }
            for start, end in unhealthy_periods
        ]
        
        return {
            'availability_percentage': availability_percentage,
            'uptime_seconds': uptime_seconds,
            'downtime_seconds': downtime_seconds,
            'total_time_seconds': total_time,
            'uptime_minutes': uptime_seconds / 60,
            'downtime_minutes': downtime_seconds / 60,
            'outage_count': len(outages),
            'outages': outages,
            'mtbf_hours': (uptime_seconds / 3600 / len(outages)) if outages else float('inf'),  # Mean Time Between Failures
            'mttr_minutes': (downtime_seconds / 60 / len(outages)) if outages else 0.0  # Mean Time To Recovery
        }