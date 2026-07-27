import re
import string
from pathlib import Path, PurePosixPath, PureWindowsPath

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
