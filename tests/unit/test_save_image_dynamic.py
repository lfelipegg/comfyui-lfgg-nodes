import sys
import types
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
import torch
from PIL import Image

import lfgg_nodes.save_image_dynamic as save_module
from lfgg_nodes.save_image_dynamic import (
    MAX_METADATA_BYTES,
    ParsedTemplate,
    SaveImageDynamic,
    image_to_pillow,
    render_filename,
    render_relative_path,
    serialize_metadata,
    validate_images,
)

NOW = datetime(2026, 7, 27, 15, 4, 5)


def render(template, **overrides):
    values = {
        "model": None,
        "timestamp": NOW,
        "width": 64,
        "height": 32,
        "batch": 0,
        "counter": 1,
    }
    values.update(overrides)
    return template.render(**values)


def test_template_expands_supported_tokens_and_defaults():
    template = ParsedTemplate(
        "{model}|{date}|{time}|{datetime}|{width}|{height}|{batch}|{counter}",
        input_name="filename_template",
    )

    assert render(template) == (
        "unknown_model|2026-07-27|15-04-05|2026-07-27_15-04-05|"
        "64|32|0|00001"
    )
    assert render(template, model="  ") == render(template)


def test_template_allows_literal_braces_and_reuses_the_supplied_timestamp():
    template = ParsedTemplate(
        "{{run}}_{date}_{time}",
        input_name="filename_template",
    )

    assert render(template) == "{run}_2026-07-27_15-04-05"
    assert render(template, batch=9) == "{run}_2026-07-27_15-04-05"


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("{missing}", "unknown field"),
        ("{model!r}", "conversions"),
        ("{counter:03}", "format specifications"),
        ("{model.value}", "unknown field"),
        ("{}", "unknown field"),
        ("{model", "malformed"),
    ],
)
def test_template_rejects_unsupported_or_malformed_fields(source, message):
    with pytest.raises(ValueError, match=message):
        ParsedTemplate(source, input_name="filename_template")


def test_template_enforces_input_and_counter_bounds():
    with pytest.raises(ValueError, match="512"):
        ParsedTemplate("x" * 513, input_name="path_template")

    template = ParsedTemplate("{counter}", input_name="filename_template")
    with pytest.raises(ValueError, match="counter"):
        render(template, counter=0)
    with pytest.raises(ValueError, match="counter"):
        render(template, counter=100_000)


def test_relative_path_sanitizes_components_and_protects_reserved_names():
    template = ParsedTemplate(
        r"runs\{model}\CON\a<b",
        input_name="path_template",
    )

    assert (
        render_relative_path(
            template,
            model="model/name",
            timestamp=NOW,
            width=64,
            height=32,
            batch=0,
            counter=1,
        ).as_posix()
        == "runs/model_name/_CON/a_b"
    )


@pytest.mark.parametrize(
    "source",
    ["/absolute", r"C:\drive", "../escape", r"nested\..\escape"],
)
def test_relative_path_rejects_absolute_drive_and_traversal(source):
    template = ParsedTemplate(source, input_name="path_template")

    with pytest.raises(ValueError, match="path_template"):
        render_relative_path(
            template,
            model="model",
            timestamp=NOW,
            width=64,
            height=32,
            batch=0,
            counter=1,
        )


def test_relative_path_allows_an_empty_subfolder():
    template = ParsedTemplate("", input_name="path_template")

    assert render_relative_path(
        template,
        model=None,
        timestamp=NOW,
        width=64,
        height=32,
        batch=0,
        counter=1,
    ).as_posix() == "."


def test_filename_normalizes_png_once_and_appends_a_counter_when_absent():
    plain = ParsedTemplate("image.png", input_name="filename_template")
    explicit = ParsedTemplate(
        "{model}_{counter}.png",
        input_name="filename_template",
    )

    assert render_filename(
        plain,
        counter_in_templates=False,
        model="model",
        timestamp=NOW,
        width=64,
        height=32,
        batch=0,
        counter=1,
    ) == "image_00001_.png"
    assert render_filename(
        explicit,
        counter_in_templates=True,
        model="a/b",
        timestamp=NOW,
        width=64,
        height=32,
        batch=0,
        counter=7,
    ) == "a_b_00007.png"


