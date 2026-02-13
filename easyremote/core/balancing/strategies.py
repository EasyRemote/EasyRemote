#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EasyRemote Load Balancing Strategies Module

This module defines the core interfaces, data structures, and strategy patterns
for the EasyRemote distributed computing framework's load balancing system.
It provides a comprehensive foundation for implementing sophisticated load
balancing algorithms with real-time performance monitoring and adaptive routing.

Architecture:
- Strategy Pattern: Abstract base classes for pluggable load balancing algorithms
- Builder Pattern: Fluent configuration objects for load balancing parameters
- Factory Pattern: Strategy creation and registration mechanisms
- Observer Pattern: Real-time statistics and performance monitoring

Key Components:
1. LoadBalancingStrategy: Enumeration of available routing strategies
2. NodeCapabilities: Comprehensive node capability modeling
3. NodeStats: Real-time performance and health metrics
4. RequestContext: Rich request metadata for intelligent routing decisions
5. LoadBalancerInterface: Abstract base class for all balancing algorithms

Design Principles:
- Type Safety: Comprehensive type hints and validation throughout
- Extensibility: Easy addition of new strategies and metrics
- Performance: Optimized data structures for sub-millisecond routing
- Observability: Rich metrics and debugging information
- Reliability: Robust error handling and graceful degradation

Usage Example:
    >>> from easyremote.core.load_balancing.strategies import *
    >>> 
    >>> # Create request context
    >>> context = RequestContext(
    ...     function_name="train_model",
    ...     data_size=1000000,
    ...     complexity_score=3.5,
    ...     requirements={"gpu_required": True, "min_memory_gb": 8}
    ... )
    >>> 
    >>> # Create node statistics
    >>> node_stats = {
    ...     "gpu-node-1": NodeStats(
    ...         node_id="gpu-node-1",
    ...         cpu_usage=45.0,
    ...         memory_usage=60.0,
    ...         gpu_usage=20.0,
    ...         has_gpu=True
    ...     )
    ... }
    >>> 
    >>> # Implement custom load balancer
    >>> class CustomBalancer(LoadBalancerInterface):
    ...     async def select_node(self, available_nodes, request_context, node_stats):
    ...         return self.find_optimal_node(available_nodes, node_stats)

