---
version: alpha
name: LFGG Custom Node Design
description: ComfyUI-native interaction and visual rules for LFGG custom nodes.
colors:
  surface: "#202020"
  media-surface: "#111111"
  on-surface: "#EEEEEE"
  muted: "#B0B0B0"
  border: "#808080"
  success: "#66BB6A"
  error: "#EF5350"
typography:
  body-md:
    fontFamily: "system-ui, sans-serif"
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.4
  label-lg:
    fontFamily: "system-ui, sans-serif"
    fontSize: 14px
    fontWeight: 600
    lineHeight: 1.2
  label-md:
    fontFamily: "system-ui, sans-serif"
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.3
  label-sm:
    fontFamily: "system-ui, sans-serif"
    fontSize: 10px
    fontWeight: 400
    lineHeight: 1.2
  code:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.4
rounded:
  none: 0px
  sm: 4px
  md: 6px
spacing:
  2xs: 2px
  xs: 4px
  sm: 8px
  md: 10px
  lg: 12px
  xl: 16px
components:
  node-panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-md}"
    rounded: "{rounded.md}"
    padding: "{spacing.lg}"
  compact-control:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-md}"
    rounded: "{rounded.sm}"
    padding: "{spacing.xs}"
    height: 32px
  dynamic-row:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-md}"
    rounded: "{rounded.none}"
    padding: "{spacing.xs}"
    height: 40px
  diagnostic-report:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    typography: "{typography.code}"
    rounded: "{rounded.none}"
    padding: "{spacing.sm}"
---

# LFGG Custom Node Design

Purpose: Define the durable interaction and visual rules for every LFGG node.
Read when: Designing, implementing, or reviewing a registered node or its frontend UI.
Source of truth: `README.md` defines node behavior; this file defines shared node UX and presentation.
Last reviewed: 2026-09-06

## Overview

LFGG nodes are small, explicit workflow utilities. They should look and behave
like native ComfyUI nodes first: compact, theme-aware, predictable, and honest
about the graph state that will execute.

Start with the Python schema and standard ComfyUI controls. Add custom frontend
UI only when it makes a real task clearer or faster. That UI is progressive
enhancement: the node must keep an executable standard-widget fallback, and a
missing or failed extension must not corrupt workflow state.

The pack is not a separate branded shell. Do not globally recolor ComfyUI or
make every LFGG node visually loud. Use one small muted-teal identity marker
beside an owned section label; native-only nodes receive no marker. Never tint
panels, recolor sockets, or brand primary buttons. The `LFGG ` title remains the
accessible identity.

## Colors

The YAML colors are compatibility fallbacks, not a palette to force over the
user's theme. Resolve colors in this order:

1. ComfyUI semantic CSS variables for pack-owned DOM widgets.
2. LiteGraph `WIDGET_*` or related theme colors for Canvas2D widgets.
3. The matching fallback token above.

Map host values once to `--lfgg-*` variables on an `.lfgg-*` root, then let
owned child styles use those variables. Never override `:root`, apply global
node selectors, or assume a dark palette. Fixed colors are reserved for
semantic state and media backdrops. Pair success, warning, disabled, stale,
and error colors with text, icons, or control state; color alone is not a label.

Maintain readable contrast in light, dark, and custom palettes. A preview may
dim non-selected content, but executable values and essential instructions
must remain legible.

Shared presentation lives in `web/node_ui.mjs` and its scoped `node_ui.css`.
Use a 3px by 12px marker with an 8px label gap. Select `#70B8AE` or `#327D73`
according to contrast against the rendered surface, including custom palettes.
Identity color is never a state or focus indicator.

## Typography

Inherit ComfyUI's active UI font for DOM controls. Canvas widgets use the
system sans fallback at 13px, 12px for supporting labels, and 14px semibold for
a single preview emphasis. Use the code
token only for diagnostic or exact machine-readable output.

Write short, concrete labels in sentence case. Prefer domain words already
used by the backend inputs. Do not encode meaning through typography alone,
truncate a value without exposing the full value, or shrink text to make an
overloaded layout fit.

## Layout

Use a 12px owned-panel inset, 8px ordinary gap, 12px between task groups, and
4px between tightly related controls. Reserve 2px for dense media strips.
Shared metrics come from `web/node_ui.mjs`; native widget and slot geometry
remains host-owned.

Keep the common path compact. Group controls by task order, place transient
selectors or actions next to the field they affect, and show advanced controls
only when relevant without clearing their saved values. Use `min-width: 0`,
wrapping, grid, or container queries so owned DOM widgets tolerate node resize
and longer localized labels.

Resize a node only to fit real content. Preserve a user's larger size, avoid
fixed width unless an editor has a demonstrated minimum, and do not use a
permanent panel when a standard widget or short context-menu action is enough.

## Elevation & Depth

Keep node-local UI flat. Separate groups with host surface tones and a 1px
theme-derived border. Do not add shadows, glass, blur, gradients, glow, or
nested card stacks. Media may use `{colors.media-surface}` behind transparent
or letterboxed content.

Previews should make structure clearer, as the aspect-ratio grid and crop
overlay do now. They must not compete with sockets, controls, or execution
state.

## Shapes

Leave native control shapes to ComfyUI. Use `{rounded.md}` for pack-owned
preview panels, `{rounded.sm}` for compact DOM controls only when the host does
not provide a shape, and square rows for dense ordered data. Do not introduce
pills or decorative containers without a semantic need.

