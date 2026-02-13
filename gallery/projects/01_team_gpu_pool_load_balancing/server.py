#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gateway server for team GPU pool simulation.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from easyremote import Server  # noqa: E402


class TeamGpuGateway:
    """
    Gateway wrapper for load-balancing demo.
    """

    def __init__(self, port: int = 8081) -> None:
        self._server = Server(port=port)

    def run(self) -> None:
        self._server.start()


if __name__ == "__main__":
    port = int(os.getenv("EASYREMOTE_PORT", "8081"))
    TeamGpuGateway(port=port).run()
