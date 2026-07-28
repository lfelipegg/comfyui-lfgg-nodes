from math import gcd

from .sizing import _bounded_int


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
