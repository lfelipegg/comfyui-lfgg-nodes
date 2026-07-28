# Load and Crop Image Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `LFGG Load and Crop Image`, a secure still-image loader with a
persisted, exact-ratio interactive crop frame and cropped `IMAGE`/`MASK`
outputs.

**Architecture:** Keep crop geometry as pure functions in the node module, with
a thin V1 adapter for ComfyUI file, Pillow, tensor, and UI-envelope boundaries.
Add one build-free canvas-widget loader and one testable ES module; use native
input upload/view behavior and normal execution UI data rather than routes.

**Tech Stack:** Python 3.10+, ComfyUI V1 nodes, Pillow, NumPy and Torch supplied
by ComfyUI, handwritten ES modules, `pytest`, and `node:test`.

---

Implementation baseline: commit `c0369f7`. Before editing, use
`@superpowers:using-git-worktrees` to create an isolated worktree. Execute each
behavior test-first with `@superpowers:test-driven-development`, and finish
with `@superpowers:verification-before-completion`.

The accepted behavior is
`docs/plans/2026-07-28-load-and-crop-image-design.md`. Do not broaden it to
animated files, connected images, URLs, arbitrary paths, resampling,
composition grids, routes, a DOM editor, or a reusable crop framework.

### Task 1: Specify and implement exact crop geometry

**Files:**
- Create: `tests/unit/test_load_and_crop_image.py`
- Create: `lfgg_nodes/load_and_crop_image.py`

**Step 1: Write the failing pure-geometry tests**

Start `tests/unit/test_load_and_crop_image.py` without importing ComfyUI:

```python
import pytest

from lfgg_nodes.load_and_crop_image import resolve_crop


def test_initializes_the_largest_centered_exact_ratio_crop():
    assert resolve_crop(
        source_width=1920,
        source_height=1080,
        ratio_width=4,
        ratio_height=5,
        crop_x=0,
        crop_y=0,
        crop_width=0,
        crop_height=0,
        max_resolution=16_384,
    ) == (528, 0, 864, 1080, 4, 5)


def test_reduces_ratio_components_before_fitting():
    assert resolve_crop(
        source_width=1920,
        source_height=1080,
        ratio_width=1920,
        ratio_height=1080,
        crop_x=160,
        crop_y=90,
        crop_width=1600,
        crop_height=900,
        max_resolution=16_384,
    ) == (160, 90, 1600, 900, 16, 9)


def test_changed_ratio_resets_instead_of_reusing_stale_geometry():
    assert resolve_crop(
        source_width=1920,
        source_height=1080,
        ratio_width=4,
        ratio_height=3,
        crop_x=160,
        crop_y=90,
        crop_width=1600,
        crop_height=900,
        max_resolution=16_384,
    ) == (240, 0, 1440, 1080, 4, 3)


def test_matching_ratio_rejects_out_of_bounds_geometry():
    with pytest.raises(ValueError, match="inside the source image"):
        resolve_crop(
            source_width=100,
            source_height=100,
            ratio_width=1,
            ratio_height=1,
            crop_x=50,
            crop_y=50,
            crop_width=60,
            crop_height=60,
            max_resolution=16_384,
        )


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"source_width": 0}, "source_width"),
        ({"ratio_width": 0}, "ratio_width"),
        ({"ratio_width": True}, "ratio_width"),
        ({"crop_width": 0, "crop_height": 1}, "crop dimensions"),
        ({"ratio_width": 101, "ratio_height": 1}, "does not fit"),
    ],
)
def test_rejects_invalid_or_impossible_geometry(arguments, message):
    values = {
        "source_width": 100,
        "source_height": 100,
        "ratio_width": 1,
        "ratio_height": 1,
        "crop_x": 0,
        "crop_y": 0,
        "crop_width": 100,
        "crop_height": 100,
        "max_resolution": 16_384,
    }
    values.update(arguments)

    with pytest.raises(ValueError, match=message):
        resolve_crop(**values)
```

Add focused cases for negative coordinates, a non-integer coordinate, a side
above `max_resolution`, and deterministic odd-pixel centering.

