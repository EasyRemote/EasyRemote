#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Basic client for quick start.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from easyremote import remote  # noqa: E402

GATEWAY_ADDRESS = os.getenv("EASYREMOTE_GATEWAY_ADDRESS", "127.0.0.1:8080")


@remote(
    function_name="add_numbers",
    node_id="basic-compute",
    gateway_address=GATEWAY_ADDRESS,
)
def add_numbers(a: int, b: int) -> int:
    # Local fallback for static analysis/debugging; @remote wrapper executes remotely.
    return a + b


@remote(
    function_name="process_payload",
    node_id="basic-compute",
    gateway_address=GATEWAY_ADDRESS,
)
def process_payload(payload: dict[str, int]) -> dict[str, int]:
    # Local fallback for static analysis/debugging; @remote wrapper executes remotely.
    return {key: value * 2 for key, value in payload.items()}


class BasicClientDemo:
    """
    Triggers simple remote calls for quick validation.
    """

    def run(self) -> None:
        add_result = add_numbers(7, 35)
        payload_result = process_payload({"x": 2, "y": 10})

        print(f"add_numbers => {add_result}")
        print(f"process_payload => {payload_result}")


if __name__ == "__main__":
    BasicClientDemo().run()
