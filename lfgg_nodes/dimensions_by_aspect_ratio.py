from .sizing import ASPECT_RATIOS, fit_aspect_ratio_dimensions


def _max_resolution():
    from nodes import MAX_RESOLUTION

    return MAX_RESOLUTION


class DimensionsByAspectRatio:
    @classmethod
    def INPUT_TYPES(cls):
        max_resolution = _max_resolution()
        return {
            "required": {
                "aspect_ratio": ("COMBO", {"options": list(ASPECT_RATIOS)}),
                "long_side": (
                    "INT",
                    {
                        "default": 1024,
                        "min": 16,
                        "max": max_resolution,
                        "step": 8,
                    },
                ),
                "divisible_by": (
                    "INT",
                    {"default": 8, "min": 1, "max": max_resolution},
                ),
                "custom_ratio_width": (
                    "INT",
                    {"default": 1, "min": 1, "max": max_resolution},
                ),
                "custom_ratio_height": (
                    "INT",
                    {"default": 1, "min": 1, "max": max_resolution},
                ),
            }
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    FUNCTION = "calculate"
    CATEGORY = "LFGG/sizing"

    def calculate(
        self,
        aspect_ratio,
        long_side,
        divisible_by,
        custom_ratio_width,
        custom_ratio_height,
    ):
        max_resolution = _max_resolution()
        return fit_aspect_ratio_dimensions(
            aspect_ratio=aspect_ratio,
            long_side=long_side,
            divisible_by=divisible_by,
            custom_ratio_width=custom_ratio_width,
            custom_ratio_height=custom_ratio_height,
            max_resolution=max_resolution,
        )
