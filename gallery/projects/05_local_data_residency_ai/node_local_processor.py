#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Local processor node for data residency AI project.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import hashlib
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from easyremote import ComputeNode  # noqa: E402


class LocalResidencyNode:
    """
    Keeps raw records local and only returns sanitized output.
    """

    def __init__(self, gateway_address: str) -> None:
        self._node = ComputeNode(gateway_address=gateway_address, node_id="local-secure-node")
        self._register_functions()

    @staticmethod
    def _stable_hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]

    def _register_functions(self) -> None:
        @self._node.register(
            name="sanitize_claim_record",
            description="Redact direct PII and return pseudonymized record",
            tags={"privacy", "compliance", "residency"},
        )
        def sanitize_claim_record(record: dict[str, object]) -> dict[str, object]:
            patient_id = str(record.get("patient_id", ""))
            email = str(record.get("email", ""))

            sanitized = dict(record)
            sanitized.pop("email", None)
            sanitized.pop("phone", None)
            sanitized["patient_hash"] = self._stable_hash(patient_id)
            sanitized["email_hash"] = self._stable_hash(email) if email else ""
            sanitized["data_residency"] = "local_only"
            return sanitized

        @self._node.register(
            name="assess_claim_risk",
            description="Return risk score on sanitized factors",
            tags={"risk", "residency"},
        )
        def assess_claim_risk(amount: float, anomaly_count: int) -> dict[str, object]:
            score = round(min(100.0, amount / 1000.0 + anomaly_count * 7.5), 3)
            level = "high" if score >= 70 else "medium" if score >= 35 else "low"
            return {
                "risk_score": score,
                "risk_level": level,
                "data_residency": "local_only",
            }

    def serve(self) -> None:
        self._node.serve()


if __name__ == "__main__":
    gateway_address = os.getenv("EASYREMOTE_GATEWAY_ADDRESS", "127.0.0.1:8083")
    LocalResidencyNode(gateway_address=gateway_address).serve()
