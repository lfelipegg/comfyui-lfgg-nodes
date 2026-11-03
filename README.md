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
| LFGG Composition Image by Aspect Ratio | preset/custom ratio, long-side cap, alignment, family, palette, complexity, seed, batch size | IMAGE, width, height |
| LFGG Image Dimensions by Long Side | IMAGE, long-side cap, alignment | width, height |
| LFGG Image Dimensions by Pixel Budget | IMAGE, exact pixel cap, alignment | width, height |
| LFGG Dimensions by Ratio and Megapixels | preset/custom ratio, megapixel budget, alignment | width, height |
| LFGG Image Dimensions by Megapixels | IMAGE ratio, megapixel budget, alignment | width, height |
| LFGG Resize Image by Long Side | IMAGE, interpolation method, long-side cap, alignment | resized image, width, height |
| LFGG Load and Crop Image | one still image, ratio, exact source-pixel crop | cropped image, alpha-derived mask |
| LFGG Power LoRA Loader (Folder) | MODEL, CLIP, folder, ordered LoRA rows | MODEL, CLIP |
| LFGG Prompt Composer | multiline template, local style/wildcard libraries, seed | prompt, negative prompt |
| LFGG Prompt Assistant | master prompt, request, skills, model, VRAM policy, seed, temperature, max tokens, up to four optional IMAGE inputs | prompt |
| LFGG String Join | literal separator, 2–32 ordered string inputs | joined text |
| LFGG String Replace | multiline text, literal search/replacement, casing | replaced text |
| LFGG String Replace (Regex) | multiline text, literal/regex search/replacement, casing | replaced text |
| LFGG Save Image Dynamic | IMAGE, path/filename templates, metadata toggle, optional model label | saved-image previews |
| LFGG Video Cutter | VIDEO, time/frame selection | selected VIDEO segment |
| LFGG Routing Organizer | 1–32 labeled ANY routing channels | matching pass-through channels |
| LFGG Boolean Switch | BOOLEAN selector, false/true ANY branches | selected value |
| LFGG Index Switch | zero-based INT selector, 2–32 ANY branches | selected value |
| LFGG Value Inspector | any connected value | inline diagnostic report |
| LFGG Output Gallery | output subfolder, subfolder recursion, media filter, name filter, sort, limit | none; read-only viewer |

All five sizing nodes are in `LFGG/sizing`. They return positive dimensions aligned
to the exact `divisible_by` value. Limits are hard ceilings and impossible
alignments raise actionable errors. The long-side and raw pixel-budget nodes
prefer aspect fidelity before pixel area, with a deterministic side-size
tie-break. The megapixel nodes scale proportionally to their budget, then
round both dimensions down to the requested alignment.

`LFGG Dimensions by Aspect Ratio` shows a theme-aware preview of the requested
aspect ratio directly below its selector, with the ratio shape above a fixed
background grid. The selector adds common-use descriptions while workflows
continue to store the raw ratio values. Presets hide the custom ratio controls;
selecting `Custom` or connecting a dynamic ratio reveals them without resetting
their values. The preview adds no workflow state and does not affect backend
sizing. If the frontend extension is unavailable, all inputs remain visible and
the node still executes normally.
Automatic height changes fit the visible controls without shrinking a node
that the user has manually enlarged.

`LFGG Image Dimensions by Long Side` and `LFGG Image Dimensions by Pixel Budget`
are downscale-only. All image-derived sizing nodes inspect the shared
`[B,H,W,C]` tensor shape. Batch count does not change the result. They do not
allocate, copy, cast, mutate, or move the image.

### Composition seed images

`LFGG Composition Image by Aspect Ratio` (`LFGG_CompositionImageByAspectRatio`,
category `LFGG/image`) generates abstract RGB compositions, not noise or latents.
It reuses the sizing node's exact preset/custom ratio controls, aspect-fidelity
and alignment policy, defaults (`1:1`, long side `1024`, alignment `8`, custom
ratio `1:1`), and requested-ratio preview. Existing sizing workflows are unchanged.

