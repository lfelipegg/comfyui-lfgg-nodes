# Audit of the local ComfyUI custom-node references

Reviewed: 2026-07-26

## Bottom line

Do not use any one reference pack as the template for the new project.

The best starting architecture is the small, explicit layout in
`reference/custom-nodes/lfgg_nodes/`: one backend module per node, a thin
registration file, per-node documentation, and focused tests. Selectively borrow
ideas from the other packs:

1. Pixaroma's image loader for correct image/mask conversion, cache invalidation,
   and input validation.
2. rgthree's image resize node for calling ComfyUI's own tensor resize helper.
3. LFGG's dynamic image saver for output metadata and path templating, after
   strengthening its symlink containment.
4. Impact Pack's `SEGS` nodes for the distinction between ComfyUI lists and tensor
   batches, and its isolated end-to-end test strategy.
5. Pixaroma's route helpers for payload limits, identifiers, and resolved-path
   containment, after adding image decode/pixel limits.

Avoid copying the large packs' global monkey patches, import-time writes or
deletions, runtime dependency installation, internal ComfyUI mutations, wildcard
type tricks, and monolithic registration.

## Scope and reference fidelity

This audit covers the seven projects immediately under
`reference/custom-nodes/`. Node counts are static counts of mapping entries in
the inspected files, not a promise about what a particular ComfyUI runtime will
successfully import.

The local material is reference evidence, not authoritative upstream source:

- Four directories are embedded Git worktrees with substantial local state. At
  review time, `git status --porcelain` reported 15 entries for `ComfyMath`, 422
  for `ComfyUI-Pixaroma`, 14 for `lfgg_nodes`, and 108 for `rgthree-comfy`.
  Consequently, a nested `HEAD`, version string, or upstream README does not
  establish the provenance of every local file.
- `reference/custom-nodes/lfgg_nodes/examples/ComfyUI_windows_portable/ComfyUI/`
  contains an entire ComfyUI snapshot. The same `examples/` directory contains
  React, Vue, and cookiecutter extension templates. These were excluded from the
  pack inventory and must not be treated as current ComfyUI documentation.
- `lfgg_nodes` also contains stale bytecode for source files not present in the
  actual pack, such as `__pycache__/multi_label_reroute...pyc` and
  `__pycache__/titled_reroute...pyc`.
- Findings below cite exact inspected local paths. Current behavior claims are
  grounded in the official ComfyUI documentation linked in the next section,
  not inferred from the embedded snapshots.

Before copying implementation code, review license compatibility and preserve
required notices. The local licenses include Apache-2.0 (`ComfyMath`), GPL-3.0
(`comfyui-impact-pack`), AGPL-3.0 (`comfyui-impact-subpack`), and MIT
(`ComfyUI-Pixaroma`, `rgthree-comfy`, and `was-ns`). `lfgg_nodes` has no license
file in the inspected pack. Prefer reimplementing the design unless code reuse
and its license are deliberately approved.

## Official contract to design against

The references are overwhelmingly V1 nodes. That makes them useful compatibility
examples, but not the final authority for a new pack.

