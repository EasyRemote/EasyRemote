"""Call the remote quote function through a typed local stub."""

from pprint import pprint

from easyremote import Client, FreshRoot, ResolvedTargetSubject, remote

client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))


@remote(client=client)
def calculate_quote(
    seats: int,
    plan: str = "team",
    annual: bool = True,
) -> dict[str, str | int]: ...


if __name__ == "__main__":
    pprint(calculate_quote(seats=48, plan="team", annual=True))
