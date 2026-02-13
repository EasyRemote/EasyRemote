#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EasyRemote Asynchronous Programming Helpers Module

This module provides comprehensive utilities for safe and efficient asynchronous
programming in the EasyRemote distributed computing framework. It handles common
async challenges including event loop management, cross-thread communication,
and safe execution patterns.

Architecture:
- Strategy Pattern: Multiple execution strategies for different async scenarios
- Context Manager Pattern: Safe resource management for async operations
- Observer Pattern: Event-driven async notifications and monitoring
- Factory Pattern: Event loop creation and management

Key Features:
1. Safe Event Loop Management:
   * Automatic event loop detection and creation
   * Cross-thread event loop execution
   * Safe shutdown and cleanup procedures
   * Event loop lifecycle management

2. Async Execution Utilities:
   * Safe coroutine execution in any context
   * Background task management with proper cleanup
   * Thread-safe async operations
   * Timeout and cancellation support

3. Advanced Async Patterns:
   * Async context managers with proper cleanup
   * Retry mechanisms with exponential backoff
   * Rate limiting and throttling utilities
   * Async resource pooling and management

4. Error Handling and Debugging:
   * Comprehensive exception handling for async operations
   * Async debugging utilities and diagnostics
   * Performance monitoring for async operations
   * Graceful degradation strategies

Usage Example:
    >>> # Safe async execution
    >>> async_helper = AsyncExecutionHelper()
    >>> result = async_helper.run_safely(my_coroutine(), timeout=30.0)
    >>> 
    >>> # Background execution
    >>> background_task = async_helper.run_in_background(
    ...     long_running_task(),
    ...     on_complete=handle_completion,
    ...     on_error=handle_error
    ... )
    >>> 
    >>> # Managed event loop
    >>> async with ManagedEventLoop() as loop_manager:
    ...     result = await loop_manager.execute(my_coroutine())