Author: Silan Hu (silan.hu@u.nus.edu)
Version: 2.0.0
Compatibility: Python 3.7+
"""

import time
import uuid
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, List, Any, Optional, Set, Callable
from dataclasses import dataclass, field
from datetime import datetime


class LoadBalancingStrategy(Enum):
    """
    Enumeration of available load balancing strategies.
    
    This enum provides type-safe strategy selection and enables
    easy extension with new load balancing algorithms.
    
    Strategies:
        ROUND_ROBIN: Cyclical distribution across nodes
        RESOURCE_AWARE: CPU, memory, and GPU utilization-based routing
        LATENCY_BASED: Network latency and response time optimization
        COST_AWARE: Budget-conscious routing with cost optimization
        SMART_ADAPTIVE: ML-inspired adaptive routing with learning
        DYNAMIC: Context-aware automatic strategy selection
    """
    ROUND_ROBIN = "round_robin"
    RESOURCE_AWARE = "resource_aware"
    LATENCY_BASED = "latency_based"
    COST_AWARE = "cost_aware"
    SMART_ADAPTIVE = "smart_adaptive"
    DYNAMIC = "dynamic"
    
    @property
    def description(self) -> str:
        """Get human-readable description of the strategy."""
        descriptions = {
            self.ROUND_ROBIN: "Simple round-robin distribution",
            self.RESOURCE_AWARE: "Resource utilization-based routing",
            self.LATENCY_BASED: "Network latency optimization",
            self.COST_AWARE: "Cost-optimized routing",
            self.SMART_ADAPTIVE: "Adaptive ML-based routing",
            self.DYNAMIC: "Automatic strategy selection"
        }
        return descriptions.get(self, "Unknown strategy")
    
    @property
    def complexity_level(self) -> int:
        """Get complexity level of the strategy (1-5, higher is more complex)."""
        complexity = {
            self.ROUND_ROBIN: 1,
            self.RESOURCE_AWARE: 3,
            self.LATENCY_BASED: 2,
            self.COST_AWARE: 4,
            self.SMART_ADAPTIVE: 5,
            self.DYNAMIC: 4
        }
        return complexity.get(self, 3)


class NodeTier(Enum):
    """
    Node performance tier classification.
    
    This enum categorizes nodes based on their computational capabilities
    and performance characteristics for intelligent workload distribution.
    """
    BASIC = "basic"          # Basic compute nodes for simple tasks
    STANDARD = "standard"    # Standard performance nodes
    HIGH_PERFORMANCE = "high_performance"  # High-end compute nodes
    GPU_ACCELERATED = "gpu_accelerated"    # GPU-enabled nodes
    SPECIALIZED = "specialized"            # Specialized hardware nodes


class RequestPriority(Enum):
    """
    Request priority levels for workload scheduling.
    
    Higher priority requests receive preferential treatment in
    node selection and resource allocation.
    """
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"
    
    @property
    def weight(self) -> float:
        """Get numerical weight for priority calculations."""
        weights = {
            self.LOW: 0.5,
            self.NORMAL: 1.0,
            self.HIGH: 2.0,
            self.CRITICAL: 5.0
        }
        return weights[self]


@dataclass
class GeographicLocation:
    """
    Geographic location information for latency optimization.
    
    This class models node and client locations to enable
    geographically-aware load balancing decisions.
    """
    region: str                    # Geographic region (e.g., "us-east-1")
    availability_zone: Optional[str] = None  # Specific AZ within region
    country: Optional[str] = None            # Country code (ISO 3166-1)
    city: Optional[str] = None               # City name
    latitude: Optional[float] = None         # GPS latitude
    longitude: Optional[float] = None        # GPS longitude
    
    def distance_to(self, other: 'GeographicLocation') -> Optional[float]:
        """
        Calculate approximate distance to another location.
        
        Args:
            other: Target location
            
        Returns:
            Distance in kilometers, or None if coordinates unavailable
        """
        if (self.latitude is None or self.longitude is None or
            other.latitude is None or other.longitude is None):
            return None
        
        # Simplified distance calculation (Haversine formula would be more accurate)
        lat_diff = abs(self.latitude - other.latitude)
        lon_diff = abs(self.longitude - other.longitude)
        return ((lat_diff ** 2 + lon_diff ** 2) ** 0.5) * 111.0  # Rough km conversion


@dataclass
class HardwareSpecification:
    """
    Detailed hardware specification for compute nodes.
    
    This class provides comprehensive hardware information enabling
    sophisticated resource matching and performance prediction.
    """
    cpu_model: Optional[str] = None          # CPU model identifier
    cpu_cores: int = 1                       # Number of CPU cores
    cpu_threads: Optional[int] = None        # Number of CPU threads
    cpu_frequency_ghz: Optional[float] = None # Base CPU frequency
    memory_gb: float = 1.0                   # Total memory in GB
    storage_gb: Optional[float] = None       # Available storage in GB
    network_bandwidth_mbps: Optional[float] = None  # Network bandwidth
    
    # GPU specifications
    gpu_count: int = 0                       # Number of GPUs
    gpu_model: Optional[str] = None          # GPU model identifier
    gpu_memory_gb: Optional[float] = None    # GPU memory per device
    gpu_compute_capability: Optional[str] = None  # CUDA compute capability
    
    # Specialized hardware
    has_tpu: bool = False                    # Tensor Processing Unit
    has_fpga: bool = False                   # Field Programmable Gate Array
    custom_accelerators: Set[str] = field(default_factory=set)  # Custom hardware
    
    @property
    def has_gpu(self) -> bool:
        """Check if node has GPU acceleration."""
        return self.gpu_count > 0
    
    @property
    def has_specialized_hardware(self) -> bool:
        """Check if node has specialized acceleration hardware."""
        return self.has_tpu or self.has_fpga or bool(self.custom_accelerators)
    
    def compute_performance_score(self) -> float:
        """
        Calculate overall performance score for this hardware configuration.
        
        Returns:
            Performance score (0.0 to 10.0, higher is better)
        """
        # Base CPU score
        cpu_score = min(self.cpu_cores / 4.0, 2.0)  # Normalize to 4 cores
        if self.cpu_frequency_ghz:
            cpu_score *= min(self.cpu_frequency_ghz / 3.0, 1.5)  # Frequency boost
        
        # Memory score
        memory_score = min(self.memory_gb / 8.0, 2.0)  # Normalize to 8GB
        
        # GPU score
        gpu_score = 0.0
        if self.has_gpu:
            gpu_score = min(self.gpu_count * 2.0, 4.0)  # GPU multiplier
            if self.gpu_memory_gb:
                gpu_score *= min(self.gpu_memory_gb / 8.0, 2.0)  # GPU memory boost
        
        # Specialized hardware bonus
        specialized_bonus = 0.0
        if self.has_specialized_hardware:
            specialized_bonus = 1.0
        
        return min(cpu_score + memory_score + gpu_score + specialized_bonus, 10.0)


@dataclass
class NodeCapabilities:
    """
    Comprehensive node capability and configuration information.
    
    This class encapsulates all aspects of a compute node's capabilities,
    including hardware specifications, software environment, performance
    characteristics, and operational constraints.
    """
    # Hardware specifications
    hardware: HardwareSpecification = field(default_factory=HardwareSpecification)
    
    # Geographic and network information
    location: Optional[GeographicLocation] = None
    network_latency_ms: float = 0.0          # Baseline network latency
    bandwidth_mbps: Optional[float] = None    # Available bandwidth
    
    # Performance characteristics
    tier: NodeTier = NodeTier.STANDARD       # Performance tier classification
    max_concurrent_executions: int = 1       # Maximum parallel executions
    average_execution_time_ms: float = 1000.0  # Typical execution time
    reliability_score: float = 1.0           # Historical reliability (0.0-1.0)
    
    # Cost and billing information
    cost_per_hour: Optional[float] = None    # Hourly cost in USD
    cost_per_execution: Optional[float] = None  # Per-execution cost
    billing_model: str = "time_based"        # Billing model type
    
    # Software and runtime environment
    supported_languages: Set[str] = field(default_factory=lambda: {"python"})
    installed_packages: Set[str] = field(default_factory=set)
    container_runtime: Optional[str] = None   # Docker, containerd, etc.
    operating_system: str = "linux"          # Operating system
    
    # Operational constraints
    maintenance_windows: List[Dict[str, Any]] = field(default_factory=list)
    maximum_runtime_hours: Optional[float] = None  # Maximum job duration
    priority_levels: Set[RequestPriority] = field(
        default_factory=lambda: {RequestPriority.NORMAL}
    )
    
    # Security and compliance
    security_level: str = "standard"         # Security classification
    compliance_certifications: Set[str] = field(default_factory=set)
    data_residency_regions: Set[str] = field(default_factory=set)
    
    def can_handle_request(self, requirements: Dict[str, Any]) -> bool:
        """
        Check if this node can satisfy the given requirements.
        
        Args:
            requirements: Dictionary of requirements to check
            
        Returns:
            True if node can handle the request, False otherwise
        """
        # Check hardware requirements
        if requirements.get("gpu_required", False) and not self.hardware.has_gpu:
            return False
        
        if requirements.get("min_memory_gb", 0) > self.hardware.memory_gb:
            return False
        
        if requirements.get("min_cpu_cores", 0) > self.hardware.cpu_cores:
            return False
        
        # Check language support
        required_language = requirements.get("language", "python")
        if required_language not in self.supported_languages:
            return False
        
        # Check performance tier
        required_tier = requirements.get("performance_tier")
        if required_tier and NodeTier(required_tier) != self.tier:
            return False
        
        # Check cost constraints
        max_cost = requirements.get("max_cost_per_hour")
        if max_cost and self.cost_per_hour and self.cost_per_hour > max_cost:
            return False
        
        # Check geographic constraints
        required_region = requirements.get("region")
        if (required_region and self.location and 
            self.location.region != required_region):
            return False
        
        return True
    
    def calculate_compatibility_score(self, requirements: Dict[str, Any]) -> float:
        """
        Calculate how well this node matches the given requirements.
        
        Args:
            requirements: Dictionary of requirements
            
        Returns:
            Compatibility score (0.0 to 1.0, higher is better)
        """
        if not self.can_handle_request(requirements):
            return 0.0
        
        score = 1.0
        
        # Hardware matching bonus
        if requirements.get("gpu_required", False) and self.hardware.has_gpu:
            score += 0.2
        
        if requirements.get("specialized_hardware", False) and self.hardware.has_specialized_hardware:
            score += 0.3
        
        # Performance tier matching
        preferred_tier = requirements.get("preferred_tier")
        if preferred_tier and NodeTier(preferred_tier) == self.tier:
            score += 0.1
        
        # Cost efficiency bonus
        max_cost = requirements.get("max_cost_per_hour")
        if max_cost and self.cost_per_hour:
            cost_efficiency = (max_cost - self.cost_per_hour) / max_cost
            score += cost_efficiency * 0.2
        
        # Reliability bonus
        score += self.reliability_score * 0.1
        
        return min(score, 1.0)


@dataclass
class PerformanceMetrics:
    """
    Real-time performance metrics for load balancing decisions.
    
    This class tracks various performance indicators that influence
    load balancing decisions and enable adaptive optimization.
    """
    # Resource utilization metrics
    cpu_usage_percent: float = 0.0          # Current CPU utilization
    memory_usage_percent: float = 0.0       # Current memory utilization
    gpu_usage_percent: float = 0.0          # Current GPU utilization
    disk_io_usage_percent: float = 0.0      # Disk I/O utilization
    network_io_usage_percent: float = 0.0   # Network I/O utilization
    
    # Queue and load metrics
    current_queue_length: int = 0           # Number of queued requests
    active_executions: int = 0              # Currently running jobs
    completed_executions: int = 0           # Total completed jobs
    failed_executions: int = 0              # Total failed jobs
    
    # Timing metrics
    average_response_time_ms: float = 0.0   # Average response time
    last_response_time_ms: float = 0.0      # Most recent response time
    uptime_hours: float = 0.0               # Node uptime
    last_health_check: datetime = field(default_factory=datetime.now)
    
    # Health and status indicators
    is_healthy: bool = True                 # Overall health status
    health_score: float = 1.0               # Health score (0.0-1.0)
    error_rate: float = 0.0                 # Recent error rate
    warning_count: int = 0                  # Active warnings
    
    # Performance history
    cpu_history: List[float] = field(default_factory=list)      # Recent CPU usage
    memory_history: List[float] = field(default_factory=list)   # Recent memory usage
    response_time_history: List[float] = field(default_factory=list)  # Recent response times
    
    def update_resource_usage(self, cpu: float, memory: float, gpu: float = 0.0):
        """
        Update resource utilization metrics.
        
        Args:
            cpu: CPU usage percentage (0.0-100.0)
            memory: Memory usage percentage (0.0-100.0)
            gpu: GPU usage percentage (0.0-100.0)
        """
        self.cpu_usage_percent = max(0.0, min(100.0, cpu))
        self.memory_usage_percent = max(0.0, min(100.0, memory))
        self.gpu_usage_percent = max(0.0, min(100.0, gpu))
        
        # Update history (keep last 10 measurements)
        self.cpu_history.append(self.cpu_usage_percent)
        self.memory_history.append(self.memory_usage_percent)
        if len(self.cpu_history) > 10:
            self.cpu_history.pop(0)
        if len(self.memory_history) > 10:
            self.memory_history.pop(0)
    
    def update_response_time(self, response_time_ms: float):
        """
        Update response time metrics.
        
        Args:
            response_time_ms: Latest response time in milliseconds
        """
        self.last_response_time_ms = response_time_ms
        
        # Update running average
        if self.average_response_time_ms == 0.0:
            self.average_response_time_ms = response_time_ms
        else:
            # Exponential moving average with alpha=0.1
            alpha = 0.1
            self.average_response_time_ms = (
                alpha * response_time_ms + 
                (1 - alpha) * self.average_response_time_ms
            )
        
        # Update history
        self.response_time_history.append(response_time_ms)
        if len(self.response_time_history) > 10:
            self.response_time_history.pop(0)
    
    def calculate_load_score(self) -> float:
        """
        Calculate overall load score for this node.
        
        Returns:
            Load score (0.0 to 1.0, where 0.0 is no load and 1.0 is maximum load)
        """
        # Weight different resource types
        weights = {
            'cpu': 0.4,
            'memory': 0.3,
            'gpu': 0.2,
            'queue': 0.1
        }
        
        # Calculate individual scores
        cpu_score = self.cpu_usage_percent / 100.0
        memory_score = self.memory_usage_percent / 100.0
        gpu_score = self.gpu_usage_percent / 100.0
        queue_score = min(self.current_queue_length / 10.0, 1.0)  # Normalize to 10 queued items
        
        # Calculate weighted load score
        load_score = (
            weights['cpu'] * cpu_score +
            weights['memory'] * memory_score +
            weights['gpu'] * gpu_score +
            weights['queue'] * queue_score
        )
        
        return min(load_score, 1.0)
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate based on completed vs failed executions."""
        total_executions = self.completed_executions + self.failed_executions
        if total_executions == 0:
            return 1.0
        return self.completed_executions / total_executions


