# Aspect Ratio Preview Polish Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use
> superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move the preview grid behind the ratio shape and add descriptive,
display-only aspect-ratio selector labels without changing saved values or the
backend schema.

**Architecture:** Keep the Python node and its combo values unchanged. Extend
the existing build-free ES module: draw one panel-relative grid before any
ratio state, fill the ratio shape opaquely above it, and use the pinned
frontend's `getOptionLabel` hook to map raw combo values to display text.

**Tech Stack:** Plain JavaScript ES modules, Canvas 2D, ComfyUI frontend
`1.45.21`, Node's built-in test runner, pytest package checks.

---

### Task 1: Specify the two frontend behavior changes

**Files:**
- Modify: `tests/frontend/ratio_preview.test.mjs`
- Test: `tests/frontend/ratio_preview.test.mjs`

**Step 1: Record enough canvas operations to verify layering**

Make the recording context retain `fill`, `stroke`, and `clip` calls in
addition to paths and text.

**Step 2: Write the failing grid test**

Replace the internal-grid assertion with checks that:

- detailed drawing emits five vertical and five horizontal lines spanning the
  panel content bounds rather than the selected ratio shape;
- the grid stroke occurs before the ratio shape's opaque fill;
- invalid and dynamic states still emit the same grid;
- low-quality drawing emits no grid or labels.

**Step 3: Write the failing selector-label test**

After `installRatioPreview(node)`, assert that
`aspectRatio.options.getOptionLabel(rawValue)` returns every accepted display
label from the design table while `aspectRatio.value` and callback values
remain raw strings such as `16:9`.

**Step 4: Verify RED**

Run:

```bash
node --test tests/frontend/ratio_preview.test.mjs
```

Expected: FAIL because the current grid follows and clips to the ratio shape,
invalid states omit it, and the combo has no `getOptionLabel`.

### Task 2: Implement the minimum frontend change

**Files:**
- Modify: `web/ratio_preview.mjs`
- Test: `tests/frontend/ratio_preview.test.mjs`

**Step 1: Add the display-only label map**

Add one constant object containing the fourteen accepted raw-value-to-label
mappings. During installation, ensure the ratio widget has an `options` object
and set:

```js
aspectRatio.options.getOptionLabel = (value) =>
  ASPECT_RATIO_LABELS[value] ?? value;
```

Do not modify `aspectRatio.value`, backend options, callbacks, serialization,
or node width.

**Step 2: Draw the grid before state-specific content**

Compute the panel content bounds before checking the state. At normal detail,
draw five vertical and five horizontal lines across those bounds. Then:

- draw neutral state text without a ratio shape;
- for ratio states, fill the fitted shape opaquely with a theme-derived color,
  then stroke it and draw its existing ratio/orientation text;
- do not clip the grid to the ratio shape;
- preserve the existing low-quality outline-only path.

**Step 3: Verify GREEN**

Run:

```bash
node --test tests/frontend/ratio_preview.test.mjs
node --check web/ratio_preview.mjs
```

Expected: PASS.

### Task 3: Refresh release evidence and qualify

**Files:**
- Modify: `README.md`
- Modify: `release/1.2.0-archive.sha256`
- Modify: `docs/plans/2026-07-27-aspect-ratio-preview-design.md`
- Create: `docs/plans/2026-07-27-aspect-ratio-preview-polish-implementation.md`

**Step 1: Update the user-facing preview description**

State that the selector shows common-use descriptions while retaining raw
workflow values, and that the fixed grid sits behind the ratio shape.

**Step 2: Refresh indexed documentation**

Run:

```bash
python3 .codex-context/ctx.py ingest
```

**Step 3: Pack and regenerate the approved manifest**

Run:

```bash
comfy node validate
comfy node pack
python3 -m pytest -q tests/package --archive node.zip
```

The first package test is expected to fail only on changed hashes. Replace
`release/1.2.0-archive.sha256` with the package inspector's sorted manifest and
rerun the package check.

**Step 4: Run full local qualification**

Run:

```bash
node --test tests/frontend/ratio_preview.test.mjs
python3 -m ruff check .
python3 -m pytest -q tests/unit
comfy node validate
comfy node pack
python3 -m pytest -q tests/package --archive node.zip
```

Use `/code-review` against the pre-implementation commit, fix confirmed
findings test-first, rerun affected checks, inspect `git diff --check`, and
commit the scoped implementation.