Choose scattered clusters, regular/jittered grids, directional bands/diagonal
arrangements, concentric/radial arrangements, large area partitions, or gradient
fields with optional shapes. **Family defaults to Random.** Complexity ranges
from `0` to `1`, default `0.5`; each family coordinates count, size, spacing and
overlap differently. Shapes use pixel-space proportions on the requested
rectangular canvas, with intentional overlap/clipping and antialiased boundaries.

**Palette defaults to Monochrome:** black and white except at smoothed boundaries.
Grayscale includes intermediate tones; Muted color and Vivid color use curated,
coordinated palettes. Random selects a palette independently for each image.
The gradient family uses thresholded regions in monochrome, never a continuous
gray gradient. Random family choices are also per image, independent of palette.

The composition `seed` defaults to `0`; `batch_size` defaults to `1`. Fixed inputs
reproduce the ordered pixel batch in the same rendering environment. Increasing
batch size preserves earlier items. Explicit family/palette choices remain fixed
while details vary. Finite output spaces can produce collisions; seed uniqueness
is not promised. Native seed controls can randomize between executions.

Output is contiguous CPU float32 RGB `IMAGE` data in `[B,H,W,3]`, normalized to
`[0,1]`, followed by the actual aligned width and height. Before allocating,
the node rejects aligned `width × height × batch_size > 16,777,216` pixels.
The inclusive limit allows sixteen `1024 × 1024` or four `2048 × 2048` images
and occupies 192 MiB for the output alone. Images render sequentially using
512-pixel tiles at 3× supersampling with three-pixel filter gutters; intermediate
buffers are tile-bounded, not full-canvas supersampled images. Invalid requests
raise actionable errors; the node never reduces the batch or resizes to fit.
This guard does not guarantee downstream VAE/sampler memory availability.

Connect `IMAGE` to native **Preview Image** to inspect pixels, or to native
**VAE Encode** and then your sampling workflow. The ratio preview is only the
requested proportion. The generator performs no sampling, VAE operation, network
request, image file write, or generator-owned pixel preview. The composition seed
is independent of the sampler seed. `workflows/composition_image.json` is an
API-format example connected to native Preview Image, which owns its normal
temporary preview files. Generator variation is not evidence of improved
Krea 2 output diversity.

### Megapixel sizing

`LFGG Dimensions by Ratio and Megapixels` uses the existing preset/custom ratio
selector and ratio preview. `LFGG Image Dimensions by Megapixels` instead uses
an input image only for its aspect ratio: its output dimensions **may exceed
the source dimensions**. Neither node resizes an image or creates a latent.
Existing non-megapixel sizing nodes and their saved workflows are unchanged.

Both accept a connectable numeric `megapixels` input, default `1.0`, with
`0.05` increments, and `divisible_by`, default `8`. The pack convention is
**1 megapixel = 1,048,576 pixels (1024 × 1024)**, not decimal megapixels.
The hard area ceiling is `floor(megapixels × 1,048,576)`; ComfyUI's per-axis
resolution limit also applies. Values must be finite and positive, at least
one pixel in the UI, and no greater than the squared per-axis limit divided
by 1,048,576. Invalid ratios and alignment raise errors. If either proportional
dimension is smaller than `divisible_by`, execution raises an error rather than
distorting the ratio to force a positive aligned result.

Both megapixel nodes first compute the proportional dimensions that fill the
budget, reducing the scale if needed to respect the per-axis limit. Each axis
is then rounded down to `divisible_by`. This keeps the hard ceiling and avoids
drastically smaller outputs chosen only for a marginally closer aspect ratio.
Alignment may slightly change the output ratio; coarse alignment or a binding
per-axis limit can leave more of the budget unused.

At `1.0` megapixels and alignment `8`, square dimensions are `1024 × 1024`;
`16:9` produces `1360 × 768`. An image ratio of `912:1905` produces
`704 × 1472`, using about 98.8% of the budget. A `512 × 512` source image
produces `1024 × 1024` dimensions without changing the input image.

Stable IDs: `LFGG_DimensionsByRatioAndMegapixels` and
`LFGG_ImageDimensionsByMegapixels`.

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
Only the oriented crop is converted to float32 tensors; returned image and mask
storage does not retain the full source image.

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
While the selected image loads, crop editing is locked and saved numeric values
are preserved. A failed preview shows a recovery message; reselect or upload the
image to retry. Execution results received during loading apply once that image
is ready.

