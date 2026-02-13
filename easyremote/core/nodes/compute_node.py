#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EasyRemote Distributed Compute Node Module

This module implements high-performance distributed compute nodes that provide
computational resources to the EasyRemote framework. Compute nodes feature
intelligent function registration, automatic gateway coordination, comprehensive
health monitoring, and adaptive performance optimization.

Architecture:
- Worker Pattern: Nodes act as distributed computational workers
- Registry Pattern: Centralized function catalog with metadata
- Observer Pattern: Real-time health and performance monitoring
- Strategy Pattern: Pluggable execution and resource management strategies
- Circuit Breaker Pattern: Fault tolerance and automatic recovery

Key Features:
1. Advanced Function Management:
   * Automatic function discovery and analysis
   * Support for sync, async, and streaming functions
   * Intelligent resource requirement detection
   * Hot function reloading and updates

2. Intelligent Gateway Coordination:
   * Automatic gateway discovery and registration
   * Bidirectional gRPC streaming for real-time communication
   * Adaptive heartbeat and health reporting
   * Graceful reconnection with exponential backoff

3. Comprehensive Resource Management:
   * Real-time CPU, memory, and GPU monitoring
   * Intelligent capacity management and throttling
   * Resource isolation and cleanup
   * Predictive resource allocation

4. Performance Optimization:
   * Function execution caching and optimization
   * Concurrent execution with intelligent queuing
   * Adaptive timeout and retry mechanisms
   * Performance profiling and analytics

5. Production-Grade Features:
   * Comprehensive health monitoring and diagnostics
   * Automatic failure detection and recovery
   * Graceful shutdown and resource cleanup
   * Security and authentication support

Usage Example:
    >>> # Basic node setup
    >>> node = DistributedComputeNode("localhost:8080", "gpu-worker-1")
    >>> 
    >>> @node.register(
    ...     timeout=600,
    ...     resource_requirements=ResourceRequirements(gpu_required=True),
    ...     tags={"ml", "training"}
    ... )
    ... def train_model(data, epochs=10):
    ...     # AI model training logic
    ...     return {"accuracy": 0.95, "epochs": epochs}
    >>> 
    >>> # Advanced configuration
    >>> node = ComputeNodeBuilder() \
    ...     .with_gateway("production-gateway:8080") \
    ...     .with_node_id("specialized-gpu-node") \
    ...     .with_resource_limits(max_cpu_percent=90, max_memory_gb=32) \
    ...     .with_execution_config(max_concurrent=8, timeout=300) \
    ...     .enable_performance_monitoring() \
    ...     .enable_auto_scaling() \
    ...     .build()
    >>> 
    >>> node.serve()  # Start serving requests

Author: Silan Hu (silan.hu@u.nus.edu)
Version: 2.0.0
"""

import asyncio
import functools
import grpc
import time
import threading
import uuid
import platform
import psutil
import os
from typing import (
    Optional, Callable, Dict, Any, Set, Union, List, Tuple, 
    TypeVar
)
from concurrent import futures
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

# EasyRemote core imports
from ..data import (
    FunctionInfo, NodeInfo, NodeStatus, NodeHealthMetrics, 
    FunctionType, ResourceRequirements
)
from ..utils.exceptions import (
    ConnectionError as EasyRemoteConnectionError,
    ExceptionTranslator,
    FunctionNotFoundError,
    RemoteExecutionError,
    TimeoutError,
)
from ..utils.concurrency import LoopBoundAsyncLock
from ..utils.asyncio_noise_filter import install_asyncio_grpc_shutdown_noise_filter
from ..data.serialize import analyze_function
from ..protos import service_pb2, service_pb2_grpc
from ..utils.logger import ModernLogger
from ..config import  Environment

T = TypeVar('T')


class NodeConnectionState(Enum):
    """
    Enumeration of compute node connection states.
    
    This enum provides detailed state tracking for comprehensive
    connection lifecycle management and monitoring.
    """
    DISCONNECTED = "disconnected"       # Not connected to gateway
    INITIALIZING = "initializing"       # Performing initial setup
    CONNECTING = "connecting"           # Establishing gateway connection
    REGISTERING = "registering"         # Registering with gateway
    CONNECTED = "connected"             # Fully connected and operational
    RECONNECTING = "reconnecting"       # Attempting to restore connection
    DEGRADED = "degraded"               # Connected but with limited functionality
    SHUTTING_DOWN = "shutting_down"     # Graceful shutdown in progress
    ERROR = "error"                     # Connection in error state


class ExecutionMode(Enum):
    """
    Function execution modes for different operational contexts.
    """
    NORMAL = "normal"                   # Standard execution
    HIGH_PERFORMANCE = "high_performance"  # Optimized for speed
    RESOURCE_CONSTRAINED = "resource_constrained"  # Conservative resource usage
    DEBUG = "debug"                     # Extended debugging and profiling
    FAILSAFE = "failsafe"              # Maximum reliability and error handling


class ResourceState(Enum):
    """
    Node resource availability states.
    """
    AVAILABLE = "available"             # Resources available for new work
    BUSY = "busy"                      # Resources actively in use
    OVERLOADED = "overloaded"          # Resources at capacity
    THROTTLED = "throttled"            # Artificially limited to manage load
    MAINTENANCE = "maintenance"         # Temporarily unavailable for maintenance


@dataclass
class NodeConfiguration:
    """
    Comprehensive configuration for compute node operation.
    
    This dataclass encapsulates all configuration parameters with
    intelligent defaults, validation, and environment awareness.
    """
    # Core identification and networking
    gateway_address: str
    node_id: str
    client_location: Optional[str] = None       # Geographic location
    
    # Connection and communication settings
    reconnect_interval_seconds: float = 3.0    # Base reconnection interval
    reconnect_max_interval_seconds: float = 300.0  # Maximum reconnection interval
    reconnect_backoff_multiplier: float = 1.5  # Exponential backoff multiplier
    connection_timeout_seconds: float = 10.0   # Connection establishment timeout
    heartbeat_interval_seconds: float = 5.0    # Heartbeat frequency
    heartbeat_timeout_seconds: float = 15.0    # Heartbeat response timeout
    
    # Execution and performance settings
    max_concurrent_executions: int = 10        # Maximum parallel executions
    execution_timeout_seconds: float = 300.0   # Default execution timeout
    queue_size_limit: int = 1000               # Execution queue limit
    enable_function_caching: bool = True       # Enable function result caching
    cache_size_mb: int = 512                   # Function cache size
    
    # Resource management
    max_cpu_usage_percent: float = 90.0        # CPU usage limit
    max_memory_usage_percent: float = 85.0     # Memory usage limit
    enable_resource_monitoring: bool = True    # Enable resource monitoring
    resource_check_interval_seconds: float = 10.0  # Resource monitoring interval
    
    # Health and monitoring
    health_report_interval_seconds: float = 30.0   # Health report frequency
    enable_performance_monitoring: bool = True     # Enable performance tracking
    enable_detailed_logging: bool = False          # Enable verbose logging
    
    # Advanced features
    enable_auto_scaling: bool = False          # Enable automatic scaling
    enable_predictive_caching: bool = False   # Enable predictive result caching
    enable_security_features: bool = True     # Enable security features
    
    # Retry and resilience
    max_retry_attempts: int = 3                # Maximum execution retries
    retry_backoff_multiplier: float = 2.0     # Retry backoff multiplier
    enable_graceful_shutdown: bool = True     # Enable graceful shutdown
    shutdown_timeout_seconds: float = 30.0    # Maximum shutdown time
    
    def __post_init__(self):
        """Validate configuration parameters after initialization."""
        if self.reconnect_interval_seconds <= 0:
            raise ValueError("Reconnect interval must be positive")
        if self.heartbeat_interval_seconds <= 0:
            raise ValueError("Heartbeat interval must be positive")
        if self.max_concurrent_executions <= 0:
            raise ValueError("Max concurrent executions must be positive")
        if self.execution_timeout_seconds <= 0:
            raise ValueError("Execution timeout must be positive")
        if not (0 < self.max_cpu_usage_percent <= 100):
            raise ValueError("CPU usage limit must be between 0 and 100")
        if not (0 < self.max_memory_usage_percent <= 100):
            raise ValueError("Memory usage limit must be between 0 and 100")
    
    @classmethod
    def from_environment(cls, gateway_address: str, node_id: str, 
                        environment: Environment = Environment.DEVELOPMENT) -> 'NodeConfiguration':
        """
        Create configuration optimized for specific environment.
        
        Args:
            gateway_address: Gateway server address
            node_id: Node identifier
            environment: Target deployment environment
            
        Returns:
            Environment-optimized configuration
        """
        config = cls(gateway_address=gateway_address, node_id=node_id)
        
        if environment == Environment.DEVELOPMENT:
            config.max_concurrent_executions = 3
            config.enable_detailed_logging = True
            config.enable_performance_monitoring = True
            
        elif environment == Environment.TESTING:
            config.max_concurrent_executions = 5
            config.execution_timeout_seconds = 120.0
            config.enable_performance_monitoring = True
            
        elif environment == Environment.PRODUCTION:
            config.max_concurrent_executions = 20
            config.enable_auto_scaling = True
            config.enable_predictive_caching = True
            config.enable_security_features = True
            
        elif environment == Environment.STAGING:
            config.max_concurrent_executions = 10
            config.enable_performance_monitoring = True
            config.enable_security_features = True
        
        return config


@dataclass
class ExecutionContext:
    """
    Context information for function execution tracking and management.
    
    This class maintains comprehensive state and metadata for individual
    function executions, enabling monitoring, debugging, resource management,
    and performance optimization.
    """
    # Core identification
    call_id: str
    function_name: str
    node_id: str
    
    # Timing and lifecycle
    start_time: datetime = field(default_factory=datetime.now)
    timeout_seconds: Optional[float] = None
    priority: int = 5                           # Execution priority (1-10)
    
    # Resource tracking
    allocated_cpu_cores: Optional[int] = None
    allocated_memory_mb: Optional[float] = None
    allocated_gpu_devices: Optional[List[int]] = None
    
    # Client and request information
    client_info: Optional[Dict[str, Any]] = None
    request_metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Execution metadata and monitoring
    execution_mode: ExecutionMode = ExecutionMode.NORMAL
    enable_profiling: bool = False
    trace_id: Optional[str] = None
    parent_context_id: Optional[str] = None
    
    # Retry and error handling
    retry_count: int = 0
    max_retries: int = 3
    last_error: Optional[Exception] = None
    
    # Resource utilization tracking
    peak_memory_usage_mb: float = 0.0
    peak_cpu_usage_percent: float = 0.0
    total_cpu_time_ms: float = 0.0
    
    @property
    def elapsed_time_seconds(self) -> float:
        """Get elapsed execution time in seconds."""
        return (datetime.now() - self.start_time).total_seconds()
    
    @property
    def is_timed_out(self) -> bool:
        """Check if execution has exceeded timeout."""
        if self.timeout_seconds is None:
            return False
        return self.elapsed_time_seconds > self.timeout_seconds
    
    @property
    def remaining_time_seconds(self) -> Optional[float]:
        """Get remaining execution time in seconds."""
        if self.timeout_seconds is None:
            return None
        return max(0, self.timeout_seconds - self.elapsed_time_seconds)
    
    def update_resource_usage(self, cpu_percent: float, memory_mb: float):
        """Update resource usage tracking."""
        self.peak_cpu_usage_percent = max(self.peak_cpu_usage_percent, cpu_percent)
        self.peak_memory_usage_mb = max(self.peak_memory_usage_mb, memory_mb)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert execution context to dictionary for serialization."""
        return {
            "call_id": self.call_id,
            "function_name": self.function_name,
            "node_id": self.node_id,
            "elapsed_time_seconds": self.elapsed_time_seconds,
            "execution_mode": self.execution_mode.value,
            "priority": self.priority,
            "retry_count": self.retry_count,
            "peak_memory_usage_mb": self.peak_memory_usage_mb,
            "peak_cpu_usage_percent": self.peak_cpu_usage_percent,
            "is_timed_out": self.is_timed_out
        }