**Step 2: Run the focused test and verify RED**

Run:

```bash
python -m pytest -q tests/unit/test_load_and_crop_image.py
```

Expected: collection fails because `lfgg_nodes.load_and_crop_image` does not
exist.

**Step 3: Implement the minimum pure geometry**

In `lfgg_nodes/load_and_crop_image.py`, import only standard-library modules at
module load:

```python
from math import gcd

from .sizing import _bounded_int


def _largest_centered_crop(source_width, source_height, ratio_width, ratio_height):
    scale = min(source_width // ratio_width, source_height // ratio_height)
    if scale < 1:
        raise ValueError("crop ratio does not fit inside the source image")
    width = scale * ratio_width
    height = scale * ratio_height
    return (
        (source_width - width) // 2,
        (source_height - height) // 2,
        width,
        height,
    )


def resolve_crop(
    *,
    source_width,
    source_height,
    ratio_width,
    ratio_height,
    crop_x,
    crop_y,
    crop_width,
    crop_height,
    max_resolution,
):
    _bounded_int("source_width", source_width, 1, max_resolution)
    _bounded_int("source_height", source_height, 1, max_resolution)
    _bounded_int("ratio_width", ratio_width, 1, max_resolution)
    _bounded_int("ratio_height", ratio_height, 1, max_resolution)
    _bounded_int("crop_x", crop_x, 0, max_resolution)
    _bounded_int("crop_y", crop_y, 0, max_resolution)
    _bounded_int("crop_width", crop_width, 0, max_resolution)
    _bounded_int("crop_height", crop_height, 0, max_resolution)

    divisor = gcd(ratio_width, ratio_height)
    reduced_width = ratio_width // divisor
    reduced_height = ratio_height // divisor
    largest = _largest_centered_crop(
        source_width,
        source_height,
        reduced_width,
        reduced_height,
    )

    if crop_width == crop_height == 0:
        return (*largest, reduced_width, reduced_height)
    if crop_width < 1 or crop_height < 1:
        raise ValueError("crop dimensions must both be zero or both be positive")
    if crop_width * reduced_height != crop_height * reduced_width:
        return (*largest, reduced_width, reduced_height)
    if (
        crop_x + crop_width > source_width
        or crop_y + crop_height > source_height
    ):
        raise ValueError("crop rectangle must stay inside the source image")
    return (
        crop_x,
        crop_y,
        crop_width,
        crop_height,
        reduced_width,
        reduced_height,
    )
```

Do not add a rectangle class, generic validator, float coordinates, or a
configurable snapping policy.

**Step 4: Run the focused tests and verify GREEN**

Run:

```bash
python -m pytest -q tests/unit/test_load_and_crop_image.py
python -m ruff check lfgg_nodes/load_and_crop_image.py tests/unit/test_load_and_crop_image.py
```

Expected: PASS.

**Step 5: Commit**

```bash
git add lfgg_nodes/load_and_crop_image.py tests/unit/test_load_and_crop_image.py
git commit -m "feat: add exact crop geometry"
```

### Task 2: Load one safe input image and crop image plus mask

**Files:**
- Modify: `tests/unit/test_load_and_crop_image.py`
- Modify: `lfgg_nodes/load_and_crop_image.py`

**Step 1: Add failing file, tensor, and trust-boundary tests**

Add fixtures that stub only the ComfyUI boundary:

