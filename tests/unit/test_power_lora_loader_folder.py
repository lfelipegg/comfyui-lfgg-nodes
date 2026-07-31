import importlib
import math
import sys
import types
from pathlib import Path

import pytest

import lfgg_nodes.power_lora_loader_folder as power_lora
from lfgg_nodes.power_lora_loader_folder import (
    ALL_LORAS,
    NO_LORAS,
    build_lora_catalog,
    filter_loras,
    validate_lora_row,
)


class CallLog(list):
    def __init__(self):
        super().__init__()
        self.resolved = []


def install_comfy_stubs(monkeypatch, tmp_path, names, *, missing=()):
    root = tmp_path / "loras"
    root.mkdir()
    missing = {name.replace("\\", "/") for name in missing}
    for name in names:
        normalized = name.replace("\\", "/")
        if normalized in missing:
            continue
        path = root / normalized
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"lora")

    calls = CallLog()

    def get_full_path_or_raise(_category, name):
        calls.resolved.append(name)
        path = root / name
        if not path.exists():
            raise FileNotFoundError(name)
        return str(path)

    class LoraLoader:
        def load_lora(
            self,
            model,
            clip,
            name,
            strength_model,
            strength_clip,
        ):
            calls.append(
                {
                    "name": name,
                    "strength_model": strength_model,
                    "strength_clip": strength_clip,
                }
            )
            label = Path(name).stem
            return f"{model}|{label}", f"{clip}|{label}"

    monkeypatch.setitem(
        sys.modules,
        "folder_paths",
        types.SimpleNamespace(
            get_filename_list=lambda _category: list(names),
            get_full_path_or_raise=get_full_path_or_raise,
            get_folder_paths=lambda _category: [str(root)],
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "nodes",
        types.SimpleNamespace(LoraLoader=LoraLoader),
    )
    return calls


def row(name, *, on=True, model=1.0, clip=1.0):
    return {
        "on": on,
        "lora": name,
        "strength_model": model,
        "strength_clip": clip,
    }


def test_catalog_infers_every_parent_and_normalizes_separators():
    folders, loras = build_lora_catalog(
        [
            r"characters\anime\hero.safetensors",
            "characters/photo.safetensors",
            "styles/ink.safetensors",
            "root.safetensors",
        ]
    )

    assert folders == [
        ALL_LORAS,
        "characters",
        "characters/anime",
        "styles",
    ]
    assert loras == [
        "characters/anime/hero.safetensors",
        "characters/photo.safetensors",
        "root.safetensors",
        "styles/ink.safetensors",
    ]


def test_filter_is_recursive_and_all_loras_disables_it():
    _, loras = build_lora_catalog(
        [
            "characters/anime/hero.safetensors",
            "characters/photo.safetensors",
            "style.safetensors",
        ]
    )

    assert filter_loras(loras, "characters") == [
        "characters/anime/hero.safetensors",
        "characters/photo.safetensors",
    ]
    assert filter_loras(loras, "characters/anime") == [
        "characters/anime/hero.safetensors"
    ]
    assert filter_loras(loras, ALL_LORAS) == loras


def test_row_validation_returns_normalized_values():
    assert validate_lora_row(
        {
            "on": True,
            "lora": r"characters\hero.safetensors",
            "strength_model": 0.75,
            "strength_clip": 1,
        }
    ) == (True, "characters/hero.safetensors", 0.75, 1.0)


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (None, "mapping"),
        (
            {
                "on": 1,
                "lora": "x",
                "strength_model": 1,
                "strength_clip": 1,
            },
            "Boolean",
        ),
        (
            {
                "on": True,
                "lora": "../x",
                "strength_model": 1,
                "strength_clip": 1,
            },
            "relative",
        ),
        (
            {
                "on": True,
                "lora": "/x",
                "strength_model": 1,
                "strength_clip": 1,
            },
            "relative",
        ),
        (
            {
                "on": True,
                "lora": "C:/x",
                "strength_model": 1,
                "strength_clip": 1,
            },
            "relative",
        ),
        (
            {
                "on": True,
                "lora": "x",
                "strength_model": True,
                "strength_clip": 1,
            },
            "numeric",
        ),
        (
            {
                "on": True,
                "lora": "x",
                "strength_model": math.inf,
                "strength_clip": 1,
            },
            "finite",
        ),
        (
            {
                "on": True,
                "lora": "x",
                "strength_model": 101,
                "strength_clip": 1,
            },
            "between",
        ),
        (
            {
                "on": True,
                "lora": "x",
                "strength_model": -101,
                "strength_clip": 1,
            },
            "between",
        ),
        (
            {
                "on": True,
                "lora": "",
                "strength_model": 1,
                "strength_clip": 1,
            },
            "non-empty",
        ),
        (
            {
                "on": True,
                "lora": "x",
                "strength_model": 1,
                "strength_clip": "1",
            },
            "numeric",
        ),
        (
            {"on": True, "lora": "x", "strength_model": 1},
            "unsupported or missing",
        ),
        (
            {
                "on": True,
                "lora": "x",
                "strength_model": 1,
                "strength_clip": 1,
                "extra": False,
            },
            "unsupported or missing",
        ),
    ],
)
def test_row_validation_rejects_untrusted_payloads(row, message):
    with pytest.raises(ValueError, match=message):
        validate_lora_row(row)