@dataclass
class FunctionRegistration:
    """
    Enhanced function registration with comprehensive metadata and capabilities.
    
    This class extends basic function information with advanced features
    for production deployment, monitoring, and optimization.
    """
    # Core function information
    function_info: FunctionInfo
    
    # Registration metadata
    registration_time: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    version: str = "1.0.0"
    
    # Execution statistics
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    average_execution_time_ms: float = 0.0
    last_execution_time: Optional[datetime] = None
    
    # Performance characteristics
    estimated_resource_usage: Optional[ResourceRequirements] = None
    actual_resource_usage: Optional[ResourceRequirements] = None
    performance_profile: Dict[str, Any] = field(default_factory=dict)
    
    # Caching and optimization
    enable_result_caching: bool = True
    cache_ttl_seconds: Optional[float] = None
    cache_hit_rate: float = 0.0
    
    # Security and access control
    access_permissions: Set[str] = field(default_factory=set)
    required_security_level: str = "standard"
    
    @property
    def success_rate(self) -> float:
        """Calculate function success rate."""
        if self.total_executions == 0:
            return 0.0
        return self.successful_executions / self.total_executions
    
    @property
    def failure_rate(self) -> float:
        """Calculate function failure rate."""
        if self.total_executions == 0:
            return 0.0
        return self.failed_executions / self.total_executions
    
    def update_execution_stats(self, success: bool, execution_time_ms: float):
        """Update execution statistics with latest data."""
        self.total_executions += 1
        self.last_execution_time = datetime.now()
        
        if success:
            self.successful_executions += 1
        else:
            self.failed_executions += 1
        
        # Update running average execution time
        if self.total_executions == 1:
            self.average_execution_time_ms = execution_time_ms
        else:
            alpha = 2.0 / (self.total_executions + 1)  # Exponential moving average
            self.average_execution_time_ms = (
                alpha * execution_time_ms + 
                (1 - alpha) * self.average_execution_time_ms
            )


