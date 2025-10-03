"""
short_metrics_demo.py - Quick demonstration of Smrti metrics system

A brief demo showing all metrics functionality in 10 seconds.
"""

import asyncio
import time
import random

from smrti.metrics import (
    MetricsCollector, MetricType, MetricLevel,
    TimeSeriesAggregator, StatisticalAggregator,
    AggregationFunction, TimePeriod,
    PrometheusExporter, JSONExporter,
    MetricsDashboard, DashboardConfig, ChartConfig, ChartType,
    AlertRule, AlertLevel, ExportConfig
)


async def quick_demo():
    """Run a quick 10-second demo of the metrics system."""
    print("🚀 Smrti Metrics System - Quick Demo")
    print("=" * 40)
    
    # Initialize collector
    collector = MetricsCollector()
    
    # Create dashboard
    dashboard = MetricsDashboard(DashboardConfig(title="Quick Demo"), collector)
    dashboard.add_chart("demo_chart", ChartConfig(
        title="Demo Metrics",
        chart_type=ChartType.LINE,
        metrics=["cpu_usage", "memory_usage", "response_time"],
        time_range_minutes=1
    ))
    
    # Add alert rule
    dashboard.add_alert_rule(AlertRule(
        name="high_cpu",
        metric_name="cpu_usage",
        condition="> 80",
        level=AlertLevel.WARNING,
        description="CPU usage is high"
    ))
    
    dashboard.start()
    
    # Initialize exporters
    json_exporter = JSONExporter(ExportConfig("json", format_options={'pretty_print': True}))
    prometheus_exporter = PrometheusExporter(ExportConfig("prometheus"))
    
    print("📊 Generating sample metrics...")
    
    # Generate 20 sample metrics over 5 seconds
    for i in range(20):
        # Simulate some metrics with realistic values and trends
        cpu_usage = 30 + 40 * random.random() + 10 * (i / 20)  # Trending upward
        memory_usage = 200 + 100 * random.random()
        response_time = 50 + 30 * random.random()
        
        # Record metrics
        collector.record_metric("cpu_usage", cpu_usage, MetricType.GAUGE, MetricLevel.MEDIUM)
        collector.record_metric("memory_usage", memory_usage, MetricType.GAUGE, MetricLevel.MEDIUM)  
        collector.record_metric("response_time", response_time, MetricType.TIMER, MetricLevel.MEDIUM)
        
        await asyncio.sleep(0.25)  # 4 metrics per second
    
    print("📈 Demonstrating aggregations...")
    
    # Get metrics and perform aggregations
    metrics = collector.get_all_metrics()
    print(f"   • Collected {len(metrics)} total metric points")
    
    # Time series aggregation
    ts_agg = TimeSeriesAggregator()
    ts_agg.add_metrics(metrics)  # First add the metrics
    
    # Aggregate cpu_usage over the last minute
    if metrics:
        cpu_metrics = [m for m in metrics if m.name == "cpu_usage"]
        if cpu_metrics:
            ts_results = ts_agg.aggregate_time_series("cpu_usage", TimePeriod.MINUTE, AggregationFunction.AVERAGE)
            print(f"   • Time series aggregation: {len(ts_results)} data points for cpu_usage")
    
    # Statistical analysis
    stats_agg = StatisticalAggregator()
    stats_agg.add_metrics(metrics)  # First add the metrics
    
    # Calculate summary for each metric type
    metric_names = set(m.name for m in metrics)
    stats_results = []
    for name in metric_names:
        summary = stats_agg.calculate_summary(name)
        if summary:
            stats_results.append(summary)
    
    print(f"   • Statistical analysis: {len(stats_results)} metrics analyzed")
    
    if stats_results:
        for stat in stats_results[:2]:  # Show first 2
            print(f"     - {stat.metric_name}: avg={stat.mean:.1f}, std={stat.std_dev:.1f}")
    
    print("📤 Demonstrating exports...")
    
    # Export to different formats
    json_output = json_exporter.export_metrics(metrics)
    prometheus_output = prometheus_exporter.export_metrics(metrics)
    
    print(f"   • JSON export: {len(json_output)} characters")
    print(f"   • Prometheus export: {len(prometheus_output)} characters") 
    
    print("📋 Dashboard summary...")
    
    # Show dashboard data
    dashboard_data = dashboard.get_dashboard_data()
    summary = dashboard_data['summary']
    
    print(f"   • Total metrics: {summary['total_metrics']}")
    print(f"   • Active alerts: {summary['active_alerts']}")
    print(f"   • Charts configured: {len(dashboard_data['charts'])}")
    
    # Check for any alerts that were triggered
    alerts = dashboard_data['alerts']['active']
    if alerts:
        print(f"   • ⚠️ Alert triggered: {alerts[0]['message']}")
    
    # Show metric summaries
    metric_summary = dashboard.get_metric_summary()
    print("   • Metric trends:")
    for name, data in list(metric_summary.items())[:3]:
        trend = data.get('trend', 'stable')
        latest = data.get('latest', 0)
        print(f"     - {name}: {latest:.1f} ({trend})")
    
    dashboard.stop()
    
    print("\n✨ Demo completed successfully!")
    print("🔍 The Smrti metrics system provides:")
    print("   • Real-time metrics collection with multiple data types")
    print("   • Advanced aggregation (time series, statistical, performance)")
    print("   • Multi-format export (Prometheus, JSON, CSV, InfluxDB)")
    print("   • Live dashboard with charts and alerting")
    print("   • Comprehensive monitoring for memory operations")


if __name__ == "__main__":
    asyncio.run(quick_demo())