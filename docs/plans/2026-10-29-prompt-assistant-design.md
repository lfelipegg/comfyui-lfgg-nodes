# Prompt Assistant Design

Purpose: Define the accepted contract, resource policy, and interaction model
for a node that asks a user-run `llama-server` to write a generation prompt
from a master prompt, attached skills, a request, and optional images.
Read when: implementing, reviewing, or qualifying `LFGG Prompt Assistant`.
Do not read for: in-process `llama-cpp-python` inference, spawning or
installing llama.cpp, multi-turn chat, or tool calling.
Source of truth: the 2026-10-29 design interview, the llama.cpp
`tools/server/README.md` and `server-models.cpp` on master as of 2026-10-29,
ComfyUI `comfy/model_management.py`, `execution.py`, and `server.py` on
master (tag v0.43.1) as of 2026-10-30, and the `lfgg-skills` repository
layout inspected on 2026-10-29.
Last reviewed: 2026-10-29

## Summary

- Add the V1 node `LFGG_PromptAssistant`, displayed as `LFGG Prompt Assistant`
  under `LFGG/text`.
- Send one stateless chat turn to an OpenAI-compatible `llama-server` that the
  user starts and configures. The node never installs, spawns, or stops it.
- Build the system message from a reusable master prompt plus the `SKILL.md`
  bodies and user-selected reference files of allowlisted skills.
- Build the user message from up to eight images across four optional image
  inputs followed by the per-run request.
- Stream the reply into the node, return it as one `prompt` string, and keep a
  read-only result preview.
- Under the default `share` VRAM policy, move ComfyUI's loaded models to RAM
  before the call and unload the LLM from `llama-server` after it, so the
  diffusion or video model gets the GPU back.
- Keep the server URL, API key, skill roots, and skill allowlist in the per-user
  `config.json`; workflows persist only skill names and widget values.

## Public contract

Register exactly one new V1 node:

| Field | Value |
|---|---|
| Node ID | `LFGG_PromptAssistant` |
| Display name | `LFGG Prompt Assistant` |
| Category | `LFGG/text` |
| Outputs | `STRING` named `prompt` |
| Output node | No; the result preview is a `ui.text` envelope |

Persisted inputs, in order:

| Input | Type | Default | Notes |
|---|---|---|---|
| `master_prompt` | multiline `STRING` | see below | Reusable standing instructions. Connectable. |
| `request` | multiline `STRING` | empty | What to write now. Connectable. May be empty only when at least one image is connected. |
| `skills` | multiline `STRING` | empty | One entry per line: a skill name or `skill-name/relative/file.md`. Edited by the picker; also hand-editable and connectable. |
| `model` | `COMBO` | `server default` | Populated from the server on refresh. Stores the server's model id. |
| `vram_policy` | `COMBO` | `share` | `share`, `keep_llm_loaded`, `off`. |
| `seed` | `INT` 0 to 2^64-1 | `0` | Native control-after-generate. Sent as the sampler seed. |
| `temperature` | `FLOAT` 0 to 2, step 0.05 | `0.7` | |
| `max_tokens` | `INT` 1 to 32768 | `1024` | Sent as `max_tokens`. |
| `image_1` to `image_4` | optional `IMAGE` | unconnected | Every batch frame of every connected input is sent, in slot order. |

Hidden input: `unique_id` for progress text.

Default master prompt:

```
You write prompts for image and video generation models. Follow the attached
skill exactly. Reply with the final prompt only, no explanation.
```

The master prompt, request, skills, model, policy, seed, temperature, and
token limit form the cache signature. Unchanged inputs return the cached
`prompt` without contacting the server. The node declares no `IS_CHANGED`.

## Configuration

Read `<ComfyUI user directory>/lfgg_nodes/config.json`, the file the Prompt
Composer already uses, and add a `prompt_assistant` section:

```json
{
  "prompt_composer": { "...": "unchanged" },
  "prompt_assistant": {
    "server": {
      "base_url": "http://127.0.0.1:8080",
      "api_key": "",
      "read_timeout_seconds": 300
    },
    "skills_roots": [
      "~/.agents/skills",
      "~/.agents/skills/lfgg-skills/skills",
      "C:/Users/<name>/.agents/skills"
    ],
    "skills": [
      "scenario-maker-sdxl",
      "scenario-maker-krea-2",
      "scenario-maker-illustrious",
      "scenario-maker-noobai",
      "scenario-maker-pony",
      "scenario-maker-wan",
      "scenario-maker-minimax-h3"
    ]
  }
}
```

