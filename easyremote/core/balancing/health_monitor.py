#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Deterministic node health monitoring for EasyRemote."""

from __future__ import annotations

import asyncio
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional

from ..utils.concurrency import LoopBoundAsyncLock
from ..utils.exceptions import ExceptionTranslator, LoadBalancingError
from ..utils.logger import ModernLogger
from .strategies import NodeStats


class NodeHealthLevel(Enum):
    """Health status levels used by routing and failover logic."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNREACHABLE = "unreachable"
    UNKNOWN = "unknown"
    QUARANTINED = "quarantined"


class HealthCheckType(Enum):
    """Supported health check depth types."""

    BASIC_PING = "basic_ping"
    RESOURCE_CHECK = "resource_check"
    SERVICE_CHECK = "service_check"
    FULL_DIAGNOSTIC = "full_diagnostic"


@dataclass
class HealthThresholds:
    """Thresholds for translating metrics into health levels."""

    cpu_healthy_max: float = 70.0
    cpu_degraded_max: float = 85.0
    cpu_unhealthy_max: float = 95.0

    memory_healthy_max: float = 75.0
    memory_degraded_max: float = 88.0
    memory_unhealthy_max: float = 95.0

    response_time_healthy_max: float = 100.0
    response_time_degraded_max: float = 500.0
    response_time_unhealthy_max: float = 2000.0

    error_rate_healthy_max: float = 1.0
    error_rate_degraded_max: float = 5.0
    error_rate_unhealthy_max: float = 15.0

    def validate_thresholds(self) -> List[str]:
        """Validate threshold ordering and value ranges."""
        errors: List[str] = []

        if not (
            0
            <= self.cpu_healthy_max
            <= self.cpu_degraded_max
            <= self.cpu_unhealthy_max
            <= 100
        ):
            errors.append("CPU thresholds must be in ascending order between 0 and 100")

        if not (
            0
            <= self.memory_healthy_max
            <= self.memory_degraded_max
            <= self.memory_unhealthy_max
            <= 100
        ):
            errors.append(
                "Memory thresholds must be in ascending order between 0 and 100"
            )

        if not (
            0
            <= self.response_time_healthy_max
            <= self.response_time_degraded_max
            <= self.response_time_unhealthy_max
        ):
            errors.append(
                "Response time thresholds must be in ascending order and non-negative"
            )

        if not (
            0
            <= self.error_rate_healthy_max
            <= self.error_rate_degraded_max
            <= self.error_rate_unhealthy_max
            <= 100
        ):
            errors.append(
                "Error rate thresholds must be in ascending order between 0 and 100"
            )

        return errors


@dataclass
class NodeHealthSnapshot:
    """Raw probe data used to update `NodeHealthStatus`."""

    node_id: str
    is_reachable: bool
    is_responding: bool
    is_available: bool
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    gpu_usage: float = 0.0
    response_time_ms: float = 0.0
    queue_length: int = 0
    current_load: Optional[float] = None
    error_rate: Optional[float] = None
    health_check_type: HealthCheckType = HealthCheckType.RESOURCE_CHECK
    error: Optional[str] = None


@dataclass
class NodeHealthStatus:
    """Cached health state for one node."""

    node_id: str

    overall_health: NodeHealthLevel = NodeHealthLevel.UNKNOWN
    health_score: float = 0.0

    is_reachable: bool = False
    is_available: bool = False
    is_responding: bool = False

    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    gpu_usage: float = 0.0

    current_load: float = 0.0
    queue_length: int = 0
    response_time_ms: float = 0.0
    average_response_time_ms: float = 0.0

    error_rate: float = 0.0
    success_rate: float = 100.0
    consecutive_failures: int = 0

    last_health_check: datetime = field(default_factory=datetime.now)
    last_successful_check: Optional[datetime] = None

    health_check_type: HealthCheckType = HealthCheckType.BASIC_PING
    health_check_duration_ms: float = 0.0
    health_check_error: Optional[str] = None

    def update_health_metrics(
        self,
        cpu_usage: Optional[float] = None,
        memory_usage: Optional[float] = None,
        gpu_usage: Optional[float] = None,
        response_time_ms: Optional[float] = None,
        error_rate: Optional[float] = None,
    ) -> None:
        """Update and normalize measurable health metrics."""
        if cpu_usage is not None:
            self.cpu_usage = max(0.0, min(100.0, cpu_usage))

        if memory_usage is not None:
            self.memory_usage = max(0.0, min(100.0, memory_usage))

        if gpu_usage is not None:
            self.gpu_usage = max(0.0, min(100.0, gpu_usage))

        if response_time_ms is not None:
            value = max(0.0, response_time_ms)
            self.response_time_ms = value
            if self.average_response_time_ms == 0.0:
                self.average_response_time_ms = value
            else:
                alpha = 0.1
                self.average_response_time_ms = (
                    alpha * value + (1 - alpha) * self.average_response_time_ms
                )

        if error_rate is not None:
            self.error_rate = max(0.0, min(100.0, error_rate))
            self.success_rate = 100.0 - self.error_rate

        self.last_health_check = datetime.now()

    def calculate_health_score(self, thresholds: HealthThresholds) -> float:
        """Calculate a 0.0-1.0 health score from current metrics."""
        if not self.is_reachable:
            return 0.0

        cpu_score = max(
            0.0,
            (thresholds.cpu_unhealthy_max - self.cpu_usage)
            / max(thresholds.cpu_unhealthy_max, 1.0),
        )
        memory_score = max(
            0.0,
            (thresholds.memory_unhealthy_max - self.memory_usage)
            / max(thresholds.memory_unhealthy_max, 1.0),
        )
        response_score = max(
            0.0,
            1 - (self.response_time_ms / max(thresholds.response_time_unhealthy_max, 1.0)),
        )
        error_score = max(0.0, (100.0 - self.error_rate) / 100.0)

        return (
            (0.3 * cpu_score)
            + (0.3 * memory_score)
            + (0.2 * response_score)
            + (0.2 * error_score)
        )

    def determine_health_level(self, thresholds: HealthThresholds) -> NodeHealthLevel:
        """Map current status into one of the defined health levels."""
        if not self.is_reachable:
            if self.consecutive_failures >= 5:
                return NodeHealthLevel.QUARANTINED
            return NodeHealthLevel.UNREACHABLE

        score = self.calculate_health_score(thresholds)
        self.health_score = score

        if score >= 0.8:
            return NodeHealthLevel.HEALTHY
        if score >= 0.6:
            return NodeHealthLevel.DEGRADED
        return NodeHealthLevel.UNHEALTHY


class NodeHealthProbe(ABC):
    """Strategy interface that reads node health from a backend system."""

    @abstractmethod
    async def collect_snapshot(self, gateway: Any, node_id: str) -> NodeHealthSnapshot:
        """Return one health snapshot for a node."""


class GatewayNodeHealthProbe(NodeHealthProbe):
    """Probe implementation that reads metrics from the in-process gateway registry."""

    async def collect_snapshot(self, gateway: Any, node_id: str) -> NodeHealthSnapshot:
        if gateway is None:
            return NodeHealthSnapshot(
                node_id=node_id,
                is_reachable=False,
                is_responding=False,
                is_available=False,
                error="gateway instance is not configured",
            )

        nodes = getattr(gateway, "_nodes", None)
        if not isinstance(nodes, Mapping):
            return NodeHealthSnapshot(
                node_id=node_id,
                is_reachable=False,
                is_responding=False,
                is_available=False,
                error="gateway has no readable node registry",
            )

        node_info = nodes.get(node_id)
        if node_info is None:
            return NodeHealthSnapshot(
                node_id=node_id,
                is_reachable=False,
                is_responding=False,
                is_available=False,
                error="node not found in gateway registry",
            )

        alive = True
        is_alive = getattr(node_info, "is_alive", None)
        if callable(is_alive):
            try:
                alive = bool(is_alive())
            except Exception as exc:
                return NodeHealthSnapshot(
                    node_id=node_id,
                    is_reachable=False,
                    is_responding=False,
                    is_available=False,
                    error=f"failed to query liveness: {exc}",
                )

        if not alive:
            return NodeHealthSnapshot(
                node_id=node_id,
                is_reachable=False,
                is_responding=False,
                is_available=False,
                error="node is not alive",
            )

        health_metrics = getattr(node_info, "health_metrics", None)
        if health_metrics is None:
            return NodeHealthSnapshot(
                node_id=node_id,
                is_reachable=True,
                is_responding=True,
                is_available=True,
            )

        cpu_usage = _safe_float(getattr(health_metrics, "cpu_usage_percent", 0.0), 0.0)
        memory_usage = _safe_float(
            getattr(health_metrics, "memory_usage_percent", 0.0), 0.0
        )
        gpu_usage = _safe_float(getattr(health_metrics, "gpu_usage_percent", 0.0), 0.0)

        response_time_ms = _safe_float(
            getattr(
                health_metrics,
                "network_latency_ms",
                getattr(health_metrics, "response_time_ms", 0.0),
            ),
            0.0,
        )

        queue_length = int(
            _safe_float(
                getattr(
                    health_metrics,
                    "concurrent_executions",
                    getattr(health_metrics, "queue_length", 0),
                ),
                0.0,
            )
        )

        explicit_load = getattr(
            health_metrics,
            "current_load",
            getattr(health_metrics, "load_factor", None),
        )
        current_load: Optional[float]
        if explicit_load is None:
            current_load = min(
                ((cpu_usage + memory_usage) / 200.0) + min(queue_length / 20.0, 0.5),
                1.0,
            )
        else:
            current_load = max(0.0, min(1.0, _safe_float(explicit_load, 0.0)))

        error_rate = getattr(
            health_metrics,
            "error_rate_percent",
            getattr(health_metrics, "error_rate", None),
        )

        return NodeHealthSnapshot(
            node_id=node_id,
            is_reachable=True,
            is_responding=True,
            is_available=cpu_usage < 95.0 and memory_usage < 95.0,
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            gpu_usage=gpu_usage,
            response_time_ms=response_time_ms,
            queue_length=max(queue_length, 0),
            current_load=current_load,
            error_rate=_safe_optional_float(error_rate),
            health_check_type=HealthCheckType.RESOURCE_CHECK,
        )


class AdvancedNodeHealthMonitor(ModernLogger):
    """Health monitor with deterministic probe/evaluation/scheduling behavior."""

    def __init__(
        self,
        monitoring_interval: float = 15.0,
        health_check_timeout: float = 5.0,
        adaptive_monitoring: bool = True,
        health_probe: Optional[NodeHealthProbe] = None,
        max_concurrent_checks: int = 10,
    ):
        super().__init__(name="AdvancedNodeHealthMonitor")

        if monitoring_interval <= 0:
            raise ValueError("monitoring_interval must be positive")
        if health_check_timeout <= 0:
            raise ValueError("health_check_timeout must be positive")
        if max_concurrent_checks <= 0:
            raise ValueError("max_concurrent_checks must be positive")

        self.monitoring_interval = monitoring_interval
        self.health_check_timeout = health_check_timeout
        self.adaptive_monitoring = adaptive_monitoring
        self.max_concurrent_checks = max_concurrent_checks
        self.thresholds = HealthThresholds()

        self._gateway: Optional[Any] = None
        self._health_probe = health_probe or GatewayNodeHealthProbe()

        self._running = False
        self._monitoring_task: Optional[asyncio.Task] = None
        self._state_lock = LoopBoundAsyncLock(name="health-monitor-state-lock")
        self._sleep_event: Optional[asyncio.Event] = None

        self._health_cache: Dict[str, NodeHealthStatus] = {}
        self._health_cache_lock = threading.RLock()

        self._semaphore: Optional[asyncio.Semaphore] = None

    async def start_monitoring(self, gateway_instance: Any) -> "AdvancedNodeHealthMonitor":
        """Start background health checks for gateway nodes."""
        async with self._state_lock:
            if self._running:
                raise LoadBalancingError(
                    message="Health monitoring is already running",
                    strategy="health_monitor",
                )

            self._gateway = gateway_instance
            self._running = True
            self._semaphore = asyncio.Semaphore(self.max_concurrent_checks)
            self._sleep_event = asyncio.Event()
            self._monitoring_task = asyncio.create_task(self._monitoring_loop())

        self.info(
            "Node health monitoring started (interval=%.2fs, adaptive=%s)",
            self.monitoring_interval,
            self.adaptive_monitoring,
        )
        return self

    async def stop_monitoring(self) -> None:
        """Stop background health checks and wait for task termination."""
        task: Optional[asyncio.Task] = None

        async with self._state_lock:
            if not self._running:
                return

            self._running = False
            if self._sleep_event is not None:
                self._sleep_event.set()

            if self._monitoring_task and not self._monitoring_task.done():
                self._monitoring_task.cancel()
                task = self._monitoring_task

        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                pass

        self.info("Node health monitoring stopped")

    async def _monitoring_loop(self) -> None:
        """Main monitor loop with adaptive but deterministic interval control."""
        try:
            while self._running:
                started_at = time.time()

                try:
                    await self._perform_health_checks()
                except Exception as exc:
                    translated = ExceptionTranslator.as_load_balancing_error(
                        exc,
                        strategy="health_monitor",
                        message="Health monitoring cycle failed",
                    )
                    self.error("Error in health monitoring cycle: %s", translated, exc_info=True)

                elapsed = time.time() - started_at
                wait_seconds = self._next_interval(elapsed)

                try:
                    event = self._sleep_event
                    if event is None:
                        await asyncio.sleep(wait_seconds)
                    else:
                        await asyncio.wait_for(event.wait(), timeout=wait_seconds)
                        event.clear()
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            self.debug("Health monitoring loop cancelled")
        except Exception as exc:
            translated = ExceptionTranslator.as_load_balancing_error(
                exc,
                strategy="health_monitor",
                message="Unexpected error in monitoring loop",
            )
            self.error("Unexpected monitor loop error: %s", translated, exc_info=True)

    def _next_interval(self, monitoring_duration: float) -> float:
        """Compute next cycle interval based on cluster health condition."""
        base = max(self.monitoring_interval - monitoring_duration, 1.0)
        if not self.adaptive_monitoring:
            return base

        with self._health_cache_lock:
            statuses = list(self._health_cache.values())

        if not statuses:
            return base

        problematic = sum(
            1
            for status in statuses
            if status.overall_health
            in (
                NodeHealthLevel.UNHEALTHY,
                NodeHealthLevel.UNREACHABLE,
                NodeHealthLevel.QUARANTINED,
            )
        )
        ratio = problematic / len(statuses)

        if ratio >= 0.5:
            return max(1.0, base * 0.5)
        if ratio == 0:
            return min(base * 1.5, self.monitoring_interval * 2.0)
        return base

    async def _perform_health_checks(self) -> None:
        """Run one health-check pass over all registered gateway nodes."""
        node_ids = await self._list_node_ids()
        if not node_ids:
            return

        results = await asyncio.gather(
            *(self._check_single_node(node_id) for node_id in node_ids),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                self.warning("Health check task failed: %s", result)

    async def _list_node_ids(self) -> List[str]:
        gateway = self._gateway
        if gateway is None:
            return []

        lock = getattr(gateway, "_global_lock", None)
        nodes_attr = "_nodes"

        if lock is not None:
            try:
                async with lock:
                    nodes = getattr(gateway, nodes_attr, {})
                    if isinstance(nodes, Mapping):
                        return list(nodes.keys())
                    return []
            except Exception:
                # Fall back to best-effort direct read.
                pass

        nodes = getattr(gateway, nodes_attr, {})
        if isinstance(nodes, Mapping):
            return list(nodes.keys())
        return []

    async def _check_single_node(self, node_id: str) -> NodeHealthStatus:
        """Run one node check with bounded concurrency."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrent_checks)

        async with self._semaphore:
            try:
                return await self.check_node_health(node_id)
            except Exception as exc:
                self.warning("Health check failed for node %s: %s", node_id, exc)
                return self._create_failed_health_status(node_id, str(exc))

    async def check_node_health(self, node_id: str) -> NodeHealthStatus:
        """Probe and refresh cached health status for one node."""
        start_time = time.time()

        with self._health_cache_lock:
            health_status = self._health_cache.get(node_id)
            if health_status is None:
                health_status = NodeHealthStatus(node_id=node_id)
                self._health_cache[node_id] = health_status

        try:
            snapshot = await asyncio.wait_for(
                self._health_probe.collect_snapshot(self._gateway, node_id),
                timeout=self.health_check_timeout,
            )

            with self._health_cache_lock:
                if snapshot.is_reachable:
                    self._apply_reachable_snapshot(health_status, snapshot)
                else:
                    self._handle_health_check_failure(
                        health_status,
                        snapshot.error or "node is unreachable",
                    )
        except Exception as exc:
            self._handle_health_check_failure(health_status, str(exc))
        finally:
            duration_ms = (time.time() - start_time) * 1000.0
            with self._health_cache_lock:
                health_status.health_check_duration_ms = duration_ms

        return health_status

    def _apply_reachable_snapshot(
        self,
        status: NodeHealthStatus,
        snapshot: NodeHealthSnapshot,
    ) -> None:
        status.is_reachable = snapshot.is_reachable
        status.is_responding = snapshot.is_responding

        status.queue_length = max(snapshot.queue_length, 0)
        if snapshot.current_load is not None:
            status.current_load = max(0.0, min(1.0, snapshot.current_load))
        else:
            status.current_load = min(
                ((snapshot.cpu_usage + snapshot.memory_usage) / 200.0)
                + min(status.queue_length / 20.0, 0.5),
                1.0,
            )

        status.update_health_metrics(
            cpu_usage=snapshot.cpu_usage,
            memory_usage=snapshot.memory_usage,
            gpu_usage=snapshot.gpu_usage,
            response_time_ms=snapshot.response_time_ms,
            error_rate=snapshot.error_rate,
        )

        status.health_check_type = snapshot.health_check_type
        status.consecutive_failures = 0
        status.last_successful_check = datetime.now()
        status.health_check_error = snapshot.error

        status.overall_health = status.determine_health_level(self.thresholds)
        status.is_available = bool(snapshot.is_available) and status.overall_health in (
            NodeHealthLevel.HEALTHY,
            NodeHealthLevel.DEGRADED,
        )

    def _handle_health_check_failure(self, status: NodeHealthStatus, error_message: str) -> None:
        with self._health_cache_lock:
            status.consecutive_failures += 1
            status.is_reachable = False
            status.is_available = False
            status.is_responding = False
            status.health_check_error = error_message
            status.last_health_check = datetime.now()

            status.overall_health = status.determine_health_level(self.thresholds)

    def _create_failed_health_status(
        self,
        node_id: str,
        error_message: str,
    ) -> NodeHealthStatus:
        with self._health_cache_lock:
            status = self._health_cache.get(node_id)
            if status is None:
                status = NodeHealthStatus(node_id=node_id)
                self._health_cache[node_id] = status

            status.consecutive_failures += 1
            status.is_reachable = False
            status.is_available = False
            status.is_responding = False
            status.health_check_error = error_message
            status.last_health_check = datetime.now()
            status.overall_health = status.determine_health_level(self.thresholds)
            return status

    def get_node_health(self, node_id: str) -> Optional[NodeHealthStatus]:
        """Return cached health status for a node, if available."""
        with self._health_cache_lock:
            return self._health_cache.get(node_id)

    def is_node_healthy(self, node_id: str) -> bool:
        """Check whether cached node status is healthy."""
        health = self.get_node_health(node_id)
        return health is not None and health.overall_health == NodeHealthLevel.HEALTHY

    def is_node_available(self, node_id: str) -> bool:
        """Check whether node can receive new requests."""
        health = self.get_node_health(node_id)
        return health is not None and health.is_available

    def get_node_stats(self, node_id: str) -> Optional[NodeStats]:
        """Convert cached health information to `NodeStats`."""
        health = self.get_node_health(node_id)
        if health is None:
            return None

        return NodeStats(
            node_id=node_id,
            cpu_usage=health.cpu_usage,
            memory_usage=health.memory_usage,
            gpu_usage=health.gpu_usage,
            current_load=health.current_load,
            queue_length=health.queue_length,
            response_time=health.response_time_ms,
            success_rate=health.success_rate / 100.0,
            has_gpu=health.gpu_usage > 0,
            last_updated=health.last_health_check.timestamp(),
        )


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    return _safe_float(value)


# Backward compatibility alias
NodeHealthMonitor = AdvancedNodeHealthMonitor


__all__ = [
    "AdvancedNodeHealthMonitor",
    "NodeHealthMonitor",
    "NodeHealthProbe",
    "GatewayNodeHealthProbe",
    "NodeHealthSnapshot",
    "NodeHealthStatus",
    "NodeHealthLevel",
    "HealthCheckType",
    "HealthThresholds",
]
