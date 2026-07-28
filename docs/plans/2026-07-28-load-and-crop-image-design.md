# Load and Crop Image 1.3.0 Design

Purpose: Define the accepted contract and interaction model for the first
interactive crop node in LFGG Nodes.
Read when: implementing, reviewing, or qualifying `LFGG Load and Crop Image`.
Do not read for: general image resizing, connected-image crop nodes, or
multi-frame image processing.
Source of truth: the 2026-07-28 design interview, checked against ComfyUI
`v0.28.0` and `comfyui-frontend-package` `1.45.21`.
Last reviewed: 2026-07-28

## Summary

- Add the V1 node `LFGG_LoadAndCropImage`, displayed as
  `LFGG Load and Crop Image` under `LFGG/image`.
- Let the node select or upload one still image, edit an exact-ratio crop
  frame, and return cropped `IMAGE` and `MASK` values without resampling.
- Persist the selected file, ratio, and source-pixel crop rectangle.
- Use a build-free, theme-aware canvas widget plus standard numeric controls;
  add no route, dependency, build tool, or general crop framework.
- Allow ratio connections. Resolve local and constant values before execution,
  and resolve arbitrary computed values through normal node execution.
- Ship the additive node as `1.3.0` without changing the existing ComfyUI,
  frontend, Python, OS, or accelerator compatibility floors.

## Public Contract

Register exactly one new V1 node:

| Field | Value |
|---|---|
| Node ID | `LFGG_LoadAndCropImage` |
| Display name | `LFGG Load and Crop Image` |
| Category | `LFGG/image` |
| Outputs | `IMAGE` named `image`; `MASK` named `mask` |

The persisted inputs are:

| Input | Meaning |
|---|---|
| `image` | A still image selected from or uploaded into ComfyUI's input directory |
| `ratio_width` | Positive width component of the crop ratio; default `1` |
| `ratio_height` | Positive height component of the crop ratio; default `1` |
| `crop_x` | Left edge in oriented source-image pixels |
| `crop_y` | Top edge in oriented source-image pixels |
| `crop_width` | Crop width in source-image pixels |
| `crop_height` | Derived crop height in source-image pixels |

`ratio_width` and `ratio_height` remain connectable `INT` controls. Crop
coordinates are local editor state rather than graph-driven inputs. The
frontend makes `crop_height` read-only and keeps it synchronized with
`crop_width` and the resolved ratio. Backend validation remains authoritative
for workflows submitted without the frontend.

Workflow compatibility treats the node ID, input names and order, output order
and types, coordinate origin, and whole-pixel crop meaning as public API.

## Source Image Boundary

Use ComfyUI's native input upload, selection, and view mechanisms. The node does
not accept URLs, arbitrary filesystem paths, or an `IMAGE` socket.

Resolve the selected file and prove containment within the allowed ComfyUI
input root at the point of access. Reject absolute paths, traversal, symlink
escape, missing files, corrupt files, unsupported decoded content, and images
above the enforced pixel limit.

Apply EXIF orientation before establishing coordinates, previewing, or
cropping. Accept exactly one still frame. Reject animated and other multi-frame
files rather than selecting a frame silently.

Follow native ComfyUI load-image channel behavior: return an RGB `IMAGE` tensor
and a `MASK` derived from alpha when present, or an empty mask when it is not.
Crop both outputs with the same coordinates. Use content-based change
detection so replacing the selected input invalidates cached execution.

## Crop Geometry

Reduce the positive ratio components by their greatest common divisor. For a
reduced ratio `rw:rh`, every valid crop has:

```text
crop_width  = scale × rw
crop_height = scale × rh
```

where `scale` is a positive integer. The node only removes source pixels; it
never resizes, interpolates, pads, or resamples.

The largest centered crop uses the greatest scale that fits the oriented source
dimensions. When integer centering leaves one unmatched pixel, place it on the
right or bottom for deterministic top-left coordinates. If even the reduced
ratio cannot fit once, report that the ratio is invalid for the selected image.

The crop rectangle must have positive dimensions, start at non-negative
top-left coordinates, match the resolved ratio exactly, and remain completely
inside the image.

## Preview and Interaction

Add a dedicated build-free canvas widget bound only to
`LFGG_LoadAndCropImage`. Reuse the extension lifecycle and current canvas
pointer API already used by the pack; keep pure ratio and rectangle geometry
separate from ComfyUI objects for dependency-free tests.

The preview uses a bounded viewport about 360 pixels tall by default. Contain
the entire image and letterbox it when necessary. Widening the node enlarges
the preview, but portrait images do not force extremely tall nodes. Display
resizing never changes source-pixel crop coordinates.

At normal canvas quality:

- dim pixels outside the crop frame;
- leave retained pixels unobscured;
- draw a theme-derived frame border and four visible corner handles; and
- show the exact cropped `width × height`.

Do not add a composition grid, fixed LFGG palette, animation, or decorative
controls. At low-quality graph zoom, omit details that are not legible while
retaining the crop boundary.

Dragging inside the frame moves it without changing its size. Dragging one of
the four corner handles keeps the opposite corner fixed and changes the
integer scale while preserving the ratio. Movement and resizing stop at image
boundaries.

