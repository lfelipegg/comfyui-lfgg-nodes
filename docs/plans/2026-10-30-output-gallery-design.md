# Output Gallery Design

Purpose: Define the accepted contract, bounds, and interaction model for a
node that shows the latest generated images, videos, and audio under the
ComfyUI output directory without re-running the workflow.
Read when: implementing, reviewing, or qualifying `LFGG Output Gallery`.
Do not read for: browsing arbitrary filesystem paths, deleting or moving
files, loading gallery items into the graph as tensors, or thumbnail
generation for video.
Source of truth: the 2026-10-30 design interview, ComfyUI `server.py` and
`execution.py` on master as of 2026-10-30, and the ComfyUI frontend
`packages/api-client/src/ComfyApi.ts` on main as of 2026-10-30.
Last reviewed: 2026-10-30

## Summary

- Add the V1 node `LFGG_OutputGallery`, displayed as `LFGG Output Gallery`
  under `LFGG/workflow`. It is a pure viewer: no outputs, no execution work.
- Scope every listing to a subfolder of the ComfyUI output root, so files and
  image previews are served by ComfyUI's native `/view` route and the pack
  serves no bytes of its own.
- List files through one new read-only route, `GET
  /lfgg/v1/output-gallery/list`, driven by the node's five persisted widgets:
  path, subfolders, media filter, sort, and limit.
- Refresh on a manual button and automatically after a queue run finishes.
  Never poll.
- Show a selected-item preview with native media controls, plus a lazy tile
  grid when expanded. Videos stay muted in tiles and loop in the preview.
- Keep v1 read-only: open, copy path, and load an embedded PNG workflow.

## Problem

After a video generation the only visible result is the last preview in the
saving node. Earlier videos, and everything saved by other workflows, are
reachable only by opening the output folder in the operating system. The
gallery brings the latest N results of a chosen output subfolder into the
graph and keeps them current as the queue runs.

## Public contract

Register exactly one new V1 node:

| Field | Value |
|---|---|
| Node ID | `LFGG_OutputGallery` |
| Display name | `LFGG Output Gallery` |
| Category | `LFGG/workflow` |
| Outputs | none |
| Output node | No. `OUTPUT_NODE` stays false; the node is never queued. |

Persisted inputs, in order:

| Input | Type | Default | Notes |
|---|---|---|---|
| `path` | `STRING` | empty | Subfolder relative to the output root. Empty means the output root itself. Free text; it may name a folder that does not exist yet. |
| `include_subfolders` | `BOOLEAN` | `true` | Recurse without a depth limit, bounded by the scan cap. |
| `media_filter` | `COMBO` | `all` | `all`, `images`, `videos`, `audio`, then one entry per extension: `png`, `jpg`, `webp`, `gif`, `mp4`, `webm`, `mov`, `mp3`, `wav`, `flac`, `ogg`. |
| `name_filter` | `STRING` | empty | Case-insensitive substring matched against the path relative to `path`, so it matches subfolder names as well as filenames. |
| `sort` | `COMBO` | `newest first` | `newest first`, `oldest first`, `name A to Z`, `name Z to A`. Time means file modification time. |
| `limit` | `INT` 1 to 200 | `24` | Items returned. One page, no pagination. |

The node declares a function that returns an empty tuple so the schema is
valid and `/object_info` lists it, but nothing connects to it and ComfyUI
never schedules it. The frontend extension owns all behavior. Without the
extension the node still loads, shows its widgets, and persists them.

The widget labels above are display labels; the stored combo values are the
literal strings shown, since workflow JSON is persisted API.

## Media kinds

| Kind | Extensions | Tile | Selected preview |
|---|---|---|---|
| image | `png jpg jpeg webp gif` | `<img>` from `/view` with `preview=webp;60` | `<img>` from `/view` at full quality |
| video | `mp4 webm mov` | muted `<video preload="metadata">` with a play/pause overlay | `<video controls loop>` |
| audio | `mp3 wav flac ogg` | labeled placeholder with filename and kind marker | `<audio controls>` |

`jpeg` is accepted on disk and reported as `jpg` in the filter. Extension
matching is case-insensitive. A video whose first frame the browser cannot
decode, for example an HEVC `.mov`, falls back to the audio-style placeholder
tile so the grid never shows a blank hole.

Fact behind the image tile: the native `/view` route's `preview` parameter
re-encodes the image as WebP or JPEG at the given quality but does not
resize it. Tiles therefore pay full pixel dimensions at reduced quality,
which is acceptable for a bounded page of at most 200 items and avoids any
server-side thumbnail cache. Server-side video thumbnails would need ffmpeg,
which the pack does not depend on, so video tiles rely on the browser's own
first-frame rendering.

