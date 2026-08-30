"""Consume the remote operators through a generated native Python import."""

from pprint import pprint

from easyremote.silan.lotus import semantic_filter, semantic_map

RECORDS = [
    "Invoice 1042 contains a duplicate charge.",
    "The API latency is within its normal range.",
    "A refund is pending for invoice 1088.",
]


if __name__ == "__main__":
    print("Input records:")
    pprint(RECORDS)
    print("\nRecords matching 'invoice refund billing':")
    pprint(semantic_filter(RECORDS, "invoice refund billing"))
    print("\nLowercase projection:")
    pprint(semantic_map(RECORDS, "lowercase"))