| Concern | Current official contract | Consequence for the new pack |
| --- | --- | --- |
| V1 registration | A node class declares `INPUT_TYPES`, `RETURN_TYPES`, `FUNCTION`, and related properties, and is exported through `NODE_CLASS_MAPPINGS`. Optional inputs may be absent at execution. Ordinary graph outputs are tuples; legacy UI/output nodes may return `{"ui": ..., "result": (...)}`. See [Properties](https://docs.comfy.org/custom-nodes/backend/server_overview). | V1 remains the broad-compatibility choice. Keep the root registration thin and prefix every stable node ID. |
| V3 registration | V3 nodes extend `io.ComfyNode`, use `define_schema`, execute through a classmethod named `execute`, and are exposed by a `ComfyExtension` returned from `comfy_entrypoint`. Future schema features are V3-only. The docs warn that the schema is still evolving; the currently documented `v0_0_2` path is also marked unstable and reexports the latest schema. See [V3 Migration](https://docs.comfy.org/custom-nodes/v3_migration) and the pinned [`v0_0_2` entrypoint source](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy_api/v0_0_2/__init__.py). | Decide the minimum ComfyUI version before coding, then pin and test the exact import against it; a numbered import is not by itself a stability guarantee. Do not depend on instance state: V3 sanitizes classes and exposes classmethods. |
| Core tensor types | `IMAGE` is `[B,H,W,C]`, normally RGB; `MASK` is `[B,H,W]`; and `LATENT` is a dictionary whose `samples` tensor is channel-first `[B,C,H,W]`. The official page documents the conventional latent `C=4`, while current core workflows also have model-specific empty-latent nodes. See [Images, Latents, and Masks](https://docs.comfy.org/custom-nodes/backend/images_and_masks). | Validate rank before indexing. Preserve batch dimensions. Convert BHWC to BCHW only around operations that require it. A node that constructs latents should state which model family/layout it supports or delegate to a core/model-aware helper. |
| Inputs and custom types | Core widget metadata belongs in the second tuple item. A custom type should have a unique uppercase name and generally use `forceInput`. `PROMPT`, `EXTRA_PNGINFO`, `UNIQUE_ID`, and `DYNPROMPT` are official hidden inputs. A `*` wildcard is accepted by the frontend but is not officially supported by the V1 backend without bypassing type validation. See [Hidden and Flexible Inputs](https://docs.comfy.org/custom-nodes/backend/more_on_inputs). | Prefer concrete types or a pack-prefixed domain type. Treat arbitrary/wildcard inputs as a compatibility exception, not the default interface. In V3, evaluate `MultiType`, `MatchType`, dynamic inputs, or autogrow before reproducing equality hacks. |
| Caching and validation | ComfyUI caches by input values. `IS_CHANGED` returns a comparable fingerprint, not a boolean; `NaN` forces every run. `VALIDATE_INPUTS` returns `True` or a useful error string, but requesting an argument there bypasses its default validation. See [Properties](https://docs.comfy.org/custom-nodes/backend/server_overview). | Hash external files and all hidden state that changes output. Avoid unconditional `NaN`. Validate again inside execution for values that can arrive through links or API workflows. |
| Switches | Inputs are eager by default. The official lazy protocol is `{"lazy": True}` plus `check_lazy_status`; a switch is the primary example. See [Lazy Evaluation](https://docs.comfy.org/custom-nodes/backend/lazy_evaluation). | A switch that evaluates every upstream branch is functionally correct but can waste model loads and inference. Implement branch selection lazily. |
| Frontend extensions | Export `WEB_DIRECTORY`, put browser modules there, and register them through `app.registerExtension` and documented hooks. See [JavaScript Extensions](https://docs.comfy.org/custom-nodes/js/javascript_overview) and [Comfy Hooks](https://docs.comfy.org/custom-nodes/js/javascript_hooks). The docs explicitly deprecate monkey-patching `app` and prototype functions; see [Comfy Objects](https://docs.comfy.org/custom-nodes/js/javascript_objects_and_hijacking). | Add JavaScript only when the backend schema cannot provide the interaction. Use supported hooks and frontend version constraints. Do not replace `app.queuePrompt`, `app.graphToPrompt`, or `api.apiURL`. |
| Custom routes | Register namespaced `PromptServer.instance.routes`; use POST for mutation and `api.fetchApi` on the client. `PromptServer` supplies no general authentication gate for local custom routes. See [Routes](https://docs.comfy.org/development/comfyui-server/comms_routes) and the pinned [server middleware](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/server.py#L115-L190). | Validate type, size, identifier, extension, decoded content, and real resolved containment at the route boundary. GET handlers must not mutate state. Put sensitive operations behind node-owned authorization or a trusted reverse proxy; CORS and `Comfy-User` are not authentication. |
| Distribution | Registry packages use PEP 621 `[project]` plus `[tool.comfy]`; `requires-python`, `requires-comfyui`, frontend constraints, and archive includes are available. See [pyproject.toml](https://docs.comfy.org/registry/specifications) and [Publishing Nodes](https://docs.comfy.org/registry/publishing). | Ship one authoritative dependency declaration, a valid license path, explicit compatibility bounds, and only needed artifacts. |
| Security | Registry standards prohibit `eval`/`exec` and runtime package installation through `subprocess`, require documentation, and forbid interfering with other custom nodes. See [Registry Standards](https://docs.comfy.org/registry/standards). | No runtime `pip`, global loader replacement, deletion of another extension's files, or executable workflow input. Model downloads should be explicit, checksum-verified, and separated from import. |

## Inventory

| Pack | Statically registered nodes | Structure and notable interfaces | Tests and packaging | Assessment |
| --- | ---: | --- | --- | --- |
| `ComfyMath` | 53 | Eight small category modules merged in the root; custom `NUMBER`, `VEC2`, `VEC3`, and `VEC4` contracts; no frontend or routes. | No tests found. Poetry-era `pyproject.toml`, no `[tool.comfy]`. | Useful dispatch-table and aggregation examples; weak current template. |
| `ComfyUI-Pixaroma` | 34 active (plus 2 development-only) | One/few nodes per backend file, a large browser application, assets, and many server routes. `WEB_DIRECTORY="./js"`. | PEP 621 and Registry metadata; a handful of parity scripts and one JS switch test, not broad automated node coverage. | Best rich image-loader and route examples; frontend is far too coupled to copy wholesale. |
| `comfyui-impact-pack` | 197 | Domain modules for detection, detailing, pipes, lists, hooks, and server integration; one very large root mapping; custom `SEGS` and pipe types. | PEP 621 Registry metadata, heavy dependencies, shell wildcard suites, and an isolated E2E strategy. | Strong domain/type and E2E reference; too large and internally coupled as a baseline. |
| `comfyui-impact-subpack` | 1 | A focused Ultralytics provider plus detector implementation; custom model folders; no web extension. | PEP 621 Registry metadata; no tests found. Installer downloads models. | Provider node is readable; its global `torch.load` replacement is a stop-ship anti-pattern. |
| `lfgg_nodes` | 9 | One backend module per node, explicit root aggregation, two small JS extensions, per-node docs. | Three focused `unittest` files. No root `pyproject.toml`, dependency declaration, or license found. | Best structural seed, but harden file access and add modern distribution metadata. |
| `rgthree-comfy` | 24 plus 2 config-gated | Backend modules paired with a substantial TypeScript/Sass frontend and namespaced routes. | PEP 621 Registry metadata; custom TypeScript workflow test harness exists, while `package.json` only exposes a build command. | Excellent core-resize reuse and frontend engineering ideas; several invasive compatibility hacks must be excluded. |
| `was-ns` | 220 baseline, plus 1 when sibling `ComfyUI_ADV_CLIP_emb` is installed | Roughly 14,800-line backend monolith, broad image/text/model/network functionality, import-time configuration and dependency management; root exports only the class map. | PEP 621 Registry metadata and a very heavy dependency set; one small pytest target built by `exec`-extracting a class. | Historical compatibility reference only, not an architectural or security template. |

## Cross-reference findings

### Registration and module boundaries

The clearest V1 aggregation patterns are:

- `reference/custom-nodes/lfgg_nodes/__init__.py:3-38`, which imports each node
  module and merges its class/display mappings, then exposes a standard
  `WEB_DIRECTORY`.
- `reference/custom-nodes/ComfyMath/__init__.py:1-29`, which merges category
  mappings and derives display names from prefixed IDs.

Use the LFGG shape, but make the merger reject duplicate IDs instead of silently
letting the last dictionary update win. Keep durable workflow IDs distinct from
display labels. A stable ID such as `LfggImageBatchSelect` is much safer than the
generic IDs used by WAS (`"Checkpoint Loader"`) or Impact (`"SAMLoader"`), which
are more likely to collide.

Pixaroma demonstrates the cost of an oversized root:
`reference/custom-nodes/ComfyUI-Pixaroma/__init__.py:1-162` manually imports and
merges dozens of maps. Impact is more coupled still:
`reference/custom-nodes/comfyui-impact-pack/__init__.py:43-64` uses wildcard
imports before a 197-entry dictionary. WAS puts most behavior and all 220 entries
in `reference/custom-nodes/was-ns/WAS_Node_Suite.py:14437-14658`.

For the new pack, use:

```text
package/
├── __init__.py              # registration only
├── nodes/
│   ├── image_batch_select.py
│   └── ...
├── shared/                  # tensor/path helpers used by 2+ nodes
├── web/                     # only if needed
├── tests/
├── docs/
└── pyproject.toml
```

Do not introduce a framework or registry abstraction until repetition actually
appears. Plain modules and dictionaries are easy to inspect and debug.

### Type contracts and execution state

Good examples:

- `reference/custom-nodes/lfgg_nodes/image_batch_select.py:9-30` validates an
  IMAGE's rank and non-empty batch; `:85-89` slices rather than indexing so the
  output remains `[1,H,W,C]`.
- `reference/custom-nodes/comfyui-impact-pack/modules/impact/core.py:46-48`
  gives a complex detection result a single named domain record.
- `reference/custom-nodes/comfyui-impact-pack/modules/impact/segs_nodes.py:771-811`
  explicitly contrasts a ComfyUI output list (`OUTPUT_IS_LIST`) with one
  batched MASK tensor.

When adopting a domain type, prefix its wire name (`LFGG_SEGS`, not `SEGS`) and
centralize its representation. Impact Pack and Subpack each define their own
`SEG` namedtuple
(`reference/custom-nodes/comfyui-impact-pack/modules/impact/core.py:46-48` and
`reference/custom-nodes/comfyui-impact-subpack/modules/subcore.py:19-21`);
duplicated structural contracts can
drift silently.

Patterns to avoid:

- ComfyMath mixes the standard `"BOOLEAN"` contract
  (`reference/custom-nodes/ComfyMath/src/comfymath/bool.py:3-53`) with
  undeclared `"BOOL"` outputs
  (`reference/custom-nodes/ComfyMath/src/comfymath/number.py:43,81` and
  `reference/custom-nodes/ComfyMath/src/comfymath/int.py:78,116`).
- Its `VEC*` inputs use a custom type as if it were a widget
  (`reference/custom-nodes/ComfyMath/src/comfymath/vec.py:7-14`) without a
  documented custom widget or `forceInput`, contrary to the official
  custom-type guidance.
- Pixaroma's
  `reference/custom-nodes/ComfyUI-Pixaroma/nodes/node_switch.py:34-69`
  predeclares 32 `AnyType` inputs and
  relies on a string whose `__ne__` always returns false. rgthree generalizes the
  same trick in `reference/custom-nodes/rgthree-comfy/py/utils.py:8-59`. These
  are compatibility techniques, not safe general contracts. Pixaroma's switch
  also lacks lazy inputs, so every connected branch is evaluated before
  selection.
- Instance state must be treated carefully. LFGG's wildcard keeps
  `_reproduce_used` on `self`
  (`reference/custom-nodes/lfgg_nodes/prompt_wildcard.py:228-232,301-318`) and its
  LoRA loader caches a loaded object on `self`
  (`reference/custom-nodes/lfgg_nodes/lora_loader_by_path.py:54-57,118-130`).
  That works as a V1 implementation detail but cannot be carried unchanged into
  V3, where execution is classmethod based and node instances expose no state.

### Images, masks, latents, lists, dtype, and device

The strongest image-loading reference is
`reference/custom-nodes/ComfyUI-Pixaroma/nodes/node_load_image.py:90-253`:

- It resolves files through `folder_paths`, transposes EXIF orientation, handles
  multiple frames, normalizes RGB to BHWC, produces BHW masks, and follows
  ComfyUI's inverted-alpha mask convention (`:137-213`).
- It batches frames with `torch.cat` (`:225-230`).
- It fingerprints both the file bytes and hidden resize state and validates the
  annotated path (`:240-253`).

The strongest resize reference is
`reference/custom-nodes/rgthree-comfy/py/image_resize.py:14-117`. It reads BHWC,
moves channels to BCHW only for `comfy.utils.common_upscale`, restores BHWC, and
allocates padding with the input dtype and device. Reusing a core helper is
preferable to maintaining an independent resampler.

LFGG's latent-size nodes correctly distinguish image BHWC from latent BCHW, but
construct `(batch,4,h/8,w/8)` directly:

- `reference/custom-nodes/lfgg_nodes/image_resolution_by_ratio.py:108-141`
- `reference/custom-nodes/lfgg_nodes/latent_size_by_ratio.py:121-153`
- `reference/custom-nodes/lfgg_nodes/pixel_budget_latent_size.py:80-114`

That is a valid conventional SD latent, not a model-neutral guarantee. Name or
document the model-family constraint, or route size output into the appropriate
core empty-latent node instead of manufacturing a generic `LATENT`.

Do not lift Impact's tensor helper file wholesale. It contains useful BHWC/BCHW
patterns
(`reference/custom-nodes/comfyui-impact-pack/modules/impact/utils.py:71-124`),
but also suspect PyTorch operations: negative repeat counts and `Tensor.copy()`
at `:25-68`, a PIL-to-tensor helper that omits the batch dimension at `:176-183`,
and squeeze-based mask helpers at `:613-640` that can collapse meaningful batch
dimensions. WAS has a similar single-image assumption:
`reference/custom-nodes/was-ns/WAS_Node_Suite.py:404-428` applies unrestricted
`.squeeze()` in PIL conversions.

New shared tensor helpers should specify accepted ranks, return ranks, value
range, dtype, device behavior, and batch semantics in their docstrings and
tests.

### Validation, errors, caching, and logging

Preferred behavior is visible in small nodes:

- `reference/custom-nodes/lfgg_nodes/image_batch_select.py:9-30` raises specific
  value errors at the boundary.
- `reference/custom-nodes/lfgg_nodes/lora_loader_by_path.py:15-24,103-131`
  rejects absolute/traversing filter subpaths, uses
  `get_full_path_or_raise`, and safe-loads through ComfyUI. Its raw string
  prefix check does **not** prove that a crafted selected name remains in the
  requested subfolder: `styles/../other.safetensors` passes. Before reuse,
  reject traversal in the selected name and verify resolved containment under
  the selected subfolder; core lookup only keeps the path within configured
  LoRA roots, and symlinks remain relevant.
- `reference/custom-nodes/comfyui-impact-subpack/modules/subpack_nodes.py:31-60`
  logs searched model locations and raises one actionable missing-model error.
- Pixaroma's load node uses both `IS_CHANGED` and `VALIDATE_INPUTS`, rather than
  forcing every execution.

Use the standard `logging` module with a pack prefix for diagnostics. Avoid
routine `print`, import banners, and broad exception suppression. Representative
noise or error-hiding examples include:

- ComfyMath printing every selected resolution
  (`reference/custom-nodes/ComfyMath/src/comfymath/graphics.py:98-121`).
- Pixaroma printing an import banner
  (`reference/custom-nodes/ComfyUI-Pixaroma/__init__.py:165-234`).
- Impact Subpack swallowing every exception around Manager integration
  (`reference/custom-nodes/comfyui-impact-subpack/__init__.py:30-38`).
- WAS suppressing broad warning categories globally
  (`reference/custom-nodes/was-ns/WAS_Node_Suite.py:14783-14792`).

Catch an exception only where the node can add context or provide a deliberately
documented fallback. Returning a blank image after an arbitrary processing
failure hides workflow defects and makes cached failures look successful.

### Filesystem and server-route boundaries

LFGG's saver is a useful starting point:
`reference/custom-nodes/lfgg_nodes/save_image_dynamic.py:112-174,177-280`
rejects absolute paths and `..`, constrains output lexically with
`commonpath`, embeds prompt metadata, preserves ComfyUI's output UI payload, and
avoids overwriting by advancing a counter. It should use resolved/real paths
before writing so a pre-existing symlink under the output directory cannot
escape the intended root.

Two LFGG text helpers need correction before reuse:

- `reference/custom-nodes/lfgg_nodes/prompt_wildcard.py:46-74,143-161` joins
  free-form `__token__` values to the wildcard root without rejecting `..` or
  proving resolved containment. A token such as a traversing relative path can
  reach readable text outside the wildcard directory.
- `reference/custom-nodes/lfgg_nodes/prompt_library.py:112-123` normalizes
  slashes but does not reject traversal or resolve-and-contain. The dropdown's
  normal validation is useful defense in depth, but the file helper itself
  should be safe for linked/API values.
- Both modules create directories and may rewrite `config.ini` while node
  definitions are being queried
  (`reference/custom-nodes/lfgg_nodes/prompt_library.py:18-42` and
  `reference/custom-nodes/lfgg_nodes/prompt_wildcard.py:19-43`). Put mutable
  configuration under ComfyUI user data and keep schema discovery read-only.
  Their class-level choice caches also require an explicit refresh path.

Pixaroma has the best local route boundary:
`reference/custom-nodes/ComfyUI-Pixaroma/server_routes.py:257-340` caps base64
input, restricts identifiers, resolves paths with `realpath`, and checks
containment before saving. Its asset routes similarly validate and contain paths
(`:61-105`). Preserve those ideas, but improve `_decode_image` (`:300-311`) with
strict base64 decoding, accepted-format checks, eager `verify/load`, a decoded
byte limit, and a maximum pixel count. A small compressed payload can otherwise
expand into an excessive image. Avoid directory creation at module import
(`:257-260`).

rgthree shows two route mistakes not to repeat:

- `reference/custom-nodes/rgthree-comfy/py/server/routes_model_info.py:100-129`
  deletes cached data from a GET route. Mutations belong on POST/DELETE and
  should receive CSRF/trust-boundary review.
- `reference/custom-nodes/rgthree-comfy/py/utils.py:161-167` checks path
  containment with a raw string prefix. A sibling such as `/safe-root-evil`
  shares the prefix. Use `Path.resolve()` plus `relative_to`, or `realpath` plus
  `commonpath`.

### Frontend extensions

The standard root declaration is correctly demonstrated by LFGG
(`reference/custom-nodes/lfgg_nodes/__init__.py:38`) and Pixaroma
(`reference/custom-nodes/ComfyUI-Pixaroma/__init__.py:159-162`). rgthree also
has a disciplined source and generated-web split
(`reference/custom-nodes/rgthree-comfy/package.json:1-11`), TypeScript frontend
types, and workflow-oriented tests under
`reference/custom-nodes/rgthree-comfy/src_web/comfyui/tests/`.

The main lesson from the rich frontends is restraint. Pixaroma replaces
`app.graphToPrompt`, `api.queuePrompt`, and `app.queuePrompt` in
`reference/custom-nodes/ComfyUI-Pixaroma/js/prompt_pack/index.js:181-209,233-263,349-362`.
rgthree replaces `api.apiURL` in
`reference/custom-nodes/rgthree-comfy/src_web/comfyui/rgthree.ts:75-86`. These
patches are exactly the kind the official frontend documentation marks
deprecated and fragile. They also compose poorly when multiple packs wrap the
same function.

Prefer:

1. A pure backend node.
2. Standard input metadata and V3 schema features.
3. A small `app.registerExtension` using documented hooks.
4. A namespaced route or message only when client/server communication is
   essential.

If custom frontend code is necessary, pin/test supported
`comfyui-frontend-package` versions, generate distributable assets in CI, and run
at least one real browser workflow test.

### Dependencies, imports, and model loading

Imports should register code, not alter the installation.

Stop-ship patterns in the references:

- Impact Subpack replaces process-global `torch.load` at
  `reference/custom-nodes/comfyui-impact-subpack/modules/subcore.py:181-313`.
  Although it attempts a safe load first, the basename-only whitelist
  (`:195-203,225-264`) can match unrelated files, and old PyTorch falls back to
  `weights_only=False` (`:296-309`). This affects every other node in the
  process. Call a scoped safe loader at the exact load site.
- rgthree recursively deletes old web-extension directories during import
  (`reference/custom-nodes/rgthree-comfy/__init__.py:85-92`).
- Impact mutates the private/global `nodes.EXTENSION_WEB_DIRS` rather than
  exporting `WEB_DIRECTORY`
  (`reference/custom-nodes/comfyui-impact-pack/__init__.py:449-453`).
- WAS creates user/config files, archives and deletes legacy files during import
  (`reference/custom-nodes/was-ns/WAS_Node_Suite.py:167-203,231-294`) and runs
  `pip freeze`, uninstall, and install through subprocess (`:377-402`). It
  contains many execution-time calls to its installer, but those calls
  currently return without installing because they omit `uninstall_first`.
  Actual uninstall/install occurs in import-time branches that pass that
  argument (`:14726-14781`). Import-time package mutation still conflicts
  directly with Registry standards.
- WAS performs network downloads without robust timeouts/checksums in its generic
  helper (`reference/custom-nodes/was-ns/WAS_Node_Suite.py:498-518`) and
  downloads a wildcard pantry on demand (`:523-539`).

Impact Subpack's installer automatically downloads three model files unless a
sentinel file exists
(`reference/custom-nodes/comfyui-impact-subpack/install.py:24-41`). For a new
pack, make model acquisition explicit, show destination and size, pin a
trustworthy URL, verify a digest, and never make normal import depend on network
access.

Packaging observations:

- Pixaroma, Impact Pack/Subpack, rgthree, and WAS have `[project]` and
  `[tool.comfy]`; ComfyMath still uses only Poetry
  (`reference/custom-nodes/ComfyMath/pyproject.toml:1-19`); LFGG has no root
  package metadata.
- Pixaroma's metadata names `LICENSE.txt`, but the inspected file is `LICENSE`.
- WAS declares OpenCV differently in
  `reference/custom-nodes/was-ns/pyproject.toml:6` and
  `reference/custom-nodes/was-ns/requirements.txt:11`, illustrating dependency
  drift from two handwritten sources.
- The inspected Registry projects omit useful `requires-python` and
  `requires-comfyui` bounds. Add them when support has been tested.

Use one authoritative dependency source. Keep optional features in extras and
import their libraries only when that feature runs, with an actionable error.

### Tests

The best small-unit example is
`reference/custom-nodes/lfgg_nodes/tests/test_image_batch_select.py:33-124`.
It covers selection behavior, empty/bad shapes, output metadata, and stable node
registration without importing a full ComfyUI server. Add real Torch tests to
that style so dtype, device, squeeze, concatenate, and non-contiguous tensor
behavior are not simulated away.

The best integration strategy is Impact's
`reference/custom-nodes/comfyui-impact-pack/docs/E2E_TEST_STRATEGY.md:20-40,96-131`.
It starts a clean server with `--disable-all-custom-nodes` and a whitelist,
checks `/object_info`, then submits workflows through `/prompt`. Its wildcard
suite documents encoding, recursion, error, cache, and statistical cases in
`reference/custom-nodes/comfyui-impact-pack/tests/README.md:1-129`. Reuse the
layered idea, not the suite's unverified “100% pass” prose.

rgthree's TypeScript tests run actual node graphs through a custom environment;
for example,
`reference/custom-nodes/rgthree-comfy/src_web/comfyui/tests/image_or_latent_size_tests.ts:10-103`
exercises IMAGE and LATENT workflows. This is valuable when a browser extension
changes sockets or widgets, but `package.json` should expose a repeatable test
command.

WAS is the negative example:
`reference/custom-nodes/was-ns/tests/was_mock.py:1-10` reads source text and
executes a sliced class definition. Besides violating the Registry's `exec`
rule, that test does not exercise normal imports or registration.

The new pack should have four layers:

1. Pure helper tests for sizing, parsing, sanitization, and boundary cases.
2. Node contract tests for schema, tuple shape, errors, dtype/device, and batch
   behavior.
3. A clean ComfyUI smoke test that imports the pack and checks `/object_info`.
4. One minimal workflow per node family; add browser E2E only for frontend code.

## Per-pack verdicts

### ComfyMath

**Reuse:** category-sized modules, operation dispatch dictionaries, derived
display names, and abstract resolution behavior
(`reference/custom-nodes/ComfyMath/src/comfymath/graphics.py:61-81`).

**Do not reuse unchanged:** the old packaging, custom widget assumptions,
`BOOL`/`BOOLEAN` mismatch, print logging, and zero-vector normalization.
`reference/custom-nodes/ComfyMath/src/comfymath/vec.py:16-29` divides by the
vector norm for both normalization and normalized checks, so zero vectors
produce invalid values/warnings. There are no tests to lock behavior.

### ComfyUI-Pixaroma

**Reuse:**
`reference/custom-nodes/ComfyUI-Pixaroma/nodes/node_load_image.py:90-253`, route
path/payload primitives in
`reference/custom-nodes/ComfyUI-Pixaroma/server_routes.py:257-340`, explicit
per-module registration, and the source/assets organization when a genuinely
rich editor is required.

**Do not reuse unchanged:** the 32-slot wildcard switch, queue/serialization
monkey patches, large hidden JSON state coupled to browser code, import-time
directory creation/banner output, or broad blank-image fallbacks. Its numerous
routes and vendored assets materially expand the security and maintenance
surface.

### ComfyUI Impact Pack

**Reuse:** the concept of a typed segmentation domain object, the list-vs-batch
nodes, isolated server E2E design, explicit optional-dependency messages, and
compatibility checks at narrow call sites (for example the guarded
`execute`/`apply` bridge in
`reference/custom-nodes/comfyui-impact-pack/modules/impact/utils.py:693-706`).

**Do not reuse unchanged:** wildcard imports, huge root map, process globals and
caches
(`reference/custom-nodes/comfyui-impact-pack/modules/impact/core.py:50-57`),
background threads at import
(`reference/custom-nodes/comfyui-impact-pack/__init__.py:58-61`),
Manager-driven installation from execution
(`reference/custom-nodes/comfyui-impact-pack/modules/impact/utils.py:683-690`),
private frontend-directory mutation, or the tensor helper module wholesale.

### ComfyUI Impact Subpack

**Reuse:** custom `folder_paths` categories and an actionable detector-provider
error
(`reference/custom-nodes/comfyui-impact-subpack/modules/subpack_nodes.py:8-60`).

**Do not reuse unchanged:** global `torch.load` replacement, basename-based
unsafe-load whitelist, import-time whitelist file creation
(`reference/custom-nodes/comfyui-impact-subpack/modules/subcore.py:24-115`),
automatic model downloads, or the broad bare `except` around registration.

### LFGG nodes

**Reuse:** module/test/doc layout, prefixed IDs and categories, root aggregation,
image batch selection, LoRA loading after fixing selected-subfolder validation,
and most of the dynamic saver.

**Fix first:** prompt/wildcard resolved-path containment, mutable configuration
location, choice refresh behavior, saver symlink containment, explicit
model-family semantics for generated latents, and V3-incompatible instance
state. Add `pyproject.toml`, license, compatibility bounds, CI, and an actual
Torch/ComfyUI smoke layer.

### rgthree-comfy

**Reuse:** `reference/custom-nodes/rgthree-comfy/py/image_resize.py:14-117`,
frontend source/build separation, typed frontend code, workflow-oriented
frontend testing, namespaced routes, and configuration organization.

**Do not reuse unchanged:** import-time deletion, `api.apiURL` patching,
string-prefix path containment, mutating GET endpoints, wildcard equality/input
hacks as the default design, or generic interfaces that assume a particular
shape. For example
`reference/custom-nodes/rgthree-comfy/py/image_or_latent_size.py` distinguishes a
latent dict from “anything else” and then assumes the latter is 4D IMAGE, so a
BHW mask would not meet that implicit contract.

### WAS Node Suite

**Reuse:** only isolated algorithms after a fresh implementation and dedicated
tests. The pack is useful for discovering historical feature expectations and
legacy workflow IDs.

**Do not reuse as structure:** the monolith, generic IDs, duplicate class
definitions
(`reference/custom-nodes/was-ns/WAS_Node_Suite.py:13794-13826`), unrestricted
squeeze helpers, runtime package management, import-time mutation, unbounded
network helpers, global warning suppression, or source-executing tests. It is
the clearest example of compatibility debt accumulated when a node collection
is not split into deep, independently tested modules.

## Ranked reuse guide

| Rank | Local implementation | What to reuse | Required adaptation |
| ---: | --- | --- | --- |
| 1 | `reference/custom-nodes/lfgg_nodes/image_batch_select.py:9-100` and `reference/custom-nodes/lfgg_nodes/tests/test_image_batch_select.py:33-124` | Small node boundary, shape validation, batch-preserving slice, stable ID, contract tests. | Replace fake-only coverage with Torch cases too. |
| 2 | `reference/custom-nodes/ComfyUI-Pixaroma/nodes/node_load_image.py:90-253` | Annotated file resolution, EXIF/multiframe handling, BHWC/BHW construction, alpha inversion, `IS_CHANGED`, `VALIDATE_INPUTS`. | Keep only needed resize state; enforce decoded image/pixel limits where input is not already trusted. |
| 3 | `reference/custom-nodes/rgthree-comfy/py/image_resize.py:14-117` | Core `common_upscale`, BHWC/BCHW boundary, dtype/device-preserving padding. | Add invalid/zero-size validation and tests for batches/devices. |
| 4 | `reference/custom-nodes/lfgg_nodes/save_image_dynamic.py:112-174,177-310` | Tokenized output folders, metadata, UI response, collision counter. | Resolve real paths and defend against symlink escape; test concurrent name allocation. |
| 5 | `reference/custom-nodes/comfyui-impact-pack/modules/impact/segs_nodes.py:771-811` | Explicit ComfyUI list versus MASK batch semantics. | Use pack-prefixed custom types and centralize the record definition. |
| 6 | `reference/custom-nodes/ComfyUI-Pixaroma/server_routes.py:257-340` | Identifier allowlist, size cap, realpath containment, namespaced POST route. | Strict base64, content/magic verification, maximum pixels, structured logging, and tests. |
| 7 | `reference/custom-nodes/comfyui-impact-pack/docs/E2E_TEST_STRATEGY.md:20-40,96-131` | Isolated server, `/object_info`, `/prompt`, whitelist-only custom-node launch. | Automate lifecycle/readiness and use tiny fixture workflows/models. |
| 8 | `reference/custom-nodes/lfgg_nodes/__init__.py:3-50` | Transparent module aggregation and standard `WEB_DIRECTORY`. | Detect duplicate IDs; expose either a clean V1 or V3 entrypoint based on the chosen support policy. |
| 9 | `reference/custom-nodes/comfyui-impact-subpack/modules/subpack_nodes.py:8-60` | Custom model folders and provider errors. | Keep all model loading scoped; never patch `torch.load`. |
| 10 | `reference/custom-nodes/rgthree-comfy/src_web/comfyui/tests/` | Real graph-oriented frontend checks. | Adopt only if the pack actually ships frontend behavior, and expose a standard CI test command. |

## Non-negotiable rules for the new pack

1. No mutation, network access, model download, dependency installation, thread
   startup, banner, or deletion during module import.
2. No global monkey patch of ComfyUI, Torch, the frontend app, API client, or
   another custom node.
3. No `eval` or `exec`; workflow text is data, never code.
4. Every public node ID and custom wire type is pack-prefixed and stable.
5. Every file path is resolved and proven to be within an allowed root at the
   point of access; dropdowns are not security boundaries.
6. Every external input has size/type/rank validation and an actionable error.
7. IMAGE, MASK, LATENT, list, and batch behavior is documented and tested.
8. Use official core helpers before adding a duplicate tensor/model/file
   implementation.
9. Frontend code uses `WEB_DIRECTORY`, `app.registerExtension`, supported hooks,
   and a declared frontend compatibility range.
10. Registry metadata, license, compatibility bounds, dependencies, docs,
    unit tests, import smoke, and at least one workflow test ship together.

## Official sources

- [Custom nodes overview](https://docs.comfy.org/custom-nodes/overview)
- [V1 node properties and validation](https://docs.comfy.org/custom-nodes/backend/server_overview)
- [Datatypes](https://docs.comfy.org/custom-nodes/backend/datatypes)
- [Images, Latents, and Masks](https://docs.comfy.org/custom-nodes/backend/images_and_masks)
- [Hidden and Flexible Inputs](https://docs.comfy.org/custom-nodes/backend/more_on_inputs)
- [Lazy Evaluation](https://docs.comfy.org/custom-nodes/backend/lazy_evaluation)
- [V3 Migration](https://docs.comfy.org/custom-nodes/v3_migration)
- [Pinned `comfy_api.v0_0_2` entrypoint source](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy_api/v0_0_2/__init__.py)
- [JavaScript Extensions](https://docs.comfy.org/custom-nodes/js/javascript_overview)
- [Comfy Hooks](https://docs.comfy.org/custom-nodes/js/javascript_hooks)
- [Comfy Objects and hijacking warning](https://docs.comfy.org/custom-nodes/js/javascript_objects_and_hijacking)
- [Server custom routes](https://docs.comfy.org/development/comfyui-server/comms_routes)
- [Registry publishing](https://docs.comfy.org/registry/publishing)
- [Registry pyproject.toml specification](https://docs.comfy.org/registry/specifications)
- [Registry standards](https://docs.comfy.org/registry/standards)
- [Current ComfyUI source](https://github.com/comfy-org/ComfyUI)
