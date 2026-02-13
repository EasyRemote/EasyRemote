#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Basic compute node for quick start.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from easyremote import ComputeNode  # noqa: E402


class BasicMathNode:
    """
    Registers basic business functions and serves remote calls.
    """

    def __init__(self, gateway_address: str, node_id: str) -> None:
        self._node = ComputeNode(gateway_address=gateway_address, node_id=node_id)
        self._register_functions()

    def _register_functions(self) -> None:
        @self._node.register(name="add_numbers", description="Add two integers")
        def add_numbers(a: int, b: int) -> int:
            return a + b

        @self._node.register(
            name="process_payload",
            description="Double all numeric values in a payload",
        )
        def process_payload(payload: dict[str, int]) -> dict[str, int]:
            return {key: value * 2 for key, value in payload.items()}

    def serve(self) -> None:
        self._node.serve()


if __name__ == "__main__":
    gateway_address = os.getenv("EASYREMOTE_GATEWAY_ADDRESS", "127.0.0.1:8080")
    BasicMathNode(
        gateway_address=gateway_address,
        node_id="basic-compute",
    ).serve()