The crop preview starts compact and remains draggable. **Edit crop** reveals
the precise X/Y/width controls and a larger preview; height stays read-only.
The dimensions caption is in source pixels. **Hide crop controls** changes
only presentation, as does resizing the node.

`LFGG Power LoRA Loader (Folder)` is in `LFGG/loaders`. It provides recursive
folder filtering for future selections, including every child folder, plus
`All LoRAs` to disable filtering. Changing the folder preserves existing rows,
including rows outside the new folder. Enabled rows load in their visible
ordered sequence, with separate model and CLIP strengths and controls to move,
remove, replace, or toggle rows. Each strength has arrows for 0.05 adjustments;
click the value itself for direct numeric entry. One combined strength is shown
by default. Enable `Separate Model and Clip strength` in the node settings to
show and edit the model and CLIP strengths independently.
Rows stack their strength controls at narrow widths instead of compressing
filenames. Basenames are ellipsized with folder context when needed; **Show
full path** opens a selectable native prompt. The node's native context menu
also exposes row operations. Disabled rows retain readable values but do not
accept strength edits.

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
`<ComfyUI user directory>/lfgg_nodes/config.json`. The user directory is the
`user` folder ComfyUI reports at startup (`ComfyUI/user` by default, or the
`--user-directory` value). The file holds one optional section per node that
needs configuration: `prompt_composer` for this node and `prompt_assistant`
for `LFGG Prompt Assistant`. Keep only the sections you use; any other
top-level key or a repeated key is rejected, and the file is limited to 64 KiB
of UTF-8 JSON. For the composer, replace both paths:

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
The wildcard selector opens a searchable checkbox list. Check one or more
entries, then choose **Insert selected**: one inserts `__folder/name__`;
multiple insert `{__folder/first__|__folder/second__}` in selection order.
Filtering preserves checked entries. **Cancel** or Escape discards the pending
selection. The style selector uses ComfyUI's searchable combo menu.
These transient editing controls insert at the text caret, replace selected
text, and do not add workflow state. **Refresh libraries** revalidates the
catalog through bounded `GET /lfgg/v1/prompt-composer/libraries`; a failed
refresh preserves the last valid choices and never returns configured paths or
file contents. Prefix `__file__` or `[[style:Name]]` with `\` to emit it
literally.
New Prompt Composer instances reuse the session's last valid catalog and share
in-flight requests. **Refresh libraries** fetches a fresh shared snapshot for
the requesting selectors and subsequently created nodes; execution-time file
fingerprints remain unchanged.
Workflow reload preserves manual node sizing and waits for a real container
width before measuring the selector panel. If an earlier version already saved
an inflated size, resize the node once and save the workflow again.

`LFGG Prompt Assistant` is in `LFGG/text`. Stable ID `LFGG_PromptAssistant`.
It asks a `llama-server` that you run yourself to write one generation prompt
and returns the reply as `prompt`. The node talks HTTP only: it never
installs, starts, or stops the server, and it does not use `llama-cpp-python`.
Persisted inputs, in order, are the multiline `master_prompt` (sent as the
system message, default shown in the node), `request`, `skills`, `model`
(`server default` or a server model id), `vram_policy` (`share`,
`keep_llm_loaded`, `off`), a 64-bit `seed` (its low 32 bits are sent),
`temperature` (0 to 2), and `max_tokens` (1 to 32768). `image_1` to `image_4`
are optional; every batch frame counts and eight images at most are sent, in
slot then batch order, downscaled to a 1024 px long side as JPEG quality 92 or
PNG when the tensor has alpha. `request` may be empty only when an image is
connected. Unchanged inputs return the cached prompt without contacting the
server.

The node reads the `prompt_assistant` section of the shared
`<ComfyUI user directory>/lfgg_nodes/config.json` described under the Prompt
Composer (`ComfyUI/user/lfgg_nodes/config.json` on a standard install; create
the `lfgg_nodes` folder if it is missing). Without that section the node fails
with an error naming the file. A complete section for a local `llama-server`
on its default port looks like this:

```json
{
  "prompt_assistant": {
    "server": {
      "base_url": "http://127.0.0.1:8080",
      "api_key": "",
      "read_timeout_seconds": 300
    },
    "skills_roots": [
      "~/.agents/skills",
      "C:/Users/<name>/.agents/skills"
    ],
    "skills": [
      "scenario-maker-sdxl",
      "scenario-maker-krea-2",
      "scenario-maker-illustrious",
      "scenario-maker-noobai",
      "scenario-maker-pony",
      "scenario-maker-wan",
      "scenario-maker-minimax-h3"
    ]
  }
}
```

The section accepts only these keys; any other key is rejected:

- `server.base_url` (optional, default `http://127.0.0.1:8080`): the
  `llama-server` origin. It must be `http` or `https` with a host and optional
  port only, no path, query, or credentials. Use the `--host` and `--port`
  values you start the server with.
