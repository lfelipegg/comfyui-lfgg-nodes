import builtins
import importlib.util
import io
import json
import os
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


def test_v1_registration_and_aspect_ratio_schema_are_exact(monkeypatch):
    package = load_root_package(monkeypatch)

    assert not hasattr(package, "comfy_entrypoint")
    assert package.WEB_DIRECTORY == "./web"
    assert package.__all__ == [
        "NODE_CLASS_MAPPINGS",
        "NODE_DISPLAY_NAME_MAPPINGS",
        "WEB_DIRECTORY",
    ]
    assert package.NODE_DISPLAY_NAME_MAPPINGS == {
        "LFGG_DimensionsByAspectRatio": "LFGG Dimensions by Aspect Ratio",
        "LFGG_ImageDimensionsByLongSide": "LFGG Image Dimensions by Long Side",
        "LFGG_ImageDimensionsByPixelBudget": (
            "LFGG Image Dimensions by Pixel Budget"
        ),
        "LFGG_LoadAndCropImage": "LFGG Load and Crop Image",
        "LFGG_SaveImageDynamic": "LFGG Save Image Dynamic",
    }
    assert list(package.NODE_CLASS_MAPPINGS) == [
        "LFGG_DimensionsByAspectRatio",
        "LFGG_ImageDimensionsByLongSide",
        "LFGG_ImageDimensionsByPixelBudget",
        "LFGG_LoadAndCropImage",
        "LFGG_SaveImageDynamic",
    ]

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


def test_load_and_crop_image_import_is_lazy_and_side_effect_free(
    monkeypatch, tmp_path
):
    input_directory = tmp_path / "input"
    input_directory.mkdir()
    nested = input_directory / "nested"
    nested.mkdir()
    source = nested / "source.png"
    source.write_bytes(b"unchanged")
    stub_directory = tmp_path / "stubs"
    stub_directory.mkdir()
    (stub_directory / "folder_paths.py").write_text(
        f"def get_input_directory():\n    return {str(input_directory)!r}\n"
    )
    monkeypatch.syspath_prepend(str(stub_directory))
    target = source.resolve()
    before_content = source.read_bytes()
    before_stat = source.stat()
    before_entries = sorted(
        path.relative_to(input_directory) for path in input_directory.rglob("*")
    )

    def reject_target_access(original):
        def guarded(path, *args, **kwargs):
            if isinstance(path, (str, bytes, os.PathLike)):
                try:
                    opened = Path(os.fsdecode(path)).resolve()
                except (OSError, TypeError):
                    opened = None
                if opened == target:
                    pytest.fail("root package import opened an input image")
            return original(path, *args, **kwargs)

        return guarded

    with monkeypatch.context() as import_guard:
        for module_name in tuple(sys.modules):
            if module_name == "lfgg_custom_node" or module_name.startswith(
                "lfgg_custom_node."
            ):
                import_guard.delitem(sys.modules, module_name)
        for owner, name in (
            (builtins, "open"),
            (io, "open"),
            (os, "open"),
        ):
            import_guard.setattr(
                owner,
                name,
                reject_target_access(getattr(owner, name)),
            )
        load_root_package(import_guard)

    assert "folder_paths" not in sys.modules
    assert sorted(
        path.relative_to(input_directory) for path in input_directory.rglob("*")
    ) == before_entries
    assert source.read_bytes() == before_content
    after_stat = source.stat()
    assert (after_stat.st_size, after_stat.st_mtime_ns) == (
        before_stat.st_size,
        before_stat.st_mtime_ns,
    )


