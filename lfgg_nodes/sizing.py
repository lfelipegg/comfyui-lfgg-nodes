PRESET_RATIOS = {
    "1:1": (1, 1),
    "4:5": (4, 5),
    "5:4": (5, 4),
    "3:4": (3, 4),
    "4:3": (4, 3),
    "2:3": (2, 3),
    "3:2": (3, 2),
    "5:7": (5, 7),
    "7:5": (7, 5),
    "9:16": (9, 16),
    "16:9": (16, 9),
    "9:21": (9, 21),
    "21:9": (21, 9),
}
ASPECT_RATIOS = (*PRESET_RATIOS, "Custom")


def _bounded_int(name, value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(
            f"{name} must be an integer between {minimum} and {maximum}"
        )


def _is_better(candidate, best):
    high, low, area, long_units, short_units = candidate[:5]
    best_high, best_low, best_area, best_long, best_short = best[:5]

    error_order = high * best_low - best_high * low
    if error_order != 0:
        return error_order < 0
    return (area, long_units, short_units) > (best_area, best_long, best_short)


def _fit_aligned_dimensions(
    *,
    ratio_width,
    ratio_height,
    max_width,
    max_height,
    max_pixels,
    divisible_by,
):
    max_width_units = max_width // divisible_by
    max_height_units = max_height // divisible_by
    unit_pixels = divisible_by * divisible_by
    best = None

    # ponytail: bounded by MAX_RESOLUTION; use continued fractions if that cap grows.
    for width_units in range(1, max_width_units + 1):
        height_limit = max_height_units
        if max_pixels is not None:
            height_limit = min(
                height_limit,
                max_pixels // (width_units * unit_pixels),
            )
        if height_limit < 1:
            continue

        scaled_height = ratio_height * width_units
        lower_height = scaled_height // ratio_width
        height_candidates = {
            max(1, min(height_limit, lower_height)),
            max(1, min(height_limit, lower_height + 1)),
        }
        for height_units in height_candidates:
            candidate_side = width_units * ratio_height
            target_side = height_units * ratio_width
            candidate = (
                max(candidate_side, target_side),
                min(candidate_side, target_side),
                width_units * height_units,
                max(width_units, height_units),
                min(width_units, height_units),
                width_units,
                height_units,
            )
            if best is None or _is_better(candidate, best):
                best = candidate

    if best is None:
        raise ValueError(
            "No positive aligned dimensions satisfy the limits; "
            "reduce divisible_by or increase the limit"
        )
    return best[-2] * divisible_by, best[-1] * divisible_by


def fit_source_dimensions(
    *,
    source_width,
    source_height,
    max_width,
    max_height,
    max_pixels,
    divisible_by,
    max_resolution,
):
    """Fit an aligned source aspect beneath independent hard ceilings."""
    if type(source_width) is not int or source_width < 1:
        raise ValueError("source_width must be a positive integer")
    if type(source_height) is not int or source_height < 1:
        raise ValueError("source_height must be a positive integer")
    _bounded_int("max_width", max_width, 1, max_resolution)
    _bounded_int("max_height", max_height, 1, max_resolution)
    _bounded_int("divisible_by", divisible_by, 1, max_resolution)
    if max_pixels is not None:
        _bounded_int("max_pixels", max_pixels, 1, max_resolution**2)

    return _fit_aligned_dimensions(
        ratio_width=source_width,
        ratio_height=source_height,
        max_width=min(source_width, max_width),
        max_height=min(source_height, max_height),
        max_pixels=max_pixels,
        divisible_by=divisible_by,
    )


def fit_aspect_ratio_dimensions(
    *,
    aspect_ratio,
    long_side,
    divisible_by,
    custom_ratio_width,
    custom_ratio_height,
    max_resolution,
):
    """Fit an aligned ratio beneath hard axis ceilings.

    Aspect error is the larger of candidate/target and target/candidate.
    Ties prefer pixel area, then the long-axis units, then short-axis units.
    """
    _bounded_int("long_side", long_side, 16, max_resolution)
    _bounded_int("divisible_by", divisible_by, 1, max_resolution)
    _bounded_int("custom_ratio_width", custom_ratio_width, 1, max_resolution)
    _bounded_int("custom_ratio_height", custom_ratio_height, 1, max_resolution)

    if aspect_ratio not in ASPECT_RATIOS:
        raise ValueError(
            f"aspect_ratio must be one of: {', '.join(ASPECT_RATIOS)}"
        )

    ratio_width, ratio_height = (
        (custom_ratio_width, custom_ratio_height)
        if aspect_ratio == "Custom"
        else PRESET_RATIOS[aspect_ratio]
    )
    return _fit_aligned_dimensions(
        ratio_width=ratio_width,
        ratio_height=ratio_height,
        max_width=long_side,
        max_height=long_side,
        max_pixels=None,
        divisible_by=divisible_by,
    )
