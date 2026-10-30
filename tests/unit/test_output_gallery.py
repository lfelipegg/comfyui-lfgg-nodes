import asyncio
import importlib
import os
import sys
from pathlib import PurePosixPath, PureWindowsPath
from types import ModuleType, SimpleNamespace

import pytest

from lfgg_nodes.output_gallery import (
    DEFAULT_LIMIT,
    LIMIT_RANGE,
    MEDIA_FILTERS,
    SCAN_CAP,
    SORTS,
    OutputGallery,
    OutputGalleryError,
    describe_item,
    list_gallery,
    output_gallery_list,
    parse_query,
    resolve_folder,
    walk_output,
)

MEDIA_NAMES = [
    "a.PNG",
    "b.jpeg",
    "c.webp",
    "d.gif",
    "e.mp4",
    "f.WEBM",
    "g.mov",
    "h.mp3",
    "i.wav",
    "j.flac",
    "k.ogg",
]


def touch(root, relative, mtime=None, content=b"x"):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def listing(root, **overrides):
    query = {
        "path": "",
        "include_subfolders": True,
        "media_filter": "all",
        "name_filter": "",
        "sort": "name A to Z",
        "limit": 200,
    }
    query.update(overrides)
    return list_gallery(root, **query)


def names(root, **overrides):
    return [item["filename"] for item in listing(root, **overrides)["items"]]


class FakeRequest:
    def __init__(self, query):
        self.query = query


def install_route_modules(monkeypatch, output_root):
    aiohttp = ModuleType("aiohttp")
    aiohttp.web = SimpleNamespace(
        json_response=lambda data, status=200: SimpleNamespace(
            status=status, data=data
        )
    )
    monkeypatch.setitem(sys.modules, "aiohttp", aiohttp)
    monkeypatch.setitem(
        sys.modules,
        "folder_paths",
        SimpleNamespace(get_output_directory=lambda: str(output_root)),
    )


# --------------------------------------------------------------------------
# Path validation
# --------------------------------------------------------------------------


def test_resolve_folder_accepts_empty_and_nested_paths(tmp_path):
    (tmp_path / "runs" / "wan22").mkdir(parents=True)

    assert resolve_folder(tmp_path, "") == tmp_path
    assert resolve_folder(tmp_path, "   ") == tmp_path
    assert resolve_folder(tmp_path, "runs/wan22") == tmp_path / "runs" / "wan22"
    assert resolve_folder(tmp_path, "runs\\wan22") == tmp_path / "runs" / "wan22"
    assert resolve_folder(tmp_path, "./runs//wan22/") == tmp_path / "runs" / "wan22"


@pytest.mark.parametrize(
    "value",
    [
        "/absolute",
        "C:\\drive",
        "C:/drive",
        "C:",
        "\\\\server\\share",
        "..",
        "runs/..",
        "runs/../..",
        "..\\runs",
    ],
)
def test_resolve_folder_rejects_paths_that_leave_the_output_root(tmp_path, value):
    with pytest.raises(OutputGalleryError, match="ComfyUI output root") as info:
        resolve_folder(tmp_path, value)

    assert info.value.status == 400
    assert str(info.value).startswith("LFGG Output Gallery: ")
    assert str(tmp_path) not in str(info.value)


def test_resolve_folder_rejects_symlinked_directories_outside_the_root(tmp_path):
    root = tmp_path / "output"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(OutputGalleryError, match="ComfyUI output root") as info:
        resolve_folder(root, "escape")

    assert info.value.status == 400


def test_resolve_folder_rejects_non_string_and_oversized_paths(tmp_path):
    with pytest.raises(OutputGalleryError, match="path must be text") as info:
        resolve_folder(tmp_path, None)
    assert info.value.status == 400
    with pytest.raises(OutputGalleryError, match="at most 1024"):
        resolve_folder(tmp_path, "a" * 1025)


def test_resolve_folder_reports_missing_folders_as_not_found(tmp_path):
    with pytest.raises(OutputGalleryError) as info:
        resolve_folder(tmp_path, "runs\\missing")

    assert info.value.status == 404
    assert str(info.value) == (
        "LFGG Output Gallery: folder not found under output: runs/missing"
    )


