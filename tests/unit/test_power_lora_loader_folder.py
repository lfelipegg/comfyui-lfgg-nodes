import math

import pytest

from lfgg_nodes.power_lora_loader_folder import (
    ALL_LORAS,
    build_lora_catalog,
    filter_loras,
    validate_lora_row,
)


def test_catalog_infers_every_parent_and_normalizes_separators():
    folders, loras = build_lora_catalog(
        [
            r"characters\anime\hero.safetensors",
            "characters/photo.safetensors",
            "styles/ink.safetensors",
            "root.safetensors",
        ]
    )

    assert folders == [
        ALL_LORAS,
        "characters",
        "characters/anime",
        "styles",
    ]
    assert loras == [
        "characters/anime/hero.safetensors",
        "characters/photo.safetensors",
        "root.safetensors",
        "styles/ink.safetensors",
    ]


def test_filter_is_recursive_and_all_loras_disables_it():
    _, loras = build_lora_catalog(
        [
            "characters/anime/hero.safetensors",
            "characters/photo.safetensors",
            "style.safetensors",
        ]
    )

    assert filter_loras(loras, "characters") == [
        "characters/anime/hero.safetensors",
        "characters/photo.safetensors",
    ]
    assert filter_loras(loras, "characters/anime") == [
        "characters/anime/hero.safetensors"
    ]
    assert filter_loras(loras, ALL_LORAS) == loras


def test_row_validation_returns_normalized_values():
    assert validate_lora_row(
        {
            "on": True,
            "lora": r"characters\hero.safetensors",
            "strength_model": 0.75,
            "strength_clip": 1,
        }
    ) == (True, "characters/hero.safetensors", 0.75, 1.0)


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (None, "mapping"),
        (
            {
                "on": 1,
                "lora": "x",
                "strength_model": 1,
                "strength_clip": 1,
            },
            "Boolean",
        ),
        (
            {
                "on": True,
                "lora": "../x",
                "strength_model": 1,
                "strength_clip": 1,
            },
            "relative",
        ),
        (
            {
                "on": True,
                "lora": "/x",
                "strength_model": 1,
                "strength_clip": 1,
            },
            "relative",
        ),
        (
            {
                "on": True,
                "lora": "C:/x",
                "strength_model": 1,
                "strength_clip": 1,
            },
            "relative",
        ),
        (
            {
                "on": True,
                "lora": "x",
                "strength_model": True,
                "strength_clip": 1,
            },
            "numeric",
        ),
        (
            {
                "on": True,
                "lora": "x",
                "strength_model": math.inf,
                "strength_clip": 1,
            },
            "finite",
        ),
        (
            {
                "on": True,
                "lora": "x",
                "strength_model": 101,
                "strength_clip": 1,
            },
            "between",
        ),
        (
            {
                "on": True,
                "lora": "x",
                "strength_model": -101,
                "strength_clip": 1,
            },
            "between",
        ),
        (
            {
                "on": True,
                "lora": "",
                "strength_model": 1,
                "strength_clip": 1,
            },
            "non-empty",
        ),
        (
            {
                "on": True,
                "lora": "x",
                "strength_model": 1,
                "strength_clip": "1",
            },
            "numeric",
        ),
        (
            {"on": True, "lora": "x", "strength_model": 1},
            "unsupported or missing",
        ),
        (
            {
                "on": True,
                "lora": "x",
                "strength_model": 1,
                "strength_clip": 1,
                "extra": False,
            },
            "unsupported or missing",
        ),
    ],
)
def test_row_validation_rejects_untrusted_payloads(row, message):
    with pytest.raises(ValueError, match=message):
        validate_lora_row(row)
