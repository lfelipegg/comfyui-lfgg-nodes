# Next Steps

## Goal and scope

Add `LFGG Prompt Assistant` (`LFGG_PromptAssistant`) to the `lfgg-nodes`
ComfyUI pack at `/home/mothmanex/projects/personal/comfyui-lfgg-nodes`: a node
that asks a user-run `llama-server` to write a generation prompt from a master
prompt, attached skills, a request, and optional images, and that shares the
GPU with diffusion/video models through a VRAM policy. The design is settled;
implementation has not started.

## Completed in this chat

- Design interview (24 questions, all answered) and primary-source research on
  the llama.cpp server API and ComfyUI model management.
- Accepted design: `docs/plans/2026-10-29-prompt-assistant-design.md`.
- Domain terms added to `CONTEXT.md` under "Prompt assistance".
- ADR: `docs/adr/0006-front-llama-server-over-http-and-release-vram-via-router-unload.md`.
- Context index re-ingested after the Markdown changes.

No node code, tests, routes, frontend, README, or `config.example.json`
changes exist yet.

## Decisions and constraints

- HTTP to a user-run `llama-server` only. No `llama-cpp-python`, no spawning or
  stopping processes, no runtime installs. See ADR 0006.
- Default `vram_policy` is `share`: call `comfy.model_management.unload_all_models()`
  and `soft_empty_cache()` before the request; after the reply call
  `POST /models/unload` and poll `GET /models` (30 s bound) in router mode;
  in single-model mode only log a warning. `keep_llm_loaded` and `off` exist.
  Guard model-management calls so signature changes degrade to warnings.
- Skills are configured in `<ComfyUI user dir>/lfgg_nodes/config.json` under a
  new `prompt_assistant` section: `server` (`base_url`, `api_key`,
  `read_timeout_seconds`), `skills_roots`, and the `skills` allowlist. The
  shipped example must default the allowlist to the seven split skills:
  `scenario-maker-sdxl`, `scenario-maker-krea-2`, `scenario-maker-illustrious`,
  `scenario-maker-noobai`, `scenario-maker-pony`, `scenario-maker-wan`,
  `scenario-maker-minimax-h3`. The same workflow must run on Linux and Windows
  with per-machine configs.
- The shared config loader in `lfgg_nodes/prompt_composer.py` currently rejects
  any section other than `prompt_composer`. Relax it to accept both optional
  sections before touching `config.example.json`; the README tells users to copy
  that file verbatim, so changing it first would break the Prompt Composer.
- Selection persists in a `skills` multiline STRING, one entry per line: a skill
  name or `skill-name/relative/file.md`. Attach `SKILL.md` always; attach
  reference `.md` files only when selected; exclude `evals`, `docs`, `tests`,
  `scripts`, `wildcards`, hidden dirs; 256 KiB total cap, error not truncation.
- Up to four optional IMAGE inputs, eight images total, long side 1024, JPEG 92
  or PNG with alpha, captions `Image N of M`, vision checked via `GET /props`.
- Streamed `POST /v1/chat/completions`, deltas forwarded with
  `send_progress_text`, result returned as `prompt` plus a `ui.text` preview;
  `reasoning_content` discarded. Async node function; interruption closes the
  connection.
- Two read-only GET routes under `/lfgg/v1/prompt-assistant/` (`models`,
  `skills`). Bounds: connect 5 s, read from config (default 300 s), no retries,
  1 MiB streamed body cap, http/https only, no redirects.
- Work within `AGENTS.md`, `DESIGN.md`, and the pack invariants (V1 mappings,
  `LFGG_` IDs, actionable errors, no blank outputs, no monkey-patching).
- Research facts are dated 2026-10-29/30 in the plan header; recheck llama.cpp
  flags and endpoints against the pinned build before implementing.

## Verification and current state

- Observed in this chat from `.venv`: `python -m pytest -q tests/unit` gave
  445 passed, 2 skipped; `python -m ruff check .` passed. No Python changed, so
  this only confirms no regression from the Markdown edits.
- State at handoff: branch `chore/claude-guidance`, last commit `b433280`
  before the plan commit requested in this chat. `.vscode/settings.json` has an
  unrelated pre-existing modification; leave it alone.