def test_schema_exposes_folder_and_add_selectors(monkeypatch, tmp_path):
    install_comfy_stubs(
        monkeypatch,
        tmp_path,
        [
            "characters/anime/hero.safetensors",
            "styles/ink.safetensors",
        ],
    )

    schema = power_lora.PowerLoraLoaderFolder.INPUT_TYPES()

    assert list(schema["required"]) == [
        "model",
        "clip",
        "folder",
        "lora_to_add",
    ]
    assert schema["required"]["folder"][1]["options"] == [
        ALL_LORAS,
        "characters",
        "characters/anime",
        "styles",
    ]
    assert schema["required"]["folder"][1]["default"] == "characters"
    assert schema["required"]["lora_to_add"][1]["options"] == [
        "characters/anime/hero.safetensors",
        "styles/ink.safetensors",
    ]
    assert dict(schema["optional"]) == {}
    assert "lora_1" in schema["optional"]
    assert "lora_0" not in schema["optional"]
    assert "other_1" not in schema["optional"]


def test_empty_catalog_uses_explicit_placeholder(monkeypatch, tmp_path):
    install_comfy_stubs(monkeypatch, tmp_path, [])

    required = power_lora.PowerLoraLoaderFolder.INPUT_TYPES()["required"]

    assert required["folder"][1]["options"] == [ALL_LORAS]
    assert required["folder"][1]["default"] == ALL_LORAS
    assert required["lora_to_add"][1]["options"] == [NO_LORAS]


def test_applies_active_rows_in_numeric_order(monkeypatch, tmp_path):
    calls = install_comfy_stubs(
        monkeypatch,
        tmp_path,
        ["a.safetensors", "b.safetensors"],
    )

    result = power_lora.PowerLoraLoaderFolder().load_loras(
        "model",
        "clip",
        ALL_LORAS,
        "a.safetensors",
        lora_2=row("b.safetensors", model=0.5, clip=0.25),
        lora_1=row("a.safetensors", model=1.0, clip=0.75),
    )

    assert [call["name"] for call in calls] == [
        "a.safetensors",
        "b.safetensors",
    ]
    assert result == ("model|a|b", "clip|a|b")


def test_validates_every_active_file_before_loading(monkeypatch, tmp_path):
    calls = install_comfy_stubs(
        monkeypatch,
        tmp_path,
        ["valid.safetensors"],
    )

    with pytest.raises(ValueError, match="LFGG.*unknown"):
        power_lora.PowerLoraLoaderFolder().load_loras(
            "model",
            "clip",
            ALL_LORAS,
            "valid.safetensors",
            lora_1=row("valid.safetensors"),
            lora_2=row("missing.safetensors"),
        )

    assert calls == []


def test_disabled_and_zero_rows_do_not_resolve_files(monkeypatch, tmp_path):
    calls = install_comfy_stubs(monkeypatch, tmp_path, [])

    result = power_lora.PowerLoraLoaderFolder().load_loras(
        "model",
        "clip",
        ALL_LORAS,
        NO_LORAS,
        lora_1=row("disabled.safetensors", on=False),
        lora_2=row("zero.safetensors", model=0, clip=0),
    )

    assert calls.resolved == []
    assert calls == []
    assert result == ("model", "clip")


