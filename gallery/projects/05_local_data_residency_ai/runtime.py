#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Agent protocol runtime for local data residency AI project.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import hashlib
from typing import Any

from easyremote.protocols import FunctionDescriptor, FunctionInvocation, ProtocolRuntime


class LocalResidencyProtocolRuntime(ProtocolRuntime):
    """
    Runtime that returns only sanitized and policy-compliant outputs.
    """

    @staticmethod
    def _stable_hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]

    async def list_functions(self) -> list[FunctionDescriptor]:
        return [
            FunctionDescriptor(
                name="sanitize_claim_record",
                description="Sanitize claim record for privacy compliance",
                node_ids=["local-secure-node"],
                tags=["privacy", "residency"],
            ),
            FunctionDescriptor(
                name="assess_claim_risk",
                description="Assess risk from non-PII factors",
                node_ids=["local-secure-node"],
                tags=["risk", "residency"],
            ),
        ]

    async def execute_invocation(self, invocation: FunctionInvocation) -> Any:
        if invocation.function_name == "sanitize_claim_record":
            record = dict(invocation.kwargs.get("record", {}))
            patient_id = str(record.get("patient_id", ""))
            email = str(record.get("email", ""))

            sanitized = dict(record)
            sanitized.pop("email", None)
            sanitized.pop("phone", None)
            sanitized["patient_hash"] = self._stable_hash(patient_id)
            sanitized["email_hash"] = self._stable_hash(email) if email else ""
            sanitized["data_residency"] = "local_only"
            return sanitized

        if invocation.function_name == "assess_claim_risk":
            amount = float(invocation.kwargs.get("amount", 0.0))
            anomalies = int(invocation.kwargs.get("anomaly_count", 0))
            score = round(min(100.0, amount / 1000.0 + anomalies * 7.5), 3)
            return {
                "risk_score": score,
                "risk_level": "high" if score >= 70 else "medium" if score >= 35 else "low",
                "data_residency": "local_only",
            }

        raise ValueError(f"Unknown data residency function: {invocation.function_name}")
