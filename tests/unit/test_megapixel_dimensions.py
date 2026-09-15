import sys
import types

import pytest
import torch

from lfgg_nodes.megapixel_dimensions import (
    DimensionsByRatioAndMegapixels,
    ImageDimensionsByMegapixels,
)
from lfgg_nodes.sizing import PIXELS_PER_MEGAPIXEL, fit_megapixel_dimensions


@pytest.fixture(autouse=True)
def comfy_nodes(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "nodes", types.SimpleNamespace(MAX_RESOLUTION=16384)
    )


def test_square_budget_uses_1024_squared_and_image_can_exceed_source():
    image = torch.zeros((2, 32, 32, 3), dtype=torch.float16)
    assert ImageDimensionsByMegapixels().calculate(image, 1.0, 8) == (1024, 1024)
    assert image.shape == (2, 32, 32, 3)
    assert image.dtype == torch.float16
    assert torch.count_nonzero(image).item() == 0
    assert DimensionsByRatioAndMegapixels().calculate("1:1", 1.0, 8, 1, 1) == (
        1024,
        1024,
    )


def test_preset_and_custom_ratio_choose_largest_exact_aligned_fit():
    node = DimensionsByRatioAndMegapixels()
    assert node.calculate("16:9", 1.0, 8, 1, 1) == (1280, 720)
    assert node.calculate("Custom", 1.0, 8, 9, 16) == (720, 1280)
    image = torch.empty((3, 90, 160, 4))
    assert ImageDimensionsByMegapixels().calculate(image, 1.0, 8) == (1280, 720)


def test_fractional_budget_is_floored_and_exact_alignment_is_respected():
    result = fit_megapixel_dimensions(
        ratio_width=1,
        ratio_height=1,
        megapixels=899.75 / PIXELS_PER_MEGAPIXEL,
        divisible_by=3,
        max_resolution=100,
    )
    assert result == (27, 27)


def test_axis_limit_wins_even_with_large_budget():
    assert fit_megapixel_dimensions(
        ratio_width=16,
        ratio_height=1,
        megapixels=1,
        divisible_by=8,
        max_resolution=1024,
    ) == (1024, 64)


@pytest.mark.parametrize("budget", [True, "1", 0, -1, float("nan"), float("inf"), 257])
def test_invalid_megapixel_budgets_are_rejected(budget):
    with pytest.raises(ValueError, match="megapixels"):
        DimensionsByRatioAndMegapixels().calculate("1:1", budget, 8, 1, 1)


def test_impossible_alignment_does_not_exceed_budget():
    with pytest.raises(ValueError, match="No positive aligned dimensions"):
        DimensionsByRatioAndMegapixels().calculate(
            "1:1", 63 / PIXELS_PER_MEGAPIXEL, 8, 1, 1
        )


@pytest.mark.parametrize(
    "ratio,width,height,alignment",
    [("unknown", 1, 1, 8), ("Custom", 0, 1, 8), ("Custom", 1, 0, 8), ("1:1", 1, 1, 0)],
)
def test_invalid_ratio_and_alignment_are_rejected(ratio, width, height, alignment):
    with pytest.raises(ValueError):
        DimensionsByRatioAndMegapixels().calculate(ratio, 1, alignment, width, height)


def test_image_requires_a_positive_bhwc_tensor():
    with pytest.raises(ValueError, match="IMAGE"):
        ImageDimensionsByMegapixels().calculate(torch.empty((3, 32, 32)), 1, 8)