```python
import sys
from types import SimpleNamespace

import torch
from PIL import Image


def install_folder_paths(monkeypatch, input_root):
    module = SimpleNamespace(
        get_input_directory=lambda: str(input_root),
        get_annotated_filepath=lambda name: str(input_root / name),
    )
    monkeypatch.setitem(sys.modules, "folder_paths", module)


def test_loads_orients_and_crops_rgba_image(monkeypatch, tmp_path):
    pixels = Image.new("RGBA", (4, 3), (10, 20, 30, 255))
    pixels.putpixel((0, 0), (100, 110, 120, 0))
    pixels.save(tmp_path / "source.png")
    install_folder_paths(monkeypatch, tmp_path)

    result = LoadAndCropImage().load_and_crop(
        image="source.png",
        ratio_width=1,
        ratio_height=1,
        crop_x=0,
        crop_y=0,
        crop_width=0,
        crop_height=0,
    )

    image, mask = result["result"]
    assert image.shape == (1, 3, 3, 3)
    assert mask.shape == (1, 3, 3)
    assert image.dtype == torch.float32
    assert mask.dtype == torch.float32
    assert torch.allclose(image[0, 0, 0], torch.tensor([100, 110, 120]) / 255)
    assert mask[0, 0, 0].item() == pytest.approx(1.0)
    assert result["ui"]["crop"] == [
        {
            "ratio_width": 1,
            "ratio_height": 1,
            "x": 0,
            "y": 0,
            "width": 3,
            "height": 3,
        }
    ]
```

Also add one focused test for each non-trivial boundary:

- RGB input produces a zero mask matching the crop dimensions.
- EXIF orientation is applied before coordinates are interpreted.
- an animated GIF with two frames raises `ValueError` containing
  `single still image`;
- an image above the hard axis/pixel limit fails before tensor allocation;
- a corrupt file raises an actionable error;
- a path resolving outside the input root, including a symlink when supported,
  raises `ValueError` containing `ComfyUI input directory`;
- `IS_CHANGED` changes after the selected file content changes; and
- `VALIDATE_INPUTS` returns an explanatory string for an invalid path and
  `True` for a valid input.

Use a small monkeypatched limit in the oversized-image test; never allocate a
large fixture.

**Step 2: Run the focused tests and verify RED**

Run:

```bash
python -m pytest -q tests/unit/test_load_and_crop_image.py
```

Expected: failures because the node adapter and file helpers are absent.

**Step 3: Implement safe loading and direct tensor slicing**

Add small boundary helpers to the same module:

```python
def _input_path(image):
    from pathlib import Path

    import folder_paths

    try:
        root = Path(folder_paths.get_input_directory()).resolve(strict=True)
        path = Path(folder_paths.get_annotated_filepath(image)).resolve(strict=True)
    except (OSError, TypeError):
        raise ValueError("selected image is unavailable") from None
    if not root.is_dir() or not path.is_file() or not path.is_relative_to(root):
        raise ValueError("selected image must stay inside the ComfyUI input directory")
    return path


def _content_hash(path):
    from hashlib import sha256

    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
```

In `LoadAndCropImage.load_and_crop`, import Pillow, NumPy, and Torch lazily.
Open the already-confined path as a binary file, reject
`getattr(source, "n_frames", 1) != 1`, apply `ImageOps.exif_transpose`, then
check positive dimensions, both axes against `nodes.MAX_RESOLUTION`, and the
decoded pixel count against the pack's existing `16_384**2` hard ceiling.
Treat Pillow decompression-bomb warnings/errors as invalid input.

Convert the oriented image once:

```python
rgb = torch.from_numpy(
    np.array(oriented.convert("RGB"), dtype=np.float32, copy=True) / 255.0
).unsqueeze(0)
if "A" in oriented.getbands():
    alpha = torch.from_numpy(
        np.array(
            oriented.getchannel("A"),
            dtype=np.float32,
            copy=True,
        )
        / 255.0
    )
    mask = (1.0 - alpha).unsqueeze(0)
else:
    mask = torch.zeros((1, height, width), dtype=torch.float32)
```

Resolve the frame with `resolve_crop`, slice:

```python
cropped_image = rgb[:, y : y + crop_height, x : x + crop_width, :]
cropped_mask = mask[:, y : y + crop_height, x : x + crop_width]
```

Return only small UI data plus graph outputs:

```python
return {
    "ui": {
        "crop": [
            {
                "ratio_width": reduced_width,
                "ratio_height": reduced_height,
                "x": x,
                "y": y,
                "width": crop_width,
                "height": crop_height,
            }
        ]
    },
    "result": (cropped_image, cropped_mask),
}
```