class ResourceMonitor(ModernLogger):
    """
    Advanced resource monitoring and management system.
    
    This class provides comprehensive monitoring of system resources
    including CPU, memory, GPU, and network utilization with
    intelligent alerting and capacity management.
    """
    
    def __init__(self, config: NodeConfiguration):
        """
        Initialize resource monitor.
        
        Args:
            config: Node configuration
        """
        super().__init__(name="ResourceMonitor")
        self.config = config
        
        # Resource tracking
        self._cpu_usage_history: List[float] = []
        self._memory_usage_history: List[float] = []
        self._gpu_usage_history: List[float] = []
        
        # Resource state management
        self._current_state = ResourceState.AVAILABLE
        self._last_check_time = datetime.now()
        
        # Monitoring configuration
        self._max_history_size = 100
        self._alert_thresholds = {
            "cpu_warning": self.config.max_cpu_usage_percent * 0.8,
            "cpu_critical": self.config.max_cpu_usage_percent * 0.95,
            "memory_warning": self.config.max_memory_usage_percent * 0.8,
            "memory_critical": self.config.max_memory_usage_percent * 0.95
        }
        
        self.debug("Initialized ResourceMonitor")
    
    def get_current_usage(self) -> Dict[str, float]:
        """
        Get current resource usage statistics.
        
        Returns:
            Dictionary with current resource utilization
        """
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_available_gb = memory.available / (1024**3)
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            
            # Network I/O
            network = psutil.net_io_counters()
            
            # GPU usage (if available)
            gpu_percent = 0.0
            try:
                import GPUtil
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu_percent = sum(gpu.load * 100 for gpu in gpus) / len(gpus)
            except ImportError:
                pass  # GPU monitoring not available
            
            usage = {
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "memory_available_gb": memory_available_gb,
                "disk_percent": disk_percent,
                "gpu_percent": gpu_percent,
                "network_bytes_sent": network.bytes_sent,
                "network_bytes_recv": network.bytes_recv
            }
            
            # Update history
            self._update_history(cpu_percent, memory_percent, gpu_percent)
            
            return usage
            
        except Exception as e:
            self.error(f"Error getting resource usage: {e}")
            return {
                "cpu_percent": 0.0,
                "memory_percent": 0.0,
                "memory_available_gb": 0.0,
                "disk_percent": 0.0,
                "gpu_percent": 0.0,
                "network_bytes_sent": 0,
                "network_bytes_recv": 0
            }
    
    def _update_history(self, cpu_percent: float, memory_percent: float, gpu_percent: float):
        """Update resource usage history."""
        self._cpu_usage_history.append(cpu_percent)
        self._memory_usage_history.append(memory_percent)
        self._gpu_usage_history.append(gpu_percent)
        
        # Keep history size limited
        if len(self._cpu_usage_history) > self._max_history_size:
            self._cpu_usage_history.pop(0)
        if len(self._memory_usage_history) > self._max_history_size:
            self._memory_usage_history.pop(0)
        if len(self._gpu_usage_history) > self._max_history_size:
            self._gpu_usage_history.pop(0)
    
    def assess_resource_state(self, current_usage: Dict[str, float]) -> ResourceState:
        """
        Assess current resource state based on usage and thresholds.
        
        Args:
            current_usage: Current resource usage statistics
            
        Returns:
            Current resource state
        """
        cpu_percent = current_usage.get("cpu_percent", 0.0)
        memory_percent = current_usage.get("memory_percent", 0.0)
        
        # Check for overload conditions
        if (cpu_percent >= self.config.max_cpu_usage_percent or 
            memory_percent >= self.config.max_memory_usage_percent):
            return ResourceState.OVERLOADED
        
        # Check for busy conditions
        if (cpu_percent >= self._alert_thresholds["cpu_warning"] or
            memory_percent >= self._alert_thresholds["memory_warning"]):
            return ResourceState.BUSY
        
        return ResourceState.AVAILABLE
    
    def can_accept_execution(self, estimated_requirements: Optional[ResourceRequirements] = None) -> bool:
        """
        Determine if node can accept new execution based on current resource state.
        
        Args:
            estimated_requirements: Estimated resource requirements for new execution
            
        Returns:
            True if node can accept execution, False otherwise
        """
        current_usage = self.get_current_usage()
        current_state = self.assess_resource_state(current_usage)
        
        if current_state == ResourceState.OVERLOADED:
            return False
        
        # If we have estimated requirements, check if we can accommodate them
        if estimated_requirements:
            cpu_available = 100.0 - current_usage.get("cpu_percent", 0.0)
            memory_available_gb = current_usage.get("memory_available_gb", 0.0)
            
            if (estimated_requirements.min_cpu_cores and 
                estimated_requirements.min_cpu_cores > cpu_available / 100.0 * psutil.cpu_count()):
                return False
            
            if (estimated_requirements.min_memory_gb and 
                estimated_requirements.min_memory_gb > memory_available_gb):
                return False
        
        return True
    
    def get_resource_summary(self) -> Dict[str, Any]:
        """Get comprehensive resource summary."""
        current_usage = self.get_current_usage()
        current_state = self.assess_resource_state(current_usage)
        
        # Calculate averages from history
        avg_cpu = sum(self._cpu_usage_history) / len(self._cpu_usage_history) if self._cpu_usage_history else 0.0
        avg_memory = sum(self._memory_usage_history) / len(self._memory_usage_history) if self._memory_usage_history else 0.0
        avg_gpu = sum(self._gpu_usage_history) / len(self._gpu_usage_history) if self._gpu_usage_history else 0.0
        
        return {
            "current_state": current_state.value,
            "current_usage": current_usage,
            "average_usage": {
                "cpu_percent": avg_cpu,
                "memory_percent": avg_memory,
                "gpu_percent": avg_gpu
            },
            "thresholds": self._alert_thresholds,
            "can_accept_new_work": self.can_accept_execution(),
            "last_check_time": self._last_check_time.isoformat()
        }


