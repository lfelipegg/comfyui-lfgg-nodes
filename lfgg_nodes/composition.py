"""Deterministic abstract composition rendering with bounded working memory.

The returned float32 tensor is the only full-resolution RGB allocation. Images
are rendered sequentially into that tensor in tiles. Antialiasing uses a fixed
512-pixel tile, a three-times supersampled tile, and a three-pixel gutter, so its
Pillow/NumPy/Torch scratch buffers are bounded independently of the requested
canvas dimensions. Scene descriptions are also bounded (at most a few hundred
small Python tuples); no full-canvas supersampled or floating-point work image
is created.
"""

import random
from math import cos, hypot, isfinite, pi, sin

FAMILIES = (
    "Scattered clusters",
    "Regular or jittered grids",
    "Directional bands or diagonal arrangements",
    "Concentric or radial arrangements",
    "Large area partitions",
    "Gradient fields with optional shapes",
)
PALETTES = ("Monochrome", "Grayscale", "Muted color", "Vivid color")
MAX_BATCH_PIXELS = 16_777_216
MAX_SEED = 2**64 - 1

__all__ = (
    "FAMILIES",
    "PALETTES",
    "MAX_BATCH_PIXELS",
    "MAX_SEED",
    "generate_composition_batch",
)

_RANDOM = "Random"
_TILE_SIZE = 512
_SUPERSAMPLE = 3
_GUTTER = 3  # Lanczos has a three-output-pixel support radius.
_MASK_64 = 2**64 - 1
_SHAPES = ("rectangle", "square", "diamond", "circle", "triangle")

# Each row is a deliberately coordinated set, ordered from a useful background
# tone toward accents. Rendering samples one row per image, never free RGB.
_PALETTE_SETS = {
    "Monochrome": (
        ((255, 255, 255), (0, 0, 0)),
        ((0, 0, 0), (255, 255, 255)),
    ),
    "Grayscale": (
        ((244, 244, 244), (191, 191, 191), (104, 104, 104), (29, 29, 29)),
        ((23, 23, 23), (78, 78, 78), (157, 157, 157), (231, 231, 231)),
        ((238, 238, 238), (176, 176, 176), (110, 110, 110), (48, 48, 48)),
    ),
    "Muted color": (
        ((224, 216, 197), (172, 111, 94), (91, 121, 116), (66, 72, 88)),
        ((218, 221, 207), (127, 148, 126), (177, 133, 107), (78, 91, 112)),
        ((229, 213, 207), (166, 116, 131), (100, 126, 141), (72, 76, 91)),
        ((216, 207, 181), (155, 141, 91), (83, 120, 119), (78, 77, 97)),
    ),
    "Vivid color": (
        ((250, 238, 56), (239, 51, 64), (31, 113, 226), (18, 24, 38)),
        ((255, 79, 15), (255, 203, 5), (0, 166, 166), (23, 43, 77)),
        ((247, 44, 127), (105, 45, 216), (0, 195, 208), (252, 231, 51)),
        ((33, 214, 124), (20, 91, 214), (247, 54, 75), (255, 180, 18)),
    ),
}


def _mix64(value):
    value = (value + 0x9E3779B97F4A7C15) & _MASK_64
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & _MASK_64
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & _MASK_64
    return value ^ (value >> 31)


def _error(message):
    raise ValueError(f"LFGG Composition Image {message}")


def _validate(width, height, family, palette, complexity, seed, batch_size):
    for name, value in (("width", width), ("height", height)):
        if type(value) is not int or value < 1:
            _error(f"{name} must be a positive integer")
    if not isinstance(family, str) or family not in (*FAMILIES, _RANDOM):
        _error(f"family must be one of: {', '.join((*FAMILIES, _RANDOM))}")
    if not isinstance(palette, str) or palette not in (*PALETTES, _RANDOM):
        _error(f"palette must be one of: {', '.join((*PALETTES, _RANDOM))}")
    if (
        type(complexity) not in (int, float)
        or not 0 <= complexity <= 1
        or not isfinite(complexity)
    ):
        _error("complexity must be a finite number between 0 and 1")
    complexity = float(complexity)
    if type(seed) is not int or not 0 <= seed <= MAX_SEED:
        _error(f"seed must be an integer between 0 and {MAX_SEED}")
    if type(batch_size) is not int or batch_size < 1:
        _error("batch_size must be a positive integer")
    total_pixels = width * height * batch_size
    if total_pixels > MAX_BATCH_PIXELS:
        _error(
            f"requested batch contains {total_pixels} pixels; reduce dimensions "
            f"or batch_size to at most {MAX_BATCH_PIXELS} pixels"
        )
    return complexity


