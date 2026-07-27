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

Restart ComfyUI after installation. Pillow is the only runtime dependency;
there is no frontend extension.

## Compatibility

The required 1.1.0 release qualification covers:

- ComfyUI `>=0.28.0`, tested at exact stable tags rather than `master`
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
| LFGG Save Image Dynamic | IMAGE, path/filename templates, metadata toggle, optional model label | saved-image previews |

All three nodes are in `LFGG/sizing`. They return positive dimensions aligned
to the exact `divisible_by` value. Aspect fidelity wins before pixel area, with
a deterministic side-size tie-break. Limits are hard ceilings and impossible
alignments raise actionable errors.

The two image-derived nodes are downscale-only and inspect the shared
`[B,H,W,C]` tensor shape. Batch count does not change the result. They do not
allocate, copy, cast, mutate, or move the image.

`LFGG Save Image Dynamic` is in `LFGG/Image`. It saves one PNG per batch frame
with separate output-relative path and filename templates. Supported brace
tokens are `{model}`, `{date}`, `{time}`, `{datetime}`, `{width}`, `{height}`,
`{batch}`, and `{counter}`. Missing or blank model labels become
`unknown_model`. PNG compression is fixed at level 4, and the node returns only
standard output-relative saved-image previews.

## File and network behavior

The sizing nodes use standard-library integer math plus tensor shape
inspection. They do not access the network and do not read or write files.
The tracked [sizing API workflow](workflows/sizing.json) uses native
`SaveLatent` nodes, which do write example `.latent` files.

The dynamic saver does not access the network. Its only writes are creation of
output subdirectories beneath ComfyUI's resolved output root, exclusive
creation of final PNG files, and cleanup of PNG files created by a failed
execution. It never overwrites or removes a pre-existing file. Imports and
schema discovery do not write files. The tracked
[dynamic-save API workflow](workflows/save_image_dynamic.json) writes small
example PNGs beneath that output root.

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
python -m ruff check .
python -m pytest -q tests/unit
comfy node validate
comfy node pack
python -m pytest -q tests/package --archive node.zip
python -m pytest -q tests/integration --comfy-ref v0.28.0 --archive node.zip --device cpu
```

There is no generated-asset build, runtime installer, or compatibility
`requirements.txt`.

## Release operators

Publishing is restricted to an exact version-matching tag after the complete
qualification workflow passes. The `registry-release` GitHub environment must
require reviewer `lfelipegg`, and its publisher-scoped
`REGISTRY_ACCESS_TOKEN` must exist only as an environment secret.

Registry versions are immutable. If a version is created before a later
release step fails, deprecate it with an actionable replacement and publish an
incremented version; never overwrite or retry the consumed version.