Implement `IS_CHANGED` with `_content_hash(_input_path(image))`.
`VALIDATE_INPUTS` catches `ValueError` from `_input_path` and returns its
message. Do not validate connected ratios in `VALIDATE_INPUTS`; runtime
validation owns resolved values.

**Step 4: Run focused checks and verify GREEN**

Run:

```bash
python -m pytest -q tests/unit/test_load_and_crop_image.py
python -m ruff check lfgg_nodes/load_and_crop_image.py tests/unit/test_load_and_crop_image.py
```

Expected: PASS.

**Step 5: Commit**

```bash
git add lfgg_nodes/load_and_crop_image.py tests/unit/test_load_and_crop_image.py
git commit -m "feat: load and crop still images safely"
```

### Task 3: Fix the V1 schema and registration contract

**Files:**
- Modify: `tests/unit/test_contract.py`
- Modify: `lfgg_nodes/load_and_crop_image.py`
- Modify: `__init__.py`

**Step 1: Write failing exact-schema assertions**

Extend `load_root_package`'s `folder_paths` stub so `INPUT_TYPES` can enumerate
a temporary input root. Add exact assertions for:

```python
assert package.NODE_DISPLAY_NAME_MAPPINGS[
    "LFGG_LoadAndCropImage"
] == "LFGG Load and Crop Image"

node = package.NODE_CLASS_MAPPINGS["LFGG_LoadAndCropImage"]
assert node.CATEGORY == "LFGG/image"
assert node.FUNCTION == "load_and_crop"
assert node.RETURN_TYPES == ("IMAGE", "MASK")
assert node.RETURN_NAMES == ("image", "mask")
assert node.OUTPUT_TOOLTIPS == (
    "Selected source region without resampling.",
    "Alpha-derived mask cropped to the same region.",
)
```

Require the exact required-input order:

```python
[
    "image",
    "ratio_width",
    "ratio_height",
    "crop_x",
    "crop_y",
    "crop_width",
    "crop_height",
]
```

The `image` entry must be a modern `COMBO` with sorted relative input
filenames, `image_upload: True`, and `allow_batch: False`. Ratio components are
`INT`, default/min `1`, max `nodes.MAX_RESOLUTION`. Crop coordinates/dimensions
are `INT`, default/min `0`, max `nodes.MAX_RESOLUTION`; their tooltips must
state source-pixel meaning and the zero-size initialization behavior.

Assert module import does not import `folder_paths`, open a file, or mutate the
input directory.

**Step 2: Run the schema tests and verify RED**

Run:

```bash
python -m pytest -q tests/unit/test_contract.py
```

Expected: failure because the new node is not registered and has no schema.

**Step 3: Add the V1 schema and registration**

Implement `INPUT_TYPES` with a standard-library recursive input listing that
does not follow escaped symlinks. Keep imports inside `INPUT_TYPES`:

```python
@classmethod
def INPUT_TYPES(cls):
    from pathlib import Path

    import folder_paths
    from nodes import MAX_RESOLUTION

    root = Path(folder_paths.get_input_directory()).resolve()
    images = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.resolve().is_relative_to(root)
    )
    return {
        "required": {
            "image": (
                "COMBO",
                {
                    "options": images,
                    "image_upload": True,
                    "allow_batch": False,
                    "tooltip": "Still image beneath the ComfyUI input directory.",
                },
            ),
            # Add the six exact INT declarations tested above.
        }
    }
```

Set the accepted description, returns, function, and category. Import and
register the class once in root `__init__.py`; preserve duplicate rejection,
registration-only behavior, V1-only registration, and `WEB_DIRECTORY`.

Do not subclass or monkey-patch core `LoadImage`.

**Step 4: Run contract and backend tests**

Run:

```bash
python -m pytest -q tests/unit/test_contract.py tests/unit/test_load_and_crop_image.py
```

Expected: PASS except for release-manifest assertions intentionally updated in
Task 6. If the monolithic contract test prevents this separation, update only
its expected node schema now and leave version/workflow assertions at `1.2.0`
until Task 6.

