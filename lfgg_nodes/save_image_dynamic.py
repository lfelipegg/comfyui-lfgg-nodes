import json
import re
import string
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath

MAX_COUNTER = 99_999
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
            1 <= counter <= MAX_COUNTER
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


def _output_root():
    import folder_paths

    try:
        root = Path(folder_paths.get_output_directory()).resolve(strict=True)
    except OSError:
        raise RuntimeError("ComfyUI output root is unavailable") from None
    if not root.is_dir():
        raise RuntimeError("ComfyUI output root is unavailable")
    return root


def _global_metadata_disabled():
    from comfy.cli_args import args

    return bool(args.disable_metadata)


def _assert_contained(parent, root):
    if not parent.is_relative_to(root):
        raise ValueError("path_template resolves outside the ComfyUI output root")


def _preflight_parent(root, subfolder):
    parent = (root / subfolder).resolve(strict=False)
    _assert_contained(parent, root)


def _prepare_parent(root, subfolder):
    parent = root / subfolder
    _assert_contained(parent.resolve(strict=False), root)
    parent.mkdir(parents=True, exist_ok=True)
    parent = parent.resolve(strict=True)
    _assert_contained(parent, root)
    return parent


def _pnginfo(metadata):
    if metadata is None:
        return None
    from PIL.PngImagePlugin import PngInfo

    pnginfo = PngInfo()
    for key, value in metadata:
        pnginfo.add_text(key, value)
    return pnginfo


def _safe_write_error(relative_path, error, root):
    reason = error.strerror or str(error) or error.__class__.__name__
    for root_text in {str(root), str(root).replace("/", "\\")}:
        reason = reason.replace(root_text, "<output-root>")
    return OSError(
        "LFGG Save Image Dynamic could not write "
        f"'{relative_path.as_posix()}': {reason}"
    )


class SaveImageDynamic:
    DESCRIPTION = (
        "Saves PNG image batches beneath the ComfyUI output directory using "
        "safe path and filename templates."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": (
                    "IMAGE",
                    {"tooltip": "Image batch to save as PNG files."},
                ),
                "path_template": (
                    "STRING",
                    {
                        "default": "runs/{model}/{date}",
                        "tooltip": (
                            "Output-relative subfolder template using supported "
                            "brace tokens."
                        ),
                    },
                ),
                "filename_template": (
                    "STRING",
                    {
                        "default": "{model}_{datetime}_{batch}_{counter}",
                        "tooltip": (
                            "PNG filename template using supported brace tokens."
                        ),
                    },
                ),
                "save_metadata": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": (
                            "Embed prompt and workflow metadata unless globally "
                            "disabled in ComfyUI."
                        ),
                    },
                ),
            },
            "optional": {
                "model_name": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": (
                            "Explicit model label used by the {model} token."
                        ),
                    },
                )
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "save_images"
    OUTPUT_NODE = True
    CATEGORY = "LFGG/Image"

    def save_images(
        self,
        images,
        path_template,
        filename_template,
        save_metadata,
        model_name=None,
        prompt=None,
        extra_pnginfo=None,
    ):
        batch, height, width, _channels = validate_images(images)
        if model_name is not None and not isinstance(model_name, str):
            raise ValueError("model_name must be a string")
        path = ParsedTemplate(path_template, input_name="path_template")
        filename = ParsedTemplate(
            filename_template,
            input_name="filename_template",
        )
        counter_in_templates = path.has_counter or filename.has_counter
        timestamp = datetime.now()
        metadata = serialize_metadata(
            save_metadata=save_metadata,
            global_disabled=_global_metadata_disabled(),
            prompt=prompt,
            extra_pnginfo=extra_pnginfo,
        )
        pnginfo = _pnginfo(metadata)
        root = _output_root()

        for batch_index in range(batch):
            values = {
                "model": model_name,
                "timestamp": timestamp,
                "width": width,
                "height": height,
                "batch": batch_index,
                "counter": 1,
            }
            subfolder = render_relative_path(path, **values)
            render_filename(
                filename,
                counter_in_templates=counter_in_templates,
                **values,
            )
            _preflight_parent(root, subfolder)

        created = []
        results = []
        counter = 1
        try:
            for batch_index, frame in enumerate(images):
                while counter <= MAX_COUNTER:
                    values = {
                        "model": model_name,
                        "timestamp": timestamp,
                        "width": width,
                        "height": height,
                        "batch": batch_index,
                        "counter": counter,
                    }
                    subfolder = render_relative_path(path, **values)
                    file = render_filename(
                        filename,
                        counter_in_templates=counter_in_templates,
                        **values,
                    )
                    relative = subfolder / file
                    try:
                        parent = _prepare_parent(root, subfolder)
                    except OSError as error:
                        raise _safe_write_error(relative, error, root) from None
                    try:
                        handle = (parent / file).open("xb")
                    except FileExistsError:
                        counter += 1
                        continue
                    except OSError as error:
                        raise _safe_write_error(relative, error, root) from None

                    candidate = parent / file
                    created.append(candidate)
                    try:
                        with handle:
                            image_to_pillow(frame).save(
                                handle,
                                format="PNG",
                                pnginfo=pnginfo,
                                compress_level=4,
                            )
                    except OSError as error:
                        raise _safe_write_error(relative, error, root) from None

                    results.append(
                        {
                            "filename": file,
                            "subfolder": (
                                "" if subfolder == Path() else subfolder.as_posix()
                            ),
                            "type": "output",
                        }
                    )
                    counter += 1
                    break
                else:
                    raise FileExistsError(
                        "LFGG Save Image Dynamic exhausted the five-digit counter"
                    )
        except Exception:
            cleanup_failed = False
            for candidate in reversed(created):
                try:
                    candidate.unlink(missing_ok=True)
                except OSError:
                    cleanup_failed = True
            if cleanup_failed:
                raise OSError(
                    "LFGG Save Image Dynamic failed and could not remove every "
                    "file created by this execution"
                ) from None
            raise

        return {"ui": {"images": results}}
