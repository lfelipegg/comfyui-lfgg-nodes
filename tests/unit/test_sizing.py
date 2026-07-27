from importlib import import_module

import pytest

MAX_RESOLUTION = 16_384
PRESETS = [
    "1:1",
    "4:5",
    "5:4",
    "3:4",
    "4:3",
    "2:3",
    "3:2",
    "5:7",
    "7:5",
    "9:16",
    "16:9",
    "9:21",
    "21:9",
]
RECIPROCALS = [
    ("4:5", "5:4"),
    ("3:4", "4:3"),
    ("2:3", "3:2"),
    ("5:7", "7:5"),
    ("9:16", "16:9"),
    ("9:21", "21:9"),
]


def fit(
    aspect_ratio,
    long_side=1024,
    divisible_by=8,
    custom_ratio_width=1,
    custom_ratio_height=1,
):
    try:
        sizing = import_module("lfgg_nodes.sizing")
    except ModuleNotFoundError:
        pytest.fail("standard-library sizing helper is not implemented")

    return sizing.fit_aspect_ratio_dimensions(
        aspect_ratio=aspect_ratio,
        long_side=long_side,
        divisible_by=divisible_by,
        custom_ratio_width=custom_ratio_width,
        custom_ratio_height=custom_ratio_height,
        max_resolution=MAX_RESOLUTION,
    )


def fit_source(
    source_width,
    source_height,
    *,
    max_width,
    max_height,
    max_pixels=None,
    divisible_by=8,
):
    sizing = import_module("lfgg_nodes.sizing")
    return sizing.fit_source_dimensions(
        source_width=source_width,
        source_height=source_height,
        max_width=max_width,
        max_height=max_height,
        max_pixels=max_pixels,
        divisible_by=divisible_by,
        max_resolution=MAX_RESOLUTION,
    )


@pytest.mark.parametrize("aspect_ratio", PRESETS + ["Custom"])
def test_every_ratio_returns_positive_aligned_dimensions_under_the_cap(aspect_ratio):
    width, height = fit(
        aspect_ratio,
        long_side=1025,
        divisible_by=64,
        custom_ratio_width=13,
        custom_ratio_height=7,
    )

    assert 0 < width <= 1025
    assert 0 < height <= 1025
    assert width % 64 == 0
    assert height % 64 == 0


@pytest.mark.parametrize(("portrait", "landscape"), RECIPROCALS)
def test_reciprocal_presets_return_reciprocal_dimensions(portrait, landscape):
    portrait_width, portrait_height = fit(
        portrait, long_side=1025, divisible_by=64
    )
    landscape_width, landscape_height = fit(
        landscape, long_side=1025, divisible_by=64
    )

    assert (portrait_width, portrait_height) == (
        landscape_height,
        landscape_width,
    )


def test_hard_ceiling_never_rounds_long_side_up():
    assert fit("16:9", long_side=1025, divisible_by=64) == (1024, 576)


def test_aspect_fidelity_wins_before_larger_area():
    assert fit("4:5", long_side=128, divisible_by=32) == (96, 128)


def test_custom_ratio_uses_the_same_policy():
    assert fit(
        "Custom",
        long_side=1024,
        divisible_by=8,
        custom_ratio_width=13,
        custom_ratio_height=7,
    ) == (936, 504)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"aspect_ratio": "4x5"}, "aspect_ratio"),
        ({"long_side": 15}, "long_side"),
        ({"long_side": 16_385}, "long_side"),
        ({"long_side": True}, "long_side"),
        ({"divisible_by": 0}, "divisible_by"),
        ({"divisible_by": 16_385}, "divisible_by"),
        ({"custom_ratio_width": 0}, "custom_ratio_width"),
        ({"custom_ratio_height": 16_385}, "custom_ratio_height"),
    ],
)
def test_invalid_api_values_fail_actionably(overrides, message):
    arguments = {
        "aspect_ratio": "16:9",
        "long_side": 1024,
        "divisible_by": 8,
        "custom_ratio_width": 1,
        "custom_ratio_height": 1,
    }
    arguments.update(overrides)

    with pytest.raises(ValueError, match=message):
        fit(**arguments)


def test_impossible_alignment_fails_actionably():
    with pytest.raises(ValueError, match="No positive aligned dimensions"):
        fit("1:1", long_side=16, divisible_by=64)


def test_source_dimensions_fit_independent_axis_caps():
    assert fit_source(
        1920,
        1080,
        max_width=1024,
        max_height=576,
        divisible_by=64,
    ) == (1024, 576)


def test_source_dimensions_are_reciprocal():
    landscape = fit_source(
        1920,
        1080,
        max_width=1024,
        max_height=576,
        divisible_by=64,
    )
    portrait = fit_source(
        1080,
        1920,
        max_width=576,
        max_height=1024,
        divisible_by=64,
    )

    assert portrait == landscape[::-1]


def test_source_dimensions_keep_an_already_aligned_small_image():
    assert fit_source(
        320,
        240,
        max_width=320,
        max_height=240,
        divisible_by=8,
    ) == (320, 240)


def test_source_dimensions_prefer_aspect_fidelity_before_area():
    assert fit_source(
        400,
        500,
        max_width=128,
        max_height=128,
        divisible_by=32,
    ) == (96, 128)


def test_source_dimensions_respect_an_exact_pixel_ceiling():
    width, height = fit_source(
        1920,
        1080,
        max_width=1920,
        max_height=1080,
        max_pixels=1_000_000,
        divisible_by=64,
    )

    assert (width, height) == (1024, 576)
    assert width * height <= 1_000_000


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"source_width": True}, "source_width"),
        ({"source_height": 0}, "source_height"),
        ({"max_width": 0}, "max_width"),
        ({"max_height": MAX_RESOLUTION + 1}, "max_height"),
        ({"max_pixels": 0}, "max_pixels"),
        ({"max_pixels": MAX_RESOLUTION**2 + 1}, "max_pixels"),
    ],
)
def test_source_dimensions_reject_invalid_bounds(overrides, message):
    arguments = {
        "source_width": 1920,
        "source_height": 1080,
        "max_width": 1024,
        "max_height": 576,
        "max_pixels": None,
    }
    arguments.update(overrides)

    with pytest.raises(ValueError, match=message):
        fit_source(**arguments)


def test_source_dimensions_reject_impossible_alignment():
    with pytest.raises(ValueError, match="No positive aligned dimensions"):
        fit_source(
            32,
            32,
            max_width=32,
            max_height=32,
            divisible_by=64,
        )
