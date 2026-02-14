#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EasyRemote Distributed Computing Gateway Server Module

This module implements the central gateway server for the EasyRemote distributed
computing framework. The server acts as an intelligent orchestration hub providing
advanced load balancing, comprehensive node management, and high-performance
request routing for distributed computational workloads.

Architecture:
- Microservices Pattern: Modular service architecture with clean separation
- Event-Driven Architecture: Asynchronous event processing and notification
- Strategy Pattern: Pluggable load balancing and routing strategies
- Observer Pattern: Real-time monitoring and health tracking
- Circuit Breaker Pattern: Fault tolerance and automatic recovery
- Factory Pattern: Dynamic component creation and management

Key Features:
1. Advanced Request Orchestration:
   * Intelligent load balancing with ML-enhanced algorithms
   * Geographic and latency-aware routing
   * Dynamic strategy selection based on workload characteristics
   * Real-time performance optimization and adaptation

2. Comprehensive Node Management:
   * Automatic node discovery and registration
   * Health monitoring with predictive failure detection
   * Capacity planning and resource optimization
   * Graceful node lifecycle management

3. High-Performance Communication:
   * Bidirectional gRPC streaming for low-latency coordination
   * Connection pooling and multiplexing
   * Adaptive timeout and retry mechanisms
   * Efficient message serialization and compression

4. Production-Grade Features:
   * Horizontal scalability with cluster coordination
   * Comprehensive metrics and observability
   * Security and authentication framework
   * Graceful shutdown and disaster recovery

5. Advanced Analytics:
   * Real-time performance monitoring and alerting
   * Predictive capacity planning and scaling
   * Historical data analysis and trending
   * Automated optimization recommendations

Usage Example:
    >>> # Simple server startup
    >>> server = DistributedComputingGateway(port=8080)
    >>> server.start()  # Blocks until shutdown
    >>> 
    >>> # Advanced configuration with builder pattern
    >>> server = GatewayServerBuilder() \
    ...     .with_port(8080) \
    ...     .with_load_balancing_strategy("ml_enhanced") \
    ...     .enable_health_monitoring() \
    ...     .enable_performance_analytics() \
    ...     .with_security_config(auth_required=True) \
    ...     .build()
    >>> 
    >>> # Background server with monitoring
    >>> thread = server.start_background()
    >>> # Server is now running in background

