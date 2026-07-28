# Resize Image by Long Side 1.4.0 Design

Purpose: Define the accepted contract for the image-producing counterpart to
`LFGG Image Dimensions by Long Side`.
Read when: implementing, reviewing, or qualifying
`LFGG Resize Image by Long Side`.
Do not read for: pixel-budget resizing, cropping, padding, or image loading.
Source of truth: the 2026-07-28 design interview, checked against ComfyUI's V1
`ImageScale` and `comfy.utils.common_upscale` contracts.
Last reviewed: 2026-07-28

## Summary

- Add V1 node `LFGG_ResizeImageByLongSide`, displayed as
  `LFGG Resize Image by Long Side` under `LFGG/image`.
- Reuse `LFGG Image Dimensions by Long Side` sizing exactly, then resample the
  full image to those dimensions.
- Return `IMAGE`, `width`, and `height`; leave the existing sizing node
  unchanged.
- Ship the additive node as `1.4.0` without changing the ComfyUI, frontend,
  Python, OS, or accelerator compatibility floors.

## Public Contract

Persist inputs in this order:

1. `image`: the `IMAGE` batch to resize.
2. `upscale_method`: `lanczos` by default, with native `nearest-exact`,
   `bilinear`, `area`, and `bicubic` alternatives.
3. `long_side`: the existing downscale-only long-axis ceiling.
4. `divisible_by`: the existing exact output alignment.

Return the resized `IMAGE`, aligned `width`, and aligned `height` in that order.
The node accepts and returns ComfyUI `[B,H,W,C]` tensors and preserves the batch.
Accept finite floating-point tensors with 1, 3, or 4 channels and at most
268,435,456 pixels across the batch. Validate this boundary before the identity
shortcut or resampler.

## Sizing and Resampling

Use the existing long-side calculator as the single sizing policy. For the same
image, `long_side`, and `divisible_by`, both nodes must return identical
dimensions. The policy never enlarges either source axis, chooses an exact
aligned source ratio when one fits, and otherwise chooses the closest aligned
ratio beneath the ceiling.

Resample the complete image directly to the selected dimensions with cropping
disabled. The closest-ratio fallback may introduce the same small
alignment-induced aspect change already represented by the sizing node.

When selected dimensions equal the source dimensions, return the original
tensor object without invoking a resampler. Reject unknown method values during
execution, including on this no-op path.

## Compatibility and Qualification

Use V1 `NODE_CLASS_MAPPINGS` and ComfyUI's existing
`comfy.utils.common_upscale`; add no dependency, frontend code, route, file
access, or network access. Preserve ComfyUI `>=0.28.0` and frontend
`>=1.45.21`.

Qualification covers exact public schema and registration, shared sizing,
native method forwarding, BHWC/BCHW boundary adaptation, batch preservation,
the identity no-op, invalid-method rejection, the release manifest, and a
tracked API workflow.
