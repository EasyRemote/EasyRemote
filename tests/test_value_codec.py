"""Python value fidelity across caller lowering and actual hosted execution."""

from dataclasses import dataclass

import pytest

from easyremote import Client, ValueCodec, _codec, register_value_codec, remote
from easyremote._host.server import HostedFunction
from easyremote.schema import derive

np = pytest.importorskip("numpy")
BaseModel = pytest.importorskip("pydantic").BaseModel


class Job:
    def __init__(self, name):
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
        lambda wire: Job(wire["name"]),
    )
)


@dataclass
class Batch:
    job: Job
    values: np.ndarray


class Report(BaseModel):
    name: str
    count: int


class HostClient(Client):
    def __init__(self, fn):
        self.host = HostedFunction(name="er.echo", fn=fn, signature=derive(fn))

    def call(self, target, **kwargs):
        return self.host.call(_codec.to_jsonable(kwargs))


def test_custom_dataclass_array_full_typed_call():
    def execute(batch: Batch) -> Batch:
        assert isinstance(batch.job, Job)
        assert isinstance(batch.values, np.ndarray)
        return Batch(Job(batch.job.name + "-done"), batch.values * 2)

    stub = remote(execute, client=HostClient(execute))
    source = np.arange(12, dtype=">i4").reshape(3, 4)[:, ::2]
    result = stub(Batch(Job("job"), source))
    assert isinstance(result, Batch)
    assert isinstance(result.job, Job)
    assert result.job.name == "job-done"
    np.testing.assert_array_equal(result.values, source * 2)


def test_real_pydantic_result_and_bound_stub():
    def execute(report: Report) -> Report:
        assert isinstance(report, Report)
        return Report(name=report.name, count=report.count + 1)

    class API:
        client = HostClient(execute)

        @remote
        def report(self, report: Report) -> Report: ...

    result = API().report(Report(name="ok", count=2))
    assert isinstance(result, Report)
    assert result.count == 3


@pytest.mark.parametrize(
    "source",
    [
        np.arange(12, dtype=">i4").reshape(3, 4)[:, ::2],
        np.array(2.5, dtype="float32"),
        np.empty((0, 3)),
        np.array([complex(1, 2)], dtype="complex128"),
        np.array([np.nan, np.inf, -0.0], dtype="float64"),
    ],
)
def test_array_exact_bytes_shape_dtype(source):
    restored = _codec.rehydrate(_codec.to_jsonable(source), np.ndarray)
    assert restored.dtype == source.dtype
    assert restored.shape == source.shape
    assert restored.tobytes() == source.tobytes()
    assert restored.flags.writeable


@pytest.mark.parametrize(
    "mutation",
    [
        {"dtype": "O"},
        {"shape": [-1]},
        {"shape": [True]},
        {"shape": [100_000_000]},
        {"data": "!!!!"},
        {"data": ""},
    ],
)
def test_array_rejects_malformed_before_allocation(mutation):
    wire = _codec.to_jsonable(np.array([1], dtype="int32"))
    wire.update(mutation)
    with pytest.raises(ValueError):
        _codec.rehydrate(wire, np.ndarray)


def test_object_dtype_rejected():
    with pytest.raises(ValueError):
        _codec.to_jsonable(np.array([Job("x")], dtype=object))


def test_duplicate_registration_rejected():
    with pytest.raises(ValueError, match="already registered"):
        register_value_codec(ValueCodec(Job, {}, lambda x: x, lambda x: x))


def test_actual_host_socket_rich_value_roundtrip(short_tmp):
    import socket

    from easyremote._host import HostServer
    from easyremote._host.protocol import (
        FrameKind,
        decode_item,
        receive_frame,
        request_frame,
    )

    def echo(batch: Batch) -> Batch:
        assert isinstance(batch.job, Job)
        assert isinstance(batch.values, np.ndarray)
        return batch

    original = Batch(Job("socket"), np.arange(6, dtype=">f8").reshape(2, 3))
    with HostServer(short_tmp / "rich.sock") as server:
        server.add(HostedFunction(name="er.echo", fn=echo, signature=derive(echo)))
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(5)
            connection.connect(str(server.socket_path))
            connection.sendall(
                request_frame(
                    {
                        "request": {
                            "fn": "er.echo",
                            "args": _codec.to_jsonable({"batch": original}),
                            "caller": "easynet:///r/acme/user/test-caller",
                            "call_id": "rich-1",
                        }
                    }
                ).to_bytes()
            )
            item = receive_frame(connection)
            assert item.kind is FrameKind.ITEM
            result = _codec.rehydrate(decode_item(item), Batch)
            terminal = receive_frame(connection)
            assert terminal.kind is FrameKind.TERMINAL
            assert terminal.sequence == 1
    assert isinstance(result.job, Job)
    assert result.job.name == original.job.name
    assert result.values.dtype == original.values.dtype
    assert result.values.shape == original.values.shape
    assert result.values.tobytes() == original.values.tobytes()
