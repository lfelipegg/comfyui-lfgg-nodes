from math import gcd

from .sizing import _bounded_int

MAX_IMAGE_PIXELS = 16_384**2


def _input_path(image):
    from pathlib import Path

    import folder_paths

    try:
        root = Path(folder_paths.get_input_directory()).resolve(strict=True)
        path = Path(folder_paths.get_annotated_filepath(image)).resolve(strict=True)
    except (OSError, TypeError):
        raise ValueError("selected image is unavailable") from None
    if not root.is_dir() or not path.is_file() or not path.is_relative_to(root):
        raise ValueError("selected image must stay inside the ComfyUI input directory")
    return path


def _content_hash(path):
    from hashlib import sha256

    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _largest_centered_crop(source_width, source_height, ratio_width, ratio_height):
    scale = min(source_width // ratio_width, source_height // ratio_height)
    if scale < 1:
        raise ValueError("crop ratio does not fit inside the source image")
    width = scale * ratio_width
    height = scale * ratio_height
    return (
        (source_width - width) // 2,
        (source_height - height) // 2,
        width,
        height,
    )


def resolve_crop(
    *,
    source_width,
    source_height,
    ratio_width,
    ratio_height,
    crop_x,
    crop_y,
    crop_width,
    crop_height,
    max_resolution,
):
    _bounded_int("source_width", source_width, 1, max_resolution)
    _bounded_int("source_height", source_height, 1, max_resolution)
    _bounded_int("ratio_width", ratio_width, 1, max_resolution)
    _bounded_int("ratio_height", ratio_height, 1, max_resolution)
    _bounded_int("crop_x", crop_x, 0, max_resolution)
    _bounded_int("crop_y", crop_y, 0, max_resolution)
    _bounded_int("crop_width", crop_width, 0, max_resolution)
    _bounded_int("crop_height", crop_height, 0, max_resolution)

    divisor = gcd(ratio_width, ratio_height)
    reduced_width = ratio_width // divisor
    reduced_height = ratio_height // divisor
    largest = _largest_centered_crop(
        source_width,
        source_height,
        reduced_width,
        reduced_height,
    )

    if crop_width == crop_height == 0:
        return (*largest, reduced_width, reduced_height)
    if crop_width < 1 or crop_height < 1:
        raise ValueError("crop dimensions must both be zero or both be positive")
    if crop_width * reduced_height != crop_height * reduced_width:
        return (*largest, reduced_width, reduced_height)
    if crop_x + crop_width > source_width or crop_y + crop_height > source_height:
        raise ValueError("crop rectangle must stay inside the source image")
    return (
        crop_x,
        crop_y,
        crop_width,
        crop_height,
        reduced_width,
        reduced_height,
    )


class LoadAndCropImage:
    def load_and_crop(
        self,
        image,
        ratio_width,
        ratio_height,
        crop_x,
        crop_y,
        crop_width,
        crop_height,
    ):
        import warnings

        import numpy as np
        import torch
        from nodes import MAX_RESOLUTION
        from PIL import Image, ImageOps

        path = _input_path(image)
        try:
            with path.open("rb") as source, warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                decoded = Image.open(source)
                if getattr(decoded, "n_frames", 1) != 1:
                    raise ValueError("selected image must be a single still image")
                oriented = ImageOps.exif_transpose(decoded)
                width, height = oriented.size
                if width < 1 or height < 1:
                    raise ValueError("selected image has invalid dimensions")
                if width > MAX_RESOLUTION or height > MAX_RESOLUTION:
                    raise ValueError(
                        "selected image exceeds the maximum supported resolution"
                    )
                if width * height > MAX_IMAGE_PIXELS:
                    raise ValueError(
                        f"selected image exceeds the {MAX_IMAGE_PIXELS}-pixel limit"
                    )
                rgb = torch.from_numpy(
                    np.array(oriented.convert("RGB"), dtype=np.float32, copy=True)
                    / 255.0
                ).unsqueeze(0)
                if "A" in oriented.getbands():
                    alpha = torch.from_numpy(
                        np.array(
                            oriented.getchannel("A"),
                            dtype=np.float32,
                            copy=True,
                        )
                        / 255.0
                    )
                    mask = (1.0 - alpha).unsqueeze(0)
                else:
                    mask = torch.zeros((1, height, width), dtype=torch.float32)
        except (
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            Image.UnidentifiedImageError,
            OSError,
            SyntaxError,
        ):
            raise ValueError(
                "selected image could not be opened as a valid image"
            ) from None

        x, y, crop_width, crop_height, reduced_width, reduced_height = resolve_crop(
            source_width=width,
            source_height=height,
            ratio_width=ratio_width,
            ratio_height=ratio_height,
            crop_x=crop_x,
            crop_y=crop_y,
            crop_width=crop_width,
            crop_height=crop_height,
            max_resolution=MAX_RESOLUTION,
        )
        return {
            "ui": {
                "crop": [
                    {
                        "ratio_width": reduced_width,
                        "ratio_height": reduced_height,
                        "x": x,
                        "y": y,
                        "width": crop_width,
                        "height": crop_height,
                    }
                ]
            },
            "result": (
                rgb[:, y : y + crop_height, x : x + crop_width, :],
                mask[:, y : y + crop_height, x : x + crop_width],
            ),
        }

    @classmethod
    def IS_CHANGED(cls, image):
        return _content_hash(_input_path(image))

    @classmethod
    def VALIDATE_INPUTS(cls, image):
        try:
            _input_path(image)
        except ValueError as error:
            return str(error)
        return True