def test_one_zero_strength_still_loads_the_other_target(monkeypatch, tmp_path):
    calls = install_comfy_stubs(monkeypatch, tmp_path, ["a.safetensors"])

    power_lora.PowerLoraLoaderFolder().load_loras(
        "model",
        "clip",
        ALL_LORAS,
        "a.safetensors",
        lora_1=row("a.safetensors", model=0, clip=0.5),
    )

    assert calls == [
        {
            "name": "a.safetensors",
            "strength_model": 0.0,
            "strength_clip": 0.5,
        }
    ]


def test_rejects_unsupported_dynamic_input_keys(monkeypatch, tmp_path):
    install_comfy_stubs(monkeypatch, tmp_path, [])

    with pytest.raises(ValueError, match="LFGG.*dynamic"):
        power_lora.PowerLoraLoaderFolder().load_loras(
            "model",
            "clip",
            ALL_LORAS,
            NO_LORAS,
            other_1=row("a.safetensors"),
        )


def test_rejects_unknown_and_missing_registered_files(monkeypatch, tmp_path):
    install_comfy_stubs(
        monkeypatch,
        tmp_path,
        ["missing.safetensors"],
        missing={"missing.safetensors"},
    )
    node = power_lora.PowerLoraLoaderFolder()

    with pytest.raises(ValueError, match="LFGG.*unknown"):
        node.load_loras(
            "model",
            "clip",
            ALL_LORAS,
            NO_LORAS,
            lora_1=row("unknown.safetensors"),
        )
    with pytest.raises(ValueError, match="LFGG.*missing"):
        node.load_loras(
            "model",
            "clip",
            ALL_LORAS,
            NO_LORAS,
            lora_1=row("missing.safetensors"),
        )


def test_rejects_resolved_symlink_escape(monkeypatch, tmp_path):
    install_comfy_stubs(monkeypatch, tmp_path, ["escape.safetensors"])
    link = tmp_path / "loras" / "escape.safetensors"
    link.unlink()
    outside = tmp_path / "outside.safetensors"
    outside.write_bytes(b"outside")
    try:
        link.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {type(error).__name__}")

    with pytest.raises(ValueError, match="LFGG.*root"):
        power_lora.PowerLoraLoaderFolder().load_loras(
            "model",
            "clip",
            ALL_LORAS,
            "escape.safetensors",
            lora_1=row("escape.safetensors"),
        )


def test_ignores_an_unavailable_unused_lora_root(monkeypatch, tmp_path):
    calls = install_comfy_stubs(monkeypatch, tmp_path, ["valid.safetensors"])
    folder_paths = sys.modules["folder_paths"]
    folder_paths.get_folder_paths = lambda _category: [
        str(tmp_path / "missing"),
        str(tmp_path / "loras"),
    ]

    result = power_lora.PowerLoraLoaderFolder().load_loras(
        "model",
        "clip",
        ALL_LORAS,
        "valid.safetensors",
        lora_1=row("valid.safetensors"),
    )

    assert result == ("model|valid", "clip|valid")
    assert [call["name"] for call in calls] == ["valid.safetensors"]


def test_current_folder_does_not_limit_existing_rows(monkeypatch, tmp_path):
    calls = install_comfy_stubs(
        monkeypatch,
        tmp_path,
        ["characters/hero.safetensors", "styles/ink.safetensors"],
    )

    power_lora.PowerLoraLoaderFolder().load_loras(
        "model",
        "clip",
        "styles",
        "styles/ink.safetensors",
        lora_1=row("characters/hero.safetensors"),
    )

    assert [call["name"] for call in calls] == [
        "characters/hero.safetensors"
    ]


def test_module_import_does_not_import_comfy_boundaries(monkeypatch):
    monkeypatch.delitem(sys.modules, "folder_paths", raising=False)
    monkeypatch.delitem(sys.modules, "nodes", raising=False)

    importlib.reload(power_lora)

    assert "folder_paths" not in sys.modules
    assert "nodes" not in sys.modules
