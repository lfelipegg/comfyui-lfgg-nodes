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

The required 1.5.0 release qualification covers:

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
| LFGG Power LoRA Loader (Folder) | MODEL, CLIP, folder, ordered LoRA rows | MODEL, CLIP |
| LFGG Prompt Composer | multiline template, local style/wildcard libraries, seed | prompt, negative prompt |
| LFGG Save Image Dynamic | IMAGE, path/filename templates, metadata toggle, optional model label | saved-image previews |
| LFGG Video Cutter | VIDEO, time/frame selection | selected VIDEO segment |
| LFGG Routing Organizer | 1–32 labeled ANY routing channels | matching pass-through channels |

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

`LFGG Power LoRA Loader (Folder)` is in `LFGG/loaders`. It provides recursive
folder filtering for future selections, including every child folder, plus
`All LoRAs` to disable filtering. Changing the folder preserves existing rows,
including rows outside the new folder. Enabled rows load in their visible
ordered sequence, with separate model and CLIP strengths and controls to move,
remove, replace, or toggle rows. Each strength has arrows for 0.05 adjustments;
click the value itself for direct numeric entry. One combined strength is shown
by default. Enable `Separate Model and Clip strength` in the node settings to
show and edit the model and CLIP strengths independently.

Refresh node definitions after adding or removing LoRA files. A saved folder
that no longer exists remains visible but offers no new choices; existing rows
remain intact and missing selected files fail with an actionable error. The
node is standalone and does not require rgthree.

`LFGG Save Image Dynamic` is in `LFGG/Image`. It saves one PNG per batch frame
with separate output-relative path and filename templates. Supported brace
tokens are `{model}`, `{date}`, `{time}`, `{datetime}`, `{width}`, `{height}`,
`{batch}`, and `{counter}`. Missing or blank model labels become
`unknown_model`. PNG compression is fixed at level 4, and the node returns only
standard output-relative saved-image previews. One execution is limited to
268,435,456 total pixels across its image batch.

`LFGG Prompt Composer` is in `LFGG/text`. Stable ID
`LFGG_PromptComposer`. Its persisted inputs are the multiline
`prompt_template` and a standard 64-bit `seed`; outputs are `prompt` and
`negative_prompt` strings. File wildcards use `__folder/name__`, relative to a
configured root and without `.txt`. Styles use `[[style:Exact Name]]`. Their
positive fragments stay at the authored token positions, while negative style
fragments are joined in encounter order. Repeated wildcard tokens draw
independently and reproducibly. Duplicate non-empty file lines act as weights,
and native inline dynamic prompts such as `{red|blue}` remain available.

Copy [`config.example.json`](config.example.json) to
`<ComfyUI user directory>/lfgg_nodes/config.json`, then replace both paths:

```json
{
  "prompt_composer": {
    "styles_csv": "/absolute/path/styles.csv",
    "wildcards": "/absolute/path/wildcards"
  }
}
```

