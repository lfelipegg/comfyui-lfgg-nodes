# Legacy LFGG node behavior and current ComfyUI overlap

Purpose: Record what the nine legacy LFGG modules actually do, where they are
unsafe or defective, and how much of each job current official ComfyUI already
covers.
Read when: deciding the disposition or contract of a legacy node.
Do not read for: successor designs, compatibility policy, packaging decisions,
or implementation instructions.
Source of truth: the pinned legacy and official source links below supersede
this audit when they change.
Last reviewed: 2026-07-26

## Summary

- The legacy pack registers nine V1 nodes and two frontend extensions.
- The prompt library and file-backed wildcard paths allow traversal, absolute
  paths, and symlink escape. The saver checks lexical containment but not
  symlink containment and returns local absolute paths.
- All three latent-producing nodes hard-code a four-channel, 8x spatial latent
  in `float32`; they do not carry the metadata, device policy, dtype policy, or
  model-family semantics of current ComfyUI latent creation.
- Current official overlap is complete for image batch selection, substantial
  for LoRA loading and image saving, and partial for sizing and wildcard
  expansion. No exact official Prompt Library or Model Name From Model node was
  found.
- Nineteen unit tests cover only Image Batch Select, Model Name From Model, and
  Save Image Dynamic. They use fakes or mocks rather than real Torch and ComfyUI
  integration.
- The legacy repository has no root `LICENSE`, `COPYING`, or `NOTICE`. No direct
  code reuse is cleared by this audit.

## Evidence baseline

### Legacy source and provenance

