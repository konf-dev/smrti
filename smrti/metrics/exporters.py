"""
smrti/metrics/exporters.py - Metrics export functionality

Implements various exporters for metrics data including Prometheus, JSON, CSV,
and time-series database formats for monitoring and analysis.
"""

from __future__ import annotations

import json
import csv
import io
import time
from typing import Dict, List, Optional, Any, TextIO, Union
from abc import ABC, abstractmethod
from dataclasses import dataclass
import asyncio
from pathlib import Path

from .collectors import MetricPoint, MetricType, MetricLevel
from .aggregators import AggregatedMetric, TimeSeriesPoint, StatisticalSummary


@dataclass
class ExportConfig:
    """Configuration for metrics export."""
    
    export_format: str
    output_path: Optional[str] = None
    include_labels: bool = True
    include_metadata: bool = True
    time_format: str = "timestamp"  # "timestamp" or "iso"
    compression: Optional[str] = None
    batch_size: int = 1000
    
    # Format-specific options
    format_options: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.format_options is None:
            self.format_options = {}


class MetricsExporter(ABC):
    """Base class for metrics exporters."""
    
    def __init__(self, config: ExportConfig):
        """Initialize the exporter.
        
        Args:
            config: Export configuration
        """
        self.config = config
        self.exported_count = 0
        self.last_export_time = 0.0
    
    @abstractmethod
    def export_metrics(self, metrics: List[MetricPoint]) -> str:
        """Export metrics to string format.
        
        Args:
            metrics: List of metric points to export
            
        Returns:
            Formatted metrics string
        """
        pass
    
    @abstractmethod
    def export_aggregated_metrics(self, metrics: List[AggregatedMetric]) -> str:
        """Export aggregated metrics.
        
        Args:
            metrics: List of aggregated metrics
            
        Returns:
            Formatted metrics string
        """
        pass
    
    def export_to_file(self, metrics: Union[List[MetricPoint], List[AggregatedMetric]], 
                      file_path: Optional[str] = None) -> None:
        """Export metrics to file.
        
        Args:
            metrics: Metrics to export
            file_path: Output file path (defaults to config path)
        """
        output_path = file_path or self.config.output_path
        if not output_path:
            raise ValueError("No output path specified")
        
        # Determine export method based on metric type
        if metrics and isinstance(metrics[0], MetricPoint):
            content = self.export_metrics(metrics)
        elif metrics and isinstance(metrics[0], AggregatedMetric):
            content = self.export_aggregated_metrics(metrics)
        else:
            content = ""
        
        # Write to file
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        self.exported_count += len(metrics)
        self.last_export_time = time.time()
    
    def _format_timestamp(self, timestamp: float) -> Union[float, str]:
        """Format timestamp according to configuration."""
        if self.config.time_format == "iso":
            from datetime import datetime
            return datetime.fromtimestamp(timestamp).isoformat()
        else:
            return timestamp
    
    def get_export_stats(self) -> Dict[str, Any]:
        """Get export statistics."""
        return {
            'exported_count': self.exported_count,
            'last_export_time': self.last_export_time,
            'export_format': self.config.export_format
        }


