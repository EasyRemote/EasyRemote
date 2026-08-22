"""Consume owned business functions without copying their implementations."""

from pprint import pprint

from easyremote import Client, FreshRoot, ResolvedTargetSubject, remote

client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))


@remote(client=client)
def normalize_invoice(amount_minor: int, currency: str) -> dict[str, str | int]: ...


@remote(client=client)
def classify_ticket(text: str) -> str: ...


@remote(client=client)
def score_customer_health(
    usage_percent: int,
    open_critical_tickets: int,
    days_since_contact: int,
) -> int: ...


if __name__ == "__main__":
    pprint(normalize_invoice(125_00, "EUR"))
    print("ticket:", classify_ticket("The latest invoice has a duplicate charge."))
    print("health:", score_customer_health(91, 1, 14))