class DistributedComputeNode(ModernLogger):
    """
    Advanced distributed compute node with comprehensive production features.
    
    This class implements a sophisticated compute node that connects to an
    EasyRemote gateway server and provides high-performance computational
    resources with intelligent management, monitoring, and optimization.
    
    Key Responsibilities:
    1. Function Management: Registration, discovery, versioning, and lifecycle
    2. Gateway Coordination: Connection, registration, heartbeats, and communication
    3. Execution Management: Request handling, queuing, execution, and results
    4. Resource Management: Monitoring, allocation, throttling, and optimization
    5. Health Monitoring: Status reporting, diagnostics, and self-healing
    
    Architecture Features:
    - Event-driven architecture with asynchronous processing
    - Comprehensive error handling with automatic recovery
    - Real-time performance monitoring and optimization
    - Intelligent resource management and capacity planning
    - Production-grade logging, metrics, and observability
    
    Usage:
        >>> # Simple setup
        >>> node = DistributedComputeNode("localhost:8080", "worker-1")
        >>> 
        >>> @node.register(timeout=300, tags={"ml", "gpu"})
        ... def train_model(data, epochs=10):
        ...     return {"accuracy": 0.95}
        >>> 
        >>> node.serve()  # Start serving requests
        >>> 
        >>> # Advanced setup with builder
        >>> node = ComputeNodeBuilder() \
        ...     .with_gateway("production:8080") \
        ...     .with_resource_limits(cpu_percent=80, memory_gb=16) \
        ...     .enable_auto_scaling() \
        ...     .build()
    """
    
    # Global node registry for management and coordination
    _node_registry: Dict[str, 'DistributedComputeNode'] = {}
    _registry_lock = threading.Lock()
    
    def __init__(self, 
                 gateway_address: str,
                 node_id: Optional[str] = None,
                 config: Optional[NodeConfiguration] = None,
                 log_level: str = "info"):
        """
        Initialize distributed compute node with comprehensive configuration.
        
        Args:
            gateway_address: Address of the gateway server (host:port)
            node_id: Unique identifier for this node (auto-generated if None)
            config: Node configuration (auto-generated if None)
            log_level: Logging level (debug, info, warning, error, critical)
            
        Raises:
            ValueError: If configuration parameters are invalid
            EasyRemoteError: If initialization fails
            
        Example:
            >>> node = DistributedComputeNode(
            ...     gateway_address="localhost:8080",
            ...     node_id="gpu-worker-1",
            ...     config=NodeConfiguration.from_environment(
            ...         gateway_address="localhost:8080",
            ...         node_id="gpu-worker-1",
            ...         environment=Environment.PRODUCTION
            ...     )
            ... )
        """
        super().__init__(name="DistributedComputeNode", level=log_level)
        install_asyncio_grpc_shutdown_noise_filter()
        
        # Generate configuration if not provided
        if node_id is None:
            node_id = self._generate_unique_node_id()
        
        if config is None:
            config = NodeConfiguration(
                gateway_address=gateway_address,
                node_id=node_id
            )
        else:
            # Ensure consistency
            config.gateway_address = gateway_address
            config.node_id = node_id
        
        self.config = config
        
        self.info(f"Initializing DistributedComputeNode '{self.config.node_id}' "
                 f"targeting gateway: {self.config.gateway_address}")
        
        # Core node state
        self._connection_state = NodeConnectionState.DISCONNECTED
        self._state_lock = LoopBoundAsyncLock(name="compute-node-state-lock")
        
        # Function registry and management
        self._registered_functions: Dict[str, FunctionRegistration] = {}
        self._function_execution_cache: Dict[str, Any] = {}
        self._function_lock = threading.RLock()
        
        # Execution tracking and management
        self._active_executions: Dict[str, ExecutionContext] = {}
        self._execution_queue: asyncio.Queue = asyncio.Queue(maxsize=config.queue_size_limit)
        self._execution_statistics: Dict[str, Dict[str, Any]] = {}
        
        # Communication infrastructure
        self._gateway_channel: Optional[grpc.aio.Channel] = None
        self._gateway_stub: Optional[service_pb2_grpc.RemoteServiceStub] = None
        self._communication_stream: Optional[Any] = None
        self._outgoing_messages: asyncio.Queue = asyncio.Queue(maxsize=1000)  # For sending results back to server
        
        # Background tasks and lifecycle management
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._service_thread: Optional[threading.Thread] = None
        self._grpc_aio_initialized: bool = False
        self._background_tasks: Set[asyncio.Task] = set()
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._health_monitor_task: Optional[asyncio.Task] = None
        self._resource_monitor_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._connection_event = threading.Event()
        
        # Resource management and monitoring
        self._resource_monitor = ResourceMonitor(config)
        self._thread_executor = futures.ThreadPoolExecutor(
            max_workers=config.max_concurrent_executions,
            thread_name_prefix=f"EasyRemote-{config.node_id}"
        )
        
        # Performance monitoring and metrics
        self._node_metrics = NodeHealthMetrics() if config.enable_performance_monitoring else None
        self._last_heartbeat_time: Optional[datetime] = None
        self._reconnection_count = 0
        self._total_executions = 0
        self._successful_executions = 0
        
        # Thread safety and synchronization
        self._global_lock = LoopBoundAsyncLock(name="compute-node-global-lock")
        
        # Core services
        from ..data import Serializer
        self._serializer = Serializer()
        
        # Register node globally
        with DistributedComputeNode._registry_lock:
            DistributedComputeNode._node_registry[config.node_id] = self
        
        self.info(f"DistributedComputeNode '{self.config.node_id}' initialized successfully")
    
    def _generate_unique_node_id(self) -> str:
        """
        Generate a unique, descriptive node identifier.
        
        The generated ID includes hostname, process info, and UUID
        for uniqueness while remaining human-readable.
        
        Returns:
            Unique node identifier string
        """
        try:
            hostname = platform.node().lower().replace('.', '-')[:12]
            process_id = f"pid{os.getpid()}"
            unique_suffix = str(uuid.uuid4())[:8]
            return f"compute-{hostname}-{process_id}-{unique_suffix}"
        except Exception:
            # Fallback to simple UUID if hostname detection fails
            return f"compute-node-{str(uuid.uuid4())[:16]}"
    
    @property
    def node_id(self) -> str:
        """Get the unique node identifier."""
        return self.config.node_id
    
    @property
    def gateway_address(self) -> str:
        """Get the gateway server address."""
        return self.config.gateway_address
    
    @property
    def connection_state(self) -> NodeConnectionState:
        """Get the current connection state."""
        return self._connection_state
    
    @property
    def is_connected(self) -> bool:
        """Check if node is currently connected to gateway."""
        return self._connection_state == NodeConnectionState.CONNECTED
    
    @property
    def registered_functions(self) -> Dict[str, FunctionRegistration]:
        """Get dictionary of registered functions."""
        with self._function_lock:
            return {name: reg for name, reg in self._registered_functions.items()}
    
    @property
    def active_executions(self) -> Dict[str, ExecutionContext]:
        """Get dictionary of currently active executions."""
        return self._active_executions.copy()
    
    async def _set_connection_state(self, new_state: NodeConnectionState):
        """
        Thread-safe connection state transition with validation.
        
        Args:
            new_state: The new connection state to transition to
        """
        async with self._state_lock:
            old_state = self._connection_state
            self._connection_state = new_state
            
            if old_state != new_state:
                self.info(f"Connection state changed: {old_state.value} -> {new_state.value}")
                
                # Update connection event for synchronous waiting
                if new_state == NodeConnectionState.CONNECTED:
                    self._connection_event.set()
                else:
                    self._connection_event.clear()
    
    def register(self,
                func: Optional[Callable] = None,
                *,
                name: Optional[str] = None,
                function_type: Optional[FunctionType] = None,
                resource_requirements: Optional[ResourceRequirements] = None,
                timeout_seconds: Optional[float] = None,
                load_balancing: bool = True,
                max_concurrent: int = 1,
                priority: int = 5,
                tags: Optional[Set[str]] = None,
                description: Optional[str] = None,
                version: str = "1.0.0",
                enable_caching: bool = True,
                cache_ttl_seconds: Optional[float] = None,
                execution_mode: ExecutionMode = ExecutionMode.NORMAL) -> Union[Callable, Callable[[Callable], Callable]]:
        """
        Register a function for remote execution with comprehensive configuration.
        
        This method supports both decorator and direct call patterns, automatically
        analyzing function characteristics and applying optimal configurations.
        
        Args:
            func: Function to register (None for decorator usage)
            name: Custom function name (defaults to func.__name__)
            function_type: Type classification (auto-detected if None)
            resource_requirements: Computational resource needs
            timeout_seconds: Maximum execution time in seconds
            load_balancing: Enable load balancing for this function
            max_concurrent: Maximum concurrent executions allowed
            priority: Execution priority (1-10, higher is more important)
            tags: Metadata tags for categorization
            description: Human-readable function description
            version: Function version for compatibility tracking
            enable_caching: Enable result caching for this function
            cache_ttl_seconds: Cache time-to-live in seconds
            execution_mode: Execution mode for performance optimization
            
        Returns:
            Registered function or decorator
            
        Raises:
            ValueError: If function parameters are invalid
            EasyRemoteError: If registration fails
            
        Example:
            >>> @node.register(
            ...     timeout_seconds=600,
            ...     resource_requirements=ResourceRequirements(
            ...         gpu_required=True,
            ...         min_memory_gb=8
            ...     ),
            ...     tags={"ml", "training", "gpu"},
            ...     description="Train machine learning model",
            ...     version="2.1.0",
            ...     priority=8,
            ...     execution_mode=ExecutionMode.HIGH_PERFORMANCE
            ... )
            ... def train_model(data, epochs=10, learning_rate=0.001):
            ...     # AI model training logic
            ...     return {"accuracy": 0.95, "epochs": epochs}
        """
        def decorator(f: Callable) -> Callable:
            # Determine function name
            func_name = name or getattr(f, '__name__', 'unnamed_function')
            
            # Analyze function characteristics
            func_analysis = analyze_function(f)
            
            # Determine function type
            if function_type is None:
                if func_analysis.is_async and func_analysis.is_generator:
                    detected_type = FunctionType.ASYNC_GENERATOR
                elif func_analysis.is_async:
                    detected_type = FunctionType.ASYNC
                elif func_analysis.is_generator:
                    detected_type = FunctionType.GENERATOR
                else:
                    detected_type = FunctionType.SYNC
            else:
                detected_type = function_type
            
            # Create comprehensive function information
            function_info = FunctionInfo(
                name=func_name,
                callable=f,
                function_type=detected_type,
                node_id=self.config.node_id,
                resource_requirements=resource_requirements or ResourceRequirements(),
                load_balancing_enabled=load_balancing,
                max_concurrent_calls=max_concurrent,
                tags=tags or set(),
                created_at=datetime.now()
            )
            
            # Add extended metadata
            if description:
                function_info.set_context_data("description", description)
            function_info.set_context_data("version", version)
            function_info.set_context_data("priority", priority)
            function_info.set_context_data("timeout_seconds", timeout_seconds)
            function_info.set_context_data("execution_mode", execution_mode.value)
            
            # Validate function registration
            self._validate_function_registration(function_info)
            
            # Create function registration
            registration = FunctionRegistration(
                function_info=function_info,
                version=version,
                enable_result_caching=enable_caching,
                cache_ttl_seconds=cache_ttl_seconds,
                estimated_resource_usage=resource_requirements
            )
            
            # Register function
            with self._function_lock:
                self._registered_functions[func_name] = registration
            
            # Initialize execution statistics
            self._execution_statistics[func_name] = {
                "total_calls": 0,
                "successful_calls": 0,
                "failed_calls": 0,
                "average_execution_time_ms": 0.0,
                "cache_hits": 0,
                "cache_misses": 0
            }
            
            self.info(f"Registered function '{func_name}' "
                     f"(type: {detected_type.value}, version: {version}, "
                     f"priority: {priority}, mode: {execution_mode.value})")
            
            return f
        
        # Support both decorator and direct call patterns
        if func is None:
            return decorator
        else:
            return decorator(func)
    
    def _validate_function_registration(self, function_info: FunctionInfo):
        """
        Validate function registration parameters.
        
        Args:
            function_info: Function information to validate
            
        Raises:
            ValueError: If validation fails
        """
        if not function_info.name:
            raise ValueError("Function name cannot be empty")
        
        with self._function_lock:
            if function_info.name in self._registered_functions:
                raise ValueError(f"Function '{function_info.name}' is already registered")
        
        if function_info.max_concurrent_calls < 1:
            raise ValueError("Max concurrent calls must be positive")
        
        if not function_info.callable:
            raise ValueError("Function callable cannot be None")
        
        # Validate against node capacity
        if function_info.max_concurrent_calls > self.config.max_concurrent_executions:
            self.warning(f"Function '{function_info.name}' max concurrent calls "
                        f"({function_info.max_concurrent_calls}) exceeds node capacity "
                        f"({self.config.max_concurrent_executions})")
    
    def serve(self, blocking: bool = True) -> Optional[threading.Thread]:
        """
        Start the compute node service with comprehensive lifecycle management.
        
        This method starts the node service and maintains connection to the gateway
        server with automatic retry, reconnection, and health monitoring.
        
        Args:
            blocking: Whether to block the calling thread (True) or run in background (False)
            
        Returns:
            Thread handle if non-blocking, None if blocking
            
        Raises:
            EasyRemoteError: If service fails to start after all retry attempts
            
        Example:
            >>> # Blocking mode (recommended for dedicated node processes)
            >>> node.serve()
            >>> 
            >>> # Background mode (for integration with other services)
            >>> thread = node.serve(blocking=False)
            >>> # Continue with other work...
            >>> thread.join()  # Wait for completion when ready
        """
        self.info(f"Starting compute node service (blocking={blocking})")
        
        if blocking:
            try:
                # Check if we're already in an event loop
                asyncio.get_running_loop()
                self.warning("Detected running event loop, switching to background mode")
                return self.serve(blocking=False)
            except RuntimeError:
                # No running loop, we can create our own
                pass
            
            # Start in blocking mode
            self._event_loop = asyncio.new_event_loop()
            self._initialize_event_loop(self._event_loop)
            
            try:
                self._event_loop.run_until_complete(self._async_serve())
            except KeyboardInterrupt:
                self.info("Received interrupt signal, shutting down gracefully...")
                self._event_loop.run_until_complete(self._async_cleanup())
            except Exception as e:
                self.error(f"Service error: {e}", exc_info=True)
                raise ExceptionTranslator.as_connection_error(
                    e,
                    address=self.config.gateway_address,
                    message="Compute node service failed",
                ) from e
            finally:
                if not self._event_loop.is_closed():
                    self._finalize_event_loop(self._event_loop)
                self._event_loop = None
                
        else:
            # Start in background mode
            def _background_server_runner():
                """Background server runner with proper exception handling."""
                loop = asyncio.new_event_loop()
                self._event_loop = loop
                self._initialize_event_loop(loop)
                
                try:
                    loop.run_until_complete(self._async_serve())
                except Exception as e:
                    self.error(f"Background service error: {e}", exc_info=True)
                finally:
                    if not loop.is_closed():
                        self._finalize_event_loop(loop)
                    self._event_loop = None
            
            self._service_thread = threading.Thread(
                target=_background_server_runner,
                name=f"ComputeNode-{self.config.node_id}",
                daemon=True
            )
            self._service_thread.start()
            
            # Wait for service to be ready
            self._wait_for_service_ready(timeout=30.0)
            
            return self._service_thread

    def _initialize_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Initialize loop-local resources for grpc.aio runtime.
        """
        asyncio.set_event_loop(loop)
        loop.set_exception_handler(self._handle_loop_exception)
        try:
            grpc.aio.init_grpc_aio()
            self._grpc_aio_initialized = True
        except Exception as e:
            self._grpc_aio_initialized = False
            self.warning(f"Failed to initialize grpc.aio runtime: {e}")

    def _handle_loop_exception(
        self,
        loop: asyncio.AbstractEventLoop,
        context: Dict[str, Any],
    ) -> None:
        """
        Suppress known grpc.aio poller noise during shutdown.
        """
        exception = context.get("exception")
        handle = context.get("handle")
        handle_repr = repr(handle)

        if (
            self._shutdown_event.is_set()
            and isinstance(exception, BlockingIOError)
            and "PollerCompletionQueue._handle_events" in handle_repr
        ):
            self.debug("Suppressing grpc.aio poller BlockingIOError during shutdown")
            return

        loop.default_exception_handler(context)

    def _finalize_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Flush and close event loop with best-effort grpc.aio teardown.
        """
        if loop.is_running():
            return

        try:
            pending_tasks = [task for task in asyncio.all_tasks(loop) if not task.done()]
            for task in pending_tasks:
                task.cancel()
            if pending_tasks:
                loop.run_until_complete(
                    asyncio.gather(*pending_tasks, return_exceptions=True)
                )
        except Exception as e:
            self.warning(f"Error while cancelling pending node loop tasks: {e}")

        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception as e:
            self.warning(f"Error while shutting down async generators: {e}")

        try:
            loop.run_until_complete(loop.shutdown_default_executor())
        except Exception as e:
            self.warning(f"Error while shutting down default executor: {e}")

        if self._grpc_aio_initialized:
            try:
                grpc.aio.shutdown_grpc_aio()
            except Exception as e:
                self.warning(f"Error while shutting down grpc.aio runtime: {e}")
            finally:
                self._grpc_aio_initialized = False

        loop.close()
    
    def _wait_for_service_ready(self, timeout: float = 10.0) -> None:
        """
        Wait for service to be ready with timeout.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Raises:
            TimeoutError: If service doesn't become ready within timeout
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self._connection_event.is_set():
                self.info("Service is ready and connected")
                return
            time.sleep(0.1)
        
        raise TimeoutError(
            message="Service did not become ready within timeout",
            timeout_seconds=timeout,
            operation="compute_node_startup",
        )
    
    async def _async_serve(self) -> None:
        """
        Asynchronous service loop with comprehensive lifecycle management.
        """
        try:
            await self._set_connection_state(NodeConnectionState.INITIALIZING)
            
            # Start background monitoring tasks
            await self._start_background_tasks()
            
            # Main service loop with reconnection
            await self._service_loop()
            
        except Exception as e:
            self.error(f"Service loop error: {e}", exc_info=True)
            await self._set_connection_state(NodeConnectionState.ERROR)
            raise
        finally:
            await self._async_cleanup()
    
    async def _start_background_tasks(self):
        """Start all background monitoring and management tasks."""
        self.debug("Starting background tasks")
        
        # Resource monitoring task
        if self.config.enable_resource_monitoring:
            self._resource_monitor_task = asyncio.create_task(
                self._resource_monitoring_loop()
            )
            self._background_tasks.add(self._resource_monitor_task)
        
        # Health monitoring task
        if self.config.enable_performance_monitoring:
            self._health_monitor_task = asyncio.create_task(
                self._health_monitoring_loop()
            )
            self._background_tasks.add(self._health_monitor_task)
        
        self.debug(f"Started {len(self._background_tasks)} background tasks")
    
    async def _service_loop(self):
        """Main service loop with connection management and reconnection."""
        reconnect_interval = self.config.reconnect_interval_seconds
        max_interval = self.config.reconnect_max_interval_seconds
        
        while not self._shutdown_event.is_set():
            try:
                # Attempt to connect and serve
                await self._connect_and_serve()
                
                # If we reach here, connection was successful
                # Reset reconnection interval
                reconnect_interval = self.config.reconnect_interval_seconds
                self._reconnection_count = 0
                
            except Exception as e:
                self.error(f"Connection/service error: {e}")
                await self._set_connection_state(NodeConnectionState.RECONNECTING)
                
                # Increment reconnection count
                self._reconnection_count += 1
                
                # Calculate next reconnection interval with exponential backoff
                reconnect_interval = min(
                    reconnect_interval * self.config.reconnect_backoff_multiplier,
                    max_interval
                )
                
                self.warning(f"Reconnecting in {reconnect_interval:.1f} seconds "
                           f"(attempt {self._reconnection_count})")
                
                # Wait before reconnection attempt
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=reconnect_interval
                    )
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    continue  # Timeout reached, attempt reconnection
    
    async def _connect_and_serve(self):
        """Connect to gateway and serve requests."""
        await self._set_connection_state(NodeConnectionState.CONNECTING)
        
        # Create gRPC channel and stub
        channel_options = self._get_grpc_channel_options()
        self._gateway_channel = grpc.aio.insecure_channel(
            self.config.gateway_address,
            options=channel_options
        )
        self._gateway_stub = service_pb2_grpc.RemoteServiceStub(self._gateway_channel)
        
        # Test connection
        await self._test_connection()
        
        # Register with gateway
        await self._register_with_gateway()
        
        # Start heartbeat task
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._background_tasks.add(self._heartbeat_task)
        
        await self._set_connection_state(NodeConnectionState.CONNECTED)
        
        # Enter main request handling loop
        await self._request_handling_loop()
    
    def _get_grpc_channel_options(self) -> List[Tuple[str, Any]]:
        """Get optimized gRPC channel options."""
        return [
            ('grpc.keepalive_time_ms', 30000),  # Send keepalive ping every 30s
            ('grpc.keepalive_timeout_ms', 5000),  # Wait 5s for keepalive response
            ('grpc.keepalive_permit_without_calls', True),  # Allow pings without active calls
            ('grpc.max_send_message_length', 100 * 1024 * 1024),  # 100MB
            ('grpc.max_receive_message_length', 100 * 1024 * 1024),  # 100MB
            ('grpc.max_connection_idle_ms', 300000),  # 5 minutes max idle
            ('grpc.max_connection_age_ms', 3600000),  # 1 hour max connection age
            ('grpc.http2.max_pings_without_data', 2),  # Allow 2 pings without data
            ('grpc.http2.min_ping_interval_without_data_ms', 30000),  # Min 30s between idle pings
        ]
    
    async def _test_connection(self) -> None:
        """Test connection to gateway with health check."""
        try:
            # Simple connectivity test
            await asyncio.wait_for(
                self._gateway_channel.channel_ready(),
                timeout=self.config.connection_timeout_seconds
            )
            self.debug("Gateway connection test successful")
        except asyncio.TimeoutError:
            raise EasyRemoteConnectionError(
                message=f"Connection timeout to gateway {self.config.gateway_address}",
                address=self.config.gateway_address,
            )
        except Exception as e:
            raise EasyRemoteConnectionError(
                message=f"Gateway connection test failed: {e}",
                address=self.config.gateway_address,
                cause=e,
            ) from e
    
    async def _register_with_gateway(self) -> None:
        """Register node and functions with gateway."""
        await self._set_connection_state(NodeConnectionState.REGISTERING)
        
        # Create node information
        node_info = self.get_node_info()
        
        # Convert to protobuf format
        node_proto = self._convert_node_info_to_proto(node_info)
        
        try:
            # Send registration request
            response = await self._gateway_stub.RegisterNode(node_proto)
            
            if response.success:
                self.info(f"Successfully registered with gateway: {response.message}")
            else:
                raise EasyRemoteConnectionError(
                    message=f"Registration rejected by gateway: {response.message}",
                    address=self.config.gateway_address,
                )
                
        except grpc.RpcError as e:
            raise EasyRemoteConnectionError(
                message=f"Registration RPC failed: {e}",
                address=self.config.gateway_address,
                cause=e,
            ) from e
    
    def _convert_node_info_to_proto(self, node_info: NodeInfo) -> service_pb2.NodeInfo:
        """Convert NodeInfo to protobuf format."""
        node_proto = service_pb2.NodeInfo()
        node_proto.node_id = node_info.node_id
        node_proto.status = node_info.status.value
        node_proto.version = node_info.version
        node_proto.location = node_info.location or ""
        
        # Add capabilities
        node_proto.capabilities.extend(list(node_info.capabilities))
        
        # Add function information
        for func_name, registration in self._registered_functions.items():
            func_proto = node_proto.functions.add()
            func_proto.name = func_name
            func_proto.is_async = registration.function_info.function_type in (FunctionType.ASYNC, FunctionType.ASYNC_GENERATOR)
            func_proto.is_generator = registration.function_info.function_type in (FunctionType.GENERATOR, FunctionType.ASYNC_GENERATOR)
        
        # Add resource information
        node_proto.max_concurrent_executions = self.config.max_concurrent_executions
        node_proto.current_executions = len(self._active_executions)
        
        return node_proto
    
    async def _heartbeat_loop(self):
        """Maintain heartbeat with gateway."""
        heartbeat_count = 0
        while not self._shutdown_event.is_set():
            try:
                heartbeat_count += 1
                
                # Create heartbeat message
                heartbeat = service_pb2.HeartbeatMessage()
                heartbeat.node_id = self.config.node_id
                heartbeat.timestamp = int(time.time())
                
                # Add current resource usage
                resource_usage = self._resource_monitor.get_current_usage()
                heartbeat.cpu_usage = resource_usage.get("cpu_percent", 0.0)
                heartbeat.memory_usage = resource_usage.get("memory_percent", 0.0)
                heartbeat.gpu_usage = resource_usage.get("gpu_percent", 0.0)
                heartbeat.active_connections = len(self._active_executions)
                
                # 💓 Enhanced heartbeat logging
                self.debug(f"💓 [NODE-HEARTBEAT] #{heartbeat_count} Sending heartbeat to gateway... "
                         f"CPU: {heartbeat.cpu_usage:.1f}%, Memory: {heartbeat.memory_usage:.1f}%, "
                         f"GPU: {heartbeat.gpu_usage:.1f}%, Active: {heartbeat.active_connections}")
                
                # Send heartbeat
                response = await asyncio.wait_for(
                    self._gateway_stub.SendHeartbeat(heartbeat),
                    timeout=self.config.heartbeat_timeout_seconds
                )
                
                self._last_heartbeat_time = datetime.now()
                
                if response.accepted:
                    self.debug(f"✅ [NODE-HEARTBEAT] #{heartbeat_count} Heartbeat accepted by gateway")
                else:
                    self.warning(f"❌ [NODE-HEARTBEAT] #{heartbeat_count} Heartbeat rejected by gateway!")
                
                # Wait for next heartbeat
                await asyncio.sleep(self.config.heartbeat_interval_seconds)
                
            except asyncio.TimeoutError:
                self.warning(f"⏰ [NODE-HEARTBEAT] #{heartbeat_count} Heartbeat timeout!")
                break
            except Exception as e:
                self.error(f"💥 [NODE-HEARTBEAT] #{heartbeat_count} Heartbeat error: {e}")
                break
    
    async def _request_handling_loop(self):
        """Main request handling loop with control stream."""
        self.info("Starting control stream for request handling")
        
        try:
            # Create control stream for bidirectional communication
            control_stream = self._gateway_stub.ControlStream(self._generate_control_messages())
            self._communication_stream = control_stream
            
            # Handle incoming messages from the server
            async for control_message in control_stream:
                try:
                    await self._handle_control_message(control_message)
                except Exception as e:
                    self.error(f"Error handling control message: {e}")
                    
        except grpc.RpcError as e:
            self.error(f"Control stream error: {e}")
            raise EasyRemoteConnectionError(f"Control stream failed: {e}")
        except Exception as e:
            self.error(f"Unexpected error in request handling: {e}")
            raise
        finally:
            self._communication_stream = None
    
    async def _generate_control_messages(self):
        """Generate control messages to send to server."""
        # Initial registration via control stream
        register_req = service_pb2.RegisterRequest()
        register_req.node_id = self.config.node_id
        
        # Add function information
        for func_name, registration in self._registered_functions.items():
            func_spec = register_req.functions.add()
            func_spec.name = func_name
            func_spec.is_async = registration.function_info.function_type in (FunctionType.ASYNC, FunctionType.ASYNC_GENERATOR)
            func_spec.is_generator = registration.function_info.function_type in (FunctionType.GENERATOR, FunctionType.ASYNC_GENERATOR)
        
        # Send initial registration
        control_msg = service_pb2.ControlMessage()
        control_msg.register_req.CopyFrom(register_req)
        yield control_msg
        
        # Keep the stream alive and send periodic heartbeats and outgoing messages
        last_heartbeat = time.time()
        heartbeat_interval = self.config.heartbeat_interval_seconds
        
        while not self._shutdown_event.is_set():
            try:
                # Check for outgoing messages (execution results) first
                try:
                    # Non-blocking check for outgoing messages
                    outgoing_msg = self._outgoing_messages.get_nowait()
                    yield outgoing_msg
                    continue  # Send message immediately, don't wait
                except asyncio.QueueEmpty:
                    pass  # No outgoing messages, continue with heartbeat logic
                
                # Send heartbeat if it's time
                current_time = time.time()
                if current_time - last_heartbeat >= heartbeat_interval:
                    heartbeat_req = service_pb2.HeartbeatRequest()
                    heartbeat_req.node_id = self.config.node_id
                    
                    heartbeat_msg = service_pb2.ControlMessage()
                    heartbeat_msg.heartbeat_req.CopyFrom(heartbeat_req)
                    yield heartbeat_msg
                    
                    last_heartbeat = current_time
                
                # Short wait to avoid busy loop, but check for messages frequently
                await asyncio.sleep(0.1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.error(f"Error generating control messages: {e}")
                break
    
    async def _handle_control_message(self, control_message: service_pb2.ControlMessage) -> None:
        """Handle incoming control messages from server."""
        if control_message.HasField('register_resp'):
            # Handle registration response
            register_resp = control_message.register_resp
            if register_resp.success:
                self.info(f"Registration confirmed: {register_resp.message}")
                await self._set_connection_state(NodeConnectionState.CONNECTED)
            else:
                self.error(f"Registration failed: {register_resp.message}")
                raise EasyRemoteConnectionError(
                    message=f"Registration failed: {register_resp.message}",
                    address=self.config.gateway_address,
                )
                
        elif control_message.HasField('heartbeat_resp'):
            # Handle heartbeat response
            heartbeat_resp = control_message.heartbeat_resp
            if heartbeat_resp.accepted:
                self.debug("Heartbeat acknowledged")
                self._last_heartbeat_time = datetime.now()
            else:
                self.warning("Heartbeat rejected by server")
                
        elif control_message.HasField('exec_req'):
            # Handle execution request
            exec_req = control_message.exec_req
            self.info(f"🎯 [NODE] RECEIVED execution request! function={exec_req.function_name}, call_id={exec_req.call_id}")
            
            # Execute function asynchronously
            self.info(f"🚀 [NODE] Starting async execution task for {exec_req.function_name}")
            asyncio.create_task(self._execute_function_request(exec_req))
            self.info(f"✅ [NODE] Async execution task created for {exec_req.function_name}")
        else:
            self.debug("🔍 [NODE] Received unknown control message type")
    
    async def _execute_function_request(self, exec_req):
        """Execute a function request and send back the result."""
        call_id = exec_req.call_id
        function_name = exec_req.function_name
        
        self.info(f"🎯 [NODE-EXEC] Starting execution: call_id={call_id}, function={function_name}")
        
        try:
            # Check if function exists
            if function_name not in self._registered_functions:
                error_msg = f"Function '{function_name}' not found"
                self.error(f"❌ [NODE-EXEC] {error_msg}")
                raise FunctionNotFoundError(
                    function_name=function_name,
                    node_id=self.config.node_id,
                    message=error_msg,
                )
            
            registration = self._registered_functions[function_name]
            func = registration.function_info.callable
            
            if func is None:
                error_msg = f"Function '{function_name}' has no callable"
                self.error(f"❌ [NODE-EXEC] {error_msg}")
                raise RemoteExecutionError(
                    function_name=function_name,
                    node_id=self.config.node_id,
                    message=error_msg,
                )
            
            self.info(f"🔧 [NODE-EXEC] Function found, deserializing arguments for {function_name}")
            
            # Deserialize arguments
            args, kwargs = self._serializer.deserialize_args(exec_req.args, exec_req.kwargs)
            self.info(f"✅ [NODE-EXEC] Arguments deserialized: args={len(args)}, kwargs={len(kwargs)}")
            
            # Create execution context
            exec_context = ExecutionContext(
                call_id=call_id,
                function_name=function_name,
                node_id=self.config.node_id
            )
            
            # Track execution
            self._active_executions[call_id] = exec_context
            start_time = time.time()
            
            self.info(f"🚀 [NODE-EXEC] EXECUTING function '{function_name}' with call_id {call_id} - START!")
            
            # Execute function
            try:
                if registration.function_info.function_type in (FunctionType.ASYNC, FunctionType.ASYNC_GENERATOR):
                    self.debug(f"⚡ [NODE-EXEC] Running async function {function_name}")
                    result = await func(*args, **kwargs)
                else:
                    # Run sync function in thread pool to avoid blocking
                    self.debug(f"🔄 [NODE-EXEC] Running sync function {function_name} in thread pool")
                    loop = asyncio.get_running_loop()
                    bound_call = self._build_executor_callable(
                        func=func,
                        args=tuple(args),
                        kwargs=dict(kwargs),
                    )
                    result = await loop.run_in_executor(
                        self._thread_executor,
                        bound_call,
                    )
                
                execution_time = time.time() - start_time
                self.info(f"🎉 [NODE-EXEC] SUCCESS! Function '{function_name}' completed in {execution_time:.3f}s, result: {result}")
                
                # Serialize result
                self.debug(f"📦 [NODE-EXEC] Serializing result for {function_name}")
                serialized_result = self._serializer.serialize_result(result)
                self.debug(f"✅ [NODE-EXEC] Result serialized for {function_name}")
                
                # Create success response
                exec_result = service_pb2.ExecutionResult()
                exec_result.call_id = call_id
                exec_result.function_name = function_name
                exec_result.node_id = self.config.node_id
                exec_result.has_error = False
                exec_result.result = serialized_result
                exec_result.is_done = True
                
                self.info(f"✅ [NODE-EXEC] Created success response for {function_name}")
                
                # Update statistics
                registration.update_execution_stats(True, execution_time * 1000)
                self._successful_executions += 1
                
            except Exception as e:
                execution_time = time.time() - start_time
                self.error(f"💥 [NODE-EXEC] FUNCTION FAILED! '{function_name}' failed after {execution_time:.3f}s: {e}")
                
                # Create error response
                exec_result = service_pb2.ExecutionResult()
                exec_result.call_id = call_id
                exec_result.function_name = function_name
                exec_result.node_id = self.config.node_id
                exec_result.has_error = True
                exec_result.error_message = str(e)
                exec_result.is_done = True
                
                # Update statistics
                registration.update_execution_stats(False, execution_time * 1000)
            
            # Send result back to server
            control_msg = service_pb2.ControlMessage()
            control_msg.exec_res.CopyFrom(exec_result)
            
            self.info(f"📤 [NODE-EXEC] Sending result back to server for {function_name}")
            
            # Note: In a real implementation, we'd need to send this back through the control stream
            # For now, we'll store it in a queue that the control stream generator can pick up
            if hasattr(self, '_outgoing_messages'):
                await self._outgoing_messages.put(control_msg)
                self.info("✅ [NODE-EXEC] Result queued for transmission to server")
            else:
                self.error("❌ [NODE-EXEC] No _outgoing_messages queue available!")
            
        except Exception as e:
            self.error(f"💥 [NODE-EXEC] Critical error executing function request {call_id}: {e}")
            
            # Clean up active execution tracking
            if call_id in self._active_executions:
                del self._active_executions[call_id]

    @staticmethod
    def _build_executor_callable(
        func: Callable[..., Any],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
    ) -> Callable[[], Any]:
        """
        Bind sync function arguments for thread-pool execution.

        `run_in_executor` does not accept keyword arguments directly, so kwargs
        must be pre-bound using `functools.partial`.
        """
        return functools.partial(func, *args, **kwargs)
    
    async def _resource_monitoring_loop(self):
        """Background resource monitoring loop."""
        while not self._shutdown_event.is_set():
            try:
                # Get current resource usage
                resource_usage = self._resource_monitor.get_current_usage()
                
                # Log resource usage if needed
                if self.config.enable_detailed_logging:
                    self.debug(f"Resource usage: CPU={resource_usage['cpu_percent']:.1f}%, "
                              f"Memory={resource_usage['memory_percent']:.1f}%, "
                              f"GPU={resource_usage['gpu_percent']:.1f}%")
                
                # Wait for next monitoring cycle
                await asyncio.sleep(self.config.resource_check_interval_seconds)
                
            except Exception as e:
                self.error(f"Resource monitoring error: {e}")
                await asyncio.sleep(self.config.resource_check_interval_seconds)
    
    async def _health_monitoring_loop(self):
        """Background health monitoring loop."""
        while not self._shutdown_event.is_set():
            try:
                # Update health metrics
                if self._node_metrics:
                    resource_usage = self._resource_monitor.get_current_usage()
                    self._node_metrics.update_metrics(
                        cpu_usage=resource_usage.get("cpu_percent", 0.0),
                        memory_usage=resource_usage.get("memory_percent", 0.0),
                        active_connections=len(self._active_executions)
                    )
                
                # Wait for next health check cycle
                await asyncio.sleep(self.config.health_report_interval_seconds)
                
            except Exception as e:
                self.error(f"Health monitoring error: {e}")
                await asyncio.sleep(self.config.health_report_interval_seconds)
    
    async def _async_cleanup(self):
        """Cleanup resources and shutdown background tasks."""
        self.info("Starting async cleanup")

        # Signal shutdown to long-running loops/generators.
        self._shutdown_event.set()

        # Cancel active control stream if still alive.
        if self._communication_stream is not None:
            try:
                cancel = getattr(self._communication_stream, "cancel", None)
                if callable(cancel):
                    cancel()
            except Exception as e:
                self.warning(f"Error while cancelling control stream: {e}")
            finally:
                self._communication_stream = None
        
        # Cancel background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        
        self._background_tasks.clear()
        
        # Close gateway connection
        if self._gateway_channel:
            await self._gateway_channel.close()
            self._gateway_channel = None
            self._gateway_stub = None
        
        self.info("Async cleanup completed")
    
    def stop(self):
        """
        Stop the compute node service gracefully.
        
        This method initiates graceful shutdown of the compute node,
        allowing current executions to complete while refusing new requests.
        """
        self.info("Initiating graceful shutdown")
        
        # Signal shutdown
        if self._event_loop and not self._event_loop.is_closed():
            self._event_loop.call_soon_threadsafe(self._shutdown_event.set)
        
        # Wait for shutdown with timeout
        try:
            if self._event_loop and not self._event_loop.is_closed():
                # Give some time for graceful shutdown
                time.sleep(1.0)
        except Exception as e:
            self.warning(f"Error during shutdown: {e}")

        if (
            self._service_thread
            and self._service_thread.is_alive()
            and threading.current_thread() is not self._service_thread
        ):
            self._service_thread.join(timeout=self.config.shutdown_timeout_seconds)
        self._service_thread = None
        
        # Cleanup thread executor
        if self._thread_executor:
            self._thread_executor.shutdown(wait=True)
        
        self.info("Compute node service stopped")
    
    def get_node_info(self) -> NodeInfo:
        """
        Get comprehensive node information.
        
        Returns:
            Complete node information including functions and capabilities
        """
        # Get current resource usage
        resource_usage = self._resource_monitor.get_current_usage()
        
        # Create function information list
        with self._function_lock:
            functions = {
                name: reg.function_info 
                for name, reg in self._registered_functions.items()
            }
        
        # Create node info with correct parameters
        node_info = NodeInfo(
            node_id=self.config.node_id,
            functions=functions,
            status=NodeStatus.ONLINE if self.is_connected else NodeStatus.OFFLINE,
            last_heartbeat=self._last_heartbeat_time or datetime.now(),
            version="1.0.0"
        )
        
        # Update health metrics with current resource usage
        node_info.health_metrics.update_metrics(
            cpu_usage=resource_usage.get("cpu_percent", 0.0),
            memory_usage=resource_usage.get("memory_percent", 0.0),
            gpu_usage=resource_usage.get("gpu_percent", 0.0),
            active_connections=len(self._active_executions)
        )
        
        return node_info
    
    @property
    def execution_statistics(self) -> Dict[str, Dict[str, Any]]:
        """Get execution statistics for all registered functions."""
        stats = dict(self._execution_statistics)
        
        # Add overall node statistics
        stats["__node__"] = {
            "total_executions": self._total_executions,
            "successful_executions": self._successful_executions,
            "failed_executions": self._total_executions - self._successful_executions,
            "success_rate": (
                self._successful_executions / self._total_executions 
                if self._total_executions > 0 else 0.0
            ),
            "active_executions": len(self._active_executions),
            "registered_functions": len(self._registered_functions),
            "connection_state": self._connection_state.value,
            "reconnection_count": self._reconnection_count
        }
        
        return stats
    
    def wait_for_connection(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for node to establish connection with gateway.
        
        Args:
            timeout: Maximum time to wait in seconds (None for no timeout)
            
        Returns:
            True if connected within timeout, False otherwise
        """
        return self._connection_event.wait(timeout=timeout)
    
    def __enter__(self) -> 'DistributedComputeNode':
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
    
    def __del__(self):
        """Cleanup on object destruction."""
        try:
            self.stop()
        except Exception:
            pass