Canvas hit regions may be larger than their marks. Owned numeric/toggle targets
and DOM controls are at least 32px high; LoRA rows are at least 40px. Grow
content rather than shrinking text or overlapping hit areas.

## Components

### Base node

- Give each node one clear workflow job, useful defaults, bounded inputs, named
  outputs, an `LFGG_` stable ID, an `LFGG ` display name, and an `LFGG/...`
  category.
- Use the repository's V1 schema by default. Adopt V3 only for a demonstrated,
  tested need; never expose both registration generations.
- Keep meaningful execution state in declared inputs. Backend validation is
  authoritative; frontend constraints are guidance.
- Reuse native widgets, context menus, media elements, and ComfyUI routes before
  drawing or building replacements.

### Custom controls and previews

- Use `nodeCreated` for per-instance enhancement and
  `beforeRegisterNodeDef` only for type-wide behavior such as the virtual
  routing organizer. Use supported extension hooks, not core prototype or DOM
  monkey-patches.
- Own the DOM subtree and namespace classes, data attributes, widget names, and
  extension names with `lfgg`. Treat renderer internals such as `.lg-node` as
  optional enhancement targets, never as the primary interface.
- Prefer native HTML controls inside DOM widgets. Labels, keyboard operation,
  visible focus, disabled/read-only state, and polite live status are required
  where they apply.
- Keep visual-only widgets non-serializing. A preview reflects declared inputs
  or backend results; it never becomes a hidden source of executable truth.
- Provide explicit empty, loading, unresolved, stale, disabled, and error
  states. Preserve the last valid data when a refresh fails and report the
  failure in actionable language.
- Keep the concrete widget returned by `addCustomWidget`; renderer state and
  redraw callbacks belong to that instance. Hide native widgets through their
  supported widget metadata, not by removing executable inputs. Handle both
  positional serialization holes and serializers that already omit them.
- Resolve Canvas width from the current node in the legacy renderer and from
  the actual widget canvas in Nodes 2.0. Keep native widget hit bounds aligned
  with that drawing width; stale retained widths must not block visible targets.
- Use the shared native prompt adapter for editable/selectable text: the host
  dialog service when available, otherwise the native canvas prompt.

### Dynamic rows and sockets

- Use one obvious add path and keep row order visible. Put destructive actions
  behind a labeled menu or confirmation appropriate to the loss.
- Bound growth and label length. Preserve row values while filtering or hiding
  choices, and show missing saved choices instead of silently substituting.
- Restore serialized state without adding phantom rows or sockets. Prove an
  actual link exists before growing from a restore callback.
- LoRA rows share one two-dimensional layout for drawing, sizing, and hit
  testing. Stack controls when name and strength lanes cannot fit. Measure
  basename ellipsis, show distinguishing folder context, and expose the exact
  stored path through a selectable native prompt. Enabled state uses a neutral
  checkbox, not identity color.
- Routing labels stay aligned with native sockets. Use native input labels in
  Nodes 2.0, where node foreground drawing is unavailable, and a non-serializing
  custom-widget footer for the hint and single identity marker.
  When a routing label changes, reconstruct only its pack-owned native input
  slot to notify the shallow Nodes 2.0 renderer. Preserve its native class,
  links, type, metadata, and pending-channel membership; do not patch prototypes.

### Rich editors and reports

- Keep editor state synchronized with the same backend inputs users can inspect
  and connect. Connected values are visibly locked rather than silently
  overridden.
- Use native media controls and focus-scoped shortcuts. Do not capture global
  keys or prevent ordinary text editing.
- Reports are read-only, selectable, bounded, and monospace. Mark previous
  results stale while newer execution is pending.
- Crop and video start compact. The shared strict-Boolean
  `node.properties.lfgg_editor_expanded` stores only disclosure state. Missing
  or malformed values mean compact. Toggling does not reload sources, query
  metadata, normalize executable values, or discard manual sizing.
- Crop remains draggable while compact; expansion adds native precise inputs.
  Share responsive viewport geometry between drawing and dragging. Use a
  two-tone frame and a source-pixel caption, with 200px/360px compact/expanded
  content caps rather than forced heights.
- Video keeps the active boundary pair visible while compact. Expansion shows
  one grouped timeline with distinct native range rows, selected interval,
  bounded thumbnails, and transport. Defer thumbnail work while closed or
  collapsed, and reuse completed captures.
- Use public graph-change and graph-configured events for linked-source
  updates across renderers. Do not wrap upstream widgets or introduce polling.

## Do's and Don'ts

- Do start schema-first and stop at native ComfyUI UI when it solves the task.
- Do preserve the standard-widget fallback and workflow behavior when frontend
  enhancement is unavailable.
- Do test new-node state, resize, connection changes, serialize/configure
  reload, clone or copy/paste, light and dark palettes, keyboard focus, and the
  supported legacy and Nodes 2.0 renderers for every custom UI.
- Do keep repaint, observers, media work, and network requests event-driven and
  bounded; suspend expensive work while collapsed when practical.
- Do update this file in the same change when introducing a new shared visual
  token or interaction pattern.
- Don't add a frontend framework, build step, global stylesheet, route, hidden
  input, or graph feature for a control native APIs can express.
- Don't serialize decorative widgets, cached previews, transient status, or
  duplicated representations of declared inputs.
- Don't reset hidden values, clamp invalid backend data silently, or make a
  valid workflow depend on frontend timing.
- Don't use color-only state, invisible focus, hover-only actions, permanent
  redraw loops, or animation without a reduced-motion path.
- Don't copy styling from another node pack or ComfyUI internals without first
  verifying the API, compatibility, and license boundary.