- `server.api_key` (optional, default empty): sent as a bearer token when the
  server runs with `--api-key`. Keep it a single line and never commit the
  file.
- `server.read_timeout_seconds` (optional, default 300): how long one
  streamed reply may stay silent before the node fails. Bounded to 10–3600.
  Connecting always times out after 5 s.
- `skills_roots` (required, may be empty): directories whose immediate
  children are skills. Entries must be absolute paths or start with `~`, in
  either OS style, so one file can serve Linux and Windows machines. Roots
  that do not exist on the current machine are skipped with a logged warning;
  a skill name found under two roots uses the first root listed.
- `skills` (optional): the allowlist of skill folder names the picker may show
  and the node may attach. Names must be plain folder names without
  separators and must not repeat. Omit the key to allow every discovered
  skill. The shipped example allowlists the seven split `scenario-maker-*`
  skills.

No restart is needed after editing the file: the node re-reads it on every
execution that is not served from ComfyUI's cache, and the picker's refresh
buttons re-read it too. Errors name the offending key. The picker shows the
configured root specs as written (for example `~/.agents/skills`) so you can
see which roots were searched, but never file contents or resolved paths.

A skill is a directory one level below a root that contains `SKILL.md`. The
`skills` text holds one entry per line: `scenario-maker-sdxl` attaches that
skill's `SKILL.md` and every reference it links to;
`scenario-maker-sdxl/README.md` also attaches one more file and implies the
skill. Attachable references are `.md` files beneath the skill outside `evals`,
`docs`, `tests`, `scripts`, `wildcards`, and hidden directories; symlinks must
resolve inside the skill. A linked reference is any attachable file whose path
appears in `SKILL.md` (relative to the skill, such as `references/routing.md`)
or in a linked reference (relative to that file, such as `../routing.md`, or to
the skill); links are followed transitively and other mentions are ignored,
because the model cannot open files itself. The system message opens with a
note that says so and names the selected skills' references that were left
out.
Each file is limited to 512 KiB and all attachments together to 256 KiB; the
node fails naming the largest attachments rather than truncating. Unknown,
non-allowlisted, missing, excluded, or non-`.md` entries fail with the entry
and the roots searched. The frontend picker below the text edits it, shows
missing allowlisted skills with the roots searched, lists each skill's
references with linked ones checked and locked, offers an **All references**
shortcut for the rest, and shows the attached-size estimate. **Refresh models** fills the `model` list from the server and keeps
a saved id that is no longer listed, marked as missing. The reply streams into
ComfyUI's progress text; the final prompt also appears in a read-only,
selectable **Generated prompt** report that is restored on workflow reload.

Under `share`, the node calls `comfy.model_management.unload_all_models()` and
`soft_empty_cache()` before the request so ComfyUI's models move to RAM, then
after the reply calls `POST /models/unload` and polls `GET /models` for up to
30 s when the server runs in router mode (`--models-dir` or
`--models-preset`). In single-model mode the language model cannot be released
and the node logs one warning recommending router mode or
`--sleep-idle-seconds`. Those model-management calls are guarded: a changed
internal API degrades to a logged warning. `keep_llm_loaded` performs only the
pre-request step; `off` performs neither. Only the reply's `content` is used;
`reasoning_content` is discarded, and an empty reply fails with an error that
points at `max_tokens`.

