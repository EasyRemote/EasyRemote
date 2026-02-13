#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Compute node for the human-coded decorator route.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from easyremote import ComputeNode


class MathComputeNode:
    """
    Registers business functions and serves them to the gateway.
    """

    def __init__(self, gateway_address: str, node_id: str) -> None:
        self._node = ComputeNode(gateway_address=gateway_address, node_id=node_id)
        self._register_functions()

    def _register_functions(self) -> None:
        @self._node.register(
            name="add_numbers",
            description="Add two integers.",
            load_balancing=True,
        )
        def add_numbers(a: int, b: int) -> int:
            return a + b

        @self._node.register(
            name="multiply_numbers",
            description="Multiply two integers.",
            load_balancing=True,
        )
        def multiply_numbers(a: int, b: int) -> int:
            return a * b

    def serve(self) -> None:
        self._node.serve()


if __name__ == "__main__":
    MathComputeNode(
        gateway_address="127.0.0.1:8080",
        node_id="math-node",
    ).serve()