**Step 5: Commit**

```bash
git add __init__.py lfgg_nodes/load_and_crop_image.py tests/unit/test_contract.py
git commit -m "feat: register load and crop image node"
```

### Task 4: Specify and implement pure frontend crop state

**Files:**
- Create: `tests/frontend/crop_editor.test.mjs`
- Create: `web/crop_editor.mjs`
- Modify: `web/ratio_preview.mjs`

**Step 1: Write failing dependency-free state tests**

Use `node:test` and `node:assert/strict`. Cover:

```javascript
import {
  fitPreviewImage,
  initializeFrame,
  moveFrame,
  normalizeTypedFrame,
  resizeFrame,
  resolveStaticInt,
} from "../../web/crop_editor.mjs";

test("initializes the largest centered exact frame", () => {
  assert.deepEqual(initializeFrame(1920, 1080, 4, 5), {
    x: 528,
    y: 0,
    width: 864,
    height: 1080,
    ratioWidth: 4,
    ratioHeight: 5,
  });
});

test("contains the source image in a bounded preview", () => {
  assert.deepEqual(
    fitPreviewImage(1920, 1080, { x: 8, y: 10, width: 320, height: 360 }),
    { x: 8, y: 100, width: 320, height: 180 },
  );
});

test("moves and clamps in source pixels", () => {
  assert.deepEqual(
    moveFrame(
      { x: 10, y: 10, width: 40, height: 20 },
      100,
      -100,
      80,
      60,
    ),
    { x: 40, y: 0, width: 40, height: 20 },
  );
});
```

Add focused tests for:

- typed width snapping to the nearest positive ratio scale;
- typed X/Y clamping after size normalization;
- all four corner resizes keeping the opposite corner fixed;
- resize clamping at every source boundary;
- reduced `1920:1080` becoming `16:9`;
- invalid and ratio-does-not-fit states;
- a local widget integer resolving immediately;
- a `PrimitiveNode` integer resolving through one or more `Reroute` nodes;
- an arbitrary computed origin returning unresolved; and
- a visited-node guard preventing reroute cycles.

Use tiny fake graph/link/node objects; do not import ComfyUI or a DOM emulator.

**Step 2: Run and verify RED**

Run:

```bash
node --test tests/frontend/crop_editor.test.mjs
```

Expected: failure because `web/crop_editor.mjs` does not exist.

**Step 3: Export the one existing reusable ratio helper**

Change only:

```javascript
export function greatestCommonDivisor(left, right) {
```

in `web/ratio_preview.mjs`. Keep its implementation and existing behavior
unchanged.

**Step 4: Implement the pure crop functions**

Import `fitRatio` and `greatestCommonDivisor` from `ratio_preview.mjs`.
Represent frames as plain objects. Use integer source coordinates only.

For a corner resize:

1. derive the fixed opposite anchor;
2. derive horizontal and vertical drag signs;
3. convert pointer distances to ratio scales;
4. choose `Math.max(1, Math.round(Math.min(xScale, yScale)))`;
5. cap scale by the source distance available from the anchor; and
6. rebuild X/Y/width/height from the anchor and reduced ratio.

`normalizeTypedFrame` rounds requested width to the nearest positive ratio
scale, caps it by the source dimensions, then clamps X and Y.

`resolveStaticInt` returns a tagged result:

```javascript
{ kind: "value", value: 4 }
{ kind: "unresolved" }
{ kind: "invalid" }
```

It may read:

- the local named widget when unlinked; or
- the first numeric widget of an origin whose exact type is
  `PrimitiveNode`, following exact `Reroute` nodes with a visited set.

It must not infer the output of any other node type.

**Step 5: Run pure frontend checks and verify GREEN**

Run:

```bash
node --test tests/frontend/ratio_preview.test.mjs tests/frontend/crop_editor.test.mjs
node --check web/crop_editor.mjs
```

Expected: PASS.

**Step 6: Commit**

