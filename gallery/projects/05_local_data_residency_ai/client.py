"""Request a released projection without receiving the provider's source note."""

from pprint import pprint

from easyremote import Client, FreshRoot, ResolvedTargetSubject, remote

client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))


@remote(client=client)
def summarize_patient_record(record_id: str) -> dict[str, str | list[str]]: ...


if __name__ == "__main__":
    pprint(summarize_patient_record("case-1042"))