The code baseline is
[`lfgg_custom_nodes_comfyui` at `3d43b00`](https://github.com/lfelipegg/lfgg_custom_nodes_comfyui/tree/3d43b00d213d39e40dc2c495f5c6923717a3f900).
The local reference checkout is behind that commit, but all nine local module
contents match the pinned upstream tree; `latent_size_by_ratio.py` differs only
in line endings.

The current upstream tree has no root `LICENSE`, `COPYING`, or `NOTICE`, and the
local history through `d066bdb` contains no historical version of those files.
The relevant commit history attributes the work to `lfelipegg` / Luis Felipe
Gonzalez, including
[`55170db` for Image Batch Select and Save Image Dynamic](https://github.com/lfelipegg/lfgg_custom_nodes_comfyui/commit/55170db31ef8eaca6bea9b60383677f484e22752),
but commit authorship alone does not prove that every implementation was
original or grant a public reuse license. Licenses inside `examples/` apply to
those example projects, not to the legacy pack.

Consequence: later tickets may use behavior as evidence, but must not recommend
copying legacy code until the owner confirms provenance and licenses the source.

The checked-in `config.ini` also contains machine-local absolute Windows paths
for prompt and wildcard libraries. Those paths are private deployment state,
not portable package configuration.

### Official comparison point

Moving overlap claims were checked against:

- [ComfyUI `806e092`](https://github.com/Comfy-Org/ComfyUI/tree/806e092ed42772e4ce7abf44c97c50021cc4bd10)
  from 2026-07-26;
- [ComfyUI frontend `4916efd`](https://github.com/Comfy-Org/ComfyUI_frontend/tree/4916efd7fe2a80e0b08a32e6c08c41617c8a4dd7)
  from 2026-07-26.

The most relevant official behavior is:

- [`EmptyLatentImage`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/nodes.py#L1229-L1249)
  creates a four-channel 8x latent on ComfyUI's intermediate device and dtype
  and includes `downscale_ratio_spacial`.
- [`ImageFromBatch`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy_extras/nodes_images.py#L136-L160)
  clones a bounded slice and accepts negative indexes.
- [`ImageScaleToTotalPixels`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy_extras/nodes_post_processing.py#L222-L254)
  and
  [`ResizeImageMaskNode`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy_extras/nodes_post_processing.py#L412-L512)
  provide native aspect-preserving image resizing, total-pixel sizing, and
  multiple alignment.
- [`LoraLoader`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/nodes.py#L693-L738)
  already lists recursive LoRA names, caches the loaded file, loads safely with
  metadata, and applies it to model and CLIP.
- [`SaveImage`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/nodes.py#L1643-L1702)
  already supports subfolders and formatted filename prefixes, metadata,
  batches, counters, and UI results through
  [`get_save_image_path`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/folder_paths.py#L501-L548).
- The frontend's
  [dynamic prompt extension](https://github.com/Comfy-Org/ComfyUI_frontend/blob/4916efd7fe2a80e0b08a32e6c08c41617c8a4dd7/src/extensions/core/dynamicPrompts.ts)
  expands `{a|b}` on inputs marked `dynamicPrompts`; its
  [parser](https://github.com/Comfy-Org/ComfyUI_frontend/blob/4916efd7fe2a80e0b08a32e6c08c41617c8a4dd7/packages/shared-frontend-utils/src/formatUtil.ts#L181-L248)
  supports nested choices, escapes, and C-style comments.

An overlap statement of “none found” means no equivalent node was found in the
official node registrations and targeted source searches at these commits; it
is not a claim about third-party packs.

## Pack-wide behavior

[`__init__.py`](https://github.com/lfelipegg/lfgg_custom_nodes_comfyui/blob/3d43b00d213d39e40dc2c495f5c6923717a3f900/__init__.py)
imports all nine modules, merges their V1 `NODE_CLASS_MAPPINGS` and display
mappings with sequential `dict.update`, and exposes `WEB_DIRECTORY = "./web"`.
Duplicate IDs would silently overwrite earlier registrations. The IDs use the
legacy `Lfgg...` spelling, not the successor pack's required `LFGG_...` prefix.

Only Latent Size By Ratio and Prompt Wildcard have frontend code. Both use the
legacy `../../scripts/app.js` extension surface and monkey-patch widget or node
callbacks.

## LFGG Latent Size by Ratio

Source:
[`latent_size_by_ratio.py`](https://github.com/lfelipegg/lfgg_custom_nodes_comfyui/blob/3d43b00d213d39e40dc2c495f5c6923717a3f900/latent_size_by_ratio.py)

**Workflow job and schema.** `LfggLatentSizeByRatio` computes dimensions from
`1:1`, `4:3`, `3:2`, `16:9`, `9:16`, or `Custom`. Required inputs are
`ratio_preset` and `base_size` (`INT`, default 1024, 256–4096, step 8).
Optional inputs are `custom_ratio_w` and `custom_ratio_h` (`INT`, default 1,
1–64), `divisible_by` (`INT`, default 8, 1–64), and `batch_size` (`INT`,
default 1, 1–64). Outputs are `width: INT`, `height: INT`, and `latent: LATENT`.

**Execution.** The selected ratio fixes the longest side to `base_size`; both
dimensions are rounded to the nearest `lcm(8, divisible_by)`. It returns a CPU
`float32` zero tensor shaped `(batch, 4, height / 8, width / 8)`.

**Defects and boundaries.**

- The runtime trusts `base_size`, preset membership, divisibility, and batch
  bounds supplied by the prompt. Invalid presets raise `KeyError`; out-of-range
  API values can allocate unexpectedly large tensors.
- The latent contract assumes four channels and an 8x spatial downscale for
  every model family, omits `downscale_ratio_spacial`, and ignores ComfyUI's
  intermediate device and dtype.
- The frontend duplicates the Python preset table, installs a 200 ms polling
  timer per node, and replaces widget and `onWidgetChanged` callbacks. This is a
  UI-only dependency; execution does not need it.

**Tests and official overlap.** No tests exist. Native `EmptyLatentImage`
covers explicit width, height, batching, and allocation; native resize nodes
cover aspect-preserving image sizing. No official ratio-preset-to-dimensions
node was found, so overlap is partial.

## LFGG Image Resolution by Ratio

Source:
[`image_resolution_by_ratio.py`](https://github.com/lfelipegg/lfgg_custom_nodes_comfyui/blob/3d43b00d213d39e40dc2c495f5c6923717a3f900/image_resolution_by_ratio.py)

**Workflow job and schema.** `LfggImageResolutionByRatio` reads an `IMAGE`
batch's size, caps its longest edge, and emits a matching empty latent plus
dimensions. Required inputs are `image: IMAGE`, `base_size: INT` (default 1024,
64–8192, step 64), and `divisible_by: INT` (default 8, 1–512). Outputs are
`latent: LATENT`, original width/height, and new width/height.

**Execution.** Inputs at or below `base_size` are not enlarged. Larger inputs
are scaled down proportionally; dimensions are rounded to
`lcm(8, divisible_by)`. The zero latent keeps the input batch count and device
but forces `float32`, four channels, and an 8x downscale.

**Defects and boundaries.**

- Valid widget combinations can fail: for example, `base_size=64` and
  `divisible_by=512` pass schema validation but execution rejects them.
- Runtime validation checks Torch type and rank, but not an empty batch or
  positive spatial dimensions, and does not enforce the advertised upper
  bounds for API prompts.
- It creates a latent but does not resize or return the input image. The same
  hard-coded latent-family and metadata defects as Latent Size By Ratio apply.

**Tests and official overlap.** No tests exist. `ResizeImageMaskNode` now
covers longer-edge aspect-preserving resizing and multiple alignment, while
`GetImageSize` and `EmptyLatentImage` cover the remaining primitives. The exact
single-node metadata-plus-latent envelope is not native; functional overlap is
substantial but not exact.

## LFGG Image Batch Select

Source:
[`image_batch_select.py`](https://github.com/lfelipegg/lfgg_custom_nodes_comfyui/blob/3d43b00d213d39e40dc2c495f5c6923717a3f900/image_batch_select.py)

**Workflow job and schema.** `LfggImageBatchSelect` selects `first`, `last`, or
`index` from `images: IMAGE`; `batch_index` is a required `INT` (default 0,
0–4095). It returns one `IMAGE`.

**Execution.** It requires a non-empty four-dimensional batch, clamps explicit
indexes to the available range, slices while preserving a batch dimension, and
clones or copies the result when supported.

**Defects and boundaries.** The node validates shape but not Torch type;
`batch_index` remains required when unused, negative indexes are coerced to
zero, and oversized indexes silently clamp. These are contract quirks rather
than file or network trust boundaries.

**Tests and official overlap.** Nine fake-batch unit tests cover modes, bounds,
shape, cloning, metadata, and registration; no real Torch tensor is used.
Official `ImageFromBatch` covers the complete job with `batch_index`, `length`,
negative indexes (including `-1` for last), bounds, and cloning. Overlap is
complete apart from the legacy mode labels.

## LFGG Pixel Budget Latent Size

Source:
[`pixel_budget_latent_size.py`](https://github.com/lfelipegg/lfgg_custom_nodes_comfyui/blob/3d43b00d213d39e40dc2c495f5c6923717a3f900/pixel_budget_latent_size.py)

**Workflow job and schema.** `LfggPixelBudgetLatentSize` derives a non-upscaling
size from `image: IMAGE` under `max_pixels: INT` (default 900,000, 64–67,108,864,
step 1024), aligned to `divisible_by: INT` (default 64, 1–512). It returns an
empty `LATENT`, width, and height.

**Execution.** It scales by
`min(sqrt(max_pixels / original_pixels), 1)`, rounds both dimensions down to
`lcm(divisible_by, 8)`, and allocates a `float32`, four-channel, 8x latent on
the image's device.

**Defects and boundaries.**

- Widget-valid low-budget/high-divisibility combinations can round an axis to
  zero and fail at execution.
- Negative API budgets and divisibility values are silently clamped rather
  than rejected; advertised maxima are not enforced during execution.
- Empty batches are not rejected. The common hard-coded latent-family,
  metadata, and dtype defects apply.

**Tests and official overlap.** No tests exist. Native
`ImageScaleToTotalPixels` and `ResizeImageMaskNode` cover aspect-preserving
total-pixel sizing of actual images; `EmptyLatentImage` covers allocation. The
legacy no-upscale budget constraint and combined latent output are not an exact
native contract, so overlap is partial.

## LFGG Prompt Library

Source:
[`prompt_library.py`](https://github.com/lfelipegg/lfgg_custom_nodes_comfyui/blob/3d43b00d213d39e40dc2c495f5c6923717a3f900/prompt_library.py)

**Workflow job and schema.** `LfggPromptLibrary` recursively discovers every
file below the configured library, exposes cached relative paths through the
optional `selected_prompt` combo, and returns the selected UTF-8 content as
`prompt: STRING` plus a UI text envelope.

**Execution.** `INPUT_TYPES` or execution reads and may rewrite `config.ini`,
creates the configured directory, caches the file list for the process, and
reads the selected file.

**Defects and boundaries.**

- `_normalize_relative_path` only changes slashes and trims separators.
  Absolute paths, `..`, and symlinks can escape the configured library, making
  this an arbitrary file-read boundary under the ComfyUI process account.
- There is no extension, file-size, or decoded-text-size limit. Errors expose
  the configured absolute base path.
- Choice invalidation exists but is never called, so added or removed files
  stay stale until process or class state is reset.
- Schema discovery writes configuration and creates directories inside or
  relative to the installed package. The checked-in configuration points to a
  machine-local drive.

**Tests and official overlap.** No tests exist and there is no frontend module.
No official general-purpose prompt-file library/loader node was found. Current
core includes Save Text and dataset-specific text loading, neither of which
covers this workflow job.

## LFGG Prompt Wildcard

Source:
[`prompt_wildcard.py`](https://github.com/lfelipegg/lfgg_custom_nodes_comfyui/blob/3d43b00d213d39e40dc2c495f5c6923717a3f900/prompt_wildcard.py)

**Workflow job and schema.** `LfggPromptWildcard` accepts optional multiline
`wildcard_text` and `populated_text`, `mode` (`populate`, `fixed`,
`reproduce`), `seed: INT` (0–2^64-1), and a cached `add_wildcard` file combo.
It returns `text: STRING` plus UI `text` and `template` values.

**Execution.** A local `random.Random(seed)` expands nested `{a|b}` choices and
turns `__path__` files into choice blocks. `fixed` returns populated text;
`reproduce` returns it once per Python node instance, then expands. The
frontend appends selected file tokens to the template and writes populated
results back into the widget.

**Defects and boundaries.**

- File token normalization has the same absolute-path, traversal, symlink, and
  unbounded-read defects as Prompt Library.
- `MAX_EXPANSION_PASSES` limits only a loop inside one call. Recursive nested
  choices and self-referencing wildcard files have no shared depth or output
  bound and can exhaust recursion, CPU, or memory.
- Invalid modes fall through to populate behavior rather than fail.
- `_reproduce_used` is hidden mutable instance state. ComfyUI cache keys do not
  include it, so the one-shot behavior is not a stable execution contract; it
  also prevents a direct stateless V3 translation.
- Wildcard choices are process-cached without automatic invalidation. The
  frontend replaces widget callbacks and `onExecuted`, creating a second
  stateful compatibility surface.

**Tests and official overlap.** No tests exist. Official frontend dynamic
prompts already cover nested inline `{a|b}`, escapes, and comments at queue
serialization. They do not provide deterministic seeding, `__file__` loading,
or the fixed/reproduce string-output modes. Inline overlap is complete; the
remaining legacy job has no exact official equivalent.

## LFGG Load LoRA (Path)

Source:
[`lora_loader_by_path.py`](https://github.com/lfelipegg/lfgg_custom_nodes_comfyui/blob/3d43b00d213d39e40dc2c495f5c6923717a3f900/lora_loader_by_path.py)

**Workflow job and schema.** `LfggLoraLoaderByPath` takes `model: MODEL`,
`clip: CLIP`, a required `lora_path: STRING`, a `lora_name` combo, and model
and CLIP strengths (`FLOAT`, default 1, -100–100, step .01). It returns MODEL
and CLIP.

**Execution.** The subpath rejects absolute paths, drive markers, and `..`.
The dropdown is built by prefix-filtering ComfyUI's recursive LoRA list. At
execution the selected name must lexically start with that prefix; the node
then resolves it through `folder_paths`, safe-loads and instance-caches the
file, and calls `load_lora_for_models`.

**Defects and boundaries.**

- The dropdown is built from class-global `_last_subpath`, which changes only
  after some node executes. It cannot react to the current node's path widget,
  is stale until definitions refresh, and leaks one execution's filter across
  nodes and clients.
- The execution check is lexical prefix validation, not proof that the
  resolved file remains beneath an allowed LoRA root. The node relies on
  ComfyUI combo validation and `folder_paths`; it does not independently reject
  symlink escape.
- Unlike current core `LoraLoader`, it does not request or pass LoRA metadata
  to `load_lora_for_models`.

**Tests and official overlap.** No tests or frontend module exist. Current core
already performs the load, safe deserialization, caching, strength handling,
and recursive subfolder listing; the legacy addition is only a stale
server-side subpath filter. Functional overlap is substantial.

## LFGG Model Name From Model

Source:
[`model_name_from_model.py`](https://github.com/lfelipegg/lfgg_custom_nodes_comfyui/blob/3d43b00d213d39e40dc2c495f5c6923717a3f900/model_name_from_model.py)

**Workflow job and schema.** `LfggModelNameFromModel` takes `model: MODEL` plus
hidden `DYNPROMPT` and `UNIQUE_ID`, then returns `model_name: STRING`.

**Execution.** It ignores the runtime model object and traverses the prompt
graph through MODEL-typed links until it finds one supported loader field:
checkpoint loaders' `ckpt_name`, deprecated `DiffusersLoader.model_path`, or
`UNETLoader.unet_name`. It returns the basename without its final extension;
cycles, unsupported roots, and ambiguous model merges return `unknown_model`.

**Defects and boundaries.**

- Supported loader class IDs and field names are hard-coded and omit new,
  renamed, V3, and third-party loaders.
- MODEL-input discovery depends on internal `nodes.NODE_CLASS_MAPPINGS` and
  `comfy_execution.graph.get_input_info`; import or lookup failures silently
  fall back to input-name heuristics.
- An unbounded `lru_cache` retains input-type results across node reloads.
  Broad exception handling converts graph and API changes into
  `unknown_model`, hiding the cause.
- It reads graph structure but emits only a filename stem, so it does not expose
  configured directories or full local paths.

**Tests and official overlap.** Five fake-graph tests cover normalization, one
modifier, UNET loading, unsupported roots, and ambiguous merges. There is no
real ComfyUI test. No official node that converts a connected MODEL back to a
source filename was found. Native Save Image formatting can reference node
widget values for filename use, but does not provide this general STRING
output; overlap is limited to that narrower use case.

## LFGG Save Image Dynamic

Source:
[`save_image_dynamic.py`](https://github.com/lfelipegg/lfgg_custom_nodes_comfyui/blob/3d43b00d213d39e40dc2c495f5c6923717a3f900/save_image_dynamic.py)

**Workflow job and schema.** `LfggSaveImageDynamic` is an output node with
required `images: IMAGE`, `path_template: STRING` (default
`runs/{model}/{date}`), and `filename_template: STRING` (default
`{model}_{datetime}_{batch}`). Optional inputs are forced `model_name: STRING`
and `compress_level: INT` (default 4, 0–9). Hidden inputs are `PROMPT` and
`EXTRA_PNGINFO`; output is newline-separated `saved_paths: STRING`.

**Execution.** It expands brace and percent tokens for model, dimensions,
batch, counter, and local date/time; sanitizes path components and filenames;
finds a free numeric counter; converts each image to 8-bit PNG; embeds prompt
and workflow metadata unless disabled; and returns UI image entries plus
absolute paths.

**Defects and boundaries.**

- Output containment uses `abspath` and `commonpath`, not resolved paths.
  Existing symlinks below the output root can redirect writes outside it.
- Free-name discovery and the later PNG write are not atomic. Concurrent
  executions can choose the same path and overwrite one another.
- Returning absolute saved paths leaks machine-local filesystem layout through
  node results and APIs.
- Runtime code does not enforce compression bounds or a strict IMAGE entry
  shape. Metadata and template lengths are unbounded.
- It reimplements current `SaveImage` and `get_save_image_path` behavior rather
  than inheriting their evolving conventions.

**Tests and official overlap.** Five mocked tests cover tokens, model fallback,
filename sanitization, literal `..` rejection, and a fake two-image save. They
do not use Torch, Pillow, a real ComfyUI output directory, symlinks, or
concurrency. Core Save Image already covers output-root subfolders, formatted
prefixes, width/height/date tokens, widget references, metadata, batching,
counters, and UI entries. Separate path/name templates, connected model-name
text, compression control, and returned paths are legacy additions; overlap is
substantial.

## Existing test inventory

| Module | Tests | Boundary of evidence |
| --- | ---: | --- |
| Image Batch Select | 9 | Fake image batch; no Torch or ComfyUI |
| Model Name From Model | 5 | Fake dynamic prompt; no real node registry |
| Save Image Dynamic | 5 | Mocked modules and writes; no real PNG integration |
| Other six modules | 0 | No automated evidence |

No canonical legacy test command or CI configuration was found. Tests were
inspected, not executed, for this research ticket.