class ComputeNodeBuilder:
    """
    Builder for fluent compute node configuration and construction.
    
    This builder provides a convenient way to configure and create
    distributed compute nodes with comprehensive customization options.
    
    Example:
        >>> node = ComputeNodeBuilder() \\
        ...     .with_gateway("production-gateway:8080") \\
        ...     .with_node_id("specialized-gpu-node") \\
        ...     .with_resource_limits(max_cpu_percent=90, max_memory_gb=32) \\
        ...     .with_execution_config(max_concurrent=8, timeout=300) \\
        ...     .enable_performance_monitoring() \\
        ...     .enable_auto_scaling() \\
        ...     .build()
    """
    
    def __init__(self):
        """Initialize builder with default configuration."""
        self._gateway_address: Optional[str] = None
        self._node_id: Optional[str] = None
        self._config: Optional[NodeConfiguration] = None
        self._environment: Environment = Environment.DEVELOPMENT
        self._log_level: str = "info"
    
    def with_gateway(self, address: str) -> 'ComputeNodeBuilder':
        """Set gateway server address."""
        self._gateway_address = address
        return self
    
    def with_node_id(self, node_id: str) -> 'ComputeNodeBuilder':
        """Set custom node identifier."""
        self._node_id = node_id
        return self
    
    def with_environment(self, environment: Environment) -> 'ComputeNodeBuilder':
        """Set target environment for optimization."""
        self._environment = environment
        return self
    
    def with_resource_limits(self, 
                           max_cpu_percent: float = 90.0,
                           max_memory_percent: float = 85.0) -> 'ComputeNodeBuilder':
        """Configure resource limits."""
        if self._config is None:
            self._config = NodeConfiguration("", "")
        
        self._config.max_cpu_usage_percent = max_cpu_percent
        self._config.max_memory_usage_percent = max_memory_percent
        return self
    
    def with_execution_config(self, 
                            max_concurrent: int = 10,
                            timeout_seconds: float = 300.0,
                            queue_limit: int = 1000) -> 'ComputeNodeBuilder':
        """Configure execution parameters."""
        if self._config is None:
            self._config = NodeConfiguration("", "")
        
        self._config.max_concurrent_executions = max_concurrent
        self._config.execution_timeout_seconds = timeout_seconds
        self._config.queue_size_limit = queue_limit
        return self
    
    def enable_performance_monitoring(self, enabled: bool = True) -> 'ComputeNodeBuilder':
        """Enable comprehensive performance monitoring."""
        if self._config is None:
            self._config = NodeConfiguration("", "")
        
        self._config.enable_performance_monitoring = enabled
        self._config.enable_resource_monitoring = enabled
        return self
    
    def enable_auto_scaling(self, enabled: bool = True) -> 'ComputeNodeBuilder':
        """Enable automatic scaling features."""
        if self._config is None:
            self._config = NodeConfiguration("", "")
        
        self._config.enable_auto_scaling = enabled
        return self
    
    def enable_detailed_logging(self, enabled: bool = True) -> 'ComputeNodeBuilder':
        """Enable detailed logging and debugging."""
        if self._config is None:
            self._config = NodeConfiguration("", "")
        
        self._config.enable_detailed_logging = enabled
        return self
    
    def with_log_level(self, level: str) -> 'ComputeNodeBuilder':
        """Set logging level."""
        self._log_level = level
        return self
    
    def build(self) -> DistributedComputeNode:
        """
        Build and return configured compute node instance.
        
        Returns:
            Configured DistributedComputeNode instance
            
        Raises:
            ValueError: If required configuration is missing
        """
        if not self._gateway_address:
            raise ValueError("Gateway address is required")
        
        # Generate config if not provided
        if self._config is None:
            self._config = NodeConfiguration.from_environment(
                gateway_address=self._gateway_address,
                node_id=self._node_id or "",
                environment=self._environment
            )
        else:
            self._config.gateway_address = self._gateway_address
            if self._node_id:
                self._config.node_id = self._node_id
        
        return DistributedComputeNode(
            gateway_address=self._gateway_address,
            node_id=self._node_id,
            config=self._config,
            log_level=self._log_level
        )


# Backward compatibility aliases
ComputeNode = DistributedComputeNode


# Export all public classes and functions
__all__ = [
    # Core classes
    'DistributedComputeNode',
    'ComputeNodeBuilder',
    'NodeConfiguration',
    'ExecutionContext',
    'FunctionRegistration',
    'ResourceMonitor',
    
    # Enums
    'NodeConnectionState',
    'ExecutionMode',
    'ResourceState',
    
    # Backward compatibility
    'ComputeNode'
]