@pytest.mark.parametrize("source", ["CON", "nul.png", "LPT9"])
def test_filename_protects_windows_reserved_names(source):
    template = ParsedTemplate(source, input_name="filename_template")

    assert render_filename(
        template,
        counter_in_templates=True,
        model="model",
        timestamp=NOW,
        width=64,
        height=32,
        batch=0,
        counter=1,
    ).startswith("_")


@pytest.mark.parametrize("source", ["", ".png", "   ", "   .png"])
def test_filename_rejects_an_empty_stem(source):
    template = ParsedTemplate(source, input_name="filename_template")

    with pytest.raises(ValueError, match="filename_template"):
        render_filename(
            template,
            counter_in_templates=True,
            model="model",
            timestamp=NOW,
            width=64,
            height=32,
            batch=0,
            counter=1,
        )


def test_rendered_components_and_filename_stems_are_bounded():
    path = ParsedTemplate("x" * 201, input_name="path_template")
    filename = ParsedTemplate("x" * 201, input_name="filename_template")
    arguments = {
        "model": "model",
        "timestamp": NOW,
        "width": 64,
        "height": 32,
        "batch": 0,
        "counter": 1,
    }

    with pytest.raises(ValueError, match="200"):
        render_relative_path(path, **arguments)
    with pytest.raises(ValueError, match="200"):
        render_filename(filename, counter_in_templates=True, **arguments)


@pytest.mark.parametrize(
    "images",
    [
        [],
        torch.zeros((4, 4, 3)),
        torch.empty((0, 4, 4, 3)),
        torch.empty((1, 0, 4, 3)),
        torch.empty((1, 4, 0, 3)),
        torch.empty((1, 4, 4, 0)),
        torch.zeros((1, 4, 4, 2)),
        torch.zeros((1, 4, 4, 3), dtype=torch.bool),
        torch.zeros((1, 4, 4, 3), dtype=torch.complex64),
    ],
)
def test_image_validation_rejects_invalid_types_shapes_channels_and_dtypes(images):
    with pytest.raises(ValueError, match=r"IMAGE.*\[B,H,W,C\]|IMAGE.*numeric"):
        validate_images(images)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_image_validation_rejects_non_finite_values(value):
    images = torch.zeros((1, 2, 2, 3))
    images[0, 0, 0, 0] = value

    with pytest.raises(ValueError, match="finite"):
        validate_images(images)


@pytest.mark.parametrize("channels", [1, 3, 4])
def test_image_validation_accepts_supported_real_tensor_batches(channels):
    images = torch.zeros((2, 3, 5, channels), dtype=torch.float64)

    assert validate_images(images) == (2, 3, 5, channels)


@pytest.mark.parametrize(
    ("channels", "mode"),
    [(1, "L"), (3, "RGB"), (4, "RGBA")],
)
def test_image_conversion_clamps_without_mutating_the_input(channels, mode):
    frame = torch.linspace(-0.5, 1.5, 4 * channels).reshape(1, 4, channels)
    original = frame.clone()

    image = image_to_pillow(frame)

    assert image.mode == mode
    assert image.size == (4, 1)
    assert image.getpixel((0, 0)) == (0 if channels == 1 else (0,) * channels)
    assert image.getpixel((3, 0)) == (
        255 if channels == 1 else (255,) * channels
    )
    assert torch.equal(frame, original)


def test_metadata_serializes_prompt_and_every_extra_entry():
    metadata = serialize_metadata(
        save_metadata=True,
        global_disabled=False,
        prompt={"text": "hello"},
        extra_pnginfo={
            "workflow": {"nodes": [1]},
            "custom": ["value"],
        },
    )

    assert metadata == [
        ("prompt", '{"text": "hello"}'),
        ("workflow", '{"nodes": [1]}'),
        ("custom", '["value"]'),
    ]