@dataclass
class NodeStats:
    """
    Consolidated real-time node statistics for load balancing decisions.
    
    This class combines performance metrics, capabilities, and status
    information to provide a complete view of node state for routing decisions.
    """
    # Core identification
    node_id: str
    
    # Legacy compatibility fields (maintained for backward compatibility)
    cpu_usage: float = 0.0                  # CPU usage percentage
    memory_usage: float = 0.0               # Memory usage percentage
    gpu_usage: float = 0.0                  # GPU usage percentage
    current_load: float = 0.0               # Overall load factor
    queue_length: int = 0                   # Queue length
    response_time: float = 0.0              # Response time in ms
    success_rate: float = 1.0               # Success rate
    has_gpu: bool = False                   # GPU availability
    last_updated: float = field(default_factory=time.time)  # Last update timestamp
    
    # Enhanced metrics and capabilities
    capabilities: Optional[NodeCapabilities] = None
    performance_metrics: Optional[PerformanceMetrics] = None
    
    # Predictive and historical data
    predicted_load: Optional[float] = None   # Predicted future load
    load_trend: Optional[str] = None         # Load trend: "increasing", "decreasing", "stable"
    performance_rank: Optional[int] = None   # Relative performance rank
    
    def __post_init__(self):
        """Initialize derived fields and ensure data consistency."""
        # Create default performance metrics if not provided
        if self.performance_metrics is None:
            self.performance_metrics = PerformanceMetrics(
                cpu_usage_percent=self.cpu_usage,
                memory_usage_percent=self.memory_usage,
                gpu_usage_percent=self.gpu_usage,
                current_queue_length=self.queue_length,
                average_response_time_ms=self.response_time,
                last_response_time_ms=self.response_time
            )
        
        # Sync legacy fields with performance metrics
        self._sync_legacy_fields()
    
    def _sync_legacy_fields(self):
        """Synchronize legacy fields with performance metrics."""
        if self.performance_metrics:
            self.cpu_usage = self.performance_metrics.cpu_usage_percent
            self.memory_usage = self.performance_metrics.memory_usage_percent
            self.gpu_usage = self.performance_metrics.gpu_usage_percent
            self.queue_length = self.performance_metrics.current_queue_length
            self.response_time = self.performance_metrics.average_response_time_ms
            self.success_rate = self.performance_metrics.success_rate
            self.current_load = self.performance_metrics.calculate_load_score()
        
        # Sync GPU availability
        if self.capabilities and self.capabilities.hardware:
            self.has_gpu = self.capabilities.hardware.has_gpu
    
    def update_metrics(self, 
                      cpu_usage: Optional[float] = None,
                      memory_usage: Optional[float] = None,
                      gpu_usage: Optional[float] = None,
                      response_time: Optional[float] = None):
        """
        Update node statistics with new measurements.
        
        Args:
            cpu_usage: New CPU usage percentage
            memory_usage: New memory usage percentage
            gpu_usage: New GPU usage percentage
            response_time: New response time in milliseconds
        """
        if not self.performance_metrics:
            self.performance_metrics = PerformanceMetrics()
        
        if cpu_usage is not None or memory_usage is not None or gpu_usage is not None:
            self.performance_metrics.update_resource_usage(
                cpu_usage or self.cpu_usage,
                memory_usage or self.memory_usage,
                gpu_usage or self.gpu_usage
            )
        
        if response_time is not None:
            self.performance_metrics.update_response_time(response_time)
        
        self.last_updated = time.time()
        self._sync_legacy_fields()
    
    def is_overloaded(self, 
                     cpu_threshold: float = 90.0,
                     memory_threshold: float = 85.0,
                     queue_threshold: int = 10) -> bool:
        """
        Check if node is currently overloaded.
        
        Args:
            cpu_threshold: CPU usage threshold percentage
            memory_threshold: Memory usage threshold percentage
            queue_threshold: Queue length threshold
            
        Returns:
            True if node is overloaded, False otherwise
        """
        return (
            self.cpu_usage > cpu_threshold or
            self.memory_usage > memory_threshold or
            self.queue_length > queue_threshold
        )
    
    def calculate_suitability_score(self, request_context: 'RequestContext') -> float:
        """
        Calculate how suitable this node is for the given request.
        
        Args:
            request_context: Context information about the request
            
        Returns:
            Suitability score (0.0 to 1.0, higher is better)
        """
        # Base score from load (inverted - lower load is better)
        base_score = 1.0 - self.current_load
        
        # Capability compatibility
        capability_score = 1.0
        if self.capabilities and request_context.requirements:
            capability_score = self.capabilities.calculate_compatibility_score(
                request_context.requirements
            )
        
        # Performance score
        performance_score = 1.0
        if self.performance_metrics:
            # Factor in success rate and health
            performance_score = (
                self.performance_metrics.success_rate * 0.5 +
                self.performance_metrics.health_score * 0.5
            )
        
        # Priority adjustment
        priority_adjustment = 1.0
        if hasattr(request_context, 'priority'):
            priority = RequestPriority(request_context.priority)
            priority_adjustment = priority.weight
        
        # Calculate final score
        final_score = (
            base_score * 0.4 +
            capability_score * 0.3 +
            performance_score * 0.3
        ) * min(priority_adjustment, 2.0)  # Cap priority boost
        
        return min(final_score, 1.0)