Rules:

- The shared loader accepts both sections, each optional, and rejects unknown
  top-level keys and duplicate keys. Nodes read only their own section.
  Existing Prompt Composer behavior and errors are unchanged.
- `base_url` must be `http` or `https` with a host and optional port, no path,
  query, credentials, or fragment. `api_key` is optional and is sent as
  `Authorization: Bearer <key>`. It is never logged, returned, or persisted
  in workflows.
- `skills_roots` entries are absolute paths or start with `~`, on either OS.
  Each root must resolve to an existing directory. Missing roots are skipped
  with one logged warning per execution, not an error, so one config can serve
  two machines.
- `skills` is the allowlist of skill folder names the picker may show and the
  backend may attach. Omitting the key allows every discovered skill. The
  shipped `config.example.json` lists the seven split scenario-maker skills.
- `read_timeout_seconds` defaults to 300 and is bounded to 10 to 3600.
- The file is limited to 64 KiB, like today.

## Skill discovery and attachment

A skill is a directory, one level below a configured root, that contains
`SKILL.md`. Discovery follows symlinked skill directories, then resolves every
path and proves it lies inside the resolved root. Entries that escape, or
whose names are not in the allowlist, are ignored. Names are the directory
names. Duplicate names across roots resolve to the first root in config order
and log a warning naming both paths.

For each skill, the attachable files are every `*.md` beneath the skill
directory except `SKILL.md` itself, hidden directories, and the directories
`evals`, `docs`, `tests`, `scripts`, and `wildcards`. The `evals` exclusion
matters: `scenario-maker` carries two dozen snapshot copies of `SKILL.md` under
`evals/`, and none of them is a skill.

Selection is persisted in the `skills` widget, one entry per line, in order:

- `scenario-maker-illustrious` attaches that skill's `SKILL.md` and its linked
  references (amended 2026-11-02, ADR 0008): every attachable file whose
  relative path appears in `SKILL.md`, or in an already linked file relative to
  that file or to the skill, followed transitively in first-mention order.
  Mentions that match no attachable file are ignored.
- `scenario-maker-illustrious/references/models/illustrious.md` attaches one
  reference file and implies the skill's `SKILL.md` even if the bare name line
  is absent.
- Entries use `/` separators. Blank lines are ignored. Leading and trailing
  whitespace is trimmed.

Validation at execution raises an actionable error, naming the entry and the
roots searched, for: unknown skill, skill not allowlisted, file not found,
file outside the skill, non-`.md` file, or an excluded directory. Nothing is
silently dropped.

Attached text is bounded: `SKILL.md` and every reference file is read as
UTF-8, individually capped at 512 KiB, and the total attached bytes across all
selected files must not exceed 256 KiB. Exceeding the total raises an error
that lists the largest attachments; the node never truncates.

The frontend picker lists allowlisted skills under each root, shows missing
allowlisted skills as unavailable with the roots searched, expands a skill to
its attachable files with linked references checked and locked, offers an
`all references` shortcut per skill for the unlinked rest, and shows
the running attached-size estimate. It edits the `skills` text; it owns no
other state. Without the frontend extension the text box remains usable.

## Message assembly

One request to `POST /v1/chat/completions`:

- `system`: the master prompt, then (when anything is attached) a note headed
  `# Attached skill files` saying the model cannot open files or run scripts,
  that a skill's "read this file" means the matching attached section, and
  naming the selected skills' attachable files that were left out; then for
  each selected skill a block headed `# Skill: <name>` containing the
  `SKILL.md` body with YAML frontmatter removed, then its linked references,
  then other selected files, each headed `## <name>/<relative path>`.
  An empty master prompt with no skills omits the system message.
- `user`: an ordered content array. For each image, a text part
  `Image N of M` followed by an `image_url` part carrying a `data:` URI; then
  one text part with the request. An empty request with images sends only the
  images and captions.
- `model`: the selected model id, omitted for `server default`.
- `stream: true`, `seed`, `temperature`, `max_tokens`.

