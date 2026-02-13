#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EasyRemote Performance Metrics Collection Module

This module implements comprehensive performance monitoring and metrics collection
for the EasyRemote distributed computing framework. It provides real-time performance
analysis, historical data tracking, and intelligent insights for load balancing
optimization and system performance monitoring.

Architecture:
- Repository Pattern: Centralized data storage and retrieval for metrics
- Observer Pattern: Real-time performance data collection and notification
- Strategy Pattern: Multiple analysis algorithms for different use cases
- Factory Pattern: Metrics aggregation and analysis object creation

Key Features:
1. Comprehensive Metrics Collection:
   * Request execution time and success rate tracking
   * Resource utilization monitoring per node and function
   * System-wide performance analysis and trending
   * Historical data retention with configurable policies

2. Advanced Analytics:
   * Statistical analysis of performance trends
   * Performance prediction based on historical data
   * Anomaly detection for performance degradation
   * Comparative analysis across nodes and functions

3. Intelligent Insights:
   * Performance bottleneck identification
   * Load balancing effectiveness analysis
   * Resource utilization optimization recommendations
   * Capacity planning and scaling insights

4. Scalable Data Management:
   * Efficient in-memory data structures with overflow protection
   * Configurable data retention policies
   * Batch processing for large-scale analysis
   * Memory-efficient aggregation and compression

Usage Example:
    >>> # Initialize performance collector
    >>> collector = AdvancedPerformanceCollector(
    ...     max_history_size=10000,
    ...     analysis_window_hours=6,
    ...     enable_predictions=True
    ... )
    >>> 
    >>> # Record request execution
    >>> await collector.record_request_execution(
    ...     node_id="worker-1",
    ...     function_name="process_data",
    ...     execution_time=1.23,
    ...     success=True,
    ...     input_size=1000000
    ... )
    >>> 
    >>> # Get performance analysis
    >>> stats = await collector.get_comprehensive_analysis("worker-1")
    >>> print(f"Node efficiency: {stats.efficiency_score:.2f}")

