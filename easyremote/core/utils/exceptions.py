from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
import traceback
import uuid
from enum import Enum
from .logger import ModernLogger

class ErrorSeverity(Enum):
    """
    Enumeration defining different severity levels for exceptions.
    
    This provides a standardized way to categorize errors based on their impact
    and urgency for handling.
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """
    Enumeration defining different categories of errors.
    
    This helps in organizing and filtering exceptions based on their functional domain.
    """
    NETWORK = "network"
    SYSTEM = "system"
    DATA = "data"
    EXECUTION = "execution"
    CONFIGURATION = "configuration"
    CONCURRENCY = "concurrency"
    PROTOCOL = "protocol"


@dataclass
class ErrorContext:
    """
    Data class to store comprehensive error context information.
    
    This class encapsulates all relevant information about an error occurrence,
    providing detailed context for debugging and error analysis.
    
    Attributes:
        timestamp: When the error occurred
        module: The module where the error originated
        function: The function where the error occurred
        line_number: Line number where the error occurred
        additional_data: Any additional context data
        stack_trace: Full stack trace of the error
    """
    timestamp: datetime = field(default_factory=datetime.now)
    module: Optional[str] = None
    function: Optional[str] = None
    line_number: Optional[int] = None
    additional_data: Dict[str, Any] = field(default_factory=dict)
    stack_trace: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert error context to dictionary representation.
        
        Returns:
            Dictionary containing all error context information
        """
        return {
            'timestamp': self.timestamp.isoformat(),
            'module': self.module,
            'function': self.function,
            'line_number': self.line_number,
            'additional_data': self.additional_data,
            'stack_trace': self.stack_trace
        }


class ErrorCodeRegistry:
    """
    Registry class for managing error codes and their metadata.
    
    This class provides a centralized way to manage error codes, their descriptions,
    severity levels, and categories.
    """
    
    ERROR_CODES: Dict[str, Dict[str, Any]] = {
        'NodeNotFoundError': {
            'code': 'E001',
            'severity': ErrorSeverity.HIGH,
            'category': ErrorCategory.SYSTEM
        },
        'FunctionNotFoundError': {
            'code': 'E002',
            'severity': ErrorSeverity.HIGH,
            'category': ErrorCategory.EXECUTION
        },
        'ConnectionError': {
            'code': 'E003',
            'severity': ErrorSeverity.CRITICAL,
            'category': ErrorCategory.NETWORK
        },
        'SerializationError': {
            'code': 'E004',
            'severity': ErrorSeverity.MEDIUM,
            'category': ErrorCategory.DATA
        },
        'RemoteExecutionError': {
            'code': 'E005',
            'severity': ErrorSeverity.HIGH,
            'category': ErrorCategory.EXECUTION
        },
        'NoAvailableNodesError': {
            'code': 'E006',
            'severity': ErrorSeverity.HIGH,
            'category': ErrorCategory.SYSTEM
        },
        'ConcurrencyBoundaryError': {
            'code': 'E007',
            'severity': ErrorSeverity.HIGH,
            'category': ErrorCategory.CONCURRENCY
        },
        'ProtocolHandlingError': {
            'code': 'E008',
            'severity': ErrorSeverity.MEDIUM,
            'category': ErrorCategory.PROTOCOL
        }
    }
    
    @classmethod
    def get_error_info(cls, exception_class_name: str) -> Dict[str, Any]:
        """
        Get complete error information for a given exception class.
        
        Args:
            exception_class_name: Name of the exception class
            
        Returns:
            Dictionary containing error code, description, severity, and category
        """
        return cls.ERROR_CODES.get(exception_class_name, {
            'code': 'E999',
            'severity': ErrorSeverity.MEDIUM,
            'category': ErrorCategory.SYSTEM
        })


