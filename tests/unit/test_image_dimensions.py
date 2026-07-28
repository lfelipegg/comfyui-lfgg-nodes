import sys
import types
from importlib import import_module

import pytest
import torch

MAX_RESOLUTION = 16_384


@pytest.fixture(autouse=True)
def comfy_nodes(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "nodes",
        types.SimpleNamespace(MAX_RESOLUTION=MAX_RESOLUTION),
    )


def image_nodes():
    try:
        module = import_module("lfgg_nodes.image_dimensions")
    except ModuleNotFoundError:
        pytest.fail("image-derived sizing nodes are not implemented")
    return module.ImageDimensionsByLongSide(), module.ImageDimensionsByPixelBudget()


def resize_node():
    try:
        module = import_module("lfgg_nodes.image_dimensions")
        return module.ResizeImageByLongSide()
    except (AttributeError, ModuleNotFoundError):
        pytest.fail("resize-by-long-side node is not implemented")


def test_resize_by_long_side_uses_shared_dimensions_and_native_method(monkeypatch):
    calls = []

    def common_upscale(image, width, height, method, crop):
        calls.append((image.shape, width, height, method, crop))
        return torch.empty((image.shape[0], image.shape[1], height, width))

    comfy_utils = types.ModuleType("comfy.utils")
    comfy_utils.common_upscale = common_upscale
    comfy = types.ModuleType("comfy")
    comfy.utils = comfy_utils
    monkeypatch.setitem(sys.modules, "comfy", comfy)
    monkeypatch.setitem(sys.modules, "comfy.utils", comfy_utils)
    image = torch.zeros((2, 108, 192, 3))

    resized, width, height = resize_node().resize(
        image,
        long_side=128,
        divisible_by=8,
        upscale_method="lanczos",
    )

    assert calls == [(torch.Size([2, 3, 108, 192]), 128, 72, "lanczos", "disabled")]
    assert resized.shape == (2, 72, 128, 3)
    assert (width, height) == (128, 72)


def test_resize_by_long_side_restores_lanczos_grayscale_channel(monkeypatch):
    def common_upscale(image, width, height, method, crop):
        assert image.shape[1] == 1
        assert (method, crop) == ("lanczos", "disabled")
        return torch.zeros((image.shape[0], height, width))

    comfy_utils = types.ModuleType("comfy.utils")
    comfy_utils.common_upscale = common_upscale
    comfy = types.ModuleType("comfy")
    comfy.utils = comfy_utils
    monkeypatch.setitem(sys.modules, "comfy", comfy)
    monkeypatch.setitem(sys.modules, "comfy.utils", comfy_utils)

    resized, width, height = resize_node().resize(
        torch.zeros((1, 32, 64, 1)),
        long_side=32,
        divisible_by=1,
        upscale_method="lanczos",
    )

    assert resized.shape == (1, 16, 32, 1)
    assert (width, height) == (32, 16)


def test_resize_by_long_side_returns_aligned_source_without_resampling(monkeypatch):
    monkeypatch.delitem(sys.modules, "comfy", raising=False)
    monkeypatch.delitem(sys.modules, "comfy.utils", raising=False)
    image = torch.rand((2, 240, 320, 3))

    resized, width, height = resize_node().resize(
        image,
        long_side=1024,
        divisible_by=8,
        upscale_method="lanczos",
    )

    assert resized is image
    assert (width, height) == (320, 240)


def test_resize_by_long_side_rejects_unknown_upscale_method():
    with pytest.raises(ValueError, match="upscale_method"):
        resize_node().resize(
            torch.empty((1, 240, 320, 3)),
            long_side=1024,
            divisible_by=8,
            upscale_method="unknown",
        )


@pytest.mark.parametrize(
    ("image", "message"),
    [
        (torch.empty((1, 2, 2, 2)), "C equal to 1, 3, or 4"),
        (torch.empty((1, 2, 2, 3), dtype=torch.int64), "floating-point"),
        (torch.full((1, 2, 2, 3), float("nan")), "finite"),
        (torch.empty((1, 3, 3, 3)), "at most 8 pixels"),
    ],
)
def test_resize_by_long_side_rejects_unsafe_image_boundaries(
    monkeypatch,
    image,
    message,
):
    module = import_module("lfgg_nodes.image_dimensions")
    monkeypatch.setattr(module, "MAX_RESIZE_PIXELS", 8, raising=False)

    with pytest.raises(ValueError, match=message):
        resize_node().resize(
            image,
            long_side=16,
            divisible_by=1,
            upscale_method="lanczos",
        )


def test_long_side_downscales_a_batch_without_growing_either_axis():
    long_side, _ = image_nodes()
    image = torch.empty((2, 1080, 1920, 3))

    width, height = long_side.calculate(image, long_side=1024, divisible_by=64)

    assert (width, height) == (1024, 576)
    assert width <= image.shape[2]
    assert height <= image.shape[1]


