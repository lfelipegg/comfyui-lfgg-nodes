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
together without distorting its geometry.

Malformed custom values render a neutral `Invalid ratio` state. If any
ratio-driving input is graph-connected and its editor-time value is unknown,
the preview renders a neutral `Dynamic ratio` state instead of stale geometry.

## Layout and Drawing

Insert the preview immediately after `aspect_ratio`. Its panel uses the full
available node width and a fixed 120 px height. The panel has a subtle
theme-derived fill and one-pixel border.

Center and contain the ratio shape without cropping. Give it a theme-aware
fill, outline, 6 px corners, and a low-contrast 6×6 grid clipped inside the
shape. Do not add a heading, dashed outline, animation, or fixed LFGG palette.
At low-quality zoom, draw only the shape outline.

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

Target package version `1.2.0`. Preserve the backend schema manifest exactly;
the release adds packaged browser assets and compatibility metadata only.
Update package/archive expectations and README statements that currently say
no frontend exists.

Leave one dependency-free `node --test` check covering ratio reduction,
geometry, invalid and dynamic states, and custom-widget visibility. Before
release, manually verify the packed node in ComfyUI at frontend `1.45.21` and
current stable, including dark/light themes, preset/custom switching, retained
custom values, node resizing, workflow reload, low zoom, and JavaScript-disabled
fallback.