def test_resolve_folder_reports_a_file_path_as_not_found(tmp_path):
    touch(tmp_path, "clip.mp4")

    with pytest.raises(OutputGalleryError, match="folder not found") as info:
        resolve_folder(tmp_path, "clip.mp4")

    assert info.value.status == 404


# --------------------------------------------------------------------------
# Walk
# --------------------------------------------------------------------------


def test_walk_recurses_only_when_requested(tmp_path):
    touch(tmp_path, "a.png")
    touch(tmp_path, "nested/deeper/b.mp4")

    flat, _, truncated = walk_output(tmp_path, tmp_path, include_subfolders=False)
    deep, _, _ = walk_output(tmp_path, tmp_path, include_subfolders=True)

    assert [relative.as_posix() for relative, _ in flat] == ["a.png"]
    assert sorted(relative.as_posix() for relative, _ in deep) == [
        "a.png",
        "nested/deeper/b.mp4",
    ]
    assert truncated is False


def test_walk_skips_hidden_files_and_directories_but_counts_them(tmp_path):
    touch(tmp_path, "a.png")
    touch(tmp_path, ".hidden.png")
    touch(tmp_path, ".hidden/c.mp4")

    files, scanned, truncated = walk_output(
        tmp_path, tmp_path, include_subfolders=True
    )

    assert [relative.as_posix() for relative, _ in files] == ["a.png"]
    assert scanned == 3
    assert truncated is False


def test_walk_never_follows_symlinked_directories(tmp_path):
    root = tmp_path / "output"
    touch(root, "real/a.png")
    (root / "inside_link").symlink_to(root / "real", target_is_directory=True)
    outside = tmp_path / "outside"
    touch(outside, "b.png")
    (root / "outside_link").symlink_to(outside, target_is_directory=True)

    files, _, _ = walk_output(root, root, include_subfolders=True)

    assert [relative.as_posix() for relative, _ in files] == ["real/a.png"]


def test_walk_keeps_symlinked_files_that_resolve_inside_the_root(tmp_path):
    root = tmp_path / "output"
    touch(root, "real/a.png")
    (root / "inside.png").symlink_to(root / "real" / "a.png")
    outside = tmp_path / "outside"
    touch(outside, "b.png")
    (root / "outside.png").symlink_to(outside / "b.png")
    (root / "dangling.png").symlink_to(root / "missing.png")

    files, _, _ = walk_output(root, root, include_subfolders=True)

    assert sorted(relative.as_posix() for relative, _ in files) == [
        "inside.png",
        "real/a.png",
    ]


def test_walk_returns_root_relative_paths_for_a_nested_folder(tmp_path):
    touch(tmp_path, "runs/wan22/clip.mp4")

    files, _, _ = walk_output(
        tmp_path, tmp_path / "runs" / "wan22", include_subfolders=True
    )

    assert [(relative.as_posix(), absolute) for relative, absolute in files] == [
        ("runs/wan22/clip.mp4", tmp_path / "runs" / "wan22" / "clip.mp4")
    ]


def test_walk_stops_at_the_scan_cap_and_reports_truncation(tmp_path):
    for index in range(5):
        touch(tmp_path, f"{index}.png")

    files, scanned, truncated = walk_output(
        tmp_path, tmp_path, include_subfolders=True, scan_cap=3
    )

    assert scanned == 3
    assert len(files) == 3
    assert truncated is True


def test_walk_at_exactly_the_scan_cap_is_not_truncated(tmp_path):
    for index in range(3):
        touch(tmp_path, f"{index}.png")

    _, scanned, truncated = walk_output(
        tmp_path, tmp_path, include_subfolders=True, scan_cap=3
    )

    assert scanned == 3
    assert truncated is False


def test_walk_reports_truncation_when_subfolders_remain_unvisited(tmp_path):
    touch(tmp_path, "a.png")
    touch(tmp_path, "nested/b.png")

    files, scanned, truncated = walk_output(
        tmp_path, tmp_path, include_subfolders=True, scan_cap=2
    )

    assert scanned == 2
    assert [relative.as_posix() for relative, _ in files] == ["a.png"]
    assert truncated is True


def test_scan_cap_is_twenty_thousand():
    assert SCAN_CAP == 20_000


