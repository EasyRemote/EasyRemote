#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gateway entrypoint for the human-coded decorator route.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from easyremote import Server


class GatewayApplication:
    """
    Minimal gateway application wrapper.
    """

    def __init__(self, port: int = 8080) -> None:
        self._server = Server(port=port)

    def run(self) -> None:
        self._server.start()


if __name__ == "__main__":
    GatewayApplication(port=8080).run()