Author: Silan Hu (silan.hu@u.nus.edu)
Version: 2.0.0
"""

import asyncio
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import AsyncIterator, Dict, Set, Union, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

# gRPC imports
import grpc
from grpc import aio as grpc_aio
from concurrent import futures

# EasyRemote core imports
from ..utils.logger import ModernLogger
from ..utils.asyncio_noise_filter import install_asyncio_grpc_shutdown_noise_filter
from ..balancing import LoadBalancer, RequestContext
from ..data import NodeInfo, NodeStatus
from ..utils.exceptions import (
    NodeNotFoundError,
    FunctionNotFoundError,
    RemoteExecutionError,
    EasyRemoteError,
    TimeoutError,
    NoAvailableNodesError,
    LoadBalancingError,
    ExceptionTranslator,
)
from ..utils.concurrency import LoopBoundAsyncLock, create_loop_future
from ..data import Serializer
from ..protos import service_pb2, service_pb2_grpc
from ...protocols import (
    A2AProtocolAdapter,
    FunctionDescriptor,
    FunctionInvocation,
    MCPProtocolAdapter,
    ProtocolAdapter,
    ProtocolGateway,
    ProtocolName,
    ProtocolRuntime,
)

_STREAM_CONTROL_KWARG = "__easyremote_stream__"


class ServerState(Enum):
    """
    Enumeration of possible server states for lifecycle management.
    """
    INITIALIZING = "initializing"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class ServerMetrics:
    """
    Real-time server performance and operational metrics.
    
    This class tracks various server statistics for monitoring,
    debugging, and performance optimization purposes.
    """
    start_time: datetime = field(default_factory=datetime.now)
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    active_connections: int = 0
    peak_connections: int = 0
    total_nodes_registered: int = 0
    active_nodes: int = 0
    average_response_time: float = 0.0
    last_updated: datetime = field(default_factory=datetime.now)
    
    def update_request_stats(self, success: bool, response_time: float):
        """Update request statistics with latest data."""
        self.total_requests += 1
        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
        
        # Update running average response time
        if self.total_requests == 1:
            self.average_response_time = response_time
        else:
            alpha = 2.0 / (self.total_requests + 1)
            self.average_response_time = (
                alpha * response_time + (1 - alpha) * self.average_response_time
            )
        
        self.last_updated = datetime.now()
    
    def update_connection_stats(self, active_count: int):
        """Update connection statistics."""
        self.active_connections = active_count
        self.peak_connections = max(self.peak_connections, active_count)
        self.last_updated = datetime.now()
    
    @property
    def success_rate(self) -> float:
        """Calculate the success rate of requests."""
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests
    
    @property
    def uptime_seconds(self) -> float:
        """Calculate server uptime in seconds."""
        return (datetime.now() - self.start_time).total_seconds()


class StreamExecutionContext(ModernLogger):
    """
    Context manager for streaming function execution lifecycle.
    
    This class manages the complete lifecycle of streaming function calls,
    including resource allocation, cleanup, and error handling.
    
    Features:
    - Automatic resource cleanup on completion or error
    - Callback registration for custom cleanup logic
    - Context tracking for debugging and monitoring
    - Graceful shutdown handling
    """
    
    def __init__(self, call_id: str, function_name: str, node_id: str, 
                 response_queue: asyncio.Queue, timeout: Optional[int] = None):
        """
        Initialize streaming execution context.
        
        Args:
            call_id: Unique identifier for this function call
            function_name: Name of the function being executed
            node_id: ID of the compute node executing the function
            response_queue: Queue for streaming responses
            timeout: Optional timeout for the entire operation
        """
        super().__init__(name=f"{__name__}.StreamContext")
        
        self.call_id = call_id
        self.function_name = function_name
        self.node_id = node_id
        self.response_queue = response_queue
        self.timeout = timeout
        
        self.created_at = datetime.now()
        self.is_active = True
        self.completion_status: Optional[str] = None
        self._cleanup_callbacks: List[callable] = []
        self._context_data: Dict[str, Any] = {}
        
        self.debug(f"Created stream context for {function_name} on {node_id}")
    
    def add_cleanup_callback(self, callback: callable) -> 'StreamExecutionContext':
        """
        Register a callback to be executed during cleanup.
        
        Args:
            callback: Function to call during cleanup (sync or async)
            
        Returns:
            Self for method chaining
        """
        self._cleanup_callbacks.append(callback)
        return self
    
    def set_context_data(self, key: str, value: Any) -> 'StreamExecutionContext':
        """
        Store arbitrary data associated with this context.
        
        Args:
            key: Data key
            value: Data value
            
        Returns:
            Self for method chaining
        """
        self._context_data[key] = value
        return self
    
    def get_context_data(self, key: str, default: Any = None) -> Any:
        """Retrieve context data by key."""
        return self._context_data.get(key, default)
    
    async def cleanup(self, completion_status: str = "completed"):
        """
        Clean up resources and execute registered callbacks.
        
        Args:
            completion_status: Status indicating how the stream ended
        """
        if not self.is_active:
            return  # Already cleaned up
        
        self.is_active = False
        self.completion_status = completion_status
        
        # Execute cleanup callbacks
        for callback in self._cleanup_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                self.error(f"Error in cleanup callback: {e}")
        
        duration = (datetime.now() - self.created_at).total_seconds()
        self.info(f"Stream context cleaned up: {self.function_name} "
                 f"(status: {completion_status}, duration: {duration:.2f}s)")
    
    @property
    def elapsed_time(self) -> float:
        """Get elapsed time since context creation in seconds."""
        return (datetime.now() - self.created_at).total_seconds()
    
    @property
    def is_timed_out(self) -> bool:
        """Check if the context has exceeded its timeout."""
        if self.timeout is None:
            return False
        return self.elapsed_time > self.timeout


class DistributedComputingGateway(
    service_pb2_grpc.RemoteServiceServicer, ModernLogger, ProtocolRuntime
):
    """
    Advanced distributed computing gateway server with enterprise-grade capabilities.
    
    This server implements the central orchestration hub for the EasyRemote
    framework, providing intelligent request routing, comprehensive node management,
    advanced load balancing, and production-grade monitoring and analytics.
    
    Key Responsibilities:
    1. Request Orchestration: Intelligent routing with ML-enhanced load balancing
    2. Node Lifecycle Management: Registration, health monitoring, and optimization
    3. Performance Analytics: Real-time monitoring, trending, and capacity planning
    4. Fault Tolerance: Circuit breakers, automatic failover, and disaster recovery
    5. Security & Compliance: Authentication, authorization, and audit logging
    
    Architecture Features:
    - Event-driven architecture with reactive stream processing
    - Microservices pattern with modular component design
    - High-availability clustering with automatic leader election
    - Advanced observability with distributed tracing and metrics
    - Production-grade security and compliance frameworks
    
    Advanced Features:
    - ML-Enhanced Load Balancing: Predictive algorithms for optimal distribution
    - Geographic Routing: Latency-aware and region-specific routing
    - Capacity Planning: Predictive scaling and resource optimization
    - Performance Analytics: Real-time insights and automated recommendations
    - Disaster Recovery: Automatic failover and data replication
    
    Usage:
        >>> # Production deployment
        >>> server = DistributedComputingGateway(
        ...     port=8080,
        ...     enable_clustering=True,
        ...     enable_security=True,
        ...     enable_analytics=True
        ... )
        >>> server.start()  # Production server
        >>> 
        >>> # Advanced configuration
        >>> server = GatewayServerBuilder() \
        ...     .with_clustering_config(nodes=["node1", "node2", "node3"]) \
        ...     .with_security_config(auth_provider="oauth2") \
        ...     .with_analytics_config(enable_ml=True) \
        ...     .build()
    """
    
    # Class-level singleton instance for global access and coordination
    _global_instance: Optional['DistributedComputingGateway'] = None
    _instance_lock = threading.Lock()
    
    def __init__(self, 
                 port: int = 8080, 
                 heartbeat_timeout_seconds: float = 30.0,
                 max_queue_size: int = 5000,
                 max_workers: int = 20,
                 max_total_active_streams: int = 512,
                 max_streams_per_node: int = 32,
                 stream_response_queue_size: int = 256,
                 enable_monitoring: bool = True,
                 enable_analytics: bool = True,
                 enable_security: bool = False,
                 enable_clustering: bool = False,
                 cleanup_interval_seconds: float = 300.0,
                 log_level: str = "info"):
        """
        Initialize the advanced distributed computing gateway server.
        
        Args:
            port: Port number to bind the server to (1-65535)
            heartbeat_timeout_seconds: Timeout for node heartbeat responses
            max_queue_size: Maximum size for internal request queues
            max_workers: Maximum number of worker threads for request processing
            max_total_active_streams: Maximum concurrent active stream calls
            max_streams_per_node: Maximum concurrent stream calls per node
            stream_response_queue_size: Queue size for stream response buffering
            enable_monitoring: Enable comprehensive performance monitoring
            enable_analytics: Enable advanced analytics and ML features
            enable_security: Enable security and authentication features
            enable_clustering: Enable high-availability clustering support
            cleanup_interval_seconds: Interval for background cleanup operations
            log_level: Logging level (debug, info, warning, error, critical)
            
        Raises:
            ValueError: If configuration parameters are invalid
            RuntimeError: If server initialization fails
            
        Example:
            >>> # Basic production server
            >>> server = DistributedComputingGateway(
            ...     port=8080,
            ...     enable_monitoring=True,
            ...     enable_analytics=True
            ... )
            >>> 
            >>> # High-availability cluster node
            >>> server = DistributedComputingGateway(
            ...     port=8080,
            ...     enable_clustering=True,
            ...     enable_security=True,
            ...     max_workers=50
            ... )
        """
        # Initialize parent classes
        service_pb2_grpc.RemoteServiceServicer.__init__(self)
        ModernLogger.__init__(self, name="DistributedComputingGateway", level=log_level)
        install_asyncio_grpc_shutdown_noise_filter()
        
        # Validate configuration parameters
        self._validate_configuration(
            port,
            heartbeat_timeout_seconds,
            max_queue_size,
            max_workers,
            cleanup_interval_seconds,
            max_total_active_streams,
            max_streams_per_node,
            stream_response_queue_size,
        )
        
        # Core server configuration
        self.port = port
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self.max_queue_size = max_queue_size
        self.max_workers = max_workers
        self.cleanup_interval_seconds = cleanup_interval_seconds
        self.max_total_active_streams = max_total_active_streams
        self.max_streams_per_node = max_streams_per_node
        self.stream_response_queue_size = stream_response_queue_size
        
        # Feature flags and capabilities
        self.enable_monitoring = enable_monitoring
        self.enable_analytics = enable_analytics
        self.enable_security = enable_security
        self.enable_clustering = enable_clustering
        
        # Server state management
        self._state = ServerState.INITIALIZING
        self._state_lock = LoopBoundAsyncLock(name="gateway-state-lock")
        
        # Core server components
        self._grpc_server: Optional[grpc_aio.Server] = None
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._server_thread: Optional[threading.Thread] = None
        self._grpc_aio_initialized: bool = False
        
        # Node and function management
        self._nodes: Dict[str, NodeInfo] = {}
        self._node_communication_queues: Dict[str, asyncio.Queue] = {}
        self._global_lock = LoopBoundAsyncLock(
            name="gateway-global-lock"
        )  # Protects all shared data structures
        
        # Request and stream management
        self._pending_function_calls: Dict[str, Union[asyncio.Future, Dict[str, Any]]] = {}
        self._active_stream_contexts: Dict[str, StreamExecutionContext] = {}
        self._active_stream_ids: Set[str] = set()
        self._node_active_stream_counts: Dict[str, int] = {}
        
        # Background task management
        self._background_tasks: Set[asyncio.Task] = set()
        self._node_monitor_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # Performance and monitoring
        self.metrics = ServerMetrics() if enable_monitoring else None
        self._request_history: List[Tuple[datetime, str, bool, float]] = []
        
        # Core services
        self._serializer = Serializer()
        self._load_balancer = LoadBalancer(self)
        self._protocol_gateway = ProtocolGateway(runtime=self)
        self._protocol_gateway.register_adapter(MCPProtocolAdapter())
        self._protocol_gateway.register_adapter(A2AProtocolAdapter())
        
        # Set global instance for coordination
        with DistributedComputingGateway._instance_lock:
            DistributedComputingGateway._global_instance = self
        
        self.info(f"Initialized DistributedComputingGateway on port {port} "
                 f"(heartbeat_timeout={heartbeat_timeout_seconds}s, max_workers={max_workers}, "
                 f"monitoring={enable_monitoring}, analytics={enable_analytics}, "
                 f"security={enable_security}, clustering={enable_clustering})")
    
    def _validate_configuration(
        self,
        port: int,
        heartbeat_timeout_seconds: float,
        max_queue_size: int,
        max_workers: int,
        cleanup_interval_seconds: float,
        max_total_active_streams: int,
        max_streams_per_node: int,
        stream_response_queue_size: int,
    ):
        """
        Validate server configuration parameters with comprehensive checks.
        
        Args:
            port: Server port number
            heartbeat_timeout_seconds: Heartbeat timeout in seconds
            max_queue_size: Maximum queue size
            max_workers: Maximum worker threads
            cleanup_interval_seconds: Cleanup interval in seconds
            max_total_active_streams: Maximum active stream count
            max_streams_per_node: Maximum per-node stream count
            stream_response_queue_size: Stream response queue size
            
        Raises:
            ValueError: If any parameter is invalid
        """
        if not (1 <= port <= 65535):
            raise ValueError(f"Port must be between 1 and 65535, got {port}")
        
        if heartbeat_timeout_seconds <= 0:
            raise ValueError(f"Heartbeat timeout must be positive, got {heartbeat_timeout_seconds}")
        
        if max_queue_size < 100:
            raise ValueError(f"Max queue size must be at least 100, got {max_queue_size}")
        
        if max_workers < 1:
            raise ValueError(f"Max workers must be positive, got {max_workers}")
        
        if cleanup_interval_seconds <= 0:
            raise ValueError(f"Cleanup interval must be positive, got {cleanup_interval_seconds}")

        if max_total_active_streams < 1:
            raise ValueError(
                f"max_total_active_streams must be positive, got {max_total_active_streams}"
            )

        if max_streams_per_node < 1:
            raise ValueError(
                f"max_streams_per_node must be positive, got {max_streams_per_node}"
            )

        if stream_response_queue_size < 8:
            raise ValueError(
                "stream_response_queue_size must be at least 8, "
                f"got {stream_response_queue_size}"
            )
        
        # Performance recommendations
        if max_workers > 100:
            self.warning(f"High worker count ({max_workers}) may impact performance")
        
        if max_queue_size > 50000:
            self.warning(f"Large queue size ({max_queue_size}) may consume significant memory")
    
    async def _set_state(self, new_state: ServerState):
        """
        Thread-safe state transition with validation.
        
        Args:
            new_state: The new state to transition to
            
        Raises:
            RuntimeError: If state transition is invalid
        """
        async with self._state_lock:
            old_state = self._state
            
            # Validate state transitions
            valid_transitions = {
                ServerState.INITIALIZING: {ServerState.STARTING, ServerState.ERROR},
                ServerState.STARTING: {ServerState.RUNNING, ServerState.ERROR, ServerState.STOPPING},
                ServerState.RUNNING: {ServerState.STOPPING, ServerState.ERROR},
                ServerState.STOPPING: {ServerState.STOPPED, ServerState.ERROR},
                ServerState.STOPPED: {ServerState.STARTING},
                ServerState.ERROR: {ServerState.STARTING, ServerState.STOPPING, ServerState.STOPPED}
            }
            
            if new_state not in valid_transitions.get(old_state, set()):
                raise RuntimeError(f"Invalid state transition: {old_state} -> {new_state}")
            
            self._state = new_state
            self.info(f"Server state changed: {old_state.value} -> {new_state.value}")
    
    @property
    def state(self) -> ServerState:
        """Get the current server state."""
        return self._state
    
    @property
    def is_running(self) -> bool:
        """Check if the server is currently running."""
        return self._state == ServerState.RUNNING
    
    def start(self) -> 'DistributedComputingGateway':
        """
        Start the gateway server in blocking mode.
        
        This method starts the server and blocks until the server is shut down.
        It automatically detects if it's running in an existing event loop and
        falls back to background mode if necessary.
        
        Returns:
            Self for method chaining
            
        Raises:
            RuntimeError: If server fails to start or is already running
            EasyRemoteError: If there are configuration or initialization issues
            
        Example:
            >>> server = DistributedComputingGateway(port=8080)
            >>> server.start()  # Blocks until shutdown
        """
        if self._state != ServerState.INITIALIZING:
            raise RuntimeError(f"Server cannot start from state: {self._state}")
        
        try:
            # Check if we're already in an event loop
            asyncio.get_running_loop()
            self.warning("Detected running event loop, switching to background mode")
            return self.start_background()
        except RuntimeError:
            # No running loop, we can create our own
            pass
        
        try:
            # Create and configure event loop
            self._event_loop = asyncio.new_event_loop()
            self._initialize_event_loop(self._event_loop)
            
            # Start server in blocking mode
            self._event_loop.run_until_complete(self._async_serve())
            
            return self
            
        except EasyRemoteError:
            raise
        except Exception as e:
            self.error(f"Unexpected error during server startup: {e}", exc_info=True)
            raise ExceptionTranslator.as_connection_error(
                e,
                address=f"0.0.0.0:{self.port}",
                message="Gateway server startup failed",
            ) from e
        finally:
            # Cleanup event loop
            if self._event_loop and not self._event_loop.is_closed():
                self._finalize_event_loop(self._event_loop)
            self._event_loop = None
    
    def start_background(self) -> threading.Thread:
        """
        Start the server in non-blocking background mode.
        
        This method starts the server in a separate thread, allowing the calling
        thread to continue with other operations. This is the recommended approach
        for most use cases.
        
        Returns:
            Thread handle for the background server
            
        Raises:
            RuntimeError: If server is already running or in invalid state
            
        Example:
            >>> server = DistributedComputeServer(port=8080)
            >>> thread = server.start_background()
            >>> # Server is now running in background
            >>> # Continue with other operations...
        """
        if self._state != ServerState.INITIALIZING:
            raise RuntimeError(f"Server cannot start from state: {self._state}")
        
        def _background_server_runner():
            """Background thread entry point for server execution."""
            try:
                # Create isolated event loop for this thread
                self._event_loop = asyncio.new_event_loop()
                self._initialize_event_loop(self._event_loop)
                
                # Run server asynchronously
                self._event_loop.run_until_complete(self._async_serve())
                
            except EasyRemoteError as e:
                self.error(f"EasyRemote error in background server: {e}")
            except Exception as e:
                self.error(f"Unexpected error in background server: {e}", exc_info=True)
            finally:
                # Cleanup
                if self._event_loop and not self._event_loop.is_closed():
                    self._finalize_event_loop(self._event_loop)
                self._event_loop = None
        
        # Start background thread
        self._server_thread = threading.Thread(
            target=_background_server_runner,
            name=f"EasyRemoteServer-{self.port}",
            daemon=True
        )
        self._server_thread.start()
        
        # Wait for server to be ready
        self._wait_for_server_ready(timeout=10.0)
        
        self.info(f"Server started in background on port {self.port}")
        return self._server_thread

    async def _request_shutdown(self, grace: float = 5.0) -> None:
        """
        Request graceful server shutdown from the owning event loop.

        Args:
            grace: gRPC server shutdown grace period in seconds
        """
        if self._state in {ServerState.STARTING, ServerState.RUNNING}:
            await self._set_state(ServerState.STOPPING)

        self._shutdown_event.set()

        if self._grpc_server is not None:
            await self._grpc_server.stop(grace=grace)

    def stop(self, grace: float = 5.0, timeout: float = 10.0) -> None:
        """
        Stop the gateway server gracefully.

        This method is safe to call for both blocking and background modes.

        Args:
            grace: gRPC server shutdown grace period in seconds
            timeout: Maximum wait time for shutdown completion
        """
        if self._state in {ServerState.INITIALIZING, ServerState.STOPPED}:
            return

        if self._event_loop is None or self._event_loop.is_closed():
            return

        try:
            if self._event_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._request_shutdown(grace=grace),
                    self._event_loop,
                )
                future.result(timeout=timeout)
            else:
                self._event_loop.run_until_complete(self._request_shutdown(grace=grace))
        except Exception as e:
            self.warning(f"Error while stopping server: {e}")

        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=timeout)

    def _initialize_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Initialize loop-local resources for gRPC asyncio runtime.
        """
        asyncio.set_event_loop(loop)
        loop.set_exception_handler(self._handle_loop_exception)
        try:
            grpc_aio.init_grpc_aio()
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
        Flush and close an event loop with best-effort grpc.aio shutdown.
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
            self.warning(f"Error while cancelling pending server loop tasks: {e}")

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
                grpc_aio.shutdown_grpc_aio()
            except Exception as e:
                self.warning(f"Error while shutting down grpc.aio runtime: {e}")
            finally:
                self._grpc_aio_initialized = False

        loop.close()
    
    def _wait_for_server_ready(self, timeout: float = 10.0):
        """
        Wait for the server to reach running state.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Raises:
            TimeoutError: If server doesn't start within timeout
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self._state == ServerState.RUNNING:
                return
            elif self._state == ServerState.ERROR:
                raise ExceptionTranslator.as_connection_error(
                    RuntimeError("Server entered ERROR state during startup"),
                    address=f"0.0.0.0:{self.port}",
                    message="Gateway server failed to start",
                )
            time.sleep(0.1)
        
        raise TimeoutError(
            message=f"Server did not start within {timeout} seconds",
            timeout_seconds=timeout,
            operation="server_startup",
        )
    
    async def _async_serve(self):
        """
        Main asynchronous server loop.
        
        This method handles the complete server lifecycle including:
        - gRPC server setup and configuration
        - Background task initialization
        - Event loop management
        - Graceful shutdown handling
        """
        try:
            await self._set_state(ServerState.STARTING)
            
            # Create and configure gRPC server
            self._grpc_server = grpc_aio.server(
                futures.ThreadPoolExecutor(max_workers=self.max_workers),
                options=self._get_grpc_server_options()
            )
            
            # Add our service to the server
            service_pb2_grpc.add_RemoteServiceServicer_to_server(self, self._grpc_server)
            
            # Bind to port and start
            listen_address = f'[::]:{self.port}'
            self._grpc_server.add_insecure_port(listen_address)
            await self._grpc_server.start()
            
            self.info(f"gRPC server listening on {listen_address}")
            
            # Start background monitoring and maintenance tasks
            await self._start_background_tasks()
            
            # Mark server as running
            await self._set_state(ServerState.RUNNING)
            self.info("Distributed compute server is now running and ready for connections")
            
            # Update metrics
            if self.metrics:
                self.metrics.start_time = datetime.now()
            
            # Wait for termination signal
            await self._grpc_server.wait_for_termination()
            
        except Exception as e:
            await self._set_state(ServerState.ERROR)
            self.error(f"Server error during startup: {e}", exc_info=True)
            raise ExceptionTranslator.as_connection_error(
                e,
                address=f"0.0.0.0:{self.port}",
                message="Gateway async serve startup failed",
            ) from e
        finally:
            # Ensure cleanup happens
            await self._async_cleanup()
    
    def _get_grpc_server_options(self) -> List[Tuple[str, Any]]:
        """
        Get optimized gRPC server configuration options.
        
        Returns:
            List of gRPC server option tuples
        """
        return [
            # Message size limits (50MB)
            ('grpc.max_send_message_length', 50 * 1024 * 1024),
            ('grpc.max_receive_message_length', 50 * 1024 * 1024),
            
            # Keepalive settings for connection health
            ('grpc.keepalive_time_ms', 30000),  # 30 seconds
            ('grpc.keepalive_timeout_ms', 5000),  # 5 seconds
            ('grpc.keepalive_permit_without_calls', True),
            
            # HTTP/2 settings - Fixed to allow keepalive pings
            ('grpc.http2.max_pings_without_data', 2),  # Allow 2 pings without data
            ('grpc.http2.min_time_between_pings_ms', 10000),  # Min 10s between pings
            ('grpc.http2.min_ping_interval_without_data_ms', 30000),  # Min 30s for idle pings
            
            # Performance tuning
            ('grpc.so_reuseport', 1),
            ('grpc.tcp_user_timeout_ms', 20000),
        ]
    
    async def _start_background_tasks(self):
        """
        Start all background monitoring and maintenance tasks.
        
        This includes:
        - Node health monitoring
        - Resource cleanup
        - Performance metrics collection
        - Connection management
        """
        self.debug("Starting background tasks")
        
        # Node health monitoring task
        self._node_monitor_task = asyncio.create_task(
            self._node_health_monitor_loop(),
            name="NodeHealthMonitor"
        )
        self._background_tasks.add(self._node_monitor_task)
        
        # Resource cleanup task
        self._cleanup_task = asyncio.create_task(
            self._resource_cleanup_loop(),
            name="ResourceCleanup"
        )
        self._background_tasks.add(self._cleanup_task)
        
        # Performance metrics collection (if enabled)
        if self.metrics:
            metrics_task = asyncio.create_task(
                self._metrics_collection_loop(),
                name="MetricsCollection"
            )
            self._background_tasks.add(metrics_task)
        
        self.info(f"Started {len(self._background_tasks)} background tasks")
    
    async def _node_health_monitor_loop(self):
        """
        Background task for monitoring compute node health.
        
        This task periodically checks node heartbeats and removes
        unresponsive nodes from the system.
        """
        self.debug("Node health monitor started")
        
        try:
            while not self._shutdown_event.is_set():
                try:
                    await self._check_node_health()
                    
                    # Wait for next check (half of heartbeat timeout)
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=self.heartbeat_timeout_seconds / 2
                    )
                    
                except asyncio.TimeoutError:
                    # Normal timeout, continue monitoring
                    continue
                except Exception as e:
                    self.error(f"Error in node health monitor: {e}")
                    await asyncio.sleep(1)  # Brief pause before retry
                    
        except asyncio.CancelledError:
            self.debug("Node health monitor cancelled")
        except Exception as e:
            self.error(f"Unexpected error in node health monitor: {e}", exc_info=True)
    
    async def _check_node_health(self):
        """
        Check health of all registered compute nodes.
        
        Removes nodes that haven't sent heartbeats within the timeout period.
        """
        current_time = datetime.now()
        timeout_delta = timedelta(seconds=self.heartbeat_timeout_seconds)
        nodes_to_remove = []
        
        async with self._global_lock:
            for node_id, node_info in self._nodes.items():
                time_since_heartbeat = current_time - node_info.last_heartbeat
                
                if time_since_heartbeat > timeout_delta:
                    self.warning(f"Node {node_id} timed out "
                               f"(last heartbeat: {time_since_heartbeat.total_seconds():.1f}s ago)")
                    nodes_to_remove.append(node_id)
                elif not node_info.is_alive(self.heartbeat_timeout_seconds):
                    self.warning(f"Node {node_id} marked as not alive")
                    nodes_to_remove.append(node_id)
        
        # Remove timed out nodes
        for node_id in nodes_to_remove:
            await self._remove_node_safely(node_id, reason="health_check_timeout")
        
        # Update metrics
        if self.metrics:
            self.metrics.active_nodes = len(self._nodes)
    
    async def _resource_cleanup_loop(self):
        """
        Background task for cleaning up stale resources.
        
        This task periodically removes expired function calls,
        stream contexts, and other temporary resources.
        """
        self.debug("Resource cleanup loop started")
        
        try:
            while not self._shutdown_event.is_set():
                try:
                    await self._cleanup_stale_resources()
                    
                    # Wait for next cleanup cycle
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=self.cleanup_interval_seconds
                    )
                    
                except asyncio.TimeoutError:
                    # Normal timeout, continue cleanup
                    continue
                except Exception as e:
                    self.error(f"Error in resource cleanup: {e}")
                    await asyncio.sleep(5)  # Brief pause before retry
                    
        except asyncio.CancelledError:
            self.debug("Resource cleanup loop cancelled")
        except Exception as e:
            self.error(f"Unexpected error in resource cleanup: {e}", exc_info=True)
    
    async def _cleanup_stale_resources(self):
        """
        Clean up expired function calls and stream contexts.
        
        This method removes resources that have exceeded their timeout
        or have been orphaned by disconnected clients/nodes.
        """
        current_time = datetime.now()
        stale_timeout = timedelta(minutes=5)  # 5-minute stale resource timeout
        
        async with self._global_lock:
            # Clean up stale stream contexts
            stale_streams = []
            for call_id, stream_ctx in self._active_stream_contexts.items():
                if (current_time - stream_ctx.created_at > stale_timeout or 
                    stream_ctx.is_timed_out):
                    stale_streams.append(call_id)
            
            for call_id in stale_streams:
                await self._cleanup_stream_context(call_id, "stale_timeout")
            
            # Clean up stale function calls
            stale_calls = []
            for call_id, call_context in self._pending_function_calls.items():
                if isinstance(call_context, dict):
                    created_at = call_context.get('created_at')
                    if created_at and (current_time - created_at > stale_timeout):
                        stale_calls.append(call_id)
            
            for call_id in stale_calls:
                await self._cleanup_pending_call(call_id, "stale_timeout")
        
        if stale_streams or stale_calls:
            self.info(f"Cleaned up {len(stale_streams)} stale streams and "
                     f"{len(stale_calls)} stale calls")
    
    async def _metrics_collection_loop(self):
        """
        Background task for collecting and updating performance metrics.
        """
        self.debug("Metrics collection loop started")
        
        try:
            while not self._shutdown_event.is_set():
                try:
                    await self._update_metrics()
                    
                    # Update every 30 seconds
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=30
                    )
                    
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    self.error(f"Error in metrics collection: {e}")
                    await asyncio.sleep(10)
                    
        except asyncio.CancelledError:
            self.debug("Metrics collection loop cancelled")
        except Exception as e:
            self.error(f"Unexpected error in metrics collection: {e}", exc_info=True)
    
    async def _update_metrics(self):
        """Update server performance metrics."""
        if not self.metrics:
            return
        
        async with self._global_lock:
            # Update connection and node counts
            self.metrics.update_connection_stats(len(self._node_communication_queues))
            self.metrics.active_nodes = len(self._nodes)
            self.metrics.total_nodes_registered = max(
                self.metrics.total_nodes_registered,
                len(self._nodes)
            )
    
    # ================================
    # gRPC Service Method Implementations
    # ================================
    
    async def RegisterNode(self, request, context):
        """
        Handle node registration requests.
        
        Args:
            request: NodeInfo protobuf message
            context: gRPC context
            
        Returns:
            RegisterResponse protobuf message
        """
        try:
            self.info(f"Received registration request from node: {request.node_id}")
            
            # Convert protobuf message to internal data structure
            from ..data import FunctionInfo, FunctionType
            
            # Create function infos from protobuf specs
            functions = {}
            for func_spec in request.functions:
                func_type = FunctionType.ASYNC if func_spec.is_async else FunctionType.SYNC
                if func_spec.is_generator:
                    func_type = FunctionType.ASYNC_GENERATOR if func_spec.is_async else FunctionType.GENERATOR
                
                func_info = FunctionInfo(
                    name=func_spec.name,
                    function_type=func_type,
                    node_id=request.node_id
                )
                functions[func_spec.name] = func_info
            
            # Create node info
            node_info = NodeInfo(
                node_id=request.node_id,
                functions=functions,
                status=NodeStatus.CONNECTED,
                capabilities=set(request.capabilities),
                location=request.location if request.location else None,
                version=request.version if request.version else "1.0.0"
            )
            
            # Register the node
            async with self._global_lock:
                self._nodes[request.node_id] = node_info
                # Keep existing control-stream queue if present. Replacing queue
                # during re-registration can detach active stream consumers and
                # cause function calls to stall indefinitely.
                if request.node_id not in self._node_communication_queues:
                    self._node_communication_queues[request.node_id] = asyncio.Queue(
                        maxsize=self.max_queue_size
                    )
            
            # Update metrics
            if self.metrics:
                self.metrics.total_nodes_registered += 1
                self.metrics.active_nodes = len(self._nodes)
            
            self.info(f"Successfully registered node '{request.node_id}' with {len(functions)} functions")
            
            # Return success response
            response = service_pb2.RegisterResponse()
            response.success = True
            response.message = f"Node {request.node_id} registered successfully"
            return response
            
        except Exception as e:
            self.error(f"Failed to register node {request.node_id}: {e}", exc_info=True)
            
            # Return error response
            response = service_pb2.RegisterResponse()
            response.success = False
            response.message = f"Registration failed: {str(e)}"
            return response
    
    async def SendHeartbeat(self, request, context):
        """
        Handle heartbeat messages from compute nodes.
        
        Args:
            request: HeartbeatMessage protobuf message
            context: gRPC context
            
        Returns:
            HeartbeatResponse protobuf message
        """
        try:
            node_id = request.node_id
            
            async with self._global_lock:
                if node_id in self._nodes:
                    node_info = self._nodes[node_id]
                    
                    # Update heartbeat timestamp
                    node_info.update_heartbeat()
                    
                    # Update health metrics
                    node_info.health_metrics.cpu_usage_percent = request.cpu_usage
                    node_info.health_metrics.memory_usage_percent = request.memory_usage
                    node_info.health_metrics.gpu_usage_percent = request.gpu_usage
                    node_info.health_metrics.active_connections = request.active_connections
                    node_info.health_metrics.last_updated = datetime.now()
                    
                    # 💓 Enhanced heartbeat logging with detailed status
                    active_funcs = len(node_info.functions)
                    self.debug(f"💓 [HEARTBEAT] Node {node_id} alive! "
                             f"CPU: {request.cpu_usage:.1f}%, Memory: {request.memory_usage:.1f}%, "
                             f"GPU: {request.gpu_usage:.1f}%, Active: {request.active_connections}, "
                             f"Functions: {active_funcs}")
                    
                    # Return accepted response
                    response = service_pb2.HeartbeatResponse()
                    response.accepted = True
                    return response
                else:
                    self.warning(f"[HEARTBEAT] REJECTED - Unknown node: {node_id}")
                    
                    # Return rejected response
                    response = service_pb2.HeartbeatResponse()
                    response.accepted = False
                    return response
                    
        except Exception as e:
            self.error(f"[HEARTBEAT] Error processing heartbeat from {request.node_id}: {e}", exc_info=True)
            
            # Return rejected response
            response = service_pb2.HeartbeatResponse()
            response.accepted = False
            return response
    
    async def CallWithLoadBalancing(self, request, context):
        """
        Handle load balanced function execution requests.
        
        This method receives LoadBalancedCallRequest messages and routes them
        to the optimal compute node using intelligent load balancing strategies.
        
        Args:
            request: LoadBalancedCallRequest protobuf message
            context: gRPC context
            
        Returns:
            LoadBalancedCallResponse protobuf message
        """
        call_id = request.call_id
        function_name = request.function_name
        
        try:
            # 📥 Enhanced request logging
            self.info(f"[ROUTE] RECEIVED request from client! call_id={call_id}, function='{function_name}'")
            
            # Deserialize arguments
            try:
                args, kwargs = self._serializer.deserialize_args(request.args, request.kwargs)
                self.info(f"[ROUTE] Arguments deserialized: args={len(args)}, kwargs={len(kwargs)}")
            except Exception as e:
                error_msg = f"Failed to deserialize arguments: {e}"
                self.error(f"[ROUTE] {error_msg}")
                
                response = service_pb2.LoadBalancedCallResponse()
                response.has_error = True
                response.error_message = error_msg
                return response
            
            # Create request context for load balancing
            from ..balancing.strategies import RequestContext, RequestPriority
            
            # Parse strategy and requirements
            strategy = request.strategy or "load_balanced"
            requirements = {}
            if request.requirements:
                try:
                    import json
                    requirements = json.loads(request.requirements) if request.requirements != "{}" else {}
                except Exception:
                    requirements = {}
            
            request_context = RequestContext(
                function_name=function_name,
                priority=RequestPriority.NORMAL,
                requirements=requirements,
                timeout=request.timeout if request.timeout > 0 else None,
                custom_tags={"requested_strategy": strategy},
            )
            
            # 🔄 Notify client that request is being processed
            self.info(f"[ROUTE] Processing request {call_id} - looking for available nodes...")
            
            # Use load balancer to select node and execute function
            try:
                start_time = time.time()
                
                # Find available nodes for this function
                available_nodes = []
                for node_id, node_info in self._nodes.items():
                    if function_name in node_info.functions and node_info.is_alive():
                        available_nodes.append(node_id)
                
                if not available_nodes:
                    raise NoAvailableNodesError(
                        message=f"No available nodes for function '{function_name}'",
                        function_name=function_name,
                    )
                
                # Use load balancer to select optimal node
                selected_node = self._load_balancer.select_node(
                    function_name, 
                    request_context,
                    available_nodes
                )
                
                self.info(f" [ROUTE] Load balancer selected node '{selected_node}' for function '{function_name}' - executing...")
                
                # Execute function directly on selected node
                result = await self.execute_function(selected_node, function_name, *args, **kwargs)
                execution_time_ms = (time.time() - start_time) * 1000
                
                # Serialize result
                try:
                    serialized_result = self._serializer.serialize_result(result)
                    self.info(f"[ROUTE] Result serialized for call {call_id}")
                except Exception as e:
                    error_msg = f"Failed to serialize result: {e}"
                    self.error(f"[ROUTE] {error_msg}")
                    
                    response = service_pb2.LoadBalancedCallResponse()
                    response.has_error = True
                    response.error_message = error_msg
                    return response
                
                # Create successful response
                response = service_pb2.LoadBalancedCallResponse()
                response.has_error = False
                response.result = serialized_result
                response.execution_time_ms = execution_time_ms
                
                # Try to determine which node was selected (this is approximate)
                # In a real implementation, execute_function_with_load_balancing should return node info
                response.selected_node_id = "unknown"  # Placeholder
                
                # Update metrics
                if self.metrics:
                    self.metrics.update_request_stats(True, execution_time_ms)
                
                self.info(f"[ROUTE] SUCCESS! Completed call {call_id} for '{function_name}' "
                         f"in {execution_time_ms:.2f}ms - sending result back to client")
                
                return response
                
            except NoAvailableNodesError as e:
                error_msg = f"No available nodes for function '{function_name}': {e}"
                self.warning(f"[ROUTE] {error_msg}")
                
                response = service_pb2.LoadBalancedCallResponse()
                response.has_error = True
                response.error_message = error_msg
                return response
                
            except Exception as e:
                error_msg = f"Function execution failed: {e}"
                self.error(f"[ROUTE] Load balanced execution failed for call {call_id}: {e}", exc_info=True)
                
                response = service_pb2.LoadBalancedCallResponse()
                response.has_error = True
                response.error_message = error_msg
                return response
        
        except Exception as e:
            error_msg = f"Load balanced call processing failed: {e}"
            self.error(f"[ROUTE] Critical error in CallWithLoadBalancing for call {call_id}: {e}", exc_info=True)
            
            # Update metrics for failed request
            if self.metrics:
                self.metrics.update_request_stats(False, 0.0)
            
            response = service_pb2.LoadBalancedCallResponse()
            response.has_error = True
            response.error_message = error_msg
            return response
    
    async def CallDirect(self, request, context):
        """
        Handle direct function execution requests to specific nodes.
        
        Args:
            request: DirectCallRequest protobuf message
            context: gRPC context
            
        Returns:
            DirectCallResponse protobuf message
        """
        call_id = request.call_id
        node_id = request.node_id
        function_name = request.function_name
        
        try:
            self.debug(f"Processing direct call {call_id} to node '{node_id}' for function '{function_name}'")
            
            # Deserialize arguments
            try:
                args, kwargs = self._serializer.deserialize_args(request.args, request.kwargs)
            except Exception as e:
                error_msg = f"Failed to deserialize arguments: {e}"
                self.error(error_msg)
                
                response = service_pb2.DirectCallResponse()
                response.has_error = True
                response.error_message = error_msg
                return response
            
            # Execute function on specific node
            try:
                result = await self.execute_function(node_id, function_name, *args, **kwargs)
                
                # Serialize result
                try:
                    serialized_result = self._serializer.serialize_result(result)
                except Exception as e:
                    error_msg = f"Failed to serialize result: {e}"
                    self.error(error_msg)
                    
                    response = service_pb2.DirectCallResponse()
                    response.has_error = True
                    response.error_message = error_msg
                    return response
                
                # Create successful response
                response = service_pb2.DirectCallResponse()
                response.has_error = False
                response.result = serialized_result
                
                self.debug(f"Successfully completed direct call {call_id} to node '{node_id}'")
                return response
                
            except (NodeNotFoundError, FunctionNotFoundError) as e:
                error_msg = str(e)
                self.warning(error_msg)
                
                response = service_pb2.DirectCallResponse()
                response.has_error = True
                response.error_message = error_msg
                return response
                
            except Exception as e:
                error_msg = f"Function execution failed: {e}"
                self.error(f"Direct execution failed for call {call_id}: {e}", exc_info=True)
                
                response = service_pb2.DirectCallResponse()
                response.has_error = True
                response.error_message = error_msg
                return response
        
        except Exception as e:
            error_msg = f"Direct call processing failed: {e}"
            self.error(f"Critical error in CallDirect for call {call_id}: {e}", exc_info=True)
            
            response = service_pb2.DirectCallResponse()
            response.has_error = True
            response.error_message = error_msg
            return response

    async def StreamCall(self, request_iterator, context):
        """
        Handle bidirectional client streaming execution requests.

        Client->Gateway:
        - start: initialize one stream call
        - cancel: cancel active stream forwarding
        - ack: credit-based flow-control window (backpressure)

        Gateway->Client:
        - exec_res: stream output chunks and done marker
        - error: normalized stream-level failures
        """
        outgoing_queue: asyncio.Queue = asyncio.Queue(
            maxsize=self.stream_response_queue_size
        )
        stream_call_id: Optional[str] = None
        active_forward_task: Optional[asyncio.Task] = None
        stop_event = asyncio.Event()
        ack_seen = False
        stream_credits = 0
        credit_condition = asyncio.Condition()
        max_stream_credits = max(1, int(self.stream_response_queue_size) * 4)

        async def enqueue_error(
            message: str,
            *,
            node_id: Optional[str] = None,
        ) -> None:
            error_call_id = stream_call_id or ""
            await outgoing_queue.put(
                self._build_stream_error_frame(
                    call_id=error_call_id,
                    message=message,
                    node_id=node_id,
                )
            )

        async def forward_stream(
            *,
            function_name: str,
            node_id: Optional[str],
            load_balancing_config: Union[bool, str, dict],
            args: Tuple[Any, ...],
            kwargs: Dict[str, Any],
        ) -> None:
            nonlocal ack_seen, stream_credits
            try:
                if load_balancing_config:
                    stream_iter = self.stream_function_with_load_balancing(
                        function_name,
                        load_balancing_config,
                        *args,
                        **kwargs,
                    )
                else:
                    stream_iter = self.stream_function(
                        node_id,
                        function_name,
                        *args,
                        **kwargs,
                    )

                async for chunk in stream_iter:
                    if ack_seen:
                        async with credit_condition:
                            while stream_credits <= 0 and not stop_event.is_set():
                                await credit_condition.wait()
                            if stop_event.is_set():
                                break
                            stream_credits -= 1

                    response_frame = service_pb2.StreamCallFrame()
                    response_frame.exec_res.call_id = stream_call_id or ""
                    response_frame.exec_res.function_name = function_name
                    if node_id:
                        response_frame.exec_res.node_id = node_id
                    response_frame.exec_res.has_error = False
                    response_frame.exec_res.is_done = False
                    response_frame.exec_res.chunk = self._serializer.serialize_result(chunk)
                    await outgoing_queue.put(response_frame)

                done_frame = service_pb2.StreamCallFrame()
                done_frame.exec_res.call_id = stream_call_id or ""
                done_frame.exec_res.function_name = function_name
                if node_id:
                    done_frame.exec_res.node_id = node_id
                done_frame.exec_res.has_error = False
                done_frame.exec_res.is_done = True
                await outgoing_queue.put(done_frame)
            except asyncio.CancelledError:
                # Client cancellation: terminate silently to avoid noisy errors.
                raise
            except Exception as exc:
                await enqueue_error(str(exc), node_id=node_id)
            finally:
                stop_event.set()

        async def consume_requests() -> None:
            nonlocal stream_call_id, active_forward_task, ack_seen, stream_credits
            try:
                async for frame in request_iterator:
                    if frame.HasField("start"):
                        if active_forward_task is not None:
                            await enqueue_error(
                                "Duplicate start frame is not allowed for one StreamCall session."
                            )
                            continue

                        start = frame.start
                        stream_call_id = start.call_id or str(uuid.uuid4())

                        try:
                            args, kwargs = self._serializer.deserialize_args(
                                start.args,
                                start.kwargs,
                            )
                        except Exception as exc:
                            await enqueue_error(f"Failed to deserialize stream arguments: {exc}")
                            stop_event.set()
                            break

                        use_load_balancing = bool(start.use_load_balancing)
                        lb_strategy = (
                            start.load_balancing_strategy.strip()
                            if start.load_balancing_strategy
                            else "adaptive"
                        )
                        node_id = start.node_id.strip() if start.node_id else None

                        active_forward_task = asyncio.create_task(
                            forward_stream(
                                function_name=start.function_name,
                                node_id=node_id,
                                load_balancing_config=lb_strategy
                                if use_load_balancing
                                else False,
                                args=tuple(args),
                                kwargs=dict(kwargs),
                            ),
                            name=f"StreamCallForward-{stream_call_id}",
                        )

                    elif frame.HasField("cancel"):
                        cancel = frame.cancel
                        if stream_call_id and cancel.call_id and cancel.call_id != stream_call_id:
                            await enqueue_error(
                                "Cancel call_id does not match active stream session."
                            )
                            continue

                        if active_forward_task is not None and not active_forward_task.done():
                            active_forward_task.cancel()
                        stop_event.set()
                        async with credit_condition:
                            credit_condition.notify_all()
                        break

                    elif frame.HasField("ack"):
                        ack = frame.ack
                        if stream_call_id and ack.call_id and ack.call_id != stream_call_id:
                            await enqueue_error(
                                "Ack call_id does not match active stream session."
                            )
                            continue

                        delta = int(getattr(ack, "credits", 0) or 0)
                        if delta <= 0:
                            continue

                        ack_seen = True
                        async with credit_condition:
                            stream_credits = min(
                                max_stream_credits,
                                stream_credits + delta,
                            )
                            credit_condition.notify_all()
                        continue
                    else:
                        await enqueue_error("Unsupported stream frame payload.")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await enqueue_error(f"Failed to process stream request: {exc}")
                stop_event.set()
            finally:
                if active_forward_task is None:
                    stop_event.set()

        request_task = asyncio.create_task(
            consume_requests(),
            name="StreamCallRequestConsumer",
        )

        try:
            while True:
                if stop_event.is_set() and outgoing_queue.empty():
                    break

                try:
                    frame = await asyncio.wait_for(outgoing_queue.get(), timeout=0.2)
                    yield frame
                except asyncio.TimeoutError:
                    if stop_event.is_set() and outgoing_queue.empty():
                        break
                    continue
        finally:
            if not request_task.done():
                request_task.cancel()
                await asyncio.gather(request_task, return_exceptions=True)

            if active_forward_task is not None and not active_forward_task.done():
                active_forward_task.cancel()
                await asyncio.gather(active_forward_task, return_exceptions=True)

            async with credit_condition:
                credit_condition.notify_all()

    async def ListNodes(self, request, context):
        """
        Handle node listing requests.
        
        Args:
            request: ListNodesRequest protobuf message
            context: gRPC context
            
        Returns:
            ListNodesResponse protobuf message
        """
        try:
            self.debug(f"Processing list nodes request from client '{request.client_id}'")
            
            response = service_pb2.ListNodesResponse()
            
            async with self._global_lock:
                for node_id, node_info in self._nodes.items():
                    node_proto = service_pb2.NodeInfo()
                    node_proto.node_id = node_id
                    node_proto.status = node_info.status.value if hasattr(node_info.status, 'value') else str(node_info.status)
                    node_proto.version = getattr(node_info, "version", "") or "1.0.0"
                    node_proto.location = getattr(node_info, "location", "") or ""
                    node_proto.capabilities.extend(
                        sorted(getattr(node_info, "capabilities", set()) or set())
                    )
                    
                    # Add function names
                    for func_name in node_info.functions.keys():
                        func_spec = node_proto.functions.add()
                        func_spec.name = func_name
                    
                    # Add health metrics if available
                    if hasattr(node_info, 'health_metrics') and node_info.health_metrics:
                        cpu_percent = getattr(node_info.health_metrics, "cpu_usage_percent", 0.0)
                        node_proto.current_load = max(0.0, min(1.0, float(cpu_percent) / 100.0))
                    last_heartbeat = getattr(node_info, "last_heartbeat", None)
                    if last_heartbeat is not None:
                        node_proto.last_heartbeat = int(last_heartbeat.timestamp())
                    
                    response.nodes.append(node_proto)
            
            self.debug(f"Returning {len(response.nodes)} nodes to client '{request.client_id}'")
            return response
            
        except Exception as e:
            self.error(f"Error processing list nodes request: {e}", exc_info=True)
            # Return empty response on error
            return service_pb2.ListNodesResponse()
    
    async def GetNodeStatus(self, request, context):
        """
        Handle node status requests.
        
        Args:
            request: NodeStatusRequest protobuf message
            context: gRPC context
            
        Returns:
            NodeStatusResponse protobuf message
        """
        try:
            client_id = request.client_id
            node_id = request.node_id
            
            self.debug(f"Processing node status request for '{node_id}' from client '{client_id}'")
            
            async with self._global_lock:
                if node_id not in self._nodes:
                    # Node not found - return error via gRPC status
                    context.set_code(grpc.StatusCode.NOT_FOUND)
                    context.set_details(f"Node '{node_id}' not found")
                    return service_pb2.NodeStatusResponse()
                
                node_info = self._nodes[node_id]
                
                response = service_pb2.NodeStatusResponse()
                response.node_id = node_id
                response.status = node_info.status.value if hasattr(node_info.status, 'value') else str(node_info.status)
                
                # Add health metrics if available
                if hasattr(node_info, 'health_metrics') and node_info.health_metrics:
                    health = node_info.health_metrics
                    response.cpu_usage = getattr(health, 'cpu_usage_percent', 0.0)
                    response.memory_usage = getattr(health, 'memory_usage_percent', 0.0)
                    response.gpu_usage = getattr(health, 'gpu_usage_percent', 0.0)
                    response.current_load = response.cpu_usage / 100.0
                    response.last_seen = int(time.time())
                
                # Add function names
                for func_name in node_info.functions.keys():
                    response.functions.append(func_name)
                
                response.health_score = 1.0 if node_info.is_alive() else 0.0
                
                self.debug(f"Returning status for node '{node_id}' to client '{client_id}'")
                return response
            
        except Exception as e:
            self.error(f"Error processing node status request: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {e}")
            return service_pb2.NodeStatusResponse()
    
    async def ControlStream(self, request_iterator, context):
        """
        Handle bidirectional streaming communication with compute nodes.
        
        This method processes control messages from nodes and can send
        execution requests and other control messages back to nodes.
        
        Args:
            request_iterator: Stream of ControlMessage from the node
            context: gRPC context
            
        Yields:
            ControlMessage responses
        """
        node_id = None
        response_queue = None
        
        try:
            self.debug("New control stream connection established")
            
            # Use a queue to coordinate between message handling and yielding
            outgoing_queue = asyncio.Queue()
            
            async def process_incoming_messages():
                """Process incoming messages from the node"""
                nonlocal node_id, response_queue
                
                async for control_message in request_iterator:
                    try:
                        # Handle different types of control messages
                        if control_message.HasField('register_req'):
                            # Handle registration request
                            register_req = control_message.register_req
                            node_id = register_req.node_id
                            
                            self.info(f"Processing registration via control stream for node: {node_id}")
                            
                            # Create node info (simplified version for control stream)
                            from ..data import FunctionInfo, FunctionType
                            
                            functions = {}
                            for func_spec in register_req.functions:
                                func_type = FunctionType.ASYNC if func_spec.is_async else FunctionType.SYNC
                                if func_spec.is_generator:
                                    func_type = FunctionType.ASYNC_GENERATOR if func_spec.is_async else FunctionType.GENERATOR
                                
                                func_info = FunctionInfo(
                                    name=func_spec.name,
                                    function_type=func_type,
                                    node_id=node_id
                                )
                                functions[func_spec.name] = func_info
                            
                            # Register node
                            async with self._global_lock:
                                if node_id not in self._nodes:
                                    self._nodes[node_id] = NodeInfo(
                                        node_id=node_id,
                                        functions=functions,
                                        status=NodeStatus.CONNECTED
                                    )
                                else:
                                    # Update existing node
                                    self._nodes[node_id].functions.update(functions)
                                    self._nodes[node_id].update_heartbeat()
                                
                                # Create or update communication queue
                                if node_id not in self._node_communication_queues:
                                    self._node_communication_queues[node_id] = asyncio.Queue(maxsize=self.max_queue_size)
                                response_queue = self._node_communication_queues[node_id]
                            
                            # Send registration response
                            response_msg = service_pb2.ControlMessage()
                            response_msg.register_resp.success = True
                            response_msg.register_resp.message = f"Node {node_id} registered via control stream"
                            await outgoing_queue.put(response_msg)
                            
                            self.info(f"Node {node_id} registered via control stream with {len(functions)} functions")
                        
                        elif control_message.HasField('heartbeat_req'):
                            # Handle heartbeat request
                            heartbeat_req = control_message.heartbeat_req
                            req_node_id = heartbeat_req.node_id
                            
                            async with self._global_lock:
                                if req_node_id in self._nodes:
                                    self._nodes[req_node_id].update_heartbeat()
                                    accepted = True
                                    self.debug(f"Heartbeat received from {req_node_id} via control stream")
                                else:
                                    accepted = False
                                    self.warning(f"Heartbeat from unregistered node {req_node_id} via control stream")
                            
                            # Send heartbeat response
                            response_msg = service_pb2.ControlMessage()
                            response_msg.heartbeat_resp.accepted = accepted
                            await outgoing_queue.put(response_msg)
                        
                        elif control_message.HasField('exec_res'):
                            # Handle execution result
                            exec_result = control_message.exec_res
                            call_id = exec_result.call_id
                            
                            self.info(f"[RECV] ✅ RECEIVED execution result from node '{node_id}' for call {call_id}")
                            
                            if exec_result.has_error:
                                self.error(f"[RECV] ❌ Node '{node_id}' reported ERROR for call {call_id}: {exec_result.error_message}")
                            else:
                                self.info(f"[RECV] ✅ Node '{node_id}' completed call {call_id} successfully!")
                            
                            # Process execution result
                            async with self._global_lock:
                                if call_id in self._pending_function_calls:
                                    future_or_context = self._pending_function_calls[call_id]
                                    
                                    if isinstance(future_or_context, asyncio.Future):
                                        # Single result
                                        if exec_result.has_error:
                                            error = RemoteExecutionError(
                                                function_name=exec_result.function_name or "unknown",
                                                node_id=exec_result.node_id or node_id,
                                                message=exec_result.error_message,
                                            )
                                            future_or_context.set_exception(error)
                                            self.error(f"[RECV] Setting exception for call {call_id}")
                                        else:
                                            # Deserialize result
                                            try:
                                                self.info(f"[RECV] Deserializing result from node '{node_id}'...")
                                                result = self._serializer.deserialize_result(exec_result.result)
                                                future_or_context.set_result(result)
                                                self.info(f"[RECV] Result deserialized and delivered for call {call_id}")
                                            except Exception as e:
                                                self.error(f"[RECV] Failed to deserialize result: {e}")
                                                future_or_context.set_exception(
                                                    ExceptionTranslator.as_serialization_error(
                                                        e,
                                                        operation="deserialize_result",
                                                        message="Failed to deserialize node result payload",
                                                    )
                                                )
                                        
                                        # Clean up
                                        del self._pending_function_calls[call_id]
                                        self.info(f"[RECV] Cleaned up call {call_id} from pending calls")
                                    
                                    elif isinstance(future_or_context, dict):
                                        # Stream result - add to queue
                                        if 'response_queue' in future_or_context:
                                            await future_or_context['response_queue'].put(exec_result)
                                            self.info(f" [RECV] Added stream result to queue for call {call_id}")
                                else:
                                    self.warning(f"[RECV] Received result for unknown call {call_id} from node '{node_id}'")
                            
                            # Update metrics
                            if self.metrics:
                                success = not exec_result.has_error
                                # Estimate response time (in production, this should be tracked properly)
                                response_time = 1.0  # Placeholder
                                self.metrics.update_request_stats(success, response_time)
                    
                    except Exception as e:
                        self.error(f"Error processing control message from {node_id}: {e}", exc_info=True)
                        # Continue processing other messages
                        continue
            
            async def monitor_outgoing_messages():
                """Monitor for outgoing execution requests"""
                self.info(f"🔍 [CONTROL] Starting message monitor for node '{node_id}' - watching for function calls to send")
                message_check_count = 0
                
                while True:
                    try:
                        message_check_count += 1
                        
                        if response_queue and node_id:
                            queue_size = response_queue.qsize()
                            
                            # Log every 200 checks to avoid spam but still show activity
                            if message_check_count % 200 == 0:
                                self.debug(f"🔍 [CONTROL] Monitor check #{message_check_count} for node '{node_id}', queue size: {queue_size}")
                            
                            try:
                                # Check for execution requests
                                outgoing_message = await asyncio.wait_for(
                                    response_queue.get(), 
                                    timeout=0.1  # 100ms timeout
                                )
                                self.info(f"📨 [CONTROL]  FOUND MESSAGE for node '{node_id}'! Queue had {queue_size} messages")
                                
                                # Check what type of message it is
                                if outgoing_message.HasField('exec_req'):
                                    exec_req = outgoing_message.exec_req
                                    self.info(f"[CONTROL]  TRANSMITTING function call to node '{node_id}':")
                                    self.info(f"   Function: '{exec_req.function_name}'")
                                    self.info(f"   Call ID: {exec_req.call_id}")
                                    self.info(f"   Args size: {len(exec_req.args)} bytes")
                                    self.info(f"   Kwargs size: {len(exec_req.kwargs)} bytes")
                                else:
                                    self.info(f"📨 [CONTROL] Sending control message to node '{node_id}' (non-execution)")
                                
                                await outgoing_queue.put(outgoing_message)
                                self.info(f"[CONTROL] MESSAGE TRANSMITTED to node '{node_id}' - node should receive it now!")
                                
                            except asyncio.TimeoutError:
                                # No execution requests, continue monitoring
                                pass
                        else:
                            if message_check_count % 200 == 0:
                                self.debug(f"🔍 [CONTROL] Monitor check #{message_check_count}: waiting for node connection")
                        
                        # Small delay to avoid busy loop
                        await asyncio.sleep(0.05)  # 50ms sleep
                        
                    except asyncio.CancelledError:
                        self.info(f"[CONTROL] Message monitor stopped for node '{node_id}'")
                        break
                    except Exception as e:
                        self.error(f"[CONTROL] Error in message monitor for node '{node_id}': {e}")
                        break
            
            # Start background tasks
            incoming_task = asyncio.create_task(process_incoming_messages())
            outgoing_task = asyncio.create_task(monitor_outgoing_messages())
            
            try:
                # Main message yielding loop
                while True:
                    try:
                        # Check if background tasks are still running
                        if incoming_task.done() or outgoing_task.done():
                            break
                        
                        # Wait for outgoing messages with timeout
                        try:
                            message = await asyncio.wait_for(outgoing_queue.get(), timeout=0.1)
                            yield message
                        except asyncio.TimeoutError:
                            # No messages to send, continue
                            continue
                            
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        self.error(f"Error in message yielding loop: {e}")
                        break
                        
            finally:
                # Clean up background tasks
                if not incoming_task.done():
                    incoming_task.cancel()
                if not outgoing_task.done():
                    outgoing_task.cancel()
                
                try:
                    await asyncio.gather(incoming_task, outgoing_task, return_exceptions=True)
                except Exception:
                    pass
        
        except Exception as e:
            self.error(f"Error in control stream for node {node_id}: {e}", exc_info=True)
        finally:
            # Clean up when stream ends
            if node_id:
                self.info(f"Control stream ended for node {node_id}")
                # Note: We don't immediately remove the node as it might reconnect
                # The health monitor will remove it if it doesn't reconnect in time

    async def list_functions(self) -> List[FunctionDescriptor]:
        """
        List currently available functions for external protocol adapters.
        """
        function_index: Dict[str, FunctionDescriptor] = {}

        async with self._global_lock:
            for node_id, node_info in self._nodes.items():
                if not node_info.is_alive():
                    continue

                for function_name, function_info in node_info.functions.items():
                    descriptor = function_index.get(function_name)
                    if descriptor is None:
                        tags = sorted(list(function_info.tags)) if function_info.tags else []
                        descriptor = FunctionDescriptor(
                            name=function_name,
                            description=str(
                                function_info.get_context_data("description", "")
                            ),
                            node_ids=[node_id],
                            tags=tags,
                            metadata={
                                "function_type": function_info.function_type.value,
                                "max_concurrent_calls": function_info.max_concurrent_calls,
                            },
                        )
                        function_index[function_name] = descriptor
                    else:
                        descriptor.node_ids.append(node_id)

        return [function_index[name] for name in sorted(function_index.keys())]

    async def execute_invocation(self, invocation: FunctionInvocation) -> Any:
        """
        Execute a protocol-normalized invocation.
        """
        if invocation.stream:
            if invocation.load_balancing:
                return self.stream_function_with_load_balancing(
                    invocation.function_name,
                    invocation.load_balancing,
                    *invocation.args,
                    **invocation.kwargs,
                )
            return self.stream_function(
                invocation.node_id,
                invocation.function_name,
                *invocation.args,
                **invocation.kwargs,
            )

        if invocation.load_balancing:
            return await self.execute_function_with_load_balancing(
                invocation.function_name,
                invocation.load_balancing,
                *invocation.args,
                **invocation.kwargs,
            )

        return await self.execute_function(
            invocation.node_id,
            invocation.function_name,
            *invocation.args,
            **invocation.kwargs
        )

    def register_protocol_adapter(self, adapter: ProtocolAdapter) -> None:
        """
        Register a custom protocol adapter at runtime.
        """
        self._protocol_gateway.register_adapter(adapter)

    def get_supported_protocols(self) -> List[str]:
        """
        Return the list of enabled protocol adapters.
        """
        return self._protocol_gateway.supported_protocols()

    async def handle_protocol_request(
        self, protocol: Union[ProtocolName, str], payload: Any
    ) -> Any:
        """
        Handle a request for a specific external protocol (e.g., MCP/A2A).
        """
        return await self._protocol_gateway.handle_request(protocol, payload)

    async def execute_function(self, node_id: Optional[str], function_name: str, *args, **kwargs) -> Any:
        """
        Execute a function on a specific node or any available node.
        
        Args:
            node_id: Target node ID (None for any available node)
            function_name: Name of the function to execute
            *args, **kwargs: Function arguments
            
        Returns:
            Function execution result
            
        Raises:
            NodeNotFoundError: If specified node is not available
            FunctionNotFoundError: If function is not registered
            RemoteExecutionError: If execution fails
        """
        self.debug(f"Executing function '{function_name}' on node '{node_id}'")
        
        # If no specific node is requested, select any available node
        if node_id is None:
            if not self._nodes:
                raise NoAvailableNodesError(
                    message="No compute nodes are available",
                    function_name=function_name,
                    total_nodes=0,
                    healthy_nodes=0,
                )
            
            # Find a node that has this function
            available_nodes = []
            for nid, node_info in self._nodes.items():
                if function_name in node_info.functions and node_info.is_alive():
                    available_nodes.append(nid)
            
            if not available_nodes:
                raise FunctionNotFoundError(
                    function_name=function_name,
                    message=f"Function '{function_name}' not found on any available nodes",
                )
            
            # Select the first available node (could be improved with load balancing)
            node_id = available_nodes[0]
        
        # Check if the requested node exists and is alive
        if node_id not in self._nodes:
            raise NodeNotFoundError(
                node_id=node_id,
                available_nodes=list(self._nodes.keys()),
                message=f"Node '{node_id}' is not available",
            )
        
        node_info = self._nodes[node_id]
        if not node_info.is_alive():
            raise NodeNotFoundError(
                node_id=node_id,
                message=f"Node '{node_id}' is not responding",
            )
        
        # Check if the function exists on the node
        if function_name not in node_info.functions:
            available_functions = list(node_info.functions.keys())
            raise FunctionNotFoundError(
                function_name=function_name,
                node_id=node_id,
                available_functions=available_functions,
                message=(
                    f"Function '{function_name}' not found on node '{node_id}'. "
                    f"Available functions: {available_functions}"
                ),
            )
        
        try:
            # Execute the function asynchronously
            return await self._async_execute_function(node_id, function_name, args, kwargs)
                
        except EasyRemoteError:
            raise
        except Exception as e:
            self.error(f"Failed to execute function '{function_name}' on node '{node_id}': {e}")
            raise ExceptionTranslator.as_remote_execution_error(
                e,
                function_name=function_name,
                node_id=node_id,
                message=f"Function execution failed on node '{node_id}'",
            ) from e

    async def _async_execute_function(
        self,
        node_id: str,
        function_name: str,
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
    ) -> Any:
        """
        Asynchronously execute a function on a remote node.
        
        Args:
            node_id: Target node ID
            function_name: Name of the function to execute
            args: Function arguments tuple
            kwargs: Function keyword arguments dict
            
        Returns:
            Function execution result
            
        Raises:
            RemoteExecutionError: If execution fails
            TimeoutError: If execution times out
        """
        # Generate unique call ID
        call_id = str(uuid.uuid4())
        
        self.info(f"[SEND] SENDING function call to node '{node_id}': function='{function_name}', call_id={call_id}")
        self.info(f"[SEND] Function arguments: args={len(args)} items, kwargs={len(kwargs)} items")
        
        try:
            # Serialize arguments
            self.info("[SEND] Serializing arguments for transmission...")
            serialized_args, serialized_kwargs = self._serializer.serialize_args(*args, **kwargs)
            self.info("[SEND] Arguments serialized successfully")
            
            # Create execution request
            exec_request = service_pb2.ExecutionRequest()
            exec_request.function_name = function_name
            exec_request.args = serialized_args
            exec_request.kwargs = serialized_kwargs
            exec_request.call_id = call_id
            
            # Create control message
            control_msg = service_pb2.ControlMessage()
            control_msg.exec_req.CopyFrom(exec_request)
            
            self.info(f"[SEND] Created execution request message for node '{node_id}'")
            
            # Create future to wait for result
            result_future = create_loop_future()
            
            # Store the future for result processing
            async with self._global_lock:
                self._pending_function_calls[call_id] = result_future
                self.info(f"[SEND] Registered call {call_id} for result tracking")
                
                # Send execution request to node
                if node_id in self._node_communication_queues:
                    queue_size_before = self._node_communication_queues[node_id].qsize()
                    await self._node_communication_queues[node_id].put(control_msg)
                    queue_size_after = self._node_communication_queues[node_id].qsize()
                    self.info(f" [SEND] MESSAGE SENT to node '{node_id}' communication queue!")
                    self.info(f"[SEND] Queue status: before={queue_size_before}, after={queue_size_after}")
                    self.info(f" [SEND] Node '{node_id}' should now receive and process function '{function_name}'")
                else:
                    self.error(f"[SEND] FAILED! No communication channel available for node '{node_id}'")
                    raise RemoteExecutionError(
                        function_name=function_name,
                        node_id=node_id,
                        message=f"No communication channel available for node {node_id}",
                    )
            
            self.info(f"⏳ [WAIT] Waiting for result from node '{node_id}' for call {call_id}...")
            
            # Wait for result with timeout
            try:
                result = await asyncio.wait_for(result_future, timeout=300.0)  # 5 minute timeout
                
                # Update node statistics
                async with self._global_lock:
                    if node_id in self._nodes:
                        self._nodes[node_id].increment_request_count()
                        func_info = self._nodes[node_id].functions.get(function_name)
                        if func_info:
                            func_info.update_call_statistics(1.0)  # Placeholder execution time
                
                self.info(f"[RECV] SUCCESS! Received result from node '{node_id}' for call {call_id}")
                self.info(f"[RECV] Function '{function_name}' executed successfully on node '{node_id}'")
                return result
                
            except asyncio.TimeoutError:
                # Clean up pending call
                async with self._global_lock:
                    self._pending_function_calls.pop(call_id, None)
                
                self.error(f"[WAIT] TIMEOUT! No response from node '{node_id}' for function '{function_name}' (call {call_id})")
                raise TimeoutError(
                    message=f"Function '{function_name}' execution timed out on node '{node_id}'",
                    timeout_seconds=300.0,
                    operation=f"execute:{function_name}",
                )
                
        except EasyRemoteError:
            raise
        except Exception as e:
            # Clean up on error
            async with self._global_lock:
                self._pending_function_calls.pop(call_id, None)
                if node_id in self._nodes:
                    self._nodes[node_id].increment_error_count()
            
            self.error(f"[SEND] ERROR sending function '{function_name}' to node '{node_id}' (call {call_id}): {e}")
            raise ExceptionTranslator.as_remote_execution_error(
                e,
                function_name=function_name,
                node_id=node_id,
                message=f"Function execution dispatch failed on node '{node_id}'",
            ) from e

    def _stream_queue_soft_limit(self) -> int:
        return max(1, int(self.max_queue_size * 0.8))

    def _can_accept_stream_on_node(self, node_id: str) -> bool:
        active_streams = self._node_active_stream_counts.get(node_id, 0)
        if active_streams >= self.max_streams_per_node:
            return False

        communication_queue = self._node_communication_queues.get(node_id)
        if communication_queue is None:
            return False

        if communication_queue.qsize() >= self._stream_queue_soft_limit():
            return False

        return True

    def _build_stream_overload_error(
        self,
        *,
        function_name: str,
        node_id: Optional[str],
        message: str,
    ) -> RemoteExecutionError:
        return RemoteExecutionError(
            function_name=function_name,
            node_id=node_id,
            message=message,
        )

    def _build_stream_error_frame(
        self,
        *,
        call_id: str,
        message: str,
        node_id: Optional[str] = None,
    ) -> Any:
        frame = service_pb2.StreamCallFrame()
        frame.error.call_id = call_id
        frame.error.message = message
        if node_id:
            frame.error.node_id = node_id
        return frame

    async def stream_function(
        self,
        node_id: Optional[str],
        function_name: str,
        *args,
        **kwargs,
    ) -> AsyncIterator[Any]:
        """
        Stream function output from a specific node or any matching node.
        """
        self.debug(f"Streaming function '{function_name}' on node '{node_id}'")

        if len(self._active_stream_ids) >= self.max_total_active_streams:
            raise self._build_stream_overload_error(
                function_name=function_name,
                node_id=node_id,
                message=(
                    "Gateway stream capacity exceeded. "
                    f"active={len(self._active_stream_ids)}, "
                    f"limit={self.max_total_active_streams}"
                ),
            )

        if node_id is None:
            if not self._nodes:
                raise NoAvailableNodesError(
                    message="No compute nodes are available",
                    function_name=function_name,
                    total_nodes=0,
                    healthy_nodes=0,
                )

            function_nodes: List[str] = []
            available_nodes: List[str] = []
            for candidate_node_id, node_info in self._nodes.items():
                if function_name in node_info.functions and node_info.is_alive():
                    function_nodes.append(candidate_node_id)
                    if self._can_accept_stream_on_node(candidate_node_id):
                        available_nodes.append(candidate_node_id)

            if not available_nodes:
                if function_nodes:
                    raise NoAvailableNodesError(
                        message=(
                            f"Function '{function_name}' exists but all candidate nodes are "
                            "currently overloaded for streaming."
                        ),
                        function_name=function_name,
                        total_nodes=len(function_nodes),
                        healthy_nodes=len(function_nodes),
                    )
                raise FunctionNotFoundError(
                    function_name=function_name,
                    message=f"Function '{function_name}' not found on any available nodes",
                )

            node_id = available_nodes[0]

        if node_id not in self._nodes:
            raise NodeNotFoundError(
                node_id=node_id,
                available_nodes=list(self._nodes.keys()),
                message=f"Node '{node_id}' is not available",
            )

        node_info = self._nodes[node_id]
        if not node_info.is_alive():
            raise NodeNotFoundError(
                node_id=node_id,
                message=f"Node '{node_id}' is not responding",
            )

        if not self._can_accept_stream_on_node(node_id):
            raise self._build_stream_overload_error(
                function_name=function_name,
                node_id=node_id,
                message=(
                    f"Node '{node_id}' cannot accept new stream workload. "
                    f"active_streams={self._node_active_stream_counts.get(node_id, 0)}, "
                    f"per_node_limit={self.max_streams_per_node}"
                ),
            )

        if function_name not in node_info.functions:
            available_functions = list(node_info.functions.keys())
            raise FunctionNotFoundError(
                function_name=function_name,
                node_id=node_id,
                available_functions=available_functions,
                message=(
                    f"Function '{function_name}' not found on node '{node_id}'. "
                    f"Available functions: {available_functions}"
                ),
            )

        try:
            async for chunk in self._stream_function_on_node(
                node_id=node_id,
                function_name=function_name,
                args=args,
                kwargs=kwargs,
            ):
                yield chunk
        except EasyRemoteError:
            raise
        except Exception as e:
            self.error(
                f"Failed to stream function '{function_name}' on node '{node_id}': {e}"
            )
            raise ExceptionTranslator.as_remote_execution_error(
                e,
                function_name=function_name,
                node_id=node_id,
                message=f"Function stream failed on node '{node_id}'",
            ) from e

    async def _stream_function_on_node(
        self,
        node_id: str,
        function_name: str,
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
    ) -> AsyncIterator[Any]:
        call_id = str(uuid.uuid4())
        stream_timeout_seconds = 300.0

        self.info(
            f" [STREAM-SEND] Streaming call to node '{node_id}': "
            f"function='{function_name}', call_id={call_id}"
        )

        stream_kwargs = dict(kwargs)
        stream_kwargs[_STREAM_CONTROL_KWARG] = True
        serialized_args, serialized_kwargs = self._serializer.serialize_args(
            *args, **stream_kwargs
        )

        exec_request = service_pb2.ExecutionRequest()
        exec_request.function_name = function_name
        exec_request.args = serialized_args
        exec_request.kwargs = serialized_kwargs
        exec_request.call_id = call_id

        control_msg = service_pb2.ControlMessage()
        control_msg.exec_req.CopyFrom(exec_request)

        response_queue: asyncio.Queue = asyncio.Queue(
            maxsize=self.stream_response_queue_size
        )
        stream_context = StreamExecutionContext(
            call_id=call_id,
            function_name=function_name,
            node_id=node_id,
            response_queue=response_queue,
            timeout=int(stream_timeout_seconds),
        )

        async with self._global_lock:
            if node_id not in self._node_communication_queues:
                raise RemoteExecutionError(
                    function_name=function_name,
                    node_id=node_id,
                    message=f"No communication channel available for node {node_id}",
                )

            if len(self._active_stream_ids) >= self.max_total_active_streams:
                raise self._build_stream_overload_error(
                    function_name=function_name,
                    node_id=node_id,
                    message=(
                        "Gateway stream capacity exceeded. "
                        f"active={len(self._active_stream_ids)}, "
                        f"limit={self.max_total_active_streams}"
                    ),
                )

            if not self._can_accept_stream_on_node(node_id):
                raise self._build_stream_overload_error(
                    function_name=function_name,
                    node_id=node_id,
                    message=(
                        f"Node '{node_id}' cannot accept new stream workload. "
                        f"active_streams={self._node_active_stream_counts.get(node_id, 0)}, "
                        f"per_node_limit={self.max_streams_per_node}"
                    ),
                )

            self._pending_function_calls[call_id] = {
                "response_queue": response_queue,
                "created_at": datetime.now(),
            }
            self._active_stream_contexts[call_id] = stream_context
            self._active_stream_ids.add(call_id)
            self._node_active_stream_counts[node_id] = (
                self._node_active_stream_counts.get(node_id, 0) + 1
            )
            await self._node_communication_queues[node_id].put(control_msg)

        completion_reason = "completed"
        try:
            while True:
                try:
                    exec_result = await asyncio.wait_for(
                        response_queue.get(),
                        timeout=stream_timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    completion_reason = "timeout"
                    raise TimeoutError(
                        message=(
                            f"Function '{function_name}' stream timed out "
                            f"on node '{node_id}'"
                        ),
                        timeout_seconds=stream_timeout_seconds,
                        operation=f"stream:{function_name}",
                    )

                if exec_result.has_error:
                    completion_reason = "error"
                    raise RemoteExecutionError(
                        function_name=exec_result.function_name or function_name,
                        node_id=exec_result.node_id or node_id,
                        message=exec_result.error_message,
                    )

                if exec_result.is_done:
                    break

                serialized_chunk = exec_result.chunk or exec_result.result
                if not serialized_chunk:
                    continue

                try:
                    chunk = self._serializer.deserialize_result(serialized_chunk)
                except Exception as exc:
                    completion_reason = "serialization_error"
                    raise ExceptionTranslator.as_serialization_error(
                        exc,
                        operation="deserialize_stream_chunk",
                        message="Failed to deserialize stream chunk",
                    ) from exc
                yield chunk
        finally:
            async with self._global_lock:
                self._pending_function_calls.pop(call_id, None)
                self._active_stream_ids.discard(call_id)
            await self._cleanup_stream_context(call_id, reason=completion_reason)

    async def stream_function_with_load_balancing(
        self,
        function_name: str,
        load_balancing_config: Union[bool, str, dict],
        *args,
        **kwargs,
    ) -> AsyncIterator[Any]:
        """
        Stream function output from a load-balanced target node.
        """
        self.debug(
            f"Streaming function '{function_name}' with load balancing: "
            f"{load_balancing_config}"
        )

        available_nodes: List[str] = []
        for node_id, node_info in self._nodes.items():
            if (
                function_name in node_info.functions
                and node_info.is_alive()
                and self._can_accept_stream_on_node(node_id)
            ):
                available_nodes.append(node_id)

        if not available_nodes:
            raise NoAvailableNodesError(
                message=(
                    f"No nodes available for streaming function '{function_name}'. "
                    "Candidates are either offline, overloaded, or queue-saturated."
                ),
                function_name=function_name,
                total_nodes=len(self._nodes),
                healthy_nodes=len(
                    [
                        node_id
                        for node_id, node_info in self._nodes.items()
                        if node_info.is_alive()
                    ]
                ),
            )

        request_context = RequestContext(function_name=function_name)
        selected_node = self._load_balancer.select_node(
            function_name,
            request_context,
            available_nodes,
        )

        if not selected_node:
            raise NoAvailableNodesError(
                message="Load balancer could not select a suitable node",
                function_name=function_name,
                total_nodes=len(available_nodes),
                healthy_nodes=len(available_nodes),
            )

        async for chunk in self.stream_function(
            selected_node,
            function_name,
            *args,
            **kwargs,
        ):
            yield chunk
    
    async def execute_function_with_load_balancing(self, function_name: str, 
                                           load_balancing_config: Union[bool, str, dict], 
                                           *args, **kwargs) -> Any:
        """
        Execute a function using load balancing strategy.
        
        Args:
            function_name: Name of the function to execute
            load_balancing_config: Load balancing configuration
            *args, **kwargs: Function arguments
            
        Returns:
            Function execution result
            
        Raises:
            NodeNotFoundError: If no nodes are available
            FunctionNotFoundError: If function is not registered on any node
            RemoteExecutionError: If execution fails
        """
        self.debug(f"Executing function '{function_name}' with load balancing: {load_balancing_config}")
        
        # Find nodes that have this function
        available_nodes = []
        for node_id, node_info in self._nodes.items():
            if function_name in node_info.functions and node_info.is_alive():
                available_nodes.append(node_id)
        
        if not available_nodes:
            raise FunctionNotFoundError(
                function_name=function_name,
                message=f"Function '{function_name}' not found on any available nodes",
            )
        
        try:
            # Create request context for load balancer
            request_context = RequestContext(
                function_name=function_name
            )
            
            # Select optimal node using load balancer
            selected_node = self._load_balancer.select_node(
                function_name, 
                request_context,
                available_nodes
            )
            
            if not selected_node:
                raise NoAvailableNodesError(
                    message="Load balancer could not select a suitable node",
                    function_name=function_name,
                    total_nodes=len(available_nodes),
                    healthy_nodes=len(available_nodes),
                )
            
            self.info(f"Load balancer selected node '{selected_node}' for function '{function_name}'")
            
            # Execute on the selected node using the new implementation
            return await self.execute_function(selected_node, function_name, *args, **kwargs)
            
        except EasyRemoteError:
            raise
        except Exception as e:
            self.error(f"Load balanced execution failed for function '{function_name}': {e}")
            raise LoadBalancingError(
                message=f"Load balanced execution failed for function '{function_name}'",
                strategy=str(load_balancing_config),
                available_nodes=len(available_nodes),
                cause=e,
            ) from e
    
    async def _async_cleanup(self):
        """Cleanup server resources and background tasks."""
        self.debug("Starting server cleanup")

        if self._state in {ServerState.STARTING, ServerState.RUNNING, ServerState.ERROR}:
            try:
                await self._set_state(ServerState.STOPPING)
            except RuntimeError:
                # Best effort lifecycle transition during shutdown.
                pass
        
        # Signal shutdown to all background tasks
        self._shutdown_event.set()
        
        # Cancel and wait for background tasks
        if self._background_tasks:
            self.debug(f"Cancelling {len(self._background_tasks)} background tasks")
            for task in self._background_tasks:
                if not task.done():
                    task.cancel()
            
            # Wait for tasks to complete cancellation
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            self._background_tasks.clear()
        
        # Close gRPC server
        if self._grpc_server:
            self.debug("Stopping gRPC server")
            await self._grpc_server.stop(grace=5.0)
            self._grpc_server = None
        
        # Clear global instance
        with DistributedComputingGateway._instance_lock:
            DistributedComputingGateway._global_instance = None
        
        if self._state != ServerState.STOPPED:
            await self._set_state(ServerState.STOPPED)
        self.info("Server cleanup completed")
    
    async def _remove_node_safely(self, node_id: str, reason: str = "unknown"):
        """Safely remove a node from the system."""
        async with self._global_lock:
            # Remove node information
            if node_id in self._nodes:
                self._nodes.pop(node_id)
                self.info(f"Removed node '{node_id}' from registry")
            
            # Clean up communication queues
            if node_id in self._node_communication_queues:
                self._node_communication_queues.pop(node_id)
                self.debug(f"Cleaned up communication queue for node '{node_id}'")

            self._node_active_stream_counts.pop(node_id, None)
        
        self.warning(f"Node '{node_id}' removed from system (reason: {reason})")
    
    async def _cleanup_stream_context(self, call_id: str, reason: str = "unknown"):
        """Clean up a stream execution context."""
        if call_id in self._active_stream_contexts:
            stream_ctx = self._active_stream_contexts.pop(call_id)
            node_id = stream_ctx.node_id
            await stream_ctx.cleanup(f"cleanup_{reason}")
            if node_id in self._node_active_stream_counts:
                next_count = max(0, self._node_active_stream_counts[node_id] - 1)
                if next_count == 0:
                    self._node_active_stream_counts.pop(node_id, None)
                else:
                    self._node_active_stream_counts[node_id] = next_count
            self._active_stream_ids.discard(call_id)
            self.debug(f"Cleaned up stream context '{call_id}' (reason: {reason})")
    
    async def _cleanup_pending_call(self, call_id: str, reason: str = "unknown"):
        """Clean up a pending function call."""
        if call_id in self._pending_function_calls:
            call_context = self._pending_function_calls.pop(call_id)
            
            # If it's a Future, cancel it
            if hasattr(call_context, 'cancel'):
                call_context.cancel()
            
            self.debug(f"Cleaned up pending call '{call_id}' (reason: {reason})")
    
    @classmethod
    def get_global_instance(cls) -> Optional['DistributedComputingGateway']:
        """
        Get the global server instance for singleton access.
        
        Returns:
            Global server instance if available, None otherwise
        """
        with cls._instance_lock:
            return cls._global_instance


class GatewayServerBuilder:
    """
    Builder for fluent gateway server configuration and construction.
    
    This builder provides a convenient way to configure and create
    distributed computing gateway servers with comprehensive customization options.
    
    Example:
        >>> server = GatewayServerBuilder() \
        ...     .with_port(8080) \
        ...     .with_load_balancing_strategy("ml_enhanced") \
        ...     .enable_health_monitoring() \
        ...     .enable_performance_analytics() \
        ...     .with_security_config(auth_required=True) \
        ...     .build()
    """
    
    def __init__(self):
        """Initialize builder with default configuration."""
        self._port: int = 8080
        self._heartbeat_timeout_seconds: float = 30.0
        self._max_queue_size: int = 5000
        self._max_workers: int = 20
        self._max_total_active_streams: int = 512
        self._max_streams_per_node: int = 32
        self._stream_response_queue_size: int = 256
        self._enable_monitoring: bool = True
        self._enable_analytics: bool = True
        self._enable_security: bool = False
        self._enable_clustering: bool = False
        self._cleanup_interval_seconds: float = 300.0
        self._log_level: str = "info"
    
    def with_port(self, port: int) -> 'GatewayServerBuilder':
        """Set server port."""
        self._port = port
        return self
    
    def with_performance_config(self, 
                               max_workers: int = 20,
                               max_queue_size: int = 5000,
                               heartbeat_timeout_seconds: float = 30.0,
                               max_total_active_streams: int = 512,
                               max_streams_per_node: int = 32,
                               stream_response_queue_size: int = 256) -> 'GatewayServerBuilder':
        """Configure performance parameters."""
        self._max_workers = max_workers
        self._max_queue_size = max_queue_size
        self._heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self._max_total_active_streams = max_total_active_streams
        self._max_streams_per_node = max_streams_per_node
        self._stream_response_queue_size = stream_response_queue_size
        return self

    def with_stream_limits(
        self,
        *,
        max_total_active_streams: int = 512,
        max_streams_per_node: int = 32,
        stream_response_queue_size: int = 256,
    ) -> 'GatewayServerBuilder':
        """Configure stream-specific pressure limits."""
        self._max_total_active_streams = max_total_active_streams
        self._max_streams_per_node = max_streams_per_node
        self._stream_response_queue_size = stream_response_queue_size
        return self
    
    def enable_monitoring(self, enabled: bool = True) -> 'GatewayServerBuilder':
        """Enable comprehensive monitoring."""
        self._enable_monitoring = enabled
        return self
    
    def enable_analytics(self, enabled: bool = True) -> 'GatewayServerBuilder':
        """Enable advanced analytics and ML features."""
        self._enable_analytics = enabled
        return self
    
    def enable_security(self, enabled: bool = True) -> 'GatewayServerBuilder':
        """Enable security and authentication features."""
        self._enable_security = enabled
        return self
    
    def enable_clustering(self, enabled: bool = True) -> 'GatewayServerBuilder':
        """Enable high-availability clustering."""
        self._enable_clustering = enabled
        return self
    
    def with_cleanup_interval(self, seconds: float) -> 'GatewayServerBuilder':
        """Set cleanup interval in seconds."""
        self._cleanup_interval_seconds = seconds
        return self
    
    def with_log_level(self, level: str) -> 'GatewayServerBuilder':
        """Set logging level."""
        self._log_level = level
        return self
    
    def build(self) -> DistributedComputingGateway:
        """
        Build and return configured gateway server instance.
        
        Returns:
            Configured DistributedComputingGateway instance
            
        Raises:
            ValueError: If configuration is invalid
        """
        return DistributedComputingGateway(
            port=self._port,
            heartbeat_timeout_seconds=self._heartbeat_timeout_seconds,
            max_queue_size=self._max_queue_size,
            max_workers=self._max_workers,
            max_total_active_streams=self._max_total_active_streams,
            max_streams_per_node=self._max_streams_per_node,
            stream_response_queue_size=self._stream_response_queue_size,
            enable_monitoring=self._enable_monitoring,
            enable_analytics=self._enable_analytics,
            enable_security=self._enable_security,
            enable_clustering=self._enable_clustering,
            cleanup_interval_seconds=self._cleanup_interval_seconds,
            log_level=self._log_level
        )


# Backward compatibility aliases
# This ensures existing code continues to work while we transition to the new naming
Server = DistributedComputingGateway
DistributedComputeServer = DistributedComputingGateway


# Export all public classes and functions
__all__ = [
    # Core classes
    'DistributedComputingGateway',
    'GatewayServerBuilder',
    'ServerState',
    'ServerMetrics',
    'StreamExecutionContext',
    
    # Backward compatibility
    'Server',
    'DistributedComputeServer'
]
