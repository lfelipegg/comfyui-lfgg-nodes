# Repository Agent Instructions

## Purpose and Current State

This repository is the future `comfyui-lfgg-nodes` custom-node pack. It
currently contains research only; the first nodes and compatibility target have
not been selected.

- Do not treat `reference/custom-nodes/` as project source. It is ignored,
  locally modified reference material with mixed licenses and dated patterns.
- Before scaffolding or implementing nodes, identify the requested node set,
  minimum supported ComfyUI/frontend versions, and registration generation.

## Context and Source Order

Use the project-context workflow below before broad documentation scans. Search
first, then read only the relevant chunks from:

- `docs/comfyui-info/README.md` for the research summary and routing;
- `docs/comfyui-info/custom-node-api.md` for node/runtime behavior;
- `docs/comfyui-info/distribution-and-quality.md` for packaging and quality;
- `docs/comfyui-info/reference-audit.md` only before using local references.

The research snapshot is dated 2026-07-26. Recheck moving API and Registry facts
before implementation or release. Prefer current/pinned ComfyUI source, current
official docs, official examples, then local reference nodes.

## Pack Invariants

- Use the standard library, ComfyUI helpers, project code, and installed
  dependencies before adding code or dependencies.
- Default to V1 `NODE_CLASS_MAPPINGS`; use V3 only for a demonstrated need with
  a tested ComfyUI floor. Never expose both registration generations.
- Prefix every registered node name/ID (`NODE_CLASS_MAPPINGS` key or V3
  `node_id`) with `LFGG_`, and every user-facing display name with `LFGG `.
  Prefix custom wire types with `LFGG_`; workflow schemas are persisted API.
- Keep root `__init__.py` registration-only and reject duplicate node IDs.
- Keep transformations ComfyUI-independent; adapt schemas, tensors, lists, and
  UI envelopes at boundaries. See `custom-node-api.md` for exact contracts.
- Keep imports fast and side-effect-free. Add shared helpers only after two
  callers and frontend/routes/hidden inputs/graph features only when required.
- Preserve tensor batches, latent extra keys, input device, and supported dtype.
  Do not confuse batches with ComfyUI scheduling lists.
- Validate trust-boundary inputs during execution. Use pack-prefixed logging and
  actionable errors; do not suppress failures with blank outputs.

## Security and Distribution

- No `eval`, `exec`, obfuscation, runtime `pip`, or subprocess package
  installation.
- Never monkey-patch ComfyUI, Torch, frontend globals, API clients, or another
  custom-node pack.
- Resolve filesystem paths and prove containment within an allowed root at the
  point of access. Reject traversal and symlink escape.
- Validate external types, sizes, identifiers, URLs, decoded content, archive
  members, and destinations.
- Bound network timeouts, retries, response sizes, concurrency, temporary
  storage, and image pixel counts. Document every network call and file write.
- Assume custom `PromptServer` routes have no general authentication gate.
  Namespace routes under `/lfgg/v1/`; use non-GET methods for mutation and add
  explicit authorization for sensitive operations.
- Never commit, log, return, index, or package credentials, private data, caches,
  or local absolute paths.
- Verify reference licenses before reuse; prefer reimplementation when unclear.
- Declare runtime dependencies in `pyproject.toml`; do not install at runtime or
  add a ceremonial `requirements.txt`.
- Use documented `WEB_DIRECTORY`; never copy into or mutate ComfyUI core.
- Publishing requires an explicitly approved release and protected Registry
  token. Published names and versions are immutable.

## Verification and Maintenance

- Leave one focused runnable test for each non-trivial branch, parser, path
  boundary, or behavior change. Use real tensors for shape/device behavior.
- No install, lint, test, build, pack, or publish command is canonical yet.
  Read checked-in metadata; never infer commands from the stack or research docs.
- Before release, test the packed archive at the minimum and current supported
  ComfyUI versions, inspect `/object_info`, and run one workflow per node family.
- Keep `AGENTS.md` durable and short. Put requirements and plans elsewhere;
  update it only for reusable commands, boundaries, or recurring guardrails.
- After meaningful Markdown changes, ingest the context index.
- Finish with changed files, checks run, limitations, and deferred work. Never
  claim an unrun check passed.

## Assumptions to Confirm

These decisions are intentionally unresolved and must be confirmed before use:

- first public nodes and their acceptance criteria;
- compatibility floor and whether a demonstrated V3-only need overrides V1;
- minimum/current ComfyUI, frontend, Python, OS, and accelerator matrix;
- package name, publisher ID, license, repository URLs, and release process;
- canonical development, lint, test, integration, pack, and CI commands.

## Project Context Retrieval

<!-- project-context:start -->
This repo uses token-efficient project context retrieval.

Use the user-level `$project-context` Skill before broad documentation scans or when a task depends on architecture, prior decisions, task history, database conventions, deployment behavior, auth/security/billing behavior, or non-obvious project behavior.

Do not use it for trivial single-file edits.

Preferred commands:

- `python3 .codex-context/ctx.py status`
- `python3 .codex-context/ctx.py search "<query>" --limit 5`
- `python3 .codex-context/ctx.py read <id> --max-chars 4000`
- `python3 .codex-context/ctx.py related <id> --limit 5`
- `python3 .codex-context/ctx.py ingest` after meaningful Markdown doc changes

Rules:

- Search first; read only directly relevant IDs.
- Never dump whole SQLite tables, full indexes, or every Markdown file.
- Treat Markdown files as the source of truth and SQLite as the retrieval index.
- If the index is missing or stale, rebuild it or fall back to targeted repo inspection.
<!-- project-context:end -->
