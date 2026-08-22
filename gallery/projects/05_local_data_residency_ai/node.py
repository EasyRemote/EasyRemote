"""Release a sanitized projection while source records remain provider-local."""

from easyremote import ComputeNode, Context

node = ComputeNode(namespace="er")

PRIVATE_RECORDS = {
    "case-1042": {
        "patient_name": "Synthetic Alice",
        "note": (
            "Synthetic Alice reports persistent cough and shortness of breath. "
            "Recent temperature is 38.4 C. Follow-up imaging is scheduled."
        ),
    },
    "case-2088": {
        "patient_name": "Synthetic Bob",
        "note": (
            "Synthetic Bob reports improved mobility after treatment. "
            "No acute symptoms are recorded."
        ),
    },
}
RISK_TERMS = {
    "respiratory": ("cough", "shortness of breath"),
    "fever": ("fever", "38."),
}


def sanitize(note: str, patient_name: str) -> str:
    redacted = note.replace(patient_name, "The patient")
    return redacted[:157] + "..." if len(redacted) > 160 else redacted


@node.register(description="Return a bounded sanitized patient-record projection.")
def summarize_patient_record(
    ctx: Context, record_id: str
) -> dict[str, str | list[str]]:
    try:
        record = PRIVATE_RECORDS[record_id]
    except KeyError as exc:
        raise ValueError("record is unavailable") from exc

    note = record["note"]
    labels = [
        label
        for label, terms in RISK_TERMS.items()
        if any(term in note.lower() for term in terms)
    ]
    return {
        "record_id": record_id,
        "summary": sanitize(note, record["patient_name"]),
        "risk_labels": labels,
        "requested_by": ctx.caller,
        "invocation_id": ctx.invocation_id,
    }


if __name__ == "__main__":
    node.serve()
