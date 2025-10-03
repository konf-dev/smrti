"""
example_metrics_system.py - Comprehensive metrics system demonstration

This example shows how to use the complete Smrti metrics system including
collection, aggregation, export, and dashboard visualization.
"""

import asyncio
import time
import random
from pathlib import Path

from smrti.metrics import (
    MetricsCollector, MetricType, MetricLevel,
    TimeSeriesAggregator, StatisticalAggregator, PerformanceAggregator,
    AggregationFunction, TimePeriod,
    PrometheusExporter, JSONExporter, CSVExporter,
    MetricsDashboard, DashboardConfig, ChartConfig, ChartType,
    AlertRule, AlertLevel, ExportConfig
)


class MetricsSystemExample:
    """Example demonstrating the complete metrics system."""
    
    def __init__(self):
        """Initialize the metrics system example."""
        # Initialize metrics collector
        self.collector = MetricsCollector()
        
        # Initialize aggregators
        self.time_series_aggregator = TimeSeriesAggregator()
        self.statistical_aggregator = StatisticalAggregator()
        self.performance_aggregator = PerformanceAggregator()
        
        # Initialize exporters
        self.setup_exporters()
        
        # Initialize dashboard
        self.setup_dashboard()
        
        # Simulation state
        self.simulation_running = False
    
    def setup_exporters(self):
        """Set up various metric exporters."""
        # Prometheus exporter
        self.prometheus_exporter = PrometheusExporter(
            ExportConfig(
                export_format="prometheus",
                output_path="metrics/prometheus_metrics.txt"
            )
        )
        
        # JSON exporter
        self.json_exporter = JSONExporter(
            ExportConfig(
                export_format="json",
                output_path="metrics/metrics_data.json",
                format_options={'pretty_print': True}
            )
        )
        
        # CSV exporter
        self.csv_exporter = CSVExporter(
            ExportConfig(
                export_format="csv",
                output_path="metrics/metrics_data.csv",
                format_options={'include_header': True, 'flatten_labels': True}
            )
        )
    
    def setup_dashboard(self):
        """Set up the metrics dashboard."""
        dashboard_config = DashboardConfig(
            title="Smrti Metrics Dashboard Example",
            refresh_interval_seconds=5,  # Fast refresh for demo
            enable_alerts=True,
            auto_refresh=True
        )
        
        self.dashboard = MetricsDashboard(dashboard_config, self.collector)
        
        # Add custom charts
        self.setup_charts()
        
        # Add alert rules
        self.setup_alerts()
        
        # Add update callback to print dashboard updates
        self.dashboard.add_update_callback(self.on_dashboard_update)
    
    def setup_charts(self):
        """Set up dashboard charts."""
        # Memory performance chart
        self.dashboard.add_chart("memory_performance", ChartConfig(
            title="Memory System Performance",
            chart_type=ChartType.LINE,
            metrics=["memory_hit_rate", "memory_response_time", "memory_throughput"],
            time_range_minutes=5,
            refresh_interval_seconds=5
        ))
        
        # System resources chart
        self.dashboard.add_chart("system_resources", ChartConfig(
            title="System Resource Usage",
            chart_type=ChartType.AREA,
            metrics=["cpu_usage", "memory_usage", "disk_io"],
            time_range_minutes=10,
            refresh_interval_seconds=5
        ))
        
        # Query statistics chart
        self.dashboard.add_chart("query_stats", ChartConfig(
            title="Query Statistics",
            chart_type=ChartType.BAR,
            metrics=["query_count", "query_errors", "query_latency"],
            time_range_minutes=3,
            refresh_interval_seconds=5
        ))
    
    def setup_alerts(self):
        """Set up alert rules."""
        # High response time alert
        self.dashboard.add_alert_rule(AlertRule(
            name="high_response_time",
            metric_name="memory_response_time",
            condition="> 100",
            level=AlertLevel.WARNING,
            description="Memory response time is high",
            debounce_seconds=30
        ))
        
        # Low hit rate alert
        self.dashboard.add_alert_rule(AlertRule(
            name="low_hit_rate",
            metric_name="memory_hit_rate",
            condition="< 0.7",
            level=AlertLevel.ERROR,
            description="Memory hit rate is below acceptable threshold",
            debounce_seconds=45
        ))
        
        # High error rate alert
        self.dashboard.add_alert_rule(AlertRule(
            name="high_error_rate",
            metric_name="query_errors",
            condition="> 5",
            level=AlertLevel.CRITICAL,
            description="Query error rate is critically high",
            debounce_seconds=20
        ))
    
    def on_dashboard_update(self, dashboard_data):
        """Callback for dashboard updates."""
        summary = dashboard_data.get('summary', {})
        alerts = dashboard_data.get('alerts', {})
        
        print(f"\n=== Dashboard Update ===")
        print(f"Metrics: {summary.get('total_metrics', 0)}")
        print(f"Active Alerts: {summary.get('active_alerts', 0)}")
        
        # Print any new alerts
        active_alerts = alerts.get('active', [])
        if active_alerts:
            print("⚠️  Active Alerts:")
            for alert in active_alerts[-3:]:  # Show last 3 alerts
                print(f"  - {alert['level'].upper()}: {alert['message']}")
    
    async def simulate_metrics(self, duration_seconds=60):
        """Simulate realistic metric data."""
        print(f"Starting metrics simulation for {duration_seconds} seconds...")
        
        self.simulation_running = True
        start_time = time.time()
        
        # Base values for realistic simulation
        base_hit_rate = 0.85
        base_response_time = 50
        base_throughput = 1000
        base_cpu = 30
        base_memory = 512
        base_queries = 100
        
        while self.simulation_running and (time.time() - start_time) < duration_seconds:
            current_time = time.time()
            
            # Simulate some patterns and occasional issues
            time_factor = (current_time - start_time) / 10  # Slow oscillation
            
            # Add some randomness and trends
            hit_rate = max(0.0, min(1.0, base_hit_rate + 
                                   0.1 * random.gauss(0, 1) + 
                                   0.05 * (1 + time_factor % 2)))
            
            response_time = max(1, base_response_time + 
                               20 * random.gauss(0, 1) + 
                               30 * (1 if time_factor % 3 < 0.5 else 0))  # Occasional spikes
            
            throughput = max(0, base_throughput + 
                            200 * random.gauss(0, 1) + 
                            100 * hit_rate)  # Correlate with hit rate
            
            cpu_usage = max(0, min(100, base_cpu + 
                                  15 * random.gauss(0, 1) + 
                                  20 * (1 - hit_rate)))  # Higher CPU when hit rate is low
            
            memory_usage = max(0, base_memory + 
                              100 * random.gauss(0, 1) + 
                              50 * throughput / 1000)
            
            disk_io = max(0, 50 + 20 * random.gauss(0, 1) + 
                         30 * (1 - hit_rate))  # More disk IO when cache misses
            
            query_count = max(0, base_queries + 
                             30 * random.gauss(0, 1))
            
            query_errors = max(0, int(random.gauss(2, 1)) if response_time > 80 else 0)
            
            query_latency = response_time + 10 * random.gauss(0, 1)
            
            # Record metrics with labels
            labels = {"simulation": "example", "environment": "demo"}
            
            # Memory metrics
            self.collector.record_metric("memory_hit_rate", hit_rate, 
                                       MetricType.GAUGE, MetricLevel.MEDIUM, labels)
            self.collector.record_metric("memory_response_time", response_time, 
                                       MetricType.TIMER, MetricLevel.MEDIUM, labels)
            self.collector.record_metric("memory_throughput", throughput, 
                                       MetricType.GAUGE, MetricLevel.MEDIUM, labels)
            
            # System metrics
            self.collector.record_metric("cpu_usage", cpu_usage, 
                                       MetricType.GAUGE, MetricLevel.MEDIUM, labels)
            self.collector.record_metric("memory_usage", memory_usage, 
                                       MetricType.GAUGE, MetricLevel.MEDIUM, labels)
            self.collector.record_metric("disk_io", disk_io, 
                                       MetricType.COUNTER, MetricLevel.MEDIUM, labels)
            
            # Query metrics
            self.collector.record_metric("query_count", query_count, 
                                       MetricType.COUNTER, MetricLevel.MEDIUM, labels)
            self.collector.record_metric("query_errors", query_errors, 
                                       MetricType.COUNTER, MetricLevel.HIGH if query_errors > 0 else MetricLevel.MEDIUM, labels)
            self.collector.record_metric("query_latency", query_latency, 
                                       MetricType.TIMER, MetricLevel.MEDIUM, labels)
            
            await asyncio.sleep(2)  # Generate metrics every 2 seconds
        
        print("Metrics simulation completed.")
    
    def export_metrics(self):
        """Export metrics in various formats."""
        print("\nExporting metrics...")
        
        # Get current metrics
        metrics = self.collector.get_all_metrics()
        if not metrics:
            print("No metrics to export.")
            return
        
        # Create output directory
        Path("metrics").mkdir(exist_ok=True)
        
        # Export to different formats
        try:
            self.prometheus_exporter.export_to_file(metrics)
            print(f"✓ Exported {len(metrics)} metrics to Prometheus format")
        except Exception as e:
            print(f"✗ Prometheus export failed: {e}")
        
        try:
            self.json_exporter.export_to_file(metrics)
            print(f"✓ Exported {len(metrics)} metrics to JSON format")
        except Exception as e:
            print(f"✗ JSON export failed: {e}")
        
        try:
            self.csv_exporter.export_to_file(metrics)
            print(f"✓ Exported {len(metrics)} metrics to CSV format")
        except Exception as e:
            print(f"✗ CSV export failed: {e}")
    
    def demonstrate_aggregations(self):
        """Demonstrate metric aggregation capabilities."""
        print("\nDemonstrating metric aggregations...")
        
        # Get metrics for aggregation
        metrics = self.collector.get_all_metrics()
        if not metrics:
            print("No metrics available for aggregation.")
            return
        
        # Time series aggregation
        print("\n--- Time Series Aggregation ---")
        try:
            ts_results = self.time_series_aggregator.aggregate_metrics(
                metrics, AggregationFunction.AVERAGE, TimePeriod.MINUTE
            )
            
            for result in ts_results[:3]:  # Show first 3 results
                print(f"• {result.name}: avg={result.value:.2f} over {result.sample_count} samples")
        
        except Exception as e:
            print(f"Time series aggregation failed: {e}")
        
        # Statistical aggregation
        print("\n--- Statistical Analysis ---")
        try:
            stats_results = self.statistical_aggregator.compute_statistics(metrics)
            
            for result in stats_results[:3]:  # Show first 3 results
                stats = result.statistics
                print(f"• {result.name}: mean={stats.get('mean', 0):.2f}, "
                     f"std={stats.get('std', 0):.2f}, min={stats.get('min', 0):.2f}, "
                     f"max={stats.get('max', 0):.2f}")
        
        except Exception as e:
            print(f"Statistical analysis failed: {e}")
        
        # Performance aggregation
        print("\n--- Performance Analysis ---")
        try:
            perf_results = self.performance_aggregator.analyze_performance(metrics)
            
            for result in perf_results[:3]:  # Show first 3 results
                print(f"• {result.name}: {result.summary}")
        
        except Exception as e:
            print(f"Performance analysis failed: {e}")
    
    def print_dashboard_summary(self):
        """Print current dashboard state."""
        dashboard_data = self.dashboard.get_dashboard_data()
        
        print("\n=== Dashboard Summary ===")
        print(f"Title: {dashboard_data['config']['title']}")
        print(f"Charts: {len(dashboard_data['charts'])}")
        print(f"Total Metrics: {dashboard_data['summary']['total_metrics']}")
        print(f"Active Alerts: {dashboard_data['summary']['active_alerts']}")
        print(f"Alert Rules: {dashboard_data['summary']['alert_rules']}")
        
        # Show metric summaries
        metric_summary = self.dashboard.get_metric_summary()
        print(f"\nMetric Summary ({len(metric_summary)} metrics):")
        for name, summary in list(metric_summary.items())[:5]:  # Show first 5
            print(f"  • {name}: latest={summary['latest']:.2f}, "
                 f"min={summary['min']:.2f}, max={summary['max']:.2f}, "
                 f"trend={summary.get('trend', 'unknown')}")
    
    async def run_complete_example(self):
        """Run the complete metrics system example."""
        print("🚀 Starting Smrti Metrics System Example")
        print("=" * 50)
        
        try:
            # Start the dashboard
            print("Starting dashboard...")
            self.dashboard.start()
            
            # Wait a moment for dashboard to initialize
            await asyncio.sleep(2)
            
            # Run simulation for 30 seconds
            await self.simulate_metrics(30)
            
            # Export metrics
            self.export_metrics()
            
            # Show aggregation results
            self.demonstrate_aggregations()
            
            # Print dashboard summary
            self.print_dashboard_summary()
            
            # Export dashboard data
            print("\nExporting dashboard data...")
            dashboard_export = self.dashboard.export_data(include_history=True)
            
            with open("metrics/dashboard_export.json", "w") as f:
                f.write(dashboard_export)
            print("✓ Dashboard data exported to metrics/dashboard_export.json")
            
            print(f"\n🎉 Metrics system example completed successfully!")
            print(f"📊 Check the 'metrics/' directory for exported data")
            
        except KeyboardInterrupt:
            print("\n⏹️  Example interrupted by user")
        except Exception as e:
            print(f"\n❌ Example failed: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Cleanup
            self.simulation_running = False
            self.dashboard.stop()
            print("🧹 Cleanup completed")


async def main():
    """Run the metrics system example."""
    example = MetricsSystemExample()
    await example.run_complete_example()


if __name__ == "__main__":
    # Run the example
    asyncio.run(main())