Visible `X`, `Y`, and crop-width controls stay synchronized with pointer
interaction. Crop height is derived and displayed read-only. Typed values snap
to the nearest valid ratio-preserving size and clamp into the image, with the
normalized values shown immediately.

## Initialization and Persistence

Selecting a new image or changing the resolved ratio resets to the largest
centered crop. Save the selected image, ratio controls, and crop rectangle with
the workflow. Reloading the same workflow and image restores the same crop.
Resizing the graph node affects only display scale.

The all-zero crop size represents uninitialized editor state. The backend
normalizes that state to the largest centered crop. A persisted crop whose
reduced dimensions do not match the currently resolved ratio also resets to
the largest centered crop; this is the intentional dynamic-ratio transition.
For an already matching ratio, malformed or out-of-bounds persisted/API
geometry fails with an actionable error instead of silently changing the crop.

## Connected Ratio Values

When both ratio values are local controls, update the crop immediately. A
frontend resolver may also follow graph links through supported reroutes to a
constant or Primitive numeric widget whose value is unambiguous before
execution.

Do not guess, evaluate arbitrary upstream graphs in the browser, or reproduce
other nodes' execution logic. If either connected value is not statically
resolvable, show `Run to resolve connected ratio` and disable crop editing.

Normal backend execution resolves arbitrary connected ratio values. If the
frame is uninitialized or belongs to another ratio, that execution returns the
largest centered cropped outputs and includes the resolved ratio and rectangle
in standard UI execution data. The frontend applies that data and enables
editing. The user reruns only when they want a custom frame rather than the
automatic centered crop. A later connected-ratio change resets in the same
way.

## Execution Flow

1. Resolve and safely open the selected still image.
2. Apply orientation and convert it to standard ComfyUI image and mask tensors.
3. Validate and reduce the resolved ratio.
4. Select the persisted frame or intentionally initialize/reset it.
5. Validate exact ratio, positive dimensions, and image containment.
6. Slice image and mask directly while preserving batch dimensions and dtype.
7. Return `(IMAGE, MASK)` plus standard UI data containing the resolved ratio
   and actual crop rectangle.

The node performs no network access and writes no files. Imports and schema
discovery remain fast and side-effect-free.

## Frontend Failure and Accessibility

If the frontend extension is missing or fails to load, the image selector and
numeric inputs remain available and backend execution still produces the
defined outputs. Only direct preview manipulation is unavailable.

The visible numeric controls provide keyboard-accessible precision editing.
Pointer targets must remain visibly distinguishable and large enough to
operate at the supported graph zoom levels. Theme-derived colors must preserve
the image itself and make the crop boundary distinguishable in both light and
dark themes.

## Architecture Boundary

Keep the transformation ComfyUI-independent. A small Python geometry function
owns ratio reduction, largest-fit initialization, and strict rectangle
validation. The V1 node adapts ComfyUI input files, Pillow images, tensors,
masks, and UI envelopes at the boundary.

Keep the browser implementation local to this node. Reuse existing pure ratio
normalization or fit helpers only where their contract already matches; do not
create a preview framework. Use one loader module registered through the
documented extension hook and one testable ES module for crop state, geometry,
drawing, and pointer updates.

Do not add backend routes, frontend-global patches, polling, a DOM overlay,
generated assets, or a JavaScript build step.

## Compatibility and Release

Version the additive public schema as `1.3.0`. Preserve:

- ComfyUI `>=0.28.0`;
- ComfyUI frontend `>=1.45.21`;
- Python `>=3.10,<3.14`;
- Linux and Windows; and
- CPU and NVIDIA CUDA qualification.

Update the package schema manifest, archive manifest, tracked workflow,
README, package/integration expectations, and release changelog together.
Publication remains tag-gated, remotely qualified, and separately approved.

## Verification

Leave focused Python unit checks for:

- ratio reduction, exact integer scaling, centering, snapping, and bounds;
- uninitialized and changed-ratio resets versus malformed matching-ratio state;
- still-image enforcement, orientation, RGB/alpha conversion, and file
  containment;
- real tensor image/mask crops with preserved shapes and dtype; and
- V1 schema, registration prefixes, outputs, and duplicate rejection.

Leave dependency-free frontend checks for:

- source-to-preview coordinate mapping and bounded layout;
- frame initialization, movement, corner resizing, snapping, and clamping;
- numeric synchronization and workflow serialization;
- immediate local/constant ratio resolution;
- unresolved computed connections and execution-result application; and
- JavaScript-disabled input fallback.

Extend packed integration with a small known input fixture and assert the
cropped `IMAGE` and `MASK` contents. Qualify the packed archive at the minimum
and current supported ComfyUI/frontend versions. Manually exercise upload,
light/dark themes, zoom, node resizing, workflow reload, pointer and numeric
editing, constant and computed ratio connections, invalid inputs, and
frontend-disabled fallback.

Run the canonical gates documented in `README.md`; do not publish as part of
implementation.

## Deferred Work

The first version intentionally excludes:

- animated or multi-frame images;
- connected `IMAGE` inputs;
- URLs and arbitrary paths;
- composition grids;
- crop resizing or resampling;
- arbitrary upstream graph evaluation before execution; and
- a reusable crop editor framework.

Add one only after a concrete workflow demonstrates that the accepted node
contract is insufficient.
