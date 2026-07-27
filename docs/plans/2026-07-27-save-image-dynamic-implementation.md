# Save Image Dynamic 1.1.0 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship `LFGG_SaveImageDynamic` as the complete, confined, collision-safe
dynamic PNG saver specified by GitHub issue #16.

**Architecture:** One runtime module contains the V1 adapter and its
standard-library/Pillow helpers. It validates the whole request before writes,
then reserves each relative PNG with exclusive creation and rolls back only
that execution's files. Existing release/package/integration seams are extended
for version `1.1.0`.

**Tech Stack:** Python 3.10–3.13, Torch supplied by ComfyUI, Pillow, pytest,
Ruff, comfy-cli.

---

### Task 1: Parse and render bounded templates

**Files:**
- Create: `tests/unit/test_save_image_dynamic.py`
- Create: `lfgg_nodes/save_image_dynamic.py`

**Step 1: Write failing template tests**

Cover defaults, all seven tokens, literal doubled braces, one supplied
timestamp, zero-based batch, five-digit counter, `unknown_model`, optional
trailing `.png`, illegal-character normalization, Windows reserved names,
empty stems, unknown/malformed fields, conversions/specifications, and the
512/200-character limits.

Use the intended pure seam:

```python
template = ParsedTemplate("runs/{model}/{date}", input_name="path_template")
rendered = template.render(
    model="unknown_model", timestamp=now, width=64, height=32,
    batch=0, counter=1,
)
```

**Step 2: Verify RED**

Run:
`python -m pytest -q tests/unit/test_save_image_dynamic.py -k template`

Expected: fail because the module does not exist.

**Step 3: Implement the minimum parser**

Use `string.Formatter.parse()`. Store only the source and whether it contains
`counter`. Reject unsupported parser output before calling `format()`. Add
small component/stem sanitizers and relative-path rendering in the same module.

**Step 4: Verify GREEN**

Run:
`python -m pytest -q tests/unit/test_save_image_dynamic.py -k template`

Expected: selected tests pass.

**Step 5: Commit**

```bash
git add lfgg_nodes/save_image_dynamic.py tests/unit/test_save_image_dynamic.py
git commit -m "feat: parse bounded save templates"
```

### Task 2: Validate images and metadata

**Files:**
- Modify: `tests/unit/test_save_image_dynamic.py`
- Modify: `lfgg_nodes/save_image_dynamic.py`

**Step 1: Write failing validation tests**

Use real Torch tensors to cover invalid types/ranks/empty axes, non-finite
values, unsupported channels/dtypes, and valid one/three/four-channel batches.
Assert metadata serialization on/off, every extra entry, invalid keys/values,
and values immediately at and above the 64-MiB aggregate boundary.

**Step 2: Verify RED**

Run:
`python -m pytest -q tests/unit/test_save_image_dynamic.py -k "image or metadata"`

Expected: fail because validation helpers are absent.

**Step 3: Implement validation helpers**

Validate without mutation. Serialize JSON once before writes and build one
`PngInfo` object per image from the bounded strings. Convert frames using a
detached CPU float copy, clamp to `[0,1]`, scale to 8-bit, and select `L`,
`RGB`, or `RGBA`.

**Step 4: Verify GREEN**

Run:
`python -m pytest -q tests/unit/test_save_image_dynamic.py -k "image or metadata"`

Expected: selected tests pass.

**Step 5: Commit**

```bash
git add lfgg_nodes/save_image_dynamic.py tests/unit/test_save_image_dynamic.py
git commit -m "feat: validate save images and metadata"
```

### Task 3: Save atomically within the output root

**Files:**
- Modify: `tests/unit/test_save_image_dynamic.py`
- Modify: `lfgg_nodes/save_image_dynamic.py`

**Step 1: Write failing filesystem tests**

Stub only lazy `folder_paths` and global metadata arguments. Cover empty and
nested relative subfolders, absolute/drive/traversal rejection, an existing
symlink escape, exclusive collisions, two simultaneous saves choosing
different files, counter exhaustion, no overwrite, standard relative
descriptors, multi-frame PNG pixels/modes, unchanged inputs, and later-frame
failure rollback that preserves a pre-existing file.

**Step 2: Verify RED**

Run:
`python -m pytest -q tests/unit/test_save_image_dynamic.py -k "save or path or collision or rollback"`

Expected: fail because the node execution path is absent.

**Step 3: Implement the V1 node**

