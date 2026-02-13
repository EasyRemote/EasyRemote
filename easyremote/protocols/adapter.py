#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Protocol adapter abstractions for EasyRemote.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Mapping, Optional, Tuple

from ..core.utils.exceptions import ExceptionTranslator
from .models import ProtocolName
from .runtime import ProtocolRuntime


class ProtocolAdapter(ABC):
    """
    Base contract for protocol adapters.
    """

    @property
    @abstractmethod
    def protocol(self) -> ProtocolName:
        """
        Protocol type implemented by this adapter.
        """

    @abstractmethod
    async def handle_request(
        self, payload: Mapping[str, Any], runtime: ProtocolRuntime
    ) -> Optional[Dict[str, Any]]:
        """
        Handle one protocol request and return protocol-specific response payload.
        """


class JsonRpcProtocolError(ValueError):
    """
    Base JSON-RPC validation error with protocol-specific error code.
    """

    code = -32000


class InvalidRequestError(JsonRpcProtocolError):
    """
    JSON-RPC invalid request error (-32600).
    """

    code = -32600


class InvalidParamsError(JsonRpcProtocolError):
    """
    JSON-RPC invalid params error (-32602).
    """

    code = -32602


class JsonRpcProtocolAdapter(ProtocolAdapter):
    """
    Shared JSON-RPC adapter utility for MCP/A2A protocol implementations.
    """

    JSON_RPC_VERSION = "2.0"
    supports_batch_requests = True

    @classmethod
    def resolve_error_code(cls, exc: Exception) -> int:
        """
        Map framework/runtime exceptions to JSON-RPC error codes.
        """
        if isinstance(exc, JsonRpcProtocolError):
            return exc.code
        if isinstance(exc, ValueError):
            return -32602
        return -32000

    @staticmethod
    def standard_error_data(
        protocol: str, method: Optional[str], error_type: str
    ) -> Dict[str, Any]:
        """
        Build a normalized JSON-RPC error.data payload.
        """
        return {
            "protocol": protocol,
            "method": method,
            "error_type": error_type,
        }

    def _parse_jsonrpc_request(
        self, payload: Mapping[str, Any]
    ) -> Tuple[Any, str, Dict[str, Any], bool]:
        if not isinstance(payload, Mapping):
            raise InvalidRequestError("JSON-RPC payload must be an object")

        request = dict(payload)
        version = request.get("jsonrpc")
        if version != self.JSON_RPC_VERSION:
            raise InvalidRequestError(
                "Unsupported jsonrpc version: {0}".format(version)
            )

        method = request.get("method")
        if not isinstance(method, str) or not method.strip():
            raise InvalidRequestError("JSON-RPC method must be a non-empty string")

        params_raw = request.get("params", {})
        if params_raw is None:
            params: Dict[str, Any] = {}
        elif isinstance(params_raw, Mapping):
            params = dict(params_raw)
        else:
            raise InvalidRequestError("JSON-RPC params must be an object")

        is_notification = "id" not in request
        return request.get("id"), method.strip(), params, is_notification

    def _success(self, request_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "jsonrpc": self.JSON_RPC_VERSION,
            "id": request_id,
            "result": result,
        }

    def _error(
        self,
        request_id: Any,
        code: int,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        error_obj: Dict[str, Any] = {
            "code": code,
            "message": message,
        }
        if data:
            error_obj["data"] = data

        return {
            "jsonrpc": self.JSON_RPC_VERSION,
            "id": request_id,
            "error": error_obj,
        }

    def method_not_found(
        self, request_id: Any, protocol: str, method: str, message: str
    ) -> Dict[str, Any]:
        """
        Build a standardized method-not-found response.
        """
        return self._error(
            request_id=request_id,
            code=-32601,
            message=message,
            data=self.standard_error_data(
                protocol=protocol,
                method=method or None,
                error_type="MethodNotFound",
            ),
        )

    def error_from_exception(
        self,
        request_id: Any,
        exc: Exception,
        protocol: str,
        method: Optional[str],
    ) -> Dict[str, Any]:
        """
        Build a standardized JSON-RPC error from runtime/validation exceptions.
        """
        translated = ExceptionTranslator.as_protocol_error(
            exc=exc,
            protocol=protocol,
            method=method,
        )
        return self._error(
            request_id=request_id,
            code=self.resolve_error_code(exc),
            message=translated.message,
            data=self.standard_error_data(
                protocol=protocol,
                method=method,
                error_type=exc.__class__.__name__,
            ),
        )