class PrometheusExporter(MetricsExporter):
    """Prometheus format exporter."""
    
    def __init__(self, config: ExportConfig):
        """Initialize Prometheus exporter."""
        config.export_format = "prometheus"
        super().__init__(config)
    
    def export_metrics(self, metrics: List[MetricPoint]) -> str:
        """Export metrics in Prometheus format."""
        lines = []
        
        # Group metrics by name for HELP and TYPE comments
        metric_groups: Dict[str, List[MetricPoint]] = {}
        for metric in metrics:
            if metric.name not in metric_groups:
                metric_groups[metric.name] = []
            metric_groups[metric.name].append(metric)
        
        for metric_name, metric_list in metric_groups.items():
            # Add HELP comment
            lines.append(f'# HELP {metric_name} Smrti system metric')
            
            # Add TYPE comment
            first_metric = metric_list[0]
            prom_type = self._get_prometheus_type(first_metric.metric_type)
            lines.append(f'# TYPE {metric_name} {prom_type}')
            
            # Add metric lines
            for metric in metric_list:
                line = self._format_prometheus_metric(metric)
                lines.append(line)
            
            lines.append('')  # Empty line between metrics
        
        return '\n'.join(lines)
    
    def export_aggregated_metrics(self, metrics: List[AggregatedMetric]) -> str:
        """Export aggregated metrics in Prometheus format."""
        lines = []
        
        for metric in metrics:
            metric_name = f"{metric.name}_{metric.aggregation_function.value}"
            
            lines.append(f'# HELP {metric_name} Aggregated Smrti metric')
            lines.append(f'# TYPE {metric_name} gauge')
            
            # Format labels
            labels = []
            if self.config.include_labels:
                for key, value in metric.labels.items():
                    labels.append(f'{key}="{value}"')
                
                # Add aggregation metadata
                labels.extend([
                    f'period="{metric.period.value}"',
                    f'function="{metric.aggregation_function.value}"',
                    f'sample_count="{metric.sample_count}"'
                ])
            
            label_str = '{' + ','.join(labels) + '}' if labels else ''
            timestamp = int(metric.end_time * 1000)  # Prometheus uses milliseconds
            
            lines.append(f'{metric_name}{label_str} {metric.value} {timestamp}')
            lines.append('')
        
        return '\n'.join(lines)
    
    def _get_prometheus_type(self, metric_type: MetricType) -> str:
        """Convert Smrti metric type to Prometheus type."""
        type_map = {
            MetricType.COUNTER: 'counter',
            MetricType.GAUGE: 'gauge',
            MetricType.HISTOGRAM: 'histogram',
            MetricType.TIMER: 'histogram'
        }
        return type_map.get(metric_type, 'gauge')
    
    def _format_prometheus_metric(self, metric: MetricPoint) -> str:
        """Format a single metric in Prometheus format."""
        labels = []
        
        if self.config.include_labels and metric.labels:
            for key, value in metric.labels.items():
                # Escape label values
                escaped_value = str(value).replace('\\', '\\\\').replace('"', '\\"')
                labels.append(f'{key}="{escaped_value}"')
        
        label_str = '{' + ','.join(labels) + '}' if labels else ''
        timestamp = int(metric.timestamp * 1000)  # Prometheus uses milliseconds
        
        return f'{metric.name}{label_str} {metric.value} {timestamp}'


class JSONExporter(MetricsExporter):
    """JSON format exporter."""
    
    def __init__(self, config: ExportConfig):
        """Initialize JSON exporter."""
        config.export_format = "json"
        super().__init__(config)
        
        # JSON-specific options
        self.pretty_print = config.format_options.get('pretty_print', True)
        self.include_schema = config.format_options.get('include_schema', True)
    
    def export_metrics(self, metrics: List[MetricPoint]) -> str:
        """Export metrics in JSON format."""
        data = {
            'metrics': [self._metric_to_dict(metric) for metric in metrics],
            'export_info': {
                'count': len(metrics),
                'export_time': time.time(),
                'format': 'smrti_metrics_v1'
            }
        }
        
        if self.include_schema:
            data['schema'] = {
                'version': '1.0',
                'fields': {
                    'name': 'string',
                    'value': 'number',
                    'timestamp': 'number|string',
                    'type': 'string',
                    'level': 'string',
                    'labels': 'object'
                }
            }
        
        return json.dumps(data, indent=2 if self.pretty_print else None)
    
    def export_aggregated_metrics(self, metrics: List[AggregatedMetric]) -> str:
        """Export aggregated metrics in JSON format."""
        data = {
            'aggregated_metrics': [metric.to_dict() for metric in metrics],
            'export_info': {
                'count': len(metrics),
                'export_time': time.time(),
                'format': 'smrti_aggregated_v1'
            }
        }
        
        if self.include_schema:
            data['schema'] = {
                'version': '1.0',
                'type': 'aggregated_metrics'
            }
        
        return json.dumps(data, indent=2 if self.pretty_print else None)
    
    def _metric_to_dict(self, metric: MetricPoint) -> Dict[str, Any]:
        """Convert metric point to dictionary."""
        result = {
            'name': metric.name,
            'value': metric.value,
            'timestamp': self._format_timestamp(metric.timestamp),
            'type': metric.metric_type.value,
            'level': metric.level.value
        }
        
        if self.config.include_labels and metric.labels:
            result['labels'] = metric.labels
        
        return result


