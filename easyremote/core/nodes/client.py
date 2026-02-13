#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EasyRemote Distributed Computing Client Module

This module implements a sophisticated client for the EasyRemote distributed computing
framework. The client provides intelligent remote function execution capabilities with
comprehensive error handling, performance monitoring, and adaptive optimization.

Architecture:
- Strategy Pattern: Multiple execution strategies for different scenarios
- Builder Pattern: Fluent client configuration and request building
- Circuit Breaker Pattern: Automatic failure detection and recovery
- Observer Pattern: Real-time performance monitoring and event notifications

Key Features:
1. Intelligent Request Routing:
   * Automatic load balancing with multiple strategies
   * Direct node targeting for specialized workloads
   * Dynamic strategy selection based on context
   * Geographical and latency-aware routing

2. Advanced Connection Management:
   * Automatic connection pooling and reuse
   * Retry mechanisms with exponential backoff
   * Circuit breaker for fault tolerance
   * Health monitoring and failover

3. Comprehensive Error Handling:
   * Detailed error classification and recovery
   * Automatic retry with intelligent backoff
   * Graceful degradation strategies
   * Rich error context and diagnostics

4. Performance Optimization:
   * Request result caching and optimization
   * Connection pooling and multiplexing
   * Adaptive timeout management
   * Real-time performance metrics

Usage Example:
    >>> # Basic usage with automatic configuration
    >>> client = DistributedComputingClient("localhost:8080")
    >>> result = client.execute("process_data", data=[1, 2, 3, 4])
    >>> 
    >>> # Advanced usage with custom configuration
    >>> client = ClientBuilder() \
    ...     .with_gateway("production-gateway:8080") \
    ...     .with_retry_policy(max_attempts=5, backoff_multiplier=2.0) \
    ...     .with_load_balancing_strategy("ml_enhanced") \
    ...     .enable_caching() \
    ...     .build()
    >>> 
    >>> # Context manager for automatic resource management
    >>> with client.session() as session:
    ...     result = session.execute_with_context(
    ...         function_name="train_model",
    ...         context=ExecutionContext(
    ...             priority=RequestPriority.HIGH,
    ...             timeout=600,
    ...             requirements={"gpu_required": True}
    ...         ),
    ...         data=training_data
    ...     )

Author: Silan Hu (silan.hu@u.nus.edu)
Version: 2.0.0
"""

import grpc
import queue
import time
import uuid
import threading
from typing import (
    Optional, Dict, Any, List, TypeVar, Generic, Tuple, Set, Iterator, Iterable
)
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

# EasyRemote core imports
from ..utils.logger import ModernLogger
from ..utils.exceptions import (
    ConnectionError as EasyRemoteConnectionError,
    RemoteExecutionError,
    EasyRemoteError,
    NoAvailableNodesError,
    TimeoutError,
    SerializationError,
    ExceptionTranslator,
)
from ..data.serialize import serialize_args, deserialize_result
from ..protos import service_pb2, service_pb2_grpc
from ..balancing.strategies import RequestContext, RequestPriority

T = TypeVar('T')


class ConnectionState(Enum):
    """
    Enumeration of client connection states.
    
    This enum provides detailed connection state tracking for
    comprehensive connection management and monitoring.
    """
    DISCONNECTED = "disconnected"       # Not connected to any gateway
    CONNECTING = "connecting"           # In process of establishing connection
    CONNECTED = "connected"             # Successfully connected and ready
    RECONNECTING = "reconnecting"       # Attempting to restore connection
    CIRCUIT_OPEN = "circuit_open"       # Circuit breaker activated
    DEGRADED = "degraded"               # Connected but with limited functionality
    ERROR = "error"                     # Connection in error state


class ExecutionStrategy(Enum):
    """
    Strategies for remote function execution.
    
    Different strategies optimize for different use cases and
    requirements such as performance, reliability, or cost.
    """
    LOAD_BALANCED = "load_balanced"     # Use intelligent load balancing
    DIRECT_TARGET = "direct_target"     # Target specific node directly
    BROADCAST = "broadcast"             # Execute on multiple nodes
    FASTEST_RESPONSE = "fastest_response"  # Race multiple executions
    COST_OPTIMIZED = "cost_optimized"   # Optimize for cost efficiency


@dataclass
class RetryPolicy:
    """
    Comprehensive retry policy configuration.
    
    This class defines how client should retry failed operations
    with intelligent backoff and circuit breaker integration.
    """
    max_attempts: int = 3                    # Maximum retry attempts
    initial_delay_ms: float = 100.0         # Initial retry delay
    max_delay_ms: float = 30000.0           # Maximum retry delay
    backoff_multiplier: float = 2.0         # Exponential backoff multiplier
    jitter: bool = True                     # Add random jitter to delays
    
    # Circuit breaker configuration
    circuit_breaker_threshold: int = 5      # Failures before opening circuit
    circuit_breaker_timeout_ms: float = 60000.0  # Circuit open duration
    
    # Retry conditions
    retryable_status_codes: Set[grpc.StatusCode] = field(default_factory=lambda: {
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.DEADLINE_EXCEEDED,
        grpc.StatusCode.RESOURCE_EXHAUSTED,
        grpc.StatusCode.ABORTED
    })
    
    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate retry delay for given attempt number.
        
        Args:
            attempt: Current attempt number (0-based)
            
        Returns:
            Delay in milliseconds
        """
        delay = min(
            self.initial_delay_ms * (self.backoff_multiplier ** attempt),
            self.max_delay_ms
        )
        
        if self.jitter:
            import random
            delay *= (0.5 + random.random() * 0.5)  # Add 0-50% jitter
        
        return delay


@dataclass
class ExecutionContext:
    """
    Comprehensive context for remote function execution.
    
    This class encapsulates all parameters and preferences that
    influence how a remote function call should be executed.
    """
    # Core execution parameters
    function_name: str
    priority: RequestPriority = RequestPriority.NORMAL
    timeout_ms: Optional[float] = None       # Execution timeout
    strategy: ExecutionStrategy = ExecutionStrategy.LOAD_BALANCED
    
    # Resource requirements and preferences
    requirements: Optional[Dict[str, Any]] = None  # Hardware/software requirements
    preferred_node_ids: Optional[List[str]] = None  # Preferred execution nodes
    excluded_node_ids: Optional[List[str]] = None   # Nodes to avoid
    
    # Geographic and network preferences  
    client_location: Optional[str] = None           # Client geographic location
    max_network_latency_ms: Optional[float] = None  # Maximum acceptable latency
    
    # Cost and billing preferences
    cost_limit: Optional[float] = None              # Maximum cost for execution
    billing_account: Optional[str] = None           # Billing account identifier
    
    # Monitoring and debugging
    enable_tracing: bool = False                    # Enable detailed tracing
    custom_tags: Dict[str, str] = field(default_factory=dict)  # Custom metadata
    
    # Retry and resilience
    retry_policy: Optional[RetryPolicy] = None      # Custom retry policy
    enable_caching: bool = True                     # Enable result caching
    cache_ttl_seconds: Optional[float] = None       # Cache time-to-live
    
    def to_request_context(self) -> RequestContext:
        """Convert execution context to load balancing request context."""
        return RequestContext(
            function_name=self.function_name,
            priority=self.priority,
            requirements=self.requirements,
            client_location_dict=(
                {"region": self.client_location} if self.client_location else None
            ),
            timeout=self.timeout_ms / 1000.0 if self.timeout_ms else None,
            cost_limit=self.cost_limit,
            custom_tags=self.custom_tags
        )