## List route

`GET /lfgg/v1/output-gallery/list`

Query parameters mirror the widgets exactly: `path`, `include_subfolders`
(`true`/`false`), `media_filter`, `name_filter`, `sort`, `limit`. Unknown
parameters are ignored. Invalid values return status 400 with
`{ "error": "<message>" }`.

Response, status 200:

```json
{
  "root": "runs/wan22",
  "items": [
    {
      "filename": "wan22_20261030_143012_0001.mp4",
      "subfolder": "runs/wan22/2026-10-30",
      "kind": "video",
      "extension": "mp4",
      "size": 4193304,
      "mtime": 1793123412.51
    }
  ],
  "scanned": 1840,
  "truncated": false
}
```

- `filename` and `subfolder` are exactly the values the frontend passes to
  `/view?type=output&filename=...&subfolder=...`. `subfolder` is relative to
  the output root, not to `path`, and uses `/` separators on every OS.
- `scanned` is the number of directory entries visited. `truncated` is true
  when the scan cap stopped the walk before it finished, so the list may be
  missing files. The widget shows this state.
- `mtime` is seconds since the epoch as a float. `size` is bytes.

Server rules:

- Resolve the output root with `folder_paths.get_output_directory()` and
  `Path.resolve(strict=True)`, exactly as `LFGG Save Image Dynamic` does.
  Resolve `root / path` and prove it is inside the output root after
  resolving symlinks. Reject absolute paths, drive markers, `..`, and symlink
  escapes with status 400 and a message that names the output root.
- A `path` that does not exist returns status 404 with `{ "error": "folder
  not found under output: <path>" }`. The widget shows that message; it never
  substitutes the root.
- Walk with `os.scandir`, never following symlinked directories. Skip hidden
  entries and entries whose resolved path leaves the output root. Count every
  entry visited against a hard scan cap of 20,000; stop the walk and set
  `truncated` when the cap is reached.
- Filter by extension and `name_filter` before sorting. Sort the surviving
  entries, then slice to `limit`. Sorting happens on at most the scanned set,
  never on the whole disk.
- Each call stats only the files it returns plus the entries it filters, and
  reads no file content. It caches nothing and mutates nothing.
- The route is registered from the node module, like the Prompt Assistant
  routes, and only when `server.PromptServer` imports; the module stays
  importable without ComfyUI.

The route is `GET` because it is read-only. It is reachable by any client
that can reach ComfyUI and reveals output filenames, sizes, and modification
times, nothing else. It serves no bytes; only the native `/view` route does,
with its own containment checks.

## Frontend

A focused build-free extension named `lfgg.outputGallery`, bound only to
`LFGG_OutputGallery`, installed on `nodeCreated` and `loadedGraphNode`, and
following `DESIGN.md`:

**Layout.** One non-serializing DOM widget below the native widgets. It uses
the shared editor view and the strict-Boolean
`node.properties.lfgg_editor_expanded` disclosure. Compact, the default for a
new node, shows the selected preview, a caption, the item count with any
truncation notice, and the refresh button. Expanded adds the tile grid below.
Tiles are at least 96px wide and the grid reflows to the widget's allocated
width. The preview is capped at 180px compact and 360px expanded without
stretching media, matching the video cutter.

**Selection.** Clicking a tile selects it. The selected item is remembered on
the node instance for the session only, keyed by `subfolder/filename`, and is
never serialized. After a refresh the selection is kept if the item is still
listed; otherwise it clears.

**Playback.** Tiles stay muted; the overlay button toggles play and pause on
that tile only. The selected preview uses native `controls`, which supply
play, seek, volume, mute, and keyboard operation. The preview starts muted.
Volume and mute changes are remembered on the node instance for the session
and applied to the next selected video or audio item. Selecting an item never
autoplays it. Videos loop. No global keys are captured.

**Refresh.** Three triggers, all debounced to one request within 500 ms:

1. The refresh button.
2. The `execution_success` event from the frontend `api` event bus, which
   ComfyUI sends to the client that queued the prompt.
3. The `status` event when the queue count reaches zero after having been
   above zero. `status` is broadcast to every client, so a run queued from
   another browser tab still refreshes this one.

Changing any of the five widgets also refreshes. There is no interval timer.

When a refresh brings items that were not in the previous list and `sort` is
`newest first`, the newest item becomes the selection unless the current
selection is playing, in which case the selection is left alone and the new
items simply appear in the grid.