```bash
git add web/ratio_preview.mjs web/crop_editor.mjs tests/frontend/crop_editor.test.mjs
git commit -m "feat: add crop editor state"
```

### Task 5: Install, draw, and interact with the canvas crop widget

**Files:**
- Modify: `tests/frontend/crop_editor.test.mjs`
- Modify: `web/crop_editor.mjs`
- Create: `web/crop_editor.js`

**Step 1: Add failing installer and interaction tests**

Build one fake `LFGG_LoadAndCropImage` node with the seven persisted widgets,
custom-widget insertion, graph links, callbacks, `setSize`, `setDirtyCanvas`,
serialization, connection, and execution hooks.

Assert:

- unrelated or incomplete nodes are ignored;
- installation is idempotent;
- the custom widget is inserted directly after the image selector and has
  `serialize = false`;
- its computed height is 360 pixels and saved node width is preserved;
- selecting/loading an image initializes the frame and synchronizes all four
  crop widgets;
- numeric edits normalize once without recursive callbacks;
- ratio widget edits reset immediately;
- constant links reset immediately and computed links show
  `Run to resolve connected ratio`;
- `onExecuted({crop: [...]})` applies the resolved ratio/frame;
- connecting to ratio widgets remains allowed;
- connecting to crop X/Y/width/height is refused;
- pointer-down inside the frame moves it;
- pointer-down on each handle resizes it;
- low-quality drawing omits handles and labels;
- normal drawing dims only the outside, outlines the frame, draws four
  handles, and labels exact dimensions;
- serialization keeps exactly the seven persisted widget values in order; and
- missing JavaScript leaves backend widgets untouched by definition.

Inject `createImage`, `buildViewUrl`, and `getGraph` into the installer so tests
do not need browser globals.

**Step 2: Run and verify RED**

Run:

```bash
node --test tests/frontend/crop_editor.test.mjs
```

Expected: failures because installation/drawing/pointer behavior is absent.

**Step 3: Implement the smallest node-specific controller**

In `web/crop_editor.mjs`:

- bind only when `node.comfyClass === "LFGG_LoadAndCropImage"`;
- locate all seven widgets by exact name;
- mark crop height disabled/read-only;
- compose existing widget callbacks and node hooks rather than replacing their
  effects;
- create one non-serialized widget with `computeSize`, `draw`, and
  `onPointerDown`;
- load the selected input through the injected `/view` URL builder;
- store browser image dimensions and a source-pixel frame in the controller;
- map source coordinates to the contained preview rectangle during drawing;
- hit-test fixed-size corner handles before the frame interior;
- use the frontend's pointer lifecycle (`onDragStart`, `onDrag`,
  `onDragEnd`, and `finally`) and return `true` only for handled gestures;
- dirty the canvas and synchronize widgets after each accepted state change;
- preserve workflow node width and avoid shrinking height while
  `app.configuringGraph` is true;
- clear the core input preview after the image selector callback so the
  dedicated widget is the only preview; and
- retain the same skipped-mid-widget serialization workaround already proven
  by `ratio_preview.mjs`.

Use theme values from `globalThis.LiteGraph` with neutral fallbacks. Draw the
selected image first, then four outside dim rectangles, frame border, handles,
and `width × height`. Do not add a grid or fixed palette.

Compose `node.onConnectInput` and reject only exact crop-state input names.
Compose `node.onExecuted` and accept only a bounded object from
`message.crop?.[0]`; normalize through the same pure state path before changing
widgets.

**Step 4: Register the loader**

Create `web/crop_editor.js`:

```javascript
import { api } from "../../scripts/api.js";
import { app } from "../../scripts/app.js";
import { installCropEditor } from "./crop_editor.mjs";

const buildViewUrl = (value) => {
  const normalized = String(value).replace(/\s+\[input\]$/, "").replaceAll("\\", "/");
  const slash = normalized.lastIndexOf("/");
  const query = new URLSearchParams({
    filename: normalized.slice(slash + 1),
    subfolder: slash < 0 ? "" : normalized.slice(0, slash),
    type: "input",
  });
  return api.apiURL(`/view?${query}`);
};

const install = (node) =>
  installCropEditor(node, {
    buildViewUrl,
    getGraph: () => app.graph,
    isConfiguring: () => app.configuringGraph,
  });

app.registerExtension({
  name: "lfgg.loadAndCropImage.editor",
  nodeCreated: install,
  loadedGraphNode: install,
});
```

