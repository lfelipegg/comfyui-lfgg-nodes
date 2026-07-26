from .sizing import ASPECT_RATIOS, fit_aspect_ratio_dimensions


def _max_resolution():
    from nodes import MAX_RESOLUTION

    return MAX_RESOLUTION


class DimensionsByAspectRatio:
    DESCRIPTION = (
        "Calculates aligned width and height for a preset or custom aspect ratio "
        "without exceeding the selected long-side limit."
    )

    @classmethod
    def INPUT_TYPES(cls):
        max_resolution = _max_resolution()
        return {
            "required": {
                "aspect_ratio": (
                    "COMBO",
                    {
                        "options": list(ASPECT_RATIOS),
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
                        "max": max_resolution,
                        "step": 8,
                        "tooltip": (
                            "Maximum size in pixels for the longer output axis."
                        ),
                    },
                ),
                "divisible_by": (
                    "INT",
                    {
                        "default": 8,
                        "min": 1,
                        "max": max_resolution,
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
                        "max": max_resolution,
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
                        "max": max_resolution,
                        "tooltip": (
                            "Height component used only when aspect_ratio is Custom."
                        ),
                    },
                ),
            }
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    OUTPUT_TOOLTIPS = (
        "Aligned output width in pixels.",
        "Aligned output height in pixels.",
    )
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
