# Plan 001: Unify custom node presentation and redesign LoRA rows first

> Implementation authorized by the user's execution request on 2026-09-06.
> Read the complete plan before editing. Execute phases in dependency order;
> do not stop after the shared helper or LoRA phase and call the whole plan done.
> Preserve unrelated working-tree changes. Update the status in
> [the plan index](README.md) only after the corresponding evidence exists.

## Status and authority

- Status: IN PROGRESS. Phase 0 runtime established; shared treatment implemented.
- Priority: P1. Effort: L. Risk: medium overall; high at UI serialization and
  Canvas pointer-geometry boundaries. Dependencies: none.
- Planned at: `ec43992`, 2026-09-06. Excerpts describe the working-tree source
  inspected that day, not a guarantee that every file equals that commit.
- Source of authorization: confirmed OMP design interview on 2026-09-06.
- First milestone: shared visual treatment plus complete adaptive LoRA rows.
- Complete deliverable: all seven existing custom visual surfaces listed below.
- No commit, push, PR, version bump, or publication is authorized.
- During Phase 0, the user explicitly authorized an isolated minimum-runtime
  setup, including ComfyUI 0.28.0 and its dependencies/frontend 1.45.21.
  This does not authorize project dependencies or changes to an existing runtime.

Before execution, compare current source with the excerpts and contracts below.
Use scoped source inspection if files changed; do not overwrite intervening work
or require a clean working tree. A material behavior or schema mismatch requires
reconciliation before editing.

## Confirmed design brief

The user explicitly selected and confirmed:

1. **All custom UI layouts**, not just the LoRA node. Simple native-widget nodes
   retain their native appearance.
2. **Adaptive LoRA rows**: one line when there is adequate room; filename above
   strength controls when narrow. Do not compress text or force a wider node.
3. **More comfortable spacing**, not a compact/comfortable preference setting.
   Compact media presentation means fewer visible controls, not smaller targets.
4. **A restrained muted-teal identity marker**, placed once in an owned panel or
   section header. No tinted panel backgrounds or branded primary buttons.
5. **Compact media previews with inline expansion**, not separate dialogs or a
   sidebar editor. Detailed editing stays with the graph node.
6. **Persist expansion per media node**. The user specifically authorized one
   optional, namespaced presentation property in workflow JSON. Older workflows
   default to compact. This property must not affect execution.
7. **Basename-first LoRA labels**, with secondary folder context when needed to
   distinguish files and an accessible way to read the full relative path.

This plan refines the existing native-first visual world; it does not replace
ComfyUI with a branded application shell. It supersedes the old 24px custom-row
and 28px custom-DOM-control presentation targets where specified below, but not
host-owned widgets, slot geometry, or backend behavior. Update DESIGN.md during
implementation so two competing active design specifications do not remain.

## Why this matters

Current custom nodes mix tightly packed Canvas controls with largely unstyled
DOM panels. Fixed preview heights waste graph space, and fixed LoRA strength
columns squeeze filenames. At a 300px node width, the current LoRA layout leaves
140px for a filename with combined strength and 56px with separate strengths.
A Chromium Canvas measurement of `portrait_detail_v2.safetensors` at the shipped
12px sans-serif font measured 157.42px. The current max-width fillText call can
compress that text rather than produce an ellipsis.

These are source-grounded layout findings, not observations of a live ComfyUI
session. There were no discovered screenshot fixtures or running ComfyUI surface
in the planning session. The executor must establish real visual evidence before
claiming the redesign looks correct.

## Scope and source map

All existing custom visual surfaces are in scope:

| Surface | Implementation and entrypoint | Current presentation | Required result |
|---|---|---|---|
| Power LoRA Loader (Folder) | `web/power_lora_loader.mjs`, `web/power_lora_loader.js` | Canvas header, 24px rows and footer | Readable adaptive rows and reusable control treatment |
| Prompt Composer | `web/prompt_composer.mjs`, `web/prompt_composer.js` | Fixed 104px DOM toolbar before seed | Insertion-first toolbar, wrapping status, comfortable controls |
| Ratio preview | `web/ratio_preview.mjs`, `web/ratio_preview.js` | Fixed 120px Canvas panel | Quieter, compact ratio display with legible state |
| Load and Crop Image | `web/crop_editor.mjs`, `web/crop_editor.js` | Fixed 360px Canvas preview | Responsive crop frame preview and expandable precise controls |
| Video Cutter | `web/video_cutter.mjs`, `web/video_cutter.js` | DOM editor, 500px minimum widget, node enlarged to 360x620 | Compact preview, coherent expanded timeline, active-mode controls |
| Value Inspector | `web/value_inspector.mjs`, `web/value_inspector.js` | Fixed 180px inner report, node enlarged to 360x240 | Height-responsive selectable report and separate status |
| Routing Organizer | `web/routing_organizer.mjs`, `web/routing_organizer.js` | Canvas labels at native slot positions | Clear label fitting and discoverable existing actions without socket changes |

Allowed production additions, each with actual multiple callers in its first
implementation phase:

- `web/node_ui.mjs`: a small presentation module for shared metrics, DOM root
  initialization, theme resolution, and the identity marker. LoRA and Prompt
  Composer are the initial Canvas/DOM callers. Do not turn this into a component
  framework, service registry, node factory, or generic event dispatcher.
- `web/node_ui.css`: owned DOM controls only, loaded once from the extension's
  own URL. Every selector is scoped beneath an `.lfgg-*` root.
- `web/editor_view.mjs`: media presentation state and safe auto-fit coordination,
  introduced only when both crop and video consume it. No media I/O, crop math,
  boundary conversions, or generic workflow serialization framework belongs here.

Allowed existing tests: all nine `tests/frontend/*.test.mjs` modules corresponding
 to the existing web entrypoints. Edit only tests actually affected. Add a focused
shared-helper test module only for a behavior with a plausible regression, not
for constant values or module wiring.

Allowed documentation updates during implementation:

- `DESIGN.md`, `README.md`, relevant `web/docs/LFGG_*/en.md` help pages that exist.
- The historical LoRA and crop design documents under `docs/plans/` may receive a
  short pointer to the new presentation contract; do not rewrite their history.
- This plan and `plans/README.md` status/evidence.

Out of scope:

- `lfgg_nodes/**`, root `__init__.py`, registration/display IDs, categories,
  execution algorithms, routes, network limits, and package/version metadata.
- `reference/custom-nodes/**`, ComfyUI core, other packs, and frontend globals.
- Global styles, private `.lg-node` descendant selectors, replacing core
  templates, frameworks, generated assets, or a new build step.
- Native-only nodes: image dimension/resize nodes, Save Image Dynamic, both
  String Replace nodes, String Join, Boolean Switch, and Index Switch. The latter
  three have frontend behavior but no custom visual layout to redesign. Keep
  their dynamic socket and title-normalization logic unchanged.
- New LoRA browsing services, model information, trained words, presets, drag
  reordering, new density settings, timeline waveform, or new processing modes.
- Full translations, arbitrary object inspection features, or report parsing.

No new glossary term is needed. `CONTEXT.md` remains unchanged. This reversible
presentation choice does not require a new ADR. Preserve the two relevant ADRs:
`docs/adr/0001-persist-dual-video-selection-representations.md` and
`docs/adr/0002-use-a-virtual-routing-organizer.md`.

## Current-state anchors and preservation contracts

### Registration and platform

`__init__.py:47-83` registers V1 mappings and `WEB_DIRECTORY = "./web"`.
`pyproject.toml:14,42` requires frontend `>=1.45.21` and ComfyUI `>=0.28.0`.
Python is `>=3.10,<3.14`. Do not raise those floors to make a UI API convenient.
The pack is build-free: `.js` entrypoints register extensions and import `.mjs`
logic; dependency-free frontend tests use `node:test` and `node:assert/strict`.

`web/power_lora_loader.js` exemplifies the entrypoint pattern:

```js
app.registerExtension({
  name: "lfgg.powerLoraLoaderFolder",
  nodeCreated: (node) => installPowerLoraLoader(node),
  loadedGraphNode: (node) =>
    installPowerLoraLoader(node, { restore: true }),
});
```

Keep installers idempotent. Use supported extension hooks and compose the
existing pack-owned instance callbacks; never patch app, global prototypes, API
clients, or another pack. Verify any new menu or renderer capability against the
minimum supported frontend as well as the current installed frontend.

### LoRA source of truth

`web/power_lora_loader.mjs:151-157` defines the exact row payload:

```js
function rowValue(row) {
  return {
    on: row.on,
    lora: row.lora,
    strength_model: row.strengthModel,
    strength_clip: row.strengthClip,
  };
}
```

`createRow` currently attaches `serializeValue: () => rowValue(row)` to a
`lfgg_lora_row` widget, and `syncWidgetOrder` assigns sequential `lora_N` names.
The workflow also stores ordered `node.properties.lfgg_lora_rows` and the
existing `Separate Model and Clip strength` setting. Preserve both existing
serialization paths. Do not add display names or shortened paths to the payload.

Current drawing/pointer functions are `rowLayout`, `drawRow`, `drawStrength`,
`createRow`, and its `onPointerDown`. Pointer handling currently uses horizontal
bands only (`web/power_lora_loader.mjs:344-407`); a stacked row requires genuine
2D rectangles. A drawing-only change is incorrect.

Retain the existing controller methods `add`, `replace`, `setEnabled`,
`setStrength`, `remove`, `move`, `toggleAll`, `refresh`, and `restore`:

- Folder changes filter future choices only and preserve existing rows.
- Full ComfyUI-relative filenames remain authoritative, including rows outside
  the current folder and missing saved choices.
- Strength arrows adjust by 0.05; direct entry remains available.
- Combined strength changes both values; separate mode edits them independently.
- Switching separate mode off currently copies model strength into CLIP strength.
  Preserve that behavior; it is not a presentation-only flag.
- Row reordering retains data and renumbers prompt keys without collisions.
- Retain the existing migration from `lfgg_link_strengths`; the redesign is not
  authorization to remove compatibility with saved workflows.
- Without the frontend, the existing backend remains importable and accepts
  valid authored/API row payloads. Do not promise new frontend-free row authoring.

### Presentation state versus executable values

The new property is exactly `node.properties.lfgg_editor_expanded`, Boolean,
used only by Load and Crop Image and Video Cutter. Absent or non-Boolean values
read as compact; save an explicit Boolean when the user changes the view. Never
coerce the string `"false"` into expanded state. Preserve unrelated properties.

- Initial view: compact. Reopening, clone, and copy/paste restore the saved flag.
- Authoritative execution state remains in the original widgets/links.
- Expansion must not call crop `reset`/`normalize` or video `writeWidgets`, change
  selection mode, normalize source end, refresh a source, or issue a network call.
- Expansion is not `node.flags.collapsed`. Do not reuse `collapse()` for it.
- Auto-fit only changes height when the node is still at a height this controller
  last fitted. Use the existing ratio-preview ownership pattern as the exemplar.
  Do not shrink nodes during configuration or shrink a larger user-saved size.
- On a legacy workflow with a large saved size, preserve that size even though
  editor content starts compact. Do not guess whether an old height was manual.
- Media view controls and markers must not become `widgets_values` or API prompt
  inputs. Native properties serialization can carry the optional Boolean.

The existing middle-widget positional-hole fix is visible in
`web/ratio_preview.mjs:271-281`:

```js
if (
  Array.isArray(serialized.widgets_values) &&
  serialized.widgets_values.length === node.widgets.length
) {
  serialized.widgets_values.splice(node.widgets.indexOf(preview), 1);
}
```

Crop has analogous single-preview cleanup; video, prompt, and inspector have
single-DOM-widget cleanup. When a node gains more than one visual widget, update
its existing cleanup to remove exactly its owned visual widgets in one pass,
using original indexes in descending order when values still contain holes.
Do not stack independent length checks, remove meaningful hidden widgets, or
strip arbitrary names by prefix. Test both serializers that include holes and
serializers that already omit nonserializing widgets.

### Domain semantics that must remain visible

- A **ratio preview** shows the requested proportion, not calculated output
  dimensions. Do not invent a result before execution.
- A **crop frame** selects exact source pixels without resampling. Preserve crop
  geometry, loading preservation, dynamic-ratio resolution and derived height.
  `crop_height` stays read-only; current code rejects crop-coordinate input
  connections. Do not relax that connection contract.
