#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Human route client for data residency AI project.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from easyremote import remote  # noqa: E402

GATEWAY_ADDRESS = os.getenv("EASYREMOTE_GATEWAY_ADDRESS", "127.0.0.1:8083")


@remote(
    function_name="sanitize_claim_record",
    node_id="local-secure-node",
    gateway_address=GATEWAY_ADDRESS,
)
def sanitize_claim_record(record: dict[str, object]) -> dict[str, object]:
    # Local fallback for static analysis/debugging; @remote wrapper executes remotely.
    sanitized = dict(record)
    sanitized.pop("email", None)
    sanitized.pop("phone", None)
    sanitized["data_residency"] = "local_only"
    return sanitized


@remote(
    function_name="assess_claim_risk",
    node_id="local-secure-node",
    gateway_address=GATEWAY_ADDRESS,
)
def assess_claim_risk(amount: float, anomaly_count: int) -> dict[str, object]:
    # Local fallback for static analysis/debugging; @remote wrapper executes remotely.
    score = round(min(100.0, amount / 1000.0 + anomaly_count * 7.5), 3)
    level = "high" if score >= 70 else "medium" if score >= 35 else "low"
    return {
        "risk_score": score,
        "risk_level": level,
        "data_residency": "local_only",
    }


class LocalResidencyClientDemo:
    """
    Demonstrates privacy-preserving processing flow.
    """

    def run(self) -> None:
        record = {
            "patient_id": "P-2026-001",
            "email": "alice@example.com",
            "phone": "+1-202-555-0101",
            "diagnosis_code": "DX-42",
            "claim_amount": 18500.0,
        }

        sanitized = sanitize_claim_record(record)
        risk = assess_claim_risk(amount=18500.0, anomaly_count=3)

        print(f"sanitize_claim_record => {sanitized}")
        print(f"assess_claim_risk => {risk}")


if __name__ == "__main__":
    LocalResidencyClientDemo().run()