def _pick_color(rng, colors, *, avoid=None):
    choices = (
        colors if avoid is None else tuple(color for color in colors if color != avoid)
    )
    return choices[rng.randrange(len(choices))]


def _polygon_for_shape(kind, cx, cy, size, aspect, angle=0.0):
    if kind == "triangle":
        points = ((0.0, -size), (-size * aspect, size), (size * aspect, size))
    elif kind == "diamond":
        points = (
            (0.0, -size),
            (size * aspect, 0.0),
            (0.0, size),
            (-size * aspect, 0.0),
        )
    else:
        half_width = size * (1.0 if kind == "square" else aspect)
        points = (
            (-half_width, -size),
            (half_width, -size),
            (half_width, size),
            (-half_width, size),
        )
    cosine, sine = cos(angle), sin(angle)
    return tuple(
        (cx + x * cosine - y * sine, cy + x * sine + y * cosine) for x, y in points
    )


def _add_shape(commands, kind, cx, cy, size, color, rng, *, angle=None, aspect=None):
    size = max(0.65, size)
    if kind == "circle":
        commands.append(
            ("ellipse", (cx - size, cy - size, cx + size, cy + size), color)
        )
        return
    if aspect is None:
        aspect = 1.0 if kind in {"square", "diamond"} else rng.uniform(0.55, 1.8)
    if angle is None:
        angle = rng.uniform(-pi, pi)
    commands.append(
        ("polygon", _polygon_for_shape(kind, cx, cy, size, aspect, angle), color)
    )


def _scattered(width, height, complexity, colors, rng):
    background = colors[0]
    commands = []
    short = min(width, height)
    cluster_count = 2 + round(complexity * 5)
    shape_count = 12 + round(complexity * 58)
    clusters = [
        (
            rng.uniform(-0.06 * width, 1.06 * width),
            rng.uniform(-0.06 * height, 1.06 * height),
            rng.uniform(0.08, 0.24) * short,
        )
        for _ in range(cluster_count)
    ]
    kinds = list(_SHAPES)
    rng.shuffle(kinds)
    for index in range(shape_count):
        center_x, center_y, spread = clusters[rng.randrange(cluster_count)]
        cx = rng.gauss(center_x, spread)
        cy = rng.gauss(center_y, spread)
        typical = short * (0.085 - 0.045 * complexity)
        size = typical * rng.uniform(0.45, 1.75)
        _add_shape(
            commands,
            kinds[index % len(kinds)],
            cx,
            cy,
            size,
            _pick_color(rng, colors, avoid=background),
            rng,
        )
    return background, commands, None