@pytest.mark.parametrize(
    ("save_metadata", "global_disabled"),
    [(False, False), (True, True), (False, True)],
)
def test_metadata_toggles_skip_serialization(save_metadata, global_disabled):
    assert (
        serialize_metadata(
            save_metadata=save_metadata,
            global_disabled=global_disabled,
            prompt=object(),
            extra_pnginfo={"bad": object()},
        )
        is None
    )


@pytest.mark.parametrize(
    ("prompt", "extra_pnginfo", "message"),
    [
        (None, [], "EXTRA_PNGINFO"),
        (None, {1: "value"}, "keys"),
        (object(), None, "prompt"),
        (None, {"workflow": object()}, "workflow"),
    ],
)
def test_metadata_rejects_invalid_inputs_without_disclosing_values(
    prompt,
    extra_pnginfo,
    message,
):
    with pytest.raises(ValueError, match=message):
        serialize_metadata(
            save_metadata=True,
            global_disabled=False,
            prompt=prompt,
            extra_pnginfo=extra_pnginfo,
        )


def test_metadata_enforces_the_exact_64_mib_serialized_boundary():
    assert MAX_METADATA_BYTES == 64 * 1024 * 1024
    at_limit = "x" * (MAX_METADATA_BYTES - 2)
    metadata = serialize_metadata(
        save_metadata=True,
        global_disabled=False,
        prompt=at_limit,
        extra_pnginfo=None,
    )
    assert len(metadata[0][1].encode()) == MAX_METADATA_BYTES
    del metadata, at_limit

    above_limit = "x" * (MAX_METADATA_BYTES - 1)
    with pytest.raises(ValueError, match="64 MiB"):
        serialize_metadata(
            save_metadata=True,
            global_disabled=False,
            prompt=above_limit,
            extra_pnginfo=None,
        )


def install_comfy_stubs(monkeypatch, output_root, *, disable_metadata=False):
    folder_paths = types.ModuleType("folder_paths")
    folder_paths.get_output_directory = lambda: str(output_root)
    comfy = types.ModuleType("comfy")
    comfy.__path__ = []
    cli_args = types.ModuleType("comfy.cli_args")
    cli_args.args = types.SimpleNamespace(disable_metadata=disable_metadata)
    monkeypatch.setitem(sys.modules, "folder_paths", folder_paths)
    monkeypatch.setitem(sys.modules, "comfy", comfy)
    monkeypatch.setitem(sys.modules, "comfy.cli_args", cli_args)


def save_images(
    images,
    *,
    path_template="",
    filename_template="image",
    save_metadata=True,
    model_name=None,
    prompt=None,
    extra_pnginfo=None,
):
    return SaveImageDynamic().save_images(
        images,
        path_template,
        filename_template,
        save_metadata,
        model_name=model_name,
        prompt=prompt,
        extra_pnginfo=extra_pnginfo,
    )


def test_save_writes_a_batch_with_metadata_and_relative_descriptors(
    monkeypatch,
    tmp_path,
):
    output = tmp_path / "output"
    output.mkdir()
    install_comfy_stubs(monkeypatch, output)
    images = torch.stack(
        (
            torch.zeros((2, 3, 3)),
            torch.ones((2, 3, 3)),
        )
    )
    original = images.clone()
    pointer = images.data_ptr()

    result = save_images(
        images,
        path_template="runs/{model}",
        filename_template="{batch}",
        model_name="model/name",
        prompt={"text": "hello"},
        extra_pnginfo={"workflow": {"nodes": [1]}},
    )

    assert result == {
        "ui": {
            "images": [
                {
                    "filename": "0_00001_.png",
                    "subfolder": "runs/model_name",
                    "type": "output",
                },
                {
                    "filename": "1_00002_.png",
                    "subfolder": "runs/model_name",
                    "type": "output",
                },
            ]
        }
    }
    assert torch.equal(images, original)
    assert images.data_ptr() == pointer
    for index, descriptor in enumerate(result["ui"]["images"]):
        path = output / descriptor["subfolder"] / descriptor["filename"]
        with Image.open(path) as image:
            assert image.mode == "RGB"
            assert image.size == (3, 2)
            assert image.getpixel((0, 0)) == ((255,) * 3 if index else (0,) * 3)
            assert image.text == {
                "prompt": '{"text": "hello"}',
                "workflow": '{"nodes": [1]}',
            }