class EasyRemoteError(Exception, ModernLogger):
    """
    Base exception class for all EasyRemote-related errors.
    
    This class provides a comprehensive error handling framework with:
    - Automatic error ID generation
    - Rich logging with color-coded output
    - Error context tracking
    - Cause chain management
    - Statistical error tracking
    
    Attributes:
        message: The error message
        cause: The underlying exception that caused this error (if any)
        error_id: Unique identifier for this error occurrence
        error_code: Standardized error code
        error_context: Detailed context information
        severity: Error severity level
        category: Error category
    """
    
    def __init__(
        self, 
        message: str, 
        cause: Optional[Exception] = None,
        context: Optional[ErrorContext] = None,
        additional_data: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the EasyRemoteError with comprehensive error information.
        
        Args:
            message: Human-readable error message
            cause: The underlying exception that caused this error
            context: Additional error context information
            additional_data: Any additional data relevant to the error
        """
        # Initialize parent classes
        Exception.__init__(self, message)
        ModernLogger.__init__(self, name=f"EasyRemoteError.{self.__class__.__name__}")
        
        # Core error properties
        self.message = message
        self.cause = cause
        
        # Generate unique error ID
        self.error_id = str(uuid.uuid4())[:8]  # Short UUID for readability
        
        # Get error metadata from registry
        error_info = ErrorCodeRegistry.get_error_info(self.__class__.__name__)
        self.error_code = error_info['code']
        self.severity = error_info['severity']
        self.category = error_info['category']
        
        # Error context management
        self.error_context = context or ErrorContext()
        if additional_data:
            self.error_context.additional_data.update(additional_data)
        
        # Capture stack trace if not provided
        if not self.error_context.stack_trace:
            self.error_context.stack_trace = traceback.format_exc()
        
        # Log the error with appropriate severity
        self._log_error()
    
    def _log_error(self) -> None:
        """Log the error with rich formatting based on severity."""
        severity_icons = {
            ErrorSeverity.LOW: "ℹ️",
            ErrorSeverity.MEDIUM: "⚠️",
            ErrorSeverity.HIGH: "❌",
            ErrorSeverity.CRITICAL: "💀"
        }
        
        icon = severity_icons.get(self.severity, "❓")
        
        # Log main error with appropriate level
        main_message = (
            f"{icon} [bold]{self.error_code}[/bold] "
            f"[dim]{self.error_id}[/dim] - "
            f"[red]{self.__class__.__name__}[/red]: {self.message}"
        )
        
        if self.severity == ErrorSeverity.CRITICAL:
            self.critical(main_message)
        elif self.severity == ErrorSeverity.HIGH:
            self.error(main_message)
        elif self.severity == ErrorSeverity.MEDIUM:
            self.warning(main_message)
        else:
            self.info(main_message)
        
        # Log cause if present
        if self.cause:
            cause_message = (
                f"    ↳ [yellow]Caused by[/yellow]: "
                f"[red]{self.cause.__class__.__name__}[/red]: {str(self.cause)}"
            )
            self.error(cause_message)
        
        # Log additional context if available
        if self.error_context.additional_data:
            context_items = []
            for key, value in self.error_context.additional_data.items():
                context_items.append(f"{key}={value}")
            
            if context_items:
                context_message = f"    ↳ [blue]Context[/blue]: {', '.join(context_items)}"
                self.info(context_message)
    
    def __str__(self) -> str:
        """
        Return a formatted string representation of the error.
        
        Returns:
            Formatted error string with ID, code, and message
        """
        error_str = f"{self.error_code} {self.error_id} - {self.message}"
        if self.cause:
            error_str += f"\n    ↳ Caused by: {self.cause.__class__.__name__}: {str(self.cause)}"
        return error_str
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert error to dictionary representation for serialization.
        
        Returns:
            Dictionary containing all error information
        """
        return {
            'error_id': self.error_id,
            'error_code': self.error_code,
            'exception_class': self.__class__.__name__,
            'message': self.message,
            'severity': self.severity.value,
            'category': self.category.value,
            'cause': {
                'class': self.cause.__class__.__name__,
                'message': str(self.cause)
            } if self.cause else None,
            'context': self.error_context.to_dict()
        }


class NodeNotFoundError(EasyRemoteError):
    """
    Exception raised when a specified node cannot be found in the system.
    
    This error occurs when attempting to access or connect to a node that
    doesn't exist in the current node registry or network topology.
    """
    
    def __init__(
        self, 
        node_id: str, 
        available_nodes: Optional[List[str]] = None,
        registry_source: Optional[str] = None,
        message: Optional[str] = None
    ):
        """
        Initialize NodeNotFoundError with node-specific information.
        
        Args:
            node_id: The identifier of the node that could not be found
            available_nodes: List of currently available nodes (for context)
            registry_source: Source of the node registry being searched
        """
        if message is None:
            message = f"Node '{node_id}' not found in the system"
        
        # Prepare additional context
        additional_data = {'node_id': node_id}
        if available_nodes is not None:
            additional_data['available_nodes'] = available_nodes
            additional_data['available_count'] = len(available_nodes)
        if registry_source:
            additional_data['registry_source'] = registry_source
        
        super().__init__(message, additional_data=additional_data)
        
        # Additional logging for debugging
        if available_nodes:
            self.info(f"    ↳ [cyan]Available nodes[/cyan]: {', '.join(available_nodes[:5])}")
            if len(available_nodes) > 5:
                self.info(f"    ↳ [cyan]...and {len(available_nodes) - 5} more[/cyan]")


class FunctionNotFoundError(EasyRemoteError):
    """
    Exception raised when a requested function is not available on the target node.
    
    This error occurs when attempting to call a function that doesn't exist
    or is not exposed on the specified node.
    """
    
    def __init__(
        self, 
        function_name: str, 
        node_id: Optional[str] = None,
        available_functions: Optional[List[str]] = None,
        message: Optional[str] = None
    ):
        """
        Initialize FunctionNotFoundError with function-specific information.
        
        Args:
            function_name: Name of the function that could not be found
            node_id: ID of the node where the function was searched
            available_functions: List of functions available on the node
        """
        if message is None:
            if node_id:
                message = f"Function '{function_name}' not found on node '{node_id}'"
            else:
                message = f"Function '{function_name}' not found in the system"
        
        # Prepare additional context
        additional_data = {'function_name': function_name}
        if node_id:
            additional_data['node_id'] = node_id
        if available_functions is not None:
            additional_data['available_functions'] = available_functions
            additional_data['available_count'] = len(available_functions)
        
        super().__init__(message, additional_data=additional_data)
        
        # Additional logging for debugging
        if available_functions:
            self.info(f"    ↳ [cyan]Available functions[/cyan]: {', '.join(available_functions[:3])}")
            if len(available_functions) > 3:
                self.info(f"    ↳ [cyan]...and {len(available_functions) - 3} more[/cyan]")


class ConnectionError(EasyRemoteError):
    """
    Exception raised when connection to a remote node fails.
    
    This error encompasses various connection-related issues including
    network timeouts, refused connections, and authentication failures.
    """
    
    def __init__(
        self, 
        message: str,
        address: Optional[str] = None, 
        port: Optional[int] = None,
        timeout: Optional[float] = None,
        cause: Optional[Exception] = None
    ):
        """
        Initialize ConnectionError with connection-specific information.
        
        Args:
            message: The error message to display
            address: The address that failed to connect
            port: The port number (if applicable)
            timeout: Connection timeout value used
            cause: The underlying network exception
        """
        # Don't overwrite the passed message
        # If no specific message provided, create a default one
        if not message and address:
            if port:
                full_address = f"{address}:{port}"
            else:
                full_address = address
            message = f"Failed to connect to {full_address}"
        
        # Prepare additional context
        additional_data = {'address': address}
        if port:
            additional_data['port'] = port
        if timeout:
            additional_data['timeout'] = timeout
        
        super().__init__(message, cause=cause, additional_data=additional_data)
        
        # Additional logging for debugging
        if timeout:
            self.info(f"    ↳ [cyan]Connection timeout[/cyan]: {timeout}s")


class SerializationError(EasyRemoteError):
    """
    Exception raised when data serialization or deserialization fails.
    
    This error occurs when converting data to/from formats for network
    transmission or storage, typically involving JSON, pickle, or other
    serialization formats.
    """
    
    def __init__(
        self, 
        operation: str,
        message: Optional[str] = None,
        data_type: Optional[str] = None,
        serialization_format: Optional[str] = None,
        cause: Optional[Exception] = None
    ):
        """
        Initialize SerializationError with serialization-specific information.
        
        Args:
            operation: The operation that failed ('serialize' or 'deserialize')
            data_type: Type of data being processed
            serialization_format: Format being used (e.g., 'json', 'pickle')
            cause: The underlying serialization exception
        """
        if message is None:
            message = f"Serialization failed during {operation}"
        
        # Prepare additional context
        additional_data = {'operation': operation}
        if data_type:
            additional_data['data_type'] = data_type
        if serialization_format:
            additional_data['serialization_format'] = serialization_format
        
        super().__init__(message, cause=cause, additional_data=additional_data)
        
        # Additional logging for debugging
        self.info(f"    ↳ [cyan]Operation[/cyan]: {operation.capitalize()}")
        if serialization_format:
            self.info(f"    ↳ [cyan]Format[/cyan]: {serialization_format}")


class RemoteExecutionError(EasyRemoteError):
    """
    Exception raised when remote function execution fails.
    
    This error occurs when a function executes on a remote node but
    encounters an error during execution, including runtime errors,
    resource limitations, or permission issues.
    """
    
    def __init__(
        self,
        function_name: str,
        node_id: Optional[str] = None,
        message: Optional[str] = None,
        execution_time: Optional[float] = None,
        return_code: Optional[int] = None,
        cause: Optional[Exception] = None
    ):
        """
        Initialize RemoteExecutionError with execution-specific information.
        
        Args:
            function_name: Name of the function that failed
            node_id: ID of the node where execution failed
            execution_time: How long the function ran before failing
            return_code: Exit code from the remote execution
            cause: The underlying execution exception
        """
        if message is None:
            if node_id:
                message = f"Remote execution failed for function '{function_name}' on node '{node_id}'"
            else:
                message = f"Remote execution failed for function '{function_name}'"
        
        # Prepare additional context
        additional_data = {'function_name': function_name}
        if node_id:
            additional_data['node_id'] = node_id
        if execution_time is not None:
            additional_data['execution_time'] = execution_time
        if return_code is not None:
            additional_data['return_code'] = return_code
        
        super().__init__(message, cause=cause, additional_data=additional_data)
        
        # Additional logging for debugging
        if execution_time is not None:
            self.info(f"    ↳ [cyan]Execution time[/cyan]: {execution_time:.2f}s")


class NoAvailableNodesError(EasyRemoteError):
    """
    Exception raised when no nodes are available to handle a request.
    
    This error occurs when the load balancer cannot find any suitable
    nodes to execute a function, either due to all nodes being offline,
    overloaded, or not meeting the requirements.
    """
    
    def __init__(
        self,
        message: str,
        function_name: Optional[str] = None,
        requirements: Optional[Dict[str, Any]] = None,
        total_nodes: Optional[int] = None,
        healthy_nodes: Optional[int] = None,
        cause: Optional[Exception] = None
    ):
        """
        Initialize NoAvailableNodesError with load balancing context.
        
        Args:
            message: Error message
            function_name: Name of the function that couldn't be executed
            requirements: Requirements that couldn't be met
            total_nodes: Total number of nodes in the system
            healthy_nodes: Number of healthy nodes available
            cause: The underlying exception
        """
        # Prepare additional context
        additional_data = {}
        if function_name:
            additional_data['function_name'] = function_name
        if requirements:
            additional_data['requirements'] = requirements
        if total_nodes is not None:
            additional_data['total_nodes'] = total_nodes
        if healthy_nodes is not None:
            additional_data['healthy_nodes'] = healthy_nodes
        
        super().__init__(message, cause=cause, additional_data=additional_data)
        
        # Additional logging for debugging
        if total_nodes is not None and healthy_nodes is not None:
            self.info(f"    ↳ [cyan]Node status[/cyan]: {healthy_nodes}/{total_nodes} healthy")
        if requirements:
            req_str = ", ".join(f"{k}={v}" for k, v in requirements.items())
            self.info(f"    ↳ [cyan]Requirements[/cyan]: {req_str}")


class LoadBalancingError(EasyRemoteError):
    """
    Exception raised when load balancing operations fail.
    
    This error occurs when the load balancer encounters issues in
    routing requests, selecting nodes, or managing load distribution.
    """
    
    def __init__(
        self,
        message: str,
        strategy: Optional[str] = None,
        available_nodes: Optional[int] = None,
        cause: Optional[Exception] = None
    ):
        """
        Initialize LoadBalancingError with load balancing context.
        
        Args:
            message: Error message
            strategy: Load balancing strategy being used
            available_nodes: Number of nodes available for load balancing
            cause: The underlying exception
        """
        # Prepare additional context
        additional_data = {}
        if strategy:
            additional_data['strategy'] = strategy
        if available_nodes is not None:
            additional_data['available_nodes'] = available_nodes
        
        super().__init__(message, cause=cause, additional_data=additional_data)
        
        # Additional logging for debugging
        if strategy:
            self.info(f"    ↳ [cyan]Strategy[/cyan]: {strategy}")
        if available_nodes is not None:
            self.info(f"    ↳ [cyan]Available nodes[/cyan]: {available_nodes}")


class TimeoutError(EasyRemoteError):
    """
    Exception raised when operations exceed their timeout limit.
    
    This error occurs when an operation takes longer than the specified
    timeout duration, helping prevent indefinite blocking.
    """
    
    def __init__(
        self,
        message: str,
        timeout_seconds: Optional[float] = None,
        operation: Optional[str] = None,
        cause: Optional[Exception] = None
    ):
        """
        Initialize TimeoutError with timeout-specific information.
        
        Args:
            message: Error message
            timeout_seconds: The timeout value that was exceeded
            operation: Name of the operation that timed out
            cause: The underlying exception
        """
        # Prepare additional context
        additional_data = {}
        if timeout_seconds is not None:
            additional_data['timeout_seconds'] = timeout_seconds
        if operation:
            additional_data['operation'] = operation
        
        super().__init__(message, cause=cause, additional_data=additional_data)
        
        # Additional logging for debugging
        if timeout_seconds is not None:
            self.info(f"    ↳ [cyan]Timeout[/cyan]: {timeout_seconds}s")
        if operation:
            self.info(f"    ↳ [cyan]Operation[/cyan]: {operation}")


class ConcurrencyBoundaryError(EasyRemoteError):
    """
    Exception raised when async/thread concurrency boundaries are violated.

    Typical causes:
    - Accessing an event-loop-bound resource from another loop
    - Attempting cross-loop reuse of lock/future objects
    """

    def __init__(
        self,
        message: str,
        resource_name: Optional[str] = None,
        bound_loop_id: Optional[str] = None,
        current_loop_id: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        additional_data: Dict[str, Any] = {}
        if resource_name:
            additional_data["resource_name"] = resource_name
        if bound_loop_id:
            additional_data["bound_loop_id"] = bound_loop_id
        if current_loop_id:
            additional_data["current_loop_id"] = current_loop_id

        super().__init__(message, cause=cause, additional_data=additional_data)


class ProtocolHandlingError(EasyRemoteError):
    """
    Exception raised for protocol parsing/handling failures.
    """

    def __init__(
        self,
        message: str,
        protocol: Optional[str] = None,
        method: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        additional_data: Dict[str, Any] = {}
        if protocol:
            additional_data["protocol"] = protocol
        if method:
            additional_data["method"] = method
        super().__init__(message, cause=cause, additional_data=additional_data)


class ExceptionTranslator:
    """
    Translate generic exceptions into layered EasyRemote exceptions.
    """

    @staticmethod
    def as_serialization_error(
        exc: Exception,
        operation: str,
        message: Optional[str] = None,
    ) -> SerializationError:
        if isinstance(exc, SerializationError):
            return exc
        return SerializationError(
            operation=operation,
            message=message or f"Serialization failure during {operation}: {exc}",
            cause=exc,
        )

    @staticmethod
    def as_remote_execution_error(
        exc: Exception,
        function_name: str,
        node_id: Optional[str] = None,
        message: Optional[str] = None,
    ) -> RemoteExecutionError:
        if isinstance(exc, RemoteExecutionError):
            return exc
        return RemoteExecutionError(
            function_name=function_name,
            node_id=node_id,
            message=message or f"Remote execution failed: {exc}",
            cause=exc,
        )

    @staticmethod
    def as_load_balancing_error(
        exc: Exception,
        strategy: Optional[str] = None,
        message: Optional[str] = None,
    ) -> LoadBalancingError:
        if isinstance(exc, LoadBalancingError):
            return exc
        return LoadBalancingError(
            message=message or f"Load balancing failed: {exc}",
            strategy=strategy,
            cause=exc,
        )

    @staticmethod
    def as_connection_error(
        exc: Exception,
        address: Optional[str] = None,
        message: Optional[str] = None,
    ) -> ConnectionError:
        if isinstance(exc, ConnectionError):
            return exc
        return ConnectionError(
            message=message or f"Connection failure: {exc}",
            address=address,
            cause=exc,
        )

    @staticmethod
    def as_protocol_error(
        exc: Exception,
        protocol: Optional[str] = None,
        method: Optional[str] = None,
        message: Optional[str] = None,
    ) -> ProtocolHandlingError:
        if isinstance(exc, ProtocolHandlingError):
            return exc
        return ProtocolHandlingError(
            message=message or f"Protocol handling failed: {exc}",
            protocol=protocol,
            method=method,
            cause=exc,
        )


class ExceptionFormatter:
    """
    Utility class for formatting exception information in various formats.
    
    This class provides standardized methods for converting exceptions
    into different output formats for logging, reporting, and debugging.
    """
    
    @staticmethod
    def format_exception(exception: Exception) -> str:
        """
        Format any exception into a standardized string representation.
        
        Args:
            exception: The exception to format
            
        Returns:
            Formatted string representation of the exception
        """
        if isinstance(exception, EasyRemoteError):
            return str(exception)
        return f"{exception.__class__.__name__}: {str(exception)}"
    
    @staticmethod
    def format_exception_chain(exception: Exception) -> str:
        """
        Format an exception with its complete cause chain.
        
        Args:
            exception: The exception to format
            
        Returns:
            Formatted string showing the complete exception chain
        """
        lines = []
        current = exception
        
        while current:
            if isinstance(current, EasyRemoteError):
                lines.append(f"🔴 {current}")
                current = current.cause
            else:
                lines.append(f"🔴 {current.__class__.__name__}: {str(current)}")
                current = getattr(current, '__cause__', None)
        
        return '\n'.join(lines)
    
    @staticmethod
    def format_exception_summary(exception: Exception) -> Dict[str, Any]:
        """
        Create a summary dictionary of exception information.
        
        Args:
            exception: The exception to summarize
            
        Returns:
            Dictionary containing exception summary information
        """
        if isinstance(exception, EasyRemoteError):
            return exception.to_dict()
        
        return {
            'exception_class': exception.__class__.__name__,
            'message': str(exception),
            'severity': ErrorSeverity.MEDIUM.value,
            'category': ErrorCategory.SYSTEM.value,
            'error_id': 'UNKNOWN',
            'error_code': 'E999'
        }