Author: Silan Hu (silan.hu@u.nus.edu)
Version: 2.0.0
"""

import asyncio
import logging
import statistics
from typing import Dict, List, Optional, Any, Set, Tuple
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import uuid

from ..utils.logger import ModernLogger
from ..utils.concurrency import LoopBoundAsyncLock


# Configure module logger
_logger = logging.getLogger(__name__)


class PerformanceMetricType(Enum):
    """Types of performance metrics that can be collected."""
    EXECUTION_TIME = "execution_time"       # Function execution duration
    SUCCESS_RATE = "success_rate"           # Request success percentage
    THROUGHPUT = "throughput"               # Requests per unit time
    RESOURCE_USAGE = "resource_usage"       # CPU, memory, GPU utilization
    LATENCY = "latency"                     # Network and processing latency
    ERROR_RATE = "error_rate"               # Error occurrence percentage
    QUEUE_LENGTH = "queue_length"           # Request queue size
    LOAD_DISTRIBUTION = "load_distribution" # Load balance across nodes


class AggregationMethod(Enum):
    """Methods for aggregating performance metrics."""
    AVERAGE = "average"                     # Arithmetic mean
    MEDIAN = "median"                       # Middle value
    PERCENTILE_95 = "percentile_95"         # 95th percentile
    PERCENTILE_99 = "percentile_99"         # 99th percentile
    MIN = "min"                             # Minimum value
    MAX = "max"                             # Maximum value
    SUM = "sum"                             # Total sum
    COUNT = "count"                         # Number of observations


@dataclass
class RequestExecutionMetrics:
    """
    Comprehensive metrics for a single request execution.
    
    This class captures detailed information about request execution
    performance, enabling fine-grained analysis and optimization.
    """
    # Core identification
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    node_id: str = ""
    function_name: str = ""
    
    # Timing metrics
    execution_time_ms: float = 0.0          # Total execution time
    queue_wait_time_ms: float = 0.0         # Time spent waiting in queue
    network_latency_ms: float = 0.0         # Network communication time
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Success and error tracking
    success: bool = True                     # Whether execution succeeded
    error_type: Optional[str] = None         # Type of error if failed
    error_message: Optional[str] = None      # Detailed error message
    retry_count: int = 0                     # Number of retries performed
    
    # Data and resource metrics
    input_data_size_bytes: int = 0          # Size of input data
    output_data_size_bytes: int = 0         # Size of output data
    memory_usage_mb: float = 0.0            # Peak memory usage during execution
    cpu_usage_percent: float = 0.0          # Average CPU usage during execution
    gpu_usage_percent: float = 0.0          # Average GPU usage during execution
    
    # Performance context
    node_load_factor: float = 0.0           # Node load at execution time
    concurrent_executions: int = 1          # Number of concurrent executions
    priority_level: int = 5                 # Execution priority (1-10)
    client_location: Optional[str] = None   # Geographic location of client
    
    # Custom metrics
    custom_metrics: Dict[str, float] = field(default_factory=dict)
    
    def calculate_efficiency_score(self) -> float:
        """
        Calculate overall execution efficiency score.
        
        Returns:
            Efficiency score from 0.0 to 1.0 (higher is better)
        """
        # Base score from execution success
        base_score = 1.0 if self.success else 0.0
        
        # Adjust for resource efficiency
        resource_efficiency = 1.0
        if self.memory_usage_mb > 0 and self.input_data_size_bytes > 0:
            # Memory efficiency (lower memory per byte is better)
            memory_per_byte = self.memory_usage_mb / (self.input_data_size_bytes / 1024 / 1024)
            resource_efficiency *= max(0.1, 1.0 - min(memory_per_byte / 100, 0.9))
        
        # Adjust for execution time relative to data size
        time_efficiency = 1.0
        if self.input_data_size_bytes > 0:
            # Time per MB (lower is better)
            time_per_mb = self.execution_time_ms / max(self.input_data_size_bytes / 1024 / 1024, 0.1)
            time_efficiency = max(0.1, 1.0 - min(time_per_mb / 1000, 0.9))
        
        # Combine scores
        return base_score * resource_efficiency * time_efficiency
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for serialization."""
        return {
            "execution_id": self.execution_id,
            "node_id": self.node_id,
            "function_name": self.function_name,
            "execution_time_ms": self.execution_time_ms,
            "success": self.success,
            "timestamp": self.timestamp.isoformat(),
            "input_data_size_bytes": self.input_data_size_bytes,
            "output_data_size_bytes": self.output_data_size_bytes,
            "efficiency_score": self.calculate_efficiency_score(),
            "custom_metrics": self.custom_metrics
        }


