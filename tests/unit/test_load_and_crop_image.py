import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch
from PIL import Image

import lfgg_nodes.load_and_crop_image as load_and_crop_image_module
from lfgg_nodes.load_and_crop_image import LoadAndCropImage, resolve_crop


def install_folder_paths(monkeypatch, input_root, *, resolve_name=None):
    module = SimpleNamespace(
        get_input_directory=lambda: str(input_root),
        get_annotated_filepath=lambda name: str(
            input_root / name if resolve_name is None else resolve_name(name)
        ),
    )
    monkeypatch.setitem(sys.modules, "folder_paths", module)
    monkeypatch.setitem(sys.modules, "nodes", SimpleNamespace(MAX_RESOLUTION=16_384))


def load_default_crop(image="source.png"):
    return LoadAndCropImage().load_and_crop(
        image=image,
        ratio_width=1,
        ratio_height=1,
        crop_x=0,
        crop_y=0,
        crop_width=0,
        crop_height=0,
    )


def test_loads_and_crops_rgba_image(monkeypatch, tmp_path):
    pixels = Image.new("RGBA", (4, 3), (10, 20, 30, 255))
    pixels.putpixel((0, 0), (100, 110, 120, 0))
    pixels.save(tmp_path / "source.png")
    install_folder_paths(monkeypatch, tmp_path)

    result = load_default_crop()

    image, mask = result["result"]
    assert image.shape == (1, 3, 3, 3)
    assert mask.shape == (1, 3, 3)
    assert image.dtype == torch.float32
    assert mask.dtype == torch.float32
    assert torch.allclose(image[0, 0, 0], torch.tensor([100, 110, 120]) / 255)
    assert mask[0, 0, 0].item() == pytest.approx(1.0)
    assert result["ui"]["crop"] == [
        {
            "ratio_width": 1,
            "ratio_height": 1,
            "x": 0,
            "y": 0,
            "width": 3,
            "height": 3,
        }
    ]


def test_rgb_image_has_a_zero_mask(monkeypatch, tmp_path):
    Image.new("RGB", (4, 3), (10, 20, 30)).save(tmp_path / "source.png")
    install_folder_paths(monkeypatch, tmp_path)

    image, mask = load_default_crop()["result"]

    assert image.shape == (1, 3, 3, 3)
    assert mask.shape == (1, 3, 3)
    assert torch.equal(mask, torch.zeros((1, 3, 3), dtype=torch.float32))


def test_applies_exif_orientation_before_interpreting_crop_coordinates(
    monkeypatch, tmp_path
):
    pixels = Image.new("RGB", (4, 2), (10, 20, 30))
    exif = Image.Exif()
    exif[274] = 6
    pixels.save(tmp_path / "source.jpg", exif=exif)
    install_folder_paths(monkeypatch, tmp_path)

    image, mask = LoadAndCropImage().load_and_crop(
        image="source.jpg",
        ratio_width=1,
        ratio_height=1,
        crop_x=0,
        crop_y=2,
        crop_width=2,
        crop_height=2,
    )["result"]

    assert image.shape == (1, 2, 2, 3)
    assert mask.shape == (1, 2, 2)


def test_rejects_animated_images(monkeypatch, tmp_path):
    first = Image.new("RGB", (2, 2), (10, 20, 30))
    first.save(
        tmp_path / "source.gif",
        save_all=True,
        append_images=[Image.new("RGB", (2, 2), (40, 50, 60))],
    )
    install_folder_paths(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="single still image"):
        LoadAndCropImage().load_and_crop(
            image="source.gif",
            ratio_width=1,
            ratio_height=1,
            crop_x=0,
            crop_y=0,
            crop_width=0,
            crop_height=0,
        )


def test_rejects_images_above_the_axis_limit_before_tensor_conversion(
    monkeypatch, tmp_path
):
    Image.new("RGB", (4, 1)).save(tmp_path / "source.png")
    install_folder_paths(monkeypatch, tmp_path)
    monkeypatch.setitem(sys.modules, "nodes", SimpleNamespace(MAX_RESOLUTION=3))
    monkeypatch.setattr(
        torch,
        "from_numpy",
        lambda _pixels: pytest.fail("tensor conversion must not be reached"),
    )

    with pytest.raises(ValueError, match="maximum supported resolution"):
        load_default_crop()


def test_rejects_images_above_the_pixel_limit_before_tensor_conversion(
    monkeypatch, tmp_path
):
    Image.new("RGB", (3, 3)).save(tmp_path / "source.png")
    install_folder_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("lfgg_nodes.load_and_crop_image.MAX_IMAGE_PIXELS", 8)
    monkeypatch.setattr(
        torch,
        "from_numpy",
        lambda _pixels: pytest.fail("tensor conversion must not be reached"),
    )

    with pytest.raises(ValueError, match="pixel limit"):
        load_default_crop()


def test_rejects_corrupt_images_with_an_actionable_error(monkeypatch, tmp_path):
    (tmp_path / "source.png").write_bytes(b"not an image")
    install_folder_paths(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="could not be opened"):
        load_default_crop()


def test_rejects_paths_outside_the_input_directory(monkeypatch, tmp_path):
    outside = tmp_path.parent / "outside.png"
    Image.new("RGB", (1, 1)).save(outside)
    install_folder_paths(monkeypatch, tmp_path, resolve_name=lambda _: outside)

    with pytest.raises(ValueError, match="ComfyUI input directory"):
        load_default_crop()


def test_rejects_symlink_escapes_from_the_input_directory(monkeypatch, tmp_path):
    outside = tmp_path.parent / "outside.png"
    Image.new("RGB", (1, 1)).save(outside)
    link = tmp_path / "source.png"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable on this platform")
    install_folder_paths(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="ComfyUI input directory"):
        load_default_crop()