Add the exact `INPUT_TYPES`, `RETURN_TYPES = ()`, `FUNCTION`, `CATEGORY`, and
`OUTPUT_NODE`. Capture one timestamp, preflight all frames, resolve/contain
before and after directory creation, reserve with `Path.open("xb")`, write
through the held handle, and clean the tracked paths on any exception.

**Step 4: Verify GREEN**

Run:
`python -m pytest -q tests/unit/test_save_image_dynamic.py`

Expected: all saver tests pass.

**Step 5: Commit**

```bash
git add lfgg_nodes/save_image_dynamic.py tests/unit/test_save_image_dynamic.py
git commit -m "feat: save confined collision-safe PNGs"
```

### Task 4: Register and publish the 1.1.0 contract

**Files:**
- Modify: `tests/unit/test_contract.py`
- Modify: `__init__.py`
- Modify: `pyproject.toml`
- Create: `release/1.1.0-schema.json`
- Create: `workflows/save_image_dynamic.json`
- Modify: `README.md`

**Step 1: Write failing contract tests**

Assert the fourth registration/display name, exact required/optional/hidden
input order and settings, output-node schema, package version/dependency,
complete `1.1.0` manifest, model-free save workflow, documented writes, and all
manual migration bullets.

**Step 2: Verify RED**

Run:
`python -m pytest -q tests/unit/test_contract.py`

Expected: fail because registration and release artifacts are absent.

**Step 3: Add the synchronized artifacts**

Register only `LFGG_SaveImageDynamic`, update version to `1.1.0`, declare
unbounded `Pillow`, add the full release manifest, and create a workflow using
core `EmptyImage`. Use two saver nodes for metadata on/off and omit counter from
the filename stem so each two-frame batch proves collision advancement.

**Step 4: Verify GREEN**

Run:
`python -m pytest -q tests/unit/test_contract.py`

Expected: pass.

**Step 5: Commit**

```bash
git add __init__.py pyproject.toml README.md release workflows tests/unit/test_contract.py
git commit -m "feat: register dynamic image saver"
```

### Task 5: Extend archive and packed workflow checks

**Files:**
- Modify: `tests/package/test_archive.py`
- Modify: `tests/integration/test_packed_comfyui.py`
- Modify: `tests/integration/harness.py`

**Step 1: Write failing package/integration tests**

Require the saver module and workflow in the archive. Extend the harness result
contract to retain sizing latent checks and additionally report confined PNG
files, modes, sizes, representative pixels, PNG text-key presence, and standard
history descriptors. Add unit-sized harness tests for PNG symlink discovery
and descriptor confinement.

**Step 2: Verify RED**

Run:
`python -m pytest -q tests/integration -k "png or descriptor"`

Expected: fail because the harness handles only latent files.

**Step 3: Extend the existing harness**

Start ComfyUI once, submit both tracked workflows, and inspect `.latent` and
`.png` files beneath the temporary output root. Use Pillow already supplied by
the package dependency. Never include metadata values or absolute paths in the
returned result.

**Step 4: Verify GREEN**

Run:
`python -m pytest -q tests/integration`

Expected: local helper tests pass and environment-dependent tests skip.

**Step 5: Commit**

```bash
git add tests/package/test_archive.py tests/integration
git commit -m "test: qualify packed dynamic image saving"
```

### Task 6: Pack, verify, review, and hand off

**Files:**
- Create: `release/1.1.0-archive.sha256`
- Modify: files above only if a concrete finding requires it

**Step 1: Install the declared dependency**

Run:
`python -m pip install -e ".[dev]"`

Expected: Pillow and development tools are available.

**Step 2: Run local gates**

Run:

```bash
python -m ruff check .
python -m pytest -q tests/unit
comfy node validate
comfy node pack
python -m pytest -q tests/package --archive node.zip
python -m pytest -q tests/integration
```

Then run the packed CPU integration command against `v0.28.0` when the
environment permits. Record unavailable remote Windows/CUDA gates.

**Step 3: Approve the archive manifest**

Generate sorted hashes from the inspected `node.zip`, write
`release/1.1.0-archive.sha256`, repack, and rerun package inspection until the
candidate matches without modifying tracked files.

**Step 4: Review**

Run the repository code-review workflow from commit `f4edee1`. Fix only
concrete issue #16 or repository-standard findings and rerun affected gates.

**Step 5: Refresh context and commit**

Run:
`python3 .codex-context/ctx.py ingest`

Commit the final manifest/docs or review fixes. Report changed files, fresh
checks, unavailable matrix jobs, and that publication remains separately
approved.
