import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
MAX_RESOLUTION = 16_384
RATIOS = [
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
    "Custom",
]


def load_root_package(monkeypatch, max_resolution=MAX_RESOLUTION):
    root_init = ROOT / "__init__.py"
    if not root_init.exists():
        pytest.fail("root custom-node package is not implemented")

    monkeypatch.setitem(
        sys.modules, "nodes", types.SimpleNamespace(MAX_RESOLUTION=max_resolution)
    )
    spec = importlib.util.spec_from_file_location(
        "lfgg_custom_node",
        root_init,
        submodule_search_locations=[str(ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def test_v1_registration_and_schema_are_exact(monkeypatch):
    package = load_root_package(monkeypatch)

    assert not hasattr(package, "comfy_entrypoint")
    assert package.NODE_DISPLAY_NAME_MAPPINGS == {
        "LFGG_DimensionsByAspectRatio": "LFGG Dimensions by Aspect Ratio"
    }
    assert list(package.NODE_CLASS_MAPPINGS) == ["LFGG_DimensionsByAspectRatio"]

    node = package.NODE_CLASS_MAPPINGS["LFGG_DimensionsByAspectRatio"]
    assert node.CATEGORY == "LFGG/sizing"
    assert node.DESCRIPTION == (
        "Calculates aligned width and height for a preset or custom aspect ratio "
        "without exceeding the selected long-side limit."
    )
    assert node.FUNCTION == "calculate"
    assert node.RETURN_TYPES == ("INT", "INT")
    assert node.RETURN_NAMES == ("width", "height")
    assert node.OUTPUT_TOOLTIPS == (
        "Aligned output width in pixels.",
        "Aligned output height in pixels.",
    )

    required = node.INPUT_TYPES()["required"]
    assert list(required) == [
        "aspect_ratio",
        "long_side",
        "divisible_by",
        "custom_ratio_width",
        "custom_ratio_height",
    ]
    assert required == {
        "aspect_ratio": (
            "COMBO",
            {
                "options": RATIOS,
                "tooltip": (
                    "Target width-to-height ratio. Select Custom to use the "
                    "custom ratio inputs."
                ),
            },
        ),
        "long_side": (
            "INT",
            {
                "default": 1024,
                "min": 16,
                "max": MAX_RESOLUTION,
                "step": 8,
                "tooltip": "Maximum size in pixels for the longer output axis.",
            },
        ),
        "divisible_by": (
            "INT",
            {
                "default": 8,
                "min": 1,
                "max": MAX_RESOLUTION,
                "tooltip": (
                    "Aligns both output dimensions to this exact multiple "
                    "without exceeding the limit."
                ),
            },
        ),
        "custom_ratio_width": (
            "INT",
            {
                "default": 1,
                "min": 1,
                "max": MAX_RESOLUTION,
                "tooltip": (
                    "Width component used only when aspect_ratio is Custom."
                ),
            },
        ),
        "custom_ratio_height": (
            "INT",
            {
                "default": 1,
                "min": 1,
                "max": MAX_RESOLUTION,
                "tooltip": (
                    "Height component used only when aspect_ratio is Custom."
                ),
            },
        ),
    }


def test_root_registration_rejects_duplicate_ids(monkeypatch):
    package = load_root_package(monkeypatch)

    with pytest.raises(RuntimeError, match="Duplicate node ID: LFGG_Duplicate"):
        package._merge_class_mappings(  # noqa: SLF001
            {"LFGG_Duplicate": object}, {"LFGG_Duplicate": object}
        )


def test_schema_uses_comfyui_max_resolution(monkeypatch):
    package = load_root_package(monkeypatch, max_resolution=4096)
    node = package.NODE_CLASS_MAPPINGS["LFGG_DimensionsByAspectRatio"]
    required = node.INPUT_TYPES()["required"]

    assert required["long_side"][1]["max"] == 4096
    assert required["divisible_by"][1]["max"] == 4096
    assert required["custom_ratio_width"][1]["max"] == 4096
    assert required["custom_ratio_height"][1]["max"] == 4096


def test_metadata_and_model_free_workflow_match_the_release_contract():
    pyproject_path = ROOT / "pyproject.toml"
    workflow_path = ROOT / "workflows" / "dimensions_by_aspect_ratio.json"
    assert pyproject_path.exists(), "pyproject.toml is not implemented"
    assert workflow_path.exists(), "model-free API workflow is not implemented"

    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib

    metadata = tomllib.loads(pyproject_path.read_text())
    project = metadata["project"]
    comfy = metadata["tool"]["comfy"]
    assert project["name"] == "lfgg-nodes"
    assert project["version"] == "1.0.0"
    assert project["requires-python"] == ">=3.10,<3.14"
    assert project["dependencies"] == []
    assert "Environment :: GPU :: NVIDIA CUDA" in project["classifiers"]
    assert comfy == {
        "PublisherId": "lfelipegg",
        "DisplayName": "LFGG Nodes",
        "requires-comfyui": ">=0.28.0",
    }

    readme = " ".join((ROOT / "README.md").read_text().split())
    for claim in [
        "ComfyUI `>=0.28.0`",
        "Python `>=3.10,<3.14`",
        "Linux and Windows",
        "CPU and NVIDIA CUDA",
        "does not write files",
        "native initializer appropriate for the model family",
    ]:
        assert claim in readme

    workflow = json.loads(workflow_path.read_text())
    assert workflow["1"]["class_type"] == "LFGG_DimensionsByAspectRatio"
    assert list(workflow["1"]["inputs"]) == [
        "aspect_ratio",
        "long_side",
        "divisible_by",
        "custom_ratio_width",
        "custom_ratio_height",
    ]
    assert workflow["2"] == {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": ["1", 0], "height": ["1", 1], "batch_size": 1},
    }
    assert workflow["3"] == {
        "class_type": "SaveLatent",
        "inputs": {
            "samples": ["2", 0],
            "filename_prefix": "lfgg/dimensions_by_aspect_ratio",
        },
    }
