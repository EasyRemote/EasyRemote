#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Simulated GPU node beta.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import random
import sys
import time
import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from easyremote import ComputeNode  # noqa: E402


@dataclass
class TrainingResult:
    node_id: str
    model_name: str
    duration_seconds: float
    score: float


class GpuBetaNode:
    """
    Second provider for the same load-balanced function.
    """

    def __init__(self, gateway_address: str) -> None:
        self._node = ComputeNode(gateway_address=gateway_address, node_id="gpu-beta")
        self._register()

    def _register(self) -> None:
        @self._node.register(
            name="train_model",
            load_balancing=True,
            description="Simulate training on GPU beta",
        )
        def train_model(model_name: str, dataset_size: int) -> dict[str, object]:
            duration = round(max(0.3, dataset_size / 4200), 2)
            time.sleep(duration)
            result = TrainingResult(
                node_id="gpu-beta",
                model_name=model_name,
                duration_seconds=duration,
                score=round(random.uniform(0.84, 0.92), 4),
            )
            return result.__dict__

    def serve(self) -> None:
        self._node.serve()


if __name__ == "__main__":
    gateway_address = os.getenv("EASYREMOTE_GATEWAY_ADDRESS", "127.0.0.1:8081")
    GpuBetaNode(gateway_address=gateway_address).serve()
