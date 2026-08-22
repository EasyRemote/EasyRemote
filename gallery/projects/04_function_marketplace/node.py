"""Publish three validated business functions owned by one provider team."""

from decimal import ROUND_HALF_UP, Decimal

from easyremote import ComputeNode

node = ComputeNode(namespace="er")

USD_PER_UNIT = {
    "USD": Decimal("1.00"),
    "EUR": Decimal("1.08"),
    "SGD": Decimal("0.74"),
}


@node.register(description="Normalize an invoice amount into USD cents.")
def normalize_invoice(amount_minor: int, currency: str) -> dict[str, str | int]:
    if currency not in USD_PER_UNIT:
        raise ValueError(f"currency must be one of {sorted(USD_PER_UNIT)}")
    if not 0 <= amount_minor <= 100_000_000:
        raise ValueError("amount_minor must be between 0 and 100,000,000")
    usd_cents = (Decimal(amount_minor) * USD_PER_UNIT[currency]).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return {
        "source_currency": currency,
        "source_amount_minor": amount_minor,
        "usd_cents": int(usd_cents),
    }


@node.register(description="Classify one bounded customer-support ticket.")
def classify_ticket(text: str) -> str:
    normalized = text.strip().lower()
    if not normalized or len(normalized) > 2_000:
        raise ValueError("text must contain between 1 and 2,000 characters")
    categories = {
        "billing": ("invoice", "charge", "refund"),
        "reliability": ("down", "timeout", "unavailable"),
        "access": ("login", "password", "permission"),
    }
    return next(
        (
            category
            for category, terms in categories.items()
            if any(term in normalized for term in terms)
        ),
        "general",
    )


@node.register(description="Score customer health from bounded business facts.")
def score_customer_health(
    usage_percent: int,
    open_critical_tickets: int,
    days_since_contact: int,
) -> int:
    if not 0 <= usage_percent <= 100:
        raise ValueError("usage_percent must be between 0 and 100")
    if not 0 <= open_critical_tickets <= 20:
        raise ValueError("open_critical_tickets must be between 0 and 20")
    if not 0 <= days_since_contact <= 365:
        raise ValueError("days_since_contact must be between 0 and 365")
    return max(
        0,
        min(100, usage_percent - 12 * open_critical_tickets - days_since_contact // 7),
    )


if __name__ == "__main__":
    node.serve()
