#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Client-sandbox node for remote robot deployment/operations.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from easyremote import ComputeNode, UserDeviceCapabilityHost  # noqa: E402


def _env_flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    gateway = os.getenv("EASYREMOTE_GATEWAY_ADDRESS", "127.0.0.1:8085")
    user_id = os.getenv("USER_ID", "demo-user")
    node_id = os.getenv("NODE_ID", "robot-sandbox-{0}".format(user_id))

    node = ComputeNode(
        gateway_address=gateway,
        node_id=node_id,
        node_capabilities={
            "device",
            "robot",
            "sandbox",
            "client-sandbox",
            "user:{0}".format(user_id),
        },
    )

    host = UserDeviceCapabilityHost(
        node,
        prefer_transferred_code=True,
        allow_transferred_code=_env_flag("ALLOW_TRANSFERRED_CODE", "1"),
        auto_consent=_env_flag("EASYREMOTE_AUTO_CONSENT", "1"),
    )

    if _env_flag("LOAD_SANDBOX_ACTIONS", "1"):
        host.try_load_sandbox(Path(__file__).parent / "sandbox")

    host.register_skill_endpoints(source="commander-agent")
    node.serve()


if __name__ == "__main__":
    main()