@pytest.mark.parametrize("operation", ["load", "hash"])
def test_rejects_file_replaced_by_external_symlink_before_open(
    monkeypatch, tmp_path, operation
):
    source = tmp_path / "source.png"
    outside = tmp_path.parent / "outside.png"
    Image.new("RGB", (1, 1), (10, 20, 30)).save(source)
    Image.new("RGB", (1, 1), (40, 50, 60)).save(outside)
    install_folder_paths(monkeypatch, tmp_path)
    original_input_path = load_and_crop_image_module._input_path

    def replace_after_validation(image):
        validated = original_input_path(image)
        source.unlink()
        try:
            source.symlink_to(outside)
        except OSError:
            pytest.skip("symlinks are unavailable on this platform")
        return validated

    monkeypatch.setattr(
        load_and_crop_image_module,
        "_input_path",
        replace_after_validation,
    )

    with pytest.raises(ValueError, match="ComfyUI input directory"):
        if operation == "load":
            load_default_crop()
        else:
            LoadAndCropImage.IS_CHANGED("source.png")


def test_rejects_absolute_image_identifier_inside_input_directory(
    monkeypatch, tmp_path
):
    source = tmp_path / "source.png"
    Image.new("RGB", (1, 1)).save(source)
    install_folder_paths(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="relative"):
        load_default_crop(str(source))
    assert "relative" in LoadAndCropImage.VALIDATE_INPUTS(str(source))


def test_fails_actionably_without_secure_descriptor_opening(monkeypatch, tmp_path):
    Image.new("RGB", (1, 1)).save(tmp_path / "source.png")
    install_folder_paths(monkeypatch, tmp_path)
    monkeypatch.delattr(os, "O_NOFOLLOW")

    with pytest.raises(ValueError, match="secure selected-image access"):
        load_default_crop()


@pytest.mark.parametrize("image", [None, b"source.png", Path("source.png")])
def test_requires_image_identifier_to_be_a_string(monkeypatch, tmp_path, image):
    Image.new("RGB", (1, 1)).save(tmp_path / "source.png")
    install_folder_paths(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="string"):
        load_default_crop(image)
    assert "string" in LoadAndCropImage.VALIDATE_INPUTS(image)


def test_change_fingerprint_tracks_file_content(monkeypatch, tmp_path):
    source = tmp_path / "source.png"
    source.write_bytes(b"first")
    install_folder_paths(monkeypatch, tmp_path)

    first = LoadAndCropImage.IS_CHANGED("source.png")
    source.write_bytes(b"second")

    assert LoadAndCropImage.IS_CHANGED("source.png") != first


def test_validates_the_selected_input_path(monkeypatch, tmp_path):
    Image.new("RGB", (1, 1)).save(tmp_path / "source.png")
    install_folder_paths(monkeypatch, tmp_path)

    assert LoadAndCropImage.VALIDATE_INPUTS("source.png") is True
    assert "selected image" in LoadAndCropImage.VALIDATE_INPUTS("../bad.png")


def test_initializes_the_largest_centered_exact_ratio_crop():
    assert resolve_crop(
        source_width=1920,
        source_height=1080,
        ratio_width=4,
        ratio_height=5,
        crop_x=0,
        crop_y=0,
        crop_width=0,
        crop_height=0,
        max_resolution=16_384,
    ) == (528, 0, 864, 1080, 4, 5)


def test_reduces_ratio_components_before_fitting():
    assert resolve_crop(
        source_width=1920,
        source_height=1080,
        ratio_width=1920,
        ratio_height=1080,
        crop_x=160,
        crop_y=90,
        crop_width=1600,
        crop_height=900,
        max_resolution=16_384,
    ) == (160, 90, 1600, 900, 16, 9)


def test_changed_ratio_resets_instead_of_reusing_stale_geometry():
    assert resolve_crop(
        source_width=1920,
        source_height=1080,
        ratio_width=4,
        ratio_height=3,
        crop_x=160,
        crop_y=90,
        crop_width=1600,
        crop_height=900,
        max_resolution=16_384,
    ) == (240, 0, 1440, 1080, 4, 3)


def test_matching_ratio_rejects_out_of_bounds_geometry():
    with pytest.raises(ValueError, match="inside the source image"):
        resolve_crop(
            source_width=100,
            source_height=100,
            ratio_width=1,
            ratio_height=1,
            crop_x=50,
            crop_y=50,
            crop_width=60,
            crop_height=60,
            max_resolution=16_384,
        )


def test_centers_odd_remaining_pixels_by_rounding_down():
    assert resolve_crop(
        source_width=101,
        source_height=100,
        ratio_width=3,
        ratio_height=2,
        crop_x=0,
        crop_y=0,
        crop_width=0,
        crop_height=0,
        max_resolution=16_384,
    ) == (1, 17, 99, 66, 3, 2)


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"source_width": 0}, "source_width"),
        ({"ratio_width": 0}, "ratio_width"),
        ({"ratio_width": True}, "ratio_width"),
        ({"crop_x": -1}, "crop_x"),
        ({"crop_y": 1.5}, "crop_y"),
        ({"source_height": 16_385}, "source_height"),
        ({"crop_width": 0, "crop_height": 1}, "crop dimensions"),
        ({"ratio_width": 101, "ratio_height": 1}, "does not fit"),
    ],
)
def test_rejects_invalid_or_impossible_geometry(arguments, message):
    values = {
        "source_width": 100,
        "source_height": 100,
        "ratio_width": 1,
        "ratio_height": 1,
        "crop_x": 0,
        "crop_y": 0,
        "crop_width": 100,
        "crop_height": 100,
        "max_resolution": 16_384,
    }
    values.update(arguments)

    with pytest.raises(ValueError, match=message):
        resolve_crop(**values)