@pytest.mark.parametrize(("channels", "mode"), [(1, "L"), (3, "RGB"), (4, "RGBA")])
def test_save_writes_supported_png_channel_modes(
    monkeypatch,
    tmp_path,
    channels,
    mode,
):
    output = tmp_path / "output"
    output.mkdir()
    install_comfy_stubs(monkeypatch, output)

    result = save_images(
        torch.ones((1, 2, 3, channels)),
        filename_template="mode_{counter}",
        save_metadata=False,
    )

    descriptor = result["ui"]["images"][0]
    with Image.open(output / descriptor["filename"]) as image:
        assert image.mode == mode
        assert image.size == (3, 2)


@pytest.mark.parametrize(
    ("save_metadata", "global_disabled"),
    [(False, False), (True, True)],
)
def test_save_respects_both_metadata_toggles(
    monkeypatch,
    tmp_path,
    save_metadata,
    global_disabled,
):
    output = tmp_path / "output"
    output.mkdir()
    install_comfy_stubs(
        monkeypatch,
        output,
        disable_metadata=global_disabled,
    )

    result = save_images(
        torch.zeros((1, 1, 1, 3)),
        filename_template="metadata",
        save_metadata=save_metadata,
        prompt={"private": "prompt"},
        extra_pnginfo={"workflow": {"private": "workflow"}},
    )

    with Image.open(output / result["ui"]["images"][0]["filename"]) as image:
        assert image.text == {}


def test_save_validates_the_full_request_before_creating_directories(
    monkeypatch,
    tmp_path,
):
    output = tmp_path / "output"
    output.mkdir()
    install_comfy_stubs(monkeypatch, output)
    images = torch.zeros((2, 1, 1, 3))
    images[1, 0, 0, 0] = float("nan")

    with pytest.raises(ValueError, match="finite"):
        save_images(images, path_template="must-not-exist")

    assert not (output / "must-not-exist").exists()


@pytest.mark.parametrize(
    "path_template",
    ["/absolute", r"C:\drive", "../escape", r"nested\..\escape"],
)
def test_save_rejects_non_relative_output_paths(
    monkeypatch,
    tmp_path,
    path_template,
):
    output = tmp_path / "output"
    output.mkdir()
    install_comfy_stubs(monkeypatch, output)

    with pytest.raises(ValueError, match="path_template"):
        save_images(
            torch.zeros((1, 1, 1, 3)),
            path_template=path_template,
        )


def test_save_rejects_a_preexisting_symlink_escape_without_path_leakage(
    monkeypatch,
    tmp_path,
):
    output = tmp_path / "output"
    outside = tmp_path / "outside"
    output.mkdir()
    outside.mkdir()
    (output / "escape").symlink_to(outside, target_is_directory=True)
    install_comfy_stubs(monkeypatch, output)

    with pytest.raises(ValueError, match="output root") as failure:
        save_images(
            torch.zeros((1, 1, 1, 3)),
            path_template="escape",
        )

    assert str(output) not in str(failure.value)
    assert str(outside) not in str(failure.value)
    assert list(outside.iterdir()) == []