@dataclass
class RequestContext:
    """
    Comprehensive context information for load balancing requests.
    
    This class encapsulates all relevant information about a request
    that influences load balancing decisions, including functional
    requirements, performance expectations, and operational constraints.
    """
    # Core request identification
    function_name: str
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    
    # Data and complexity characteristics
    data_size: int = 0                       # Input data size in bytes
    complexity_score: float = 1.0           # Computational complexity (1.0-10.0)
    estimated_execution_time_ms: Optional[float] = None  # Expected runtime
    
    # Resource requirements
    requirements: Optional[Dict[str, Any]] = None  # Detailed requirements
    min_memory_gb: Optional[float] = None           # Minimum memory needed
    min_cpu_cores: Optional[int] = None             # Minimum CPU cores needed
    gpu_required: bool = False                      # Whether GPU is required
    specialized_hardware: Optional[Set[str]] = None # Specialized hardware needs
    
    # Geographic and network preferences
    client_location: Optional[GeographicLocation] = None  # Client location
    preferred_regions: Optional[Set[str]] = None           # Preferred regions
    max_network_latency_ms: Optional[float] = None        # Max acceptable latency
    
    # Performance and timing constraints
    priority: RequestPriority = RequestPriority.NORMAL    # Request priority
    deadline: Optional[datetime] = None                    # Hard deadline
    timeout: Optional[float] = None                        # Execution timeout
    max_retries: int = 3                                  # Maximum retry attempts
    
    # Cost and billing constraints
    cost_limit: Optional[float] = None                    # Maximum cost limit
    cost_preference: str = "balanced"                     # "cost_optimized", "balanced", "performance_optimized"
    billing_account: Optional[str] = None                 # Billing account ID
    
    # Security and compliance requirements
    security_level: str = "standard"                      # Security level required
    data_classification: str = "internal"                 # Data classification
    compliance_requirements: Set[str] = field(default_factory=set)  # Compliance needs
    encryption_required: bool = False                     # Encryption requirement
    
    # Runtime environment preferences
    preferred_language: str = "python"                    # Programming language
    container_image: Optional[str] = None                 # Container image to use
    environment_variables: Dict[str, str] = field(default_factory=dict)  # Environment vars
    
    # Monitoring and observability
    enable_detailed_metrics: bool = False                 # Enable detailed monitoring
    trace_request: bool = False                           # Enable request tracing
    custom_tags: Dict[str, str] = field(default_factory=dict)  # Custom metadata tags
    
    # Legacy compatibility fields
    client_location_dict: Optional[Dict[str, Any]] = None  # Legacy location format
    
    def __post_init__(self):
        """Initialize derived fields and validate constraints."""
        # Convert legacy location format if provided
        if self.client_location_dict and not self.client_location:
            self.client_location = GeographicLocation(**self.client_location_dict)
        
        # Validate complexity score
        self.complexity_score = max(1.0, min(10.0, self.complexity_score))
        
        # Initialize requirements dict if needed
        if self.requirements is None:
            self.requirements = {}
        
        # Populate requirements from individual fields
        if self.min_memory_gb is not None:
            self.requirements["min_memory_gb"] = self.min_memory_gb
        if self.min_cpu_cores is not None:
            self.requirements["min_cpu_cores"] = self.min_cpu_cores
        if self.gpu_required:
            self.requirements["gpu_required"] = True
        if self.specialized_hardware:
            self.requirements["specialized_hardware"] = self.specialized_hardware
    
    def estimate_resource_needs(self) -> Dict[str, float]:
        """
        Estimate resource needs based on request characteristics.
        
        Returns:
            Dictionary with estimated resource requirements
        """
        # Base resource estimation
        base_cpu = 1.0
        base_memory_gb = 1.0
        base_gpu_usage = 0.0
        
        # Scale based on complexity
        cpu_multiplier = min(self.complexity_score / 2.0, 4.0)
        memory_multiplier = min(self.complexity_score / 3.0, 3.0)
        
        # Scale based on data size
        data_size_gb = self.data_size / (1024 ** 3)  # Convert to GB
        memory_multiplier += data_size_gb * 0.5  # Assume 0.5x memory overhead per GB data
        
        # GPU estimation
        if self.gpu_required:
            base_gpu_usage = 0.5  # Assume moderate GPU usage
            if self.complexity_score > 5.0:
                base_gpu_usage = min(0.8, base_gpu_usage + (self.complexity_score - 5.0) / 10.0)
        
        return {
            "estimated_cpu_cores": base_cpu * cpu_multiplier,
            "estimated_memory_gb": base_memory_gb * memory_multiplier,
            "estimated_gpu_usage": base_gpu_usage,
            "estimated_execution_time_ms": self._estimate_execution_time()
        }
    
    def _estimate_execution_time(self) -> float:
        """Estimate execution time based on request characteristics."""
        if self.estimated_execution_time_ms:
            return self.estimated_execution_time_ms
        
        # Base estimation: 1 second for simple tasks
        base_time_ms = 1000.0
        
        # Scale by complexity
        complexity_factor = self.complexity_score ** 1.5
        
        # Scale by data size (assume 100ms per MB)
        data_factor = (self.data_size / (1024 * 1024)) * 100.0
        
        return base_time_ms * complexity_factor + data_factor
    
    def is_time_critical(self) -> bool:
        """Check if this request is time-critical."""
        if self.priority in (RequestPriority.HIGH, RequestPriority.CRITICAL):
            return True
        
        if self.deadline:
            time_until_deadline = (self.deadline - datetime.now()).total_seconds()
            return time_until_deadline < 300  # Less than 5 minutes
        
        return False


