from .dimensions_by_aspect_ratio import DimensionsByAspectRatio, _max_resolution
from .image_dimensions import _divisible_by_input, _image_dimensions
from .sizing import (
    ASPECT_RATIOS,
    PIXELS_PER_MEGAPIXEL,
    PRESET_RATIOS,
    _bounded_int,
    fit_megapixel_dimensions,
)


def _megapixels_input(max_resolution):
    return (
        "FLOAT",
        {
            "default": 1.0,
            "min": 1 / PIXELS_PER_MEGAPIXEL,
            "max": max_resolution**2 / PIXELS_PER_MEGAPIXEL,
            "step": 0.05,
            "tooltip": (
                "Hard area ceiling: 1 megapixel = 1,048,576 pixels (1024×1024), "
                "not decimal megapixels. Scales proportionally to the budget, "
                "then rounds each axis down to divisible_by."
            ),
        },
    )


class DimensionsByRatioAndMegapixels(DimensionsByAspectRatio):
    DESCRIPTION = (
        "Calculates aligned width and height from a preset or custom ratio under "
        "a hard megapixel budget. One megapixel means 1,048,576 pixels."
    )

    @classmethod
    def INPUT_TYPES(cls):
        inputs = super().INPUT_TYPES()["required"]
        return {
            "required": {
                ("megapixels" if name == "long_side" else name): (
                    _megapixels_input(_max_resolution())
                    if name == "long_side"
                    else definition
                )
                for name, definition in inputs.items()
            }
        }

    def calculate(
        self,
        aspect_ratio,
        megapixels,
        divisible_by,
        custom_ratio_width,
        custom_ratio_height,
    ):
        max_resolution = _max_resolution()
        _bounded_int("custom_ratio_width", custom_ratio_width, 1, max_resolution)
        _bounded_int("custom_ratio_height", custom_ratio_height, 1, max_resolution)
        if aspect_ratio not in ASPECT_RATIOS:
            raise ValueError(f"aspect_ratio must be one of: {', '.join(ASPECT_RATIOS)}")
        width, height = (
            (custom_ratio_width, custom_ratio_height)
            if aspect_ratio == "Custom"
            else PRESET_RATIOS[aspect_ratio]
        )
        return fit_megapixel_dimensions(
            ratio_width=width,
            ratio_height=height,
            megapixels=megapixels,
            divisible_by=divisible_by,
            max_resolution=max_resolution,
        )


class ImageDimensionsByMegapixels:
    DESCRIPTION = (
        "Calculates aligned width and height from an image's ratio under a hard "
        "megapixel budget. Dimensions may exceed the source size; no image is "
        "resized. One megapixel means 1,048,576 pixels."
    )

    @classmethod
    def INPUT_TYPES(cls):
        max_resolution = _max_resolution()
        return {
            "required": {
                "image": (
                    "IMAGE",
                    {
                        "tooltip": (
                            "Image batch used only for its shared "
                            "width-to-height ratio."
                        ),
                    },
                ),
                "megapixels": _megapixels_input(max_resolution),
                "divisible_by": _divisible_by_input(max_resolution),
            }
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    OUTPUT_TOOLTIPS = (
        "Aligned target width in pixels; may exceed source width.",
        "Aligned target height in pixels; may exceed source height.",
    )
    FUNCTION = "calculate"
    CATEGORY = "LFGG/sizing"

    def calculate(self, image, megapixels, divisible_by):
        width, height = _image_dimensions(image)
        return fit_megapixel_dimensions(
            ratio_width=width,
            ratio_height=height,
            megapixels=megapixels,
            divisible_by=divisible_by,
            max_resolution=_max_resolution(),
        )