- Video **selection mode** is a representation of the same segment. Both numeric
  pairs persist, in order: `video`, `selection_mode`, `start_time`, `end_time`,
  `first_frame`, `last_frame`. Time ranges are end-exclusive; frame ranges are
  inclusive and zero-based; `-1` means source end. Preserve those conventions.
- A **connected boundary** remains controlled upstream. Hiding controls does not
  unlock it, remove its link, or replace the saved local value.
- A **routing channel** is a linked input/output pair, not a LoRA row. Keep native
  slot positions and channel count; no phantom channels on restore.
- A **value inspector** displays bounded diagnostic text, including honest stale
  state. Do not parse that text into an invented object schema.

## Shared visual specification

### Tokens and scope

Resolve owned DOM colors from supported host semantic variables, then existing
host/LiteGraph values where needed, then the fallbacks in DESIGN.md. Map them
once to `--lfgg-*` variables at the owned root. Do not apply CSS to `:root`,
ComfyUI node selectors, raw global `button`/`input`, or user node colors.

Keep numerical metrics centralized in `web/node_ui.mjs` for Canvas use and map
those same metrics to owned DOM custom properties rather than maintaining a
second unrelated spacing scale. Read computed theme state at initialization and
on supported theme changes, not during every row draw. Prefer live CSS variables
for DOM; avoid per-node polling or permanent redraw loops.

| Role | Target |
|---|---|
| Owned panel inset and main group gap | 12px inset, 8px ordinary gap, 12px between task groups |
| Tightly related label/control gap | 4px |
| DOM control minimum height | 32px; grow for wrapped labels rather than clip |
| LoRA numeric/toggle action target | At least 32px high; visible mark can be smaller |
| LoRA single-line row | At least 40px including vertical breathing room; content determines larger height |
| Body / filename | Inherit host UI font; 13px system sans fallback for owned drawing |
| Secondary label | 12px; a semantic secondary text color, not opacity as the only contrast strategy |
| Section label | 14px semibold; at most one emphasis level per small panel |
| Exact report/numeric text | Existing system monospace stack; report 12px or host-readable equivalent; no downloaded font |
| Panel/control corners | Existing 6px / 4px tokens; square ordered rows |
| Separators | 1px host-derived; no full boxed outline on every LoRA row |
| Media backdrop | Existing dark media-only fallback is permitted; do not recolor the media content |
| Motion | No decorative animation; expansion is immediate and focus-safe |

Native controls and routing slot rows retain host geometry. Comfortable spacing
applies to owned controls, not a global LiteGraph row-height change.

Proposed muted-teal identity variants:

- Dark surface: `#70B8AE`.
- Light surface: `#327D73`.
- Marker: approximately 3px wide by 12px high, once beside the first owned
  section label, with an 8px text gap. DOM decoration is `aria-hidden`.
- Never use these colors to mean on/off, stale, error, focus, execution, or
  selected wire. Do not change `node.color` or `node.bgcolor`.
- For Canvas-only panels, draw the same marker inside their existing content
  bounds, not over the core title, sockets, or row hit targets. Native-only nodes
  receive no new marker widget solely for branding.
- Use actual rendered surface contrast to select/adjust the variant in custom
  themes; do not classify theme by a guessed CSS class or OS dark-mode setting.

Arithmetic checks during planning: dark marker on `#202020` is 7.10:1; light
marker on white is 4.86:1 and on `#EEEEEE` is 4.19:1. These are fallback-pair
calculations, not proof of contrast in ComfyUI. Essential text needs 4.5:1 and
interactive boundaries/focus need 3:1 where applicable. Identity remains
nonessential and cannot substitute for the `LFGG ` title.

### Interaction treatment

- Use native DOM labels, controls and focus behavior on existing DOM surfaces.
  Canvas controls retain host dialogs/menus and need a keyboard-accessible
  equivalent for their existing actions; do not make hover the only way to get
  a full filename or recover from an error.
- Native context menus remain searchable where they are searchable today.
  Resolve the current `className: "dark"` override only after verifying the
  minimum/current host menu behavior; do not copy another pack's menu service.
- Disabled state means neutral, noninteractive, and explained when the reason
  is not obvious. Preserve the ability to re-enable disabled LoRA rows.
- Status uses text and appropriate control state. DOM updates use a polite
  status element; keep transient status separate from report/prompt content.
- At narrow widths, wrap or stack. No horizontal text scaling, clipped recovery
  instructions, overlapping targets, or forced width growth just to preserve
  the wide layout.

## Execution phases

### Phase 0 — Establish runtime and contract evidence

Read root instructions, DESIGN.md, the relevant ADRs, source and existing tests.
Use the repository's existing ComfyUI environment and installed dependencies;
no install or compatibility-floor change is authorized. Identify the actual
ComfyUI URL rather than assuming a port.

1. Run the nine frontend test modules using the command below and retain output.
2. In a scratch workflow in real ComfyUI, add the seven custom visual nodes and
   native controls for comparison. Do not save private filenames/media paths
   into committed examples. Use synthetic or redistributable media and real,
   locally available LoRA catalog entries for the relevant interaction check.
3. Record frontend/ComfyUI versions and availability of both legacy and Nodes
   2.0 renderers. Check `addCustomWidget`, `addDOMWidget`, current node-local menu
   APIs, theme-change notification, and configure/clone lifecycle on the minimum
   supported frontend before designing around new capabilities.
4. Capture before screenshots and workflow/API prompt output for the contract
   comparisons. Use a dedicated browser tab; do not disturb a user's workflow.
5. Confirm node search display/category/package metadata. Check routing title
   migration and that restored disconnected channels do not grow.

**Gate:** `node --test tests/frontend/*.test.mjs` exits 0, or record unrelated
baseline failures explicitly and resolve their impact before editing. A missing
runtime is a UI verification blocker, not permission to substitute fake-node
screenshots as proof of host compatibility. Investigate reachable setup first;
report any prerequisite that cannot be obtained safely.

### Phase 1 — Introduce shared treatment with two real callers

Files: new `web/node_ui.mjs`, `web/node_ui.css`; existing LoRA and Prompt Composer
modules/entrypoints only as necessary; DESIGN.md.