# --------------------------------------------------------------------------
# Filtering, sorting, limit, and item shape
# --------------------------------------------------------------------------


def test_media_filter_values_match_the_widget_order():
    assert MEDIA_FILTERS == (
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
    assert SORTS == ("newest first", "oldest first", "name A to Z", "name Z to A")
    assert LIMIT_RANGE == (1, 200)
    assert DEFAULT_LIMIT == 24


def test_media_filter_kinds_match_extensions_case_insensitively(tmp_path):
    for name in [*MEDIA_NAMES, "l.txt", "m.PNG.bak", "noext"]:
        touch(tmp_path, name)

    assert names(tmp_path) == MEDIA_NAMES
    assert names(tmp_path, media_filter="images") == MEDIA_NAMES[:4]
    assert names(tmp_path, media_filter="videos") == MEDIA_NAMES[4:7]
    assert names(tmp_path, media_filter="audio") == MEDIA_NAMES[7:]


@pytest.mark.parametrize(
    ("media_filter", "expected"),
    [
        ("png", ["a.PNG"]),
        ("jpg", ["b.jpeg", "n.JPG"]),
        ("webp", ["c.webp"]),
        ("gif", ["d.gif"]),
        ("mp4", ["e.mp4"]),
        ("webm", ["f.WEBM"]),
        ("mov", ["g.mov"]),
        ("mp3", ["h.mp3"]),
        ("wav", ["i.wav"]),
        ("flac", ["j.flac"]),
        ("ogg", ["k.ogg"]),
    ],
)
def test_each_extension_filter_selects_only_its_files(tmp_path, media_filter, expected):
    for name in [*MEDIA_NAMES, "n.JPG"]:
        touch(tmp_path, name)

    assert names(tmp_path, media_filter=media_filter) == expected


def test_jpeg_is_reported_as_jpg_with_the_image_kind(tmp_path):
    touch(tmp_path, "photo.JPEG")

    [item] = listing(tmp_path)["items"]

    assert item["filename"] == "photo.JPEG"
    assert item["extension"] == "jpg"
    assert item["kind"] == "image"


def test_name_filter_matches_subfolders_and_filenames_case_insensitively(tmp_path):
    touch(tmp_path, "runs/Wan22/clip.mp4")
    touch(tmp_path, "runs/flux/image.png")
    touch(tmp_path, "WAN_single.png")

    assert names(tmp_path, name_filter="wan") == ["clip.mp4", "WAN_single.png"]
    assert names(tmp_path, name_filter="IMAGE") == ["image.png"]
    assert names(tmp_path, name_filter="runs/", path="runs") == []
    assert names(tmp_path, name_filter="flux/", path="runs") == ["image.png"]


@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        ("newest first", ["Zed.png", "beta.png", "alpha.png"]),
        ("oldest first", ["alpha.png", "beta.png", "Zed.png"]),
        ("name A to Z", ["alpha.png", "beta.png", "Zed.png"]),
        ("name Z to A", ["Zed.png", "beta.png", "alpha.png"]),
    ],
)
def test_sort_orders_by_mtime_or_case_folded_name(tmp_path, sort, expected):
    touch(tmp_path, "alpha.png", mtime=1_000)
    touch(tmp_path, "beta.png", mtime=2_000)
    touch(tmp_path, "Zed.png", mtime=3_000)

    assert names(tmp_path, sort=sort) == expected


def test_limit_slices_after_sorting(tmp_path):
    for index in range(5):
        touch(tmp_path, f"{index}.png", mtime=1_000 + index)

    result = listing(tmp_path, sort="newest first", limit=2)

    assert [item["filename"] for item in result["items"]] == ["4.png", "3.png"]
    assert result["scanned"] == 5
    assert result["truncated"] is False


def test_listing_echoes_the_normalized_root_and_root_relative_subfolders(tmp_path):
    touch(tmp_path, "runs/wan22/2026-10-30/clip.mp4", mtime=1_793_123_412.5)
    touch(tmp_path, "top.png")

    nested = listing(tmp_path, path="runs\\wan22")
    top = listing(tmp_path)

    assert nested["root"] == "runs/wan22"
    assert nested["items"] == [
        {
            "filename": "clip.mp4",
            "subfolder": "runs/wan22/2026-10-30",
            "kind": "video",
            "extension": "mp4",
            "size": 1,
            "mtime": pytest.approx(1_793_123_412.5),
        }
    ]
    assert top["root"] == ""
    assert next(item for item in top["items"] if item["filename"] == "top.png")[
        "subfolder"
    ] == ""