Tested against llama.cpp build b10970 (commit `bfdc32183`, Windows CUDA
build) in router mode with a Qwen 3.8 27B GGUF plus its `--mmproj`
projector: a streamed text-only run, a two-image run, and a `share` run whose
`POST /models/unload` returned the model's VRAM to the OS within two seconds.
Before a release, repeat those runs from a ComfyUI workflow in router mode and
in single-model mode and confirm the following sampler reloads its model.

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

The build-free editor starts with the source player, active time/frame boundary
pair, and an explicit segment summary. **Edit selection** reveals the filmstrip,
playhead, separately labeled boundary sliders, previous/next-frame controls,
Set Start/End, and selection looping. **Hide selection controls** returns to
the compact view without changing the segment or reloading its metadata.
Ten bounded client-side thumbnails are decoded only while the editor is open
and the node is not collapsed; completed thumbnails are reused.

Focus-scoped Space, Left/Right, and I/O control playback and marks. These
shortcuts do not intercept native buttons, media controls, or text fields.
Connected boundaries remain discoverable and read-only, including inactive
inputs. Disconnecting restores the saved local value. Unavailable or invalid
previews leave the native numeric fallback visible. There is no waveform.

Crop and video editors share one presentation-only workflow property,
`node.properties.lfgg_editor_expanded`. Only Boolean `true` opens the editor;
old workflows and malformed values open compact. It does not enter API prompts
or replace any backend input. This UI adds no external network calls.

`LFGG Routing Organizer` is a virtual node in `LFGG/workflow` with a minimal
backend definition for package discovery and frontend-only routing behavior.
Stable ID `LFGG_RoutingOrganizer`. Each routing channel has one input socket,
one matching output socket, and one label; outputs may fan out. Labels are
centered in the legacy renderer and use native input labels in Nodes 2.0. The
first connection selects the channel's ComfyUI wire type, including compatible
widget and combo types, and chained native reroutes or routing organizers
propagate that type without entering prompt execution.

The node begins with one empty channel and supports up to 32 channels.
Right-click for Add, Rename, and Remove actions. The legacy renderer also
supports double-clicking a label to rename it; Nodes 2.0 lists numbered channel
actions in the native menu. Long labels are visually ellipsized, and the rename
prompt retains the complete label. Unconnected unlabeled channels beyond the
first are removed after disconnect or workflow normalization. Labels are
trimmed to 64 Unicode characters and numbered defaults follow their positions.
Removing a connected channel reconnects its upstream source directly to every
compatible downstream target; a channel is kept if that splice cannot be done
without losing links. Deleting the whole organizer uses ComfyUI's normal
index-matched node bypass. Channel order, labels, types, and links persist in
workflow JSON. Reordering, collapsing, execution modes, routing cycles, and
conversion inside groups or subgraphs are intentionally unsupported.

`LFGG Boolean Switch` and `LFGG Index Switch` are executable lazy nodes in
`LFGG/workflow`, with stable IDs `LFGG_BooleanSwitch` and `LFGG_IndexSwitch`.
The Boolean selector maps `False` to `false` and `True` to `true`; the Index
selector is zero-based. Each switch evaluates only its
selected branch, and a selected missing branch or an invalid selector fails
with an actionable LFGG error. The index node starts with branches `0` and
`1`, adds one trailing branch after its last branch receives a real link, and
never shrinks or renumbers branches (maximum 32). All connected branches and
the `value` output share one propagated wire type. Branch count and type are
saved in workflows; restored disconnected slots do not create branches. Like
other V1 wildcard sockets, `*` may have limitations through native reroutes
and some custom socket types.

`LFGG String Replace` and `LFGG String Replace (Regex)` are in `LFGG/text`,
with stable IDs `LFGG_StringReplace` and `LFGG_StringReplaceRegex`. Both
replace every match and default to `Match case`; disable it for `Ignore case`.
The literal node persists inputs in `text`, `search`, `replacement`,
`case_sensitive` order. The regex node persists `text`, `search`,
`replacement`, `use_regex`, `case_sensitive`; it defaults to `Use regex`,
and `Literal text` makes search and replacement literal. Regex mode supports
inline flags and capture references such as `\1` and `\g<name>`. An empty
search returns the input text unchanged. Malformed regexes, invalid capture
references, non-string inputs, and values over the 1 MiB
text/replacement/output or 4 KiB search limits fail with an actionable error.
These nodes make no file or network I/O. Regexes are locally authored workflow
patterns; Python's standard library engine has no hard match timeout.

