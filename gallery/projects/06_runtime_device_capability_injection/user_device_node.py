#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
User device node for runtime camera/video capability injection.

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


def main() -> None:
    gateway = os.getenv("EASYREMOTE_GATEWAY_ADDRESS", "127.0.0.1:8084")
    user_id = os.getenv("USER_ID", "demo-user")
    node_id = os.getenv("NODE_ID", "user-device-{0}".format(user_id))
    auto_consent = os.getenv("EASYREMOTE_AUTO_CONSENT", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    node = ComputeNode(
        gateway_address=gateway,
        node_id=node_id,
        node_capabilities={"device", "camera", "voice", "user:{0}".format(user_id)},
    )
    # Start with an "empty" device surface and inject capabilities at runtime
    # via transferred code modules from the server-side agent.
    host = UserDeviceCapabilityHost(
        node,
        prefer_transferred_code=True,
        allow_transferred_code=True,
        auto_consent=auto_consent,
    )

    # Optional fallback: map to pre-approved local actions (disabled by default).
    if os.getenv("LOAD_SANDBOX_ACTIONS", "0").strip().lower() in {"1", "true", "yes", "on"}:
        host.load_sandbox(Path(__file__).parent / "sandbox")
    # Auto-register install/list skill management endpoints
    host.register_skill_endpoints(source="server-agent")
    node.serve()


if __name__ == "__main__":
    main()