class CSVExporter(MetricsExporter):
    """CSV format exporter."""
    
    def __init__(self, config: ExportConfig):
        """Initialize CSV exporter."""
        config.export_format = "csv"
        super().__init__(config)
        
        # CSV-specific options
        self.delimiter = config.format_options.get('delimiter', ',')
        self.include_header = config.format_options.get('include_header', True)
        self.flatten_labels = config.format_options.get('flatten_labels', True)
    
    def export_metrics(self, metrics: List[MetricPoint]) -> str:
        """Export metrics in CSV format."""
        output = io.StringIO()
        
        if not metrics:
            return ""
        
        # Determine all possible label keys for consistent columns
        all_label_keys = set()
        if self.flatten_labels:
            for metric in metrics:
                all_label_keys.update(metric.labels.keys())
        
        # Define field names
        fieldnames = ['name', 'value', 'timestamp', 'type', 'level']
        
        if self.flatten_labels:
            fieldnames.extend(sorted(all_label_keys))
        else:
            fieldnames.append('labels')
        
        writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter=self.delimiter)
        
        if self.include_header:
            writer.writeheader()
        
        # Write metric rows
        for metric in metrics:
            row = {
                'name': metric.name,
                'value': metric.value,
                'timestamp': self._format_timestamp(metric.timestamp),
                'type': metric.metric_type.value,
                'level': metric.level.value
            }
            
            if self.flatten_labels:
                # Add label values as separate columns
                for key in all_label_keys:
                    row[key] = metric.labels.get(key, '')
            else:
                # Add labels as JSON string
                row['labels'] = json.dumps(metric.labels) if metric.labels else ''
            
            writer.writerow(row)
        
        return output.getvalue()
    
    def export_aggregated_metrics(self, metrics: List[AggregatedMetric]) -> str:
        """Export aggregated metrics in CSV format."""
        output = io.StringIO()
        
        if not metrics:
            return ""
        
        fieldnames = [
            'name', 'value', 'function', 'period', 'start_time', 'end_time',
            'duration_seconds', 'sample_count'
        ]
        
        # Determine label keys
        all_label_keys = set()
        if self.flatten_labels:
            for metric in metrics:
                all_label_keys.update(metric.labels.keys())
            fieldnames.extend(sorted(all_label_keys))
        else:
            fieldnames.append('labels')
        
        writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter=self.delimiter)
        
        if self.include_header:
            writer.writeheader()
        
        # Write aggregated metric rows
        for metric in metrics:
            row = {
                'name': metric.name,
                'value': metric.value,
                'function': metric.aggregation_function.value,
                'period': metric.period.value,
                'start_time': self._format_timestamp(metric.start_time),
                'end_time': self._format_timestamp(metric.end_time),
                'duration_seconds': metric.duration_seconds,
                'sample_count': metric.sample_count
            }
            
            if self.flatten_labels:
                for key in all_label_keys:
                    row[key] = metric.labels.get(key, '')
            else:
                row['labels'] = json.dumps(metric.labels) if metric.labels else ''
            
            writer.writerow(row)
        
        return output.getvalue()


