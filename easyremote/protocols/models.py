#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Protocol domain models for EasyRemote.

This module defines protocol-agnostic data structures used by protocol adapters
such as MCP and A2A.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union


class ProtocolName(str, Enum):
    """
    Supported external protocol names.
    """

    MCP = "mcp"
    A2A = "a2a"

    @classmethod
    def from_value(cls, value: Union["ProtocolName", str]) -> "ProtocolName":
        """
        Parse protocol name from enum/string.
        """
        if isinstance(value, cls):
            return value
        return cls(str(value).strip().lower())


@dataclass
class FunctionDescriptor:
    """
    Lightweight function description exposed to protocol adapters.
    """

    name: str
    description: str = ""
    node_ids: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FunctionInvocation:
    """
    Normalized function invocation command used by protocol adapters.
    """

    function_name: str
    args: Tuple[Any, ...] = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    node_id: Optional[str] = None
    load_balancing: Union[bool, str, Dict[str, Any]] = False
    stream: bool = False

    @staticmethod
    def _normalize_arguments_envelope(
        arguments: Mapping[str, Any]
    ) -> Tuple[Tuple[Any, ...], Dict[str, Any]]:
        args_key = "__args__" if "__args__" in arguments else "args"
        kwargs_key = "__kwargs__" if "__kwargs__" in arguments else "kwargs"

        raw_args: Sequence[Any] = arguments.get(args_key, ()) or ()
        raw_kwargs = arguments.get(kwargs_key, {}) or {}

        if not isinstance(raw_args, (list, tuple)):
            raise ValueError(f"{args_key} must be a list/tuple")
        if not isinstance(raw_kwargs, Mapping):
            raise ValueError(f"{kwargs_key} must be an object")

        return tuple(raw_args), dict(raw_kwargs)

    @staticmethod
    def _normalize_load_balancing(
        load_balancing: Union[bool, str, Dict[str, Any]]
    ) -> Union[bool, str, Dict[str, Any]]:
        if isinstance(load_balancing, (bool, str, dict)):
            return load_balancing
        raise ValueError("load_balancing must be bool, str or object")

    @classmethod
    def from_arguments(
        cls,
        function_name: str,
        arguments: Any = None,
        node_id: Optional[str] = None,
        load_balancing: Union[bool, str, Dict[str, Any]] = False,
        stream: bool = False,
    ) -> "FunctionInvocation":
        """
        Build invocation from flexible argument payload.

        Accepted argument formats:
        - dict: treated as kwargs by default
        - dict with "__args__"/"__kwargs__": explicit split
        - list/tuple: treated as positional args
        - scalar: treated as a single positional arg
        - None: no args
        """
        args = ()
        kwargs: Dict[str, Any] = {}

        if arguments is None:
            args = ()
            kwargs = {}
        elif isinstance(arguments, Mapping):
            if (
                "__args__" in arguments
                or "__kwargs__" in arguments
                or "args" in arguments
                or "kwargs" in arguments
            ):
                args, kwargs = cls._normalize_arguments_envelope(arguments)
            else:
                kwargs = dict(arguments)
        elif isinstance(arguments, (list, tuple)):
            args = tuple(arguments)
        else:
            args = (arguments,)

        return cls(
            function_name=function_name,
            args=args,
            kwargs=kwargs,
            node_id=node_id,
            load_balancing=cls._normalize_load_balancing(load_balancing),
            stream=bool(stream),
        )
