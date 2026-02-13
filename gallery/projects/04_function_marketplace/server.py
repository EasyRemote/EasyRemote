#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gateway server for function marketplace quickstart.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from easyremote import Server  # noqa: E402


class MarketplaceGatewayServer:
    """
    Gateway process for marketplace functions.
    """

    def __init__(self, port: int = 8082) -> None:
        self._server = Server(port=port)

    def run(self) -> None:
        self._server.start()


if __name__ == "__main__":
    port = int(os.getenv("EASYREMOTE_PORT", "8082"))
    MarketplaceGatewayServer(port=port).run()