@dataclass
class ExecutionResult(Generic[T]):
    """
    Comprehensive result of remote function execution.
    
    This class provides detailed information about the execution
    including performance metrics, metadata, and debugging information.
    """
    # Core result data
    result: T                                       # Actual function result
    success: bool = True                           # Whether execution succeeded
    error: Optional[Exception] = None              # Error if execution failed
    
    # Execution metadata
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    function_name: str = ""                        # Executed function name
    node_id: Optional[str] = None                  # Node that executed the function
    execution_strategy: Optional[ExecutionStrategy] = None  # Strategy used
    
    # Performance metrics
    total_duration_ms: float = 0.0                # Total execution time
    network_latency_ms: float = 0.0               # Network round-trip time
    execution_time_ms: float = 0.0                # Actual function execution time
    queue_wait_time_ms: float = 0.0               # Time spent in queue
    
    # Resource utilization
    memory_usage_mb: Optional[float] = None        # Peak memory usage
    cpu_time_ms: Optional[float] = None            # CPU time consumed
    
    # Billing and cost information
    execution_cost: Optional[float] = None         # Cost of execution
    billing_units: Optional[float] = None          # Billing units consumed
    
    # Caching information
    cached: bool = False                           # Whether result was cached
    cache_hit: bool = False                        # Whether cache was used
    
    # Debugging and monitoring
    trace_id: Optional[str] = None                 # Distributed trace ID
    retry_count: int = 0                           # Number of retries performed
    warnings: List[str] = field(default_factory=list)  # Execution warnings
    
    @property
    def efficiency_score(self) -> float:
        """Calculate execution efficiency score (0.0 to 1.0)."""
        if not self.success:
            return 0.0
        
        # Base score from success
        score = 1.0
        
        # Adjust for execution time (assuming 1 second is baseline)
        if self.execution_time_ms > 0:
            time_efficiency = min(1000.0 / self.execution_time_ms, 1.0)
            score *= (0.8 + 0.2 * time_efficiency)
        
        # Adjust for retries (more retries = lower efficiency)
        if self.retry_count > 0:
            retry_penalty = max(0.5, 1.0 - (self.retry_count * 0.1))
            score *= retry_penalty
        
        return score
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for serialization."""
        return {
            "execution_id": self.execution_id,
            "function_name": self.function_name,
            "success": self.success,
            "node_id": self.node_id,
            "total_duration_ms": self.total_duration_ms,
            "execution_time_ms": self.execution_time_ms,
            "network_latency_ms": self.network_latency_ms,
            "efficiency_score": self.efficiency_score,
            "retry_count": self.retry_count,
            "cached": self.cached,
            "execution_cost": self.execution_cost,
            "warnings": self.warnings
        }


class CircuitBreaker(ModernLogger):
    """
    Circuit breaker implementation for fault tolerance.
    
    This class implements the circuit breaker pattern to prevent
    cascading failures and provide automatic recovery mechanisms.
    """
    
    def __init__(self, 
                 failure_threshold: int = 5,
                 recovery_timeout_ms: float = 60000.0,
                 half_open_max_calls: int = 3):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout_ms: Time before attempting recovery
            half_open_max_calls: Max calls in half-open state
        """
        super().__init__(name="CircuitBreaker")
        
        self.failure_threshold = failure_threshold
        self.recovery_timeout_ms = recovery_timeout_ms
        self.half_open_max_calls = half_open_max_calls
        
        self._failure_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._state = "closed"  # closed, open, half_open
        self._half_open_calls = 0
        
        self.debug(f"Initialized circuit breaker (threshold: {failure_threshold})")
    
    def can_execute(self) -> bool:
        """Check if execution is allowed based on circuit state."""
        if self._state == "closed":
            return True
        elif self._state == "open":
            # Check if recovery timeout has passed
            if (self._last_failure_time and 
                (datetime.now() - self._last_failure_time).total_seconds() * 1000 
                >= self.recovery_timeout_ms):
                self._state = "half_open"
                self._half_open_calls = 0
                self.info("Circuit breaker entering half-open state")
                return True
            return False
        elif self._state == "half_open":
            return self._half_open_calls < self.half_open_max_calls
        
        return False
    
    def record_success(self):
        """Record successful execution."""
        if self._state == "half_open":
            self._half_open_calls += 1
            if self._half_open_calls >= self.half_open_max_calls:
                self._state = "closed"
                self._failure_count = 0
                self.info("Circuit breaker closed after successful recovery")
        elif self._state == "closed":
            self._failure_count = max(0, self._failure_count - 1)
    
    def record_failure(self):
        """Record failed execution."""
        self._failure_count += 1
        self._last_failure_time = datetime.now()
        
        if self._state == "closed" and self._failure_count >= self.failure_threshold:
            self._state = "open"
            self.warning(f"Circuit breaker opened after {self._failure_count} failures")
        elif self._state == "half_open":
            self._state = "open"
            self.warning("Circuit breaker re-opened during half-open state")
    
    @property
    def state(self) -> str:
        """Get current circuit breaker state."""
        return self._state


