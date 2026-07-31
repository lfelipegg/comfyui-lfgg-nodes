# Power LoRA Loader Folder Design

Purpose: Define the accepted contract and interaction model for a standalone
multi-LoRA loader whose chooser is scoped by a workflow-saved folder.
Read when: implementing, reviewing, or qualifying
`LFGG Power LoRA Loader (Folder)`.
Do not read for: the deferred single-LoRA loader by path or changes to
rgthree-comfy.
Source of truth: the 2026-07-30 design interview, the repository's ComfyUI
research snapshot, and rgthree-comfy's current Power LoRA Loader behavior
inspected on 2026-07-30.
Last reviewed: 2026-07-30

## Summary

- Add the standalone V1 node `LFGG_PowerLoraLoaderFolder`, displayed as
  `LFGG Power LoRA Loader (Folder)` under `LFGG/loaders`.
- Accept a model and CLIP, then apply any number of ordered LoRA rows with
  per-row enable, model-strength, and CLIP-strength controls.
- Add a visible, workflow-saved `Folder` combo that recursively filters only
  future LoRA selections.
- Keep existing rows unchanged when the folder changes.
- Reuse ComfyUI's LoRA discovery and loading behavior; add no rgthree
  dependency, server route, package dependency, or frontend build step.

## Public Contract

Register exactly one new V1 node:

| Field | Value |
|---|---|
| Node ID | `LFGG_PowerLoraLoaderFolder` |
| Display name | `LFGG Power LoRA Loader (Folder)` |
| Category | `LFGG/loaders` |
| Required inputs | `MODEL` named `model`; `CLIP` named `clip` |
| Outputs | `MODEL` named `model`; `CLIP` named `clip` |

The node also persists:

- `folder`, a non-connectable combo used only to scope the chooser;
- the current add-row LoRA choice; and
- ordered dynamic `lora_N` rows containing `on`, `lora`,
  `strength_model`, and `strength_clip`.

Dynamic row identifiers are an implementation detail, but their serialized
values and order are workflow API. The backend must accept valid prompt/API
submissions without trusting the frontend.

## Folder and Chooser Behavior

Build the folder and LoRA catalogs from ComfyUI's registered `loras` filenames.
Normalize separators to `/` for comparison and workflow display. Infer every
non-empty parent folder represented by at least one LoRA; empty filesystem
directories do not need to appear.

Sort folders and LoRA filenames deterministically. The folder combo contains
`All LoRAs` plus every inferred folder, including nested folders. For a new
node, default to the first actual folder when one exists and otherwise to
`All LoRAs`.

Selecting `characters` includes every LoRA whose normalized relative name
starts with `characters/`, including files beneath
`characters/anime/portraits`. Selecting `characters/anime` narrows the same
way. `All LoRAs` disables prefix filtering.

The chooser displays names relative to the selected folder for readability,
but each row stores the complete ComfyUI-relative LoRA filename. Folder
changes update only the choices available for the next added row. They never
remove, disable, rename, or otherwise mutate existing rows, including rows
outside the newly selected folder.

Refreshing node definitions refreshes both catalogs. If a saved folder no
longer exists, preserve it visibly as missing and show no addable choices
until the user selects an available folder. Existing valid rows remain
executable.

## Row Interaction and Persistence

Use a focused build-free frontend extension bound only to
`LFGG_PowerLoraLoaderFolder`. Keep the visible `Folder` and add-row selector as
ordinary combo widgets. Add the minimum custom UI needed for compact dynamic
rows and row controls.

The node provides:

- an `Add LoRA` action;
- any number of ordered LoRA rows;
- one enable toggle per row;
- separate model and CLIP strengths per row, defaulting to `1.0`;
- move-up, move-down, and remove actions per row; and
- one toggle-all control.

Do not add rgthree's model-information dialog, trained-word integration,
templates, regex matching property, or other pack-specific services.

Save the folder, current chooser value, complete row values, and row order in
the workflow. Reopening the workflow restores them exactly. Adding and moving
rows must keep stable unique row keys within that node so prompt serialization
cannot overwrite another row.

## Execution Flow

