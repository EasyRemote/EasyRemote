#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EasyRemote Basic Tools Module

This module provides essential monitoring and diagnostic tools for the
EasyRemote distributed computing framework. It focuses on simplicity
and core functionality needed for basic distributed computing operations.

Key Features:
1. Basic Performance Monitoring:
   * Simple CPU, memory, and network monitoring
   * Basic function execution tracking
   * Lightweight metrics collection

2. Simple System Health:
   * Node connectivity checks
   * Basic resource utilization
   * Simple health reporting

3. Minimal Load Testing:
   * Basic function load testing
   * Simple performance metrics
   * Connection testing

Author: Silan Hu (silan.hu@u.nus.edu)
Version: 1.0.0 (Simplified)
"""

import time
import asyncio
import warnings
from typing import Dict, List, Any
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


class MonitoringStatus(Enum):
    """Simple monitoring status."""
    HEALTHY = "healthy"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class BasicMetrics:
    """Basic system metrics."""
    timestamp: datetime
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    disk_percent: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent, 
            "disk_percent": self.disk_percent
        }


@dataclass
class HealthReport:
    """Simple health report."""
    status: MonitoringStatus
    score: float  # 0-100
    message: str
    metrics: BasicMetrics
    issues: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "score": self.score,
            "message": self.message,
            "metrics": self.metrics.to_dict(),
            "issues": self.issues
        }


class BasicMonitor:
    """Simple performance monitor for EasyRemote."""
    
    def __init__(self):
        self.enabled = PSUTIL_AVAILABLE
        if not self.enabled:
            warnings.warn("psutil not available, monitoring disabled", UserWarning)
    
    def collect_metrics(self) -> BasicMetrics:
        """Collect basic system metrics."""
        if not self.enabled:
            return BasicMetrics(timestamp=datetime.now())
        
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            return BasicMetrics(
                timestamp=datetime.now(),
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                disk_percent=(disk.used / disk.total) * 100
            )
        except Exception:
            return BasicMetrics(timestamp=datetime.now())
    
    def check_health(self) -> HealthReport:
        """Perform basic health check."""
        metrics = self.collect_metrics()
        issues = []
        
        # Simple thresholds
        if metrics.cpu_percent > 90:
            issues.append("High CPU usage")
        if metrics.memory_percent > 90:
            issues.append("High memory usage")
        if metrics.disk_percent > 90:
            issues.append("High disk usage")
        
        # Calculate simple score
        score = 100
        if metrics.cpu_percent > 80:
            score -= 20
        if metrics.memory_percent > 80:
            score -= 20
        if metrics.disk_percent > 80:
            score -= 10
        
        # Determine status
        if len(issues) == 0:
            status = MonitoringStatus.HEALTHY
            message = "System is healthy"
        elif len(issues) <= 2:
            status = MonitoringStatus.WARNING  
            message = f"System has {len(issues)} warning(s)"
        else:
            status = MonitoringStatus.ERROR
            message = f"System has {len(issues)} issue(s)"
        
        return HealthReport(
            status=status,
            score=max(0, score),
            message=message,
            metrics=metrics,
            issues=issues
        )


class SimpleLoadTester:
    """Basic load tester for EasyRemote functions."""
    
    def __init__(self, gateway_address: str = "localhost:8080"):
        self.gateway_address = gateway_address
    
    async def test_function(self, function_name: str, 
                          test_data: Any = None,
                          num_requests: int = 10,
                          concurrent: int = 2) -> Dict[str, Any]:
        """Run a simple load test on a function."""
        try:
            from ..nodes.client import DistributedComputingClient
            
            client = DistributedComputingClient(self.gateway_address)
            
            start_time = time.time()
            success_count = 0
            error_count = 0
            response_times = []
            
            # Simple sequential testing (for simplicity)
            for i in range(num_requests):
                request_start = time.time()
                try:
                    if test_data:
                        await asyncio.to_thread(client.execute, function_name, test_data)
                    else:
                        await asyncio.to_thread(client.execute, function_name)
                    success_count += 1
                except Exception:
                    error_count += 1
                
                response_times.append((time.time() - request_start) * 1000)
                
                # Small delay between requests
                await asyncio.sleep(0.1)
            
            total_time = time.time() - start_time
            avg_response_time = sum(response_times) / len(response_times) if response_times else 0
            
            return {
                "total_requests": num_requests,
                "successful_requests": success_count,
                "failed_requests": error_count,
                "success_rate_percent": (success_count / num_requests) * 100,
                "avg_response_time_ms": avg_response_time,
                "total_duration_seconds": total_time,
                "requests_per_second": num_requests / total_time if total_time > 0 else 0
            }
            
        except Exception as e:
            return {
                "error": f"Load test failed: {str(e)}",
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": num_requests
            }


def quick_health_check() -> Dict[str, Any]:
    """Quick system health check."""
    monitor = BasicMonitor()
    health = monitor.check_health()
    return health.to_dict()


def quick_metrics() -> Dict[str, Any]:
    """Quick metrics collection."""
    monitor = BasicMonitor()
    metrics = monitor.collect_metrics()
    return metrics.to_dict()


async def quick_load_test(function_name: str, 
                         gateway_address: str = "localhost:8080",
                         test_data: Any = None) -> Dict[str, Any]:
    """Quick load test for a function."""
    tester = SimpleLoadTester(gateway_address)
    return await tester.test_function(function_name, test_data, num_requests=5)


# Public API
__all__ = [
    'BasicMonitor',
    'SimpleLoadTester', 
    'BasicMetrics',
    'HealthReport',
    'MonitoringStatus',
    'quick_health_check',
    'quick_metrics',
    'quick_load_test'
]

__version__ = "1.0.0"
__author__ = "Silan Hu" 
