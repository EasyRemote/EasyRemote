#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Regression tests for sync compute-node execution argument binding.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from easyremote.core.nodes.compute_node import DistributedComputeNode


def test_build_executor_callable_supports_keyword_arguments_for_sync_functions():
    def train_model(dataset_size: int, model_name: str) -> str:
        return f"{model_name}:{dataset_size}"

    bound = DistributedComputeNode._build_executor_callable(
        func=train_model,
        args=(),
        kwargs={"dataset_size": 2000, "model_name": "resnet50"},
    )

    assert bound() == "resnet50:2000"


def test_build_executor_callable_supports_mixed_positional_and_keyword_arguments():
    def compute_score(base: int, scale: int, offset: int = 0) -> int:
        return base * scale + offset

    bound = DistributedComputeNode._build_executor_callable(
        func=compute_score,
        args=(7,),
        kwargs={"scale": 3, "offset": 5},
    )

    assert bound() == 26