Only the reply's `content` is used. Any `reasoning_content` is discarded. An
empty `content` after a complete stream raises an error that mentions
`max_tokens` and reasoning models. The returned `prompt` is the content with
leading and trailing whitespace trimmed.

## Images

Each connected image input is a `[B,H,W,C]` float tensor with 1, 3, or 4
channels. Every frame counts as one image; frames are taken in slot order,
then batch order. More than eight images total raises an error before any
encoding. Each frame is converted on CPU, downscaled with Lanczos so its long
side is at most 1024 px, and encoded as JPEG quality 92, or PNG when the
tensor has an alpha channel. The input tensor is never mutated or moved. Per
frame the source pixel count is bounded at 268,435,456 like the resize node.

Before sending images the node reads `GET /props` and raises an error if
`modalities.vision` is false or absent, naming the `--mmproj` flag.

## Server interaction and bounds

Endpoints used, all on the configured `base_url`:

| Call | When | Purpose |
|---|---|---|
| `GET /health` | start of execution | Fail fast with the URL when unreachable or not ready. |
| `GET /models` | refresh route; `share` policy | Router-mode model list and status. A 404 means single-model mode. |
| `GET /v1/models` | refresh route in single-model mode | Model id list. |
| `GET /props` | when images are attached | Vision capability. |
| `POST /v1/chat/completions` | every uncached execution | The generation, streamed. |
| `POST /models/unload` | `share` policy, router mode | Release the LLM after the reply. |

Bounds: connect timeout 5 s; read timeout from config; one attempt, no
retries; streamed body capped at 1 MiB plus 1 KiB per `max_tokens` (each
token arrives wrapped in its own SSE JSON chunk); non-streaming bodies capped at
256 KiB; `http` and `https` only; no redirects followed. Any failure raises
an actionable `LFGG Prompt Assistant` error that names the base URL and the
likely fix. No blank output is ever returned.

The node function is `async`. The HTTP work runs through ComfyUI's bundled
`aiohttp` client session created per execution and closed deterministically.
Between stream chunks the node calls ComfyUI's interruption check; an
interruption closes the connection, which makes `llama-server` cancel the
slot, and then re-raises.

Every text delta is forwarded with `PromptServer.send_progress_text` for the
node's `unique_id`, so the reply appears live. On completion the node returns
`{"ui": {"text": [prompt]}, "result": (prompt,)}`.

## VRAM policy

`vram_policy` controls two steps:

| Policy | Before the request | After the reply |
|---|---|---|
| `share` (default) | `comfy.model_management.unload_all_models()` then `soft_empty_cache()` | Router mode: `POST /models/unload` for the model used, then poll `GET /models` until its status is `unloaded`, bounded at 30 s. Single-model mode: log one warning recommending router mode or `--sleep-idle-seconds`; do not wait. |
| `keep_llm_loaded` | same as `share` | nothing |
| `off` | nothing | nothing |

Facts behind the policy:

- ComfyUI's `unload_all_models()` moves loaded weights to the offload device
  (CPU RAM) and keeps the `ModelPatcher` objects; the next sampler, VAE, or
  CLIP call reloads them automatically. Core uses the same path on OOM.
- llama.cpp cannot move a loaded model between GPU and CPU; changing
  `-ngl` at runtime was closed as not planned. Router-mode unload ends the
  model's child process, returning its VRAM to the OS. The GGUF file usually
  stays in the OS page cache, which is what makes the next load fast.
- The ComfyUI `POST /free` route applies only after the whole prompt
  finishes, so it is not used.

Before the pre-request step the node reads free system RAM and total VRAM
through `comfy.model_management` and logs a warning, without blocking, when
free RAM is smaller than the VRAM currently in use plus the selected model's
reported file size. Both model-management calls are guarded: an unexpected
signature or exception logs a warning with the exception text and continues,
because the module is an undocumented internal API.

Model loading is left to `llama-server` autoload on the chat request. The
node does not call `POST /models/load`.

## Routes

Two read-only routes, registered with `PromptServer`, used by the frontend:

- `GET /lfgg/v1/prompt-assistant/models`: returns `{ "mode": "router" |
  "single", "models": [{"id", "status"}] }` by proxying `GET /models` or
  `GET /v1/models`. Errors return `{ "error": "<message>" }` with status 502
  and never include the API key.
