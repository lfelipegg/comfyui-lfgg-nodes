# Composition Image by Aspect Ratio Design

Purpose: Define the approved composition-image generator contract.
Read when: Implementing or verifying the composition-image node.
Source of truth: Confirmed design interview on 2026-09-16.
Status: Approved design; not implemented by this document.

## Goal and evidence boundary

Generate abstract composition seed images for downstream VAE encoding and
img2img-style sampling. The reference is
`docs/reference/image-variance/image-variance.png`; use its composition ideas,
not copied artwork. Its sampling advice is anecdotal, not a verified Krea 2
recipe. Acceptance covers generator correctness and visible composition
variation, not demonstrated improvement in final model outputs.

A composition seed image influences spatial structure or color; it is not
pixel noise or an empty latent. A composition family describes an organizing
principle, not a fixed reference tile.

## Node boundary

- Display name: `LFGG Composition Image by Aspect Ratio`.
- New registration ID: `LFGG_CompositionImageByAspectRatio`.
- Outputs, in order: standard ComfyUI `IMAGE` batch, `width`, `height`.
- No VAE input, latent output, preliminary sampling, or denoise controls.
- Leave `LFGG Dimensions by Aspect Ratio` unchanged. It currently produces
  width and height, not a latent.
- Reuse its sizing behavior, preset/custom aspect-ratio controls, `long_side`,
  `divisible_by`, custom ratio fields, sizing defaults, and ratio preview.
- The ratio preview represents the requested proportion, not generated pixels.
- Inspect actual output using native downstream `Preview Image`; do not add
  generator-owned previews or preview file writes.

Suggested connection: composition image → native VAE Encode → sampling workflow.
The sampler's seed and the composition seed are independent.

## Composition controls

### Family

Provide the following families and a Random option:

1. Scattered clusters.
2. Regular or jittered grids.
3. Directional bands or diagonal arrangements.
4. Concentric or radial arrangements.
5. Large area partitions.
6. Gradient fields with optional shapes.

Generate variations within each family rather than selecting copied tiles.
Default: Random.

### Palette

Provide monochrome, grayscale, muted color, vivid color, and Random modes.
Use coordinated palettes rather than unrestricted independent RGB colors.
Default: monochrome.

Monochrome means black and white except for intermediate values at smoothed
boundaries. Grayscale permits intermediate tones throughout. Family rendering
must respect the selected palette: monochrome cannot silently introduce a
continuous tonal gradient. Tonal regions or a thresholded field can express
the gradient family's spatial direction in monochrome mode.

### Complexity

One normalized low-to-high control, default 0.5. Interpret it within each
family, coordinating shape count, size, spacing, and overlap. It is not an
exact shape count or an independent coverage setting.

### Geometry

Generate directly in the requested rectangular canvas; do not stretch square
art to fit. Preserve individual shape proportions. The vocabulary includes
rectangles, squares and diamonds, circles, and triangles. Allow intentional
overlap and edge clipping where appropriate to the family. Smooth boundaries.

## Seed and batches

- Explicit composition seed; default 0.
- Native seed control may randomize between executions.
- Explicit batch size; default 1.
- Fixed inputs reproduce the same ordered pixel batch.
- Each batch item receives its own generated composition, not a copied image.
- Increasing batch size preserves all earlier batch items.
- Random family and palette selections happen independently per image.
- Explicit family and palette selections stay fixed across the batch, while
  generated details vary.
- Do not promise that every seed produces unique pixels; finite output spaces
  and constrained settings can produce collisions.

## Output and resource boundary

Return standard ComfyUI RGB images with a batch axis and valid normalized
pixel values. All batch items have the returned width and height.

Reject requests whose aligned output width × height × batch size exceeds
16,777,216 pixels, before allocating the output batch. Do not silently clamp
batch size or resize output. At this limit, RGB float32 output alone occupies
192 MiB. Render batch items sequentially to bound additional working memory;
the implementation must also bound any smoothing/intermediate buffers.

Examples at the total-pixel limit: 16 images at 1024 × 1024, or four images at
2048 × 2048. This is an output allocation guard, not a guarantee that downstream
VAE encoding or sampling will fit available memory.

## Verification and acceptance

Verify observable contracts:

- Same seed and controls reproduce identical pixels.
- Increasing batch size leaves earlier images unchanged.
- Explicit family/palette choices remain respected across a batch.
- Random choices are per item, not selected once for the entire batch.
- Output dimensions follow the existing sizing/alignment policy.
- Output uses valid standard RGB image tensor shape and normalized finite values.
- Over-budget requests fail before output allocation; the boundary is accepted.
- Invalid execution inputs fail actionably rather than returning blank images.

Visually inspect representative seeded outputs for every family and palette,
including square, portrait, and landscape canvases, and low/high complexity.
Check preserved proportions, intended organizing structure, intentional clipping,
and smoothed edges. Verify the actual ComfyUI surface and downstream image
preview when implementing, including restored sizing controls and node metadata.
Do not claim visual or runtime verification from this design document alone.

## Non-goals

No shape editor, custom color inputs, exact shape-count control, coverage slider,
live image preview, model-specific latent initializer, sampler wrapper, network
fetching, or image file export. No changes to existing registration IDs or
persisted sizing-node contracts. No claim that the screenshot's denoise values
are universally appropriate or that generator-level variation proves improved
Krea 2 output diversity.
