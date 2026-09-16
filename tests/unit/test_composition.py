import random

import numpy as np
import pytest
import torch
from PIL import Image, ImageDraw

from lfgg_nodes import composition
from lfgg_nodes.composition import (
    FAMILIES,
    MAX_BATCH_PIXELS,
    MAX_SEED,
    PALETTES,
    generate_composition_batch,
)


def render(**overrides):
    arguments = dict(
        width=96,
        height=64,
        family="Random",
        palette="Monochrome",
        complexity=0.5,
        seed=123,
        batch_size=1,
    )
    arguments.update(overrides)
    return generate_composition_batch(**arguments)


@pytest.mark.parametrize("family", FAMILIES)
def test_seed_reproduction_and_batch_prefix(family):
    first = render(family=family, palette="Random", batch_size=2)
    assert torch.equal(first, render(family=family, palette="Random", batch_size=2))
    extended = render(family=family, palette="Random", batch_size=3)
    assert torch.equal(first, extended[:2])
    assert not torch.equal(extended[0], extended[1])
    assert not torch.equal(
        first, render(family=family, palette="Random", seed=124, batch_size=2)
    )


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("palette", PALETTES)
def test_all_families_respect_palette_and_tensor_contract(family, palette):
    image = render(family=family, palette=palette, batch_size=2)
    assert image.shape == (2, 64, 96, 3)
    assert image.dtype == torch.float32
    assert image.device.type == "cpu"
    assert image.is_contiguous()
    assert torch.isfinite(image).all()
    assert image.min() >= 0 and image.max() <= 1
    assert not torch.equal(image[:, :1, :1].expand_as(image), image)
    if palette in ("Monochrome", "Grayscale"):
        assert torch.equal(image[..., 0], image[..., 1])
        assert torch.equal(image[..., 1], image[..., 2])
    else:
        assert (image[..., 0] != image[..., 1]).any()
    if palette == "Monochrome":
        pixels = image[..., 0]
        maximum = torch.nn.functional.max_pool2d(pixels.unsqueeze(1), 7, 1, 3)
        minimum = -torch.nn.functional.max_pool2d(-pixels.unsqueeze(1), 7, 1, 3)
        interior = (maximum == minimum)[:, 0]
        assert interior.any()
        assert ((pixels[interior] == 0) | (pixels[interior] == 1)).all()
        assert ((pixels > 0) & (pixels < 1)).any()


def test_monochrome_gradient_is_thresholded_not_continuous_tones():
    image = render(family=FAMILIES[5], complexity=0, width=512, height=512)[0, ..., 0]
    gray = render(
        family=FAMILIES[5], palette="Grayscale", complexity=0, width=512, height=512
    )[0, ..., 0]
    assert ((image == 0) | (image == 1)).float().mean() > 0.98
    assert ((gray > 0.05) & (gray < 0.95)).float().mean() > 0.5


def test_random_selection_is_per_item_and_respects_explicit_choices():
    random_batch = render(palette="Random", batch_size=8, width=48, height=48)
    matches = [set() for _ in range(8)]
    for family in FAMILIES:
        for palette in PALETTES:
            explicit = render(
                family=family, palette=palette, batch_size=8, width=48, height=48
            )
            for index in range(8):
                if torch.equal(random_batch[index], explicit[index]):
                    matches[index].add((family, palette))
    assert all(len(match) == 1 for match in matches)
    selections = [next(iter(match)) for match in matches]
    assert len({family for family, _ in selections}) > 1
    assert len({palette for _, palette in selections}) > 1
    assert torch.equal(
        random_batch[:2], render(palette="Random", batch_size=2, width=48, height=48)
    )


@pytest.mark.parametrize("family", FAMILIES)
def test_complexity_changes_family_composition(family):
    assert not torch.equal(
        render(family=family, complexity=0), render(family=family, complexity=1)
    )


def test_render_does_not_consume_global_random_state():
    python_state = random.getstate()
    torch_state = torch.random.get_rng_state()
    render()
    assert random.getstate() == python_state
    assert torch.equal(torch.random.get_rng_state(), torch_state)


@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"width": True}, "width"),
        ({"height": 0}, "height"),
        ({"width": 1.5}, "width"),
        ({"height": "64"}, "height"),
        ({"family": []}, "family"),
        ({"family": "unknown"}, "family"),
        ({"palette": None}, "palette"),
        ({"palette": "unknown"}, "palette"),
        ({"complexity": True}, "complexity"),
        ({"complexity": "0.5"}, "complexity"),
        ({"complexity": float("nan")}, "complexity"),
        ({"complexity": float("inf")}, "complexity"),
        ({"complexity": 10**400}, "complexity"),
        ({"complexity": -0.01}, "complexity"),
        ({"complexity": 1.01}, "complexity"),
        ({"seed": -1}, "seed"),
        ({"seed": MAX_SEED + 1}, "seed"),
        ({"seed": True}, "seed"),
        ({"seed": 1.5}, "seed"),
        ({"batch_size": 0}, "batch_size"),
        ({"batch_size": True}, "batch_size"),
        ({"batch_size": 1.5}, "batch_size"),
        ({"batch_size": MAX_BATCH_PIXELS + 1}, "pixel"),
    ],
)
def test_invalid_execution_inputs_fail_actionably(overrides, field):
    with pytest.raises(ValueError, match=field):
        render(**overrides)


def test_total_pixel_budget_rejects_before_allocating_impossible_output():
    # An allocation attempt cannot succeed for this size; validation must win.
    with pytest.raises(ValueError, match="pixel"):
        render(width=MAX_BATCH_PIXELS, height=MAX_BATCH_PIXELS)
    with pytest.raises(ValueError, match="pixel"):
        render(width=2048, height=2048, batch_size=5)


def test_exact_pixel_budget_is_accepted():
    image = render(
        width=2048,
        height=2048,
        batch_size=4,
        family=FAMILIES[4],
        complexity=0,
        seed=MAX_SEED,
    )
    assert image.shape == (4, 2048, 2048, 3)
    assert image.numel() == MAX_BATCH_PIXELS * 3
    assert torch.isfinite(image).all()
    assert image.min() >= 0 and image.max() <= 1


@pytest.mark.parametrize("family", FAMILIES)
def test_tile_boundaries_match_continuous_canvas_rendering(family):
    # Rendering the same geometry in bounded tiles must not create seams.
    width, height = 777, 617
    scene = composition._build_scene(
        width, height, family, "Vivid color", 1, random.Random(42)
    )
    continuous = composition._draw_tile(
        scene, (0, 0, width, height), width, height, np, Image, ImageDraw
    )
    expected = torch.from_numpy(np.array(continuous)).float().mul_(1 / 255)
    actual = torch.empty((height, width, 3))
    composition._render_into(actual, scene, width, height, np, torch, Image, ImageDraw)
    assert torch.equal(actual, expected)