def test_load_and_crop_image_v1_schema_is_exact(monkeypatch, tmp_path):
    input_directory = tmp_path / "input"
    input_directory.mkdir()
    (input_directory / "zebra.png").write_bytes(b"zebra")
    nested = input_directory / "nested"
    nested.mkdir()
    (nested / "apple.png").write_bytes(b"apple")
    external = tmp_path / "external.png"
    external.write_bytes(b"external")
    (input_directory / "outside.png").symlink_to(external)

    package = load_root_package(monkeypatch)

    monkeypatch.setitem(
        sys.modules,
        "folder_paths",
        types.SimpleNamespace(
            get_input_directory=lambda: str(input_directory),
        ),
    )
    node = package.NODE_CLASS_MAPPINGS["LFGG_LoadAndCropImage"]
    assert package.NODE_DISPLAY_NAME_MAPPINGS["LFGG_LoadAndCropImage"] == (
        "LFGG Load and Crop Image"
    )
    assert node.CATEGORY == "LFGG/image"
    assert node.DESCRIPTION == (
        "Loads one still image from the ComfyUI input directory and crops it "
        "without resampling."
    )
    assert node.FUNCTION == "load_and_crop"
    assert node.RETURN_TYPES == ("IMAGE", "MASK")
    assert node.RETURN_NAMES == ("image", "mask")
    assert node.OUTPUT_TOOLTIPS == (
        "Selected source region without resampling.",
        "Alpha-derived mask cropped to the same region.",
    )
    schema = node.INPUT_TYPES()
    required = schema["required"]
    assert list(required) == [
        "image",
        "ratio_width",
        "ratio_height",
        "crop_x",
        "crop_y",
        "crop_width",
        "crop_height",
    ]
    assert schema == {
        "required": {
            "image": (
                "COMBO",
                {
                    "options": ["nested/apple.png", "zebra.png"],
                    "image_upload": True,
                    "allow_batch": False,
                    "tooltip": "Still image beneath the ComfyUI input directory.",
                },
            ),
            "ratio_width": (
                "INT",
                {
                    "default": 1,
                    "min": 1,
                    "max": MAX_RESOLUTION,
                    "tooltip": "Positive width component of the crop ratio.",
                },
            ),
            "ratio_height": (
                "INT",
                {
                    "default": 1,
                    "min": 1,
                    "max": MAX_RESOLUTION,
                    "tooltip": "Positive height component of the crop ratio.",
                },
            ),
            "crop_x": (
                "INT",
                {
                    "default": 0,
                    "min": 0,
                    "max": MAX_RESOLUTION,
                    "tooltip": "Left edge in oriented source-image pixels.",
                },
            ),
            "crop_y": (
                "INT",
                {
                    "default": 0,
                    "min": 0,
                    "max": MAX_RESOLUTION,
                    "tooltip": "Top edge in oriented source-image pixels.",
                },
            ),
            "crop_width": (
                "INT",
                {
                    "default": 0,
                    "min": 0,
                    "max": MAX_RESOLUTION,
                    "tooltip": (
                        "Crop width in source-image pixels. Zero width and height "
                        "initialize the largest centered crop."
                    ),
                },
            ),
            "crop_height": (
                "INT",
                {
                    "default": 0,
                    "min": 0,
                    "max": MAX_RESOLUTION,
                    "tooltip": (
                        "Derived crop height in source-image pixels. Zero width and "
                        "height initialize the largest centered crop."
                    ),
                },
            ),
        }
    }


def test_image_derived_v1_schemas_are_exact(monkeypatch):
    package = load_root_package(monkeypatch)
    long_side = package.NODE_CLASS_MAPPINGS["LFGG_ImageDimensionsByLongSide"]
    pixel_budget = package.NODE_CLASS_MAPPINGS[
        "LFGG_ImageDimensionsByPixelBudget"
    ]

    for node in (long_side, pixel_budget):
        assert node.CATEGORY == "LFGG/sizing"
        assert node.FUNCTION == "calculate"
        assert node.RETURN_TYPES == ("INT", "INT")
        assert node.RETURN_NAMES == ("width", "height")
        assert node.OUTPUT_TOOLTIPS == (
            "Aligned target width in pixels.",
            "Aligned target height in pixels.",
        )

    assert long_side.DESCRIPTION == (
        "Calculates aligned dimensions from an image without upscaling or "
        "exceeding the selected long-side limit."
    )
    assert long_side.INPUT_TYPES()["required"] == {
        "image": (
            "IMAGE",
            {"tooltip": "Image batch whose shared spatial shape is inspected."},
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
                "tooltip": "Aligns both output dimensions to this exact multiple.",
            },
        ),
    }

    assert pixel_budget.DESCRIPTION == (
        "Calculates aligned dimensions from an image without upscaling or "
        "exceeding the selected pixel budget."
    )
    assert pixel_budget.INPUT_TYPES()["required"] == {
        "image": (
            "IMAGE",
            {"tooltip": "Image batch whose shared spatial shape is inspected."},
        ),
        "max_pixels": (
            "INT",
            {
                "default": 1_048_576,
                "min": 1,
                "max": MAX_RESOLUTION**2,
                "step": 1024,
                "tooltip": "Maximum total pixel count for the output dimensions.",
            },
        ),
        "divisible_by": (
            "INT",
            {
                "default": 8,
                "min": 1,
                "max": MAX_RESOLUTION,
                "tooltip": "Aligns both output dimensions to this exact multiple.",
            },
        ),
    }


