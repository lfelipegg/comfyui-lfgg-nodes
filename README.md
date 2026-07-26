# LFGG Nodes

Small, explicit workflow utility nodes for ComfyUI.

## Install

Until the first Registry release, clone this repository into ComfyUI's
`custom_nodes` directory:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/lfelipegg/comfyui-lfgg-nodes.git lfgg-nodes
```

Restart ComfyUI after installation. This sizing-only release has no runtime
dependency and no frontend extension.

## Compatibility

- ComfyUI `>=0.28.0`
- Python `>=3.10,<3.14`
- Linux and Windows
- CPU and NVIDIA CUDA workflows

The sizing node performs standard-library integer math only. It does not
allocate or inspect tensors, use an accelerator, access the network, or read or
write files.

## LFGG Dimensions by Aspect Ratio

`LFGG_DimensionsByAspectRatio` returns positive `width` and `height` integers
in the `LFGG/sizing` category. It fits a stable preset or custom ratio under
`long_side`, with both axes aligned to the exact `divisible_by` value.

Limits are hard ceilings: the node never rounds an axis above `long_side` or
ComfyUI's `MAX_RESOLUTION`. Candidate dimensions are chosen by symmetric
relative aspect error, then pixel area, then long-axis and short-axis size.
Invalid API values and alignments that cannot produce positive dimensions
raise actionable errors.

Presets: `1:1`, `4:5`, `5:4`, `3:4`, `4:3`, `2:3`, `3:2`, `5:7`, `7:5`,
`9:16`, `16:9`, `9:21`, and `21:9`. Select `Custom` to use
`custom_ratio_width` and `custom_ratio_height`.

The tracked
[API workflow](workflows/dimensions_by_aspect_ratio.json) connects the returned
dimensions to ComfyUI's native `EmptyLatentImage` and `SaveLatent` nodes. The
example writes a `.latent` file; `LFGG Dimensions by Aspect Ratio` itself does
not write files.

## Migrate from LfggLatentSizeByRatio

Replace `LfggLatentSizeByRatio` manually with
`LFGG_DimensionsByAspectRatio`:

1. Map `base_size` to `long_side` and retain the ratio/custom values.
2. Move `batch_size` and latent creation to the native initializer appropriate
   for the model family.
3. To preserve the legacy effective alignment, set `divisible_by` to
   `lcm(8, legacy_divisible_by)`; otherwise the new node honors the chosen value
   exactly.

Dimensions may change where the legacy node rounded beyond a cap or selected a
poorer aspect match. No legacy workflow ID is registered.

## Develop

```bash
python -m pip install -e ".[dev]"
python -m ruff check .
python -m pytest -q tests/unit
```

There is no generated-asset build or compatibility `requirements.txt`.
