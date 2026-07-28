# LFGG Nodes

Small, explicit workflow utility nodes for ComfyUI.

## Install

After the Registry release:

```bash
comfy node install lfgg-nodes
```

Until then, clone the repository into ComfyUI's `custom_nodes` directory:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/lfelipegg/comfyui-lfgg-nodes.git lfgg-nodes
```

Restart ComfyUI after installation. Pillow is the only Python runtime
dependency. The pack includes a build-free frontend extension.

## Compatibility

The required 1.4.0 release qualification covers:

- ComfyUI `>=0.28.0`, tested at exact stable tags rather than `master`
- ComfyUI frontend `>=1.45.21`
- Python `>=3.10,<3.14`
- Linux and Windows
- CPU and NVIDIA CUDA

Publication waits for the complete remote matrix. Other operating systems and
accelerators are not claimed.

## Nodes

| Node | Inputs | Outputs |
|---|---|---|
| LFGG Dimensions by Aspect Ratio | preset/custom ratio, long-side cap, alignment | width, height |
| LFGG Image Dimensions by Long Side | IMAGE, long-side cap, alignment | width, height |
| LFGG Image Dimensions by Pixel Budget | IMAGE, exact pixel cap, alignment | width, height |
| LFGG Resize Image by Long Side | IMAGE, interpolation method, long-side cap, alignment | resized image, width, height |
| LFGG Load and Crop Image | one still image, ratio, exact source-pixel crop | cropped image, alpha-derived mask |
| LFGG Save Image Dynamic | IMAGE, path/filename templates, metadata toggle, optional model label | saved-image previews |

All three nodes are in `LFGG/sizing`. They return positive dimensions aligned
to the exact `divisible_by` value. Aspect fidelity wins before pixel area, with
a deterministic side-size tie-break. Limits are hard ceilings and impossible
alignments raise actionable errors.

`LFGG Dimensions by Aspect Ratio` shows a theme-aware preview of the requested
aspect ratio directly below its selector, with the ratio shape above a fixed
background grid. The selector adds common-use descriptions while workflows
continue to store the raw ratio values. Presets hide the custom ratio controls;
selecting `Custom` or connecting a dynamic ratio reveals them without resetting
their values. The preview adds no workflow state and does not affect backend
sizing. If the frontend extension is unavailable, all inputs remain visible and
the node still executes normally.

The two image-derived nodes are downscale-only and inspect the shared
`[B,H,W,C]` tensor shape. Batch count does not change the result. They do not
allocate, copy, cast, mutate, or move the image.

`LFGG Resize Image by Long Side` is in `LFGG/image`. It uses the same
downscale-only dimensions as `LFGG Image Dimensions by Long Side`, then
resamples the complete image with cropping disabled. Its `upscale_method`
defaults to `lanczos`; the other native choices are `nearest-exact`, `bilinear`,
`area`, and `bicubic`. It preserves the batch and returns the resized `IMAGE`,
`width`, and `height`. When the aligned dimensions already match the source, it
returns the original tensor without resampling. Inputs must contain finite
floating-point values with 1, 3, or 4 channels and at most 268,435,456 pixels
across the batch.

`LFGG Load and Crop Image` is in `LFGG/image`. It reads one still image from
the ComfyUI input directory, accepts images up to `16384 × 16384` pixels and
268,435,456 total pixels, and returns the selected exact-ratio source rectangle
without resampling. Alpha produces an Alpha-derived mask using ComfyUI's
transparent-is-white convention. Stable ID `LFGG_LoadAndCropImage`.

Persisted inputs, in order, are:

- `image` (required selection)
- `ratio_width` (default `1`)
- `ratio_height` (default `1`)
- `crop_x` (default `0`)
- `crop_y` (default `0`)
- `crop_width` (default `0`)
- `crop_height` (default `0`); derived by the frontend

Outputs: `image` (`IMAGE`) and `mask` (`MASK`). The source must be a relative,
contained file beneath ComfyUI's input directory; URLs, arbitrary paths,
symlink escapes, corrupt images, and multi-frame images are rejected. EXIF
orientation is applied before source-pixel coordinates. Ratio components must
be positive, are reduced before use, and must fit as a whole-pixel crop.

The all-zero crop initializes the largest centered exact-ratio frame. A
positive, contained frame persists for the same selected image and resolved
ratio; selecting another image or changing the ratio resets it. Primitive
numeric ratios through reroutes update immediately. Other dynamic ratio
connections display `Run to resolve connected ratio` until backend execution
returns a resolved centered crop. Resizing the graph node changes only the
preview. If the frontend extension is unavailable, the same seven standard
inputs remain as the numeric fallback. The frontend uses ComfyUI's native input
view endpoint and adds no route. The node does not access the network and writes
no files.

`LFGG Save Image Dynamic` is in `LFGG/Image`. It saves one PNG per batch frame
with separate output-relative path and filename templates. Supported brace
tokens are `{model}`, `{date}`, `{time}`, `{datetime}`, `{width}`, `{height}`,
`{batch}`, and `{counter}`. Missing or blank model labels become
`unknown_model`. PNG compression is fixed at level 4, and the node returns only
standard output-relative saved-image previews. One execution is limited to
268,435,456 total pixels across its image batch.

## File and network behavior

The sizing nodes use standard-library integer math plus tensor shape
inspection. They do not access the network and do not read or write files.
The tracked [sizing API workflow](workflows/sizing.json) uses native
`SaveLatent` and `SaveImage` nodes, which do write example `.latent` and `.png`
files. The resize node uses ComfyUI's in-memory image resampler and does not
itself access the network or filesystem.

The dynamic saver does not access the network. Its only writes are creation of
output subdirectories beneath ComfyUI's resolved output root, exclusive
creation of final PNG files, and cleanup of PNG files created by a failed
execution. It never overwrites or removes a pre-existing file. Imports and
schema discovery do not write files. The tracked
[dynamic-save API workflow](workflows/save_image_dynamic.json) writes small
example PNGs beneath that output root.

The tracked [load-and-crop API workflow](workflows/load_and_crop_image.json)
requires the redistributable same-stem asset
`workflows/load_and_crop_image.png`; copy it to
`ComfyUI/input/load_and_crop_image.png` before opening or running the workflow.
The loader reads that input file but performs no file writes.

## Migrate legacy workflows

No legacy workflow ID is registered. Replace nodes manually:

- `LfggLatentSizeByRatio` → `LFGG_DimensionsByAspectRatio`. Map `base_size` to
  `long_side`, retain the ratio/custom values, and move `batch_size` plus latent
  creation to the native initializer appropriate for the model family.
- `LfggImageResolutionByRatio` → `LFGG_ImageDimensionsByLongSide`. Map
  `base_size` to `long_side`. Use native `Get Image Size` only when the removed
  original-dimension outputs were consumed, and replace the latent output with
  the appropriate native initializer.
- `LfggPixelBudgetLatentSize` → `LFGG_ImageDimensionsByPixelBudget`. Transfer
  `max_pixels` unchanged and replace latent creation with the appropriate
  native initializer. The new default is `1048576`, replacing `900000`.
- `LfggSaveImageDynamic` → `LFGG_SaveImageDynamic`. Reconnect `images` and the
  optional explicit `model_name`. Convert `%token%` to `{token}` and
  `%batch_num%` to `{batch}` in both templates. Remove `compress_level`; PNG
  compression is fixed at 4. Use `save_metadata` to disable both prompt and
  workflow metadata when needed. Remove downstream uses of `saved_paths`; the
  successor exposes only standard saved-image previews. No legacy workflow ID
  alias or automatic workflow rewrite is provided.

To preserve the legacy effective alignment, set
`divisible_by = lcm(8, legacy_divisible_by)`. Otherwise the new nodes honor the
chosen value exactly. Dimensions may change where legacy rounding exceeded a
cap or produced a poorer aspect match.

Additional dispositions:

- Replace `LfggImageBatchSelect` with native `ImageFromBatch`. Use
  `batch_index=0` for first, `batch_index=-1` for last, or the desired explicit
  index, with `length=1`.
- Remove `LfggModelNameFromModel`; pass an explicit label string alongside the
  model instead of trying to infer provenance from the prompt graph.
- Prompt Library, Prompt Wildcard, and LoRA Loader by Path are deferred to
  separate future efforts.

## Develop and qualify

```bash
python -m pip install -e ".[dev]"
node --test tests/frontend/ratio_preview.test.mjs
node --test tests/frontend/crop_editor.test.mjs
python -m ruff check .
python -m pytest -q tests/unit
comfy node validate
comfy node pack
python -m pytest -q tests/package --archive node.zip
python -m pytest -q tests/integration --comfy-ref v0.28.0 --archive node.zip --device cpu
```

The handwritten frontend extension has no generated-asset build. There is no
runtime installer or compatibility `requirements.txt`.

## Release operators

Publishing is restricted to an exact version-matching tag after the complete
qualification workflow passes. The `registry-release` GitHub environment must
require reviewer `lfelipegg`, and its publisher-scoped
`REGISTRY_ACCESS_TOKEN` must exist only as an environment secret.

Registry versions are immutable. If a version is created before a later
release step fails, deprecate it with an actionable replacement and publish an
incremented version; never overwrite or retry the consumed version.
