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
    high, low, area, long_units, short_units = candidate
    best_high, best_low, best_area, best_long, best_short = best

    error_order = high * best_low - best_high * low
    if error_order != 0:
        return error_order < 0
    return (area, long_units, short_units) > (best_area, best_long, best_short)


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
    max_units = long_side // divisible_by
    if max_units < 1:
        raise ValueError(
            "No positive aligned dimensions fit within long_side; "
            "reduce divisible_by or increase long_side"
        )

    width_is_long = ratio_width >= ratio_height
    target_long = max(ratio_width, ratio_height)
    target_short = min(ratio_width, ratio_height)
    best = None

    # ponytail: bounded by MAX_RESOLUTION; use continued fractions if that cap grows.
    for long_units in range(1, max_units + 1):
        scaled_short = target_short * long_units
        lower_short = scaled_short // target_long
        for short_units in (lower_short, lower_short + 1):
            if not 1 <= short_units <= max_units:
                continue
            candidate_side = short_units * target_long
            target_side = long_units * target_short
            candidate = (
                max(candidate_side, target_side),
                min(candidate_side, target_side),
                long_units * short_units,
                long_units,
                short_units,
            )
            if best is None or _is_better(candidate, best):
                best = candidate

    _, _, _, fitted_long, fitted_short = best
    if width_is_long:
        return fitted_long * divisible_by, fitted_short * divisible_by
    return fitted_short * divisible_by, fitted_long * divisible_by
