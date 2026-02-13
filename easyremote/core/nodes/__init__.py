# -*- coding: utf-8 -*-

"""
EasyRemote Distributed Computing Nodes Module

This module provides the core distributed computing components for the EasyRemote
framework, including gateway servers, compute nodes, and client interfaces.

Components:
- DistributedComputingGateway: Central orchestration hub for distributed computing
- DistributedComputeNode: High-performance compute nodes with intelligent management
- DistributedComputingClient: Advanced client for remote function execution

Features:
- Production-grade reliability and performance
- Comprehensive monitoring and analytics
- Advanced load balancing and routing
- Enterprise security and compliance
- Horizontal scalability and clustering

Author: Silan Hu (silan.hu@u.nus.edu)
Version: 2.0.0
"""

# Import new production-grade classes
from .server import DistributedComputingGateway, GatewayServerBuilder
from .compute_node import DistributedComputeNode, ComputeNodeBuilder
from .client import DistributedComputingClient, ClientBuilder

# Backward compatibility aliases
from .server import Server, DistributedComputeServer
from .compute_node import ComputeNode
from .client import Client

__all__ = [
    # Core production classes
    "DistributedComputingGateway",
    "DistributedComputeNode", 
    "DistributedComputingClient",
    
    # Builder classes
    "GatewayServerBuilder",
    "ComputeNodeBuilder",
    "ClientBuilder",
    
    # Backward compatibility
    "Server",
    "ComputeNode", 
    "Client",
    "DistributedComputeServer"
]
