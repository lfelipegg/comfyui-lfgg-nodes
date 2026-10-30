# Output Gallery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add the read-only `LFGG Output Gallery` node that lists the latest
images, videos, and audio under one subfolder of the ComfyUI output root and
shows them in the graph without running the workflow.

**Architecture:** Keep path validation, the bounded `os.scandir` walk,
filtering, sorting, and limiting in one dependency-light Python module whose
only ComfyUI contact is the output-root lookup and one `GET` route. Serve every
byte through ComfyUI's native `/view` route. Put all interaction in one
build-free ES module installed by a thin extension loader, tested with the
existing `node:test` harness.

**Tech Stack:** Python 3.10+, ComfyUI V1 nodes, standard library, `aiohttp`
(already a ComfyUI dependency), handwritten ES modules, `pytest`, `node:test`.

---

Implementation baseline: commit `615a371`. The accepted behavior is
`docs/plans/2026-10-30-output-gallery-design.md` and ADR 0007. Use the terms
from `CONTEXT.md` "Output review": gallery item, media filter, selected
preview, gallery refresh, scan cap. Do not broaden to paths outside the output
root, a file-serving route, delete/rename/move, outputs, pagination, server
thumbnails, polling, or ffmpeg.

Commits are deferred: leave every task's changes in the working tree and
report changed files, checks run with output, limitations, and deferred work.

### Task 1: Validate paths and walk the output root

**Files:**
- Create: `tests/unit/test_output_gallery.py`
- Create: `lfgg_nodes/output_gallery.py`

**Step 1: Write the failing pure tests**

Start without importing ComfyUI. Build a temporary output root per test and
pass it to the pure functions:

```python
import os
from pathlib import Path

import pytest

from lfgg_nodes.output_gallery import (
    SCAN_CAP,
    OutputGalleryError,
    resolve_folder,
    walk_output,
)


def touch(root, relative, mtime=None):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def test_resolve_folder_accepts_empty_and_nested_paths(tmp_path):
    (tmp_path / "runs" / "wan22").mkdir(parents=True)
    assert resolve_folder(tmp_path, "") == tmp_path
    assert resolve_folder(tmp_path, "runs/wan22") == tmp_path / "runs" / "wan22"
    assert resolve_folder(tmp_path, "runs\\wan22") == tmp_path / "runs" / "wan22"


@pytest.mark.parametrize(
    "value",
    ["/absolute", "C:\\drive", "C:/drive", "..", "runs/../..", "runs/../../x"],
)
def test_resolve_folder_rejects_paths_that_leave_the_output_root(tmp_path, value):
    with pytest.raises(OutputGalleryError, match="output root") as info:
        resolve_folder(tmp_path, value)
    assert info.value.status == 400


def test_resolve_folder_rejects_symlink_escape(tmp_path):
    outside = tmp_path.parent / "outside"
    outside.mkdir(exist_ok=True)
    (tmp_path / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(OutputGalleryError, match="output root") as info:
        resolve_folder(tmp_path, "escape")
    assert info.value.status == 400


def test_resolve_folder_reports_missing_folders_as_not_found(tmp_path):
    with pytest.raises(OutputGalleryError, match="folder not found under output: runs/missing") as info:
        resolve_folder(tmp_path, "runs/missing")
    assert info.value.status == 404


def test_walk_recurses_only_when_requested_and_skips_hidden_entries(tmp_path):
    touch(tmp_path, "a.png")
    touch(tmp_path, ".hidden.png")
    touch(tmp_path, "nested/b.mp4")
    touch(tmp_path, ".hidden/c.mp4")
    flat, scanned, truncated = walk_output(tmp_path, tmp_path, include_subfolders=False)
    assert [relative.as_posix() for relative, _ in flat] == ["a.png"]
    deep, _, _ = walk_output(tmp_path, tmp_path, include_subfolders=True)
    assert sorted(relative.as_posix() for relative, _ in deep) == ["a.png", "nested/b.mp4"]
    assert truncated is False


def test_walk_never_follows_symlinked_directories_but_keeps_inside_symlinked_files(tmp_path): ...


def test_walk_stops_at_the_scan_cap_and_reports_truncation(tmp_path):
    for index in range(5):
        touch(tmp_path, f"{index}.png")
    files, scanned, truncated = walk_output(tmp_path, tmp_path, include_subfolders=True, scan_cap=3)
    assert scanned == 3
    assert truncated is True
```

