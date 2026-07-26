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
