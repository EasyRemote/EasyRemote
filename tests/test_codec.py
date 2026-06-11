"""Data fidelity: annotation-driven rehydration and JSON lowering."""

import base64
import enum
from dataclasses import dataclass

import pytest

from easyremote._host import codec
from easyremote._host.server import HostedFunction
from easyremote.errors import InvalidArgument
from easyremote.schema import derive


@dataclass
class Job:
    name: str
    priority: int = 0


@dataclass
class Batch:
    jobs: list[Job]
    blob: bytes


class Color(enum.Enum):
    RED = "red"
    BLUE = "blue"


# -- rehydrate -----------------------------------------------------------------


def test_dataclass_param_arrives_as_object():
    job = codec.rehydrate({"name": "train", "priority": 3}, Job)
    assert isinstance(job, Job)
    assert job.name == "train"  # attribute access works


def test_nested_dataclass_list_and_bytes():
    batch = codec.rehydrate(
        {"jobs": [{"name": "a"}, {"name": "b", "priority": 1}], "blob": "AAEC"},
        Batch,
    )
    assert [j.name for j in batch.jobs] == ["a", "b"]
    assert isinstance(batch.jobs[0], Job)
    assert batch.blob == b"\x00\x01\x02"


def test_pydantic_duck_typing():
    class FakeModel:
        @classmethod
        def model_validate(cls, value):
            instance = cls()
            instance.data = value
            return instance

    model = codec.rehydrate({"x": 1}, FakeModel)
    assert isinstance(model, FakeModel)
    assert model.data == {"x": 1}


def test_tuple_set_enum_optional():
    assert codec.rehydrate([1, "a"], tuple[int, str]) == (1, "a")
    assert codec.rehydrate([1, 2, 2], set[int]) == {1, 2}
    assert codec.rehydrate([1], frozenset[int]) == frozenset({1})
    assert codec.rehydrate("red", Color) is Color.RED
    assert codec.rehydrate(None, Job | None) is None
    assert isinstance(codec.rehydrate({"name": "x"}, Job | None), Job)


def test_dict_values_rehydrated():
    out = codec.rehydrate({"k": {"name": "x"}}, dict[str, Job])
    assert isinstance(out["k"], Job)


# -- to_jsonable ----------------------------------------------------------------


def test_dataclass_result_lowers_recursively():
    lowered = codec.to_jsonable(Batch(jobs=[Job(name="a")], blob=b"\x01"))
    assert lowered == {
        "jobs": [{"name": "a", "priority": 0}],
        "blob": base64.b64encode(b"\x01").decode(),
    }


def test_model_set_tuple_enum_results():
    class FakeModel:
        def model_dump(self, mode="python"):
            return {"mode": mode}

    assert codec.to_jsonable(FakeModel()) == {"mode": "json"}
    assert sorted(codec.to_jsonable({1, 2})) == [1, 2]
    assert codec.to_jsonable((1, "a")) == [1, "a"]
    assert codec.to_jsonable(Color.BLUE) == "blue"


# -- through the host -----------------------------------------------------------


def test_host_round_trips_rich_types_end_to_end():
    def submit(job: Job, tags: tuple[str, ...] = ()) -> Job:
        assert isinstance(job, Job)
        return Job(name=f"{job.name}+{','.join(tags)}", priority=job.priority + 1)

    hosted = HostedFunction(name="er.submit", fn=submit, signature=derive(submit))
    result = hosted.call({"job": {"name": "x", "priority": 1}, "tags": ["a", "b"]})
    assert result == {"name": "x+a,b", "priority": 2}


def test_bad_value_for_annotation_is_argument_mismatch():
    def takes(color: Color) -> str:
        return color.value

    hosted = HostedFunction(name="er.takes", fn=takes, signature=derive(takes))
    with pytest.raises(InvalidArgument) as exc_info:
        hosted.call({"color": "magenta"})
    assert exc_info.value.reason == "argument_mismatch"
