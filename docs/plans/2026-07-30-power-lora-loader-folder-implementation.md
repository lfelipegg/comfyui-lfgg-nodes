# Power LoRA Loader Folder Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a standalone `LFGG Power LoRA Loader (Folder)` with recursive,
workflow-saved folder filtering and ordered compact multi-LoRA controls.

**Architecture:** Keep filename normalization, folder inference, row
validation, and ordering in one dependency-light Python node module. Use
ComfyUI's V1 schema and native `LoraLoader` at the backend boundary, plus one
build-free frontend loader and one testable ES module for dynamic rows and
workflow restoration.

**Tech Stack:** Python 3.10+, ComfyUI V1 nodes, standard library, handwritten
ES modules, `pytest`, and `node:test`.

---

Implementation baseline: commit `0027763`. Before editing, use
`@superpowers:using-git-worktrees` to create an isolated worktree. Execute each
behavior test-first with `@superpowers:test-driven-development`, and finish
with `@superpowers:verification-before-completion`.

The accepted behavior is
`docs/plans/2026-07-30-power-lora-loader-folder-design.md`. Do not broaden it
to rgthree integration, regex/multi-folder filters, connected folder inputs,
model-info services, routes, presets, trigger outputs, or a reusable dynamic
widget framework.

### Task 1: Implement catalog and row validation

**Files:**
- Create: `tests/unit/test_power_lora_loader_folder.py`
- Create: `lfgg_nodes/power_lora_loader_folder.py`

**Step 1: Write the failing pure tests**

Start the test module without importing ComfyUI:

```python
import math

import pytest

from lfgg_nodes.power_lora_loader_folder import (
    ALL_LORAS,
    build_lora_catalog,
    filter_loras,
    validate_lora_row,
)


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
        ({"on": 1, "lora": "x", "strength_model": 1, "strength_clip": 1}, "Boolean"),
        ({"on": True, "lora": "../x", "strength_model": 1, "strength_clip": 1}, "relative"),
        ({"on": True, "lora": "x", "strength_model": True, "strength_clip": 1}, "numeric"),
        ({"on": True, "lora": "x", "strength_model": math.inf, "strength_clip": 1}, "finite"),
        ({"on": True, "lora": "x", "strength_model": 101, "strength_clip": 1}, "between"),
    ],
)
def test_row_validation_rejects_untrusted_payloads(row, message):
    with pytest.raises(ValueError, match=message):
        validate_lora_row(row)
```

Add one case each for absolute POSIX paths, drive markers, missing/extra row
fields, empty names, nonnumeric CLIP strength, and a value below `-100`.

**Step 2: Run the focused tests and verify RED**

Run:

```bash
python -m pytest -q tests/unit/test_power_lora_loader_folder.py
```

Expected: collection fails because the module does not exist.

**Step 3: Implement the minimum pure helpers**

In `lfgg_nodes/power_lora_loader_folder.py`, use only standard-library imports
at module load:

```python
from math import isfinite
from pathlib import PurePosixPath

ALL_LORAS = "All LoRAs"
NO_LORAS = "<no LoRAs found>"
ROW_FIELDS = frozenset(
    {"on", "lora", "strength_model", "strength_clip"}
)


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
```

Do not add a catalog class, regex support, filesystem scan, configuration
object, or shared validator module.

**Step 4: Run focused checks and verify GREEN**

Run:

```bash
python -m pytest -q tests/unit/test_power_lora_loader_folder.py
python -m ruff check lfgg_nodes/power_lora_loader_folder.py tests/unit/test_power_lora_loader_folder.py
```

Expected: PASS.

**Step 5: Commit**

```bash
git add lfgg_nodes/power_lora_loader_folder.py tests/unit/test_power_lora_loader_folder.py
git commit -m "feat: validate folder-filtered lora rows"
```

### Task 2: Add secure ordered ComfyUI execution and registration

**Files:**
- Modify: `tests/unit/test_power_lora_loader_folder.py`
- Modify: `tests/unit/test_contract.py`
- Modify: `lfgg_nodes/power_lora_loader_folder.py`
- Modify: `__init__.py`

**Step 1: Add failing schema, execution, and path-boundary tests**

Stub `folder_paths` and `nodes.LoraLoader` through `sys.modules`. Cover:

```python
def test_schema_exposes_folder_and_add_selectors(monkeypatch, tmp_path):
    install_comfy_stubs(
        monkeypatch,
        tmp_path,
        [
            "characters/anime/hero.safetensors",
            "styles/ink.safetensors",
        ],
    )

    schema = PowerLoraLoaderFolder.INPUT_TYPES()

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


def test_applies_active_rows_in_numeric_order(monkeypatch, tmp_path):
    calls = install_comfy_stubs(
        monkeypatch,
        tmp_path,
        ["a.safetensors", "b.safetensors"],
    )

    result = PowerLoraLoaderFolder().load_loras(
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
    calls = install_comfy_stubs(monkeypatch, tmp_path, ["valid.safetensors"])

    with pytest.raises(ValueError, match="unknown"):
        PowerLoraLoaderFolder().load_loras(
            "model",
            "clip",
            ALL_LORAS,
            "valid.safetensors",
            lora_1=row("valid.safetensors"),
            lora_2=row("missing.safetensors"),
        )

    assert calls == []
```

Also test:

- disabled and both-zero rows do not resolve or load a file;
- one zero strength still loads the other target;
- malformed row keys such as `other_1` are rejected;
- missing files and unknown registered names fail;
- resolved symlink escape fails;
- a selected row outside the current folder still loads;
- an empty catalog uses `[ALL_LORAS]` and `[NO_LORAS]`;
- module/root-package import does not import `folder_paths` or `nodes.LoraLoader`;
- registration and display names are exactly prefixed.

**Step 2: Run the focused tests and verify RED**

Run:

```bash
python -m pytest -q tests/unit/test_power_lora_loader_folder.py tests/unit/test_contract.py
```

Expected: FAIL because the node class, dynamic input mapping, and registration
do not exist.

**Step 3: Implement the V1 boundary**

Add a strict local dynamic optional-input mapping. It should report only
`lora_<positive integer>` keys as supported and return a local wildcard string
whose `__ne__` is always false. Iteration stays empty so object info remains
JSON-safe. Do not copy rgthree's general flexible-input utility.

Implement:

```python
class _AnyType(str):
    def __ne__(self, _other):
        return False


class _DynamicLoraInputs(dict):
    _type = _AnyType("*")

    @staticmethod
    def _valid(key):
        prefix, separator, suffix = key.partition("_")
        return prefix == "lora" and separator and suffix.isdigit() and int(suffix) > 0

    def __contains__(self, key):
        return isinstance(key, str) and self._valid(key)

    def __getitem__(self, key):
        if key not in self:
            raise KeyError(key)
        return (self._type,)
```

`INPUT_TYPES()` imports `folder_paths` locally, calls
`folder_paths.get_filename_list("loras")`, and returns required `MODEL`,
`CLIP`, `folder`, and `lora_to_add` inputs plus
`"optional": _DynamicLoraInputs()`. The combos use the current
`("COMBO", {"options": [...]})` form. Keep both selectors non-connectable
ordinary widgets.

Add class metadata:

```python
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
```

Before loading, validate all row keys and values. Sort by the numeric suffix,
then resolve every active, nonzero row:

1. Compare the normalized name against the normalized current
   `get_filename_list("loras")`.
2. Resolve `folder_paths.get_full_path_or_raise("loras", name)` strictly.
3. Resolve every `folder_paths.get_folder_paths("loras")` root.
4. Require a regular file beneath at least one resolved root.

Only after every active row passes, import `nodes.LoraLoader`, create one
loader instance, and call:

```python
model, clip = loader.load_lora(
    model,
    clip,
    name,
    strength_model,
    strength_clip,
)
```

Register the node in root `__init__.py` through `_merge_class_mappings` and add
the exact display name. Preserve registration-only imports and duplicate
rejection.

Do not add `VALIDATE_INPUTS(**kwargs)`: it would disable ComfyUI's built-in
validation for all captured schema inputs. Execution validation is the
authoritative dynamic-row trust boundary.

**Step 4: Run focused checks and verify GREEN**

Run:

```bash
python -m pytest -q tests/unit/test_power_lora_loader_folder.py tests/unit/test_contract.py
python -m ruff check lfgg_nodes/power_lora_loader_folder.py __init__.py tests/unit/test_power_lora_loader_folder.py tests/unit/test_contract.py
```

Expected: PASS.

**Step 5: Commit**

```bash
git add __init__.py lfgg_nodes/power_lora_loader_folder.py tests/unit/test_power_lora_loader_folder.py tests/unit/test_contract.py
git commit -m "feat: load ordered loras from validated rows"
```

### Task 3: Add the compact folder-aware frontend

**Files:**
- Create: `web/power_lora_loader.js`
- Create: `web/power_lora_loader.mjs`
- Create: `tests/frontend/power_lora_loader.test.mjs`

**Step 1: Write failing dependency-free frontend tests**

Import only the `.mjs` module. Use a fake node with standard `folder` and
`lora_to_add` widgets plus `addCustomWidget`, `setSize`, `computeSize`, and
`setDirtyCanvas` methods.

Cover:

```javascript
test("filters recursively and shortens visible labels", () => {
  assert.deepEqual(
    folderChoices([
      "characters/anime/hero.safetensors",
      "characters/photo.safetensors",
      "style.safetensors",
    ]),
    ["All LoRAs", "characters", "characters/anime"],
  );
  assert.deepEqual(
    chooserChoices(
      ["characters/anime/hero.safetensors", "characters/photo.safetensors"],
      "characters",
    ),
    [
      { label: "anime/hero.safetensors", value: "characters/anime/hero.safetensors" },
      { label: "photo.safetensors", value: "characters/photo.safetensors" },
    ],
  );
});

test("changing folders preserves existing rows", () => {
  const node = fakeNode();
  const controls = installPowerLoraLoader(node);
  controls.add("characters/hero.safetensors");

  controls.setFolder("styles");

  assert.deepEqual(controls.rows.map((row) => row.lora), [
    "characters/hero.safetensors",
  ]);
});

test("reorder renumbers prompt widgets without changing row values", () => {
  const node = fakeNode();
  const controls = installPowerLoraLoader(node);
  controls.add("a.safetensors");
  controls.add("b.safetensors");

  controls.move(1, -1);

  assert.deepEqual(controls.rows.map((row) => row.lora), [
    "b.safetensors",
    "a.safetensors",
  ]);
  assert.deepEqual(controls.rowWidgets.map((widget) => widget.name), [
    "lora_1",
    "lora_2",
  ]);
});
```

Also cover:

- `All LoRAs`;
- nested folder selection;
- folder default and empty results;
- add, replace, enable, strengths, remove, and toggle-all;
- unique sequential prompt keys after every edit;
- row `serializeValue()` returning exactly the four backend fields;
- `onSerialize` saving ordered rows under
  `properties.lfgg_lora_rows` without positional dynamic widget values;
- restoration through the second install/loaded-node call;
- preserving a missing saved folder and exposing no add choices; and
- idempotent installation.

**Step 2: Run the focused test and verify RED**

Run:

```bash
node --test tests/frontend/power_lora_loader.test.mjs
```

Expected: FAIL because the module does not exist.

**Step 3: Implement pure state and the smallest custom row UI**

In `web/power_lora_loader.mjs`:

- keep catalog/filter/relative-label functions pure;
- bind only when `node.comfyClass === "LFGG_PowerLoraLoaderFolder"`;
- retain the complete original LoRA options from `lora_to_add`;
- compose, rather than replace, existing combo callbacks;
- update `lora_to_add.options.values` when `folder` changes;
- store complete filenames and display only folder-relative labels;
- keep ordered rows in one local array;
- renumber row widget names after add/move/remove;
- clamp finite strengths to `[-100, 100]`; and
- resize without shrinking a user-expanded node.

Use one 24-pixel custom canvas widget per row. Draw only:

- enabled toggle;
- relative filename;
- model strength;
- CLIP strength; and
- a row-menu affordance.

Clicking the filename opens the current filtered choices to replace that row.
Clicking a strength opens the normal canvas numeric prompt. The row menu
contains only move up, move down, and remove. The header contains toggle-all;
the footer contains `Add LoRA`. Use theme-derived LiteGraph colors and omit
decorative animation or model-info affordances.

Each row widget's `serializeValue()` returns:

```javascript
{
  on: row.on,
  lora: row.lora,
  strength_model: row.strengthModel,
  strength_clip: row.strengthClip,
}
```

Persist restoration data in `node.properties.lfgg_lora_rows`. Compose
`node.onSerialize` to remove row-widget positional values after copying the
plain row array to properties. Mark header/footer widgets with
`serialize: false` directly on each widget; do not rely only on
`widget.options.serialize`.

The small loader `web/power_lora_loader.js` imports `app` and registers:

```javascript
app.registerExtension({
  name: "lfgg.powerLoraLoaderFolder",
  nodeCreated: (node) => installPowerLoraLoader(node),
  loadedGraphNode: (node) => installPowerLoraLoader(node, { restore: true }),
});
```

Do not use `beforeRegisterNodeDef`, patch a prototype, import rgthree, fetch a
route, poll, or add a build system.

**Step 4: Run frontend checks and verify GREEN**

Run:

```bash
node --test tests/frontend/power_lora_loader.test.mjs
node --test tests/frontend/ratio_preview.test.mjs
node --test tests/frontend/crop_editor.test.mjs
```

Expected: PASS.

**Step 5: Commit**

```bash
git add web/power_lora_loader.js web/power_lora_loader.mjs tests/frontend/power_lora_loader.test.mjs
git commit -m "feat: add folder-aware power lora controls"
```

### Task 4: Document and package the additive 1.5.0 contract

**Files:**
- Create: `web/docs/LFGG_PowerLoraLoaderFolder/en.md`
- Create: `release/1.5.0-schema.json`
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `tests/unit/test_contract.py`
- Modify: `tests/package/test_archive.py`

