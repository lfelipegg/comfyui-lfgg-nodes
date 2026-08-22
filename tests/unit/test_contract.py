import builtins
import importlib.util
import io
import json
import os
import sys
import types
from pathlib import Path

import pytest
from PIL import Image

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
        "LFGG_ResizeImageByLongSide": "LFGG Resize Image by Long Side",
        "LFGG_LoadAndCropImage": "LFGG Load and Crop Image",
        "LFGG_PowerLoraLoaderFolder": "LFGG Power LoRA Loader (Folder)",
        "LFGG_PromptComposer": "LFGG Prompt Composer",
        "LFGG_RoutingOrganizer": "LFGG Routing Organizer",
        "LFGG_SaveImageDynamic": "LFGG Save Image Dynamic",
        "LFGG_VideoCutter": "LFGG Video Cutter",
    }
    assert list(package.NODE_CLASS_MAPPINGS) == [
        "LFGG_DimensionsByAspectRatio",
        "LFGG_ImageDimensionsByLongSide",
        "LFGG_ImageDimensionsByPixelBudget",
        "LFGG_ResizeImageByLongSide",
        "LFGG_LoadAndCropImage",
        "LFGG_PowerLoraLoaderFolder",
        "LFGG_PromptComposer",
        "LFGG_RoutingOrganizer",
        "LFGG_SaveImageDynamic",
        "LFGG_VideoCutter",
    ]

    routing_organizer = package.NODE_CLASS_MAPPINGS["LFGG_RoutingOrganizer"]
    assert routing_organizer.CATEGORY == "LFGG/workflow"
    assert routing_organizer.DESCRIPTION == (
        "Keeps labeled workflow connections aligned without changing their values."
    )
    assert routing_organizer.FUNCTION == "route"
    assert routing_organizer.RETURN_TYPES == ()
    assert routing_organizer.INPUT_TYPES() == {"required": {}}
    assert routing_organizer().route() == ()

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

    power_lora = package.NODE_CLASS_MAPPINGS["LFGG_PowerLoraLoaderFolder"]
    assert power_lora.CATEGORY == "LFGG/loaders"
    assert power_lora.DESCRIPTION == (
        "Applies ordered LoRAs while limiting new selections to a saved "
        "LoRA folder."
    )
    assert power_lora.FUNCTION == "load_loras"
    assert power_lora.RETURN_TYPES == ("MODEL", "CLIP")
    assert power_lora.RETURN_NAMES == ("model", "clip")
    assert power_lora.OUTPUT_TOOLTIPS == (
        "Model with every enabled LoRA applied in row order.",
        "CLIP with every enabled LoRA applied in row order.",
    )
    monkeypatch.setitem(
        sys.modules,
        "folder_paths",
        types.SimpleNamespace(
            get_filename_list=lambda _category: [
                "characters/anime/hero.safetensors",
                "styles/ink.safetensors",
            ]
        ),
    )
    assert json.loads(json.dumps(power_lora.INPUT_TYPES())) == {
        "required": {
            "model": ["MODEL"],
            "clip": ["CLIP"],
            "folder": [
                "COMBO",
                {
                    "options": [
                        "All LoRAs",
                        "characters",
                        "characters/anime",
                        "styles",
                    ],
                    "default": "characters",
                    "tooltip": (
                        "Limits future LoRA choices to this folder and its "
                        "descendants."
                    ),
                },
            ],
            "lora_to_add": [
                "COMBO",
                {
                    "options": [
                        "characters/anime/hero.safetensors",
                        "styles/ink.safetensors",
                    ],
                    "default": "characters/anime/hero.safetensors",
                    "tooltip": "LoRA to add as the next ordered row.",
                },
            ],
        },
        "optional": {},
    }

    prompt_composer = package.NODE_CLASS_MAPPINGS["LFGG_PromptComposer"]
    assert prompt_composer.CATEGORY == "LFGG/text"
    assert prompt_composer.DESCRIPTION == (
        "Composes positioned style and file-wildcard tokens from configured local "
        "libraries with reproducible wildcard choices."
    )
    assert prompt_composer.FUNCTION == "compose"
    assert prompt_composer.RETURN_TYPES == ("STRING", "STRING")
    assert prompt_composer.RETURN_NAMES == ("prompt", "negative_prompt")
    assert prompt_composer.OUTPUT_TOOLTIPS == (
        "Resolved positive prompt in the authored token order.",
        "Negative style fragments joined in token order.",
    )
    assert prompt_composer.INPUT_TYPES() == {
        "required": {
            "prompt_template": (
                "STRING",
                {
                    "default": "",
                    "multiline": True,
                    "dynamicPrompts": True,
                    "placeholder": "Write a prompt and insert styles or wildcards…",
                    "tooltip": (
                        "Prompt template. File wildcards use __folder/name__; "
                        "styles use [[style:Exact Name]]."
                    ),
                },
            ),
            "seed": (
                "INT",
                {
                    "default": 0,
                    "min": 0,
                    "max": 2**64 - 1,
                    "control_after_generate": True,
                    "tooltip": "Seed for reproducible file-wildcard choices.",
                },
            ),
        }
    }

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
        assert not hasattr(sys.modules["nodes"], "LoraLoader")

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


