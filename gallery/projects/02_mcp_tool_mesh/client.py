"""Exercise three enterprise functions through typed remote tool stubs."""

from pprint import pprint

from easyremote import Client, FreshRoot, ResolvedTargetSubject, remote

client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))


@remote(client=client)
def lookup_account(account_id: str) -> dict[str, str | int]: ...


@remote(client=client)
def revenue_trend(account_id: str, months: int = 3) -> list[int]: ...


@remote(client=client)
def create_followup(
    account_id: str,
    owner: str,
    due_in_days: int,
) -> dict[str, str | int]: ...


if __name__ == "__main__":
    pprint(lookup_account("acme"))
    print("revenue:", revenue_trend("acme", months=4))
    pprint(create_followup("acme", owner="alex", due_in_days=5))
