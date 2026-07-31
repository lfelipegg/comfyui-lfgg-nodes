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
