#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Client for team GPU load-balancing simulation.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from easyremote import remote  # noqa: E402

GATEWAY_ADDRESS = os.getenv("EASYREMOTE_GATEWAY_ADDRESS", "127.0.0.1:8081")


@remote(
    function_name="train_model",
    load_balancing={"strategy": "resource_aware"},
    gateway_address=GATEWAY_ADDRESS,
)
def train_model(model_name: str, dataset_size: int) -> dict[str, object]:
    # Local fallback for static analysis/debugging; @remote wrapper executes remotely.
    return {
        "node_id": "local-fallback",
        "model_name": model_name,
        "duration_seconds": round(max(0.2, dataset_size / 5000), 2),
        "score": 0.9,
    }


class TeamGpuPoolClient:
    """
    Submits multiple jobs to verify multi-node routing.
    """

    def run(self) -> None:
        jobs = [
            ("resnet50", 2000),
            ("bert-base", 3200),
            ("vit-small", 2600),
            ("gpt-mini", 1800),
        ]

        for model_name, dataset_size in jobs:
            response = train_model(model_name=model_name, dataset_size=dataset_size)
            print(response)


if __name__ == "__main__":
    TeamGpuPoolClient().run()