def test_video_cutter_v1_schema_is_exact(monkeypatch):
    package = load_root_package(monkeypatch)
    node = package.NODE_CLASS_MAPPINGS["LFGG_VideoCutter"]

    assert package.NODE_DISPLAY_NAME_MAPPINGS["LFGG_VideoCutter"] == (
        "LFGG Video Cutter"
    )
    assert node.CATEGORY == "LFGG/video"
    assert node.DESCRIPTION == (
        "Selects one frame-aligned segment from a ComfyUI video while keeping "
        "its primary video and audio synchronized."
    )
    assert node.FUNCTION == "cut"
    assert node.RETURN_TYPES == ("VIDEO",)
    assert node.RETURN_NAMES == ("video",)
    assert node.OUTPUT_TOOLTIPS == ("Selected contiguous video segment.",)
    assert node.INPUT_TYPES() == {
        "required": {
            "video": ("VIDEO", {"tooltip": "Source ComfyUI video."}),
            "selection_mode": (
                "COMBO",
                {
                    "options": ["Time", "Frames"],
                    "default": "Time",
                    "tooltip": "Representation used to select the segment.",
                },
            ),
            "start_time": (
                "FLOAT",
                {
                    "default": 0.0,
                    "min": -1.0,
                    "max": 1_000_000_000.0,
                    "step": 0.001,
                    "tooltip": "Inclusive start in seconds.",
                },
            ),
            "end_time": (
                "FLOAT",
                {
                    "default": -1.0,
                    "min": -1.0,
                    "max": 1_000_000_000.0,
                    "step": 0.001,
                    "tooltip": "Exclusive end in seconds, or -1 for source end.",
                },
            ),
            "first_frame": (
                "INT",
                {
                    "default": 0,
                    "min": -1,
                    "max": 2_147_483_647,
                    "tooltip": "Inclusive zero-based first frame index.",
                },
            ),
            "last_frame": (
                "INT",
                {
                    "default": -1,
                    "min": -1,
                    "max": 2_147_483_647,
                    "tooltip": (
                        "Inclusive zero-based last frame index, or -1 for "
                        "source end."
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


def test_resize_image_by_long_side_v1_schema_is_exact(monkeypatch):
    package = load_root_package(monkeypatch)
    node = package.NODE_CLASS_MAPPINGS["LFGG_ResizeImageByLongSide"]

    assert (
        package.NODE_DISPLAY_NAME_MAPPINGS["LFGG_ResizeImageByLongSide"]
        == "LFGG Resize Image by Long Side"
    )
    assert node.CATEGORY == "LFGG/image"
    assert node.DESCRIPTION == (
        "Resizes an image to aligned dimensions without upscaling or exceeding "
        "the selected long-side limit."
    )
    assert node.FUNCTION == "resize"
    assert node.RETURN_TYPES == ("IMAGE", "INT", "INT")
    assert node.RETURN_NAMES == ("image", "width", "height")
    assert node.OUTPUT_TOOLTIPS == (
        "Image resized to the aligned dimensions.",
        "Aligned output width in pixels.",
        "Aligned output height in pixels.",
    )
    assert node.INPUT_TYPES()["required"] == {
        "image": (
            "IMAGE",
            {"tooltip": "Image batch to resize."},
        ),
        "upscale_method": (
            ["lanczos", "nearest-exact", "bilinear", "area", "bicubic"],
            {"tooltip": "Interpolation method used when resizing the image."},
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
    resize_required = package.NODE_CLASS_MAPPINGS[
        "LFGG_ResizeImageByLongSide"
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
    assert resize_required["long_side"][1]["max"] == 4096
    assert resize_required["divisible_by"][1]["max"] == 4096
    assert pixel_required["max_pixels"][1]["max"] == 4096**2
    assert pixel_required["divisible_by"][1]["max"] == 4096
    assert crop_required["ratio_width"][1]["max"] == 4096
    assert crop_required["ratio_height"][1]["max"] == 4096
    assert crop_required["crop_x"][1]["max"] == 4096
    assert crop_required["crop_y"][1]["max"] == 4096
    assert crop_required["crop_width"][1]["max"] == 4096
    assert crop_required["crop_height"][1]["max"] == 4096


def test_metadata_manifest_and_workflow_match_the_release_contract(
    monkeypatch, tmp_path
):
    pyproject_path = ROOT / "pyproject.toml"
    manifest_path = ROOT / "release" / "1.5.0-schema.json"
    workflow_path = ROOT / "workflows" / "sizing.json"
    save_workflow_path = ROOT / "workflows" / "save_image_dynamic.json"
    crop_workflow_path = ROOT / "workflows" / "load_and_crop_image.json"
    video_workflow_path = ROOT / "workflows" / "video_cutter.json"
    crop_asset_path = ROOT / "workflows" / "load_and_crop_image.png"
    crop_help_path = ROOT / "web" / "docs" / "LFGG_LoadAndCropImage" / "en.md"
    power_lora_help_path = (
        ROOT / "web" / "docs" / "LFGG_PowerLoraLoaderFolder" / "en.md"
    )
    video_help_path = ROOT / "web" / "docs" / "LFGG_VideoCutter" / "en.md"
    assert pyproject_path.exists(), "pyproject.toml is not implemented"
    assert manifest_path.exists(), "release schema manifest is not implemented"
    assert workflow_path.exists(), "complete sizing API workflow is not implemented"
    assert save_workflow_path.exists(), "dynamic save API workflow is not implemented"
    assert crop_workflow_path.exists(), "load and crop API workflow is not implemented"
    assert video_workflow_path.exists(), "video cutter API workflow is not implemented"
    assert crop_asset_path.exists(), (
        "load and crop workflow input asset is not implemented"
    )
    assert crop_help_path.exists(), "load and crop embedded help is not implemented"
    assert power_lora_help_path.exists(), (
        "power LoRA loader embedded help is not implemented"
    )
    assert video_help_path.exists(), "video cutter embedded help is not implemented"

    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib

    metadata = tomllib.loads(pyproject_path.read_text())
    project = metadata["project"]
    comfy = metadata["tool"]["comfy"]
    assert project["name"] == "lfgg-nodes"
    assert project["version"] == "1.5.0"
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
        "node --test tests/frontend/crop_editor.test.mjs",
        "node --test tests/frontend/power_lora_loader.test.mjs",
        "node --test tests/frontend/video_cutter.test.mjs",
        "node --test tests/frontend/prompt_composer.test.mjs",
        "node --test tests/frontend/routing_organizer.test.mjs",
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
        "LFGG Load and Crop Image",
        "one still image",
        "ComfyUI input directory",
        "does not access the network and writes no files",
        "without resampling",
        "Alpha-derived mask",
        "dynamic ratio",
        "frontend extension is unavailable",
        "Stable ID `LFGG_LoadAndCropImage`",
        "`image` (required selection)",
        "`ratio_width` (default `1`)",
        "`ratio_height` (default `1`)",
        "`crop_x` (default `0`)",
        "`crop_y` (default `0`)",
        "`crop_width` (default `0`)",
        "`crop_height` (default `0`)",
        "Outputs: `image` (`IMAGE`) and `mask` (`MASK`)",
        "`Run to resolve connected ratio`",
            "`workflows/load_and_crop_image.png`",
            "copy it to `ComfyUI/input/load_and_crop_image.png`",
            "same selected image and resolved ratio",
            "LFGG Resize Image by Long Side",
            "`lanczos`",
            "`nearest-exact`",
            "`bilinear`",
            "`area`",
            "`bicubic`",
        "returns the original tensor",
        "LFGG Power LoRA Loader (Folder)",
        "recursive folder filtering",
        "`All LoRAs`",
        "existing rows",
        "ordered",
        "Refresh node definitions",
        "does not require rgthree",
        "no network calls or file writes",
        "LFGG Video Cutter",
        "Stable ID `LFGG_VideoCutter`",
        "start-inclusive and end-exclusive",
        "zero-based and inclusive",
        "native `VideoInput.as_trimmed`",
        "variable-frame-rate",
        "`POST /lfgg/v1/video-metadata`",
        "selection looping",
        "workflows/video_cutter.json",
        "LFGG Prompt Composer",
        "Stable ID `LFGG_PromptComposer`",
        "`__folder/name__`",
        "`[[style:Exact Name]]`",
        "`GET /lfgg/v1/prompt-composer/libraries`",
        "disabled headings",
        ]:
        assert claim in readme

    input_directory = tmp_path / "input"
    input_directory.mkdir()
    (input_directory / "load_and_crop_image.png").write_bytes(b"fixture")
    monkeypatch.setitem(
        sys.modules,
        "folder_paths",
        types.SimpleNamespace(
            get_input_directory=lambda: str(input_directory),
            get_filename_list=lambda _category: [],
        ),
    )
    package = load_root_package(monkeypatch)
    help_ids = {
        path.name
        for path in (ROOT / "web" / "docs").iterdir()
        if (path / "en.md").is_file()
    }
    assert help_ids == {
        "LFGG_LoadAndCropImage",
        "LFGG_PowerLoraLoaderFolder",
        "LFGG_PromptComposer",
        "LFGG_VideoCutter",
    }
    assert help_ids <= package.NODE_CLASS_MAPPINGS.keys()

    with Image.open(crop_asset_path) as asset:
        assert asset.mode == "RGBA"
        assert asset.size == (6, 4)
        assert [
            asset.getpixel((x, y))
            for y in range(asset.height)
            for x in range(asset.width)
        ] == [
            (100, 110, 120, 0) if (x, y) == (1, 0) else (10, 20, 30, 255)
            for y in range(4)
            for x in range(6)
        ]

    expected_nodes = {}
    for node_id, node in package.NODE_CLASS_MAPPINGS.items():
        if node_id in {
            "LFGG_PromptComposer",
            "LFGG_RoutingOrganizer",
            "LFGG_VideoCutter",
        }:
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
        "version": "1.5.0",
        "nodes": expected_nodes,
    }

    video_workflow = json.loads(video_workflow_path.read_text())
    assert video_workflow == {
        "1": {"class_type": "LoadVideo", "inputs": {"file": "video_cutter.mp4"}},
        "2": {
            "class_type": "LFGG_VideoCutter",
            "inputs": {
                "video": ["1", 0],
                "selection_mode": "Frames",
                "start_time": 0.0,
                "end_time": -1.0,
                "first_frame": 3,
                "last_frame": 8,
            },
        },
        "3": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["2", 0],
                "filename_prefix": "lfgg/video/cut",
                "format": "mp4",
                "codec": "h264",
            },
        },
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
    assert workflow["11"] == {
        "class_type": "LFGG_ResizeImageByLongSide",
        "inputs": {
            "image": ["4", 0],
            "upscale_method": "lanczos",
            "long_side": 512,
            "divisible_by": 8,
        },
    }
    assert workflow["12"] == {
        "class_type": "SaveImage",
        "inputs": {
            "images": ["11", 0],
            "filename_prefix": "lfgg/sizing/resized",
        },
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

    assert json.loads(crop_workflow_path.read_text()) == {
        "1": {
            "class_type": "LFGG_LoadAndCropImage",
            "inputs": {
                "image": "load_and_crop_image.png",
                "ratio_width": 1,
                "ratio_height": 1,
                "crop_x": 1,
                "crop_y": 0,
                "crop_width": 4,
                "crop_height": 4,
            },
        },
        "2": {
            "class_type": "LFGG_SaveImageDynamic",
            "inputs": {
                "images": ["1", 0],
                "path_template": "lfgg/crop",
                "filename_template": "image",
                "save_metadata": False,
            },
        },
        "3": {
            "class_type": "MaskToImage",
            "inputs": {"mask": ["1", 1]},
        },
        "4": {
            "class_type": "LFGG_SaveImageDynamic",
            "inputs": {
                "images": ["3", 0],
                "path_template": "lfgg/crop",
                "filename_template": "mask",
                "save_metadata": False,
            },
        },
    }