1. Implement the limited theme/root/metric/marker responsibilities above.
2. Load CSS once, using a URL relative to the extension module; no external
   fonts/assets. Loading code must be safe when imported in non-browser tests.
3. Apply the module to LoRA Canvas presentation and Prompt Composer DOM root in
   the same phase. Shared helpers must not ship unused or with one caller.
4. Ensure stylesheet failure does not disable native inputs or mutation controls.
   Restore host visibility on failed enhancement; capability detection must not
   silently leave a half-installed node.
5. Document the token and marker rules in DESIGN.md, replacing obsolete sizes
   and the old implication that no identity marker is permitted.

**Gate:** run the LoRA and Prompt Composer frontend test commands; in the real
browser change light/dark theme without reloading. Both callers update, unrelated
nodes remain unchanged, no marker overlaps a socket or focus indicator, and
there are no repeated stylesheet insertions after node creation/reload.
Do not add permanent tests that assert helper imports or hardcode brand colors.

### Phase 2 — Complete adaptive LoRA rows

Files: `web/power_lora_loader.mjs`, its frontend test, shared styles/metrics only
where genuinely shared.

1. Keep existing row objects and serializing row widgets. Replace the layout
   calculation with one canonical set of row-local rectangles and total height
   used by drawing, computeSize and pointer hit testing.
2. Determine wide versus stacked layout from available width and control/name
   requirements. At 300px with separate strengths, use stacked layout. At 600px,
   ordinary short filenames should fit in the single-line layout. Handle
   intermediate widths from actual available space, not device breakpoints.
3. Make minimum filename space approximately 160px in the wide layout. When
   filename space or folder context needs more room, grow row height, not node
   width. A narrow stacked row puts filename/context above strengths. Keep the
   toggle associated with the file and the row menu reachable without overlap.
4. Display the basename (including extension) without horizontal compression.
   Use measured ellipsis at the current font; make the complete ComfyUI-relative
   path available through a labeled, selectable detail/menu action. Hover may
   supplement but cannot be the only access path.
5. Show secondary folder context for duplicate basenames referring to different
   paths in the catalog or selected rows, and for rows outside the active folder.
   Repeated uses of the same LoRA remain valid. Preserve case and stored paths.
   Build name/context indexes when catalog/rows change, not in every draw call.
6. Replace colored-dot-only enable state with a recognizable checked/unchecked
   control. Use neutral disabled styling, readable filenames and preserved
   strengths. Keep explicit labels for combined strength or Model/CLIP columns.
7. Use quiet row separators and host hover/focus treatment. Keep row order
   visible and retain one Add LoRA path, toggle-all and searchable replacement.
   Keep move/remove in the existing row menu instead of adding button clutter.
8. Retain numeric stepping/direct entry and all controller semantics above.
   Route any keyboard/menu equivalent through the same controller operations,
   not a second state model. Use the host's verified node-local menu/command
   capability; no global key handler. If the minimum renderer cannot expose an
   accessible equivalent, report that capability conflict before claiming parity.
9. Recompute geometry on width, separate-strength mode, filename/context and row
   changes. Use both pointer X and Y relative to the actual row origin. Do not
   capture right-clicks or gaps between controls. Preserve manually enlarged
   height, correcting the current unconditional resize behavior where needed.

Existing regression anchors include tests named `serializes exact backend rows
without positional workflow values`, `reorder renumbers prompt widgets without
changing row values`, `strength arrows adjust by 0.05 and keep direct entry`,
`restores ordered rows on the loaded-node install and stays idempotent`, and
`preserves a missing saved folder and exposes no add choices`.

Delete `colors toggles and darkens disabled rows`: it pins exact colors and a
particular glyph, not behavior. Replace coordinate snapshots in the footer and
stale-widget-width tests with behavioral resize/hit-target coverage. Do not just
update their pixel literals. Preserve the underlying zero/stale supplied-width
regression by exercising a control at its actual visible location after resize.

**Gate:** `node --test tests/frontend/power_lora_loader.test.mjs` exits 0.
Use real ComfyUI at 300/400/600px widths to toggle, step, enter a number, replace,
move and remove rows in combined/separate modes, including long and duplicate
basenames. After save/reload, ordered row payloads and strengths are identical.
This is the first milestone, not completion of the full plan.

### Phase 3 — Apply the treatment to remaining non-media surfaces

#### Prompt Composer

Files: `web/prompt_composer.mjs` and its test.

- Replace the fixed 104px height and matching min/max/computeSize constraints
  with content-driven layout. Keep the prompt editor dominant and the seed in
  its current semantic position; do not reorder serialized inputs.
- Use action-oriented labels `Insert wildcard` and `Insert style`, adjacent to
  the prompt. Keep an unobtrusive caret-insertion explanation.
- Keep Refresh libraries visible but secondary. Use a separate wrapping status
  line for loading/errors; routine success should not create a large panel.
- Preserve catalog caching, in-flight sharing, disabled headings, failed-refresh
  preservation, token syntax, selection replacement, caret and focus restoration.
- Preserve native select keyboard behavior if the enhanced searchable menu is
  unavailable. Do not trap focus or silently lose typed prompt content.

#### Ratio preview

Files: `web/ratio_preview.mjs` and its test.

- Use a compact content-derived preview, targeting about 80-104px for ordinary
  ratios rather than a permanent 120px panel. Allow extra room if labels need it.
- Keep the fixed-reference grid concept but reduce its visual weight. Make the
  ratio shape and readable label dominant; show labels outside extreme shapes.
- Preserve dynamic/invalid text, preset/custom behavior, connected custom inputs,
  original auto-fit ownership and serialized input positions. Do not show output
  dimensions the backend has not computed.

#### Value Inspector

Files: `web/value_inspector.mjs` and its test.

- Replace the fixed 180px inner report with an available-height layout, a compact
  empty state, and a scrollable report when content exceeds the available space.
  Enlarging the node must give the report more room, not blank space below it.
- Keep the report a selectable, bounded `pre` rendered through textContent.
  Add a small separate polite status line for waiting/current/stale, retaining
  the previous successful report if execution is pending or fails.
- Preserve session-only report lifetime and native caching; no report parsing,
  persistent report state, new backend messages or invented tensor metadata.

#### Routing Organizer

