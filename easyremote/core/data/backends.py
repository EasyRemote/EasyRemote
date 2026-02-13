import pickle
import json
import gzip
import zlib
from typing import Any, Dict, Protocol, runtime_checkable
from .config import CompressionAlgorithm
from ..utils.exceptions import SerializationError


@runtime_checkable
class SerializationBackend(Protocol):
    """Protocol defining the interface for serialization backends"""
    
    def serialize(self, obj: Any) -> bytes:
        """Serialize an object to bytes"""
        ...
    
    def deserialize(self, data: bytes) -> Any:
        """Deserialize bytes back to object"""
        ...


@runtime_checkable
class CompressionCodec(Protocol):
    """Protocol for compression/decompression strategies."""

    def compress(self, data: bytes, level: int) -> bytes:
        """Compress raw bytes."""
        ...

    def decompress(self, data: bytes) -> bytes:
        """Decompress raw bytes."""
        ...


class NoCompressionCodec:
    """No-op compression strategy."""

    def compress(self, data: bytes, level: int) -> bytes:
        return data

    def decompress(self, data: bytes) -> bytes:
        return data


class ZlibCompressionCodec:
    """Zlib compression strategy."""

    def compress(self, data: bytes, level: int) -> bytes:
        return zlib.compress(data, level=level)

    def decompress(self, data: bytes) -> bytes:
        return zlib.decompress(data)


class GzipCompressionCodec:
    """Gzip compression strategy."""

    def compress(self, data: bytes, level: int) -> bytes:
        return gzip.compress(data, compresslevel=level)

    def decompress(self, data: bytes) -> bytes:
        return gzip.decompress(data)


class CompressionCodecFactory:
    """Factory for compression codecs."""

    _CODEC_MAP: Dict[CompressionAlgorithm, CompressionCodec] = {
        CompressionAlgorithm.NONE: NoCompressionCodec(),
        CompressionAlgorithm.ZLIB: ZlibCompressionCodec(),
        CompressionAlgorithm.GZIP: GzipCompressionCodec(),
    }

    @classmethod
    def create(cls, algorithm: CompressionAlgorithm) -> CompressionCodec:
        return cls._CODEC_MAP.get(algorithm, NoCompressionCodec())


class PickleBackend:
    """Pickle-based serialization backend"""
    
    def __init__(self, protocol: int = 4, safe_mode: bool = True, compress: bool = False, 
                 compression_algorithm: CompressionAlgorithm = CompressionAlgorithm.ZLIB,
                 compression_level: int = 6):
        if protocol not in range(0, pickle.HIGHEST_PROTOCOL + 1):
            raise ValueError(
                f"Unsupported pickle protocol {protocol}. "
                f"Supported range: 0-{pickle.HIGHEST_PROTOCOL}"
            )
        if not 0 <= compression_level <= 9:
            raise ValueError("compression_level must be in the range 0-9")

        self.protocol = protocol
        self.safe_mode = safe_mode
        self.compress = compress
        self.compression_algorithm = compression_algorithm
        self.compression_level = compression_level
        self._compression_codec = CompressionCodecFactory.create(compression_algorithm)
    
    def _compress_data(self, data: bytes) -> bytes:
        """Compress data using the configured algorithm"""
        if not self.compress:
            return data
        return self._compression_codec.compress(data, self.compression_level)
    
    def _decompress_data(self, data: bytes) -> bytes:
        """Decompress data using the configured algorithm"""
        if not self.compress:
            return data
        return self._compression_codec.decompress(data)
    
    def serialize(self, obj: Any) -> bytes:
        """Serialize object using pickle"""
        try:
            data = pickle.dumps(obj, protocol=self.protocol)
            data = self._compress_data(data)
            return data
        except (pickle.PicklingError, TypeError, AttributeError) as e:
            raise SerializationError(
                operation="serialize",
                message=f"Pickle serialization failed: {e}",
                data_type=type(obj).__name__,
                serialization_format="pickle",
                cause=e,
            ) from e
    
    def deserialize(self, data: bytes) -> Any:
        """Deserialize bytes using pickle"""
        if not data:
            return None
        try:
            data = self._decompress_data(data)
            
            if self.safe_mode:
                # Perform safety checks before deserialization
                self._validate_pickle_data(data)
            return pickle.loads(data)
        except (pickle.UnpicklingError, EOFError, ValueError, zlib.error, OSError) as e:
            raise SerializationError(
                operation="deserialize",
                message=f"Pickle deserialization failed: {e}",
                serialization_format="pickle",
                cause=e,
            ) from e
    
    def _validate_pickle_data(self, data: bytes) -> None:
        """
        Validate pickle data for potential security risks.
        
        This is a basic implementation - in production, you might want
        to use more sophisticated security checks.
        """
        # Check for minimum data size (empty pickle is 4+ bytes)
        if len(data) < 4:
            raise SerializationError(
                operation="deserialize",
                message="Invalid pickle data: too short",
                serialization_format="pickle",
            )
        
        # Check for pickle protocol magic bytes
        if data[0] not in [0x80, 0x03, 0x02, 0x01, 0x00]:  # Valid pickle protocols
            raise SerializationError(
                operation="deserialize",
                message="Invalid pickle data: bad magic bytes",
                serialization_format="pickle",
            )
        
        # Check for maximum reasonable size (1GB default)
        max_size = 1024 * 1024 * 1024  # 1GB
        if len(data) > max_size:
            raise SerializationError(
                operation="deserialize",
                message=f"Pickle data too large: {len(data)} bytes",
                serialization_format="pickle",
            )
        
        # You could add more checks here:
        # - Scan for dangerous opcodes
        # - Check for suspicious module imports
        # - Validate against whitelist of allowed types