@dataclass
class NodePerformanceProfile:
    """
    Comprehensive performance profile for a compute node.
    
    This class provides detailed performance analysis and insights
    for individual nodes, enabling informed load balancing decisions.
    """
    # Core identification
    node_id: str
    
    # Request statistics
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    
    # Performance metrics
    average_execution_time_ms: float = 0.0
    median_execution_time_ms: float = 0.0
    p95_execution_time_ms: float = 0.0      # 95th percentile
    p99_execution_time_ms: float = 0.0      # 99th percentile
    
    # Throughput and efficiency
    requests_per_minute: float = 0.0
    throughput_mb_per_second: float = 0.0
    efficiency_score: float = 0.0           # Overall efficiency (0.0-1.0)
    
    # Resource utilization
    average_cpu_usage: float = 0.0
    average_memory_usage: float = 0.0
    average_gpu_usage: float = 0.0
    peak_memory_usage_mb: float = 0.0
    
    # Reliability metrics
    success_rate: float = 1.0               # Percentage of successful requests
    error_rate: float = 0.0                 # Percentage of failed requests
    average_retry_count: float = 0.0        # Average retries per request
    
    # Load and capacity metrics
    average_load_factor: float = 0.0        # Average node load during requests
    max_concurrent_executions: int = 0      # Peak concurrent executions observed
    capacity_utilization: float = 0.0       # Percentage of capacity used
    
    # Time-based analysis
    analysis_period_hours: float = 0.0      # Time period for this analysis
    last_updated: datetime = field(default_factory=datetime.now)
    data_quality_score: float = 1.0         # Quality of data (based on sample size)
    
    # Performance trends
    performance_trend: Optional[str] = None  # "improving", "declining", "stable"
    trend_confidence: float = 0.0           # Confidence in trend assessment
    
    # Function-specific insights
    top_functions: List[Tuple[str, int]] = field(default_factory=list)  # (function, count)
    slowest_functions: List[Tuple[str, float]] = field(default_factory=list)  # (function, avg_time)
    
    @property
    def availability_score(self) -> float:
        """Calculate node availability score based on success rate and reliability."""
        return self.success_rate * (1.0 - min(self.average_retry_count / 5.0, 0.5))
    
    @property
    def performance_score(self) -> float:
        """Calculate overall performance score combining multiple factors."""
        # Normalize execution time (assuming 1000ms is average)
        time_score = max(0.1, 1.0 - min(self.average_execution_time_ms / 1000.0, 0.9))
        
        # Combine with other metrics
        return (
            self.availability_score * 0.3 +
            self.efficiency_score * 0.3 +
            time_score * 0.2 +
            (self.requests_per_minute / 60.0) * 0.2  # Normalize throughput
        )
    
    def get_capacity_recommendation(self) -> Dict[str, Any]:
        """
        Get capacity and scaling recommendations based on performance profile.
        
        Returns:
            Dictionary with capacity insights and recommendations
        """
        recommendations = {
            "current_utilization": self.capacity_utilization,
            "recommendations": [],
            "scaling_factors": {},
            "bottlenecks": []
        }
        
        # Utilization-based recommendations
        if self.capacity_utilization > 0.8:
            recommendations["recommendations"].append("Consider scaling up - high utilization")
            recommendations["scaling_factors"]["urgent"] = True
        elif self.capacity_utilization < 0.3:
            recommendations["recommendations"].append("Consider scaling down - low utilization")
            recommendations["scaling_factors"]["scale_down"] = True
        
        # Performance-based recommendations
        if self.average_execution_time_ms > 2000:  # > 2 seconds
            recommendations["bottlenecks"].append("High execution time")
            if self.average_cpu_usage > 80:
                recommendations["bottlenecks"].append("CPU bottleneck")
            if self.average_memory_usage > 85:
                recommendations["bottlenecks"].append("Memory bottleneck")
        
        # Success rate recommendations
        if self.success_rate < 0.95:
            recommendations["recommendations"].append("Investigate reliability issues")
            recommendations["bottlenecks"].append("High failure rate")
        
        return recommendations