def test_listing_propagates_scan_cap_truncation(tmp_path, monkeypatch):
    import lfgg_nodes.output_gallery as module

    for index in range(4):
        touch(tmp_path, f"{index}.png")
    monkeypatch.setattr(module, "SCAN_CAP", 2)

    result = listing(tmp_path)

    assert result["scanned"] == 2
    assert result["truncated"] is True
    assert len(result["items"]) == 2


def test_listing_drops_files_that_vanish_before_stat(tmp_path, monkeypatch):
    touch(tmp_path, "gone.png")
    touch(tmp_path, "kept.png")
    original = os.stat

    def flaky_stat(path, *args, **kwargs):
        if str(path).endswith("gone.png"):
            raise FileNotFoundError(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", flaky_stat)

    assert names(tmp_path) == ["kept.png"]


def test_describe_item_uses_posix_separators_for_windows_relative_paths():
    item = describe_item(
        PureWindowsPath("runs\\wan22\\2026-10-30\\clip.MP4"),
        size=4_193_304,
        mtime=1_793_123_412.51,
    )

    assert item == {
        "filename": "clip.MP4",
        "subfolder": "runs/wan22/2026-10-30",
        "kind": "video",
        "extension": "mp4",
        "size": 4_193_304,
        "mtime": 1_793_123_412.51,
    }
    assert describe_item(PurePosixPath("song.FLAC"), size=2, mtime=1.0) == {
        "filename": "song.FLAC",
        "subfolder": "",
        "kind": "audio",
        "extension": "flac",
        "size": 2,
        "mtime": 1.0,
    }


# --------------------------------------------------------------------------
# Query parsing and the list route
# --------------------------------------------------------------------------


def test_parse_query_applies_defaults_and_ignores_unknown_parameters():
    assert parse_query({"unknown": "x"}) == {
        "path": "",
        "include_subfolders": True,
        "media_filter": "all",
        "name_filter": "",
        "sort": "newest first",
        "limit": DEFAULT_LIMIT,
    }
    assert parse_query(
        {
            "path": "runs",
            "include_subfolders": "false",
            "media_filter": "mp4",
            "name_filter": "Wan",
            "sort": "name Z to A",
            "limit": "7",
        }
    ) == {
        "path": "runs",
        "include_subfolders": False,
        "media_filter": "mp4",
        "name_filter": "Wan",
        "sort": "name Z to A",
        "limit": 7,
    }


@pytest.mark.parametrize(
    ("query", "message"),
    [
        ({"include_subfolders": "maybe"}, "include_subfolders must be true or false"),
        ({"include_subfolders": "TRUE"}, "include_subfolders must be true or false"),
        ({"media_filter": "exe"}, "media_filter must be one of"),
        ({"sort": "random"}, "sort must be one of"),
        ({"limit": "0"}, "limit must be an integer between 1 and 200"),
        ({"limit": "201"}, "limit must be an integer between 1 and 200"),
        ({"limit": "ten"}, "limit must be an integer between 1 and 200"),
        ({"limit": "1.5"}, "limit must be an integer between 1 and 200"),
        ({"name_filter": "x" * 257}, "name_filter must be at most 256"),
    ],
)
def test_parse_query_rejects_invalid_values(query, message):
    with pytest.raises(OutputGalleryError, match=message) as info:
        parse_query(query)

    assert info.value.status == 400


def test_list_route_returns_items_for_valid_queries(monkeypatch, tmp_path):
    touch(tmp_path, "runs/wan22/clip.mp4", mtime=2_000)
    touch(tmp_path, "runs/wan22/old.png", mtime=1_000)
    install_route_modules(monkeypatch, tmp_path)

    response = asyncio.run(
        output_gallery_list(
            FakeRequest({"path": "runs/wan22", "limit": "1", "ignored": "yes"})
        )
    )

    assert response.status == 200
    assert response.data["root"] == "runs/wan22"
    assert [item["filename"] for item in response.data["items"]] == ["clip.mp4"]
    assert response.data["scanned"] == 2
    assert response.data["truncated"] is False


@pytest.mark.parametrize(
    ("query", "status", "message"),
    [
        ({"path": "/absolute"}, 400, "path must stay inside the ComfyUI output root"),
        ({"path": "../x"}, 400, "path must stay inside the ComfyUI output root"),
        ({"path": "missing"}, 404, "folder not found under output: missing"),
        ({"include_subfolders": "1"}, 400, "include_subfolders must be true or false"),
        ({"media_filter": "exe"}, 400, "media_filter must be one of"),
        ({"sort": "random"}, 400, "sort must be one of"),
        ({"limit": "0"}, 400, "limit must be an integer between 1 and 200"),
    ],
)
def test_list_route_rejects_invalid_queries_with_json_errors(
    monkeypatch, tmp_path, query, status, message
):
    install_route_modules(monkeypatch, tmp_path)

    response = asyncio.run(output_gallery_list(FakeRequest(query)))

    assert response.status == status
    assert set(response.data) == {"error"}
    assert response.data["error"].startswith("LFGG Output Gallery: ")
    assert message in response.data["error"]
    assert str(tmp_path) not in response.data["error"]


def test_list_route_reports_an_unavailable_output_root_as_500(
    monkeypatch, tmp_path
):
    install_route_modules(monkeypatch, tmp_path / "missing")

    response = asyncio.run(output_gallery_list(FakeRequest({})))

    assert response.status == 500
    assert response.data == {
        "error": "LFGG Output Gallery: ComfyUI output root is unavailable"
    }


def test_list_route_runs_the_scan_off_the_event_loop(monkeypatch, tmp_path):
    touch(tmp_path, "a.png")
    install_route_modules(monkeypatch, tmp_path)
    import lfgg_nodes.output_gallery as module

    threads = []
    original = module.list_gallery

    def record(*args, **kwargs):
        import threading

        threads.append(threading.current_thread())
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "list_gallery", record)

    async def run():
        import threading

        response = await output_gallery_list(FakeRequest({}))
        return response, threading.current_thread()

    response, loop_thread = asyncio.run(run())

    assert response.status == 200
    assert threads and threads[0] is not loop_thread


