import json
import re
import string
from pathlib import Path, PurePosixPath, PureWindowsPath

MAX_METADATA_BYTES = 64 * 1024 * 1024
_ALLOWED_FIELDS = {
    "model",
    "date",
    "time",
    "datetime",
    "width",
    "height",
    "batch",
    "counter",
}
_ILLEGAL_COMPONENT = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_TRAILING_DOT_OR_SPACE = re.compile(r"[. ]+$")
_WINDOWS_RESERVED = re.compile(
    r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)",
    re.IGNORECASE,
)


def _sanitize_component(value):
    sanitized = _ILLEGAL_COMPONENT.sub("_", value)
    sanitized = _TRAILING_DOT_OR_SPACE.sub(
        lambda match: "_" * len(match.group()),
        sanitized,
    )
    if _WINDOWS_RESERVED.match(sanitized):
        sanitized = f"_{sanitized}"
    return sanitized


def _model_token(model):
    if model is None or not isinstance(model, str) or not model.strip():
        return "unknown_model"
    return _sanitize_component(model.strip())


class ParsedTemplate:
    def __init__(self, source, *, input_name):
        if not isinstance(source, str):
            raise ValueError(f"{input_name} must be a string")
        if len(source) > 512:
            raise ValueError(f"{input_name} must be at most 512 characters")

        self.source = source
        self.input_name = input_name
        formatter = string.Formatter()
        try:
            parsed = tuple(formatter.parse(source))
        except ValueError as error:
            raise ValueError(f"{input_name} is malformed: {error}") from None

        fields = []
        for _literal, field, format_spec, conversion in parsed:
            if field is None:
                continue
            if field not in _ALLOWED_FIELDS:
                raise ValueError(f"{input_name} has unknown field {field!r}")
            if conversion is not None:
                raise ValueError(f"{input_name} does not allow conversions")
            if format_spec:
                raise ValueError(
                    f"{input_name} does not allow format specifications"
                )
            fields.append(field)
        self.has_counter = "counter" in fields

    def render(
        self,
        *,
        model,
        timestamp,
        width,
        height,
        batch,
        counter,
    ):
        if isinstance(counter, bool) or not isinstance(counter, int) or not (
            1 <= counter <= 99_999
        ):
            raise ValueError("counter must be between 1 and 99999")
        values = {
            "model": _model_token(model),
            "date": timestamp.strftime("%Y-%m-%d"),
            "time": timestamp.strftime("%H-%M-%S"),
            "datetime": timestamp.strftime("%Y-%m-%d_%H-%M-%S"),
            "width": width,
            "height": height,
            "batch": batch,
            "counter": f"{counter:05d}",
        }
        return self.source.format(**values)


def render_relative_path(template, **values):
    rendered = template.render(**values)
    windows_path = PureWindowsPath(rendered)
    if (
        PurePosixPath(rendered).is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
    ):
        raise ValueError("path_template must be output-relative")

    components = []
    for component in rendered.replace("\\", "/").split("/"):
        if component == "..":
            raise ValueError("path_template must not contain '..'")
        if component in {"", "."}:
            continue
        component = _sanitize_component(component)
        if len(component) > 200:
            raise ValueError(
                "path_template rendered components must be at most 200 characters"
            )
        components.append(component)
    return Path(*components)


def render_filename(template, *, counter_in_templates, **values):
    stem = template.render(**values)
    while stem.lower().endswith(".png"):
        stem = stem[:-4]
    if not stem.strip():
        raise ValueError("filename_template must render a non-empty filename")
    stem = _sanitize_component(stem)
    if len(stem) > 200:
        raise ValueError(
            "filename_template rendered stem must be at most 200 characters"
        )
    if not counter_in_templates:
        stem = f"{stem}_{values['counter']:05d}_"
    return f"{stem}.png"


def validate_images(images):
    from torch import Tensor, isfinite
    from torch import bool as torch_bool

    if not isinstance(images, Tensor) or images.ndim != 4 or any(
        dimension < 1 for dimension in images.shape
    ):
        raise ValueError(
            "IMAGE must be a Torch tensor shaped [B,H,W,C] with positive dimensions"
        )
    if images.shape[3] not in {1, 3, 4}:
        raise ValueError(
            "IMAGE must be shaped [B,H,W,C] with C equal to 1, 3, or 4"
        )
    if images.dtype == torch_bool or images.is_complex():
        raise ValueError("IMAGE values must have a real numeric dtype")
    if not isfinite(images).all().item():
        raise ValueError("IMAGE values must all be finite")
    return tuple(int(dimension) for dimension in images.shape)


def image_to_pillow(frame):
    from PIL import Image
    from torch import float32, uint8

    pixels = (
        frame.detach()
        .to(device="cpu", dtype=float32)
        .clamp(0, 1)
        .mul(255)
        .to(uint8)
        .numpy()
    )
    if pixels.shape[2] == 1:
        pixels = pixels[:, :, 0]
    return Image.fromarray(pixels)


def serialize_metadata(
    *,
    save_metadata,
    global_disabled,
    prompt,
    extra_pnginfo,
):
    if not isinstance(save_metadata, bool):
        raise ValueError("save_metadata must be a boolean")
    if not save_metadata or global_disabled:
        return None
    if extra_pnginfo is not None and not isinstance(extra_pnginfo, dict):
        raise ValueError("EXTRA_PNGINFO must be a dictionary")
    if extra_pnginfo is not None and not all(
        isinstance(key, str) for key in extra_pnginfo
    ):
        raise ValueError("EXTRA_PNGINFO keys must be strings")

    values = []
    if prompt is not None:
        values.append(("prompt", _serialize_metadata_value("prompt", prompt)))
    if extra_pnginfo is not None:
        values.extend(
            (
                key,
                _serialize_metadata_value(f"EXTRA_PNGINFO entry {key!r}", value),
            )
            for key, value in extra_pnginfo.items()
        )

    if sum(len(value.encode("utf-8")) for _key, value in values) > (
        MAX_METADATA_BYTES
    ):
        raise ValueError("serialized metadata must be at most 64 MiB")
    return values


def _serialize_metadata_value(input_name, value):
    try:
        return json.dumps(value)
    except (OverflowError, RecursionError, TypeError, ValueError):
        raise ValueError(f"{input_name} must be JSON serializable") from None
