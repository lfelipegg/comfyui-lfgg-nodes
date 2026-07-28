# Aspect Ratio Preview 1.2.0 Design

Purpose: Define the proposed frontend behavior for `LFGG Dimensions by Aspect
Ratio`.
Read when: implementing or reviewing the aspect-ratio preview and conditional
custom-ratio controls.
Do not read for: image-derived sizing nodes or backend dimension fitting.
Source of truth: the 2026-07-27 design interview, checked against ComfyUI
`v0.28.0` and `comfyui-frontend-package` `1.45.21`.
Last reviewed: 2026-07-27

## Summary

- Add a non-interactive, theme-aware ratio preview directly below
  `aspect_ratio`.
- Preview only the requested proportion; do not reproduce backend alignment or
  serialize additional workflow state.
- Hide custom ratio controls for presets, retain their values, and reveal them
  for `Custom` or a dynamic ratio input.
- Keep the existing node ID, input order, outputs, execution, and ComfyUI
  `v0.28.0` floor unchanged.
- Ship build-free JavaScript as a compatible `1.2.0` feature.

## Preview Meaning and Content

The ratio preview represents the requested width-to-height proportion, not the
aligned dimensions produced from `long_side` and `divisible_by`. It derives
entirely from the existing input values and never affects execution.

Preset labels use their existing values. Custom labels are reduced by their
greatest common divisor, so `1920:1080` displays as `16:9`. The ratio is
centered in the shape with a smaller `Landscape`, `Portrait`, or `Square`
label beneath it. When both labels cannot fit, they move below the shape
together without distorting its geometry. These geometric orientation labels
remain unchanged and do not repeat the selector's use-case descriptions.

Malformed custom values render a neutral `Invalid ratio` state. If any
ratio-driving input is graph-connected and its editor-time value is unknown,
the preview renders a neutral `Dynamic ratio` state instead of stale geometry.
At normal canvas detail, the fixed background grid remains visible in both
neutral states; only the ratio shape is omitted, with the status label centered
above the grid.

## Layout and Drawing

Insert the preview immediately after `aspect_ratio`. Its panel uses the full
available node width and a fixed 120 px height. The panel has a subtle
theme-derived fill and one-pixel border.

Draw a low-contrast 6×6 grid across the panel's inner preview area. Its
geometry is independent of the selected ratio, so changing presets never
changes the background grid. Center and contain the ratio shape without
cropping, then draw it above the grid with a theme-aware opaque fill, outline,
and 6 px corners. Do not add a heading, dashed outline, animation, or fixed
LFGG palette. At low-quality zoom, omit the unreadable grid and labels and draw
only the shape outline.

The preview responds to node width changes. Existing workflows retain their
saved node width and grow in height only when needed to fit the preview.
Switching between presets and `Custom` recomputes the minimum height while
preserving width.

## Conditional Custom Controls

Hide `custom_ratio_width` and `custom_ratio_height` whenever a preset is
selected. Reveal them for `Custom` and whenever `aspect_ratio` is dynamic.
Hiding never resets either value or removes it from workflow serialization.

The preview itself is a non-serialized UI widget. The existing five input
widgets remain the only persisted values. If the frontend extension is absent
or fails to load, the Python node remains fully usable and all five inputs stay
visible.

## Preset Selector Labels

Show each aspect-ratio preset with a concise description of its common use.
This is presentation metadata only: workflows, prompts, and backend validation
continue to use the existing raw values such as `16:9`. Existing workflows
therefore load without migration, and selecting a described option still sends
only its raw ratio value to the backend. Descriptions use generic, durable
format language rather than platform or brand names. The full display label is
visible both in the open option list and in the selector's collapsed state.
If the frontend extension is unavailable, the node remains usable and the
selector falls back to its raw ratio values. Do not resize existing nodes to
fit the longest description; at unusually narrow widths the collapsed label
may use the frontend's native clipping while the open list retains the full
text.

| Value | Display label |
|---|---|
| `1:1` | `1:1 — Square` |
| `4:5` | `4:5 — Social portrait` |
| `5:4` | `5:4 — Landscape print` |
| `3:4` | `3:4 — Portrait` |
| `4:3` | `4:3 — Standard landscape` |
| `2:3` | `2:3 — Poster` |
| `3:2` | `3:2 — Photography` |
| `5:7` | `5:7 — Portrait print` |
| `7:5` | `7:5 — Landscape print` |
| `9:16` | `9:16 — Vertical video` |
| `16:9` | `16:9 — Widescreen` |
| `9:21` | `9:21 — Phone wallpaper` |
| `21:9` | `21:9 — Ultrawide` |
| `Custom` | `Custom — Custom ratio` |

## Frontend Boundary and Compatibility

Limit the binding to `LFGG_DimensionsByAspectRatio`. Keep only pure ratio
normalization and geometry helpers reusable for a possible future node; do not
introduce a preview framework.

Use the documented extension registration hook and the frontend's custom
widget and widget-visibility APIs. Do not poll, monkey-patch frontend globals,
replace shared callbacks, add routes, or add a build tool. Export
`WEB_DIRECTORY` and declare
`comfyui-frontend-package>=1.45.21`, matching the frontend bundled with
ComfyUI `v0.28.0`.

## Release and Verification

Keep the changes in the untagged, unpublished `1.2.0` candidate. Preserve the
backend schema manifest exactly; the release adds packaged browser behavior and
compatibility metadata only. Regenerate the approved archive manifest after
the browser assets change. Update package/archive expectations and README
statements that currently say no frontend exists.

Leave one dependency-free `node --test` check covering ratio reduction,
geometry, invalid and dynamic states, and custom-widget visibility. Before
release, manually verify the packed node in ComfyUI at frontend `1.45.21` and
current stable, including dark/light themes, preset/custom switching, retained
custom values, node resizing, workflow reload, low zoom, and JavaScript-disabled
fallback.
