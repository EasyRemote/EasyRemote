"""Publish one bounded commercial quote calculation."""

from easyremote import ComputeNode

node = ComputeNode(namespace="er")

MONTHLY_PRICE_CENTS = {
    "starter": 1_500,
    "team": 3_900,
    "enterprise": 8_500,
}


@node.register(description="Calculate a validated seat-based product quote.")
def calculate_quote(
    seats: int,
    plan: str = "team",
    annual: bool = True,
) -> dict[str, str | int]:
    if plan not in MONTHLY_PRICE_CENTS:
        raise ValueError(f"plan must be one of {sorted(MONTHLY_PRICE_CENTS)}")
    if not 1 <= seats <= 5_000:
        raise ValueError("seats must be between 1 and 5,000")

    months = 12 if annual else 1
    subtotal = MONTHLY_PRICE_CENTS[plan] * seats * months
    discount = subtotal * 15 // 100 if annual else 0
    return {
        "plan": plan,
        "seats": seats,
        "billing_period": "annual" if annual else "monthly",
        "subtotal_cents": subtotal,
        "discount_cents": discount,
        "total_cents": subtotal - discount,
    }


if __name__ == "__main__":
    node.serve()