- The system `python3` has no pytest; use `.venv/bin/python`.
- No llama-server or ComfyUI runtime was exercised; integration checks in the
  plan's "Verification and acceptance" section are not run.

## Next steps

Authorized: implement the accepted plan. Follow the plan's test list and the
`AGENTS.md` gates (`python -m ruff check .`, `python -m pytest -q tests/unit`,
`comfy node validate`, `comfy node pack`).

1. Shared config loader: accept optional `prompt_composer` and
   `prompt_assistant` sections, validate the new section per the plan's
   "Configuration" section, then update `config.example.json` and the README
   config instructions. Tests for both sections, unknown/duplicate keys, URL
   forms, timeout bounds, `~` expansion on both OS path styles.
2. Skill discovery, selection parsing, and attachment assembly with the
   containment, allowlist, exclusion, and size rules. Tests including the
   `evals/` snapshot case.
3. Message assembly and image encoding with real tensors (1/3/4 channels,
   batches across slots, eight-image cap, input untouched).
4. Async server client against a local fake server: health, errors, streaming,
   body cap, reasoning-only reply, API key header, interruption, router versus
   single-model detection, unload polling.
5. VRAM policy sequencing against a stubbed `comfy.model_management`,
   including the guarded failure path.
6. Node class, root registration in `__init__.py` (`LFGG_PromptAssistant`,
   display `LFGG Prompt Assistant`, category `LFGG/text`), the two routes.
7. Frontend extension per `DESIGN.md`: skills picker editing the `skills`
   text, model refresh, read-only result report; test new-node state and
   serialize/configure reload.
8. README section (nodes table, behavior, file and network behavior), then
   integration runs against a real llama-server in router and single-model
   modes as listed in the plan; record the tested llama.cpp build.

Optional, not authorized: per-skill default reference sets in config, non-`.md`
attachments, a separate VRAM-release node.

## Prompt for a new chat

```text
Project: lfgg-nodes ComfyUI pack at /home/mothmanex/projects/personal/comfyui-lfgg-nodes.
Goal: implement the accepted LFGG Prompt Assistant node (LFGG_PromptAssistant).

Read AGENTS.md, DESIGN.md, docs/next-steps.md, and the accepted design
docs/plans/2026-10-29-prompt-assistant-design.md before changing anything.
CONTEXT.md ("Prompt assistance") holds the canonical terms; docs/adr/0006 records
why we front a user-run llama-server over HTTP and release VRAM via router-mode
unload. Use the user-level project-context skill for targeted doc lookups.

State: design is complete and committed; no implementation exists. Branch at
handoff was chore/claude-guidance. .vscode/settings.json carries an unrelated
local change; do not touch it. Use .venv/bin/python for tests and lint.

Non-negotiables from the design: HTTP only to a user-configured llama-server,
no llama-cpp-python, no process management, no runtime installs; V1 node under
LFGG/text; config in <ComfyUI user dir>/lfgg_nodes/config.json with a
prompt_assistant section whose skills allowlist defaults to the seven split
scenario-maker skills listed in the plan; skills persisted by name in a
multiline STRING; 256 KiB attached-context cap with errors not truncation;
four optional IMAGE inputs and eight images max; streamed chat completion with
progress text; default vram_policy "share" using comfy.model_management
unload before the call and POST /models/unload after it, guarded.

Start with step 1 in docs/next-steps.md: relax the shared config loader in
lfgg_nodes/prompt_composer.py to accept both optional sections and validate the
new one, with unit tests, and only then update config.example.json and the
README config instructions. Then continue in order through steps 2 to 8. Check
current file state before editing, preserve unrelated work, and do not ask for
approval again for this agreed work. Recheck llama-server flags and endpoints
against the user's pinned build before step 4.

Acceptance per step: focused unit tests per the plan's "Verification and
acceptance" section, then .venv/bin/python -m ruff check . and
.venv/bin/python -m pytest -q tests/unit passing; comfy node validate and
comfy node pack before any release work. Finish with changed files, checks run,
limitations, and deferred work. Never claim an unrun check passed.
```