Files: `web/routing_organizer.mjs` and its test; entrypoint only if a verified
node-local menu hook is required.

- Fit/ellipsize labels without overlapping sockets. Keep complete labels
  available via the existing rename flow. Do not modify persisted labels merely
  to fit them or replace a user's custom node title.
- Expose a short empty/selected-node hint for existing Add/Rename/Remove actions
  and double-click rename. Keep the native context menu as the action path.
  Put any hint/identity marker in an owned footer region that is excluded from
  channel hit-testing; no decorative socket or pseudo-channel.
- Keep native `NODE_SLOT_HEIGHT` channel alignment. If footer space is added,
  update sizing and rowAt together so a footer click never renames the last
  channel. Keep no-collapse and no-subgraph-conversion behavior.
- Preserve 1-32 channels, link/type propagation, fan-out, remove-with-splice,
  restore normalization, category/package/display metadata and title migration.

**Gate:** run the four named frontend test commands. In real ComfyUI, check
narrow/expanded widths, long labels, prompt caret insertion with keyboard and
pointer, failed library refresh with retained choices, empty/current/stale
reports, and routing reload with disconnected slots. Native switch/join visuals
and behavior must remain untouched.

### Phase 4 — Introduce media disclosure in both callers

Files: `web/editor_view.mjs`, crop/video modules and tests; shared presentation
module only for shared metrics. Add the exact Boolean property contract above
in both callers together, with appropriately labeled native disclosure controls.
For DOM use a native button or details/summary; for the Canvas crop surface use
a supported native node control, not a tiny painted triangle as the sole action.

- Expose `Edit crop` / `Hide crop controls` and `Edit selection` / `Hide selection
  controls` as appropriate, with expansion semantics and focus preservation.
- Read the property after workflow configuration and on clone/copy-paste, not
  only during the initial constructor call. Existing installers are idempotent
  but that alone does not prove configure replay or copied-state restoration.
- Reuse safe height ownership and configure guards. Keep actual node size and
  expansion state distinct; never persist cached content height or observed
  media dimensions just to support the view.
- Ensure presentational widgets are omitted from positional values in both
  serializer modes described earlier. Preserve all meaningful hidden inputs.
- When details close, move focus to the disclosure control if it was inside the
  hidden section. Opening/closing must not disturb the input caret elsewhere.
- Do not add thumbnail work or source refresh on every expansion or resize.
  Reuse existing request generation guards and bounded thumbnail count.

**Gate:** both media frontend modules pass. Check compact/new, saved expanded,
saved compact, absent/malformed flag, unrelated properties, clone/copy-paste,
serialization with/without holes, and manually enlarged node sizes. Compare
API prompt inputs before and after toggling view: they must be identical.

### Phase 5 — Complete the crop presentation

Files: `web/crop_editor.mjs`, its frontend test, shared media helper as needed.

- Compact content: source image selector, responsive image/crop-frame preview,
  ratio controls, dimensions caption, explicit unresolved/loading/error status,
  and the disclosure control. Precise crop X/Y/width/derived-height controls
  appear in the expanded view without losing their saved values.
- Keep the crop frame directly draggable when the existing currentRatio/source
  state permits it, including in compact view. Expansion adds precision and
  space, not a second crop engine.
- Replace `CROP_PREVIEW_HEIGHT` assumptions in computeSize, cropBounds,
  fitPreviewImage, drawing and hit-testing with the same resolved geometry.
  Start with a compact media viewport cap of 200px and an expanded cap of 360px;
  fit to available width and source ratio, with bounds for extreme ratios.
  These are content caps, not forced node heights. Larger user-allocated space
  may increase the expanded viewport where the host provides that allocation.
- Move dimension text from the center of the image to a stable caption below
  the viewport. Use a two-tone crop outline over unpredictable image colors;
  retain existing enlarged corner hit regions and no-resampling semantics.
- Keep native precise numeric controls as the keyboard alternative to dragging.
  Preserve read-only derived height and explain dynamic-ratio/loading locks.
  A connected ratio that is statically resolvable is not automatically an error.
- Preserve selected-image loading generations, last valid crop on failed load,
  delayed execution results, same-image retry, ratio-reset rules and coordinate
  connection rejection. Merely changing view must invoke none of those resets.
- Only hide fallback widgets after successful enhancement. With the extension
  unavailable, the same seven standard inputs must remain usable as before.

**Gate:** `node --test tests/frontend/crop_editor.test.mjs` exits 0. In real
ComfyUI, move/resize the same crop at compact/expanded and multiple node widths;
source-pixel coordinates remain identical for view-only changes. Check portrait,
landscape and extreme-ratio synthetic images, bright/dark content, loading/error,
connected ratios, reload and numeric-only editing.

### Phase 6 — Complete the video cutter presentation

Files: `web/video_cutter.mjs`, its frontend test; entrypoint/helper as needed.

- Compact content: source player with native controls, selection mode and active
  boundary controls, concise segment summary, status and expansion control.
  Keep the active start/end pair editable without opening the large editor.
- Expanded content: one aligned timeline region containing the thumbnail
  filmstrip, playhead and highlighted selected interval, active-mode precise
  inputs, grouped previous/next-frame transport, Set Start/Set End, and loop.
  Preserve accessible native range inputs; visually aligning tracks must not
  make one overlapping range steal the other handle or block keyboard use.
- Present only the active time/frame editor pair as primary controls. The other
  representation may appear as read-only secondary text when metadata is known.
  Both backend pairs, their widgets and connectability remain preserved. Never
  hide a connected socket or lose discoverability of connected inactive inputs.
- Where an enhanced input replaces a native numeric control visually, hide only
  its successful local visual duplicate; keep the original authoritative widget
  and restore its visibility when preview/enhancement cannot provide editing.
  Do not leave users with every numeric input disabled after preview failure.
- Keep selection endpoints explicit: End time is exclusive; Last frame is
  inclusive. Source end remains `-1` in persisted state. Add duration to the
  summary only when real metadata is available; never fabricate zero duration.
- Explain connected-boundary locks with text associated with the controls.
  Preserve saved local values when disconnecting. Do not introduce clamping or
  change setSelection, writeWidgets or selectionFromWidgets numerical semantics.
