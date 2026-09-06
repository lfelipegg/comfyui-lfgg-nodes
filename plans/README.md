# Implementation Plans

Read the complete plan before implementation. Planning approval does not authorize
publication, dependency installation, backend contract changes, or committing work.

## Execution order and status

| Plan | Title | Priority | Effort | Dependencies | Status |
|---|---|---|---|---|---|
| [001](001-comfyui-native-node-redesign.md) | Unify custom node presentation and redesign LoRA rows first | P1 | L | None | DONE — implemented and qualified on both supported renderer hosts |

Plan 001 was confirmed through the OMP design interview on 2026-09-06 and scoped
against source revision `ec43992` plus inspected working-tree files. It is a
single end-to-end redesign, not seven independent plans with duplicated contracts.

## Milestones

1. Establish runtime and existing workflow/renderer evidence.
2. Shared theme/control treatment and adaptive LoRA rows: first usable milestone.
3. Prompt Composer, ratio preview, Value Inspector and Routing Organizer.
4. Shared media expansion state, responsive crop presentation and video timeline.
5. Full visual/behavioral qualification, packaging and user-facing documentation.

Shared modules land before surface work. Crop and video introduce their shared
presentation state together. One integration owner is responsible for the whole
plan; completion of the first milestone does not mean the plan is DONE.

## Confirmed direction

All existing custom layouts; comfortable spacing; adaptive LoRA rows;
basename-first filenames with distinguishing folder context; a small muted-teal
identity marker; compact media previews with inline expansion; per-node saved
expansion. Preserve native-only node visuals and all execution contracts.

## Considered and rejected

- LoRA-only scope: the user explicitly chose all custom UI layouts.
- Fixed one-line or always-stacked LoRA rows: the user selected adaptive rows.
- Compact/comfortable density preference: one comfortable treatment was selected.
- A distinct branded skin or accented primary buttons: use only the small marker.
- Separate media dialogs/sidebar: use inline expansion instead.
- Session-only expansion: the user authorized the optional workflow property.
- Red/green alone for enabled state, horizontally compressed filenames, and
  globally recolored nodes: not acceptable solutions to the identified problems.
- New glossary/ADR material: no new domain term or hard-to-reverse architectural
  choice requires it; the existing domain and persistence decisions still apply.

## Evidence and indexing

The plan contains current-source anchors, scoped files, phase gates, regression
scenarios, real-browser acceptance, and explicit environmental limitations.
No product code was implemented during planning. Track subsequent implementation
evidence in the plan before changing this index to DONE.

Plan 001's final qualification records the shipped implementation and evidence:
134 frontend tests passed; Ruff and node validation passed; 339 Python unit
tests passed, 2 skipped. Candidate package checks passed 28 tests, 1 skipped;
the final extracted archive passed 53 minimum-host integration tests, 1 skipped.
Real-browser qualification covered ComfyUI 0.28.0 / frontend 1.45.21 and
ComfyUI 0.33.0 / frontend 1.49.6, both renderers, light/dark palettes, responsive
widths, media disclosure, native actions, and workflow reloads. Native routing
slot reconstruction received explicit user approval and passed real label,
link, and persistence checks. Temporary qualification environments were removed.
The plan records the unavailable design validator and the existing non-blocking
crop cache-signature warning. Release manifests remain unchanged; nothing was
committed, released, or published.

The current context index includes README.md and docs/**, not plans/**. These
plans must be read directly; a fresh context index does not imply they are indexed.
Index configuration remains unchanged.
