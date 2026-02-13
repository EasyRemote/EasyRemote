#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Smoke test runner for gallery projects.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


@dataclass
class SmokeResult:
    name: str
    route: str
    passed: bool
    duration_seconds: float
    detail: str


@dataclass
class ProtocolCase:
    name: str
    script: Path
    required_keys: tuple[str, ...]


@dataclass
class HumanCase:
    name: str
    port: int
    server_script: Path
    node_scripts: tuple[Path, ...]
    client_script: Path


class GallerySmokeTester:
    """
    Runs smoke tests for supported gallery cases.
    """

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self.gallery_root = workspace_root / "gallery"
        self.results: list[SmokeResult] = []
        self._python_command_prefix = self._resolve_python_command_prefix()

    def run(self) -> int:
        protocol_cases = self._protocol_cases()
        human_cases = self._human_cases()

        for case in protocol_cases:
            self.results.append(self._run_protocol_case(case))

        for case in human_cases:
            self.results.append(self._run_human_case(case))

        self._print_summary()
        self._write_report()

        return 0 if all(result.passed for result in self.results) else 1

    def _protocol_cases(self) -> tuple[ProtocolCase, ...]:
        return (
            ProtocolCase(
                name="P1 MCP Tool Mesh",
                script=self.gallery_root / "projects/02_mcp_tool_mesh/run_demo.py",
                required_keys=("initialize", "tools_list", "tools_call", "batch"),
            ),
            ProtocolCase(
                name="P2 A2A Incident Copilot",
                script=self.gallery_root
                / "projects/03_a2a_incident_copilot/run_demo.py",
                required_keys=("capabilities", "task_execute", "notification", "batch"),
            ),
            ProtocolCase(
                name="P3 Function Marketplace Agent Route",
                script=self.gallery_root
                / "projects/04_function_marketplace/agent_catalog_demo.py",
                required_keys=(
                    "mcp_tools_list",
                    "mcp_tools_call",
                    "a2a_capabilities",
                    "a2a_task_execute",
                ),
            ),
            ProtocolCase(
                name="P4 Local Data Residency Agent Route",
                script=self.gallery_root
                / "projects/05_local_data_residency_ai/protocol_demo.py",
                required_keys=("mcp_sanitize", "mcp_risk", "a2a_capabilities", "a2a_task"),
            ),
        )

    def _human_cases(self) -> tuple[HumanCase, ...]:
        return (
            HumanCase(
                name="H1 Basic Remote Math",
                port=18080,
                server_script=self.gallery_root / "projects/00_basic_remote_math/server.py",
                node_scripts=(
                    self.gallery_root / "projects/00_basic_remote_math/compute_node.py",
                ),
                client_script=self.gallery_root / "projects/00_basic_remote_math/client.py",
            ),
            HumanCase(
                name="H2 Team GPU Pool",
                port=18081,
                server_script=self.gallery_root
                / "projects/01_team_gpu_pool_load_balancing/server.py",
                node_scripts=(
                    self.gallery_root
                    / "projects/01_team_gpu_pool_load_balancing/node_gpu_alpha.py",
                    self.gallery_root
                    / "projects/01_team_gpu_pool_load_balancing/node_gpu_beta.py",
                ),
                client_script=self.gallery_root
                / "projects/01_team_gpu_pool_load_balancing/client.py",
            ),
            HumanCase(
                name="H3 Function Marketplace Human Route",
                port=18082,
                server_script=self.gallery_root / "projects/04_function_marketplace/server.py",
                node_scripts=(
                    self.gallery_root
                    / "projects/04_function_marketplace/node_finance.py",
                    self.gallery_root / "projects/04_function_marketplace/node_ops.py",
                ),
                client_script=self.gallery_root / "projects/04_function_marketplace/client.py",
            ),
            HumanCase(
                name="H4 Local Data Residency Human Route",
                port=18083,
                server_script=self.gallery_root
                / "projects/05_local_data_residency_ai/server.py",
                node_scripts=(
                    self.gallery_root
                    / "projects/05_local_data_residency_ai/node_local_processor.py",
                ),
                client_script=self.gallery_root
                / "projects/05_local_data_residency_ai/client.py",
            ),
            HumanCase(
                name="H5 Runtime Device Capability Injection",
                port=18084,
                server_script=self.gallery_root
                / "projects/06_runtime_device_capability_injection/server.py",
                node_scripts=(
                    self.gallery_root
                    / "projects/06_runtime_device_capability_injection/user_device_node.py",
                ),
                client_script=self.gallery_root
                / "projects/06_runtime_device_capability_injection/agent_client.py",
            ),
        )

    def _run_protocol_case(self, case: ProtocolCase) -> SmokeResult:
        start = time.monotonic()
        command = self._python_command_for_script(case.script)
        completed = subprocess.run(
            command,
            cwd=self.workspace_root,
            capture_output=True,
            text=True,
            timeout=60,
            env=self._base_env(),
        )

        duration = time.monotonic() - start
        if completed.returncode != 0:
            return SmokeResult(
                name=case.name,
                route="agent",
                passed=False,
                duration_seconds=duration,
                detail=self._truncate(
                    f"exit={completed.returncode}; stderr={completed.stderr.strip()}"
                ),
            )

        payload = self._extract_json_payload(completed.stdout)
        if payload is None:
            return SmokeResult(
                name=case.name,
                route="agent",
                passed=False,
                duration_seconds=duration,
                detail="stdout did not contain valid JSON payload",
            )

        missing = [key for key in case.required_keys if key not in payload]
        if missing:
            return SmokeResult(
                name=case.name,
                route="agent",
                passed=False,
                duration_seconds=duration,
                detail=f"missing keys: {missing}",
            )

        return SmokeResult(
            name=case.name,
            route="agent",
            passed=True,
            duration_seconds=duration,
            detail="ok",
        )

    def _run_human_case(self, case: HumanCase) -> SmokeResult:
        start = time.monotonic()
        gateway_address = f"127.0.0.1:{case.port}"
        processes: list[subprocess.Popen[str]] = []
        try:
            server_process = self._start_background(
                case.server_script,
                extra_env={"EASYREMOTE_PORT": str(case.port)},
            )
            processes.append(server_process)

            if not self._wait_for_port("127.0.0.1", case.port, timeout_seconds=15.0):
                return SmokeResult(
                    name=case.name,
                    route="human",
                    passed=False,
                    duration_seconds=time.monotonic() - start,
                    detail="gateway port did not become ready",
                )

            for node_script in case.node_scripts:
                node_process = self._start_background(
                    node_script,
                    extra_env={"EASYREMOTE_GATEWAY_ADDRESS": gateway_address},
                )
                processes.append(node_process)

            # Wait for function registration/heartbeat.
            time.sleep(4.0)

            client_detail = ""
            success = False
            for attempt in range(1, 4):
                completed = subprocess.run(
                    self._python_command_for_script(case.client_script),
                    cwd=self.workspace_root,
                    capture_output=True,
                    text=True,
                    timeout=90,
                    env=self._base_env(
                        {"EASYREMOTE_GATEWAY_ADDRESS": gateway_address}
                    ),
                )
                if completed.returncode == 0:
                    success = True
                    client_detail = completed.stdout.strip() or "ok"
                    break
                client_detail = (
                    f"attempt={attempt}; exit={completed.returncode}; "
                    f"stderr={completed.stderr.strip()}"
                )
                time.sleep(2.0)

            duration = time.monotonic() - start
            if not success:
                return SmokeResult(
                    name=case.name,
                    route="human",
                    passed=False,
                    duration_seconds=duration,
                    detail=self._truncate(client_detail),
                )

            return SmokeResult(
                name=case.name,
                route="human",
                passed=True,
                duration_seconds=duration,
                detail=self._truncate(client_detail),
            )
        except subprocess.TimeoutExpired as exc:
            return SmokeResult(
                name=case.name,
                route="human",
                passed=False,
                duration_seconds=time.monotonic() - start,
                detail=f"timeout: {exc}",
            )
        finally:
            self._stop_background(processes)

    def _start_background(
        self,
        script: Path,
        extra_env: Optional[dict[str, str]] = None,
    ) -> subprocess.Popen[str]:
        return subprocess.Popen(
            self._python_command_for_script(script),
            cwd=self.workspace_root,
            env=self._base_env(extra_env),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    @staticmethod
    def _wait_for_port(host: str, port: int, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                with socket.create_connection((host, port), timeout=0.5):
                    return True
            except OSError:
                time.sleep(0.2)
        return False

    def _stop_background(self, processes: Iterable[subprocess.Popen[str]]) -> None:
        for process in processes:
            if process.poll() is None:
                process.terminate()

        for process in processes:
            if process.poll() is not None:
                continue
            try:
                process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=2)

    def _base_env(self, extra: Optional[dict[str, str]] = None) -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        if extra:
            env.update(extra)
        return env

    @staticmethod
    def _resolve_python_command_prefix() -> tuple[str, ...]:
        """
        Prefer uv-managed execution; fallback to current interpreter if uv is unavailable.
        """
        if shutil.which("uv"):
            return ("uv", "run", "--no-sync", "python")
        return (sys.executable,)

    def _python_command_for_script(self, script: Path) -> list[str]:
        return [*self._python_command_prefix, str(script)]

    @staticmethod
    def _extract_json_payload(stdout: str) -> Optional[dict[str, object]]:
        text = stdout.strip()
        if not text:
            return None

        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                return payload
            return None
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        try:
            payload = json.loads(text[start : end + 1])
            return payload if isinstance(payload, dict) else None
        except json.JSONDecodeError:
            return None

    def _print_summary(self) -> None:
        print("\nGallery Smoke Test Summary")
        print("=" * 60)
        for result in self.results:
            status = "PASS" if result.passed else "FAIL"
            print(
                f"[{status}] {result.route:<5} {result.name:<40} "
                f"({result.duration_seconds:.2f}s)"
            )
            if not result.passed:
                print(f"       detail: {result.detail}")

    def _write_report(self) -> None:
        report_path = self.gallery_root / "SMOKE_TEST_REPORT.md"
        generated_at = datetime.now(timezone.utc).isoformat()

        lines = [
            "# Gallery Smoke Test Report",
            "",
            "Author: Silan Hu (silan.hu@u.nus.edu)",
            "",
            f"Generated at (UTC): {generated_at}",
            "",
            "| Case | Route | Status | Duration(s) | Detail |",
            "|---|---|---:|---:|---|",
        ]

        for result in self.results:
            status = "PASS" if result.passed else "FAIL"
            detail = result.detail.replace("|", "\\|")
            lines.append(
                f"| {result.name} | {result.route} | {status} | "
                f"{result.duration_seconds:.2f} | {detail} |"
            )

        failed = [result for result in self.results if not result.passed]
        lines.extend(["", "## Conclusion", ""])
        if failed:
            lines.append(
                f"{len(failed)} case(s) failed. Please inspect logs and fix before release."
            )
        else:
            lines.append("All smoke cases passed.")

        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _truncate(text: str, limit: int = 220) -> str:
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3] + "..."


def main() -> int:
    workspace_root = Path(__file__).resolve().parents[1]
    tester = GallerySmokeTester(workspace_root=workspace_root)
    return tester.run()


if __name__ == "__main__":
    raise SystemExit(main())