1. Accept the required model and CLIP plus the ordered dynamic row payloads.
2. Validate every submitted row before applying any LoRA.
3. Walk rows in UI order.
4. Skip rows that are disabled or whose model and CLIP strengths are both
   zero.
5. Delegate each remaining load to ComfyUI's native LoRA loader so native
   deserialization, caching, metadata handling, and model/CLIP application
   remain authoritative.
6. Feed each result into the next row and return the final model and CLIP.

The selected folder is not an execution boundary. A row remains valid when
its LoRA lies outside the currently selected folder because folder changes
intentionally affect only future selection.

## Validation and Filesystem Boundary

Treat frontend payloads as untrusted. Before loading, require:

- a mapping with exactly the supported row fields;
- a Boolean enabled state;
- a non-empty string LoRA name;
- finite numeric strengths within the documented ComfyUI-style range; and
- a filename currently registered beneath a LoRA root.

Resolve the selected file at the point of access and prove that its real path
remains beneath one of ComfyUI's registered LoRA roots. Reject traversal,
absolute paths, drive markers, missing files, unknown names, and symlink
escape with actionable `LFGG` errors.

Validate the complete active row set before loading the first LoRA so one bad
later row cannot produce partially transformed in-memory outputs before the
error is reported. Disabled rows do not access their files.

The node performs no network calls or file writes. Imports remain fast and
side-effect-free; ComfyUI-heavy imports and filesystem discovery occur only
at schema or execution boundaries.

## Frontend Failure Boundary

The Python node remains importable and its definition remains JSON-safe when
the frontend extension is unavailable. Dynamic row authoring is a frontend
feature, so a missing extension should produce a clear empty-row or malformed
row validation error rather than guess at UI state.

Use the documented extension registration lifecycle and local node methods.
Do not patch frontend globals, another custom-node pack, or ComfyUI
prototypes. Do not add a backend route: the normal node definition already
supplies the folder and LoRA combo catalogs required by the UI.

## Compatibility and Release

Target the next additive package version, `1.5.0`, without changing:

- ComfyUI `>=0.28.0`;
- ComfyUI frontend package `>=1.45.21`;
- Python `>=3.10,<3.14`;
- Linux and Windows support; or
- CPU and NVIDIA CUDA qualification.

The implementation may study rgthree-comfy's MIT-licensed interaction model,
but should use project-local code and ComfyUI APIs rather than import
rgthree's private modules. Preserve any required attribution if substantial
source is adapted.

Publication is not part of implementation and remains tag-gated and manually
approved.

## Verification

Leave focused Python unit checks for:

- deterministic nested-folder inference and recursive filtering;
- separator normalization and complete stored filenames;
- ordered loading and result chaining;
- disabled and both-zero row skips;
- malformed row values and non-finite/out-of-range strengths;
- unknown, missing, traversing, absolute, and symlink-escaping files;
- validation of all active rows before the first load; and
- V1 schema, prefixed registration, JSON-safe object info, and lazy imports.

Leave dependency-free frontend checks for:

- `All LoRAs`, parent-folder, and nested-folder filtering;
- relative display names with complete serialized filenames;
- adding, toggling, reordering, removing, and toggling all rows;
- folder changes preserving existing rows;
- stable unique row keys; and
- workflow serialization and restoration, including a missing saved folder.

Extend package expectations for the new Python and frontend files. Run the
canonical lint, unit, frontend, validation, packing, package, and packed
integration gates documented in `README.md`. Manually smoke-test the node
against minimum and current supported ComfyUI/frontend versions with LoRAs in
root, parent, and nested folders.

Do not add an example workflow initially. A runnable example would require a
redistributable LoRA asset or an undocumented external prerequisite.

## Deferred Work

The first version intentionally excludes:

- rgthree compatibility or dependency;
- regex and multi-folder filters;
- folder connections or graph-driven filtering;
- model-information and trained-word services;
- templates and presets;
- trigger-word or LoRA-name outputs;
- server routes;
- an example workflow requiring an external LoRA; and
- a reusable dynamic-row framework.

Add one only after a concrete workflow demonstrates that the accepted node
contract is insufficient.