@dataclass
class LoadBalancingConfig:
    """
    Comprehensive configuration for load balancing behavior.
    
    This class provides fine-grained control over load balancing
    algorithms, fallback strategies, and operational parameters.
    """
    # Core strategy configuration
    strategy: LoadBalancingStrategy = LoadBalancingStrategy.RESOURCE_AWARE
    fallback_strategy: Optional[LoadBalancingStrategy] = LoadBalancingStrategy.ROUND_ROBIN
    
    # Requirements and preferences
    requirements: Optional[Dict[str, Any]] = None
    preferences: Optional[Dict[str, Any]] = None
    
    # Health and monitoring configuration
    health_check_enabled: bool = True
    health_check_interval_seconds: float = 30.0
    health_check_timeout_seconds: float = 5.0
    
    # Performance and scaling configuration
    scaling_enabled: bool = True
    auto_scaling_thresholds: Dict[str, float] = field(default_factory=lambda: {
        "cpu_scale_up": 80.0,
        "cpu_scale_down": 20.0,
        "memory_scale_up": 85.0,
        "memory_scale_down": 25.0,
        "queue_scale_up": 5.0,
        "queue_scale_down": 1.0
    })
    
    # Budget and cost configuration
    budget_enabled: bool = False
    budget_limit_hourly: Optional[float] = None
    budget_limit_daily: Optional[float] = None
    cost_optimization_priority: float = 0.5  # 0.0 = performance, 1.0 = cost
    
    # Timing and retry configuration
    timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_backoff_multiplier: float = 2.0
    circuit_breaker_enabled: bool = True
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_time_seconds: float = 60.0
    
    # Geographic and network configuration
    region_preference: Optional[str] = None
    multi_region_enabled: bool = False
    cross_region_latency_penalty_ms: float = 50.0
    
    # Security and compliance configuration
    enforce_security_level: bool = True
    required_compliance_certifications: Set[str] = field(default_factory=set)
    data_residency_enforcement: bool = False
    
    # Advanced features
    predictive_scaling_enabled: bool = False
    machine_learning_optimization: bool = False
    custom_metrics_enabled: bool = False
    custom_balancing_functions: Dict[str, Callable] = field(default_factory=dict)
    
    def validate_configuration(self) -> List[str]:
        """
        Validate the load balancing configuration.
        
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        # Validate timeout values
        if self.timeout_seconds <= 0:
            errors.append("timeout_seconds must be positive")
        
        if self.health_check_interval_seconds <= 0:
            errors.append("health_check_interval_seconds must be positive")
        
        if self.health_check_timeout_seconds <= 0:
            errors.append("health_check_timeout_seconds must be positive")
        
        # Validate retry configuration
        if self.max_retries < 0:
            errors.append("max_retries must be non-negative")
        
        if self.retry_backoff_multiplier < 1.0:
            errors.append("retry_backoff_multiplier must be >= 1.0")
        
        # Validate budget configuration
        if self.budget_enabled:
            if self.budget_limit_hourly is not None and self.budget_limit_hourly <= 0:
                errors.append("budget_limit_hourly must be positive when budget is enabled")
            
            if self.budget_limit_daily is not None and self.budget_limit_daily <= 0:
                errors.append("budget_limit_daily must be positive when budget is enabled")
        
        # Validate cost optimization priority
        if not (0.0 <= self.cost_optimization_priority <= 1.0):
            errors.append("cost_optimization_priority must be between 0.0 and 1.0")
        
        # Validate circuit breaker configuration
        if self.circuit_breaker_enabled:
            if self.circuit_breaker_failure_threshold <= 0:
                errors.append("circuit_breaker_failure_threshold must be positive")
            
            if self.circuit_breaker_recovery_time_seconds <= 0:
                errors.append("circuit_breaker_recovery_time_seconds must be positive")
        
        return errors


class LoadBalancerInterface(ABC):
    """
    Abstract base class for all load balancing strategy implementations.
    
    This interface defines the contract that all load balancing algorithms
    must implement, ensuring consistent behavior and enabling pluggable
    strategy implementations.
    
    Key Responsibilities:
    1. Node Selection: Choose optimal node for request execution
    2. Strategy Identification: Provide strategy name and metadata
    3. Performance Tracking: Support for performance monitoring
    4. Configuration: Handle strategy-specific configuration
    
    Implementation Guidelines:
    - Implement async node selection for high performance
    - Provide meaningful strategy names and descriptions
    - Handle edge cases gracefully (empty node lists, etc.)
    - Log important decisions for debugging and monitoring
    - Support configuration validation and error handling
    
    Example Implementation:
        >>> class CustomLoadBalancer(LoadBalancerInterface):
        ...     async def select_node(self, available_nodes, request_context, node_stats):
        ...         # Custom selection logic
        ...         return self._find_best_node(available_nodes, node_stats)
        ...     
        ...     def get_strategy_name(self) -> str:
        ...         return "custom_algorithm"
        ...     
        ...     def get_strategy_description(self) -> str:
        ...         return "Custom algorithm optimized for specific workloads"
    """
    
    @abstractmethod
    async def select_node(self, 
                         available_nodes: List[str], 
                         request_context: RequestContext,
                         node_stats: Dict[str, NodeStats]) -> str:
        """
        Select the optimal node for executing the given request.
        
        This is the core method that implements the load balancing algorithm.
        It should analyze available nodes, consider request requirements, and
        select the most appropriate node for execution.
        
        Args:
            available_nodes: List of node IDs that can handle the request
            request_context: Comprehensive request context and requirements
            node_stats: Real-time statistics for all available nodes
            
        Returns:
            Node ID of the selected optimal node
            
        Raises:
            NoAvailableNodesError: When no suitable nodes are available
            LoadBalancingError: When the selection algorithm fails
            
        Implementation Notes:
        - Must handle empty available_nodes list gracefully
        - Should consider all relevant factors from request_context
        - Must return a node ID that exists in available_nodes
        - Should be efficient for sub-millisecond routing decisions
        - Should log selection reasoning for debugging
        
        Example:
            >>> balancer = MyLoadBalancer()
            >>> context = RequestContext(function_name="process_data")
            >>> nodes = ["node-1", "node-2", "node-3"]
            >>> stats = {node: NodeStats(node_id=node, ...) for node in nodes}
            >>> selected = await balancer.select_node(nodes, context, stats)
            >>> print(f"Selected node: {selected}")
        """
        pass
    
    @abstractmethod
    def get_strategy_name(self) -> str:
        """
        Get the unique identifier name for this load balancing strategy.
        
        Returns:
            Strategy name string (should be lowercase with underscores)
            
        Example:
            >>> balancer.get_strategy_name()
            'resource_aware'
        """
        pass
    
    def get_strategy_description(self) -> str:
        """
        Get a human-readable description of this load balancing strategy.
        
        Returns:
            Strategy description string
            
        Example:
            >>> balancer.get_strategy_description()
            'Resource-aware load balancing based on CPU, memory, and GPU utilization'
        """
        return f"Load balancing strategy: {self.get_strategy_name()}"
    
    def get_strategy_complexity(self) -> int:
        """
        Get the complexity level of this strategy (1-5, higher is more complex).
        
        Returns:
            Complexity level integer
        """
        return 3  # Default complexity level
    
    def supports_prediction(self) -> bool:
        """
        Check if this strategy supports predictive load balancing.
        
        Returns:
            True if strategy supports prediction, False otherwise
        """
        return False
    
    def supports_learning(self) -> bool:
        """
        Check if this strategy supports machine learning adaptation.
        
        Returns:
            True if strategy supports learning, False otherwise
        """
        return False
    
    def validate_configuration(self, config: LoadBalancingConfig) -> List[str]:
        """
        Validate strategy-specific configuration.
        
        Args:
            config: Load balancing configuration to validate
            
        Returns:
            List of validation error messages (empty if valid)
        """
        return []  # Default: no validation errors
    
    def reset_state(self):
        """
        Reset any internal state maintained by the strategy.
        
        This method should be called when restarting or reconfiguring
        the load balancer to ensure clean state.
        """
        pass  # Default: no state to reset


# Export all public classes and enums
__all__ = [
    # Core enums
    'LoadBalancingStrategy',
    'NodeTier',
    'RequestPriority',
    
    # Data structures
    'GeographicLocation',
    'HardwareSpecification',
    'NodeCapabilities',
    'PerformanceMetrics',
    'NodeStats',
    'RequestContext',
    'LoadBalancingConfig',
    
    # Interfaces
    'LoadBalancerInterface'
] 
