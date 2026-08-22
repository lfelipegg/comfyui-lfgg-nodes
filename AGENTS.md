# Repository Agent Instructions

## Purpose and Current State

This repository contains the implemented LFGG Nodes successor pack for ComfyUI.
`README.md` is the source of truth for current nodes, behavior, and qualification
requirements. `pyproject.toml` is the source of truth for package metadata,
dependencies, and compatibility floors.

- Do not treat `reference/custom-nodes/` as project source. It is ignored,
  locally modified reference material with mixed licenses and dated patterns.

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

## Subagent Routing

- Do not delegate small, sequential tasks; the primary agent completes them
  directly.
- For standard or critical work, follow `agents/orchestrator.md`.
- Use one writer by default.
- Treat `.codex/agents/` as the source of truth for project agent profiles.

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

### Frontend graph invariants

- Give every pack-owned virtual node a minimal V1 backend definition plus root
  class/display mappings. Attach its behavior with `beforeRegisterNodeDef`; do
  not rely only on `LiteGraph.registerNodeType`, which makes node search assign
  the raw ID, `__frontend_only__` category, and frontend-only package source.
- Keep the backend `CATEGORY`, display mapping, frontend title, and persisted
  title migration aligned so node search and restored workflows show the
  user-facing `LFGG ` label rather than the serialized `LFGG_` ID.
- Treat LiteGraph restore callbacks as state replay, not proof of a connection:
  `onConnectionsChange` can report `isConnected=true` with a null link for a
  disconnected restored slot. Grow or activate dynamic slots only after proving
  that the link or slot connection exists; never grow the array being restored
  from the boolean alone.
- For dynamic-slot nodes, test new-node state and a serialize/configure reload.
  Assert package/display/category metadata, title migration, links and labels,
  and that disconnected channel counts remain unchanged.

## Design system enforcement

- Read `DESIGN.md` before creating or changing a registered node or its frontend UI.
- Treat it as the source of truth for node interaction, theme tokens, layout,
  accessibility, progressive enhancement, and workflow-state presentation.
- Reuse native ComfyUI controls and existing LFGG patterns before adding custom
  styling; update `DESIGN.md` with any new shared token or interaction pattern.
- When `DESIGN.md` changes, run its available design-md structural validator.

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
- Canonical local gates are `python -m ruff check .`,
  `python -m pytest -q tests/unit`, `comfy node validate`, `comfy node pack`,
  and the explicit package/integration pytest commands in `README.md`.
  Publication remains tag-gated and manually approved.
- Before release, test the packed archive at the minimum and current supported
  ComfyUI versions, inspect `/object_info`, and run one workflow per node family.
- Keep `AGENTS.md` durable and short. Put requirements and plans elsewhere;
  update it only for reusable commands, boundaries, or recurring guardrails.
- After meaningful Markdown changes, ingest the context index.
- Finish with changed files, checks run, limitations, and deferred work. Never
  claim an unrun check passed.

## Agent skills

### Issue tracker

GitHub Issues; external PRs are not a triage surface. See
`docs/agents/issue-tracker.md`.

### Triage labels

Use the default five-role vocabulary. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root `CONTEXT.md` and `docs/adr/`. See
`docs/agents/domain.md`.

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