Add cases for `scanned` counting hidden entries, an exact-cap fixture that is
not truncated, a pending subfolder left unvisited at the cap, and a symlinked
file that resolves outside the root being skipped.

**Step 2: Run the focused tests and verify RED**

```bash
.venv/bin/python -m pytest -q tests/unit/test_output_gallery.py
```

Expected: collection fails because the module does not exist.

**Step 3: Implement the pure helpers**

In `lfgg_nodes/output_gallery.py` use only standard-library imports at module
load: `collections.deque`, `logging`, `os`, `pathlib`. Define the
`lfgg_nodes.output_gallery` logger, the `LFGG Output Gallery: ` error prefix,
`SCAN_CAP = 20_000`, and `OutputGalleryError(ValueError)` carrying `status`.

`resolve_folder(root, path)`:

1. Reject non-string or over-long values.
2. Normalize `\` to `/`, reject POSIX/Windows absolute paths and drive markers
   with `PurePosixPath`/`PureWindowsPath`, reject any `..` component, and drop
   empty and `.` components.
3. Resolve `root / path` with `strict=False`, prove `is_relative_to(root)`,
   then resolve `strict=True`; a missing folder is 404
   `folder not found under output: <path>`; anything that resolves outside the
   root is 400 `path must stay inside the ComfyUI output root`.

`walk_output(root, folder, *, include_subfolders, scan_cap=SCAN_CAP)` walks
breadth-first with `os.scandir`, never follows symlinked directories, skips
names starting with `.`, counts every entry against the cap, resolves symlinked
files and keeps only those inside the root, and returns
`([(relative_path, absolute_path), ...], scanned, truncated)`.

**Step 4: Run focused checks and verify GREEN**

```bash
.venv/bin/python -m pytest -q tests/unit/test_output_gallery.py
.venv/bin/python -m ruff check lfgg_nodes/output_gallery.py tests/unit/test_output_gallery.py
```

### Task 2: Filter, sort, limit, and describe gallery items

**Files:**
- Modify: `tests/unit/test_output_gallery.py`
- Modify: `lfgg_nodes/output_gallery.py`

**Step 1: Add failing listing tests**

```python
def test_media_filter_matches_kinds_and_extensions_case_insensitively(tmp_path):
    for name in ["a.PNG", "b.jpeg", "c.webp", "d.gif", "e.mp4", "f.WEBM", "g.mov", "h.mp3", "i.wav", "j.flac", "k.ogg", "l.txt"]:
        touch(tmp_path, name)
    def names(media_filter):
        result = list_gallery(tmp_path, path="", include_subfolders=True, media_filter=media_filter, name_filter="", sort="name A to Z", limit=200)
        return [item["filename"] for item in result["items"]]
    assert names("all") == [...]  # every media file, never l.txt
    assert names("images") == ["a.PNG", "b.jpeg", "c.webp", "d.gif"]
    assert names("jpg") == ["b.jpeg"]


def test_jpeg_is_reported_as_jpg_with_its_kind(tmp_path): ...
def test_name_filter_matches_subfolders_and_filenames_case_insensitively(tmp_path): ...


@pytest.mark.parametrize(("sort", "expected"), [
    ("newest first", ["c.png", "b.png", "a.png"]),
    ("oldest first", ["a.png", "b.png", "c.png"]),
    ("name A to Z", ["a.png", "b.png", "c.png"]),
    ("name Z to A", ["c.png", "b.png", "a.png"]),
])
def test_sort_orders_by_mtime_or_name(tmp_path, sort, expected): ...


def test_limit_slices_after_sorting(tmp_path): ...


def test_items_use_root_relative_posix_subfolders_and_stat_values():
    item = describe_item(PureWindowsPath("runs\\wan22\\2026-10-30\\clip.MP4"), size=4193304, mtime=1793123412.51)
    assert item == {"filename": "clip.MP4", "subfolder": "runs/wan22/2026-10-30", "kind": "video", "extension": "mp4", "size": 4193304, "mtime": 1793123412.51}
