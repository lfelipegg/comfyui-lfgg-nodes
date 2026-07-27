# Aspect Ratio Preview Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add the accepted ratio preview and conditional custom-ratio controls
to `LFGG Dimensions by Aspect Ratio` without changing its backend schema or
execution.

**Architecture:** Keep the Python node authoritative and unchanged. A tiny
ComfyUI loader registers documented node lifecycle hooks; one testable ES
module owns derived preview state, canvas drawing, conditional widget
visibility, and node resizing. Existing input widgets remain the only
serialized state.

**Tech Stack:** Plain JavaScript ES modules, Canvas 2D, Node's built-in test
runner, ComfyUI V1 registration, pytest package/contract tests.

---

### Task 1: Specify the frontend behavior in a failing Node test

**Files:**
- Create: `tests/frontend/ratio_preview.test.mjs`
- Create later: `web/ratio_preview.mjs`

**Step 1: Write the failing tests**

Use `node:test` and `node:assert/strict`. Import `previewState`, `fitRatio`, and
`installRatioPreview` from `../../web/ratio_preview.mjs`.

Cover these accepted seams:

- `previewState("Custom", 1920, 1080, false)` returns ratio `16:9` and
  `Landscape`;
- non-positive custom values return `Invalid ratio`;
- a dynamic active ratio returns `Dynamic ratio`;
- `fitRatio` contains landscape and portrait shapes without changing their
  proportions;
- installing the widget inserts a non-serialized 120 px preview immediately
  after `aspect_ratio`;
- presets hide custom widgets without changing their values;
- selecting `Custom` reveals them and recomputes height while retaining width;
- a dynamic `aspect_ratio` reveals custom widgets;
- normal drawing emits the internal grid while low-quality drawing omits it.

Use one small fake node and recording canvas context, not a browser framework.

**Step 2: Verify RED**

Run:

```bash
node --test tests/frontend/ratio_preview.test.mjs
```

Expected: FAIL because `web/ratio_preview.mjs` does not exist.

### Task 2: Implement the smallest testable ratio-preview module

**Files:**
- Create: `web/ratio_preview.mjs`
- Test: `tests/frontend/ratio_preview.test.mjs`

**Step 1: Add pure derived-state and geometry functions**

Implement:

```js
export function previewState(
  aspectRatio,
  customWidth,
  customHeight,
  dynamic = false
)
```

Return a tagged state for `ratio`, `invalid`, or `dynamic`. Parse presets from
their `W:H` value; reduce custom components with Euclid's greatest common
divisor; derive `Landscape`, `Portrait`, or `Square`.

Implement:

```js
export function fitRatio(ratioWidth, ratioHeight, bounds)
```

Use one `Math.min` scale and return a centered `{ x, y, width, height }`.

**Step 2: Add one instance installer**

Implement:

```js
export function installRatioPreview(node, { allowShrink = false } = {})
```

Return immediately for other node IDs or an already installed node. Find the
five existing widgets by name, add one custom widget with
`serialize: false`, `options.serialize: false`, and
`computeSize: () => [0, 120]`, then move it directly after `aspect_ratio`.

Compose—never discard—the three ratio widget callbacks and
`node.onConnectionsChange`. On each relevant change:

- detect active graph-connected ratio inputs by existing input names and links;
- set `custom_ratio_width.hidden` and `custom_ratio_height.hidden`;
- retain their values;
- preserve node width;
- use computed minimum height, shrinking only for an editor interaction;
- mark the canvas dirty.

**Step 3: Draw the accepted preview**

Draw a theme-aware panel and centered, contained ratio shape. Use native Canvas
2D paths and `roundRect` with 6 px corners. Clip five vertical and five
horizontal internal lines to create the 6×6 grid. Center the simplified ratio
and smaller orientation label; refit the shape with a caption reserve when
they cannot fit. Draw neutral invalid/dynamic labels. At low-quality zoom,
draw only the ratio outline.

Read LiteGraph theme constants when available and use neutral fallbacks. Do
not install timers, routes, DOM widgets, or global patches.

**Step 4: Verify GREEN**

Run:

```bash
node --test tests/frontend/ratio_preview.test.mjs
```

Expected: PASS.

### Task 3: Register and package the browser extension test-first

**Files:**
- Create: `web/ratio_preview.js`
- Modify: `__init__.py`
- Modify: `tests/unit/test_contract.py`

**Step 1: Extend the failing contract test**

Require:

```python
assert package.WEB_DIRECTORY == "./web"
assert package.__all__ == [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]
```

Run:

```bash
python3 -m pytest -q tests/unit/test_contract.py::test_v1_registration_and_aspect_ratio_schema_are_exact
```

Expected: FAIL because `WEB_DIRECTORY` is absent.

**Step 2: Export the frontend directory**

Add `WEB_DIRECTORY = "./web"` to the registration-only root `__init__.py` and
include it in `__all__`. Do not change node mappings or schemas.

**Step 3: Add the loader**

`web/ratio_preview.js` imports `app` from `../../scripts/app.js` and
`installRatioPreview` locally. Register the unique extension name
`lfgg.dimensionsByAspectRatio.preview`.