@dataclass
class SystemPerformanceInsights:
    """
    System-wide performance insights and analysis.
    
    This class provides comprehensive analysis of the entire distributed
    system's performance, enabling strategic optimization decisions.
    """
    # System-wide metrics
    total_nodes: int = 0
    active_nodes: int = 0
    total_requests: int = 0
    system_success_rate: float = 1.0
    system_throughput_rpm: float = 0.0       # Requests per minute
    
    # Performance distribution
    load_distribution_variance: float = 0.0  # How evenly load is distributed
    performance_consistency: float = 1.0     # How consistent performance is across nodes
    
    # Top performers and bottlenecks
    best_performing_nodes: List[Tuple[str, float]] = field(default_factory=list)
    worst_performing_nodes: List[Tuple[str, float]] = field(default_factory=list)
    bottleneck_functions: List[Tuple[str, float]] = field(default_factory=list)
    
    # System health indicators
    overall_health_score: float = 1.0        # Overall system health (0.0-1.0)
    capacity_utilization: float = 0.0        # System-wide capacity utilization
    efficiency_score: float = 1.0            # System efficiency score
    
    # Trends and predictions
    growth_trend: Optional[str] = None       # "growing", "shrinking", "stable"
    predicted_capacity_exhaustion: Optional[datetime] = None
    scaling_recommendations: List[str] = field(default_factory=list)
    
    def generate_executive_summary(self) -> Dict[str, Any]:
        """Generate executive summary of system performance."""
        return {
            "system_health": "healthy" if self.overall_health_score > 0.8 else 
                           "degraded" if self.overall_health_score > 0.6 else "critical",
            "key_metrics": {
                "success_rate": f"{self.system_success_rate:.1%}",
                "throughput": f"{self.system_throughput_rpm:.1f} req/min",
                "efficiency": f"{self.efficiency_score:.1%}",
                "utilization": f"{self.capacity_utilization:.1%}"
            },
            "top_concerns": self._identify_top_concerns(),
            "scaling_status": self._assess_scaling_needs(),
            "recommendations": self.scaling_recommendations[:3]  # Top 3 recommendations
        }
    
    def _identify_top_concerns(self) -> List[str]:
        """Identify top performance concerns."""
        concerns = []
        
        if self.system_success_rate < 0.95:
            concerns.append("Low system success rate")
        
        if self.load_distribution_variance > 0.5:
            concerns.append("Uneven load distribution")
        
        if self.performance_consistency < 0.8:
            concerns.append("Inconsistent node performance")
        
        if self.capacity_utilization > 0.85:
            concerns.append("High capacity utilization")
        
        return concerns[:3]  # Return top 3 concerns
    
    def _assess_scaling_needs(self) -> str:
        """Assess current scaling needs."""
        if self.capacity_utilization > 0.8:
            return "scale_up_needed"
        elif self.capacity_utilization < 0.3 and self.active_nodes > 2:
            return "scale_down_possible"
        else:
            return "optimal"