- Content-driven sizing replaces the fixed 500px widget / 620px node minimum.
  Use a compact player cap near 180px and expanded cap near 260px, responsive to
  available width. Derive overall height from actual content, not a guessed sum
  that clips wrapped labels at narrow widths.
- Reserve bounded thumbnail space with loading/empty feedback; keep ten samples.
  Defer thumbnail work while the filmstrip is hidden and resume only pending
  work when shown. Expansion alone must not re-probe metadata or reassign src.
  Preserve source/request generation checks; no background polling or cache layer.
- Keep scoped Space/Left/Right/I/O shortcuts. Native buttons/details controls
  must retain their own Space/Enter activation without bubbling a second media
  action; INPUT/TEXTAREA/SELECT editing must not trigger playback/mark shortcuts.
- Distinguish disconnected/computed source, loading, preview unavailable and
  invalid saved selection, with truthful recovery and the executable fallback.
  A preview failure must not invalidate a valid VIDEO output.

**Gate:** `node --test tests/frontend/video_cutter.test.mjs` exits 0. Real-browser
checks cover direct Load Video, computed-video post-execution preview, selection
mode changes, source end, locks/disconnect, invalid saved values, compact/expanded
reload, timeline keyboard controls, and collapse/expand during thumbnail capture.
Toggling view, resizing or changing an unrelated connection must not add metadata
requests, alter selection inputs or load the same media again unnecessarily.

### Phase 7 — Qualify the complete UI and update user-facing documentation

Do this after every surface is integrated. There is one integration owner.
At most three agents may work concurrently only after shared contracts land;
parallel writers own disjoint surface files. Shared modules and integration
remain single-writer. Agents skip project-wide validation; the owner runs it
once after integration. No delegation is necessary for small sequential work.

1. Run all frontend tests once together; resolve interactions among adapters.
2. Run the canonical Python/package gates available in the prepared environment.
   Do not install missing tools automatically. Tests passing is not permission
   to publish or raise a compatibility floor.
3. Run the visual matrix below in the actual minimum and current supported
   frontend/ComfyUI environments. Capture before/after and compact/expanded
   screenshots, version identifiers, and concise interaction results.
4. Verify archive contents include the new .mjs/.css files and no local paths,
   private images, screenshots with private catalogs, caches or temporary smoke
   harnesses. Do not overwrite the existing archive without explicit approval;
   use an isolated working copy/output location supported by the packaging tool.
5. Update README node usage and relevant existing node help. Update DESIGN.md
   with the actual tokens, adaptive rows, disclosure property and layout rules.
   Document no new external network activity and the one new workflow property.
   Keep CONTEXT.md, ADRs and backend contracts unchanged.
6. Run the available design-md structural validator if one is supplied in the
   execution environment. Planning found no validator script in the installed
   design-md skill or repository; do not invent a command or claim it passed.
7. Run context ingest/status after meaningful Markdown edits. Remove temporary
   smoke artifacts after saving appropriate non-private verification evidence.

**Gate:** all applicable commands and visual acceptance cases succeed. Report
missing environmental gates as blocked, not passed, and do not mark the complete
plan DONE until the required UI/runtime evidence exists.

## Verification commands

The following commands come from README.md:375-394 or are direct aggregates of
its documented per-module frontend commands. They are execution gates, not
claims of checks performed during planning. Use the project's prepared Python
environment where `python`, pytest, ruff and comfy are available.

| Purpose | Command | Expected result |
|---|---|---|
| Entire frontend set | `node --test tests/frontend/*.test.mjs` | Exit 0, no failing tests |
| LoRA | `node --test tests/frontend/power_lora_loader.test.mjs` | Exit 0 |
| Prompt | `node --test tests/frontend/prompt_composer.test.mjs` | Exit 0 |
| Ratio | `node --test tests/frontend/ratio_preview.test.mjs` | Exit 0 |
| Inspector | `node --test tests/frontend/value_inspector.test.mjs` | Exit 0 |
| Routing | `node --test tests/frontend/routing_organizer.test.mjs` | Exit 0 |
| Crop | `node --test tests/frontend/crop_editor.test.mjs` | Exit 0 |
| Video | `node --test tests/frontend/video_cutter.test.mjs` | Exit 0 |
| Python lint | `python -m ruff check .` | Exit 0 |
| Python units | `python -m pytest -q tests/unit` | Exit 0 |
| Node metadata | `comfy node validate` | Exit 0 |
| Build archive in authorized isolated output | `comfy node pack` | Exit 0; inspect produced archive |
| Archive tests | `python -m pytest -q tests/package --archive node.zip` | Exit 0 against the new isolated archive |
| Minimum ComfyUI integration | `python -m pytest -q tests/integration --comfy-ref v0.28.0 --archive node.zip --device cpu` | Exit 0 in prepared integration environment |
| Documentation index | `python3 .codex-context/ctx.py ingest` then `python3 .codex-context/ctx.py status` | Ingest succeeds; configured sources fresh |

The integration harness may need prepared ComfyUI environments/assets; read
`tests/integration/harness.py` and its conftest before invoking it. Do not assume
it is a no-network unit test. A current-version qualification run must use the
actual version identified in Phase 0, not an invented moving tag.

An Impeccable detector may be run on changed web files using the installed
skill's `scripts/detect.mjs --json web` once at the end. It returned `[]` during
the earlier audit, but its static scan is not proof for dynamically created DOM
or Canvas controls. The actual UI/browser matrix is mandatory.

## Focused regression coverage

Match existing dependency-free tests and avoid a framework/build addition.
Keep or add tests for these observable regressions, not one test per style token:

| Risk | Observable regression check |
|---|---|
| Adaptive LoRA target drift | A click on the rendered toggle/strength/menu location changes only that row/action before and after resize; right-click and empty gaps do not mutate data |
| Saved LoRA corruption | Combined/separate strengths, row reorder, full paths and missing saved folders survive serialize/configure without dropped or duplicated rows |
| Ambiguous filename display | Different full paths with the same basename remain distinguishable and full relative paths can be retrieved without changing selected LoRAs |
| Expansion changes execution | Toggle media view in both modes; original backend values and API prompt inputs are identical |
| Workflow positional shift | With hole-including and hole-omitting serialization, exact original native values restore in order after visual controls are added |
| Disclosure restore | New/absent/malformed properties are compact; explicit true/false survives configure, clone and copy/paste; unrelated properties are untouched |
| Auto-fit overwrites user sizing | Content may grow a small node; a user-enlarged or saved node is not shrunk by source loading, filter changes, restore or disclosure |
| Crop view resets frame | Resize/disclosure preserve source coordinates, loading generations and deferred execution result; derived crop height remains read-only |
| Hidden video controls override links | Connected boundaries remain locked, inactive representation does not lose saved data, and disconnect restores the local value |
| Hidden filmstrip work | No thumbnail decoding while hidden; resume bounded pending work without metadata re-probe or a second capture stream |
| Button key bubbling | Space on disclosure/transport button performs its own action once; typing and range keys do not accidentally trigger global playback |
| Prompt toolbar regressions | Selection insertion and caret/focus are preserved; failed refresh retains prior choices with a readable recovery message |
| Inspector status/lifetime | Last successful report remains selectable and marked stale while new execution is pending; report never enters workflow JSON |
| Routing footer mis-targeting | Footer/hint interaction cannot rename/delete a channel; disconnected restore count, links, title migration and package/category metadata remain correct |

Where existing fakes cannot establish actual DOM sizing, font fitting or screen
reader behavior, use the real browser rather than extending fakes to claim visual
proof. Do not assert source strings, exact color codes, glyph choices, labels or
incidental coordinates merely because earlier tests did. Preserve the meaningful
behavior those tests were attempting to protect.

## Real-browser acceptance matrix

Use OMP's managed browser with a dedicated tab and the actual running ComfyUI.
Observe structure/state, exercise actions, inspect computed styles/bounding boxes
where applicable, then capture screenshots of the actual node surface. Canvas
controls require visible inspection and interaction; DOM-only detectors cannot
see them. Stop any temporary server started solely for verification.

Cover these dimensions in representative combinations rather than claiming a
full Cartesian product:

- Minimum/current supported frontend and ComfyUI; legacy and Nodes 2.0 renderers.
- Light and dark palettes, plus one custom palette and a user-assigned node color.
- Node widths 300, 400 and 600px where the host permits; each renderer's actual
  minimum width otherwise. Graph zoom 75%, 100%, 150%; browser zoom 200% for DOM.
- Long names, duplicate basenames, non-ASCII text and approximately doubled
  labels. No new translation catalog is required.
- New node, old saved workflow, saved expanded/compact, clone/copy-paste, and
  full graph collapse where already supported. Routing remains non-collapsible.
- Pointer and keyboard operation; visible focus, non-color-only state,
  connected/disabled/loading/error/stale/empty views.

Observable acceptance:

1. No overlapping controls, clipped essential text, horizontally compressed
   filenames, or status text that can only be read on hover.
2. Meaningful control hit rectangles do not overlap and match what is drawn.
3. One small teal marker per custom visual node; none on native-only controls;
   native user colors, wires, focus and execution indicators remain authoritative.
4. Enlarged inspector/editor content uses available space; compact media views
   no longer force the old large minimum heights on new nodes.
5. Repeated view toggles do not mutate graph values or add network requests.
6. Existing prompt/API values and node metadata compare equal before/after
   view-only actions; only the authorized Boolean workflow property may differ.
7. Removing/unloading extension enhancement leaves the existing fallback
   capabilities intact. No new dependence on preview success or CSS loading.
8. No per-row theme DOM reads, duplicate stylesheet loads, leaked observers or
   perpetual redraw/media loops across repeated node creation/removal.

## Done criteria

- [x] Shared treatment has real Canvas and DOM callers; no global/private styling.
- [x] Adaptive LoRA rows meet filename, strength, pointer, path and serialization contracts.
- [x] Prompt, ratio, inspector and routing refinements are complete.
- [x] Crop and video have functional compact/expanded presentation and saved view state.
- [x] Existing native-only nodes remain native; no backend or ID/schema changes.
- [x] Relevant regression tests and all frontend tests pass.
- [x] Required real-browser matrix and minimum/current renderer qualification are recorded.
- [x] Applicable Python/package checks pass against the actual produced archive.
- [x] DESIGN.md and existing user help match the shipped interactions.
- [x] Temporary artifacts removed; index refreshed; plan index updated with evidence.

## STOP conditions and maintenance risks

Stop the affected phase and report the concrete conflict rather than improvising:

- A requirement needs a new execution input, node ID, changed serialized LoRA
  payload, renamed category, altered video semantics, or higher compatibility floor.
- A new API is unavailable on the minimum frontend and preserving the agreed
  behavior would require core patching or silently dropping a supported renderer.
- View changes mutate crop/video values, saved local connected values, row order
  or links. Treat this as a contract regression, not a cosmetic discrepancy.
- The only way to fit a control is to compress text, overlap hit areas, rewrite
  saved labels or force user node widths.
- A repeated verification failure remains after two focused fix attempts.
- The real UI environment or essential test assets cannot be obtained safely;
  list what was tried and the missing prerequisite. A fake screenshot is not a
  substitute, and a clean detector does not remove this blocker.

Future reviewers should focus on draw/computeSize/hit-test agreement, widget
serialization, configure ordering, focus when details hide, connected input
locks, theme changes and observer/media cleanup. Keep presentation and execution
state separate. Do not introduce extra state merely to avoid recomputing cheap
layout facts, and do not compute expensive catalog/theme facts on every paint.

## Planning evidence and limitations

- Source inspected: seven custom visual modules, native-only wrapper boundaries,
  registration/metadata, LoRA tests, design/domain documents, and relevant ADRs.