- `GET /lfgg/v1/prompt-assistant/skills`: returns the allowlisted skill tree
  from config: per skill its name, root, availability, and attachable files
  with byte sizes.

Both read `config.json` on every call, cache nothing, mutate nothing, and are
bounded by the same timeouts and size caps as execution.

## Frontend

A focused build-free extension bound only to `LFGG_PromptAssistant`, following
`DESIGN.md`:

- The skills picker sits below the `skills` text widget and edits it. Expand
  and collapse state is `node.properties.lfgg_editor_expanded`.
- The `model` combo gets a refresh action that calls the models route and
  preserves a saved id that is no longer listed, shown as missing.
- The live progress text uses ComfyUI's native progress-text preview. The
  final result is a read-only, selectable, monospace, bounded report widget
  that is not serialized, marked stale while a newer execution is pending, and
  restored from node outputs on workflow reload.
- Connected `master_prompt`, `request`, or `skills` inputs lock their editors
  visibly. Nothing is reset, clamped, or depends on frontend timing.

## Errors and logging

All errors derive from `PromptAssistantError` and are prefixed
`LFGG Prompt Assistant:`. Logging uses the `lfgg_nodes.prompt_assistant`
logger. Logs and errors never include the API key, attached skill text, image
bytes, or the reply.

## Security boundary

- Network: outbound calls go only to the configured `base_url`. No other host,
  no redirects, no downloads. The API key travels only in the request header.
- Filesystem: reads are limited to `config.json` and `.md` files proven to lie
  inside a configured skills root after resolving symlinks. No writes.
- Routes: both routes are `GET`, read-only, and expose no secrets. They can be
  called by any client that can reach ComfyUI; they reveal skill names and
  file sizes and the server's model ids, nothing else.
- Images: encoded in memory only; bounded by frame count and pixel count.
- No `eval`, `exec`, subprocess, runtime install, or monkey-patching. The
  model-management calls use public module functions only.

## Verification and acceptance

Unit tests with no ComfyUI or llama.cpp dependency:

- Config parsing: both sections, missing section, unknown keys, duplicate
  keys, invalid URL forms, bounds on timeout, `~` expansion on both OS path
  styles.
- Skill discovery: allowlist filtering, symlink following and escape
  rejection, duplicate names across roots, excluded directories, the
  `evals/` snapshot case, missing allowlisted skill reporting.
- Selection parsing: bare names, file entries implying the skill, blank
  lines, separators, every validation error.
- Attachment bounds: per-file and total caps, frontmatter stripping, block
  headers, ordering.
- Message assembly: system omitted when empty, image caption ordering, empty
  request with images, request without images.
- Images: real tensors for 1, 3, and 4 channels, batches across slots, the
  eight-image cap, downscale geometry, PNG-versus-JPEG choice, input tensor
  untouched.
- Server client against a local fake `aiohttp` server: health failure,
  non-2xx, timeout, stream parsing, body cap, reasoning-only reply, API key
  header, interruption closing the connection, router versus single-model
  detection, unload polling with the 30 s bound.
- VRAM policy: each policy's call sequence against a stubbed model-management
  module, including the guarded failure path.

Integration, documented in `README.md` and run before release: a real
`llama-server` in router mode and in single-model mode, one text-only run,
one two-image run on a vision model, and one `share` run that proves VRAM
returns to baseline after the node and that the following sampler reloads its
model. Record the tested llama.cpp build.

Gates: `python -m ruff check .`, `python -m pytest -q tests/unit`,
`comfy node validate`, `comfy node pack`, and the frontend checks listed in
`DESIGN.md` for a new custom UI.

## Non-goals and deferred work

- No in-process inference, no `llama-cpp-python`, no process management.
- No chat history, tool calling, JSON-schema output, or automatic
  positive/negative splitting; the master prompt and skill define the format.
- No `POST /models/load`, no waiting on `--sleep-idle-seconds`, no use of
  `--models-memory-margin` memory reports.
- No support claims for Ollama, LM Studio, or vLLM; they may work for plain
  generation only.
- Deferred: per-skill default reference sets in config, attaching non-`.md`
  reference data such as the Danbooru CSVs, and a second node that only
  releases VRAM.