Use only:

- `nodeCreated(node)` to install on new instances; and
- `loadedGraphNode(node)` to resync loaded values without shrinking saved
  height.

**Step 4: Verify GREEN and syntax**

Run:

```bash
python3 -m pytest -q tests/unit/test_contract.py::test_v1_registration_and_aspect_ratio_schema_are_exact
node --check web/ratio_preview.js
node --test tests/frontend/ratio_preview.test.mjs
```

Expected: all pass.

### Task 4: Update the compatible 1.2.0 package contract test-first

**Files:**
- Modify: `tests/unit/test_contract.py`
- Modify: `pyproject.toml`
- Create: `release/1.2.0-schema.json`
- Modify: `tests/integration/test_packed_comfyui.py`

**Step 1: Change contract expectations first**

Expect package version `1.2.0`, schema manifest
`release/1.2.0-schema.json`, and dependencies:

```python
["Pillow", "comfyui-frontend-package>=1.45.21"]
```

Keep `[tool.comfy].requires-comfyui = ">=0.28.0"` and assert the generated
expected node schema is byte-for-behavior identical apart from manifest
version.

Run the focused contract test and verify it fails on the old metadata.

**Step 2: Update metadata and schema**

Bump `pyproject.toml` to `1.2.0`, add the frontend compatibility pseudo
dependency, and copy the prior schema manifest to `1.2.0` with only its
top-level version changed.

Point both packed and installed integration tests to the `1.2.0` schema.

**Step 3: Verify GREEN**

Run:

```bash
python3 -m pytest -q tests/unit/test_contract.py::test_metadata_manifest_and_workflow_match_the_release_contract
python3 -m pytest -q tests/integration/test_packed_comfyui.py
```

Expected: focused contract passes; integration collection/unit portions pass
and environment-requiring cases skip.

### Task 5: Update package and CI gates test-first

**Files:**
- Modify: `tests/package/test_archive.py`
- Modify: `.github/workflows/qualify.yml`
- Modify: `tests/unit/test_release_workflows.py`
- Create after packing: `release/1.2.0-archive.sha256`

**Step 1: Change failing package expectations**

Add `web/ratio_preview.js` and `web/ratio_preview.mjs` to `EXPECTED_PATHS` and
point the approved content manifest at `1.2.0-archive.sha256`.

Require the qualification workflow to run:

```yaml
- run: node --test tests/frontend/ratio_preview.test.mjs
```

Run the focused workflow and package tests and verify the old files fail.

**Step 2: Add the frontend check to CI**

Run the dependency-free Node test in the existing unit matrix. Do not add npm,
a package manifest, a lockfile, or an asset build.

**Step 3: Pack and record the approved candidate**

Run:

```bash
comfy node validate
comfy node pack
python3 -m pytest -q tests/package --archive node.zip
```

Use the package inspector's sorted content-manifest format to create
`release/1.2.0-archive.sha256`, then rerun the package test.

Expected: PASS with exactly the two handwritten frontend assets added.

### Task 6: Synchronize user and release documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/research/package-verification-and-distribution-contract.md`
- Modify: `.github/workflows/release.yml`
- Modify: `tests/unit/test_release_workflows.py`

**Step 1: Update assertions first**

Require README claims for the ratio preview, conditional custom controls,
frontend `>=1.45.21`, build-free browser assets, and
`node --test tests/frontend/ratio_preview.test.mjs`.

Require the release changelog:

```text
Add the aspect-ratio preview and conditional custom-ratio controls.
```

Run focused tests and verify failure on the old text.

**Step 2: Update documentation and release text**

Describe the preview as requested-ratio-only and progressive enhancement.
Replace statements that the pack is Python-only or has no frontend. Preserve
the no-generated-build claim. Add the frontend test to canonical local gates,
package expectations, compatibility metadata, and release-readiness checks.

Update the tag release changelog without changing security boundaries.

**Step 3: Refresh indexed context and verify**

Run:

```bash
python3 .codex-context/ctx.py ingest
python3 -m pytest -q tests/unit/test_contract.py tests/unit/test_release_workflows.py
```

Expected: PASS.

### Task 7: Full verification, review, and commit

**Files:**
- Review every changed file

**Step 1: Run canonical local gates**

```bash
node --test tests/frontend/ratio_preview.test.mjs
python3 -m ruff check .
python3 -m pytest -q tests/unit
comfy node validate
comfy node pack
python3 -m pytest -q tests/package --archive node.zip
```

Run the packed ComfyUI integration command at `v0.28.0` when the environment
can provision it. Never claim an unavailable gate passed.

**Step 2: Perform the requested code review**

Use `/code-review` against the pre-implementation commit. Fix every confirmed
finding test-first and rerun affected gates.

**Step 3: Inspect and commit**

Run `git diff --check`, inspect `git diff` and `git status --short`, then commit
the scoped change:

```bash
git add CONTEXT.md __init__.py pyproject.toml README.md web tests release \
  docs/plans docs/research/package-verification-and-distribution-contract.md \
  .github/workflows
git commit -m "feat: add aspect ratio preview"
```