- Independent read-only mapping: MediaPlanConstraints and UtilityPlanConstraints.
- Official API documentation rechecked on 2026-09-06:
  [extension hooks](https://docs.comfy.org/custom-nodes/js/javascript_hooks) and
  [Comfy objects/widgets](https://docs.comfy.org/custom-nodes/js/javascript_objects_and_hijacking).
  Current documentation explicitly warns against global/prototype hijacking;
  it does not prove a new API exists at the minimum supported frontend.
- Numeric evidence: browser filename measurement from the audit and teal fallback
  contrast calculations during planning. No live ComfyUI visual pass was run.
- No frontend/backend/package tests were run for this documentation-only plan.
  The preceding instruction-update task found system Python lacked pytest;
  environment readiness must be established by the executor, not assumed.
- No source, DESIGN.md, glossary, ADR, backend contract or dependency was changed
  while preparing this plan.
- `plans/` is not included by the current `.codex-context/config.toml` source
  patterns. Ingesting existing configured sources does not index this plan.
  Read it directly through the plan index; changing index configuration is not
  part of this planning-only deliverable.

## Implementation evidence — 2026-09-06

- Reconciled against `ec43992`: existing changes were root `AGENTS.md`,
  `.omp/RULES.md`, and the untracked `plans/` directory; preserved.
- Baseline frontend suite: 126 passed, zero failures.
- Prepared project Python environment: Ruff passed; unit tests 339 passed,
  2 skipped; `comfy node validate` passed. These are baseline checks, not final
  qualification of the redesign.
- Configured Linux ComfyUI target was absent. Found an existing Windows
  ComfyUI 0.33.0 / frontend 1.49.6 installation; not yet visually qualified.
- With explicit user approval, prepared an isolated ComfyUI 0.28.0
  (`700821e1364eaab0e8f21c538a2131719fec57bf`) runtime with frontend 1.45.21.
  Started CPU-only with only this pack whitelisted and API nodes disabled.
- Real browser: created seven custom surfaces; captured legacy/dark and
  Nodes 2.0/light baseline screenshots and scratch workflow/prompt data.
  Both renderer settings are available. This is not the final visual matrix.
- Shared-treatment gate: 29 LoRA/Prompt tests passed. Verified one stylesheet
  and correct marker variant after live light/dark changes. Fixed an observed
  theme-event ordering issue before continuing.
- Minimum frontend source inspection confirmed three load-bearing adapter
  contracts: `addCustomWidget` can return a normalized wrapper; Nodes 2.0
  visibility reads `widget.options.hidden`; its legacy Canvas adapter exposes
  `triggerDraw`. Surface integrations are being reconciled with these facts.
- Real crop dragging also exposed the preexisting callback mismatch:
  `CanvasPointer` callbacks are assigned functions and receive native events;
  they are not callback-registration methods. The redesign now uses the
  actual pointer contract, with focused regression coverage in progress.
- Media regression run during integration: 53 passed, one test-fixture failure
  from assuming absent presentation properties existed; fixture corrected.
  Final media/integrated suites and complete browser/package qualification
  remain outstanding. No completion criterion is certified by this entry.

### Final qualification

- Implemented all seven surfaces, the shared Canvas/DOM treatment, and the
  strict-Boolean media disclosure state. Backend source, registration IDs,
  execution schemas, dependencies, and compatibility floors remain unchanged.
- Real hosts: ComfyUI 0.28.0 / frontend 1.45.21 and ComfyUI 0.33.0 /
  frontend 1.49.6. Representative combinations covered legacy and Nodes 2.0,
  light and dark palettes, 300/400/600px widths, compact/expanded media,
  workflow reload, Unicode and duplicate filenames, and long content.
  Supplemental checks covered a custom palette, user node color, graph zoom,
  and actual 200% browser zoom. These are observed browser checks, not a
  claimed full Cartesian product.
- The LoRA pointer matrix passed 24 combinations: two hosts, two renderers,
  three widths, and combined/separate strengths. Native direct entry,
  replacement, reorder, removal, addition, full-path selection, and saved-row
  restoration also passed on both hosts without changing neighboring rows.
- Real resizing exposed stale native widget hit bounds. Drawing and native hit
  widths now share the same renderer-aware resolution. Crop dragging after a
  narrow-to-wide renderer transition moved source x from 140 to 104 while
  preserving the 360-by-360 crop on both hosts.
- The user explicitly approved native routing input-slot reconstruction after
  shallow Nodes 2.0 label refresh failed. Changed labels now reconstruct only
  the affected native slot and retain pending-channel membership. Both hosts
  passed visible label updates, native rename dialogs, named-channel addition,
  renderer changes, reload, and real link dragging into reconstructed slots.
  Links, types, and execution prompts remained unchanged. Existing unused,
  unlabeled-channel normalization is preserved.
- Crop/video disclosure and theme/size changes preserved execution inputs.
  A real video-metadata failure exposed native numeric fallback controls;
  recovery removed the fallback without changing the saved segment.
- Final frontend suite: **134 passed**. Ruff passed; Python unit suite:
  **339 passed, 2 skipped**. `comfy node validate` and isolated
  `comfy node pack` passed.
- Final candidate package suite: **28 passed, 1 skipped**. The optional
  immutable-release comparison was intentionally skipped for candidate mode.
  A separate negative check proved the unchanged 1.5.0 manifest rejects this
  modified candidate. Release CI explicitly requires the tag-specific approved
  manifest; no release manifest was rewritten and nothing was published.
- The final extracted archive passed the minimum-host integration suite:
  **53 passed, 1 skipped**, including exact object-info comparison and sizing,
  dynamic image saving, crop, and video workflows. The alternative tag-install
  path was skipped. Tests ran from an isolated regular test-package copy to
  avoid an installed `tests` namespace collision; production behavior was not
  substituted or mocked.
- Archive inspection: **51 files, 339426 uncompressed bytes**; all shared assets
  present, with no plan files, private paths, fixture catalogs, or smoke tools.
  SHA-256: `7801af2864d40ad4ead83bfe590ce1ab87fa93b904140a0d9c39199481e77aeb`.
- README, existing node help, and DESIGN.md describe the shipped interactions.
  The installed design-md skill supplies no structural validator; none was
  invented or claimed. The supplemental Impeccable detector returned `[]`.
- Non-blocking existing host warning: ComfyUI 0.28.0 reports that
  `LoadAndCropImage.IS_CHANGED()` does not accept `ratio_width`. The crop
  workflow completed and its output assertions passed. Backend cache-signature
  maintenance is outside this presentation-only change.
- Qualification servers stopped and all three managed browser tabs released.
  Isolated runtimes, fixture catalogs, candidate archive, and scratch drivers
  were removed after recording the non-private evidence above. The user's
  existing installation, original archive, and initial working changes remain
  untouched. Context ingest/status reported fresh sources with zero stale or
  orphaned documents. No commit, release, or publication was performed.