If the pinned frontend represents annotated input names differently, adjust
only `buildViewUrl` and its focused tests. Do not add a route.

**Step 5: Run frontend checks and verify GREEN**

Run:

```bash
node --test tests/frontend/ratio_preview.test.mjs tests/frontend/crop_editor.test.mjs
node --check web/ratio_preview.js
node --check web/ratio_preview.mjs
node --check web/crop_editor.js
node --check web/crop_editor.mjs
```

Expected: PASS.

**Step 6: Commit**

```bash
git add web/crop_editor.js web/crop_editor.mjs tests/frontend/crop_editor.test.mjs
git commit -m "feat: add interactive crop canvas"
```

### Task 6: Add the 1.3.0 workflow and release contract

**Files:**
- Modify: `tests/unit/test_contract.py`
- Modify: `tests/integration/harness.py`
- Modify: `tests/integration/test_packed_comfyui.py`
- Modify: `tests/package/test_archive.py`
- Modify: `tests/unit/test_release_workflows.py`
- Create: `workflows/load_and_crop_image.json`
- Create: `release/1.3.0-schema.json`
- Modify: `pyproject.toml`
- Modify: `.github/workflows/qualify.yml`
- Modify: `.github/workflows/release.yml`
- Modify: `README.md`

**Step 1: Write failing synchronized contract assertions**

Update the monolithic release contract to require:

- package version and schema version `1.3.0`;
- all five registered IDs and exact new schema;
- `workflows/load_and_crop_image.json`;
- both crop frontend files in the packed path set;
- both frontend test files in qualification;
- a release changelog of
  `Add LFGG Load and Crop Image with an interactive exact-ratio crop frame.`;
- README node, file-read, still-image, alpha-mask, dynamic-ratio, fallback,
  and no-resampling claims; and
- unchanged dependency and compatibility floors.

Run:

```bash
python -m pytest -q tests/unit/test_contract.py tests/unit/test_release_workflows.py
```

Expected: FAIL on the old version, missing workflow/manifest, CI command, and
documentation.

**Step 2: Add a deterministic integration fixture and workflow**

In `tests/integration/harness.py`, create one small RGBA input beneath the
already-confined temporary input root before starting ComfyUI:

```python
fixture = Image.new("RGBA", (6, 4), (10, 20, 30, 255))
fixture.putpixel((1, 0), (100, 110, 120, 0))
fixture.save(input_directory / "lfgg_crop_fixture.png")
```

Create `workflows/load_and_crop_image.json` with:

1. `LFGG_LoadAndCropImage`, image `lfgg_crop_fixture.png`, ratio `1:1`,
   crop `(1, 0, 4, 4)`;
2. `LFGG_SaveImageDynamic` saving output 0 beneath `lfgg/crop` as
   `image`; and
3. native `MaskToImage` consuming output 1, followed by another
   `LFGG_SaveImageDynamic` saving `mask`.

Extend `release_workflows()` and result assertions. Verify both PNGs are
`4×4`, the image's first pixel is `[100, 110, 120]`, and the mask image's
first pixel represents the fully transparent source pixel under ComfyUI's
mask convention. Keep output descriptor confinement checks unchanged.

Run unit-only integration tests:

```bash
python -m pytest -q tests/integration/test_packed_comfyui.py
```

Expected: local harness tests pass and environment-dependent executions skip.

**Step 3: Synchronize package metadata, schema, docs, and CI**

- Bump only `project.version` to `1.3.0`.
- Generate `release/1.3.0-schema.json` from the exact registered V1 schemas;
  do not hand-diverge it from `/object_info`.