**Step 1: Add failing documentation and package assertions**

Update contract expectations to require:

- project and schema version `1.5.0`;
- the exact node ID, display name, category, inputs, outputs, descriptions,
  tooltips, and registration order;
- embedded help IDs
  `{"LFGG_LoadAndCropImage", "LFGG_PowerLoraLoaderFolder"}`;
- README claims for recursive folder filtering, `All LoRAs`, existing-row
  preservation, ordered loading, refresh behavior, no rgthree dependency,
  no network/file writes, and the new frontend test command; and
- the new Python, frontend, and help files in `EXPECTED_PATHS`.

Point the release-schema assertion at `release/1.5.0-schema.json`.

**Step 2: Run focused checks and verify RED**

Run:

```bash
python -m pytest -q tests/unit/test_contract.py
```

Expected: FAIL on version, documentation, help, and schema expectations.

**Step 3: Write the minimum user documentation and manifests**

Add the node to the README's node table and behavior/security sections. Make
clear that:

- folder filtering affects only future selections;
- child folders are included recursively;
- existing rows are never removed by a folder change;
- `All LoRAs` is available;
- refresh node definitions after adding/removing LoRA files;
- the node is standalone and does not require rgthree; and
- it reads LoRA files through ComfyUI but performs no writes or network calls.

Remove only the claim that all LoRA loader work is deferred; keep the separate
legacy single-LoRA-by-path effort deferred.

Add concise embedded help with inputs, row controls, execution order, missing
folder/file behavior, and outputs. Bump `pyproject.toml` to `1.5.0` without
changing dependencies or compatibility floors.

Generate `release/1.5.0-schema.json` from the exact JSON-safe
`NODE_CLASS_MAPPINGS` contract using the same shape asserted in
`test_contract.py`. Do not hand-edit unrelated node schemas.

After the Markdown changes, run:

```bash
python3 .codex-context/ctx.py ingest
```

**Step 4: Run focused checks and verify GREEN**

Run:

```bash
python -m pytest -q tests/unit/test_contract.py
python -m pytest -q tests/package/test_archive.py -k "not candidate"
python -m ruff check .
```

Expected: PASS.

**Step 5: Commit**

```bash
git add README.md pyproject.toml release/1.5.0-schema.json tests/unit/test_contract.py tests/package/test_archive.py web/docs/LFGG_PowerLoraLoaderFolder/en.md
git commit -m "docs: qualify power lora loader contract"
```

### Task 5: Verify the package and record the exact archive

**Files:**
- Create after packing: `release/1.5.0-archive.sha256`
- Modify if required by exact packed results:
  `tests/package/test_archive.py`

**Step 1: Run all local source gates**

Run:

```bash
python -m ruff check .
python -m pytest -q tests/unit
node --test tests/frontend/ratio_preview.test.mjs
node --test tests/frontend/crop_editor.test.mjs
node --test tests/frontend/power_lora_loader.test.mjs
comfy node validate
```

Expected: PASS.

**Step 2: Pack and inspect**

Run:

```bash
comfy node pack
python -m pytest -q tests/package --archive node.zip
```

The first package run should fail only because
`release/1.5.0-archive.sha256` is absent or stale. Use
`tests.package.archive.inspect_archive` and `format_manifest` to record the
sorted hashes for that exact `node.zip`, then rerun the package test.

Do not add `node.zip` to git.

**Step 3: Run packed integration**

Run:

```bash
python -m pytest -q tests/integration \
  --comfy-ref v0.28.0 \
  --archive node.zip \
  --device cpu
```

Expected: PASS. If current supported ComfyUI is available as an exact checkout,
repeat with `--installed-comfyui <path>`.

**Step 4: Perform the manual UI smoke**

Use test LoRAs arranged as:

```text
loras/
  root.safetensors
  characters/
    photo.safetensors
    anime/
      hero.safetensors
```

Verify:

- both nested folders appear;
- `characters` shows both descendants;
- `characters/anime` shows only `hero`;
- `All LoRAs` shows every file;
- changing folders leaves existing rows untouched;
- add, replace, toggle, strengths, reorder, remove, and toggle-all persist
  across workflow reload;
- missing saved folders remain visible without destroying rows;
- missing selected files fail with an actionable `LFGG` error; and
- light/dark themes and supported zoom levels remain legible.

Record any unrun current-version or GPU qualification as a limitation; do not
claim it passed.

**Step 5: Commit the archive manifest**

```bash
git add release/1.5.0-archive.sha256
git commit -m "chore: record 1.5.0 package manifest"
```

Publication, tagging, pushing, and Registry release remain separate,
explicitly approved work.