class AdvancedPerformanceCollector(ModernLogger):
    """
    Advanced performance metrics collection and analysis system.
    
    This class provides comprehensive performance monitoring capabilities
    with sophisticated analytics, trend analysis, and intelligent insights
    for optimizing distributed system performance.
    
    Key Features:
    1. Multi-dimensional Metrics Collection: Request, node, and system-level metrics
    2. Advanced Analytics: Statistical analysis, trend detection, anomaly identification
    3. Performance Profiling: Detailed node and function performance profiling
    4. Predictive Insights: Capacity planning and performance prediction
    5. Intelligent Recommendations: Automated optimization suggestions
    
    Usage:
        >>> collector = AdvancedPerformanceCollector(
        ...     max_history_size=50000,
        ...     enable_real_time_analysis=True
        ... )
        >>> 
        >>> # Record request execution
        >>> await collector.record_request_execution(
        ...     node_id="worker-1",
        ...     function_name="ml_training",
        ...     execution_time_ms=2500.0,
        ...     success=True
        ... )
        >>> 
        >>> # Get performance analysis
        >>> profile = await collector.analyze_node_performance("worker-1")
        >>> insights = await collector.get_system_insights()
    """
    
    def __init__(self,
                 max_history_size: int = 10000,
                 analysis_window_hours: float = 6.0,
                 cache_duration_seconds: int = 300,
                 enable_real_time_analysis: bool = True,
                 enable_predictions: bool = False):
        """
        Initialize the advanced performance collector.
        
        Args:
            max_history_size: Maximum number of metrics to retain in memory
            analysis_window_hours: Time window for performance analysis
            cache_duration_seconds: How long to cache analysis results
            enable_real_time_analysis: Enable real-time performance analysis
            enable_predictions: Enable predictive analytics (experimental)
            
        Raises:
            ValueError: If configuration parameters are invalid
        """
        super().__init__(name="AdvancedPerformanceCollector")
        
        # Validate configuration
        if max_history_size < 1000:
            raise ValueError("max_history_size must be at least 1000")
        if analysis_window_hours <= 0:
            raise ValueError("analysis_window_hours must be positive")
        if cache_duration_seconds < 60:
            raise ValueError("cache_duration_seconds must be at least 60")
        
        # Configuration
        self.max_history_size = max_history_size
        self.analysis_window_hours = analysis_window_hours
        self.cache_duration_seconds = cache_duration_seconds
        self.enable_real_time_analysis = enable_real_time_analysis
        self.enable_predictions = enable_predictions
        
        # Core data storage
        self._request_metrics: deque = deque(maxlen=max_history_size)
        self._node_metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history_size // 10))
        self._function_metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history_size // 10))
        
        # Analysis cache
        self._analysis_cache: Dict[str, Tuple[Any, datetime]] = {}
        self._cache_lock = LoopBoundAsyncLock(name="performance-cache-lock")
        
        # Performance monitoring
        self._collection_stats = {
            "total_recorded": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "analysis_count": 0
        }
        
        # Background tasks
        self._background_tasks: Set[asyncio.Task] = set()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
        self.info(f"Initialized AdvancedPerformanceCollector "
                 f"(history: {max_history_size}, window: {analysis_window_hours}h, "
                 f"real_time: {enable_real_time_analysis})")
    
    async def start_collection(self) -> 'AdvancedPerformanceCollector':
        """
        Start the performance collection system.
        
        Returns:
            Self for method chaining
        """
        if self._running:
            return self
        
        self._running = True
        
        # Start background cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._background_tasks.add(self._cleanup_task)
        
        self.info("Advanced performance collection started")
        return self
    
    async def stop_collection(self):
        """Stop the performance collection system gracefully."""
        if not self._running:
            return
        
        self._running = False
        
        # Cancel background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        
        self._background_tasks.clear()
        self.info("Advanced performance collection stopped")
    
    async def record_request_execution(self,
                                     node_id: str,
                                     function_name: str,
                                     execution_time_ms: float,
                                     success: bool = True,
                                     **kwargs) -> str:
        """
        Record comprehensive metrics for a request execution.
        
        Args:
            node_id: ID of the node that executed the request
            function_name: Name of the executed function
            execution_time_ms: Total execution time in milliseconds
            success: Whether the execution was successful
            **kwargs: Additional metrics (input_size, memory_usage, etc.)
            
        Returns:
            Unique execution ID for this record
            
        Example:
            >>> execution_id = await collector.record_request_execution(
            ...     node_id="gpu-worker-1",
            ...     function_name="train_model",
            ...     execution_time_ms=15000.0,
            ...     success=True,
            ...     input_data_size_bytes=50000000,
            ...     memory_usage_mb=8192.0,
            ...     gpu_usage_percent=85.0
            ... )
        """
        # Create comprehensive metrics record
        metrics = RequestExecutionMetrics(
            node_id=node_id,
            function_name=function_name,
            execution_time_ms=execution_time_ms,
            success=success,
            **{k: v for k, v in kwargs.items() if hasattr(RequestExecutionMetrics, k)}
        )
        
        # Store in various collections for efficient querying
        self._request_metrics.append(metrics)
        self._node_metrics[node_id].append(metrics)
        self._function_metrics[function_name].append(metrics)
        
        # Update collection statistics
        self._collection_stats["total_recorded"] += 1
        
        # Invalidate relevant cache entries
        await self._invalidate_cache_for_node(node_id)
        
        # Real-time analysis if enabled
        if self.enable_real_time_analysis:
            await self._trigger_real_time_analysis(metrics)
        
        self.debug(f"Recorded execution metrics: {function_name}@{node_id} "
                  f"({execution_time_ms:.1f}ms, success={success})")
        
        return metrics.execution_id
    
    async def analyze_node_performance(self, 
                                     node_id: str,
                                     time_window_hours: Optional[float] = None) -> NodePerformanceProfile:
        """
        Perform comprehensive performance analysis for a specific node.
        
        Args:
            node_id: ID of the node to analyze
            time_window_hours: Analysis time window (uses default if None)
            
        Returns:
            Comprehensive performance profile for the node
            
        Raises:
            ValueError: If node has no recorded metrics
        """
        cache_key = f"node_analysis_{node_id}_{time_window_hours or self.analysis_window_hours}"
        
        # Check cache first
        cached_result = await self._get_cached_result(cache_key)
        if cached_result is not None:
            self._collection_stats["cache_hits"] += 1
            return cached_result
        
        self._collection_stats["cache_misses"] += 1
        
        # Perform analysis
        time_window_hours = time_window_hours or self.analysis_window_hours
        cutoff_time = datetime.now() - timedelta(hours=time_window_hours)
        
        # Get metrics for this node within time window
        node_metrics = [
            metric for metric in self._node_metrics[node_id]
            if metric.timestamp >= cutoff_time
        ]
        
        if not node_metrics:
            raise ValueError(f"No metrics found for node {node_id} in the specified time window")
        
        # Calculate comprehensive performance profile
        profile = await self._calculate_node_profile(node_id, node_metrics, time_window_hours)
        
        # Cache the result
        await self._cache_result(cache_key, profile)
        
        self._collection_stats["analysis_count"] += 1
        return profile
    
    async def _calculate_node_profile(self, 
                                    node_id: str, 
                                    metrics: List[RequestExecutionMetrics],
                                    time_window_hours: float) -> NodePerformanceProfile:
        """Calculate comprehensive node performance profile."""
        total_requests = len(metrics)
        successful_requests = sum(1 for m in metrics if m.success)
        failed_requests = total_requests - successful_requests
        
        # Execution time statistics
        execution_times = [m.execution_time_ms for m in metrics]
        avg_execution_time = statistics.mean(execution_times) if execution_times else 0.0
        median_execution_time = statistics.median(execution_times) if execution_times else 0.0
        
        # Percentiles
        p95_execution_time = 0.0
        p99_execution_time = 0.0
        if execution_times:
            sorted_times = sorted(execution_times)
            p95_idx = int(len(sorted_times) * 0.95)
            p99_idx = int(len(sorted_times) * 0.99)
            p95_execution_time = sorted_times[p95_idx] if p95_idx < len(sorted_times) else sorted_times[-1]
            p99_execution_time = sorted_times[p99_idx] if p99_idx < len(sorted_times) else sorted_times[-1]
        
        # Throughput calculation
        if total_requests > 1 and metrics:
            time_span_hours = (max(metrics, key=lambda x: x.timestamp).timestamp - 
                             min(metrics, key=lambda x: x.timestamp).timestamp).total_seconds() / 3600
            requests_per_minute = (total_requests / max(time_span_hours * 60, 1))
        else:
            requests_per_minute = 0.0
        
        # Resource utilization
        cpu_usages = [m.cpu_usage_percent for m in metrics if m.cpu_usage_percent > 0]
        memory_usages = [m.memory_usage_mb for m in metrics if m.memory_usage_mb > 0]
        gpu_usages = [m.gpu_usage_percent for m in metrics if m.gpu_usage_percent > 0]
        
        avg_cpu = statistics.mean(cpu_usages) if cpu_usages else 0.0
        avg_memory = statistics.mean(memory_usages) if memory_usages else 0.0
        avg_gpu = statistics.mean(gpu_usages) if gpu_usages else 0.0
        peak_memory = max(memory_usages) if memory_usages else 0.0
        
        # Efficiency calculation
        efficiency_scores = [m.calculate_efficiency_score() for m in metrics]
        avg_efficiency = statistics.mean(efficiency_scores) if efficiency_scores else 0.0
        
        # Function analysis
        function_counts = defaultdict(int)
        function_times = defaultdict(list)
        for metric in metrics:
            function_counts[metric.function_name] += 1
            function_times[metric.function_name].append(metric.execution_time_ms)
        
        top_functions = sorted(function_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        slowest_functions = [
            (func, statistics.mean(times)) 
            for func, times in function_times.items()
        ]
        slowest_functions.sort(key=lambda x: x[1], reverse=True)
        slowest_functions = slowest_functions[:5]
        
        return NodePerformanceProfile(
            node_id=node_id,
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            average_execution_time_ms=avg_execution_time,
            median_execution_time_ms=median_execution_time,
            p95_execution_time_ms=p95_execution_time,
            p99_execution_time_ms=p99_execution_time,
            requests_per_minute=requests_per_minute,
            efficiency_score=avg_efficiency,
            average_cpu_usage=avg_cpu,
            average_memory_usage=avg_memory,
            average_gpu_usage=avg_gpu,
            peak_memory_usage_mb=peak_memory,
            success_rate=successful_requests / total_requests if total_requests > 0 else 0.0,
            error_rate=failed_requests / total_requests if total_requests > 0 else 0.0,
            analysis_period_hours=time_window_hours,
            top_functions=top_functions,
            slowest_functions=slowest_functions
        )
    
    async def get_system_insights(self) -> SystemPerformanceInsights:
        """
        Generate comprehensive system-wide performance insights.
        
        Returns:
            System performance insights and recommendations
        """
        cache_key = f"system_insights_{self.analysis_window_hours}"
        
        # Check cache
        cached_result = await self._get_cached_result(cache_key)
        if cached_result is not None:
            return cached_result
        
        # Calculate system insights
        cutoff_time = datetime.now() - timedelta(hours=self.analysis_window_hours)
        recent_metrics = [
            metric for metric in self._request_metrics
            if metric.timestamp >= cutoff_time
        ]
        
        if not recent_metrics:
            # Return empty insights if no data
            insights = SystemPerformanceInsights()
        else:
            insights = await self._calculate_system_insights(recent_metrics)
        
        # Cache result
        await self._cache_result(cache_key, insights)
        
        return insights
    
    async def _calculate_system_insights(self, metrics: List[RequestExecutionMetrics]) -> SystemPerformanceInsights:
        """Calculate comprehensive system performance insights."""
        total_requests = len(metrics)
        successful_requests = sum(1 for m in metrics if m.success)
        
        # Node analysis
        active_nodes = set(m.node_id for m in metrics)
        node_request_counts = defaultdict(int)
        
        for metric in metrics:
            node_request_counts[metric.node_id] += 1
        
        # Calculate load distribution variance
        if len(node_request_counts) > 1:
            request_counts = list(node_request_counts.values())
            mean_requests = statistics.mean(request_counts)
            variance = statistics.variance(request_counts)
            load_distribution_variance = variance / (mean_requests ** 2) if mean_requests > 0 else 0
        else:
            load_distribution_variance = 0.0
        
        # System throughput
        if total_requests > 1 and metrics:
            time_span_hours = (max(metrics, key=lambda x: x.timestamp).timestamp - 
                             min(metrics, key=lambda x: x.timestamp).timestamp).total_seconds() / 3600
            system_throughput_rpm = total_requests / max(time_span_hours * 60, 1)
        else:
            system_throughput_rpm = 0.0
        
        # Overall health score
        success_rate = successful_requests / total_requests if total_requests > 0 else 1.0
        efficiency_scores = [m.calculate_efficiency_score() for m in metrics]
        avg_efficiency = statistics.mean(efficiency_scores) if efficiency_scores else 1.0
        
        overall_health_score = (success_rate * 0.6 + avg_efficiency * 0.4)
        
        return SystemPerformanceInsights(
            total_nodes=len(self._node_metrics),
            active_nodes=len(active_nodes),
            total_requests=total_requests,
            system_success_rate=success_rate,
            system_throughput_rpm=system_throughput_rpm,
            load_distribution_variance=load_distribution_variance,
            overall_health_score=overall_health_score,
            efficiency_score=avg_efficiency,
            capacity_utilization=min(system_throughput_rpm / 1000.0, 1.0)  # Normalize
        )
    
    # Utility methods
    async def _get_cached_result(self, cache_key: str) -> Optional[Any]:
        """Get cached analysis result if still valid."""
        async with self._cache_lock:
            if cache_key in self._analysis_cache:
                result, timestamp = self._analysis_cache[cache_key]
                if (datetime.now() - timestamp).total_seconds() < self.cache_duration_seconds:
                    return result
                else:
                    del self._analysis_cache[cache_key]
        return None
    
    async def _cache_result(self, cache_key: str, result: Any):
        """Cache analysis result."""
        async with self._cache_lock:
            self._analysis_cache[cache_key] = (result, datetime.now())
    
    async def _invalidate_cache_for_node(self, node_id: str):
        """Invalidate cache entries related to a specific node."""
        async with self._cache_lock:
            keys_to_remove = [
                key for key in self._analysis_cache.keys()
                if f"node_analysis_{node_id}" in key or "system_insights" in key
            ]
            for key in keys_to_remove:
                del self._analysis_cache[key]
    
    async def _trigger_real_time_analysis(self, metrics: RequestExecutionMetrics) -> None:
        """Trigger real-time analysis for immediate insights."""
        # Lightweight real-time signals without adding heavy computation.
        if not metrics.success:
            self.warning(
                "Real-time alert: execution failed (node=%s, function=%s, error=%s)",
                metrics.node_id,
                metrics.function_name,
                metrics.error_type or "unknown",
            )
            return

        if metrics.execution_time_ms >= 5000.0:
            self.warning(
                "Real-time alert: slow execution detected "
                "(node=%s, function=%s, execution_time_ms=%.2f)",
                metrics.node_id,
                metrics.function_name,
                metrics.execution_time_ms,
            )

        efficiency = metrics.calculate_efficiency_score()
        if efficiency < 0.25:
            self.warning(
                "Real-time alert: low efficiency detected "
                "(node=%s, function=%s, efficiency=%.3f)",
                metrics.node_id,
                metrics.function_name,
                efficiency,
            )
    
    async def _cleanup_loop(self):
        """Background cleanup task."""
        try:
            while self._running:
                await self._cleanup_old_data()
                await asyncio.sleep(3600)  # Run every hour
        except asyncio.CancelledError:
            pass
    
    async def _cleanup_old_data(self):
        """Clean up old performance data to prevent memory bloat."""
        cutoff_time = datetime.now() - timedelta(hours=self.analysis_window_hours * 2)
        
        # Clean main metrics
        while self._request_metrics and self._request_metrics[0].timestamp < cutoff_time:
            self._request_metrics.popleft()
        
        # Clean node-specific metrics
        for node_id in list(self._node_metrics.keys()):
            node_queue = self._node_metrics[node_id]
            while node_queue and node_queue[0].timestamp < cutoff_time:
                node_queue.popleft()
            if not node_queue:
                del self._node_metrics[node_id]
        
        # Clean function-specific metrics
        for function_name in list(self._function_metrics.keys()):
            function_queue = self._function_metrics[function_name]
            while function_queue and function_queue[0].timestamp < cutoff_time:
                function_queue.popleft()
            if not function_queue:
                del self._function_metrics[function_name]
        
        # Clean expired cache entries
        async with self._cache_lock:
            current_time = datetime.now()
            expired_keys = [
                key for key, (_, timestamp) in self._analysis_cache.items()
                if (current_time - timestamp).total_seconds() > self.cache_duration_seconds
            ]
            for key in expired_keys:
                del self._analysis_cache[key]
        
        self.debug("Completed performance data cleanup")
    
    def get_collection_statistics(self) -> Dict[str, Any]:
        """Get performance collection statistics."""
        return {
            **self._collection_stats,
            "metrics_in_memory": len(self._request_metrics),
            "tracked_nodes": len(self._node_metrics),
            "tracked_functions": len(self._function_metrics),
            "cache_entries": len(self._analysis_cache),
            "cache_hit_rate": self._collection_stats["cache_hits"] / 
                             max(self._collection_stats["cache_hits"] + self._collection_stats["cache_misses"], 1)
        }


# Backward compatibility alias
PerformanceCollector = AdvancedPerformanceCollector


# Export all public classes
__all__ = [
    'AdvancedPerformanceCollector',
    'PerformanceCollector',  # Backward compatibility
    'RequestExecutionMetrics',
    'NodePerformanceProfile',
    'SystemPerformanceInsights',
    'PerformanceMetricType',
    'AggregationMethod'
] 
