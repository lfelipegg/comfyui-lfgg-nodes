# Next Steps

## Goal and scope

Add `LFGG Prompt Assistant` (`LFGG_PromptAssistant`) to the `lfgg-nodes`
ComfyUI pack at `/home/mothmanex/projects/personal/comfyui-lfgg-nodes`: a node
that asks a user-run `llama-server` to write a generation prompt from a master
prompt, attached skills, a request, and optional images, and that shares the
GPU with diffusion/video models through a VRAM policy. The design is settled
and the implementation is complete and locally verified; ComfyUI workflow
qualification and release prep remain.

## Completed in this chat

- Implemented `LFGG_PromptAssistant` end to end in `lfgg_nodes/prompt_assistant.py`:
  config validation, skill discovery/selection/attachment, image encoding,
  message assembly, the bounded `aiohttp` client, VRAM policy helpers, the
  async node, and the two `GET /lfgg/v1/prompt-assistant/{models,skills}`
  routes. Registered in root `__init__.py` as `LFGG Prompt Assistant` under
  `LFGG/text`.
- Relaxed the shared loader in `lfgg_nodes/prompt_composer.py`
  (`load_config_document`) to accept optional `prompt_composer` and
  `prompt_assistant` sections; `config.example.json` ships both with the seven
  split scenario-maker skills.
- Frontend `web/prompt_assistant.{js,mjs}`: skills picker editing the
  `skills` text, model refresh preserving a missing saved id, read-only result
  report restored from node outputs, connected-input locks, disclosure in
  `node.properties.lfgg_editor_expanded`. Help page
  `web/docs/LFGG_PromptAssistant/en.md`.
- Tests: `tests/unit/test_prompt_assistant_{config,skills,messages,client,vram,node}.py`
  with a fake `aiohttp` llama-server (`tests/unit/prompt_assistant_fakes.py`),
  `tests/frontend/prompt_assistant.test.mjs`; contract, archive, and composer
  tests updated. `aiohttp` added to the `dev` extras for CI.
- README: nodes table row, behavior section, file/network behavior, develop
  list, tested build note.
- Integration against the user's pinned llama.cpp b10970 (`bfdc32183`,
  `/mnt/c/llama.cpp`, router mode, Qwen 3.8 27B IQ2_M with `--mmproj`):
  text-only streamed run, two-image vision run, and `share` unload that
  returned ~16.6 GiB VRAM within 1.5 s. This surfaced and fixed a real bug:
  router-proxied `/props?model=` bodies are chunked, so bodies are now read to
  EOF under the cap.

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

- From `.venv`: `python -m ruff check .` passed; `python -m pytest -q tests/unit`
  gave 545 passed, 2 skipped; `node --test tests/frontend/*.test.mjs` 147
  passed; `comfy node validate` passed; `comfy node pack` then
  `python -m pytest -q tests/package --archive node.zip` passed (new files are
  staged with `git add` because `comfy node pack` only includes tracked files).
- Not run: the ComfyUI-in-the-loop workflow runs (router and single-model
  mode, proof that the following sampler reloads its model), the
  `tests/integration` suite, and manual frontend checks in light/dark palettes
  and the Nodes 2.0 renderer. Single-model mode was not exercised because the
  user's server was running in router mode and the pack must not restart it.
- State: branch `chore/claude-guidance`, implementation uncommitted; new files
  staged, modified files unstaged. `.vscode/settings.json` still carries the
  unrelated local change; leave it alone.

## Next steps

1. Review the diff and commit the Prompt Assistant implementation (do not
   touch `.vscode/settings.json`).
2. Run one ComfyUI workflow per mode against the pinned llama-server: router
   mode `share` run followed by a sampler (confirm the sampler reloads its
   model and VRAM returns to baseline), then single-model mode (expect the
   logged warning, no unload). Record results in `README.md`.
3. Manually check the picker, model refresh, and report in light and dark
   palettes and in the Nodes 2.0 renderer; confirm serialize/reload keeps the
   `skills` text and the disclosure state.
4. Bump `pyproject.toml` version and add a `release/<version>-schema.json`
   manifest entry before the next release; `LFGG_PromptAssistant` is excluded
   from the frozen 1.5.0 manifest check in `tests/unit/test_contract.py`.

Optional, not authorized: per-skill default reference sets in config, non-`.md`
attachments, a separate VRAM-release node.

## Prompt for a new chat

```text
Project: lfgg-nodes ComfyUI pack at /home/mothmanex/projects/personal/comfyui-lfgg-nodes.
Goal: finish qualifying the implemented LFGG Prompt Assistant node (LFGG_PromptAssistant).

Read AGENTS.md, DESIGN.md, docs/next-steps.md, and
docs/plans/2026-10-29-prompt-assistant-design.md first. The implementation,
tests, frontend, README, and config.example.json are done and pass the local
gates (see docs/next-steps.md "Verification and current state"). Use
.venv/bin/python for tests and lint; .vscode/settings.json carries an
unrelated local change, do not touch it.

Remaining: review and commit the work; run the ComfyUI workflow integration
checks in router and single-model mode against the user's llama-server at
http://127.0.0.1:8080 (llama.cpp b10970, /mnt/c/llama.cpp, started by the
user, never by the pack); manual frontend checks in light/dark and Nodes 2.0;
then release prep (version bump, schema manifest). Never claim an unrun check
passed.
```