Both configured values must be absolute. The UTF-8 CSV requires the exact
`name,prompt,negative_prompt` header. Rows with no positive or negative value
are disabled headings; `.txt` files with no non-empty lines are also disabled.
The transient selectors insert relative wildcard or exact style tokens at the
text caret and do not add workflow state. **Refresh libraries** revalidates the
catalog through bounded `GET /lfgg/v1/prompt-composer/libraries`; a failed
refresh preserves the last valid choices and never returns configured paths or
file contents. Prefix `__file__` or `[[style:Name]]` with `\` to emit it
literally.

`LFGG Video Cutter` is in `LFGG/video`. Stable ID `LFGG_VideoCutter`. It
returns one contiguous `VIDEO` segment through native `VideoInput.as_trimmed`,
which keeps the primary video and audio synchronized and leaves auxiliary
tracks out of trimmed encodes. A whole-range selection returns the original
input object. Constant-frame-rate boundaries are exact; variable-frame-rate
boundaries use reported FPS as a nominal frame grid.

Persisted inputs, in order, are `video`, `selection_mode`, `start_time`,
`end_time`, `first_frame`, and `last_frame`. Time ranges are start-inclusive and
end-exclusive. Frame ranges are zero-based and inclusive. `-1` means source end
for `end_time` or `last_frame`; other negative, reversed, empty, or out-of-bounds
selections fail rather than clamp. Changing modes preserves the same segment.

The build-free editor provides a source player, playhead, dual boundary
handles, ten client-side thumbnails, editable timecodes and frame indexes, Set
Start/End, nominal previous/next-frame controls, and selection looping enabled
by default. Focus-scoped Space, Left/Right, and I/O control playback and marks.
Connected active boundaries are read-only. There is no waveform. The editor
adds no serialized value; all six backend inputs remain the executable
fallback.

`LFGG Routing Organizer` is a frontend-only virtual node in `LFGG/workflow`.
Stable ID `LFGG_RoutingOrganizer`. Each routing channel has one input socket,
one matching output socket, and one centered label; outputs may fan out. The
first connection selects the channel's ComfyUI wire type, including compatible
widget and combo types, and chained native reroutes or routing organizers
propagate that type without entering prompt execution.

The node begins with one empty channel and adds another when the last channel
is connected or labeled, up to 32 channels. Right-click for Add, Rename, and
Remove actions, or double-click a label to rename it. Labels are trimmed to 64
Unicode characters and numbered defaults follow their current positions.
Removing a connected channel reconnects its upstream source directly to every
compatible downstream target; a channel is kept if that splice cannot be done
without losing links. Deleting the whole organizer uses ComfyUI's normal
index-matched node bypass. Channel order, labels, types, and links persist in
workflow JSON. Reordering, collapsing, execution modes, routing cycles, and
conversion inside groups or subgraphs are intentionally unsupported.

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

The folder-filtered LoRA loader reads selected LoRA files through ComfyUI. It
performs no network calls or file writes.

The prompt composer reads its fixed configuration beneath the ComfyUI user
directory, its configured styles CSV, and referenced wildcard `.txt` files. It
writes no files and makes no outbound network calls. Refresh inspects at most
10,000 wildcard-library entries (including directories and non-`.txt` files)
and 64 MiB of wildcard content; configuration, styles, each decoded CSV field,
each wildcard, and combined resolved outputs are capped at 64 KiB, 4 MiB,
128 KiB, 1 MiB, and 1 MiB respectively. Wildcard symlinks must resolve inside
the configured root.

The video cutter makes no outbound network calls. Before queueing, only a
direct native `LoadVideo` source (through simple reroutes) may call the local,
bounded `POST /lfgg/v1/video-metadata` route. That route accepts one short input
identifier, securely confines it beneath ComfyUI's input root, and reads PyAV
stream metadata without decoding the full video. Metadata probing accepts only
AVI, MOV/M4V/MP4, MKV, and WebM files, forces the matching demuxer, and permits
no nested file or network protocols. Playback uses ComfyUI's native `/view`
endpoint. After execution, the node may write a capped MP4 preview to ComfyUI's
temp directory only for selections up to 30 seconds, 900 nominal frames, and
1920×1080; at most eight cached entries are retained. Preview or cache failure
returns a UI warning without changing the valid `VIDEO` result.
The tracked [video-cutter API workflow](workflows/video_cutter.json) expects a
`video_cutter.mp4` test input and writes its result through native `SaveVideo`.

The routing organizer makes no network calls and reads or writes no files. It
exists only in saved workflow graph data and is omitted from prompt execution.

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
- Replace Prompt Library and Prompt Wildcard nodes with
  `LFGG_PromptComposer`, preserving token positions in one template. The legacy
  single LoRA Loader by Path remains deferred.

## Develop and qualify

```bash
python -m pip install -e ".[dev]"
node --test tests/frontend/ratio_preview.test.mjs
node --test tests/frontend/crop_editor.test.mjs
node --test tests/frontend/power_lora_loader.test.mjs
node --test tests/frontend/video_cutter.test.mjs
node --test tests/frontend/prompt_composer.test.mjs
node --test tests/frontend/routing_organizer.test.mjs
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