class InfluxDBExporter(MetricsExporter):
    """InfluxDB line protocol exporter."""
    
    def __init__(self, config: ExportConfig):
        """Initialize InfluxDB exporter."""
        config.export_format = "influxdb"
        super().__init__(config)
        
        # InfluxDB-specific options
        self.measurement_prefix = config.format_options.get('measurement_prefix', 'smrti')
        self.database_name = config.format_options.get('database', 'smrti_metrics')
    
    def export_metrics(self, metrics: List[MetricPoint]) -> str:
        """Export metrics in InfluxDB line protocol format."""
        lines = []
        
        for metric in metrics:
            line = self._format_influx_line(metric)
            lines.append(line)
        
        return '\n'.join(lines)
    
    def export_aggregated_metrics(self, metrics: List[AggregatedMetric]) -> str:
        """Export aggregated metrics in InfluxDB format."""
        lines = []
        
        for metric in metrics:
            # Create measurement name
            measurement = f"{self.measurement_prefix}_{metric.name}_{metric.aggregation_function.value}"
            
            # Build tags
            tags = []
            if metric.labels:
                for key, value in metric.labels.items():
                    tags.append(f"{key}={self._escape_influx_value(str(value))}")
            
            # Add aggregation metadata as tags
            tags.extend([
                f"period={metric.period.value}",
                f"function={metric.aggregation_function.value}"
            ])
            
            tag_str = ',' + ','.join(tags) if tags else ''
            
            # Build fields
            fields = [
                f"value={metric.value}",
                f"sample_count={metric.sample_count}i",
                f"duration_seconds={metric.duration_seconds}"
            ]
            
            field_str = ','.join(fields)
            
            # Format timestamp (InfluxDB uses nanoseconds)
            timestamp_ns = int(metric.end_time * 1_000_000_000)
            
            line = f"{measurement}{tag_str} {field_str} {timestamp_ns}"
            lines.append(line)
        
        return '\n'.join(lines)
    
    def _format_influx_line(self, metric: MetricPoint) -> str:
        """Format a single metric in InfluxDB line protocol."""
        # Measurement name
        measurement = f"{self.measurement_prefix}_{metric.name}"
        
        # Tags
        tags = []
        if metric.labels:
            for key, value in metric.labels.items():
                escaped_key = self._escape_influx_key(key)
                escaped_value = self._escape_influx_value(str(value))
                tags.append(f"{escaped_key}={escaped_value}")
        
        # Add metric metadata as tags
        tags.extend([
            f"type={metric.metric_type.value}",
            f"level={metric.level.value}"
        ])
        
        tag_str = ',' + ','.join(tags) if tags else ''
        
        # Fields (always include value)
        field_str = f"value={metric.value}"
        
        # Timestamp (InfluxDB uses nanoseconds)
        timestamp_ns = int(metric.timestamp * 1_000_000_000)
        
        return f"{measurement}{tag_str} {field_str} {timestamp_ns}"
    
    def _escape_influx_key(self, key: str) -> str:
        """Escape InfluxDB tag/field key."""
        return key.replace(' ', '\\ ').replace(',', '\\,').replace('=', '\\=')
    
    def _escape_influx_value(self, value: str) -> str:
        """Escape InfluxDB tag value."""
        return value.replace(' ', '\\ ').replace(',', '\\,').replace('=', '\\=')


class MultiFormatExporter:
    """Exporter that supports multiple output formats simultaneously."""
    
    def __init__(self):
        """Initialize multi-format exporter."""
        self.exporters: Dict[str, MetricsExporter] = {}
    
    def add_exporter(self, name: str, exporter: MetricsExporter) -> None:
        """Add an exporter.
        
        Args:
            name: Name for the exporter
            exporter: MetricsExporter instance
        """
        self.exporters[name] = exporter
    
    def export_to_all(self, metrics: Union[List[MetricPoint], List[AggregatedMetric]]) -> Dict[str, str]:
        """Export metrics using all configured exporters.
        
        Args:
            metrics: Metrics to export
            
        Returns:
            Dictionary mapping exporter name to exported content
        """
        results = {}
        
        for name, exporter in self.exporters.items():
            try:
                if metrics and isinstance(metrics[0], MetricPoint):
                    content = exporter.export_metrics(metrics)
                elif metrics and isinstance(metrics[0], AggregatedMetric):
                    content = exporter.export_aggregated_metrics(metrics)
                else:
                    content = ""
                
                results[name] = content
                
            except Exception as e:
                results[name] = f"Export error: {str(e)}"
        
        return results
    
    def export_to_files(self, metrics: Union[List[MetricPoint], List[AggregatedMetric]]) -> Dict[str, bool]:
        """Export metrics to files using all configured exporters.
        
        Args:
            metrics: Metrics to export
            
        Returns:
            Dictionary mapping exporter name to success status
        """
        results = {}
        
        for name, exporter in self.exporters.items():
            try:
                if exporter.config.output_path:
                    exporter.export_to_file(metrics)
                    results[name] = True
                else:
                    results[name] = False  # No output path configured
                    
            except Exception as e:
                print(f"Export error for {name}: {e}")
                results[name] = False
        
        return results
    
    def get_exporters(self) -> Dict[str, str]:
        """Get information about configured exporters.
        
        Returns:
            Dictionary mapping exporter name to format
        """
        return {name: exporter.config.export_format for name, exporter in self.exporters.items()}