"""LFGG Output Gallery: list recent output files for the frontend viewer.

The node is a pure viewer with no outputs. Its frontend extension asks the
read-only ``GET /lfgg/v1/output-gallery/list`` route for gallery items under
one subfolder of the ComfyUI output root, and ComfyUI's native ``/view`` route
serves every byte. See ``docs/plans/2026-10-30-output-gallery-design.md`` for
the accepted contract and ADR 0007 for the scope decision.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections import deque
from pathlib import Path, PurePosixPath, PureWindowsPath

LOGGER = logging.getLogger("lfgg_nodes.output_gallery")
ERROR_PREFIX = "LFGG Output Gallery: "

SCAN_CAP = 20_000
LIMIT_RANGE = (1, 200)
DEFAULT_LIMIT = 24
MAX_PATH_CHARS = 1024
MAX_NAME_FILTER_CHARS = 256

IMAGE_EXTENSIONS = ("png", "jpg", "jpeg", "webp", "gif")
VIDEO_EXTENSIONS = ("mp4", "webm", "mov")
AUDIO_EXTENSIONS = ("mp3", "wav", "flac", "ogg")
KIND_BY_EXTENSION = {
    **{extension: "image" for extension in IMAGE_EXTENSIONS},
    **{extension: "video" for extension in VIDEO_EXTENSIONS},
    **{extension: "audio" for extension in AUDIO_EXTENSIONS},
}
REPORTED_EXTENSION = {"jpeg": "jpg"}
EXTENSIONS_BY_KIND_FILTER = {
    "images": IMAGE_EXTENSIONS,
    "videos": VIDEO_EXTENSIONS,
    "audio": AUDIO_EXTENSIONS,
}
MEDIA_FILTERS = (
    "all",
    "images",
    "videos",
    "audio",
    "png",
    "jpg",
    "webp",
    "gif",
    "mp4",
    "webm",
    "mov",
    "mp3",
    "wav",
    "flac",
    "ogg",
)
SORTS = ("newest first", "oldest first", "name A to Z", "name Z to A")
DEFAULT_SORT = SORTS[0]


class OutputGalleryError(ValueError):
    """Actionable failure with the HTTP status the list route should return."""

    def __init__(self, message, status=400):
        super().__init__(f"{ERROR_PREFIX}{message}")
        self.status = status


# --------------------------------------------------------------------------
# Path validation (ComfyUI-independent)
# --------------------------------------------------------------------------


def _outside_root():
    return OutputGalleryError("path must stay inside the ComfyUI output root")


def normalize_path(value):
    """Return the output-relative POSIX form of ``value`` or raise 400."""
    if not isinstance(value, str):
        raise OutputGalleryError("path must be text")
    if len(value) > MAX_PATH_CHARS:
        raise OutputGalleryError(f"path must be at most {MAX_PATH_CHARS} characters")
    cleaned = value.strip().replace("\\", "/")
    windows = PureWindowsPath(cleaned)
    if (
        PurePosixPath(cleaned).is_absolute()
        or windows.is_absolute()
        or windows.drive
        or cleaned.startswith("//")
    ):
        raise _outside_root()
    components = []
    for component in cleaned.split("/"):
        if component == "..":
            raise _outside_root()
        if component in {"", "."}:
            continue
        components.append(component)
    return "/".join(components)


def resolve_folder(root, path):
    """Resolve ``root / path`` and prove it is a directory inside ``root``."""
    relative = normalize_path(path)
    candidate = root.joinpath(*relative.split("/")) if relative else root
    try:
        loose = candidate.resolve(strict=False)
    except (OSError, RuntimeError):
        raise _outside_root() from None
    if not loose.is_relative_to(root):
        raise _outside_root()
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError:
        raise OutputGalleryError(
            f"folder not found under output: {relative}", status=404
        ) from None
    except (OSError, RuntimeError):
        raise _outside_root() from None
    if not resolved.is_relative_to(root):
        raise _outside_root()
    if not resolved.is_dir():
        raise OutputGalleryError(
            f"folder not found under output: {relative}", status=404
        )
    return resolved


# --------------------------------------------------------------------------
# Walk, filter, sort, limit (ComfyUI-independent)
# --------------------------------------------------------------------------


def _inside_file(root, entry):
    """Return the absolute path for a file entry inside ``root`` or ``None``."""
    if entry.is_symlink():
        try:
            resolved = Path(entry.path).resolve(strict=True)
        except (OSError, RuntimeError):
            return None
        if not resolved.is_relative_to(root) or not resolved.is_file():
            return None
        return Path(entry.path)
    try:
        if not entry.is_file(follow_symlinks=False):
            return None
    except OSError:
        return None
    return Path(entry.path)


def walk_output(root, folder, *, include_subfolders, scan_cap=None):
    """Walk ``folder`` under ``root`` without following symlinked directories.

    Returns ``(files, scanned, truncated)`` where ``files`` holds
    ``(relative_to_root, absolute)`` pairs, ``scanned`` counts every directory
    entry visited, and ``truncated`` reports a walk stopped by the scan cap.
    """
    cap = SCAN_CAP if scan_cap is None else scan_cap
    pending = deque([folder])
    files = []
    scanned = 0
    truncated = False
    while pending and not truncated:
        directory = pending.popleft()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if scanned >= cap:
                        truncated = True
                        break
                    scanned += 1
                    if entry.name.startswith("."):
                        continue
                    try:
                        is_directory = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        continue
                    if is_directory:
                        if include_subfolders:
                            pending.append(Path(entry.path))
                        continue
                    absolute = _inside_file(root, entry)
                    if absolute is not None:
                        files.append((absolute.relative_to(root), absolute))
        except OSError as error:
            LOGGER.warning(
                "could not read output folder %s: %s",
                Path(directory).relative_to(root).as_posix() or ".",
                error.strerror or error.__class__.__name__,
            )
    if pending:
        truncated = True
    return files, scanned, truncated


def _extension(name):
    return name.rsplit(".", 1)[1].lower() if "." in name else ""


def _accepted_extensions(media_filter):
    if media_filter == "all":
        return frozenset(KIND_BY_EXTENSION)
    if media_filter in EXTENSIONS_BY_KIND_FILTER:
        return frozenset(EXTENSIONS_BY_KIND_FILTER[media_filter])
    return frozenset(
        extension
        for extension in KIND_BY_EXTENSION
        if REPORTED_EXTENSION.get(extension, extension) == media_filter
    )


def describe_item(relative, *, size, mtime):
    """Build one gallery item from a root-relative path and stat values."""
    extension = _extension(relative.name)
    return {
        "filename": relative.name,
        "subfolder": "/".join(relative.parent.parts),
        "kind": KIND_BY_EXTENSION[extension],
        "extension": REPORTED_EXTENSION.get(extension, extension),
        "size": size,
        "mtime": mtime,
    }


def list_gallery(
    root,
    *,
    path,
    include_subfolders,
    media_filter,
    name_filter,
    sort,
    limit,
):
    """List gallery items under ``root / path`` with the widget semantics."""
    folder = resolve_folder(root, path)
    files, scanned, truncated = walk_output(
        root, folder, include_subfolders=include_subfolders
    )
    accepted = _accepted_extensions(media_filter)
    needle = name_filter.lower()
    candidates = []
    for relative, absolute in files:
        if _extension(relative.name) not in accepted:
            continue
        local = absolute.relative_to(folder).as_posix()
        if needle and needle not in local.lower():
            continue
        candidates.append((relative, absolute, local))

    if sort in {"newest first", "oldest first"}:
        stamped = []
        for relative, absolute, local in candidates:
            try:
                result = os.stat(absolute)
            except OSError:
                continue
            stamped.append((result.st_mtime, local, relative, result))
        stamped.sort(key=lambda row: (row[0], row[1]), reverse=sort == "newest first")
        selected = [(relative, result) for _, _, relative, result in stamped[:limit]]
    else:
        candidates.sort(
            key=lambda row: (row[2].casefold(), row[2]),
            reverse=sort == "name Z to A",
        )
        selected = []
        for relative, absolute, _local in candidates:
            if len(selected) >= limit:
                break
            try:
                selected.append((relative, os.stat(absolute)))
            except OSError:
                continue

    return {
        "root": normalize_path(path),
        "items": [
            describe_item(relative, size=result.st_size, mtime=result.st_mtime)
            for relative, result in selected
        ],
        "scanned": scanned,
        "truncated": truncated,
    }


# --------------------------------------------------------------------------
# Query parsing
# --------------------------------------------------------------------------


def parse_query(query):
    """Validate the list route parameters; unknown parameters are ignored."""
    path = query.get("path", "")
    if not isinstance(path, str):
        raise OutputGalleryError("path must be text")
    include = query.get("include_subfolders", "true")
    if include not in {"true", "false"}:
        raise OutputGalleryError("include_subfolders must be true or false")
    media_filter = query.get("media_filter", "all")
    if media_filter not in MEDIA_FILTERS:
        raise OutputGalleryError(
            f"media_filter must be one of: {', '.join(MEDIA_FILTERS)}"
        )
    name_filter = query.get("name_filter", "")
    if not isinstance(name_filter, str):
        raise OutputGalleryError("name_filter must be text")
    if len(name_filter) > MAX_NAME_FILTER_CHARS:
        raise OutputGalleryError(
            f"name_filter must be at most {MAX_NAME_FILTER_CHARS} characters"
        )
    sort = query.get("sort", DEFAULT_SORT)
    if sort not in SORTS:
        raise OutputGalleryError(f"sort must be one of: {', '.join(SORTS)}")
    raw_limit = query.get("limit", str(DEFAULT_LIMIT))
    low, high = LIMIT_RANGE
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        limit = None
    if limit is None or not low <= limit <= high:
        raise OutputGalleryError(
            f"limit must be an integer between {low} and {high}"
        )
    return {
        "path": path,
        "include_subfolders": include == "true",
        "media_filter": media_filter,
        "name_filter": name_filter,
        "sort": sort,
        "limit": limit,
    }


# --------------------------------------------------------------------------
# Node and route (ComfyUI boundary)
# --------------------------------------------------------------------------


def _output_root():
    import folder_paths

    try:
        root = Path(folder_paths.get_output_directory()).resolve(strict=True)
    except OSError:
        raise OutputGalleryError(
            "ComfyUI output root is unavailable", status=500
        ) from None
    if not root.is_dir():
        raise OutputGalleryError("ComfyUI output root is unavailable", status=500)
    return root


async def output_gallery_list(request):
    from aiohttp import web

    try:
        query = parse_query(request.query)
        root = _output_root()
        result = await asyncio.to_thread(list_gallery, root, **query)
    except OutputGalleryError as error:
        if error.status >= 500:
            LOGGER.warning("list failed: %s", error)
        return web.json_response({"error": str(error)}, status=error.status)
    return web.json_response(result)


class OutputGallery:
    DESCRIPTION = (
        "Shows the latest images, videos, and audio saved under one output "
        "subfolder without running the workflow."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "path": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": (
                            "Subfolder relative to the ComfyUI output root. "
                            "Empty means the output root itself."
                        ),
                    },
                ),
                "include_subfolders": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": (
                            "Include files from nested subfolders, bounded by "
                            "the scan cap."
                        ),
                    },
                ),
                "media_filter": (
                    "COMBO",
                    {
                        "options": list(MEDIA_FILTERS),
                        "default": "all",
                        "tooltip": (
                            "Limit items to all media, one kind, or one file "
                            "extension."
                        ),
                    },
                ),
                "name_filter": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": (
                            "Case-insensitive text matched against the path "
                            "relative to the chosen subfolder."
                        ),
                    },
                ),
                "sort": (
                    "COMBO",
                    {
                        "options": list(SORTS),
                        "default": DEFAULT_SORT,
                        "tooltip": (
                            "Order by file modification time or by name."
                        ),
                    },
                ),
                "limit": (
                    "INT",
                    {
                        "default": DEFAULT_LIMIT,
                        "min": LIMIT_RANGE[0],
                        "max": LIMIT_RANGE[1],
                        "step": 1,
                        "tooltip": "Number of items shown; one page only.",
                    },
                ),
            }
        }

    RETURN_TYPES = ()
    RETURN_NAMES = ()
    OUTPUT_TOOLTIPS = ()
    FUNCTION = "show"
    OUTPUT_NODE = False
    CATEGORY = "LFGG/workflow"

    def show(self, **_inputs):
        return ()


try:
    from server import PromptServer
except ModuleNotFoundError as error:
    if error.name != "server":
        raise
else:
    PromptServer.instance.routes.get("/lfgg/v1/output-gallery/list")(
        output_gallery_list
    )


__all__ = [
    "DEFAULT_LIMIT",
    "LIMIT_RANGE",
    "MEDIA_FILTERS",
    "SCAN_CAP",
    "SORTS",
    "OutputGallery",
    "OutputGalleryError",
    "describe_item",
    "list_gallery",
    "normalize_path",
    "output_gallery_list",
    "parse_query",
    "resolve_folder",
    "walk_output",
]