`LFGG String Join` is in `LFGG/text`, with stable ID `LFGG_StringJoin`. It
joins connected `text_1` through `text_32` in order with a literal `separator`.
It begins with two inputs and adds one trailing socket after the final input
receives a real link, up to 32; the saved count never shrinks and restored
disconnected sockets do not grow. Missing inputs are omitted, while supplied
empty strings and whitespace are preserved. The separator, each input, and the
joined output are valid UTF-8 text limited to 1 MiB; invalid values fail with an
actionable error. It makes no file or network I/O.

`LFGG Value Inspector` is a terminal output node in `LFGG/debug`. Stable ID
`LFGG_ValueInspector`. Connect any value and queue the workflow to show a
read-only diagnostic report inside the node. One scheduled value is shown
directly; multiple values are numbered. Scalars show bounded content,
containers show at most 50 entries and four levels, and tensors show only type,
shape, dtype, device, and layout. Reports are capped at 16 KiB, individual
strings and byte values at 8 KiB, and obvious credential fields are redacted.
Unknown objects show only their qualified runtime type.

The `*` input is ComfyUI's V1 wildcard escape hatch, so native reroutes and some
custom socket types may have link-type limitations. The report is session-only:
it is not saved into workflow JSON, and a previous report is marked stale while
a later execution is pending or fails. Normal ComfyUI caching applies.
Enlarging the node gives the selectable report more room. Overflow scrolls
inside the report; a separate status line identifies waiting, current, or
stale content without replacing the last successful report.

`LFGG Output Gallery` is a read-only viewer in `LFGG/workflow`. Stable ID
`LFGG_OutputGallery`. It lists the latest gallery items (images, videos, and
audio) saved under one subfolder of the ComfyUI output root and shows them in
the graph without running the workflow. It has no outputs, is never queued,
and does not change execution; without the frontend extension the node still
loads and persists its widgets.

Persisted inputs, in order, are `path` (subfolder relative to the output root;
empty means the root itself), `include_subfolders` (default `true`; recursion
is bounded by the scan cap), `media_filter` (`all`, `images`, `videos`,
`audio`, or one extension among `png`, `jpg`, `webp`, `gif`, `mp4`, `webm`,
`mov`, `mp3`, `wav`, `flac`, `ogg`; `jpeg` files match and are reported as
`jpg`), `name_filter` (case-insensitive substring matched against the path
relative to `path`, so it matches subfolder names as well as filenames),
`sort` (`newest first`, `oldest first`, `name A to Z`, `name Z to A`; time is
file modification time), and `limit` (1 to 200, default 24; one page, no
pagination).

The compact view shows the selected preview with native media controls, a
caption, the item count, and **Refresh**. **Show gallery** adds a lazy tile
grid; **Hide gallery** returns to the compact view. Clicking a tile selects
it. Tiles stay muted and offer a play/pause overlay for videos; audio files and
videos the browser cannot decode show a labeled placeholder tile. The preview
starts muted; its volume and mute state are remembered for the session and
applied to the next selected video or audio item. Selecting an item never
autoplays it, and videos loop. Selection and volume are session-only and are
never saved into the workflow.

A gallery refresh happens on **Refresh**, on any widget change, after a run
you queued finishes (`execution_success`), and when the queue drains after
having been busy (`status`), so a run queued from a second browser tab also
refreshes this one. Bursts collapse into one request within 500 ms; there is
no interval timer. Under `newest first`, newly listed items select the newest
one unless the current selection is playing, in which case the selection stays
and the new items simply appear in the grid. A kept selection survives a
refresh; a missing one clears. States are announced in a polite live region:
`no items match`, loading, stale (the previous list is dimmed while a refresh
is in flight), error (the route message is shown verbatim and the last valid
list is preserved), `list may be incomplete: scan cap reached`, and folder not
found. Each tile and the preview offer **Open** (the `/view` URL in a new
tab), **Copy path** (`subfolder/filename` relative to the output root), and,
for PNG files only, **Load workflow**, which loads the embedded workflow the
same way dropping the file on the canvas would. Tile media loads only while
the grid is shown, the node is not collapsed, and the tile is in view; playing
media pauses when the node leaves view and is released when the node is
removed.