def test_save_image_dynamic_v1_schema_is_exact(monkeypatch):
    node = load_root_package(monkeypatch).NODE_CLASS_MAPPINGS[
        "LFGG_SaveImageDynamic"
    ]

    assert node.CATEGORY == "LFGG/Image"
    assert node.DESCRIPTION == (
        "Saves PNG image batches beneath the ComfyUI output directory using "
        "safe path and filename templates."
    )
    assert node.FUNCTION == "save_images"
    assert node.RETURN_TYPES == ()
    assert node.RETURN_NAMES == ()
    assert node.OUTPUT_TOOLTIPS == ()
    assert node.OUTPUT_NODE is True
    assert node.INPUT_TYPES() == {
        "required": {
            "images": (
                "IMAGE",
                {"tooltip": "Image batch to save as PNG files."},
            ),
            "path_template": (
                "STRING",
                {
                    "default": "runs/{model}/{date}",
                    "tooltip": (
                        "Output-relative subfolder template using supported "
                        "brace tokens."
                    ),
                },
            ),
            "filename_template": (
                "STRING",
                {
                    "default": "{model}_{datetime}_{batch}_{counter}",
                    "tooltip": (
                        "PNG filename template using supported brace tokens."
                    ),
                },
            ),
            "save_metadata": (
                "BOOLEAN",
                {
                    "default": True,
                    "tooltip": (
                        "Embed prompt and workflow metadata unless globally "
                        "disabled in ComfyUI."
                    ),
                },
            ),
        },
        "optional": {
            "model_name": (
                "STRING",
                {
                    "forceInput": True,
                    "tooltip": "Explicit model label used by the {model} token.",
                },
            )
        },
        "hidden": {
            "prompt": "PROMPT",
            "extra_pnginfo": "EXTRA_PNGINFO",
        },
    }


def test_root_registration_rejects_duplicate_ids(monkeypatch):
    package = load_root_package(monkeypatch)

    with pytest.raises(RuntimeError, match="Duplicate node ID: LFGG_Duplicate"):
        package._merge_class_mappings(  # noqa: SLF001
            {"LFGG_Duplicate": object}, {"LFGG_Duplicate": object}
        )


def test_schema_uses_comfyui_max_resolution(monkeypatch, tmp_path):
    package = load_root_package(monkeypatch, max_resolution=4096)
    monkeypatch.setitem(
        sys.modules,
        "folder_paths",
        types.SimpleNamespace(get_input_directory=lambda: str(tmp_path)),
    )
    aspect_required = package.NODE_CLASS_MAPPINGS[
        "LFGG_DimensionsByAspectRatio"
    ].INPUT_TYPES()["required"]
    long_required = package.NODE_CLASS_MAPPINGS[
        "LFGG_ImageDimensionsByLongSide"
    ].INPUT_TYPES()["required"]
    pixel_required = package.NODE_CLASS_MAPPINGS[
        "LFGG_ImageDimensionsByPixelBudget"
    ].INPUT_TYPES()["required"]
    crop_required = package.NODE_CLASS_MAPPINGS[
        "LFGG_LoadAndCropImage"
    ].INPUT_TYPES()["required"]

    assert aspect_required["long_side"][1]["max"] == 4096
    assert aspect_required["divisible_by"][1]["max"] == 4096
    assert aspect_required["custom_ratio_width"][1]["max"] == 4096
    assert aspect_required["custom_ratio_height"][1]["max"] == 4096
    assert long_required["long_side"][1]["max"] == 4096
    assert long_required["divisible_by"][1]["max"] == 4096
    assert pixel_required["max_pixels"][1]["max"] == 4096**2
    assert pixel_required["divisible_by"][1]["max"] == 4096
    assert crop_required["ratio_width"][1]["max"] == 4096
    assert crop_required["ratio_height"][1]["max"] == 4096
    assert crop_required["crop_x"][1]["max"] == 4096
    assert crop_required["crop_y"][1]["max"] == 4096
    assert crop_required["crop_width"][1]["max"] == 4096
    assert crop_required["crop_height"][1]["max"] == 4096


