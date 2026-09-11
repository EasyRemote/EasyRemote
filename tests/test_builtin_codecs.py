"""Built-in codecs for widely used scientific types resolve without setup."""

import json
import sys

import pytest

from easyremote.value_codec import codec_for


def roundtrip(annotation, value):
    """Encode, force it through real JSON, decode — the invocation path."""
    codec = codec_for(annotation)
    assert codec is not None, f"no built-in codec for {annotation}"
    return codec.decode(json.loads(json.dumps(codec.encode(value))))


# -- import cost ------------------------------------------------------------


def test_optional_libraries_are_never_imported_to_resolve_other_types():
    """A codec for an absent library must cost nothing. Importing eagerly
    would make every user pay for libraries they do not have."""
    before = {m for m in ("torch", "pandas", "PIL", "pyarrow") if m in sys.modules}

    class Unrelated:
        pass

    for annotation in (int, str, dict, list, bytes, Unrelated):
        assert codec_for(annotation) is None

    after = {m for m in ("torch", "pandas", "PIL", "pyarrow") if m in sys.modules}
    assert after == before, "resolving ordinary types imported an optional library"


# -- torch ------------------------------------------------------------------


def test_torch_tensor_roundtrips_without_registration():
    torch = pytest.importorskip("torch")

    original = torch.arange(6, dtype=torch.float32).reshape(2, 3)
    restored = roundtrip(torch.Tensor, original)

    assert restored.dtype == original.dtype
    assert tuple(restored.shape) == tuple(original.shape)
    assert torch.equal(restored, original)


def test_torch_bfloat16_survives_because_numpy_is_not_in_the_path():
    """bfloat16 has no NumPy equivalent, so a `.numpy()` bridge would lose it."""
    torch = pytest.importorskip("torch")

    original = torch.tensor([1.0, 2.5, -3.25], dtype=torch.bfloat16)
    restored = roundtrip(torch.Tensor, original)

    assert restored.dtype == torch.bfloat16
    assert torch.equal(restored, original)


@pytest.mark.parametrize(
    "make",
    [
        pytest.param(lambda t: t.tensor(42.0), id="zero_dim_scalar"),
        pytest.param(lambda t: t.empty((0, 3), dtype=t.float32), id="empty"),
        pytest.param(lambda t: t.tensor([1 + 2j], dtype=t.complex64), id="complex64"),
        pytest.param(lambda t: t.tensor([True, False]), id="bool"),
        pytest.param(lambda t: t.tensor([-128, 127], dtype=t.int8), id="int8"),
        pytest.param(lambda t: t.randn(2, 3, 4), id="three_dim"),
    ],
)
def test_torch_shape_and_dtype_edge_cases(make):
    torch = pytest.importorskip("torch")

    original = make(torch)
    restored = roundtrip(torch.Tensor, original)

    assert restored.dtype == original.dtype
    assert tuple(restored.shape) == tuple(original.shape)
    assert torch.equal(restored, original)


def test_torch_non_contiguous_tensor_keeps_its_values():
    """A transposed view's storage is not row-major; sending it raw would
    silently transpose the values back."""
    torch = pytest.importorskip("torch")

    original = torch.arange(12, dtype=torch.float32).reshape(3, 4).T
    restored = roundtrip(torch.Tensor, original)

    assert tuple(restored.shape) == (4, 3)
    assert torch.equal(restored, original.contiguous())


def test_torch_tensor_subclass_keeps_the_tensor_wire_shape():
    """`nn.Parameter` is a Tensor. Falling through to the generic object
    encoder would lose its dtype and values."""
    torch = pytest.importorskip("torch")

    parameter = torch.nn.Parameter(torch.randn(2, 2))

    assert codec_for(type(parameter)) is not None


def test_torch_requires_grad_is_refused_rather_than_silently_detached():
    """The autograd graph does not cross the wire; detaching quietly would
    hand back a tensor the caller still believes is differentiable."""
    torch = pytest.importorskip("torch")

    codec = codec_for(torch.Tensor)

    with pytest.raises(ValueError, match="requires grad"):
        codec.encode(torch.ones(2, requires_grad=True))


def test_torch_oversized_tensor_is_refused_with_a_usable_message():
    torch = pytest.importorskip("torch")
    from easyremote import _torch_codec

    codec = codec_for(torch.Tensor)
    too_big = torch.empty(_torch_codec.MAX_TENSOR_BYTES // 4 + 8, dtype=torch.float32)

    with pytest.raises(ValueError, match="chunked transfer"):
        codec.encode(too_big)


# -- pandas -----------------------------------------------------------------


def test_pandas_dataframe_keeps_index_and_dtypes():
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")

    original = pd.DataFrame(
        {
            "a": [1, 2],
            "b": ["x", "y"],
            "t": pd.to_datetime(["2024-01-01", "2024-06-01"]),
        }
    ).set_index("a")

    restored = roundtrip(pd.DataFrame, original)

    assert restored.equals(original)
    assert list(restored.dtypes) == list(original.dtypes)
    assert restored.index.name == "a"


def test_pandas_series_keeps_its_name():
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")

    original = pd.Series([1.5, 2.5], name="vals")
    restored = roundtrip(pd.Series, original)

    assert restored.equals(original)
    assert restored.name == "vals"


# -- Pillow -----------------------------------------------------------------


def test_pillow_image_pixels_survive_exactly():
    Image = pytest.importorskip("PIL.Image")

    original = Image.new("RGB", (4, 3))
    original.putpixel((0, 0), (255, 128, 7))
    original.putpixel((3, 2), (1, 2, 3))

    restored = roundtrip(Image.Image, original)

    assert restored.size == original.size
    assert restored.getpixel((0, 0)) == (255, 128, 7)
    assert restored.getpixel((3, 2)) == (1, 2, 3)


# -- regression -------------------------------------------------------------


def test_numpy_codec_still_resolves():
    np = pytest.importorskip("numpy")

    original = np.arange(6, dtype=">f8").reshape(2, 3)
    restored = roundtrip(np.ndarray, original)

    assert restored.dtype == original.dtype
    assert (restored == original).all()


def test_explicit_registration_still_wins_over_a_built_in():
    """A caller who registers their own codec must keep their wire shape."""
    from easyremote import ValueCodec, register_value_codec

    class Marker:
        def __init__(self, n):
            self.n = n

    register_value_codec(
        ValueCodec(
            Marker,
            {"type": "integer"},
            lambda v: v.n,
            lambda v: Marker(v),
        )
    )

    assert codec_for(Marker) is not None
    assert roundtrip(Marker, Marker(7)).n == 7
