#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tests for compute node capability tagging.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from easyremote.core.nodes.compute_node import ComputeNode


def test_compute_node_exposes_configured_capabilities_in_node_info():
    node = ComputeNode(
        gateway_address="127.0.0.1:8080",
        node_id="node-cap",
        node_capabilities={"user:user-1", "camera"},
    )
    info = node.get_node_info()
    assert "user:user-1" in info.capabilities
    assert "camera" in info.capabilities