def test_list_route_registers_as_namespaced_get(monkeypatch):
    registered = []
    routes = SimpleNamespace(
        get=lambda path: lambda handler: registered.append((path, handler))
    )
    server = ModuleType("server")
    server.PromptServer = SimpleNamespace(instance=SimpleNamespace(routes=routes))
    monkeypatch.setitem(sys.modules, "server", server)
    import lfgg_nodes.output_gallery as module

    importlib.reload(module)

    assert registered == [
        ("/lfgg/v1/output-gallery/list", module.output_gallery_list)
    ]


def test_module_import_is_side_effect_free_without_comfyui(monkeypatch):
    monkeypatch.delitem(sys.modules, "server", raising=False)
    monkeypatch.delitem(sys.modules, "folder_paths", raising=False)
    monkeypatch.delitem(sys.modules, "lfgg_nodes.output_gallery", raising=False)

    module = importlib.import_module("lfgg_nodes.output_gallery")

    assert "folder_paths" not in sys.modules
    assert "server" not in sys.modules
    assert module.OutputGallery.OUTPUT_NODE is False


# --------------------------------------------------------------------------
# Node
# --------------------------------------------------------------------------


def test_node_is_a_pure_viewer_with_no_outputs():
    assert OutputGallery.RETURN_TYPES == ()
    assert OutputGallery.RETURN_NAMES == ()
    assert OutputGallery.OUTPUT_TOOLTIPS == ()
    assert OutputGallery.OUTPUT_NODE is False
    assert OutputGallery.FUNCTION == "show"
    assert OutputGallery.CATEGORY == "LFGG/workflow"
    assert (
        OutputGallery().show(
            path="",
            include_subfolders=True,
            media_filter="all",
            name_filter="",
            sort="newest first",
            limit=24,
        )
        == ()
    )