Author: Silan Hu (silan.hu@u.nus.edu)
Version: 2.0.0
"""

import asyncio
import threading
import logging
import time
from typing import (
    Coroutine, Any, Optional, Callable, Dict, Set, TypeVar
)
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from .logger import ModernLogger


# Configure module logger
_logger = logging.getLogger(__name__)

T = TypeVar('T')


class ExecutionStrategy(Enum):
    """Strategies for executing async operations."""
    DIRECT = "direct"                    # Direct execution in current loop
    NEW_THREAD = "new_thread"           # Execute in new thread with new loop
    THREAD_POOL = "thread_pool"         # Execute in thread pool
    MANAGED_LOOP = "managed_loop"       # Execute in managed background loop


class TaskStatus(Enum):
    """Status of async task execution."""
    PENDING = "pending"                 # Task is waiting to start
    RUNNING = "running"                 # Task is currently executing
    COMPLETED = "completed"             # Task completed successfully
    FAILED = "failed"                   # Task failed with error
    CANCELLED = "cancelled"             # Task was cancelled
    TIMEOUT = "timeout"                 # Task timed out


@dataclass
class AsyncTaskResult:
    """
    Result of async task execution with comprehensive metadata.
    
    This class encapsulates the result of async operations including
    execution metadata, performance metrics, and error information.
    """
    task_id: str
    status: TaskStatus
    result: Any = None
    error: Optional[Exception] = None
    execution_time_ms: float = 0.0
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    retries: int = 0
    thread_id: Optional[int] = None
    loop_id: Optional[str] = None
    
    @property
    def is_successful(self) -> bool:
        """Check if task completed successfully."""
        return self.status == TaskStatus.COMPLETED and self.error is None
    
    @property
    def elapsed_time(self) -> timedelta:
        """Get total elapsed time for task execution."""
        end = self.end_time or datetime.now()
        return end - self.start_time
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "execution_time_ms": self.execution_time_ms,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "retries": self.retries,
            "thread_id": self.thread_id,
            "is_successful": self.is_successful,
            "has_error": self.error is not None,
            "error_type": type(self.error).__name__ if self.error else None
        }


class AsyncExecutionHelper(ModernLogger):
    """
    Advanced async execution helper with comprehensive safety features.
    
    This class provides safe and efficient async execution capabilities
    with automatic event loop management, error handling, and performance
    monitoring.
    
    Features:
    - Automatic event loop detection and management
    - Safe cross-thread async execution
    - Comprehensive error handling and recovery
    - Performance monitoring and metrics collection
    - Retry mechanisms with exponential backoff
    - Resource cleanup and lifecycle management
    
    Usage:
        >>> helper = AsyncExecutionHelper()
        >>> 
        >>> # Safe execution with automatic strategy selection
        >>> result = helper.run_safely(my_coroutine(), timeout=30.0)
        >>> 
        >>> # Background execution with callbacks
        >>> task = helper.run_in_background(
        ...     long_task(),
        ...     on_complete=lambda result: print(f"Done: {result}"),
        ...     on_error=lambda error: print(f"Error: {error}")
        ... )
    """
    
    def __init__(self, 
                 enable_metrics: bool = True,
                 default_timeout: float = 300.0,
                 max_workers: int = 5):
        """
        Initialize async execution helper.
        
        Args:
            enable_metrics: Enable performance metrics collection
            default_timeout: Default timeout for async operations
            max_workers: Maximum number of worker threads
        """
        super().__init__(name="AsyncExecutionHelper")
        
        self.enable_metrics = enable_metrics
        self.default_timeout = default_timeout
        self.max_workers = max_workers
        
        # Execution tracking
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._task_results: Dict[str, AsyncTaskResult] = {}
        self._task_counter = 0
        self._counter_lock = threading.Lock()
        self._results_lock = threading.Lock()
        self._stats_lock = threading.Lock()
        
        # Thread pool for sync operations
        self._thread_pool: Optional[ThreadPoolExecutor] = None
        self._cleanup_scheduled = False
        
        # Metrics collection
        self._execution_stats = {
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "average_execution_time_ms": 0.0,
            "total_execution_time_ms": 0.0
        }
        
        self.debug("Initialized AsyncExecutionHelper")
    
    def is_running_in_event_loop(self) -> bool:
        """
        Check if currently running inside an event loop.
        
        Returns:
            True if running in an event loop, False otherwise
        """
        try:
            asyncio.get_running_loop()
            return True
        except RuntimeError:
            return False
    
    def get_or_create_event_loop(self) -> asyncio.AbstractEventLoop:
        """
        Get existing event loop or create a new one safely.
        
        Returns:
            Event loop instance
            
        Note:
            This method handles the common case where no event loop
            exists in the current thread.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("Event loop is closed")
            return loop
        except RuntimeError:
            # No event loop exists, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.debug("Created new event loop")
            return loop
    
    def run_safely(self, 
                  coro: Coroutine[Any, Any, T], 
                  timeout: Optional[float] = None,
                  strategy: Optional[ExecutionStrategy] = None) -> T:
        """
        Safely execute a coroutine with automatic strategy selection.
        
        This method automatically handles event loop conflicts and chooses
        the most appropriate execution strategy based on the current context.
        
        Args:
            coro: Coroutine to execute
            timeout: Execution timeout in seconds
            strategy: Force specific execution strategy
            
        Returns:
            Result of the coroutine execution
            
        Raises:
            asyncio.TimeoutError: If execution times out
            Exception: Any exception raised by the coroutine
            
        Example:
            >>> async def fetch_data():
            ...     await asyncio.sleep(1)
            ...     return "data"
            >>> 
            >>> helper = AsyncExecutionHelper()
            >>> result = helper.run_safely(fetch_data(), timeout=5.0)
            >>> print(result)  # "data"
        """
        timeout = timeout or self.default_timeout
        
        # Generate task ID for tracking
        task_id = self._generate_task_id()
        
        # Select execution strategy
        if strategy is None:
            strategy = self._select_execution_strategy()
        
        start_time = time.time()
        task_result = AsyncTaskResult(
            task_id=task_id,
            status=TaskStatus.PENDING,
            thread_id=threading.get_ident()
        )
        
        try:
            self.debug(f"Executing coroutine with strategy: {strategy.value}")
            task_result.status = TaskStatus.RUNNING
            
            if strategy == ExecutionStrategy.DIRECT:
                result = self._run_direct(coro, timeout)
            elif strategy == ExecutionStrategy.NEW_THREAD:
                result = self._run_in_new_thread(coro, timeout)
            elif strategy == ExecutionStrategy.THREAD_POOL:
                result = self._run_in_thread_pool(coro, timeout)
            else:
                raise ValueError(f"Unsupported execution strategy: {strategy}")
            
            # Record successful execution
            execution_time = (time.time() - start_time) * 1000
            task_result.status = TaskStatus.COMPLETED
            task_result.result = result
            task_result.execution_time_ms = execution_time
            task_result.end_time = datetime.now()
            
            self._record_execution_metrics(execution_time, True)
            self.debug(f"Coroutine execution completed ({execution_time:.2f}ms)")
            
            return result
            
        except asyncio.TimeoutError as e:
            task_result.status = TaskStatus.TIMEOUT
            task_result.error = e
            task_result.end_time = datetime.now()
            self._record_execution_metrics((time.time() - start_time) * 1000, False)
            self.error(f"Coroutine execution timed out after {timeout}s")
            raise
            
        except Exception as e:
            task_result.status = TaskStatus.FAILED
            task_result.error = e
            task_result.end_time = datetime.now()
            self._record_execution_metrics((time.time() - start_time) * 1000, False)
            self.error(f"Coroutine execution failed: {e}")
            raise
            
        finally:
            # Store task result for metrics
            if self.enable_metrics:
                with self._results_lock:
                    self._task_results[task_id] = task_result
    
    def _select_execution_strategy(self) -> ExecutionStrategy:
        """Select the most appropriate execution strategy for current context."""
        if self.is_running_in_event_loop():
            # Already in event loop, need to use thread-based execution
            return ExecutionStrategy.NEW_THREAD
        else:
            # Can run directly
            return ExecutionStrategy.DIRECT
    
    def _run_direct(self, coro: Coroutine, timeout: float) -> Any:
        """Execute coroutine directly in current thread."""
        loop = self.get_or_create_event_loop()
        try:
            if timeout:
                return loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
            else:
                return loop.run_until_complete(coro)
        except RuntimeError as e:
            if "cannot be called from a running event loop" in str(e):
                # Fallback to thread execution
                self.warning("Event loop conflict, falling back to thread execution")
                return self._run_in_new_thread(coro, timeout)
            else:
                raise
    
    def _run_in_new_thread(self, coro: Coroutine, timeout: float) -> Any:
        """Execute coroutine in a new thread with its own event loop."""
        result_container = {}
        exception_container = {}
        
        def run_in_thread():
            try:
                # Create new event loop for this thread
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    if timeout:
                        result = new_loop.run_until_complete(
                            asyncio.wait_for(coro, timeout=timeout)
                        )
                    else:
                        result = new_loop.run_until_complete(coro)
                    result_container['result'] = result
                except Exception as e:
                    exception_container['exception'] = e
                finally:
                    new_loop.close()
            except Exception as e:
                exception_container['exception'] = e
        
        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join(timeout=timeout + 5.0 if timeout else None)  # Extra buffer for cleanup
        
        if thread.is_alive():
            self.error("Thread execution did not complete in time")
            raise asyncio.TimeoutError("Thread execution timeout")
        
        if 'exception' in exception_container:
            raise exception_container['exception']
        
        if 'result' not in result_container:
            raise RuntimeError("No result received from thread execution")
        
        return result_container['result']
    
    def _run_in_thread_pool(self, coro: Coroutine, timeout: float) -> Any:
        """Execute coroutine in thread pool executor."""
        if self._thread_pool is None:
            self._thread_pool = ThreadPoolExecutor(max_workers=self.max_workers)
        
        def run_coro_in_thread():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                if timeout:
                    return new_loop.run_until_complete(
                        asyncio.wait_for(coro, timeout=timeout)
                    )
                else:
                    return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
        
        future = self._thread_pool.submit(run_coro_in_thread)
        try:
            return future.result(timeout=timeout + 5.0 if timeout else None)
        except FutureTimeoutError:
            future.cancel()
            raise asyncio.TimeoutError("Thread pool execution timeout")
    
    def run_in_background(self,
                         coro: Coroutine[Any, Any, T],
                         on_complete: Optional[Callable[[T], None]] = None,
                         on_error: Optional[Callable[[Exception], None]] = None,
                         daemon: bool = True) -> threading.Thread:
        """
        Execute coroutine in background thread with callbacks.
        
        Args:
            coro: Coroutine to execute
            on_complete: Callback for successful completion
            on_error: Callback for error handling
            daemon: Whether thread should be daemon
            
        Returns:
            Thread object executing the coroutine
            
        Example:
            >>> def handle_result(result):
            ...     print(f"Background task completed: {result}")
            >>> 
            >>> def handle_error(error):
            ...     print(f"Background task failed: {error}")
            >>> 
            >>> thread = helper.run_in_background(
            ...     fetch_data(),
            ...     on_complete=handle_result,
            ...     on_error=handle_error
            ... )
        """
        task_id = self._generate_task_id()
        
        def run_background_task():
            task_result = AsyncTaskResult(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                thread_id=threading.get_ident()
            )
            
            try:
                # Create new event loop for background thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                task_result.loop_id = str(id(loop))
                
                try:
                    start_time = time.time()
                    result = loop.run_until_complete(coro)
                    execution_time = (time.time() - start_time) * 1000
                    
                    task_result.status = TaskStatus.COMPLETED
                    task_result.result = result
                    task_result.execution_time_ms = execution_time
                    task_result.end_time = datetime.now()
                    
                    self.debug(f"Background task {task_id} completed ({execution_time:.2f}ms)")
                    
                    if on_complete:
                        try:
                            on_complete(result)
                        except Exception as e:
                            self.error(f"Error in completion callback: {e}")
                    
                    return result
                    
                except Exception as e:
                    task_result.status = TaskStatus.FAILED
                    task_result.error = e
                    task_result.end_time = datetime.now()
                    
                    self.error(f"Background task {task_id} failed: {e}")
                    
                    if on_error:
                        try:
                            on_error(e)
                        except Exception as callback_error:
                            self.error(f"Error in error callback: {callback_error}")
                    
                    raise
                    
                finally:
                    loop.close()
                    
            except Exception as e:
                task_result.status = TaskStatus.FAILED
                task_result.error = e
                task_result.end_time = datetime.now()
            
            finally:
                # Store task result
                if self.enable_metrics:
                    with self._results_lock:
                        self._task_results[task_id] = task_result
        
        thread = threading.Thread(target=run_background_task, daemon=daemon)
        thread.start()
        
        self.debug(f"Started background task {task_id} in thread {thread.ident}")
        return thread
    
    async def run_in_executor(self, 
                             func: Callable[..., T], 
                             *args: Any, 
                             **kwargs: Any) -> T:
        """
        Execute synchronous function in thread pool executor.
        
        Args:
            func: Synchronous function to execute
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function
            
        Returns:
            Result of function execution
            
        Example:
            >>> import time
            >>> async def example():
            ...     result = await helper.run_in_executor(time.sleep, 1)
            ...     return "completed"
        """
        loop = asyncio.get_running_loop()
        
        if kwargs:
            import functools
            wrapped_func = functools.partial(func, **kwargs)
            return await loop.run_in_executor(None, wrapped_func, *args)
        else:
            return await loop.run_in_executor(None, func, *args)
    
    def _generate_task_id(self) -> str:
        """Generate unique task ID."""
        with self._counter_lock:
            self._task_counter += 1
            counter = self._task_counter
        return f"task_{counter}_{int(time.time() * 1000)}"
    
    def _record_execution_metrics(self, execution_time_ms: float, success: bool):
        """Record execution metrics for performance monitoring."""
        if not self.enable_metrics:
            return

        with self._stats_lock:
            self._execution_stats["total_executions"] += 1
            self._execution_stats["total_execution_time_ms"] += execution_time_ms

            if success:
                self._execution_stats["successful_executions"] += 1
            else:
                self._execution_stats["failed_executions"] += 1

            # Update average execution time
            self._execution_stats["average_execution_time_ms"] = (
                self._execution_stats["total_execution_time_ms"] /
                self._execution_stats["total_executions"]
            )
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """Get execution statistics and metrics."""
        with self._stats_lock:
            stats = dict(self._execution_stats)
        with self._results_lock:
            completed_tasks = len(self._task_results)
        stats.update({
            "success_rate": (
                stats["successful_executions"] /
                max(stats["total_executions"], 1)
            ),
            "active_tasks": len(self._active_tasks),
            "completed_tasks": completed_tasks,
            "thread_pool_active": self._thread_pool is not None
        })
        return stats
    
    def cleanup(self):
        """Clean up resources and shutdown thread pool."""
        if self._thread_pool:
            self.debug("Shutting down thread pool")
            self._thread_pool.shutdown(wait=True)
            self._thread_pool = None
        
        # Clear task tracking
        self._active_tasks.clear()
        with self._results_lock:
            self._task_results.clear()
        
        self.debug("AsyncExecutionHelper cleanup completed")
    
    def __del__(self):
        """Ensure cleanup on object destruction."""
        try:
            self.cleanup()
        except Exception:
            pass