- Update README compatibility wording from `1.2.0` to `1.3.0`, add the node
  table row and accepted limits, describe its input-file read and no writes,
  and list both frontend test commands.
- Update qualification to run both dependency-free frontend test files.
- Update only the release changelog in `.github/workflows/release.yml`;
  preserve its tag, environment, token, immutable publication, download, and
  installed-version checks.
- Add the node module, both crop frontend files, and crop workflow to package
  `EXPECTED_PATHS`; point archive expectations at
  `release/1.3.0-archive.sha256`.

Do not change dependencies, compatibility floors, publication authority, or
add npm metadata.

**Step 4: Run focused contract checks**

Run:

```bash
node --test tests/frontend/ratio_preview.test.mjs tests/frontend/crop_editor.test.mjs
python -m pytest -q tests/unit/test_contract.py tests/unit/test_release_workflows.py
python -m pytest -q tests/integration/test_packed_comfyui.py
```

Expected: PASS, with only environment-requiring integration cases skipped.

**Step 5: Commit**

```bash
git add __init__.py pyproject.toml README.md web workflows release \
  tests/unit tests/frontend tests/integration tests/package \
  .github/workflows
git commit -m "build: define load and crop image release"
```

### Task 7: Pack, record the archive, and qualify without publishing

**Files:**
- Create: `release/1.3.0-archive.sha256`
- Modify only if verification finds a defect: files already in scope

**Step 1: Run all source checks**

Run:

```bash
node --test tests/frontend/ratio_preview.test.mjs tests/frontend/crop_editor.test.mjs
python -m ruff check .
python -m pytest -q tests/unit
python -m pytest -q tests/integration/test_packed_comfyui.py
comfy node validate
```

Expected: PASS; integration executions without explicit ComfyUI options skip.

**Step 2: Pack and record the exact content manifest**

Run:

```bash
comfy node pack
python -m pytest -q tests/package --archive node.zip
```

The first package test is expected to fail only because
`release/1.3.0-archive.sha256` is absent. Use
`tests.package.archive.inspect_archive` and `format_manifest` to write the
sorted hashes for that exact `node.zip`, inspect the new manifest, then rerun:

```bash
python -m pytest -q tests/package --archive node.zip
```

Expected: PASS with exactly the approved package files and no docs, tests,
credentials, absolute paths, caches, or generated build assets.

**Step 3: Run packed ComfyUI qualification**

At minimum:

```bash
python -m pytest -q tests/integration \
  --comfy-ref v0.28.0 \
  --archive node.zip \
  --device cpu
```

Also run the current supported stable frontend/ComfyUI combination and the
remote Windows/CPU and Linux/CUDA qualification matrix before release. Record
an unavailable gate as unrun; do not claim it passed.

**Step 4: Perform manual frontend qualification**

On frontend `1.45.21` and current stable, verify:

- root and nested input upload/selection;
- light and dark themes;
- landscape and portrait sources;
- node width changes and low graph zoom;
- all four resize handles and inside-frame movement;
- X/Y/width editing plus derived height;
- save/reload restoration;
- immediate local and Primitive ratios through reroutes;
- unresolved computed ratio, first-run centered crop, and second-run edited
  crop;
- invalid/impossible ratio errors;
- alpha mask output; and
- JavaScript-disabled numeric fallback.

Inspect `/object_info` for the exact manifest and run the tracked workflow.

**Step 5: Review and fix confirmed findings test-first**

Use `@code-review` against baseline `c0369f7`. Fix only confirmed defects,
starting with a failing focused test, and rerun every affected gate. Do not add
deferred features.

**Step 6: Refresh indexed docs and verify the final tree**

Run:

```bash
python .codex-context/ctx.py ingest
git diff --check
git status --short
```

Inspect every changed file and confirm only scoped source, tests, workflows,
release evidence, and documentation remain.

**Step 7: Commit the approved archive evidence**

```bash
git add release/1.3.0-archive.sha256
git commit -m "build: approve load and crop image candidate"
```

Do not tag or publish. Release still requires the explicit protected approval
documented in `README.md`.