def test_long_side_keeps_an_already_small_aligned_image():
    long_side, _ = image_nodes()
    image = torch.empty((3, 240, 320, 4))

    assert long_side.calculate(image, long_side=1024, divisible_by=8) == (320, 240)


def test_long_side_prefers_aspect_fidelity_with_coarse_alignment():
    long_side, _ = image_nodes()
    image = torch.empty((1, 500, 400, 3))

    assert long_side.calculate(image, long_side=128, divisible_by=32) == (96, 128)


def test_pixel_budget_downscales_without_exceeding_the_budget():
    _, pixel_budget = image_nodes()
    image = torch.empty((2, 1080, 1920, 3))

    width, height = pixel_budget.calculate(
        image,
        max_pixels=1_000_000,
        divisible_by=64,
    )

    assert (width, height) == (1024, 576)
    assert width * height <= 1_000_000
    assert width <= image.shape[2]
    assert height <= image.shape[1]


def test_pixel_budget_keeps_an_already_small_aligned_image():
    _, pixel_budget = image_nodes()
    image = torch.empty((4, 240, 320, 3))

    assert pixel_budget.calculate(
        image,
        max_pixels=1_048_576,
        divisible_by=8,
    ) == (320, 240)


@pytest.mark.parametrize(
    "image",
    [
        object(),
        torch.empty((10, 10, 3)),
        torch.empty((0, 10, 10, 3)),
        torch.empty((1, 0, 10, 3)),
        torch.empty((1, 10, 0, 3)),
        torch.empty((1, 10, 10, 0)),
    ],
)
def test_image_nodes_reject_invalid_tensor_types_and_shapes(image):
    long_side, pixel_budget = image_nodes()

    with pytest.raises(ValueError, match=r"IMAGE.*\[B,H,W,C\].*positive"):
        long_side.calculate(image, long_side=1024, divisible_by=8)
    with pytest.raises(ValueError, match=r"IMAGE.*\[B,H,W,C\].*positive"):
        pixel_budget.calculate(image, max_pixels=1_048_576, divisible_by=8)


@pytest.mark.parametrize(
    ("node_name", "arguments", "message"),
    [
        ("long", {"long_side": 15, "divisible_by": 8}, "long_side"),
        (
            "long",
            {"long_side": MAX_RESOLUTION + 1, "divisible_by": 8},
            "long_side",
        ),
        ("long", {"long_side": 1024, "divisible_by": 0}, "divisible_by"),
        ("pixel", {"max_pixels": 0, "divisible_by": 8}, "max_pixels"),
        (
            "pixel",
            {"max_pixels": MAX_RESOLUTION**2 + 1, "divisible_by": 8},
            "max_pixels",
        ),
        ("pixel", {"max_pixels": 1_048_576, "divisible_by": True}, "divisible_by"),
    ],
)
def test_image_nodes_reject_invalid_api_bounds(node_name, arguments, message):
    long_side, pixel_budget = image_nodes()
    node = long_side if node_name == "long" else pixel_budget

    with pytest.raises(ValueError, match=message):
        node.calculate(torch.empty((1, 64, 64, 3)), **arguments)


@pytest.mark.parametrize("node_name", ["long", "pixel"])
def test_image_nodes_reject_impossible_alignment(node_name):
    long_side, pixel_budget = image_nodes()
    image = torch.empty((1, 32, 32, 3))

    with pytest.raises(ValueError, match="No positive aligned dimensions"):
        if node_name == "long":
            long_side.calculate(image, long_side=32, divisible_by=64)
        else:
            pixel_budget.calculate(image, max_pixels=1024, divisible_by=64)


@pytest.mark.parametrize("node_name", ["long", "pixel"])
def test_image_nodes_only_inspect_tensor_shape(node_name):
    long_side, pixel_budget = image_nodes()
    image = torch.arange(2 * 24 * 32 * 3, dtype=torch.float64).reshape(
        (2, 24, 32, 3)
    )
    before = image.clone()
    identity = id(image)
    storage = image.data_ptr()
    shape = image.shape
    dtype = image.dtype
    device = image.device

    if node_name == "long":
        long_side.calculate(image, long_side=1024, divisible_by=8)
    else:
        pixel_budget.calculate(image, max_pixels=1_048_576, divisible_by=8)

    assert id(image) == identity
    assert image.data_ptr() == storage
    assert image.shape == shape
    assert image.dtype == dtype
    assert image.device == device
    assert torch.equal(image, before)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA is unavailable")
def test_image_nodes_only_inspect_cuda_tensor_shape():
    long_side, pixel_budget = image_nodes()
    image = torch.empty((2, 240, 320, 3), device="cuda")
    storage = image.data_ptr()

    assert long_side.calculate(image, long_side=1024, divisible_by=8) == (320, 240)
    assert pixel_budget.calculate(
        image,
        max_pixels=1_048_576,
        divisible_by=8,
    ) == (320, 240)
    assert image.data_ptr() == storage
    assert image.device.type == "cuda"
