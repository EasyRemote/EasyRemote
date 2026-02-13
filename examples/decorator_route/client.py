#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Client caller for the human-coded decorator route.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import os

from easyremote import remote

GATEWAY_ADDRESS = os.getenv("EASYREMOTE_GATEWAY_ADDRESS", "127.0.0.1:8080")


@remote(
    function_name="add_numbers",
    node_id="math-node",
    gateway_address=GATEWAY_ADDRESS,
)
def add_numbers(a: int, b: int) -> int:
    # Local fallback for static analysis/debugging; @remote wrapper executes remotely.
    return a + b


@remote(
    function_name="multiply_numbers",
    load_balancing=True,
    gateway_address=GATEWAY_ADDRESS,
)
def multiply_numbers(a: int, b: int) -> int:
    # Local fallback for static analysis/debugging; @remote wrapper executes remotely.
    return a * b


class HumanDecoratorDemo:
    """
    Demonstrates direct-node and load-balanced function calls.
    """

    def run(self) -> None:
        add_result = add_numbers(12, 30)
        mul_result = multiply_numbers(7, 8)

        print(f"add_numbers -> {add_result}")
        print(f"multiply_numbers(load_balancing=True) -> {mul_result}")


if __name__ == "__main__":
    HumanDecoratorDemo().run()
