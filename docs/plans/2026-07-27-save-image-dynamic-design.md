# Save Image Dynamic 1.1.0 Design

Purpose: Define the approved implementation shape for GitHub issue #16.
Read when: implementing or reviewing `LFGG_SaveImageDynamic`.
Do not read for: unrelated image, prompt, or loader nodes.
Source of truth: issue #10 comment 5085601649 and issue #16, checked against
ComfyUI `v0.28.0`.
Last reviewed: 2026-07-27

## Summary

- Add one V1 output node with no graph output, frontend, route, or legacy alias.
- Keep templates, image conversion, and metadata preparation in one runtime
  module; import ComfyUI globals lazily at the execution boundary.
- Reserve PNGs with exclusive creation beneath the resolved ComfyUI output
  root and roll back only files created by the failed execution.
- Add Pillow as the only runtime dependency and qualify the `1.1.0` archive
  with one model-free dynamic-save workflow.

## Selected Approach

Issue #10 considered dropping the legacy node in favor of core `SaveImage`,
preserving the legacy implementation, and keeping only the distinct
path/filename-template job while mirroring core save conventions. The accepted
third option is the smallest one that retains the useful behavior without
preserving percent tokens, absolute paths, compression control, `saved_paths`,
or old security defects.

`lfgg_nodes/save_image_dynamic.py` owns the node and its directly used helpers.
The helpers use `string.Formatter`, `pathlib`, `json`, and Pillow. Torch,
`folder_paths`, and `comfy.cli_args.args` are imported only where their runtime
values are needed. No shared abstraction is added because this is the first
file-writing node.

## Execution Flow

At execution start, capture one local timestamp. Validate both template
grammars and lengths, the complete real Torch `[B,H,W,C]` batch, and selected
metadata before creating files. Pre-render every frame at counter one to catch
invalid components and bounds early.

Resolve `folder_paths.get_output_directory()` once. For each frame, render and
sanitize a relative subfolder and PNG stem. Resolve and contain the prospective
parent, create it, then resolve and contain it again immediately before
opening. Open the candidate with `xb`; on collision, advance the counter and
retry. Keep the handle open while Pillow writes compression level 4.

Track each successfully reserved path immediately. Any later validation,
encoding, metadata, or write failure closes the active handle and unlinks only
those tracked files. Returned UI descriptors contain only `filename`,
output-relative `subfolder`, and `type: "output"`.

## Validation and Security

Use `string.Formatter.parse()` and reject unknown fields, conversions, format
specifications, malformed braces, over-512-character templates, and rendered
components or stems over 200 characters. Treat both slash styles as path
separators, reject absolute/drive-qualified paths and `..`, normalize illegal
component characters, protect Windows reserved names, and reject an empty
filename. Counters are decimal `00001` through `99999`; exhaustion fails
without overwrite.

Accept numeric finite Torch tensors only, with a non-empty batch, positive
spatial dimensions, one, three, or four channels, and no more than
`16_384**2` aggregate batch pixels. Copy each frame to CPU only for clamping
and 8-bit PNG encoding; never mutate the input.

Serialize prompt and every `EXTRA_PNGINFO` value with the standard JSON
encoder only when both metadata toggles allow it. Reject non-string metadata
keys, serialization failures, and aggregate encoded metadata over 64 MiB
before reserving files. Errors identify the input or output-relative
destination but never include absolute paths or metadata values.

## Release and Verification

Version the package and schema as `1.1.0`, declare Pillow, register the one new
ID, add `workflows/save_image_dynamic.json`, and document exact writes plus
manual migration. Extend existing contract, archive, and packed-integration
tests instead of adding another runner.

Use test-first slices for template/path behavior, real Torch/Pillow saving,
exclusive collision/rollback behavior, registration/artifacts, and packed
workflow verification. The packed workflow uses only core `EmptyImage` plus
this node and covers metadata on/off and counter collisions.
