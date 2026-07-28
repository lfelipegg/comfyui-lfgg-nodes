from .dimensions_by_aspect_ratio import _max_resolution
from .sizing import _bounded_int, fit_source_dimensions

UPSCALE_METHODS = ("lanczos", "nearest-exact", "bilinear", "area", "bicubic")
MAX_RESIZE_PIXELS = 16_384**2


def _image_dimensions(image):
    from torch import Tensor

    if not isinstance(image, Tensor) or image.ndim != 4 or any(
        dimension < 1 for dimension in image.shape
    ):
        raise ValueError(
            "IMAGE must be a Torch tensor shaped [B,H,W,C] with positive dimensions"
        )
    return image.shape[2], image.shape[1]


def _divisible_by_input(max_resolution):
    return (
        "INT",
        {
            "default": 8,
            "min": 1,
            "max": max_resolution,
            "tooltip": "Aligns both output dimensions to this exact multiple.",
        },
    )


def _validate_resize_image(image):
    width, height = _image_dimensions(image)
    if image.shape[3] not in {1, 3, 4}:
        raise ValueError(
            "IMAGE must be shaped [B,H,W,C] with C equal to 1, 3, or 4"
        )
    if image.shape[0] * height * width > MAX_RESIZE_PIXELS:
        raise ValueError(
            f"IMAGE batch must contain at most {MAX_RESIZE_PIXELS} pixels"
        )
    if not image.is_floating_point():
        raise ValueError("IMAGE values must have a floating-point dtype")

    from torch import isfinite

    if not isfinite(image).all().item():
        raise ValueError("IMAGE values must all be finite")
    return width, height


class ImageDimensionsByLongSide:
    DESCRIPTION = (
        "Calculates aligned dimensions from an image without upscaling or "
        "exceeding the selected long-side limit."
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
                            "Image batch whose shared spatial shape is inspected."
                        )
                    },
                ),
                "long_side": (
                    "INT",
                    {
                        "default": 1024,
                        "min": 16,
                        "max": max_resolution,
                        "step": 8,
                        "tooltip": (
                            "Maximum size in pixels for the longer output axis."
                        ),
                    },
                ),
                "divisible_by": _divisible_by_input(max_resolution),
            }
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    OUTPUT_TOOLTIPS = (
        "Aligned target width in pixels.",
        "Aligned target height in pixels.",
    )
    FUNCTION = "calculate"
    CATEGORY = "LFGG/sizing"

    def calculate(self, image, long_side, divisible_by):
        max_resolution = _max_resolution()
        _bounded_int("long_side", long_side, 16, max_resolution)
        source_width, source_height = _image_dimensions(image)
        source_long = max(source_width, source_height)
        target_long = min(source_long, long_side)
        max_width = source_width * target_long // source_long
        max_height = source_height * target_long // source_long
        if max_width < 1 or max_height < 1:
            raise ValueError(
                "No positive aligned dimensions satisfy long_side; increase long_side"
            )

        return fit_source_dimensions(
            source_width=source_width,
            source_height=source_height,
            max_width=max_width,
            max_height=max_height,
            max_pixels=None,
            divisible_by=divisible_by,
            max_resolution=max_resolution,
        )


class ResizeImageByLongSide(ImageDimensionsByLongSide):
    DESCRIPTION = (
        "Resizes an image to aligned dimensions without upscaling or exceeding "
        "the selected long-side limit."
    )

    @classmethod
    def INPUT_TYPES(cls):
        sizing_inputs = super().INPUT_TYPES()["required"]
        return {
            "required": {
                "image": (
                    "IMAGE",
                    {"tooltip": "Image batch to resize."},
                ),
                "upscale_method": (
                    list(UPSCALE_METHODS),
                    {
                        "tooltip": (
                            "Interpolation method used when resizing the image."
                        )
                    },
                ),
                "long_side": sizing_inputs["long_side"],
                "divisible_by": sizing_inputs["divisible_by"],
            }
        }

    RETURN_TYPES = ("IMAGE", "INT", "INT")
    RETURN_NAMES = ("image", "width", "height")
    OUTPUT_TOOLTIPS = (
        "Image resized to the aligned dimensions.",
        "Aligned output width in pixels.",
        "Aligned output height in pixels.",
    )
    FUNCTION = "resize"
    CATEGORY = "LFGG/image"

    def resize(self, image, long_side, divisible_by, upscale_method):
        if upscale_method not in UPSCALE_METHODS:
            raise ValueError(
                f"upscale_method must be one of: {', '.join(UPSCALE_METHODS)}"
            )
        source_dimensions = _validate_resize_image(image)
        width, height = self.calculate(image, long_side, divisible_by)
        if (width, height) == source_dimensions:
            return image, width, height

        from comfy.utils import common_upscale

        resized = common_upscale(
            image.movedim(-1, 1),
            width,
            height,
            upscale_method,
            "disabled",
        )
        if image.shape[3] == 1 and resized.ndim == 3:
            resized = resized.unsqueeze(1)
        return resized.movedim(1, -1), width, height


class ImageDimensionsByPixelBudget:
    DESCRIPTION = (
        "Calculates aligned dimensions from an image without upscaling or "
        "exceeding the selected pixel budget."
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
                            "Image batch whose shared spatial shape is inspected."
                        )
                    },
                ),
                "max_pixels": (
                    "INT",
                    {
                        "default": 1_048_576,
                        "min": 1,
                        "max": max_resolution**2,
                        "step": 1024,
                        "tooltip": (
                            "Maximum total pixel count for the output dimensions."
                        ),
                    },
                ),
                "divisible_by": _divisible_by_input(max_resolution),
            }
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    OUTPUT_TOOLTIPS = (
        "Aligned target width in pixels.",
        "Aligned target height in pixels.",
    )
    FUNCTION = "calculate"
    CATEGORY = "LFGG/sizing"

    def calculate(self, image, max_pixels, divisible_by):
        max_resolution = _max_resolution()
        source_width, source_height = _image_dimensions(image)
        return fit_source_dimensions(
            source_width=source_width,
            source_height=source_height,
            max_width=min(source_width, max_resolution),
            max_height=min(source_height, max_resolution),
            max_pixels=max_pixels,
            divisible_by=divisible_by,
            max_resolution=max_resolution,
        )