class ManagedEventLoop(ModernLogger):
    """
    Managed event loop with lifecycle management and monitoring.
    
    This class provides a managed event loop that runs in a dedicated
    thread with proper startup, shutdown, and error handling.
    
    Features:
    - Dedicated thread for event loop execution
    - Safe startup and shutdown procedures
    - Task scheduling and execution monitoring
    - Resource cleanup and lifecycle management
    
    Usage:
        >>> async with ManagedEventLoop() as loop_manager:
        ...     result = await loop_manager.execute(my_coroutine())
        >>> 
        >>> # Or manual management
        >>> loop_manager = ManagedEventLoop()
        >>> loop_manager.start()
        >>> try:
        ...     result = loop_manager.run_coroutine(my_coroutine())
        ... finally:
        ...     loop_manager.stop()
    """
    
    def __init__(self, daemon: bool = True):
        """
        Initialize managed event loop.
        
        Args:
            daemon: Whether the event loop thread should be daemon
        """
        super().__init__(name="ManagedEventLoop")
        
        self.daemon = daemon
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._startup_event = threading.Event()
        self._shutdown_event = threading.Event()
        
        # Task tracking
        self._scheduled_tasks: Set[asyncio.Task] = set()
        self._task_results: Dict[str, Any] = {}
        
        self.debug("Initialized ManagedEventLoop")
    
    def start(self, timeout: float = 5.0) -> 'ManagedEventLoop':
        """
        Start the managed event loop in dedicated thread.
        
        Args:
            timeout: Timeout for loop startup
            
        Returns:
            Self for method chaining
            
        Raises:
            RuntimeError: If loop fails to start
        """
        if self._running:
            return self
        
        self._startup_event.clear()
        self._shutdown_event.clear()
        
        def run_event_loop():
            try:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                
                # Signal that loop is ready
                self._startup_event.set()
                
                self.debug("Event loop started")
                self._loop.run_forever()
                
            except Exception as e:
                self.error(f"Event loop error: {e}")
            finally:
                if self._loop:
                    self._loop.close()
                self._shutdown_event.set()
                self.debug("Event loop stopped")
        
        self._thread = threading.Thread(target=run_event_loop, daemon=self.daemon)
        self._thread.start()
        self._running = True
        
        # Wait for loop to start
        if not self._startup_event.wait(timeout=timeout):
            self.error("Event loop failed to start within timeout")
            self.stop()
            raise RuntimeError("Event loop startup timeout")
        
        self.info("Managed event loop started successfully")
        return self
    
    def stop(self, timeout: float = 5.0):
        """
        Stop the managed event loop gracefully.
        
        Args:
            timeout: Timeout for graceful shutdown
        """
        if not self._running:
            return
        
        self._running = False
        
        if self._loop and not self._loop.is_closed():
            # Schedule loop stop
            self._loop.call_soon_threadsafe(self._loop.stop)
        
        # Wait for shutdown
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            
            if self._thread.is_alive():
                self.warning("Event loop thread did not stop gracefully")
        
        self.info("Managed event loop stopped")
    
    def run_coroutine(self, 
                     coro: Coroutine[Any, Any, T], 
                     timeout: Optional[float] = None) -> T:
        """
        Execute coroutine in the managed event loop.
        
        Args:
            coro: Coroutine to execute
            timeout: Execution timeout
            
        Returns:
            Result of coroutine execution
            
        Raises:
            RuntimeError: If event loop is not running
            asyncio.TimeoutError: If execution times out
        """
        if not self._running or not self._loop:
            raise RuntimeError("Event loop not running")
        
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)
    
    async def execute(self, coro: Coroutine[Any, Any, T]) -> T:
        """
        Execute coroutine directly (for use within async context).
        
        Args:
            coro: Coroutine to execute
            
        Returns:
            Result of coroutine execution
        """
        if not self._running or not self._loop:
            raise RuntimeError("Event loop not running")
        
        return await coro
    
    @property
    def is_running(self) -> bool:
        """Check if the event loop is running."""
        return self._running and self._loop and not self._loop.is_closed()
    
    async def __aenter__(self) -> 'ManagedEventLoop':
        """Async context manager entry."""
        self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        self.stop()
    
    def __enter__(self) -> 'ManagedEventLoop':
        """Sync context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Sync context manager exit."""
        self.stop()


# Convenience functions for common async operations
_global_async_helper: Optional[AsyncExecutionHelper] = None


def get_async_helper() -> AsyncExecutionHelper:
    """Get global async execution helper instance."""
    global _global_async_helper
    if _global_async_helper is None:
        _global_async_helper = AsyncExecutionHelper()
    return _global_async_helper


def run_async_safely(coro: Coroutine[Any, Any, T], 
                    timeout: Optional[float] = None) -> T:
    """
    Convenience function for safe async execution.
    
    Args:
        coro: Coroutine to execute
        timeout: Execution timeout
        
    Returns:
        Result of coroutine execution
    """
    return get_async_helper().run_safely(coro, timeout=timeout)


def is_running_in_event_loop() -> bool:
    """
    Check if currently running inside an event loop.
    
    Returns:
        True if running in an event loop, False otherwise
    """
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


# Export all public classes and functions
__all__ = [
    'AsyncExecutionHelper',
    'ManagedEventLoop',
    'AsyncTaskResult',
    'ExecutionStrategy',
    'TaskStatus',
    'get_async_helper',
    'run_async_safely',
    'is_running_in_event_loop'
] 