```

Add `scanned` and `truncated` propagation, a root-level item with an empty
`subfolder`, and the `root` echo of the normalized `path`.

**Step 2: Run the focused tests and verify RED**

```bash
.venv/bin/python -m pytest -q tests/unit/test_output_gallery.py
```

**Step 3: Implement listing**

Add the extension tables (`jpeg` maps to kind `image`, reported `jpg`), the
`MEDIA_FILTERS` and `SORTS` tuples in the exact widget order,
`describe_item(relative, *, size, mtime)`, and
`list_gallery(root, *, path, include_subfolders, media_filter, name_filter, sort, limit)`:

1. `resolve_folder`, then `walk_output`.
2. Filter by extension and by lower-cased `name_filter` against the path
   relative to the requested folder.
3. `os.stat` only the surviving files; drop files that vanish mid-call.
4. Sort by `(mtime, name)` or by case-folded relative name, slice to `limit`.
5. Return `{"root", "items", "scanned", "truncated"}`.

**Step 4: Run focused checks and verify GREEN**

```bash
.venv/bin/python -m pytest -q tests/unit/test_output_gallery.py
.venv/bin/python -m ruff check lfgg_nodes/output_gallery.py tests/unit/test_output_gallery.py
```

### Task 3: Add the V1 node, the list route, and registration

**Files:**
- Modify: `tests/unit/test_output_gallery.py`
- Modify: `tests/unit/test_contract.py`
- Modify: `lfgg_nodes/output_gallery.py`
- Modify: `__init__.py`

**Step 1: Add failing route, schema, and registration tests**

Stub `aiohttp.web.json_response` and `folder_paths` through `sys.modules` as
`tests/unit/test_video_cutter.py` does. Cover:

```python
def test_list_route_returns_items_for_valid_queries(monkeypatch, tmp_path): ...


@pytest.mark.parametrize(("query", "status", "message"), [
    ({"path": "/abs"}, 400, "path must stay inside the ComfyUI output root"),
    ({"path": "missing"}, 404, "folder not found under output: missing"),
    ({"include_subfolders": "maybe"}, 400, "include_subfolders must be true or false"),
    ({"media_filter": "exe"}, 400, "media_filter must be one of"),
    ({"sort": "random"}, 400, "sort must be one of"),
    ({"limit": "0"}, 400, "limit must be an integer between 1 and 200"),
    ({"limit": "201"}, 400, ...),
    ({"limit": "ten"}, 400, ...),
])
def test_list_route_rejects_invalid_queries_with_json_errors(...): ...


