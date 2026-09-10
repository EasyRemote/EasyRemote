"""Real paired Runtime acceptance: rich values and incremental duplex media.

Run provider and caller roles on separate devices with matching candidate builds.
No fake transport, credentials, signer or admission bypass is used here.
"""

import argparse
import base64
import json
import signal
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from easynet_sdk import BidiStreamDescriptor as StreamSpec
from pydantic import BaseModel

from easyremote import (
    CallTarget,
    Client,
    ComputeNode,
    Duplex,
    FreshRoot,
    ResolvedTargetSubject,
    StreamFrame,
    ValueCodec,
    register_value_codec,
)


class Job:
    def __init__(self, name: str):
        self.name = name


register_value_codec(
    ValueCodec(
        Job,
        {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
        lambda job: {"name": job.name},
        lambda value: Job(value["name"]),
    )
)


@dataclass
class Batch:
    job: Job
    values: np.ndarray


class Report(BaseModel):
    name: str
    count: int


def provide(ready: Path) -> None:
    node = ComputeNode(namespace="acceptance")

    @node.register
    def transform(batch: Batch) -> Batch:
        assert isinstance(batch.job, Job)
        assert isinstance(batch.values, np.ndarray)
        return Batch(Job(batch.job.name + "-done"), batch.values.copy())

    @node.register
    def summarize(report: Report) -> Report:
        assert isinstance(report, Report)
        return Report(name=report.name, count=report.count + 1)

    @node.register
    def countdown(n: int):
        for tick in range(n, 0, -1):
            yield {"tick": tick}

    @node.register
    async def async_countdown(n: int):
        for tick in range(n, 0, -1):
            yield {"tick": tick}

    @node.register
    def media_echo(channel: Duplex) -> None:
        count = 0
        for frame in channel:
            channel.send(frame)
            count += 1
        channel.send({"received": count})

    @node.register
    async def async_media_echo(channel: Duplex) -> None:
        count = 0
        async for frame in channel:
            await channel.asend(frame)
            count += 1
        await channel.asend({"received": count})

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    node.start()
    try:
        ready.write_text(
            json.dumps({"abilities": [a.qualified_name for a in node.abilities]})
        )
        stop.wait()
    finally:
        ready.unlink(missing_ok=True)
        node.stop()


def consume(node_id: str, case: str = "all") -> None:
    client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))
    owner = client.device(node_id)
    catalog = client.abilities.list_device(owner.device_ura)
    assert any(row.name == "acceptance.transform" for row in catalog)

    results = {"duplex": {}}
    if case in ("all", "objects"):

        @owner.remote(name="acceptance.transform")
        def transform(batch: Batch) -> Batch: ...

        @owner.remote(name="acceptance.summarize")
        def summarize(report: Report) -> Report: ...

        original = np.arange(12, dtype=">f8").reshape(3, 4)[:, ::2]
        result = transform(Batch(Job("inference"), original))
        assert isinstance(result, Batch) and isinstance(result.job, Job)
        assert result.job.name == "inference-done"
        assert result.values.dtype == original.dtype
        assert result.values.shape == original.shape
        assert result.values.tobytes() == original.tobytes()
        report = summarize(Report(name="model", count=2))
        assert isinstance(report, Report) and report.count == 3
        results["typed_objects"] = True
    if case in ("all", "streams"):
        results["server_streams"] = {}
        for function in ("countdown", "async_countdown"):
            for n in (0, 3):
                # Exhaustion includes the SDK's mandatory terminal transcript
                # verification; seeing progress alone is not a successful call.
                chunks = list(
                    client.stream(
                        CallTarget("acceptance." + function, node=node_id), n=n
                    )
                )
                assert [chunk for chunk in chunks if chunk is not None] == [
                    {"tick": tick} for tick in range(n, 0, -1)
                ], chunks
            results["server_streams"][function] = {
                "ordered_items": True,
                "empty_stream": True,
                "verified_completion": True,
            }
    if case in ("objects", "streams"):
        print(json.dumps(results, indent=2))
        return
    for function in ("media_echo", "async_media_echo"):
        deadline = time.monotonic() + 20
        payload = b"\x00\xffaudio\x01"
        with client.session(
            CallTarget("acceptance." + function, node=node_id),
            streams=[
                StreamSpec(stream_id=1, content_type="audio/pcm", ordering="STRICT"),
                StreamSpec(
                    stream_id=2, content_type="application/json", ordering="STRICT"
                ),
            ],
        ) as session:
            session.send_frame(StreamFrame(payload, "audio/pcm"), sequence=1)
            echoed = False
            for _ in range(16):
                frame = session.recv(timeout=max(0.001, deadline - time.monotonic()))
                assert frame and not frame.get("terminal"), (
                    "ended before incremental echo"
                )
                if frame.get("kind") == "data":
                    assert frame["stream_id"] == 1
                    assert base64.b64decode(frame["payload_base64"]) == payload
                    echoed = True
                    break
            assert echoed, "no echo before input half-close"
            session.close_send()
            terminal = None
            summary_received = False
            for _ in range(16):
                frame = session.recv(timeout=max(0.001, deadline - time.monotonic()))
                assert frame, "missing terminal outcome"
                if frame.get("kind") == "data":
                    assert frame["stream_id"] == 2, (
                        frame["stream_id"],
                        base64.b64decode(frame["payload_base64"]),
                    )
                    assert json.loads(base64.b64decode(frame["payload_base64"])) == {
                        "received": 1
                    }
                    summary_received = True
                if frame.get("terminal"):
                    terminal = frame
                    break
            assert summary_received, "missing JSON result on the declared second stream"
            assert terminal and terminal.get("terminal_receipt"), (
                "missing terminal receipt"
            )
            receipt = terminal["terminal_receipt"]
            assert receipt["state"] == "Completed", receipt["state"]
            assert receipt["cleanup_complete"] is True
            results["duplex"][function] = {
                "incremental_echo": True,
                "terminal_receipt": True,
                "json_stream": True,
            }
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=["provider", "caller"])
    parser.add_argument("--ready-file", type=Path)
    parser.add_argument("--node")
    parser.add_argument(
        "--case", choices=["all", "objects", "duplex", "streams"], default="all"
    )
    args = parser.parse_args()
    if args.role == "provider":
        if args.ready_file is None:
            parser.error("provider requires --ready-file")
        provide(args.ready_file)
    else:
        if not args.node:
            parser.error("caller requires --node")
        consume(args.node, args.case)