**States.** Empty (`no items match`), loading, error (route message shown
verbatim, last valid list preserved), stale (previous list shown dimmed while
a refresh is in flight), truncated (`list may be incomplete: scan cap
reached`), and folder-not-found. Every state is announced in a polite live
region.

**Laziness.** Tiles outside the visible grid defer their media with an
intersection observer. While the node is collapsed, compact, or off-canvas,
no tile loads media and every playing element is paused. Media elements are
released when the node is removed.

**Actions.** Each tile and the selected preview offer a small labeled menu:

- Open: the `/view` URL in a new tab.
- Copy path: `subfolder/filename` relative to the output root.
- Load workflow: PNG only. Fetches the file through `/view`, hands the blob
  to the frontend's file loading path, which reads the embedded `workflow`
  metadata, and prompts the same way dropping the file on the canvas would.
  Hidden for non-PNG items.

URLs are built with `api.apiURL` and requests with `api.fetchApi`, as the
video cutter does, so subpath deployments work.

## Errors and logging

Route errors are JSON `{ "error": "<message>" }` with status 400, 404, or
500 and the prefix `LFGG Output Gallery:`. Logging uses the
`lfgg_nodes.output_gallery` logger. Logs never include absolute paths; they
name paths relative to the output root.

## Security boundary

- Filesystem: read-only directory listing and `stat` under the resolved output
  root. Symlinked directories are not followed. Every returned path is
  proven inside the root. No file content is read by the pack.
- Serving: only the native `/view` route serves bytes, with `type=output`
  fixed by the frontend. The pack adds no file-serving route.
- Routes: one `GET`, no mutation, no secrets, bounded by the scan cap and the
  200-item limit.
- No `eval`, `exec`, subprocess, ffmpeg, runtime install, or monkey-patching.
  The extension uses only `api`, `app.registerExtension`, and the node's own
  widget and property surface.

## Verification and acceptance

Unit tests with no ComfyUI dependency, using a temporary output root:

- Path validation: empty, nested, absolute, drive-marker, `..`, symlink to a
  directory outside the root, symlinked file inside, missing folder.
- Walk: recursion on and off, hidden entries skipped, symlinked directory not
  followed, scan cap reached with `truncated` true and `scanned` equal to the
  cap.
- Filtering: every `media_filter` value, case-insensitive extensions, `jpeg`
  reported as `jpg`, substring against subfolder and filename.
- Sorting and limit: each sort value on a fixture with known mtimes and
  names, limit slicing, limit bounds.
- Response shape: `subfolder` relative to the root with `/` separators on a
  Windows-style fixture, `mtime` and `size` values, error JSON for every 400
  and 404 case.
- Contract: schema order, combo values, defaults, no outputs, registration in
  root mappings, category and display name.

Frontend tests in the existing Node-based harness:

- Install on a new node and on a configured reload; widgets untouched; no
  serialized gallery state.
- Refresh triggers: button, `execution_success`, `status` zero transition,
  widget change, debounce collapsing bursts.
- Selection rules: kept across refresh, cleared when missing, newest
  auto-selected only under `newest first` and only when nothing is playing.
- Volume and mute remembered and applied; preview starts muted; tiles muted.
- States: each state's text and live-region announcement; last valid list
  preserved on error.
- Laziness: no media loaded while compact or collapsed; pause on collapse.

Manual qualification before release: one Save Image Dynamic run and one
video save into a nested subfolder, confirm the gallery refreshes and selects
the new item, play with sound, confirm a run queued from a second tab
refreshes the first, and check Nodes 2.0 and the legacy renderer.

Gates: `python -m ruff check .`, `python -m pytest -q tests/unit`,
`comfy node validate`, `comfy node pack`, and the frontend checks listed in
`DESIGN.md`. Update `DESIGN.md` with the gallery tile and selected-preview
pattern and run its structural validator.

## Non-goals and deferred work

- No paths outside the output root. If that is ever needed it requires a
  pack-owned file route with a `config.json` root allowlist and full
  containment, and is a separate design.
- No delete, rename, move, or send-to-input. These are mutations that need
  non-GET routes and explicit authorization.
- No outputs. Turning a UI selection into an executable value is deliberately
  excluded.
- No pagination, infinite scroll, date-range filter, regex, or glob.
- No server-side thumbnails or thumbnail cache.
- Deferred: a `mkv` or animated-webp kind, a second page, and reading
  `/view` blake3 asset ids if ComfyUI's asset manager becomes the default.