class ClientSession(ModernLogger):
    """
    Client session for grouped operations with shared context.
    
    This class provides a session-based interface for executing
    multiple related operations with shared configuration and
    connection pooling.
    """
    
    def __init__(self, client: 'DistributedComputingClient'):
        """
        Initialize client session.
        
        Args:
            client: Parent client instance
        """
        super().__init__(name="ClientSession")
        self._client = client
        self._session_id = str(uuid.uuid4())[:8]
        self._active = True
        self._operations_count = 0
        self._start_time = datetime.now()
        
        self.debug(f"Created client session {self._session_id}")
    
    def execute(self, function_name: str, *args, **kwargs) -> Any:
        """Execute function with session context."""
        if not self._active:
            raise RuntimeError("Session is closed")
        
        self._operations_count += 1
        return self._client.execute(function_name, *args, **kwargs)
    
    def execute_with_context(self, 
                           context: ExecutionContext, 
                           *args, 
                           **kwargs) -> ExecutionResult:
        """Execute function with custom execution context."""
        if not self._active:
            raise RuntimeError("Session is closed")
        
        self._operations_count += 1
        return self._client.execute_with_context(context, *args, **kwargs)

    def execute_on_node(
        self,
        node_id: str,
        function_name: str,
        *args,
        timeout_ms: Optional[float] = None,
        **kwargs,
    ) -> Any:
        """Execute function on a specific node with session context."""
        if not self._active:
            raise RuntimeError("Session is closed")

        self._operations_count += 1
        return self._client.execute_on_node(
            node_id,
            function_name,
            *args,
            timeout_ms=timeout_ms,
            **kwargs,
        )

    def stream(self, function_name: str, *args, **kwargs) -> Iterator[Any]:
        """Stream function output with session context."""
        if not self._active:
            raise RuntimeError("Session is closed")

        self._operations_count += 1
        return self._client.stream(function_name, *args, **kwargs)

    def stream_with_context(
        self,
        context: ExecutionContext,
        *args,
        **kwargs,
    ) -> Iterator[Any]:
        """Stream function output with custom execution context."""
        if not self._active:
            raise RuntimeError("Session is closed")

        self._operations_count += 1
        return self._client.stream_with_context(context, *args, **kwargs)

    def stream_on_node(
        self,
        node_id: str,
        function_name: str,
        *args,
        timeout_ms: Optional[float] = None,
        **kwargs,
    ) -> Iterator[Any]:
        """Stream function output from a specific node with session context."""
        if not self._active:
            raise RuntimeError("Session is closed")

        self._operations_count += 1
        return self._client.stream_on_node(
            node_id,
            function_name,
            *args,
            timeout_ms=timeout_ms,
            **kwargs,
        )
    
    def close(self):
        """Close the session and cleanup resources."""
        if self._active:
            self._active = False
            duration = (datetime.now() - self._start_time).total_seconds()
            self.info(f"Session {self._session_id} closed "
                     f"({self._operations_count} operations, {duration:.2f}s)")
    
    def __enter__(self) -> 'ClientSession':
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class DistributedComputingClient(ModernLogger):
    """
    Advanced distributed computing client with comprehensive features.
    
    This client provides sophisticated remote function execution capabilities
    with intelligent routing, fault tolerance, performance optimization,
    and comprehensive monitoring.
    
    Key Features:
    1. Multiple Execution Strategies: Load balancing, direct targeting, broadcasting
    2. Advanced Error Handling: Circuit breaker, exponential backoff, automatic retry
    3. Performance Optimization: Connection pooling, result caching, adaptive timeouts
    4. Comprehensive Monitoring: Real-time metrics, distributed tracing, profiling
    5. Flexible Configuration: Builder pattern, environment awareness, runtime updates
    
    Architecture:
    - Strategy Pattern: Pluggable execution strategies
    - Circuit Breaker Pattern: Fault tolerance and recovery
    - Observer Pattern: Real-time monitoring and events
    - Builder Pattern: Fluent configuration construction
    
    Usage:
        >>> # Simple usage
        >>> client = DistributedComputingClient("localhost:8080")
        >>> result = client.execute("process_data", data=[1, 2, 3])
        >>> 
        >>> # Advanced usage with custom context
        >>> context = ExecutionContext(
        ...     function_name="train_model",
        ...     priority=RequestPriority.HIGH,
        ...     requirements={"gpu_required": True},
        ...     timeout_ms=600000
        ... )
        >>> result = client.execute_with_context(context, training_data)
    """
    
    # Global client registry for connection reuse
    _client_registry: Dict[str, 'DistributedComputingClient'] = {}
    _registry_lock = threading.Lock()
    
    def __init__(self,
                 gateway_address: str,
                 client_id: Optional[str] = None,
                 connection_timeout_ms: float = 10000.0,
                 request_timeout_ms: float = 300000.0,
                 retry_policy: Optional[RetryPolicy] = None,
                 enable_monitoring: bool = True,
                 enable_caching: bool = True,
                 connection_pool_size: int = 5,
                 log_level: str = "info"):
        """
        Initialize advanced distributed computing client.
        
        Args:
            gateway_address: Gateway server address (host:port)
            client_id: Unique client identifier (auto-generated if None)
            connection_timeout_ms: Connection establishment timeout
            request_timeout_ms: Default request timeout
            retry_policy: Custom retry policy (uses default if None)
            enable_monitoring: Enable performance monitoring
            enable_caching: Enable result caching
            connection_pool_size: Size of connection pool
            log_level: Logging level (debug, info, warning, error, critical)
            
        Raises:
            ValueError: If configuration parameters are invalid
            EasyRemoteError: If initialization fails
        """
        super().__init__(name="DistributedComputingClient", level=log_level)
        
        # Validate parameters
        self._validate_configuration(gateway_address, connection_timeout_ms, 
                                   request_timeout_ms, connection_pool_size)
        
        # Core configuration
        self.gateway_address = gateway_address
        self.client_id = client_id or self._generate_client_id()
        self.connection_timeout_ms = connection_timeout_ms
        self.request_timeout_ms = request_timeout_ms
        self.connection_pool_size = connection_pool_size
        
        # Policies and configuration
        self.retry_policy = retry_policy or RetryPolicy()
        self.enable_monitoring = enable_monitoring
        self.enable_caching = enable_caching
        
        # Connection management
        self._connection_state = ConnectionState.DISCONNECTED
        self._gateway_channel: Optional[grpc.Channel] = None
        self._gateway_stub: Optional[service_pb2_grpc.RemoteServiceStub] = None
        self._connection_pool: List[grpc.Channel] = []
        self._connection_lock = threading.RLock()
        
        # Fault tolerance and resilience
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=self.retry_policy.circuit_breaker_threshold,
            recovery_timeout_ms=self.retry_policy.circuit_breaker_timeout_ms
        )
        
        # Performance monitoring and metrics
        self._execution_history: List[ExecutionResult] = []
        self._connection_metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "average_response_time_ms": 0.0,
            "cache_hits": 0,
            "cache_misses": 0
        }
        
        # Caching system
        self._result_cache: Dict[str, Tuple[Any, datetime, float]] = {}  # (result, timestamp, ttl)
        self._cache_lock = threading.RLock()
        
        # Background tasks
        self._background_tasks: List[threading.Thread] = []
        self._shutdown_event = threading.Event()
        
        # Register client for connection reuse
        with DistributedComputingClient._registry_lock:
            DistributedComputingClient._client_registry[self.client_id] = self
        
        self.info(f"Initialized DistributedComputingClient '{self.client_id}' "
                 f"targeting {gateway_address}")
    
    def _validate_configuration(self, gateway_address: str, connection_timeout_ms: float,
                               request_timeout_ms: float, connection_pool_size: int):
        """Validate client configuration parameters."""
        if not gateway_address:
            raise ValueError("Gateway address cannot be empty")
        
        if connection_timeout_ms <= 0:
            raise ValueError("Connection timeout must be positive")
        
        if request_timeout_ms <= 0:
            raise ValueError("Request timeout must be positive")
        
        if connection_pool_size < 1:
            raise ValueError("Connection pool size must be at least 1")
    
    def _generate_client_id(self) -> str:
        """Generate unique client identifier."""
        import platform
        hostname = platform.node().lower().replace('.', '-')[:12]
        unique_id = str(uuid.uuid4())[:8]
        return f"client-{hostname}-{unique_id}"
    
    def connect(self) -> 'DistributedComputingClient':
        """
        Establish connection to the gateway server.
        
        Returns:
            Self for method chaining
            
        Raises:
            EasyRemoteConnectionError: If connection fails
        """
        if self._connection_state == ConnectionState.CONNECTED:
            return self
        
        with self._connection_lock:
            try:
                # Validate gateway address before connecting
                if not self.gateway_address:
                    raise EasyRemoteConnectionError(
                        message="Gateway address is None or empty"
                    )
                
                self._connection_state = ConnectionState.CONNECTING
                self.debug(f"Connecting to gateway at {self.gateway_address}")
                
                # Configure gRPC channel options for optimal performance
                channel_options = self._get_grpc_channel_options()
                
                # Create primary connection
                self._gateway_channel = grpc.insecure_channel(
                    self.gateway_address, 
                    options=channel_options
                )
                self._gateway_stub = service_pb2_grpc.RemoteServiceStub(self._gateway_channel)
                
                # Test connection with health check
                self._test_connection()
                
                # Initialize connection pool
                self._initialize_connection_pool()
                
                self._connection_state = ConnectionState.CONNECTED
                self.info(f"Successfully connected to gateway at {self.gateway_address}")
                
                return self
                
            except Exception as e:
                self._connection_state = ConnectionState.ERROR
                self.error(f"Failed to connect to gateway: {e}")
                raise EasyRemoteConnectionError(
                    message=f"Connection failed to {self.gateway_address}",
                    address=self.gateway_address,
                    cause=e
                )
    
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
    
    def _test_connection(self):
        """Test connection with simple health check."""
        try:
            # Simple connectivity test with short timeout
            # Handle both old and new gRPC API versions
            if hasattr(self._gateway_channel, 'channel_ready'):
                future = self._gateway_channel.channel_ready()
                future.result(timeout=self.connection_timeout_ms / 1000.0)
            else:
                # For newer gRPC versions, try to create a simple stub to test connectivity
                import grpc
                try:
                    # Wait for channel to be ready
                    grpc.channel_ready_future(self._gateway_channel).result(
                        timeout=self.connection_timeout_ms / 1000.0
                    )
                except Exception:
                    # If channel_ready_future doesn't exist, just continue
                    # The actual connection will be tested during the first RPC call
                    pass
        except Exception as e:
            raise EasyRemoteConnectionError(
                message=f"Gateway health check failed: {e}",
                address=self.gateway_address,
                cause=e
            )
    
    def _initialize_connection_pool(self):
        """Initialize connection pool for high throughput scenarios."""
        try:
            channel_options = self._get_grpc_channel_options()
            
            for i in range(self.connection_pool_size - 1):  # -1 because we already have primary
                channel = grpc.insecure_channel(
                    self.gateway_address,
                    options=channel_options
                )
                self._connection_pool.append(channel)
            
            self.debug(f"Initialized connection pool with {self.connection_pool_size} connections")
            
        except Exception as e:
            self.warning(f"Failed to initialize connection pool: {e}")
    
    def disconnect(self):
        """Disconnect from gateway and cleanup resources."""
        with self._connection_lock:
            try:
                self._connection_state = ConnectionState.DISCONNECTED
                
                # Close primary connection
                if self._gateway_channel:
                    self._gateway_channel.close()
                    self._gateway_channel = None
                    self._gateway_stub = None
                
                # Close connection pool
                for channel in self._connection_pool:
                    try:
                        channel.close()
                    except Exception as e:
                        self.warning(f"Error closing pooled connection: {e}")
                self._connection_pool.clear()
                
                self.info("Disconnected from gateway")
                
            except Exception as e:
                self.error(f"Error during disconnect: {e}")
    
    def execute(self, function_name: str, *args, **kwargs) -> Any:
        """
        Execute remote function with automatic load balancing.
        
        This is the primary method for remote function execution with
        intelligent routing and comprehensive error handling.
        
        Args:
            function_name: Name of the function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            Function execution result
            
        Raises:
            EasyRemoteError: If execution fails after all retries
            
        Example:
            >>> result = client.execute("process_data", data=[1, 2, 3, 4])
            >>> model_result = client.execute("train_model", 
            ...                              training_data=data, 
            ...                              epochs=100)
        """
        context = ExecutionContext(
            function_name=function_name,
            strategy=ExecutionStrategy.LOAD_BALANCED
        )
        
        execution_result = self.execute_with_context(context, *args, **kwargs)
        return execution_result.result

    def execute_on_node(
        self,
        node_id: str,
        function_name: str,
        *args,
        timeout_ms: Optional[float] = None,
        **kwargs,
    ) -> Any:
        """
        Execute function on a specific compute node.
        """
        target_node_id = str(node_id).strip()
        if not target_node_id:
            raise ValueError("node_id cannot be empty")

        context = ExecutionContext(
            function_name=function_name,
            strategy=ExecutionStrategy.DIRECT_TARGET,
            preferred_node_ids=[target_node_id],
            timeout_ms=timeout_ms,
            enable_caching=False,
        )
        execution_result = self.execute_with_context(context, *args, **kwargs)
        return execution_result.result
    
    def execute_with_context(self, 
                           context: ExecutionContext, 
                           *args, 
                           **kwargs) -> ExecutionResult:
        """
        Execute remote function with comprehensive execution context.
        
        This method provides full control over execution parameters
        including strategy, requirements, and performance preferences.
        
        Args:
            context: Execution context with detailed parameters
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            Comprehensive execution result with metadata
            
        Raises:
            EasyRemoteError: If execution fails after all retries
            
        Example:
            >>> context = ExecutionContext(
            ...     function_name="train_model",
            ...     priority=RequestPriority.HIGH,
            ...     requirements={"gpu_required": True},
            ...     timeout_ms=600000
            ... )
            >>> result = client.execute_with_context(context, training_data)
        """
        if not self._circuit_breaker.can_execute():
            raise EasyRemoteConnectionError(
                message=f"Circuit breaker is open for gateway {self.gateway_address}",
                address=self.gateway_address,
            )
        
        # Ensure connection
        if self._connection_state != ConnectionState.CONNECTED:
            self.connect()
        
        # Check cache first if enabled
        cache_key = self._generate_cache_key(context.function_name, args, kwargs)
        if context.enable_caching and self.enable_caching:
            cached_result = self._check_cache(cache_key)
            if cached_result is not None:
                self._connection_metrics["cache_hits"] += 1
                return ExecutionResult(
                    result=cached_result,
                    function_name=context.function_name,
                    cached=True,
                    cache_hit=True,
                    total_duration_ms=0.0
                )
        
        # Execute with retry logic
        last_exception = None
        start_time = time.time()
        
        for attempt in range(self.retry_policy.max_attempts):
            try:
                # Record attempt
                self._connection_metrics["total_requests"] += 1
                
                # Execute based on strategy
                if context.strategy == ExecutionStrategy.LOAD_BALANCED:
                    result = self._execute_load_balanced(context, args, kwargs)
                elif context.strategy == ExecutionStrategy.DIRECT_TARGET:
                    result = self._execute_direct_target(context, args, kwargs)
                else:
                    raise RemoteExecutionError(
                        function_name=context.function_name,
                        message=f"Unsupported execution strategy: {context.strategy}",
                    )
                
                # Record successful execution
                execution_time = (time.time() - start_time) * 1000
                self._circuit_breaker.record_success()
                self._connection_metrics["successful_requests"] += 1
                self._update_average_response_time(execution_time)
                
                # Cache result if enabled
                if context.enable_caching and self.enable_caching:
                    self._cache_result(cache_key, result.result, context.cache_ttl_seconds)
                    self._connection_metrics["cache_misses"] += 1
                
                # Update result with execution metadata
                result.total_duration_ms = execution_time
                result.retry_count = attempt
                result.execution_strategy = context.strategy
                
                if self.enable_monitoring:
                    self._execution_history.append(result)
                    # Keep only recent history
                    if len(self._execution_history) > 1000:
                        self._execution_history = self._execution_history[-500:]
                
                return result
                
            except Exception as e:
                last_exception = e
                self.warning(f"Execution attempt {attempt + 1} failed: {e}")
                
                # Check if we should retry
                if attempt == self.retry_policy.max_attempts - 1:
                    break  # Last attempt, don't wait
                
                if not self._should_retry(e):
                    break  # Non-retryable error
                
                # Calculate and apply retry delay
                delay_ms = self.retry_policy.calculate_delay(attempt)
                time.sleep(delay_ms / 1000.0)
        
        # All attempts failed
        self._circuit_breaker.record_failure()
        self._connection_metrics["failed_requests"] += 1
        
        if isinstance(last_exception, EasyRemoteError):
            raise last_exception

        raise ExceptionTranslator.as_remote_execution_error(
            last_exception or Exception("Unknown execution failure"),
            function_name=context.function_name,
            message=(
                f"Function '{context.function_name}' failed after "
                f"{self.retry_policy.max_attempts} attempts"
            ),
        )

    def stream(self, function_name: str, *args, **kwargs) -> Iterator[Any]:
        """
        Stream remote function output using load-balanced routing.
        """
        context = ExecutionContext(
            function_name=function_name,
            strategy=ExecutionStrategy.LOAD_BALANCED,
            enable_caching=False,
        )
        return self.stream_with_context(context, *args, **kwargs)

    def stream_on_node(
        self,
        node_id: str,
        function_name: str,
        *args,
        timeout_ms: Optional[float] = None,
        **kwargs,
    ) -> Iterator[Any]:
        """
        Stream remote function output from a specific node.
        """
        target_node_id = str(node_id).strip()
        if not target_node_id:
            raise ValueError("node_id cannot be empty")

        context = ExecutionContext(
            function_name=function_name,
            strategy=ExecutionStrategy.DIRECT_TARGET,
            preferred_node_ids=[target_node_id],
            timeout_ms=timeout_ms,
            enable_caching=False,
        )
        return self.stream_with_context(context, *args, **kwargs)

    def stream_with_context(
        self,
        context: ExecutionContext,
        *args,
        cancel_event: Optional[threading.Event] = None,
        initial_credits: int = 32,
        **kwargs,
    ) -> Iterator[Any]:
        """
        Stream remote function output through bidirectional StreamCall RPC.
        """
        if self._connection_state != ConnectionState.CONNECTED:
            self.connect()

        call_id = str(uuid.uuid4())

        try:
            args_bytes, kwargs_bytes = serialize_args(*args, **kwargs)
        except Exception as e:
            raise SerializationError(
                operation="serialize_args",
                message="Failed to serialize arguments for stream request",
                cause=e,
            )

        request_timeout_seconds = (context.timeout_ms or self.request_timeout_ms) / 1000.0
        outgoing_control: "queue.Queue[Optional[Any]]" = queue.Queue()
        cancelled = threading.Event()

        def request_iterator():
            start_frame = service_pb2.StreamCallFrame()
            start_frame.start.call_id = call_id
            start_frame.start.function_name = context.function_name
            start_frame.start.args = args_bytes
            start_frame.start.kwargs = kwargs_bytes

            if context.strategy == ExecutionStrategy.DIRECT_TARGET:
                if not context.preferred_node_ids:
                    raise NoAvailableNodesError(
                        message="Direct stream strategy requires preferred_node_ids",
                        function_name=context.function_name,
                        requirements={"preferred_node_ids": "required"},
                    )
                start_frame.start.node_id = context.preferred_node_ids[0]
                start_frame.start.use_load_balancing = False
            else:
                start_frame.start.use_load_balancing = True
                start_frame.start.load_balancing_strategy = context.strategy.value

            yield start_frame

            credits = max(0, min(int(initial_credits), 1024))
            if credits:
                ack_frame = service_pb2.StreamCallFrame()
                ack_frame.ack.call_id = call_id
                ack_frame.ack.credits = credits
                yield ack_frame

            while True:
                frame = outgoing_control.get()
                if frame is None:
                    break
                yield frame

        response_stream = self._gateway_stub.StreamCall(
            request_iterator(),
            timeout=request_timeout_seconds,
        )

        if cancel_event is not None:

            def _watch_cancel() -> None:
                cancel_event.wait()
                if cancelled.is_set():
                    return
                try:
                    cancel_frame = service_pb2.StreamCallFrame()
                    cancel_frame.cancel.call_id = call_id
                    cancel_frame.cancel.reason = "client_cancel_requested"
                    outgoing_control.put(cancel_frame)
                    cancelled.set()
                    outgoing_control.put(None)
                except Exception:
                    pass

                cancel_rpc = getattr(response_stream, "cancel", None)
                if callable(cancel_rpc):
                    try:
                        cancel_rpc()
                    except Exception:
                        pass

            threading.Thread(
                target=_watch_cancel,
                name=f"EasyRemoteStreamCancel-{call_id}",
                daemon=True,
            ).start()

        try:
            for frame in response_stream:
                if frame.HasField("error"):
                    raise RemoteExecutionError(
                        function_name=context.function_name,
                        node_id=frame.error.node_id or None,
                        message=frame.error.message or "Stream call failed",
                    )

                if not frame.HasField("exec_res"):
                    continue

                exec_result = frame.exec_res
                if exec_result.has_error:
                    raise RemoteExecutionError(
                        function_name=exec_result.function_name or context.function_name,
                        node_id=exec_result.node_id or None,
                        message=exec_result.error_message,
                    )

                if exec_result.is_done:
                    break

                payload = exec_result.chunk or exec_result.result
                if not payload:
                    continue

                try:
                    item = deserialize_result(payload)
                    yield item
                    if not cancelled.is_set():
                        ack_frame = service_pb2.StreamCallFrame()
                        ack_frame.ack.call_id = call_id
                        ack_frame.ack.credits = 1
                        outgoing_control.put(ack_frame)
                except Exception as exc:
                    raise SerializationError(
                        operation="deserialize_result",
                        message="Failed to deserialize stream payload",
                        cause=exc,
                    ) from exc
        except grpc.RpcError as e:
            if cancel_event is not None and cancel_event.is_set():
                return
            raise EasyRemoteConnectionError(
                message=f"gRPC stream call failed: {e}",
                cause=e,
            )
        finally:
            if not cancelled.is_set():
                cancel_frame = service_pb2.StreamCallFrame()
                cancel_frame.cancel.call_id = call_id
                cancel_frame.cancel.reason = "client_stream_closed"
                outgoing_control.put(cancel_frame)
                cancelled.set()
            outgoing_control.put(None)

            cancel = getattr(response_stream, "cancel", None)
            if callable(cancel):
                try:
                    cancel()
                except Exception:
                    pass
    
    def _execute_load_balanced(self, 
                              context: ExecutionContext, 
                              args: Tuple[Any, ...], 
                              kwargs: Dict[str, Any]) -> ExecutionResult[Any]:
        """Execute function using intelligent load balancing."""
        call_id = str(uuid.uuid4())
        
        try:
            #  Enhanced client logging
            self.debug(f" [CLIENT] Preparing to call function '{context.function_name}' (call_id: {call_id})")
            
            # Serialize arguments
            args_bytes, kwargs_bytes = serialize_args(*args, **kwargs)
            self.debug(f"📦 [CLIENT] Arguments serialized for '{context.function_name}'")
        except Exception as e:
            self.error(f"❌ [CLIENT] Failed to serialize arguments: {e}")
            raise SerializationError(
                operation="serialize_args",
                message="Failed to serialize arguments for load-balanced request",
                cause=e,
            )
        
        # Create load balanced call request
        request = service_pb2.LoadBalancedCallRequest(
            call_id=call_id,
            function_name=context.function_name,
            args=args_bytes,
            kwargs=kwargs_bytes,
            strategy=context.strategy.value,
            requirements=str(context.requirements or {}),
            timeout=int(context.timeout_ms or self.request_timeout_ms)
        )
        
        try:
            self.debug(f" [CLIENT] Sending request to gateway for '{context.function_name}'...")
            
            start_time = time.time()
            response = self._gateway_stub.CallWithLoadBalancing(
                request,
                timeout=(context.timeout_ms or self.request_timeout_ms) / 1000.0
            )
            network_time = (time.time() - start_time) * 1000
            
            self.debug(f"📨 [CLIENT] Received response from gateway for '{context.function_name}' "
                     f"(network time: {network_time:.1f}ms)")
            
            if response.has_error:
                self.error(f"❌ [CLIENT] Remote execution failed: {response.error_message}")
                raise RemoteExecutionError(
                    function_name=context.function_name,
                    node_id=response.selected_node_id,
                    message=response.error_message
                )
            
            # Deserialize result
            result = deserialize_result(response.result)
            execution_time = getattr(response, 'execution_time_ms', 0.0)
            
            self.debug(f"✅ [CLIENT] SUCCESS! Function '{context.function_name}' completed "
                     f"(execution: {execution_time:.1f}ms, network: {network_time:.1f}ms)")
            
            return ExecutionResult(
                result=result,
                function_name=context.function_name,
                node_id=response.selected_node_id,
                network_latency_ms=network_time,
                execution_time_ms=execution_time
            )
            
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                self.error(f"❌ [CLIENT] No nodes available for function '{context.function_name}'")
                raise NoAvailableNodesError(
                    message=f"No nodes available for function '{context.function_name}'",
                    function_name=context.function_name,
                )
            self.error(f"💥 [CLIENT] gRPC error during call: {e}")
            raise EasyRemoteConnectionError(
                message=f"gRPC error during load-balanced call: {e}",
                cause=e
            )
    
    def _execute_direct_target(self, 
                              context: ExecutionContext, 
                              args: Tuple[Any, ...], 
                              kwargs: Dict[str, Any]) -> ExecutionResult[Any]:
        """Execute function on specific target node."""
        if not context.preferred_node_ids:
            raise NoAvailableNodesError(
                message="Direct target strategy requires preferred_node_ids",
                function_name=context.function_name,
                requirements={"preferred_node_ids": "required"},
            )
        
        node_id = context.preferred_node_ids[0]  # Use first preferred node
        
        try:
            args_bytes, kwargs_bytes = serialize_args(*args, **kwargs)
        except Exception as e:
            raise SerializationError(
                operation="serialize_args",
                message="Failed to serialize arguments for direct target request",
                cause=e,
            )
        
        request = service_pb2.DirectCallRequest(
            call_id=str(uuid.uuid4()),
            node_id=node_id,
            function_name=context.function_name,
            args=args_bytes,
            kwargs=kwargs_bytes
        )
        
        try:
            start_time = time.time()
            response = self._gateway_stub.CallDirect(
                request,
                timeout=(context.timeout_ms or self.request_timeout_ms) / 1000.0
            )
            network_time = (time.time() - start_time) * 1000
            
            if response.has_error:
                raise RemoteExecutionError(
                    function_name=context.function_name,
                    node_id=node_id,
                    message=response.error_message
                )
            
            result = deserialize_result(response.result)
            
            return ExecutionResult(
                result=result,
                function_name=context.function_name,
                node_id=node_id,
                network_latency_ms=network_time
            )
            
        except grpc.RpcError as e:
            raise EasyRemoteConnectionError(
                message=f"Direct call failed: {e}",
                cause=e
            )
    
    def _should_retry(self, exception: Exception) -> bool:
        """Determine if an exception should trigger a retry."""
        if isinstance(exception, grpc.RpcError):
            return exception.code() in self.retry_policy.retryable_status_codes
        
        # Retry on connection errors and timeouts
        return isinstance(exception, (
            EasyRemoteConnectionError,
            TimeoutError,
        ))
    
    def _generate_cache_key(self, function_name: str, args: tuple, kwargs: dict) -> str:
        """Generate cache key for function call."""
        import hashlib
        
        # Create deterministic hash of function name and arguments
        content = f"{function_name}:{args}:{sorted(kwargs.items())}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _check_cache(self, cache_key: str) -> Optional[Any]:
        """Check if result is available in cache."""
        with self._cache_lock:
            if cache_key in self._result_cache:
                result, timestamp, ttl = self._result_cache[cache_key]
                
                # Check if cache entry is still valid
                if ttl is None or (datetime.now() - timestamp).total_seconds() < ttl:
                    self.debug(f"Cache hit for key {cache_key[:8]}...")
                    return result
                else:
                    # Remove expired entry
                    del self._result_cache[cache_key]
        
        return None
    
    def _cache_result(self, cache_key: str, result: Any, ttl_seconds: Optional[float]):
        """Cache execution result."""
        with self._cache_lock:
            self._result_cache[cache_key] = (result, datetime.now(), ttl_seconds)
            
            # Simple cache size management
            if len(self._result_cache) > 10000:
                # Remove oldest 20% of entries
                sorted_entries = sorted(
                    self._result_cache.items(),
                    key=lambda x: x[1][1]  # Sort by timestamp
                )
                remove_count = len(sorted_entries) // 5
                for key, _ in sorted_entries[:remove_count]:
                    del self._result_cache[key]
    
    def _update_average_response_time(self, response_time_ms: float):
        """Update running average response time."""
        current_avg = self._connection_metrics["average_response_time_ms"]
        total_requests = self._connection_metrics["total_requests"]
        
        if total_requests == 1:
            self._connection_metrics["average_response_time_ms"] = response_time_ms
        else:
            # Exponential moving average
            alpha = 2.0 / (total_requests + 1)
            self._connection_metrics["average_response_time_ms"] = (
                alpha * response_time_ms + (1 - alpha) * current_avg
            )
    
    def session(self) -> ClientSession:
        """
        Create a new client session for grouped operations.
        
        Returns:
            New client session instance
            
        Example:
            >>> with client.session() as session:
            ...     result1 = session.execute("func1", arg1)
            ...     result2 = session.execute("func2", arg2)
        """
        return ClientSession(self)
    
    def list_nodes(self) -> List[Dict[str, Any]]:
        """
        Get list of available compute nodes.
        
        Returns:
            List of node information dictionaries
            
        Raises:
            EasyRemoteConnectionError: If request fails
        """
        if self._connection_state != ConnectionState.CONNECTED:
            self.connect()
        
        try:
            request = service_pb2.ListNodesRequest(client_id=self.client_id)
            response = self._gateway_stub.ListNodes(request)
            
            nodes = []
            for node_info in response.nodes:
                nodes.append({
                    "node_id": node_info.node_id,
                    "functions": [item.name for item in node_info.functions],
                    "status": node_info.status,
                    "last_heartbeat": node_info.last_heartbeat,
                    "current_load": node_info.current_load,
                    "capabilities": list(getattr(node_info, "capabilities", [])),
                    "location": getattr(node_info, "location", ""),
                    "version": getattr(node_info, "version", ""),
                })
            
            return nodes
            
        except grpc.RpcError as e:
            raise EasyRemoteConnectionError(
                message=f"Failed to list nodes: {e}",
                cause=e
            )

    def find_nodes(
        self,
        *,
        required_capabilities: Optional[Iterable[str]] = None,
        required_functions: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find nodes matching required capabilities/functions.
        """
        capability_set = {
            str(item).strip()
            for item in (required_capabilities or [])
            if str(item).strip()
        }
        function_set = {
            str(item).strip()
            for item in (required_functions or [])
            if str(item).strip()
        }

        candidates = self.list_nodes()
        matched: List[Dict[str, Any]] = []
        for node in candidates:
            node_capabilities = set(node.get("capabilities", []))
            node_functions = set(node.get("functions", []))
            if capability_set and not capability_set.issubset(node_capabilities):
                continue
            if function_set and not function_set.issubset(node_functions):
                continue
            matched.append(node)
        return matched

    def resolve_node_id(
        self,
        *,
        required_capabilities: Optional[Iterable[str]] = None,
        required_functions: Optional[Iterable[str]] = None,
    ) -> str:
        """
        Resolve exactly one node id by required capability/function filters.
        """
        matches = self.find_nodes(
            required_capabilities=required_capabilities,
            required_functions=required_functions,
        )
        if not matches:
            raise NoAvailableNodesError(
                message="No nodes match required capability/function filters",
            )
        if len(matches) > 1:
            candidate_ids = sorted(item["node_id"] for item in matches)
            raise NoAvailableNodesError(
                message=(
                    "Multiple nodes match filters; refine selector. matches={0}"
                ).format(candidate_ids)
            )
        return str(matches[0]["node_id"])
    
    def get_node_status(self, node_id: str) -> Dict[str, Any]:
        """
        Get detailed status for a specific node.
        
        Args:
            node_id: ID of the node to query
            
        Returns:
            Node status information dictionary
            
        Raises:
            NoAvailableNodesError: If node is not found
            EasyRemoteConnectionError: If request fails
        """
        if self._connection_state != ConnectionState.CONNECTED:
            self.connect()
        
        try:
            request = service_pb2.NodeStatusRequest(
                client_id=self.client_id,
                node_id=node_id
            )
            response = self._gateway_stub.GetNodeStatus(request)
            
            return {
                "node_id": response.node_id,
                "status": response.status,
                "cpu_usage": response.cpu_usage,
                "memory_usage": response.memory_usage,
                "gpu_usage": response.gpu_usage,
                "current_load": response.current_load,
                "functions": list(response.functions),
                "health_score": getattr(response, 'health_score', 1.0),
                "last_seen": getattr(response, 'last_seen', 0)
            }
            
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                raise NoAvailableNodesError(message=f"Node '{node_id}' not found")
            raise EasyRemoteConnectionError(
                message=f"Failed to get node status: {e}",
                cause=e
            )
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive client performance metrics.
        
        Returns:
            Dictionary with performance metrics and statistics
        """
        metrics = dict(self._connection_metrics)
        
        # Add derived metrics
        total_requests = metrics["total_requests"]
        if total_requests > 0:
            metrics["success_rate"] = metrics["successful_requests"] / total_requests
            metrics["failure_rate"] = metrics["failed_requests"] / total_requests
            metrics["cache_hit_rate"] = metrics["cache_hits"] / (
                metrics["cache_hits"] + metrics["cache_misses"]
            ) if (metrics["cache_hits"] + metrics["cache_misses"]) > 0 else 0.0
        else:
            metrics["success_rate"] = 0.0
            metrics["failure_rate"] = 0.0
            metrics["cache_hit_rate"] = 0.0
        
        # Add execution history statistics
        if self.enable_monitoring and self._execution_history:
            recent_executions = self._execution_history[-100:]  # Last 100 executions
            
            metrics["recent_executions"] = len(recent_executions)
            metrics["average_execution_time_ms"] = sum(
                r.execution_time_ms for r in recent_executions
            ) / len(recent_executions)
            metrics["average_efficiency_score"] = sum(
                r.efficiency_score for r in recent_executions
            ) / len(recent_executions)
        
        # Add circuit breaker status
        metrics["circuit_breaker_state"] = self._circuit_breaker.state
        
        # Add connection information
        metrics["connection_state"] = self._connection_state.value
        metrics["gateway_address"] = self.gateway_address
        metrics["client_id"] = self.client_id
        
        return metrics
    
    def clear_cache(self):
        """Clear the result cache."""
        with self._cache_lock:
            cleared_count = len(self._result_cache)
            self._result_cache.clear()
            self.info(f"Cleared {cleared_count} cached results")
    
    def __enter__(self) -> 'DistributedComputingClient':
        """Context manager entry - establish connection."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup resources."""
        self.disconnect()
    
    def __del__(self):
        """Cleanup resources on object destruction."""
        try:
            self.disconnect()
        except Exception:
            pass


class ClientBuilder:
    """
    Builder for fluent client configuration and construction.
    
    This builder provides a convenient way to configure and create
    distributed computing clients with comprehensive customization options.
    
    Example:
        >>> client = ClientBuilder() \\
        ...     .with_gateway("production-gateway:8080") \\
        ...     .with_retry_policy(max_attempts=5, backoff_multiplier=2.0) \\
        ...     .with_load_balancing_strategy("ml_enhanced") \\
        ...     .enable_caching(ttl_seconds=300) \\
        ...     .enable_monitoring() \\
        ...     .build()
    """
    
    def __init__(self):
        """Initialize client builder with default configuration."""
        self._gateway_address: Optional[str] = None
        self._client_id: Optional[str] = None
        self._connection_timeout_ms: float = 10000.0
        self._request_timeout_ms: float = 300000.0
        self._retry_policy: Optional[RetryPolicy] = None
        self._enable_monitoring: bool = True
        self._enable_caching: bool = True
        self._connection_pool_size: int = 5
        self._log_level: str = "info"
    
    def with_gateway(self, address: str) -> 'ClientBuilder':
        """Set gateway server address."""
        self._gateway_address = address
        return self
    
    def with_client_id(self, client_id: str) -> 'ClientBuilder':
        """Set custom client identifier."""
        self._client_id = client_id
        return self
    
    def with_timeouts(self, 
                     connection_timeout_ms: float, 
                     request_timeout_ms: float) -> 'ClientBuilder':
        """Configure timeout settings."""
        self._connection_timeout_ms = connection_timeout_ms
        self._request_timeout_ms = request_timeout_ms
        return self
    
    def with_retry_policy(self, 
                         max_attempts: int = 3,
                         backoff_multiplier: float = 2.0,
                         circuit_breaker_threshold: int = 5) -> 'ClientBuilder':
        """Configure retry policy."""
        self._retry_policy = RetryPolicy(
            max_attempts=max_attempts,
            backoff_multiplier=backoff_multiplier,
            circuit_breaker_threshold=circuit_breaker_threshold
        )
        return self
    
    def enable_monitoring(self, enabled: bool = True) -> 'ClientBuilder':
        """Enable or disable performance monitoring."""
        self._enable_monitoring = enabled
        return self
    
    def enable_caching(self, enabled: bool = True) -> 'ClientBuilder':
        """Enable or disable result caching."""
        self._enable_caching = enabled
        return self
    
    def with_connection_pool_size(self, size: int) -> 'ClientBuilder':
        """Set connection pool size."""
        self._connection_pool_size = size
        return self
    
    def with_log_level(self, level: str) -> 'ClientBuilder':
        """Set logging level."""
        self._log_level = level
        return self
    
    def build(self) -> DistributedComputingClient:
        """
        Build and return configured client instance.
        
        Returns:
            Configured DistributedComputingClient instance
            
        Raises:
            ValueError: If required configuration is missing
        """
        if not self._gateway_address:
            raise ValueError("Gateway address is required")
        
        return DistributedComputingClient(
            gateway_address=self._gateway_address,
            client_id=self._client_id,
            connection_timeout_ms=self._connection_timeout_ms,
            request_timeout_ms=self._request_timeout_ms,
            retry_policy=self._retry_policy,
            enable_monitoring=self._enable_monitoring,
            enable_caching=self._enable_caching,
            connection_pool_size=self._connection_pool_size,
            log_level=self._log_level
        )


# Convenience functions for global client management
_default_client: Optional[DistributedComputingClient] = None
_client_lock = threading.Lock()


def set_default_gateway(gateway_address: str, **kwargs) -> DistributedComputingClient:
    """
    Set default gateway and create global client instance.
    
    Args:
        gateway_address: Gateway server address
        **kwargs: Additional client configuration parameters
        
    Returns:
        Configured client instance
        
    Example:
        >>> client = set_default_gateway("localhost:8080", enable_caching=True)
        >>> result = call("my_function", arg1, arg2)
    """
    global _default_client
    
    with _client_lock:
        if _default_client:
            _default_client.disconnect()
        
        _default_client = DistributedComputingClient(gateway_address, **kwargs)
        _default_client.connect()
        
        return _default_client


def get_default_client() -> Optional[DistributedComputingClient]:
    """Get the default client instance."""
    return _default_client


def call(function_name: str, *args, **kwargs) -> Any:
    """
    Execute function using default client.
    
    Args:
        function_name: Name of function to execute
        *args: Positional arguments
        **kwargs: Keyword arguments
        
    Returns:
        Function execution result
        
    Raises:
        EasyRemoteError: If no default client is set
    """
    if _default_client is None:
        raise EasyRemoteConnectionError(
            message="No default gateway configured. Call set_default_gateway() first."
        )
    return _default_client.execute(function_name, *args, **kwargs)


def call_node(node_id: str, function_name: str, *args, **kwargs) -> Any:
    """
    Execute function on specific node using default client.
    
    Args:
        node_id: Target node identifier
        function_name: Name of function to execute
        *args: Positional arguments
        **kwargs: Keyword arguments
        
    Returns:
        Function execution result
        
    Raises:
        EasyRemoteError: If no default client is set
    """
    if _default_client is None:
        raise EasyRemoteConnectionError(
            message="No default gateway configured. Call set_default_gateway() first."
        )
    return _default_client.execute_on_node(node_id, function_name, *args, **kwargs)


def list_nodes() -> List[Dict[str, Any]]:
    """
    List available nodes using default client.
    
    Returns:
        List of node information dictionaries
        
    Raises:
        EasyRemoteError: If no default client is set
    """
    if _default_client is None:
        raise EasyRemoteConnectionError(
            message="No default gateway configured. Call set_default_gateway() first."
        )
    return _default_client.list_nodes()


def call_stream(function_name: str, *args, **kwargs) -> Iterator[Any]:
    """
    Stream function output using the default client.
    """
    if _default_client is None:
        raise EasyRemoteConnectionError(
            message="No default gateway configured. Call set_default_gateway() first."
        )
    return _default_client.stream(function_name, *args, **kwargs)


def call_stream_node(node_id: str, function_name: str, *args, **kwargs) -> Iterator[Any]:
    """
    Stream function output from a specific node using the default client.
    """
    if _default_client is None:
        raise EasyRemoteConnectionError(
            message="No default gateway configured. Call set_default_gateway() first."
        )
    return _default_client.stream_on_node(node_id, function_name, *args, **kwargs)


# Backward compatibility aliases
Client = DistributedComputingClient


# Export all public classes and functions
__all__ = [
    # Core classes
    'DistributedComputingClient',
    'ClientBuilder', 
    'ClientSession',
    'ExecutionContext',
    'ExecutionResult',
    'RetryPolicy',
    'CircuitBreaker',
    
    # Enums
    'ConnectionState',
    'ExecutionStrategy',
    
    # Convenience functions
    'set_default_gateway',
    'get_default_client',
    'call',
    'call_node', 
    'call_stream',
    'call_stream_node',
    'list_nodes',
    
    # Backward compatibility
    'Client'
] 
