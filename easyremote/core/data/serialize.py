import threading
from typing import Tuple, Dict, Any, Optional, Callable
from .config import SerializationConfig, SerializationProtocol
from .backends import SerializationBackend, PickleBackend, JSONBackend
from .analysis import FunctionAnalysis, analyze_function
from ..utils.exceptions import SerializationError
from ..utils.logger import ModernLogger


class Serializer(ModernLogger):
    """
    Advanced serialization utility with support for multiple backends,
    configuration options, and comprehensive error handling.
    """
    
    def __init__(self, config: Optional[SerializationConfig] = None):
        """
        Initialize the serializer with configuration.
        
        Args:
            config: Serialization configuration. Uses defaults if None.
        """
        super().__init__(name="Serializer")
        self.config = config or SerializationConfig()
        self._backend = self._create_backend()
        self._analysis_cache: Dict[str, FunctionAnalysis] = {}
    
    def _create_backend(self) -> SerializationBackend:
        """Create the appropriate serialization backend based on configuration"""
        if self.config.protocol == SerializationProtocol.PICKLE_V4:
            return PickleBackend(
                protocol=4, 
                safe_mode=self.config.safe_mode, 
                compress=self.config.compress,
                compression_algorithm=self.config.compression_algorithm,
                compression_level=self.config.compression_level
            )
        elif self.config.protocol == SerializationProtocol.PICKLE_V5:
            return PickleBackend(
                protocol=5, 
                safe_mode=self.config.safe_mode, 
                compress=self.config.compress,
                compression_algorithm=self.config.compression_algorithm,
                compression_level=self.config.compression_level
            )
        elif self.config.protocol == SerializationProtocol.JSON:
            return JSONBackend()
        else:
            raise ValueError(f"Unsupported serialization protocol: {self.config.protocol}")
    
    def _validate_size(self, data: bytes, operation: str) -> None:
        """Validate serialized data size against configuration limits"""
        if self.config.max_size and len(data) > self.config.max_size:
            raise SerializationError(
                f"{operation} size ({len(data)} bytes) exceeds limit ({self.config.max_size} bytes)"
            )
    
    def serialize_args(self, *args, **kwargs) -> Tuple[bytes, bytes]:
        """
        Serialize function arguments and keyword arguments.
        
        Args:
            *args: Positional arguments to serialize
            **kwargs: Keyword arguments to serialize
            
        Returns:
            Tuple of (serialized_args, serialized_kwargs)
            
        Raises:
            SerializationError: If serialization fails
        """
        try:
            self.debug(f"Serializing {len(args)} args and {len(kwargs)} kwargs")
            
            args_bytes = self._backend.serialize(args) if args else b''
            kwargs_bytes = self._backend.serialize(kwargs) if kwargs else b''
            
            self._validate_size(args_bytes, "Arguments serialization")
            self._validate_size(kwargs_bytes, "Keyword arguments serialization")
            
            return args_bytes, kwargs_bytes
            
        except Exception as e:
            self.error(f"Failed to serialize arguments: {e}")
            raise SerializationError(
                operation="serialize_args",
                message="Failed to serialize function arguments",
                cause=e
            ) from e
    
    def deserialize_args(self, args_bytes: bytes, kwargs_bytes: bytes) -> Tuple[tuple, dict]:
        """
        Deserialize function arguments and keyword arguments.
        
        Args:
            args_bytes: Serialized positional arguments
            kwargs_bytes: Serialized keyword arguments
            
        Returns:
            Tuple of (args, kwargs)
            
        Raises:
            SerializationError: If deserialization fails
        """
        try:
            self.debug("Deserializing function arguments")
            
            args = self._backend.deserialize(args_bytes) if args_bytes else ()
            kwargs = self._backend.deserialize(kwargs_bytes) if kwargs_bytes else {}
            
            # Ensure we return the correct types
            if not isinstance(args, tuple):
                args = tuple(args) if args else ()
            if not isinstance(kwargs, dict):
                kwargs = {}
            
            self.debug(f"Deserialized {len(args)} args and {len(kwargs)} kwargs")
            return args, kwargs
            
        except Exception as e:
            self.error(f"Failed to deserialize arguments: {e}")
            raise SerializationError(
                operation="deserialize_args",
                message="Failed to deserialize function arguments",
                cause=e
            ) from e
    
    def serialize_result(self, result: Any) -> bytes:
        """
        Serialize function execution result.
        
        Args:
            result: The result to serialize
            
        Returns:
            Serialized result as bytes
            
        Raises:
            SerializationError: If serialization fails
        """
        try:
            if result is None:
                self.debug("Serializing None result")
                return b''
            
            self.debug(f"Serializing result of type {type(result).__name__}")
            result_bytes = self._backend.serialize(result)
            
            self._validate_size(result_bytes, "Result serialization")
            
            return result_bytes
            
        except Exception as e:
            self.error(f"Serialization failed for type {type(result).__name__}: {e}")
            raise SerializationError(
                operation="serialize_result",
                message=f"Failed to serialize result of type {type(result).__name__}",
                cause=e
            ) from e
    
    def deserialize_result(self, result_bytes: bytes) -> Any:
        """
        Deserialize function execution result.
        
        Args:
            result_bytes: Serialized result bytes
            
        Returns:
            Deserialized result
            
        Raises:
            SerializationError: If deserialization fails
        """
        if not result_bytes:
            self.debug("Deserializing empty result (None)")
            return None
        
        try:
            self.debug(f"Deserializing result from {len(result_bytes)} bytes")
            return self._backend.deserialize(result_bytes)
            
        except Exception as e:
            self.error(f"Failed to deserialize result: {e}")
            raise SerializationError(
                operation="deserialize_result",
                message="Failed to deserialize execution result",
                cause=e
            ) from e
    
    def analyze_function(self, func: Callable, use_cache: bool = True) -> FunctionAnalysis:
        """
        Analyze function characteristics for execution planning.
        
        Args:
            func: Function or callable to analyze
            use_cache: Whether to use cached analysis results
            
        Returns:
            FunctionAnalysis object with function characteristics
        """
        cache = self._analysis_cache if use_cache else None
        analysis = analyze_function(func, cache)
        
        # Create cache key for logging
        cache_key = f"{func.__module__}.{func.__name__}" if hasattr(func, '__module__') else str(func)
        
        self.debug(f"Analyzed function {cache_key}: async={analysis.is_async}, "
                  f"generator={analysis.is_generator}, class={analysis.is_class}")
        
        return analysis
    
    def clear_cache(self) -> None:
        """Clear the function analysis cache"""
        self._analysis_cache.clear()
        self.debug("Cleared function analysis cache")
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get statistics about the function analysis cache"""
        return {"cached_functions": len(self._analysis_cache)}


_DEFAULT_SERIALIZER: Optional[Serializer] = None
_DEFAULT_SERIALIZER_LOCK = threading.Lock()


def _get_default_serializer() -> Serializer:
    """Get a lazily initialized process-wide serializer instance."""
    global _DEFAULT_SERIALIZER
    if _DEFAULT_SERIALIZER is None:
        with _DEFAULT_SERIALIZER_LOCK:
            if _DEFAULT_SERIALIZER is None:
                _DEFAULT_SERIALIZER = Serializer()
    return _DEFAULT_SERIALIZER


# Convenience functions for backward compatibility
def serialize_result(result: Any) -> bytes:
    """Serialize function execution result using default serializer."""
    return _get_default_serializer().serialize_result(result)


def deserialize_result(result_bytes: bytes) -> Any:
    """Deserialize function execution result using default serializer."""
    return _get_default_serializer().deserialize_result(result_bytes)


def serialize_args(*args, **kwargs) -> Tuple[bytes, bytes]:
    """Serialize function arguments using default serializer."""
    return _get_default_serializer().serialize_args(*args, **kwargs)


def deserialize_args(args_bytes: bytes, kwargs_bytes: bytes) -> Tuple[tuple, dict]:
    """Deserialize function arguments using default serializer."""
    return _get_default_serializer().deserialize_args(args_bytes, kwargs_bytes)