def test_metadata_manifest_and_workflow_match_the_release_contract(monkeypatch):
    pyproject_path = ROOT / "pyproject.toml"
    manifest_path = ROOT / "release" / "1.2.0-schema.json"
    workflow_path = ROOT / "workflows" / "sizing.json"
    save_workflow_path = ROOT / "workflows" / "save_image_dynamic.json"
    assert pyproject_path.exists(), "pyproject.toml is not implemented"
    assert manifest_path.exists(), "release schema manifest is not implemented"
    assert workflow_path.exists(), "complete sizing API workflow is not implemented"
    assert save_workflow_path.exists(), "dynamic save API workflow is not implemented"

    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib

    metadata = tomllib.loads(pyproject_path.read_text())
    project = metadata["project"]
    comfy = metadata["tool"]["comfy"]
    assert project["name"] == "lfgg-nodes"
    assert project["version"] == "1.2.0"
    assert project["requires-python"] == ">=3.10,<3.14"
    assert project["dependencies"] == [
        "Pillow",
        "comfyui-frontend-package>=1.45.21",
    ]
    assert "setuptools>=77" in project["optional-dependencies"]["dev"]
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
        "frontend `>=1.45.21`",
        "requested aspect ratio",
        "custom ratio controls",
        "node --test tests/frontend/ratio_preview.test.mjs",
        "do not read or write files",
        "exclusive creation of final PNG files",
        "cleanup of PNG files created by a failed execution",
        "Imports and schema discovery do not write files",
        "268,435,456 total pixels",
        "native initializer appropriate for the model family",
        "`ImageFromBatch`",
        "explicit label",
        "Prompt Library",
        "Prompt Wildcard",
        "LoRA Loader by Path",
        "deferred",
        "`LfggSaveImageDynamic` → `LFGG_SaveImageDynamic`",
        "`%token%` to `{token}`",
        "`%batch_num%` to `{batch}`",
        "Remove `compress_level`",
        "Remove downstream uses of `saved_paths`",
        "No legacy workflow ID alias",
    ]:
        assert claim in readme

    package = load_root_package(monkeypatch)
    expected_nodes = {}
    for node_id, node in package.NODE_CLASS_MAPPINGS.items():
        if node_id == "LFGG_LoadAndCropImage":
            continue
        expected_nodes[node_id] = {
            "display_name": package.NODE_DISPLAY_NAME_MAPPINGS[node_id],
            "description": node.DESCRIPTION,
            "category": node.CATEGORY,
            "input": json.loads(json.dumps(node.INPUT_TYPES())),
            "output": list(node.RETURN_TYPES),
            "output_name": list(getattr(node, "RETURN_NAMES", ())),
            "output_tooltips": list(getattr(node, "OUTPUT_TOOLTIPS", ())),
        }
    assert json.loads(manifest_path.read_text()) == {
        "version": "1.2.0",
        "nodes": expected_nodes,
    }

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
            "filename_prefix": "lfgg/sizing/aspect_ratio",
        },
    }
    assert workflow["4"] == {
        "class_type": "EmptyImage",
        "inputs": {"width": 640, "height": 360, "batch_size": 2, "color": 0},
    }
    assert workflow["5"]["class_type"] == "LFGG_ImageDimensionsByLongSide"
    assert workflow["5"]["inputs"]["image"] == ["4", 0]
    assert workflow["6"] == {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": ["5", 0], "height": ["5", 1], "batch_size": 2},
    }
    assert workflow["7"]["inputs"] == {
        "samples": ["6", 0],
        "filename_prefix": "lfgg/sizing/long_side",
    }
    assert workflow["8"]["class_type"] == "LFGG_ImageDimensionsByPixelBudget"
    assert workflow["8"]["inputs"]["image"] == ["4", 0]
    assert workflow["9"] == {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": ["8", 0], "height": ["8", 1], "batch_size": 2},
    }
    assert workflow["10"]["inputs"] == {
        "samples": ["9", 0],
        "filename_prefix": "lfgg/sizing/pixel_budget",
    }

    save_workflow = json.loads(save_workflow_path.read_text())
    assert save_workflow == {
        "1": {
            "class_type": "EmptyImage",
            "inputs": {
                "width": 3,
                "height": 2,
                "batch_size": 2,
                "color": 0,
            },
        },
        "2": {
            "class_type": "LFGG_SaveImageDynamic",
            "inputs": {
                "images": ["1", 0],
                "path_template": "lfgg/dynamic",
                "filename_template": "metadata_on",
                "save_metadata": True,
            },
        },
        "3": {
            "class_type": "LFGG_SaveImageDynamic",
            "inputs": {
                "images": ["1", 0],
                "path_template": "lfgg/dynamic",
                "filename_template": "metadata_off",
                "save_metadata": False,
            },
        },
    }
