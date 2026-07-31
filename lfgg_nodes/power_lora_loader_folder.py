from math import isfinite
from pathlib import PurePosixPath

ALL_LORAS = "All LoRAs"
NO_LORAS = "<no LoRAs found>"
ROW_FIELDS = frozenset({"on", "lora", "strength_model", "strength_clip"})


def normalize_lora_name(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("LoRA name must be a non-empty relative string")
    cleaned = value.replace("\\", "/").strip()
    path = PurePosixPath(cleaned)
    if (
        path.is_absolute()
        or ":" in cleaned
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError("LoRA name must be a relative path beneath a LoRA root")
    return path.as_posix()


def build_lora_catalog(names):
    loras = sorted({normalize_lora_name(name) for name in names})
    folders = {
        "/".join(PurePosixPath(name).parts[:depth])
        for name in loras
        for depth in range(1, len(PurePosixPath(name).parts))
    }
    return [ALL_LORAS, *sorted(folders)], loras


def filter_loras(loras, folder):
    if folder == ALL_LORAS:
        return list(loras)
    normalized = normalize_lora_name(folder)
    prefix = f"{normalized}/"
    return [name for name in loras if name.startswith(prefix)]


def _strength(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    value = float(value)
    if not isfinite(value):
        raise ValueError(f"{name} must be finite")
    if not -100.0 <= value <= 100.0:
        raise ValueError(f"{name} must be between -100 and 100")
    return value


def validate_lora_row(row):
    if not isinstance(row, dict):
        raise ValueError("LoRA row must be a mapping")
    if set(row) != ROW_FIELDS:
        raise ValueError("LoRA row has unsupported or missing fields")
    if type(row["on"]) is not bool:
        raise ValueError("LoRA row on must be Boolean")
    return (
        row["on"],
        normalize_lora_name(row["lora"]),
        _strength("strength_model", row["strength_model"]),
        _strength("strength_clip", row["strength_clip"]),
    )


class _AnyType(str):
    def __ne__(self, _other):
        return False


class _DynamicLoraInputs(dict):
    _type = _AnyType("*")

    @staticmethod
    def _valid(key):
        prefix, separator, suffix = key.partition("_")
        return (
            prefix == "lora"
            and separator
            and suffix.isdigit()
            and int(suffix) > 0
        )

    def __contains__(self, key):
        return isinstance(key, str) and self._valid(key)

    def __getitem__(self, key):
        if key not in self:
            raise KeyError(key)
        return (self._type,)


def _catalog():
    import folder_paths

    return build_lora_catalog(folder_paths.get_filename_list("loras"))


def _validated_active_rows(rows):
    optional = _DynamicLoraInputs()
    if any(key not in optional for key in rows):
        raise ValueError("LFGG received an unsupported dynamic LoRA input")

    validated = []
    for key, value in sorted(
        rows.items(),
        key=lambda item: int(item[0].partition("_")[2]),
    ):
        try:
            row = validate_lora_row(value)
        except ValueError as error:
            raise ValueError(f"LFGG invalid {key}: {error}") from None
        if row[0] and (row[2] != 0 or row[3] != 0):
            validated.append(row)
    return validated


def _validate_active_files(rows):
    from pathlib import Path

    import folder_paths

    try:
        registered = {
            normalize_lora_name(name)
            for name in folder_paths.get_filename_list("loras")
        }
    except (TypeError, ValueError):
        raise ValueError("LFGG LoRA catalog contains an invalid filename") from None

    try:
        roots = [
            Path(root).resolve(strict=True)
            for root in folder_paths.get_folder_paths("loras")
        ]
    except (OSError, TypeError, ValueError):
        raise ValueError("LFGG LoRA root is missing or unavailable") from None
    if not roots or any(not root.is_dir() for root in roots):
        raise ValueError("LFGG LoRA root is missing or unavailable")

    for _on, name, _strength_model, _strength_clip in rows:
        if name not in registered:
            raise ValueError(f"LFGG unknown LoRA: {name}")
        try:
            path = Path(
                folder_paths.get_full_path_or_raise("loras", name)
            ).resolve(strict=True)
        except (OSError, TypeError, ValueError):
            raise ValueError(f"LFGG LoRA file is missing: {name}") from None
        if not path.is_file() or not any(
            path.is_relative_to(root) for root in roots
        ):
            raise ValueError(f"LFGG LoRA file must stay beneath a LoRA root: {name}")


class PowerLoraLoaderFolder:
    CATEGORY = "LFGG/loaders"
    DESCRIPTION = (
        "Applies ordered LoRAs while limiting new selections to a saved "
        "LoRA folder."
    )
    FUNCTION = "load_loras"
    RETURN_TYPES = ("MODEL", "CLIP")
    RETURN_NAMES = ("model", "clip")
    OUTPUT_TOOLTIPS = (
        "Model with every enabled LoRA applied in row order.",
        "CLIP with every enabled LoRA applied in row order.",
    )

    @classmethod
    def INPUT_TYPES(cls):
        folders, loras = _catalog()
        folder_default = folders[1] if len(folders) > 1 else ALL_LORAS
        lora_options = loras or [NO_LORAS]
        return {
            "required": {
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "folder": (
                    "COMBO",
                    {
                        "options": folders,
                        "default": folder_default,
                        "tooltip": (
                            "Limits future LoRA choices to this folder and "
                            "its descendants."
                        ),
                    },
                ),
                "lora_to_add": (
                    "COMBO",
                    {
                        "options": lora_options,
                        "default": lora_options[0],
                        "tooltip": "LoRA to add as the next ordered row.",
                    },
                ),
            },
            "optional": _DynamicLoraInputs(),
        }

    def load_loras(
        self,
        model,
        clip,
        folder,
        lora_to_add,
        **rows,
    ):
        active_rows = _validated_active_rows(rows)
        _validate_active_files(active_rows)
        if not active_rows:
            return model, clip

        from nodes import LoraLoader

        loader = LoraLoader()
        for _on, name, strength_model, strength_clip in active_rows:
            model, clip = loader.load_lora(
                model,
                clip,
                name,
                strength_model,
                strength_clip,
            )
        return model, clip
