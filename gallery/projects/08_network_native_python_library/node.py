"""Own the semantic-operator implementation without distributing it."""

import re

from easyremote import ComputeNode

node = ComputeNode(namespace="lotus")

MAX_RECORDS = 1_000
MAX_RECORD_LENGTH = 2_000
MAX_CONDITION_LENGTH = 500


def _terms(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower()))


def _validate_records(records: list[str]) -> None:
    if not 1 <= len(records) <= MAX_RECORDS:
        raise ValueError("records must contain between 1 and 1,000 items")
    if any(not item.strip() or len(item) > MAX_RECORD_LENGTH for item in records):
        raise ValueError("each record must contain between 1 and 2,000 characters")


@node.register(description="Keep records that semantically match a condition.")
def semantic_filter(records: list[str], condition: str) -> list[str]:
    _validate_records(records)
    if not condition.strip() or len(condition) > MAX_CONDITION_LENGTH:
        raise ValueError("condition must contain between 1 and 500 characters")
    condition_terms = _terms(condition)
    if not condition_terms:
        raise ValueError("condition must contain searchable letters or numbers")
    return [record for record in records if _terms(record) & condition_terms]


@node.register(description="Apply one bounded semantic instruction to records.")
def semantic_map(records: list[str], instruction: str) -> list[str]:
    _validate_records(records)
    normalized = instruction.strip().lower()
    if normalized == "normalize whitespace":
        return [" ".join(record.split()) for record in records]
    if normalized == "lowercase":
        return [record.lower() for record in records]
    raise ValueError("instruction must be 'normalize whitespace' or 'lowercase'")


if __name__ == "__main__":
    node.serve()
