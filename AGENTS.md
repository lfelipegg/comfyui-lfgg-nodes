# Repository Agent Instructions

## Purpose and Current State

This repository is the future `comfyui-lfgg-nodes` custom-node pack. It
currently contains research only; the first nodes and compatibility target have
not been selected.

- Do not treat `reference/custom-nodes/` as project source. It is ignored,
  locally modified reference material with mixed licenses and dated patterns.
- Before scaffolding or implementing nodes, identify the requested node set,
  minimum supported ComfyUI/frontend versions, and registration generation.

## Required Reading and Source Order

Start with `docs/comfyui-info/README.md`, then read the document relevant to the
task:

- `docs/comfyui-info/custom-node-api.md` for registration, schemas, execution,
  caching, tensors, lists, routes, and frontend boundaries.
- `docs/comfyui-info/distribution-and-quality.md` for packaging, dependencies,
  tests, documentation, CI, security, and releases.
- `docs/comfyui-info/reference-audit.md` before borrowing any local reference
  design or code.

The research snapshot is dated 2026-07-26. When facts conflict or may have
changed, prefer:

1. Pinned/current ComfyUI backend or frontend source.
2. Current official ComfyUI documentation.
3. Official examples and generators.
4. Local reference nodes.

Recheck moving API and Registry facts before implementation or release,
especially V3 stability and compatibility metadata.

## Implementation Rules

- Use the standard library, ComfyUI helpers, existing project code, and existing
  dependencies before writing another abstraction or adding a dependency.
- Default to V1 `NODE_CLASS_MAPPINGS` for broad compatibility unless a stated
  requirement needs a V3-only feature. If V3 is chosen, set and test a concrete
  ComfyUI floor; do not use `comfy_api.v0_0_1`.
- Expose exactly one registration generation from an imported module. V1 takes
  precedence if V1 and V3 hooks coexist.
- Prefix stable node IDs and custom wire types with `LFGG_`. Treat IDs, input
  names/order, outputs, defaults, and list semantics as persisted workflow API.
- Keep the root `__init__.py` limited to registration. Reject duplicate node IDs
  while aggregating module mappings.
- Put ordinary transformations in small ComfyUI-independent functions. Keep
  schemas, tensor adaptation, UI envelopes, and ComfyUI imports at boundaries.
- Prefer one focused module per node or cohesive node family. Add shared helpers
  only after at least two callers need the same behavior.
- Keep module import fast and side-effect-free: no model/device allocation,
  writes, deletion, downloads, network access, installers, threads, or banners.
- Use `logging` with a pack prefix. Do not hide failures with blank outputs or
  broad exception suppression.
- Add frontend code, server routes, hidden inputs, graph expansion, wildcard
  types, and ComfyUI scheduling-list flags only for a demonstrated requirement.

## Node Contracts

- V1 execution returns tuples aligned with `RETURN_TYPES`; optional inputs must
  tolerate omission. V3 execution uses classmethods and `io.NodeOutput`.
- Validate trust-boundary values in backend execution even when widgets or
  prompt validation constrain them.
- Preserve tensor batch dimensions: `IMAGE` is normally `[B,H,W,C]`, `MASK` is
  `[B,H,W]` with `[H,W]` accepted where documented, and `LATENT` is a dictionary
  whose extra keys must survive transformations.
- Do not confuse tensor batches with ComfyUI scheduling lists. Test each
  separately when a node supports it.
- Operate on the input/model device and supported dtype. Avoid unconditional
  CUDA moves, unnecessary copies, global cache clearing, and global Torch state.
- Pure deterministic nodes need no cache hook. Represent external state as an
  input or fingerprint it; use explicit seeds for randomness.
- Keep graph-visible behavior in declared inputs. Request hidden context only
  when the node actually uses it.

## Security and Isolation

- No `eval`, `exec`, obfuscation, runtime `pip`, or subprocess package
  installation.
- Never monkey-patch ComfyUI, Torch, frontend globals, API clients, or another
  custom-node pack.
- Resolve filesystem paths and prove containment within an allowed root at the
  point of access. Reject traversal and symlink escape.
- Validate external types, ranks, sizes, identifiers, URLs, decoded content,
  archive members, and output destinations with actionable errors.
- Bound network timeouts, retries, response sizes, concurrency, temporary
  storage, and image pixel counts. Document every network call and file write.
- Assume custom `PromptServer` routes have no general authentication gate.
  Namespace routes under `/lfgg/v1/`; use non-GET methods for mutation and add
  explicit authorization for sensitive operations.
- Never commit, log, return, or package credentials, private data, caches, or
  local absolute paths.
- Before copying reference code, verify its license and preserve required
  notices. Prefer reimplementation when compatibility is unclear.

## Packaging and Dependencies

- Start with only `__init__.py`, focused node modules, `pyproject.toml`,
  `README.md`, `LICENSE`, and tests. Add `web/`, routes, build tooling,
  `example_workflows/`, `subgraphs/`, or `locales/` only when used.
- Keep runtime dependencies static in `[project].dependencies`; keep development
  tools in an optional extra. Do not add a ceremonial `requirements.txt`.
- Declare direct runtime dependencies with the least restrictive tested bounds.
  Do not pin ComfyUI's Torch/core stack without a proven incompatibility.
- Use documented `WEB_DIRECTORY` for browser assets. Do not copy files into
  ComfyUI core directories or rely on undocumented frontend mutation.
- Treat published Registry versions and package names as immutable. Publishing
  requires an explicitly approved tag or release workflow and a protected
  `REGISTRY_ACCESS_TOKEN`.

## Testing and Verification

- Leave one focused runnable test for every non-trivial branch, parser, path
  boundary, or behavior change.
- Test pure helpers independently from ComfyUI, then test node schema,
  registration, tuple/output order, validation, errors, and cache behavior.
- Use real tensors for dtype/device/shape behavior. Relevant image nodes cover
  `B=1` and `B>1`; mask nodes cover `[H,W]` and `[B,H,W]`.
- Before release, test the packed archive in clean ComfyUI at the declared
  minimum and current supported versions, check `/object_info`, and execute a
  minimal workflow per node family.
- Add browser E2E tests only when browser behavior exists.
- No install, lint, test, build, pack, or publish command is canonical yet.
  Read checked-in project metadata once it exists; do not infer commands from
  the stack or copy documentation examples as repository policy.

## Documentation and Review

- Keep `AGENTS.md` limited to durable agent rules. Put requirements and plans in
  their own documents rather than expanding this file.
- Once nodes exist, keep the README node catalog, compatibility matrix,
  external effects, examples, and migration notes aligned with registration.
- Update this file when canonical commands, compatibility policy, architecture
  boundaries, or recurring guardrails change—not for one-off task details.
- Before finishing work, report changed files, checks run, known limitations,
  and deferred work. Do not claim unrun checks passed.

## Assumptions to Confirm

These decisions are intentionally unresolved and must be confirmed before use:

- first public nodes and their acceptance criteria;
- V1 baseline versus a V3-only requirement;
- minimum/current ComfyUI, frontend, Python, OS, and accelerator matrix;
- package name, publisher ID, license, repository URLs, and release process;
- canonical development, lint, test, integration, pack, and CI commands.
