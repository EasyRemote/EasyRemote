"""Publish bounded CRM tools without exposing CRM credentials."""

import threading

from easyremote import ComputeNode, Context

node = ComputeNode(namespace="er")

ACCOUNTS = {
    "acme": {"name": "Acme Labs", "segment": "enterprise", "health": 82},
    "northstar": {"name": "Northstar Co", "segment": "growth", "health": 67},
}
REVENUE = {
    "acme": [124_000, 131_000, 139_000, 146_000, 151_000, 159_000],
    "northstar": [38_000, 41_000, 43_000, 42_000, 47_000, 52_000],
}
FOLLOWUP_OWNERS = {"alex", "jamie", "morgan", "riley"}


class FollowupStore:
    """Serialize fixture writes and replay one result per invocation."""

    def __init__(self, capacity: int = 100) -> None:
        self._by_invocation: dict[str, dict[str, str | int]] = {}
        self._capacity = capacity
        self._lock = threading.Lock()

    def create(
        self,
        *,
        invocation_id: str,
        requested_by: str,
        account_id: str,
        owner: str,
        due_in_days: int,
    ) -> dict[str, str | int]:
        with self._lock:
            existing = self._by_invocation.get(invocation_id)
            if existing is not None:
                return dict(existing)
            if len(self._by_invocation) >= self._capacity:
                raise ValueError("follow-up fixture capacity reached")

            task: dict[str, str | int] = {
                "task_id": f"followup-{len(self._by_invocation) + 1}",
                "account_id": account_id,
                "owner": owner,
                "due_in_days": due_in_days,
                "requested_by": requested_by,
                "invocation_id": invocation_id,
            }
            self._by_invocation[invocation_id] = task
            return dict(task)


FOLLOWUPS = FollowupStore()


def require_account(account_id: str) -> None:
    if account_id not in ACCOUNTS:
        raise ValueError(f"unknown account {account_id!r}")


@node.register(description="Read one account projection by stable identifier.")
def lookup_account(account_id: str) -> dict[str, str | int]:
    require_account(account_id)
    return {"account_id": account_id, **ACCOUNTS[account_id]}


@node.register(description="Read a bounded monthly revenue series.")
def revenue_trend(account_id: str, months: int = 3) -> list[int]:
    require_account(account_id)
    if not 1 <= months <= 6:
        raise ValueError("months must be between 1 and 6")
    return REVENUE[account_id][-months:]


@node.register(description="Create one caller-attributed sales follow-up.")
def create_followup(
    ctx: Context,
    account_id: str,
    owner: str,
    due_in_days: int,
) -> dict[str, str | int]:
    require_account(account_id)
    if owner not in FOLLOWUP_OWNERS:
        raise ValueError(f"owner must be one of {sorted(FOLLOWUP_OWNERS)}")
    if not 1 <= due_in_days <= 30:
        raise ValueError("due_in_days must be between 1 and 30")
    return FOLLOWUPS.create(
        invocation_id=ctx.invocation_id,
        requested_by=ctx.caller,
        account_id=account_id,
        owner=owner,
        due_in_days=due_in_days,
    )


if __name__ == "__main__":
    node.serve()
