from .composition import FAMILIES, MAX_BATCH_PIXELS, MAX_SEED, PALETTES
from .dimensions_by_aspect_ratio import DimensionsByAspectRatio


class CompositionImageByAspectRatio:
    DESCRIPTION = (
        "Generates seeded abstract RGB compositions at an aligned aspect ratio. "
        "Connect IMAGE to native Preview Image or VAE Encode. The composition "
        "seed is independent of the sampler seed; total batch limit is "
        "16,777,216 pixels."
    )

    @classmethod
    def INPUT_TYPES(cls):
        inputs = DimensionsByAspectRatio.INPUT_TYPES()
        inputs["required"].update(
            {
                "family": (
                    "COMBO",
                    {
                        "options": ["Random", *FAMILIES],
                        "default": "Random",
                        "tooltip": (
                            "Spatial organizing principle; Random chooses per image."
                        ),
                    },
                ),
                "palette": (
                    "COMBO",
                    {
                        "options": [*PALETTES, "Random"],
                        "default": "Monochrome",
                        "tooltip": (
                            "Coordinated colors; Random chooses per image. Monochrome "
                            "uses black and white except at smoothed boundaries."
                        ),
                    },
                ),
                "complexity": (
                    "FLOAT",
                    {
                        "default": 0.5,
                        "min": 0.0,
                        "max": 1.0,
                        "step": 0.01,
                        "tooltip": (
                            "Low to high detail within the selected family: changes "
                            "count, size, spacing and overlap, not an exact "
                            "shape count."
                        ),
                    },
                ),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": MAX_SEED,
                        "control_after_generate": True,
                        "tooltip": "Composition seed, independent of the sampler seed. "
                        "Increasing batch size preserves earlier images.",
                    },
                ),
                "batch_size": (
                    "INT",
                    {
                        "default": 1,
                        "min": 1,
                        "max": MAX_BATCH_PIXELS,
                        "tooltip": "Independent compositions. Aligned width × height × "
                        "batch size must not exceed 16,777,216 pixels.",
                    },
                ),
            }
        )
        return inputs

    RETURN_TYPES = ("IMAGE", "INT", "INT")
    RETURN_NAMES = ("image", "width", "height")
    OUTPUT_TOOLTIPS = (
        "Seeded RGB image batch; inspect using native Preview Image.",
        "Aligned output width in pixels.",
        "Aligned output height in pixels.",
    )
    FUNCTION = "generate"
    CATEGORY = "LFGG/image"

    def generate(
        self,
        aspect_ratio,
        long_side,
        divisible_by,
        custom_ratio_width,
        custom_ratio_height,
        family="Random",
        palette="Monochrome",
        complexity=0.5,
        seed=0,
        batch_size=1,
    ):
        from .composition import generate_composition_batch

        width, height = DimensionsByAspectRatio().calculate(
            aspect_ratio,
            long_side,
            divisible_by,
            custom_ratio_width,
            custom_ratio_height,
        )
        images = generate_composition_batch(
            width=width,
            height=height,
            family=family,
            palette=palette,
            complexity=complexity,
            seed=seed,
            batch_size=batch_size,
        )
        return images, width, height