def _grid(width, height, complexity, colors, rng):
    background = colors[0]
    commands = []
    short = min(width, height)
    target_cells = 9 + round(complexity * 135)
    columns = max(1, min(target_cells, round((target_cells * width / height) ** 0.5)))
    rows = max(1, (target_cells + columns - 1) // columns)
    cell_width, cell_height = width / columns, height / rows
    jitter = min(cell_width, cell_height) * (0.03 + complexity * 0.20)
    kinds = list(_SHAPES)
    rng.shuffle(kinds)
    for row in range(rows):
        for column in range(columns):
            if rng.random() < 0.12 * (1.0 - complexity):
                continue
            cx = (column + 0.5) * cell_width + rng.uniform(-jitter, jitter)
            cy = (row + 0.5) * cell_height + rng.uniform(-jitter, jitter)
            size = min(cell_width, cell_height) * rng.uniform(
                0.25, 0.48 + 0.12 * complexity
            )
            kind = kinds[(row * columns + column) % len(kinds)]
            _add_shape(
                commands,
                kind,
                cx,
                cy,
                size,
                _pick_color(rng, colors, avoid=background),
                rng,
                angle=rng.uniform(-0.18, 0.18) if complexity < 0.55 else None,
            )
    # The direct rectangular layout above uses each axis independently; short is
    # retained only as the isotropic scale source for the optional accent.
    if complexity > 0.72:
        _add_shape(
            commands,
            "diamond",
            width / 2,
            height / 2,
            short * 0.07,
            _pick_color(rng, colors, avoid=background),
            rng,
            angle=0.0,
        )
    return background, commands, None


def _directional(width, height, complexity, colors, rng):
    background = colors[0]
    commands = []
    short = min(width, height)
    angle = rng.choice((-1, 1)) * rng.uniform(0.25, 1.10)
    dx, dy = cos(angle), sin(angle)
    nx, ny = -dy, dx
    extent = hypot(width, height) * 1.4
    band_count = 3 + round(complexity * 9)
    spacing = (abs(nx) * width + abs(ny) * height) / max(1, band_count - 1)
    band_width = spacing * rng.uniform(0.28, 0.68 + 0.18 * complexity)
    for index in range(band_count):
        offset = (index - (band_count - 1) / 2) * spacing
        cx = width / 2 + nx * offset
        cy = height / 2 + ny * offset
        polygon = (
            (
                cx - dx * extent - nx * band_width / 2,
                cy - dy * extent - ny * band_width / 2,
            ),
            (
                cx + dx * extent - nx * band_width / 2,
                cy + dy * extent - ny * band_width / 2,
            ),
            (
                cx + dx * extent + nx * band_width / 2,
                cy + dy * extent + ny * band_width / 2,
            ),
            (
                cx - dx * extent + nx * band_width / 2,
                cy - dy * extent + ny * band_width / 2,
            ),
        )
        commands.append(("polygon", polygon, colors[(index + 1) % len(colors)]))
    accent_count = 3 + round(complexity * 16)
    for index in range(accent_count):
        along = rng.uniform(-extent * 0.45, extent * 0.45)
        across = rng.uniform(-spacing * 0.42, spacing * 0.42)
        lane = rng.randrange(band_count) - (band_count - 1) / 2
        cx = width / 2 + dx * along + nx * (lane * spacing + across)
        cy = height / 2 + dy * along + ny * (lane * spacing + across)
        _add_shape(
            commands,
            _SHAPES[index % len(_SHAPES)],
            cx,
            cy,
            short * rng.uniform(0.025, 0.075),
            colors[(index + 2) % len(colors)],
            rng,
            angle=angle,
        )
    return background, commands, None


def _concentric(width, height, complexity, colors, rng):
    background = colors[0]
    commands = []
    short = min(width, height)
    cx = width * rng.uniform(0.36, 0.64)
    cy = height * rng.uniform(0.36, 0.64)
    ring_count = 4 + round(complexity * 10)
    outer = short * rng.uniform(0.42, 0.72)
    kind = rng.choice(("circle", "diamond", "square"))
    for index in range(ring_count, 0, -1):
        size = outer * index / ring_count
        _add_shape(
            commands,
            kind,
            cx,
            cy,
            size,
            colors[(ring_count - index + 1) % len(colors)],
            rng,
            angle=0.0 if kind == "diamond" else rng.uniform(-0.12, 0.12),
        )
    spoke_count = 3 + round(complexity * 9)
    satellite_kind = rng.choice(("circle", "triangle", "diamond", "rectangle"))
    for index in range(spoke_count):
        theta = 2 * pi * index / spoke_count + rng.uniform(-0.08, 0.08)
        radius = outer * rng.uniform(0.72, 1.22)
        _add_shape(
            commands,
            satellite_kind if index % 2 else _SHAPES[index % len(_SHAPES)],
            cx + cos(theta) * radius,
            cy + sin(theta) * radius,
            short * rng.uniform(0.025, 0.07),
            colors[(index + 2) % len(colors)],
            rng,
            angle=theta,
        )
    return background, commands, None


def _partitions(width, height, complexity, colors, rng):
    background = colors[0]
    regions = [(0.0, 0.0, float(width), float(height), 0)]
    target = 4 + round(complexity * 15)
    while len(regions) < target:
        candidates = [
            (index, (right - left) * (bottom - top))
            for index, (left, top, right, bottom, _depth) in enumerate(regions)
            if right - left >= 4 and bottom - top >= 4
        ]
        if not candidates:
            break
        index = max(candidates, key=lambda item: item[1] * rng.uniform(0.75, 1.25))[0]
        left, top, right, bottom, depth = regions.pop(index)
        split_vertical = (right - left) / (bottom - top) > rng.uniform(0.75, 1.35)
        fraction = rng.uniform(0.30, 0.70)
        if split_vertical:
            middle = left + (right - left) * fraction
            regions.extend(
                (
                    (left, top, middle, bottom, depth + 1),
                    (middle, top, right, bottom, depth + 1),
                )
            )
        else:
            middle = top + (bottom - top) * fraction
            regions.extend(
                (
                    (left, top, right, middle, depth + 1),
                    (left, middle, right, bottom, depth + 1),
                )
            )
    commands = []
    for index, (left, top, right, bottom, depth) in enumerate(regions):
        color = colors[(index + depth + 1) % len(colors)]
        commands.append(("rectangle", (left, top, right, bottom), color))
        if complexity > 0.62 and index % 3 == 0:
            size = min(right - left, bottom - top) * rng.uniform(0.12, 0.28)
            _add_shape(
                commands,
                _SHAPES[index % len(_SHAPES)],
                (left + right) / 2,
                (top + bottom) / 2,
                size,
                colors[(index + 2) % len(colors)],
                rng,
            )
    return background, commands, None


def _gradient(width, height, complexity, colors, rng, palette_name):
    commands = []
    short = min(width, height)
    field = {
        "angle": rng.uniform(-pi, pi),
        "phase": rng.uniform(-pi, pi),
        "waves": 0 if complexity < 0.28 else 1 + round(complexity * 3),
        "radial": rng.random() < 0.35,
        "center": (rng.uniform(0.25, 0.75), rng.uniform(0.25, 0.75)),
        "monochrome": palette_name == "Monochrome",
        "colors": colors,
    }
    shape_count = round(complexity * 18)
    for index in range(shape_count):
        size = short * rng.uniform(0.025, 0.12 - 0.035 * complexity)
        _add_shape(
            commands,
            _SHAPES[index % len(_SHAPES)],
            rng.uniform(-0.05 * width, 1.05 * width),
            rng.uniform(-0.05 * height, 1.05 * height),
            size,
            colors[(index + 1) % len(colors)],
            rng,
        )
    return colors[0], commands, field


_BUILDERS = {
    FAMILIES[0]: _scattered,
    FAMILIES[1]: _grid,
    FAMILIES[2]: _directional,
    FAMILIES[3]: _concentric,
    FAMILIES[4]: _partitions,
}


def _build_scene(width, height, family, palette, complexity, rng):
    colors = rng.choice(_PALETTE_SETS[palette])
    if family == FAMILIES[5]:
        return _gradient(width, height, complexity, colors, rng, palette)
    return _BUILDERS[family](width, height, complexity, colors, rng)


def _field_image(field, left, top, right, bottom, width, height, np, Image):
    scale = _SUPERSAMPLE
    pixel_width = (right - left) * scale
    pixel_height = (bottom - top) * scale
    xs = (left + (np.arange(pixel_width, dtype=np.float32) + 0.5) / scale) / width
    ys = (top + (np.arange(pixel_height, dtype=np.float32) + 0.5) / scale) / height
    xx = xs[None, :] - field["center"][0]
    yy = ys[:, None] - field["center"][1]
    if field["radial"]:
        # Normalize each axis before radius calculation, retaining circles in
        # pixel space rather than stretching them with canvas aspect ratio.
        radius_scale = max(width, height) / min(width, height)
        if width > height:
            values = np.sqrt((xx * radius_scale) ** 2 + yy**2)
        else:
            values = np.sqrt(xx**2 + (yy * radius_scale) ** 2)
        values = np.clip(values * 1.7, 0.0, 1.0)
    else:
        cosine, sine = cos(field["angle"]), sin(field["angle"])
        span = abs(cosine) + abs(sine)
        values = np.clip(0.5 + (xx * cosine + yy * sine) / span, 0.0, 1.0)
    if field["waves"]:
        values = np.clip(
            values + 0.08 * np.sin(values * field["waves"] * 2 * pi + field["phase"]),
            0.0,
            1.0,
        )
    colors = np.asarray(field["colors"], dtype=np.float32)
    if field["monochrome"]:
        indexes = (values >= 0.5).astype(np.uint8)
        rgb = colors[indexes].astype(np.uint8, copy=False)
    else:
        position = values * (len(colors) - 1)
        lower = np.floor(position).astype(np.int16)
        upper = np.minimum(lower + 1, len(colors) - 1)
        fraction = (position - lower)[..., None]
        rgb = np.rint(
            colors[lower] * (1.0 - fraction) + colors[upper] * fraction
        ).astype(np.uint8)
    return Image.fromarray(rgb, "RGB")


def _draw_tile(scene, box, width, height, np, Image, ImageDraw):
    background, commands, field = scene
    left, top, right, bottom = box
    if field is None:
        image = Image.new(
            "RGB",
            ((right - left) * _SUPERSAMPLE, (bottom - top) * _SUPERSAMPLE),
            background,
        )
    else:
        image = _field_image(field, left, top, right, bottom, width, height, np, Image)
    draw = ImageDraw.Draw(image)

    def point(value, origin):
        return int(round((value - origin) * _SUPERSAMPLE))

    for kind, geometry, color in commands:
        if kind == "polygon":
            draw.polygon(
                [(point(x, left), point(y, top)) for x, y in geometry],
                fill=color,
            )
        else:
            x0, y0, x1, y1 = geometry
            coordinates = (
                point(x0, left),
                point(y0, top),
                point(x1, left),
                point(y1, top),
            )
            if kind == "ellipse":
                draw.ellipse(coordinates, fill=color)
            else:
                draw.rectangle(coordinates, fill=color)
    logical_size = (right - left, bottom - top)
    return image.resize(logical_size, Image.Resampling.LANCZOS)


def _render_into(target, scene, width, height, np, torch, Image, ImageDraw):
    for top in range(0, height, _TILE_SIZE):
        bottom = min(height, top + _TILE_SIZE)
        for left in range(0, width, _TILE_SIZE):
            right = min(width, left + _TILE_SIZE)
            expanded = (
                max(0, left - _GUTTER),
                max(0, top - _GUTTER),
                min(width, right + _GUTTER),
                min(height, bottom + _GUTTER),
            )
            tile = _draw_tile(scene, expanded, width, height, np, Image, ImageDraw)
            crop = tile.crop(
                (
                    left - expanded[0],
                    top - expanded[1],
                    right - expanded[0],
                    bottom - expanded[1],
                )
            )
            pixels = np.array(crop, dtype=np.uint8, copy=True)
            destination = target[top:bottom, left:right]
            destination.copy_(torch.from_numpy(pixels))
            destination.mul_(1.0 / 255.0)


def generate_composition_batch(
    *, width, height, family, palette, complexity, seed, batch_size
):
    """Return a deterministic CPU-contiguous ``[B,H,W,3]`` float32 tensor."""
    complexity = _validate(width, height, family, palette, complexity, seed, batch_size)

    # Heavy dependencies are deliberately delayed until every input and the
    # total output budget have been accepted.
    import numpy as np
    import torch
    from PIL import Image, ImageDraw

    output = torch.empty(
        (batch_size, height, width, 3), dtype=torch.float32, device="cpu"
    )
    for index in range(batch_size):
        item_seed = _mix64(seed ^ _mix64(index))
        chosen_family = family
        if family == _RANDOM:
            family_rng = random.Random(_mix64(item_seed ^ 0x46414D494C59))
            chosen_family = FAMILIES[family_rng.randrange(len(FAMILIES))]
        chosen_palette = palette
        if palette == _RANDOM:
            palette_rng = random.Random(_mix64(item_seed ^ 0x50414C45545445))
            chosen_palette = PALETTES[palette_rng.randrange(len(PALETTES))]
        detail_rng = random.Random(_mix64(item_seed ^ 0x44455441494C53))
        scene = _build_scene(
            width,
            height,
            chosen_family,
            chosen_palette,
            complexity,
            detail_rng,
        )
        _render_into(output[index], scene, width, height, np, torch, Image, ImageDraw)
    return output