class JSONBackend:
    """JSON-based serialization backend with extended type support"""
    
    def __init__(self):
        self.supported_types = {
            'tuple': lambda x: {'__type__': 'tuple', 'data': list(x)},
            'set': lambda x: {'__type__': 'set', 'data': list(x)},
            'complex': lambda x: {'__type__': 'complex', 'real': x.real, 'imag': x.imag},
            'bytes': lambda x: {'__type__': 'bytes', 'data': x.decode('latin-1')},
        }
    
    def _custom_encoder(self, obj: Any) -> Any:
        """Custom encoder for non-JSON-native types"""
        if isinstance(obj, tuple):
            return self.supported_types['tuple'](obj)
        elif isinstance(obj, set):
            return self.supported_types['set'](obj)
        elif isinstance(obj, complex):
            return self.supported_types['complex'](obj)
        elif isinstance(obj, bytes):
            return self.supported_types['bytes'](obj)
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    def _encode_recursive(self, obj: Any) -> Any:
        """
        Recursively encode values so extended types are preserved.

        `json.dumps(..., default=...)` does not call `default` for tuples because
        tuples are natively converted to JSON arrays. We pre-encode recursively to
        preserve tuple identity.
        """
        if isinstance(obj, dict):
            return {k: self._encode_recursive(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._encode_recursive(item) for item in obj]
        if isinstance(obj, tuple):
            return {"__type__": "tuple", "data": [self._encode_recursive(i) for i in obj]}
        if isinstance(obj, set):
            return {"__type__": "set", "data": [self._encode_recursive(i) for i in obj]}
        if isinstance(obj, complex):
            return {"__type__": "complex", "real": obj.real, "imag": obj.imag}
        if isinstance(obj, bytes):
            return {"__type__": "bytes", "data": obj.decode("latin-1")}
        return obj
    
    def _custom_decoder(self, obj: Any) -> Any:
        """Custom decoder for non-JSON-native types"""
        if isinstance(obj, dict) and '__type__' in obj:
            type_name = obj['__type__']
            if type_name == 'tuple':
                return tuple(obj['data'])
            elif type_name == 'set':
                return set(obj['data'])
            elif type_name == 'complex':
                return complex(obj['real'], obj['imag'])
            elif type_name == 'bytes':
                return obj['data'].encode('latin-1')
        return obj
    
    def serialize(self, obj: Any) -> bytes:
        """Serialize object using JSON with extended type support"""
        try:
            encoded_obj = self._encode_recursive(obj)
            json_str = json.dumps(encoded_obj, ensure_ascii=False, default=self._custom_encoder)
            return json_str.encode('utf-8')
        except (TypeError, ValueError) as e:
            raise SerializationError(
                operation="serialize",
                message=f"JSON serialization failed: {e}",
                data_type=type(obj).__name__,
                serialization_format="json",
                cause=e,
            ) from e
    
    def deserialize(self, data: bytes) -> Any:
        """Deserialize bytes using JSON with extended type support"""
        if not data:
            return None
        try:
            decoded_str = data.decode('utf-8')
            obj = json.loads(decoded_str)
            return self._decode_recursive(obj)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise SerializationError(
                operation="deserialize",
                message=f"JSON deserialization failed: {e}",
                serialization_format="json",
                cause=e,
            ) from e
    
    def _decode_recursive(self, obj: Any) -> Any:
        """Recursively decode custom types"""
        if isinstance(obj, dict):
            # First check if it's a custom type marker
            decoded = self._custom_decoder(obj)
            if decoded is not obj:  # It was a custom type
                return decoded
            # Otherwise decode all values in the dict
            return {k: self._decode_recursive(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._decode_recursive(item) for item in obj]
        return obj 
