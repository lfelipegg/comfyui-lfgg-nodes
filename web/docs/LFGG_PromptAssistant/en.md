# LFGG Prompt Assistant

Asks a `llama-server` that you start yourself to write one generation prompt.
The node sends one stateless chat turn over HTTP: the `master_prompt` plus the
attached skills become the system message; the images and `request` become the
user message. The reply is returned as `prompt` and shown in the read-only
**Generated prompt** report. The node never installs, starts, or stops the
server.

Configure the server and skills in
`<ComfyUI user directory>/lfgg_nodes/config.json` under `prompt_assistant`:
`server.base_url` (http or https, host and port only), optional
`server.api_key`, `server.read_timeout_seconds` (10 to 3600, default 300),
`skills_roots` (absolute paths or `~` paths for Linux and Windows; missing roots
are skipped), and the `skills` allowlist of skill folder names.

**Skills** are directories one level below a root that contain `SKILL.md`. The
`skills` text lists one entry per line: a skill name attaches its `SKILL.md`;
`skill-name/references/file.md` also attaches that reference. The picker below
the text edits it: check a skill, open its references, or choose **All
references**. Hand-written lines are kept. Attachments are limited to 256 KiB in
total and 512 KiB per file; the node fails rather than truncates. Files under
`evals`, `docs`, `tests`, `scripts`, `wildcards`, and hidden directories are
never attached.

**Model** stores the server's model id. **Refresh models** lists the models the
server knows; a saved id that is no longer listed is kept and marked. Keep
`server default` to let the server pick.

**vram_policy** `share` (default) moves ComfyUI's loaded models to RAM before
the call and, when the server runs in router mode, unloads the language model
afterwards so the next sampler gets the GPU back. In single-model mode the node
only logs a warning. `keep_llm_loaded` skips the unload; `off` does nothing.

Up to four optional images may be connected; every batch frame counts, eight
images at most. Frames are downscaled to a 1024 px long side and sent as JPEG,
or PNG when they carry alpha. The server must report vision support (start it
with `--mmproj`).

The reply streams into ComfyUI's progress text. Empty replies, missing skills,
oversized attachments, unreachable servers, and timeouts fail with an
actionable error; the node never returns a blank prompt.
