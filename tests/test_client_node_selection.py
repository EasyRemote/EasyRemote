#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tests for client-side node capability selection helpers.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import pytest

from easyremote.core.nodes.client import DistributedComputingClient
from easyremote.core.utils.exceptions import NoAvailableNodesError


def test_find_nodes_filters_by_capabilities_and_functions():
    client = DistributedComputingClient("127.0.0.1:8080")
    client.list_nodes = lambda: [  # type: ignore[method-assign]
        {
            "node_id": "node-a",
            "capabilities": ["user:user-1", "camera"],
            "functions": ["device.install_remote_skill", "user.camera.take_photo"],
            "current_load": 0.3,
        },
        {
            "node_id": "node-b",
            "capabilities": ["user:user-2", "voice"],
            "functions": ["device.install_remote_skill"],
            "current_load": 0.1,
        },
    ]

    matches = client.find_nodes(
        required_capabilities=["user:user-1"],
        required_functions=["device.install_remote_skill"],
    )
    assert [item["node_id"] for item in matches] == ["node-a"]


def test_resolve_node_id_requires_unique_match():
    client = DistributedComputingClient("127.0.0.1:8080")
    client.list_nodes = lambda: [  # type: ignore[method-assign]
        {"node_id": "node-a", "capabilities": ["user:user-1"], "functions": ["f"]},
        {"node_id": "node-b", "capabilities": ["user:user-1"], "functions": ["f"]},
    ]

    with pytest.raises(NoAvailableNodesError):
        client.resolve_node_id(
            required_capabilities=["user:user-1"],
            required_functions=["f"],
        )

    client.list_nodes = lambda: [  # type: ignore[method-assign]
        {"node_id": "node-a", "capabilities": ["user:user-1"], "functions": ["f"]},
    ]
    resolved = client.resolve_node_id(
        required_capabilities=["user:user-1"],
        required_functions=["f"],
    )
    assert resolved == "node-a"
