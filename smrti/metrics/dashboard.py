"""
smrti/metrics/dashboard.py - Metrics dashboard and visualization

Provides a comprehensive dashboard for viewing and analyzing Smrti system metrics
with real-time updates, charts, and alerting capabilities.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Dict, List, Optional, Any, Callable, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import threading
from datetime import datetime, timedelta
from pathlib import Path

from .collectors import MetricsCollector, MetricPoint, MetricType, MetricLevel
from .aggregators import (
    TimeSeriesAggregator, StatisticalAggregator, PerformanceAggregator,
    AggregatedMetric, AggregationFunction, TimePeriod
)
from .exporters import MetricsExporter, JSONExporter, ExportConfig


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ChartType(Enum):
    """Chart visualization types."""
    LINE = "line"
    BAR = "bar"
    AREA = "area"
    GAUGE = "gauge"
    HEATMAP = "heatmap"
    HISTOGRAM = "histogram"


@dataclass
class AlertRule:
    """Alert rule configuration."""
    
    name: str
    metric_name: str
    condition: str  # e.g., "> 100", "< 0.5", "== 0"
    level: AlertLevel
    description: str
    
    # Alert behavior
    enabled: bool = True
    debounce_seconds: int = 60
    max_alerts_per_hour: int = 10
    
    # Tracking
    last_triggered: Optional[float] = None
    alert_count: int = 0
    
    def evaluate(self, value: float) -> bool:
        """Evaluate if the condition is met.
        
        Args:
            value: Metric value to evaluate
            
        Returns:
            True if alert should be triggered
        """
        if not self.enabled:
            return False
        
        # Check debounce
        if (self.last_triggered and 
            time.time() - self.last_triggered < self.debounce_seconds):
            return False
        
        # Check rate limit
        hour_ago = time.time() - 3600
        if self.last_triggered and self.last_triggered > hour_ago:
            if self.alert_count >= self.max_alerts_per_hour:
                return False
        else:
            # Reset counter for new hour
            self.alert_count = 0
        
        # Evaluate condition
        try:
            # Simple condition evaluation (extend as needed)
            if self.condition.startswith('>'):
                threshold = float(self.condition[1:].strip())
                return value > threshold
            elif self.condition.startswith('<'):
                threshold = float(self.condition[1:].strip())
                return value < threshold
            elif self.condition.startswith('=='):
                threshold = float(self.condition[2:].strip())
                return abs(value - threshold) < 0.001  # Float comparison
            elif self.condition.startswith('!='):
                threshold = float(self.condition[2:].strip())
                return abs(value - threshold) >= 0.001
            elif self.condition.startswith('>='):
                threshold = float(self.condition[2:].strip())
                return value >= threshold
            elif self.condition.startswith('<='):
                threshold = float(self.condition[2:].strip())
                return value <= threshold
        except (ValueError, IndexError):
            pass
        
        return False
    
    def trigger(self) -> None:
        """Mark alert as triggered."""
        self.last_triggered = time.time()
        self.alert_count += 1


@dataclass
class Alert:
    """Active alert instance."""
    
    rule_name: str
    metric_name: str
    value: float
    threshold: str
    level: AlertLevel
    message: str
    timestamp: float
    
    resolved: bool = False
    resolved_timestamp: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary."""
        return {
            'rule_name': self.rule_name,
            'metric_name': self.metric_name,
            'value': self.value,
            'threshold': self.threshold,
            'level': self.level.value,
            'message': self.message,
            'timestamp': self.timestamp,
            'resolved': self.resolved,
            'resolved_timestamp': self.resolved_timestamp
        }