def test_save_never_overwrites_and_advances_the_exclusive_counter(
    monkeypatch,
    tmp_path,
):
    output = tmp_path / "output"
    output.mkdir()
    existing = output / "image_00001_.png"
    existing.write_bytes(b"existing")
    install_comfy_stubs(monkeypatch, output)

    result = save_images(torch.zeros((1, 1, 1, 3)))

    assert existing.read_bytes() == b"existing"
    assert result["ui"]["images"][0]["filename"] == "image_00002_.png"


def test_save_does_not_treat_a_directory_creation_error_as_a_name_collision(
    monkeypatch,
    tmp_path,
):
    output = tmp_path / "output"
    output.mkdir()
    (output / "blocked").write_bytes(b"not a directory")
    install_comfy_stubs(monkeypatch, output)
    monkeypatch.setattr(save_module, "MAX_COUNTER", 2)

    with pytest.raises(OSError, match=r"blocked/image_00001_\.png.*File exists"):
        save_images(
            torch.zeros((1, 1, 1, 3)),
            path_template="blocked",
        )


def test_save_rerenders_both_templates_when_counter_is_explicit(
    monkeypatch,
    tmp_path,
):
    output = tmp_path / "output"
    (output / "run_00001").mkdir(parents=True)
    (output / "run_00001" / "image.png").write_bytes(b"existing")
    install_comfy_stubs(monkeypatch, output)

    result = save_images(
        torch.zeros((1, 1, 1, 3)),
        path_template="run_{counter}",
        filename_template="image",
    )

    assert result["ui"]["images"] == [
        {
            "filename": "image.png",
            "subfolder": "run_00002",
            "type": "output",
        }
    ]


def test_simultaneous_saves_reserve_distinct_files(monkeypatch, tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    install_comfy_stubs(monkeypatch, output)
    images = torch.zeros((1, 1, 1, 3))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: save_images(images), range(2)))

    filenames = sorted(
        result["ui"]["images"][0]["filename"] for result in results
    )
    assert filenames == ["image_00001_.png", "image_00002_.png"]
    assert all((output / filename).stat().st_size > 0 for filename in filenames)


def test_later_frame_write_failure_rolls_back_only_this_execution(
    monkeypatch,
    tmp_path,
):
    output = tmp_path / "output"
    output.mkdir()
    existing = output / "image_00001_.png"
    existing.write_bytes(b"existing")
    install_comfy_stubs(monkeypatch, output)
    original_save = Image.Image.save
    writes = 0

    def fail_second_write(image, file, *args, **kwargs):
        nonlocal writes
        writes += 1
        if writes == 2:
            raise OSError("disk full")
        return original_save(image, file, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "save", fail_second_write)

    with pytest.raises(OSError, match=r"image_00003_\.png.*disk full") as failure:
        save_images(torch.zeros((2, 1, 1, 3)))

    assert str(output) not in str(failure.value)
    assert existing.read_bytes() == b"existing"
    assert sorted(path.name for path in output.iterdir()) == [existing.name]


def test_counter_exhaustion_fails_without_overwrite(monkeypatch, tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    (output / "image_00001_.png").write_bytes(b"one")
    (output / "image_00002_.png").write_bytes(b"two")
    install_comfy_stubs(monkeypatch, output)
    monkeypatch.setattr(save_module, "MAX_COUNTER", 2)

    with pytest.raises(FileExistsError, match="counter"):
        save_images(torch.zeros((1, 1, 1, 3)))

    assert (output / "image_00001_.png").read_bytes() == b"one"
    assert (output / "image_00002_.png").read_bytes() == b"two"


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA unavailable")
def test_save_preserves_cuda_input_device_and_storage(monkeypatch, tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    install_comfy_stubs(monkeypatch, output)
    images = torch.rand((1, 2, 3, 3), device="cuda")
    original = images.clone()
    pointer = images.data_ptr()

    save_images(images, save_metadata=False)

    assert images.device.type == "cuda"
    assert images.data_ptr() == pointer
    assert torch.equal(images, original)
