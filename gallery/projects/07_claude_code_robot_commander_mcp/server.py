#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gateway server for Claude-Code commander + robot sandbox MCP case.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from easyremote import Server  # noqa: E402


class ClaudeCommanderGatewayServer:
    """
    Gateway wrapper tuned for commander-to-sandbox traffic.
    """

    def __init__(self, port: int = 8085) -> None:
        self._server = Server(
            port=port,
            max_total_active_streams=256,
            max_streams_per_node=16,
            stream_response_queue_size=256,
        )

    def run(self) -> None:
        self._server.start()


if __name__ == "__main__":
    port = int(os.getenv("EASYREMOTE_PORT", "8085"))
    ClaudeCommanderGatewayServer(port=port).run()