@dataclass
class ChartConfig:
    """Chart configuration."""
    
    title: str
    chart_type: ChartType
    metrics: List[str]  # Metric names to display
    
    # Display options
    time_range_minutes: int = 60
    refresh_interval_seconds: int = 30
    show_legend: bool = True
    show_grid: bool = True
    
    # Chart-specific options
    y_axis_min: Optional[float] = None
    y_axis_max: Optional[float] = None
    color_scheme: List[str] = field(default_factory=lambda: ['#007acc', '#ff6b6b', '#4ecdc4', '#45b7d1'])
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert chart config to dictionary."""
        return {
            'title': self.title,
            'chart_type': self.chart_type.value,
            'metrics': self.metrics,
            'time_range_minutes': self.time_range_minutes,
            'refresh_interval_seconds': self.refresh_interval_seconds,
            'show_legend': self.show_legend,
            'show_grid': self.show_grid,
            'y_axis_min': self.y_axis_min,
            'y_axis_max': self.y_axis_max,
            'color_scheme': self.color_scheme
        }


@dataclass
class DashboardConfig:
    """Dashboard configuration."""
    
    title: str = "Smrti Metrics Dashboard"
    refresh_interval_seconds: int = 30
    max_data_points: int = 1000
    auto_refresh: bool = True
    
    # Layout
    charts_per_row: int = 2
    chart_height: int = 300
    
    # Alert settings
    enable_alerts: bool = True
    show_alert_history: bool = True
    max_alert_history: int = 100


class MetricsDashboard:
    """Real-time metrics dashboard."""
    
    def __init__(self, config: DashboardConfig, metrics_collector: MetricsCollector):
        """Initialize the dashboard.
        
        Args:
            config: Dashboard configuration
            metrics_collector: Metrics collector instance
        """
        self.config = config
        self.collector = metrics_collector
        
        # Aggregators
        self.time_series_aggregator = TimeSeriesAggregator()
        self.statistical_aggregator = StatisticalAggregator()
        self.performance_aggregator = PerformanceAggregator()
        
        # Dashboard state
        self.charts: Dict[str, ChartConfig] = {}
        self.alert_rules: Dict[str, AlertRule] = {}
        self.active_alerts: List[Alert] = []
        self.alert_history: List[Alert] = []
        
        # Data storage
        self.metric_history: Dict[str, List[MetricPoint]] = {}
        self.chart_data: Dict[str, List[Dict[str, Any]]] = {}
        
        # Real-time updates
        self.update_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self.running = False
        self.update_thread: Optional[threading.Thread] = None
        
        # Export capability
        self.exporter = JSONExporter(ExportConfig("json", include_metadata=True))
    
    def add_chart(self, chart_id: str, chart_config: ChartConfig) -> None:
        """Add a chart to the dashboard.
        
        Args:
            chart_id: Unique identifier for the chart
            chart_config: Chart configuration
        """
        self.charts[chart_id] = chart_config
        self.chart_data[chart_id] = []
    
    def remove_chart(self, chart_id: str) -> None:
        """Remove a chart from the dashboard.
        
        Args:
            chart_id: Chart identifier
        """
        self.charts.pop(chart_id, None)
        self.chart_data.pop(chart_id, None)
    
    def add_alert_rule(self, rule: AlertRule) -> None:
        """Add an alert rule.
        
        Args:
            rule: Alert rule configuration
        """
        self.alert_rules[rule.name] = rule
    
    def remove_alert_rule(self, rule_name: str) -> None:
        """Remove an alert rule.
        
        Args:
            rule_name: Name of the rule to remove
        """
        self.alert_rules.pop(rule_name, None)
    
    def add_update_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Add a callback for real-time updates.
        
        Args:
            callback: Function to call with dashboard data updates
        """
        self.update_callbacks.append(callback)
    
    def start(self) -> None:
        """Start the dashboard."""
        if self.running:
            return
        
        self.running = True
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()
    
    def stop(self) -> None:
        """Stop the dashboard."""
        self.running = False
        if self.update_thread:
            self.update_thread.join(timeout=5.0)
    
    def _update_loop(self) -> None:
        """Main update loop for real-time data."""
        while self.running:
            try:
                # Collect current metrics
                current_metrics = self.collector.get_all_metrics()
                
                # Update metric history
                self._update_metric_history(current_metrics)
                
                # Update chart data
                self._update_chart_data()
                
                # Check alerts
                if self.config.enable_alerts:
                    self._check_alerts(current_metrics)
                
                # Notify callbacks
                dashboard_data = self.get_dashboard_data()
                for callback in self.update_callbacks:
                    try:
                        callback(dashboard_data)
                    except Exception as e:
                        print(f"Dashboard callback error: {e}")
                
            except Exception as e:
                print(f"Dashboard update error: {e}")
            
            time.sleep(self.config.refresh_interval_seconds)
    
    def _update_metric_history(self, metrics: List[MetricPoint]) -> None:
        """Update the metric history storage."""
        current_time = time.time()
        cutoff_time = current_time - (3600)  # Keep 1 hour of data
        
        # Add new metrics
        for metric in metrics:
            if metric.name not in self.metric_history:
                self.metric_history[metric.name] = []
            
            self.metric_history[metric.name].append(metric)
        
        # Clean old data
        for metric_name in self.metric_history:
            self.metric_history[metric_name] = [
                m for m in self.metric_history[metric_name]
                if m.timestamp > cutoff_time
            ]
            
            # Limit data points
            if len(self.metric_history[metric_name]) > self.config.max_data_points:
                self.metric_history[metric_name] = self.metric_history[metric_name][-self.config.max_data_points:]
    
    def _update_chart_data(self) -> None:
        """Update chart data for visualization."""
        for chart_id, chart_config in self.charts.items():
            chart_data = []
            
            # Calculate time range
            current_time = time.time()
            start_time = current_time - (chart_config.time_range_minutes * 60)
            
            # Collect data for each metric in the chart
            for metric_name in chart_config.metrics:
                if metric_name in self.metric_history:
                    # Filter by time range
                    filtered_metrics = [
                        m for m in self.metric_history[metric_name]
                        if m.timestamp >= start_time
                    ]
                    
                    # Convert to chart format
                    metric_data = {
                        'name': metric_name,
                        'data': [
                            {
                                'x': m.timestamp * 1000,  # JavaScript timestamp
                                'y': m.value,
                                'timestamp': m.timestamp,
                                'labels': m.labels
                            }
                            for m in filtered_metrics
                        ]
                    }
                    chart_data.append(metric_data)
            
            self.chart_data[chart_id] = chart_data
    
    def _check_alerts(self, metrics: List[MetricPoint]) -> None:
        """Check alert rules against current metrics."""
        # Group metrics by name for easier lookup
        metric_values = {}
        for metric in metrics:
            if metric.name not in metric_values:
                metric_values[metric.name] = []
            metric_values[metric.name].append(metric.value)
        
        # Evaluate alert rules
        for rule_name, rule in self.alert_rules.items():
            if rule.metric_name in metric_values:
                # Use the latest value for the metric
                latest_value = metric_values[rule.metric_name][-1]
                
                if rule.evaluate(latest_value):
                    # Create alert
                    alert = Alert(
                        rule_name=rule_name,
                        metric_name=rule.metric_name,
                        value=latest_value,
                        threshold=rule.condition,
                        level=rule.level,
                        message=f"{rule.description}: {rule.metric_name}={latest_value} {rule.condition}",
                        timestamp=time.time()
                    )
                    
                    # Add to active alerts
                    self.active_alerts.append(alert)
                    self.alert_history.append(alert)
                    
                    # Trigger the rule
                    rule.trigger()
                    
                    print(f"Alert triggered: {alert.message}")
        
        # Clean up old alerts from history
        if len(self.alert_history) > self.config.max_alert_history:
            self.alert_history = self.alert_history[-self.config.max_alert_history:]
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get complete dashboard data for display.
        
        Returns:
            Dictionary containing all dashboard data
        """
        return {
            'config': {
                'title': self.config.title,
                'refresh_interval': self.config.refresh_interval_seconds,
                'auto_refresh': self.config.auto_refresh,
                'charts_per_row': self.config.charts_per_row,
                'chart_height': self.config.chart_height
            },
            'charts': {
                chart_id: {
                    'config': chart_config.to_dict(),
                    'data': self.chart_data.get(chart_id, [])
                }
                for chart_id, chart_config in self.charts.items()
            },
            'alerts': {
                'active': [alert.to_dict() for alert in self.active_alerts],
                'history': [alert.to_dict() for alert in self.alert_history[-20:]]  # Last 20 alerts
            },
            'summary': {
                'total_metrics': len(self.metric_history),
                'active_alerts': len(self.active_alerts),
                'alert_rules': len(self.alert_rules),
                'uptime': time.time() - getattr(self, 'start_time', time.time())
            },
            'timestamp': time.time()
        }
    
    def get_metric_summary(self) -> Dict[str, Any]:
        """Get summary statistics for all metrics.
        
        Returns:
            Dictionary with metric summaries
        """
        summary = {}
        
        for metric_name, history in self.metric_history.items():
            if not history:
                continue
            
            values = [m.value for m in history]
            
            # Calculate basic statistics
            summary[metric_name] = {
                'count': len(values),
                'latest': values[-1] if values else None,
                'min': min(values) if values else None,
                'max': max(values) if values else None,
                'avg': sum(values) / len(values) if values else None,
                'first_timestamp': history[0].timestamp if history else None,
                'last_timestamp': history[-1].timestamp if history else None
            }
            
            # Add trend information if we have enough data
            if len(values) >= 2:
                trend = "stable"
                if values[-1] > values[0]:
                    trend = "increasing"
                elif values[-1] < values[0]:
                    trend = "decreasing"
                
                summary[metric_name]['trend'] = trend
                summary[metric_name]['change'] = values[-1] - values[0]
        
        return summary
    
    def export_data(self, format_type: str = "json", 
                   include_history: bool = True) -> str:
        """Export dashboard data.
        
        Args:
            format_type: Export format ("json", "csv")
            include_history: Whether to include metric history
            
        Returns:
            Formatted export data
        """
        export_data = {
            'dashboard_config': self.config.__dict__,
            'charts': {chart_id: config.to_dict() for chart_id, config in self.charts.items()},
            'alert_rules': {name: {
                'name': rule.name,
                'metric_name': rule.metric_name,
                'condition': rule.condition,
                'level': rule.level.value,
                'description': rule.description,
                'enabled': rule.enabled
            } for name, rule in self.alert_rules.items()},
            'summary': self.get_metric_summary(),
            'export_timestamp': time.time()
        }
        
        if include_history:
            # Convert metric history to serializable format
            history_data = {}
            for metric_name, metrics in self.metric_history.items():
                history_data[metric_name] = [
                    {
                        'name': m.name,
                        'value': m.value,
                        'timestamp': m.timestamp,
                        'type': m.metric_type.value,
                        'level': m.level.value,
                        'labels': m.labels
                    }
                    for m in metrics
                ]
            export_data['metric_history'] = history_data
        
        if format_type == "json":
            return json.dumps(export_data, indent=2)
        else:
            # For other formats, convert using the exporter system
            return str(export_data)
    
    def create_default_charts(self) -> None:
        """Create default charts for common metrics."""
        # Memory tier performance chart
        self.add_chart("memory_tiers", ChartConfig(
            title="Memory Tier Performance",
            chart_type=ChartType.LINE,
            metrics=["tier_access_count", "tier_hit_rate", "tier_response_time"],
            time_range_minutes=30
        ))
        
        # System resources chart
        self.add_chart("system_resources", ChartConfig(
            title="System Resources",
            chart_type=ChartType.AREA,
            metrics=["memory_usage_mb", "cpu_usage_percent", "disk_io_operations"],
            time_range_minutes=60
        ))
        
        # Query performance chart
        self.add_chart("query_performance", ChartConfig(
            title="Query Performance",
            chart_type=ChartType.BAR,
            metrics=["query_count", "average_query_time", "query_success_rate"],
            time_range_minutes=15
        ))
        
        # Consolidation activity chart
        self.add_chart("consolidation", ChartConfig(
            title="Consolidation Activity",
            chart_type=ChartType.LINE,
            metrics=["consolidation_tasks_completed", "consolidation_errors", "consolidation_efficiency"],
            time_range_minutes=120
        ))
    
    def create_default_alerts(self) -> None:
        """Create default alert rules for common issues."""
        # High memory usage alert
        self.add_alert_rule(AlertRule(
            name="high_memory_usage",
            metric_name="memory_usage_mb",
            condition="> 1000",
            level=AlertLevel.WARNING,
            description="System memory usage is high"
        ))
        
        # Low hit rate alert
        self.add_alert_rule(AlertRule(
            name="low_hit_rate",
            metric_name="tier_hit_rate",
            condition="< 0.8",
            level=AlertLevel.WARNING,
            description="Memory tier hit rate is below threshold"
        ))
        
        # High response time alert
        self.add_alert_rule(AlertRule(
            name="high_response_time",
            metric_name="tier_response_time",
            condition="> 100",
            level=AlertLevel.ERROR,
            description="Memory tier response time is too high"
        ))
        
        # Consolidation errors alert
        self.add_alert_rule(AlertRule(
            name="consolidation_errors",
            metric_name="consolidation_errors",
            condition="> 0",
            level=AlertLevel.ERROR,
            description="Consolidation process has errors"
        ))