The gallery never lists paths outside the output root and never deletes,
renames, moves, or re-encodes files. Folders on other drives, pagination, and
server-side thumbnails are out of scope.

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

The prompt assistant reads the shared configuration beneath the ComfyUI user
directory and `.md` files proven to resolve inside a configured skills root. It
writes no files. Its only outbound network calls go to the configured
`server.base_url`: `GET /health` at the start of every uncached execution,
`GET /props` when images are attached, `POST /v1/chat/completions` streamed,
and under the `share` policy `GET /models`, `POST /models/unload`, and
`GET /models` polling. The two read-only routes
`GET /lfgg/v1/prompt-assistant/models` and
`GET /lfgg/v1/prompt-assistant/skills` proxy the model list and the
allowlisted skill tree for the picker; they expose model ids, skill names,
file sizes, and configured root paths, never the API key or file contents.
Bounds: 5 s connect timeout, the configured read timeout, one attempt without
retries or redirects, 256 KiB plain responses, streamed replies of 1 MiB plus
1 KiB per `max_tokens` (33 MiB at the 32768 maximum), 64 KiB
configuration, 512 KiB per attachment, 256 KiB attached total, eight images,
and 268,435,456 source pixels per frame. Interrupting the queue closes the
connection, which makes `llama-server` cancel the slot.

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

The value inspector makes no network calls and reads or writes no files. It
returns only its bounded report through ComfyUI's execution UI message.

The output gallery reads only directory listings and file metadata. Its single
read-only route, `GET /lfgg/v1/output-gallery/list`, resolves the ComfyUI
output root, proves the requested subfolder stays inside it after resolving
symlinks, and rejects absolute paths, drive markers, `..`, and symlink escapes
with status 400; a missing subfolder returns 404. The walk uses `os.scandir`,
never follows symlinked directories, skips hidden entries and files that
resolve outside the root, and visits at most 20,000 directory entries (the
scan cap) before reporting the list as truncated. It stats only the files it
returns plus the entries it sorts, reads no file content, caches nothing, and
writes nothing. Like every custom route it has no authentication gate; it
reveals output filenames, subfolders, sizes, and modification times, never
absolute paths. Every image, video, and audio byte is served by ComfyUI's
native `/view` route with `type=output`; the pack serves no bytes of its own
and adds no file-serving route. The frontend makes no other network calls.

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
node --test tests/frontend/prompt_assistant.test.mjs
node --test tests/frontend/routing_organizer.test.mjs
node --test tests/frontend/switches.test.mjs
node --test tests/frontend/string_join.test.mjs
node --test tests/frontend/value_inspector.test.mjs
node --test tests/frontend/output_gallery.test.mjs
python -m ruff check .
python -m pytest -q tests/unit
comfy node validate
comfy node pack
python -m pytest -q tests/package --archive node.zip
python -m pytest -q tests/integration --comfy-ref v0.28.0 --archive node.zip --device cpu
```

The handwritten frontend extension has no generated-asset build. There is no
runtime installer or compatibility `requirements.txt`.
Candidate archive tests check the intended file inventory and bytes against the
current source. Release verification additionally requires
`--approved-release-manifest release/<version>-archive.sha256`; both release
workflow archive checks supply it. Existing approved release manifests are
immutable and are not regenerated for ordinary development changes.

## Release operators

Publishing is restricted to an exact version-matching tag after the complete
qualification workflow passes. The `registry-release` GitHub environment must
require reviewer `lfelipegg`, and its publisher-scoped
`REGISTRY_ACCESS_TOKEN` must exist only as an environment secret.

Registry versions are immutable. If a version is created before a later
release step fails, deprecate it with an actionable replacement and publish an
incremented version; never overwrite or retry the consumed version.