def test_list_route_reports_unavailable_output_root_as_500(...): ...
def test_list_route_registers_as_namespaced_get(monkeypatch): ...
def test_module_import_is_side_effect_free_without_comfyui(): ...
```

In `tests/unit/test_contract.py` add `LFGG_OutputGallery` to the display and
class mapping assertions after `LFGG_VideoCutter`, and add
`test_output_gallery_v1_schema_is_exact` asserting category `LFGG/workflow`,
`FUNCTION == "show"`, empty `RETURN_TYPES`, `OUTPUT_NODE is False`, and the
exact `INPUT_TYPES()` with the six inputs in order, combo options, and
defaults.

**Step 2: Run the focused tests and verify RED**

```bash
.venv/bin/python -m pytest -q tests/unit/test_output_gallery.py tests/unit/test_contract.py
```

**Step 3: Implement the ComfyUI boundary**

- `_output_root()` mirrors `save_image_dynamic._output_root`.
- `parse_query(mapping)` validates the six parameters and ignores unknown keys.
- `async def output_gallery_list(request)` parses, runs `list_gallery` with
  `asyncio.to_thread`, and returns `web.json_response` with the result or
  `{"error": message}` at 400, 404, or 500. Log at warning level with
  output-relative paths only.
- `class OutputGallery` with the exact schema, `RETURN_TYPES = ()`,
  `OUTPUT_NODE = False`, `CATEGORY = "LFGG/workflow"`, and `show()` returning
  an empty tuple.
- Register the `GET /lfgg/v1/output-gallery/list` route in the same
  `try: from server import PromptServer` block the video cutter uses.
- Add `{"LFGG_OutputGallery": OutputGallery}` after the video cutter in
  `__init__.py` and `"LFGG_OutputGallery": "LFGG Output Gallery"` to the
  display mapping.

**Step 4: Run focused checks and verify GREEN**

```bash
.venv/bin/python -m pytest -q tests/unit/test_output_gallery.py tests/unit/test_contract.py
.venv/bin/python -m ruff check .
```

### Task 4: Add the gallery frontend

**Files:**
- Create: `web/output_gallery.mjs`
- Create: `web/output_gallery.js`
- Create: `tests/frontend/output_gallery.test.mjs`

**Step 1: Write failing dependency-free frontend tests**

Import only the `.mjs` module. Use the element stub from
`tests/frontend/video_cutter.test.mjs`, a fake node with the six standard
widgets plus `addDOMWidget`, `setSize`, `computeSize`, and `setDirtyCanvas`,
an injected `fetchList`, fake timers for the 500 ms debounce, a fake event bus
with `addEventListener`/`removeEventListener`/`dispatch`, and an optional fake
intersection observer. Cover every case under "Verification and acceptance":

- install on a new node and on a configured reload; widgets untouched; the DOM
  widget is non-serializing and `onSerialize` drops its positional hole;
- refresh from the button, `execution_success`, the `status` zero transition
  (and not on the first zero), each widget change, and burst collapsing;
- selection kept across refresh, cleared when missing, newest auto-selected
  only under `newest first` and only when nothing is playing;
- preview starts muted, tiles muted, volume and mute remembered and applied;
- empty, loading, error with the last valid list preserved, stale dimming,
  truncated, and not-found text in the live region;
- no tile media while compact or collapsed, pause when the root leaves view,
  media released on `onRemoved`;
- open, copy path, and load-workflow actions, with load hidden for non-PNG.

**Step 2: Run the focused test and verify RED**

```bash
node --test tests/frontend/output_gallery.test.mjs
```

**Step 3: Implement the module and loader**

`web/output_gallery.mjs` exports `OUTPUT_GALLERY_ID`, `buildOutputViewUrl`,
`itemKey`, `buildListQuery`, `kindOf`, and `installOutputGallery(node, deps)`.
It binds only to `LFGG_OutputGallery`, is idempotent per instance, uses
`createEditorView` with `lfgg_editor_expanded`, `initializeRoot`, and
`omitPresentationValues`. Layout: heading, selected preview (180/360 px caps,
`object-fit: contain`), caption, count line, refresh button, disclosure, lazy
tile grid (`repeat(auto-fill, minmax(96px, 1fr))`), and one polite live region.
Keep selection and volume on the controller only.

`web/output_gallery.js` imports `api` and `app`, maps `fetchList` to
`api.fetchApi`, `viewUrl` to `api.apiURL`, `fetchBlob` to `api.fetchApi`,
`loadFile` to `app.handleFile`, passes `api` as `events`, and registers
`lfgg.outputGallery` on `nodeCreated` and `loadedGraphNode`.

**Step 4: Run frontend checks and verify GREEN**

```bash
node --test tests/frontend/output_gallery.test.mjs
node --test tests/frontend/video_cutter.test.mjs
```

### Task 5: Document, bump, and qualify the 1.6.0 contract

**Files:**
- Modify: `README.md`, `DESIGN.md`, `pyproject.toml`
- Modify: `tests/unit/test_contract.py`, `tests/package/test_archive.py`
- Create: `release/1.6.0-schema.json`

**Step 1: Add failing documentation and package assertions**

Point the contract test at version `1.6.0` and `release/1.6.0-schema.json`,
add README claims for `LFGG Output Gallery`, `Stable ID \`LFGG_OutputGallery\``,
`GET /lfgg/v1/output-gallery/list`, the scan cap, and the new
`node --test tests/frontend/output_gallery.test.mjs` line. Add the three new
runtime files to `EXPECTED_PATHS`.

**Step 2: Run focused checks and verify RED**

```bash
.venv/bin/python -m pytest -q tests/unit/test_contract.py
```

**Step 3: Write the documentation**

- README: node table row, a node section under "## Nodes" naming the widgets,
  states, actions, and refresh triggers, a paragraph under "## File and network
  behavior" documenting the read-only route, bounds, and that only `/view`
  serves bytes, and the test line under "## Develop and qualify".
- DESIGN.md: add the gallery tile and selected-preview pattern under "Rich
  editors and reports", bump "Last reviewed", then run
  `python3 ~/.claude/skills/design-md-governor/scripts/validate_design_md.py DESIGN.md`.
- `pyproject.toml` version `1.6.0`; generate `release/1.6.0-schema.json` from
  the same JSON-safe mapping shape the contract test asserts.
- `python3 .codex-context/ctx.py ingest`.

**Step 4: Run every gate and verify GREEN**

```bash
node --test tests/frontend/output_gallery.test.mjs
.venv/bin/python -m ruff check .
.venv/bin/python -m pytest -q tests/unit
.venv/bin/comfy node validate
.venv/bin/comfy node pack
.venv/bin/python -m pytest -q tests/package --archive node.zip
```

Manual qualification before release stays as the design lists it: one Save
Image Dynamic run and one nested video save, play with sound, a second-tab
queue, Nodes 2.0 and the legacy renderer, and the packed integration run.
Record any unrun step as a limitation.
