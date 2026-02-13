#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tests for gateway ListNodes capability metadata exposure.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import asyncio
from types import SimpleNamespace

from easyremote.core.data import NodeInfo, NodeStatus
from easyremote.core.nodes.server import DistributedComputingGateway


def test_list_nodes_includes_capabilities_and_version():
    server = DistributedComputingGateway(port=19100)
    server._nodes["node-1"] = NodeInfo(
        node_id="node-1",
        status=NodeStatus.CONNECTED,
        capabilities={"user:user-1", "camera"},
        version="2.1.0",
        location="desktop-nyc",
    )

    response = asyncio.run(
        server.ListNodes(
            SimpleNamespace(client_id="test-client"),
            context=None,
        )
    )
    assert len(response.nodes) == 1
    node = response.nodes[0]
    assert node.node_id == "node-1"
    assert sorted(node.capabilities) == ["camera", "user:user-1"]
    assert node.version == "2.1.0"
    assert node.location == "desktop-nyc"
