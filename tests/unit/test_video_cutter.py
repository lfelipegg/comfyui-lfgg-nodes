import asyncio
import importlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


class FakeVideo:
    def __init__(
        self,
        *,
        duration=10.0,
        fps=30,
        frames=300,
        dimensions=(640, 360),
        trimmed=None,
    ):
        self.duration = duration
        self.fps = Fraction(fps)
        self.frames = frames
        self.dimensions = dimensions
        self.trimmed = object() if trimmed is None else trimmed
        self.trim_calls = []
        self.save_calls = 0

    def get_duration(self):
        return self.duration

    def get_frame_rate(self):
        return self.fps

    def get_frame_count(self):
        return self.frames

    def get_dimensions(self):
        return self.dimensions

    def as_trimmed(self, start_time, duration, strict_duration=False):
        self.trim_calls.append((start_time, duration, strict_duration))
        return self.trimmed

    def save_to(self, destination, **_options):
        self.save_calls += 1
        destination.write(b"bounded mp4 preview")


def execute(video, **selection):
    from lfgg_nodes.video_cutter import VideoCutter

    values = {
        "selection_mode": "Time",
        "start_time": 0.0,
        "end_time": -1.0,
        "first_frame": 0,
        "last_frame": -1,
    }
    values.update(selection)
    return VideoCutter().cut(video=video, **values)


def test_time_selection_snaps_to_reported_fps_and_trims_end_exclusively():
    video = FakeVideo()

    result = execute(video, start_time=1.017, end_time=2.01)

    assert result["result"] == (video.trimmed,)
    assert len(video.trim_calls) == 1
    start, duration, strict = video.trim_calls[0]
    assert start == pytest.approx(31 / 30)
    assert duration == pytest.approx(29 / 30)
    assert strict is True


def test_frame_selection_is_zero_based_and_inclusive():
    video = FakeVideo()

    result = execute(
        video,
        selection_mode="Frames",
        first_frame=15,
        last_frame=44,
    )

    assert result["result"] == (video.trimmed,)
    assert video.trim_calls == [(0.5, 1.0, True)]


def test_explicit_final_frame_is_exact_source_end_and_whole_range_identity():
    video = FakeVideo(duration=10.01, fps=30, frames=300)

    result = execute(
        video,
        selection_mode="Frames",
        first_frame=0,
        last_frame=299,
    )

    assert result["result"] == (video,)
    assert video.trim_calls == []
    assert result["ui"]["video_cutter"][0]["selection_end"] == 10.01


def test_explicit_exact_duration_is_source_end_before_nominal_snapping():
    video = FakeVideo(duration=10.01, fps=30, frames=300)

    result = execute(video, start_time=0, end_time=10.01)

    assert result["result"] == (video,)
    assert video.trim_calls == []
    assert result["ui"]["video_cutter"][0]["selection_end"] == 10.01


def test_vfr_frame_mapping_rejects_an_end_not_after_the_start():
    video = FakeVideo(duration=0.5, fps=30, frames=100)

    with pytest.raises(ValueError, match="frame range must end after it starts"):
        execute(
            video,
            selection_mode="Frames",
            first_frame=20,
            last_frame=99,
        )

    assert video.trim_calls == []


@pytest.mark.parametrize(
    ("selection", "message"),
    [
        ({"start_time": -0.01}, "start_time must be non-negative"),
        ({"start_time": 2.0, "end_time": 1.0}, "end_time must be after start_time"),
        ({"end_time": 10.1}, "end_time exceeds the source duration"),
        (
            {"selection_mode": "Frames", "first_frame": -1},
            "first_frame must be non-negative",
        ),
        (
            {"selection_mode": "Frames", "first_frame": 20, "last_frame": 19},
            "last_frame must not be before first_frame",
        ),
        (
            {"selection_mode": "Frames", "last_frame": 300},
            "last_frame exceeds the source frame range",
        ),
    ],
)
def test_invalid_selections_fail_without_clamping(selection, message):
    video = FakeVideo()

    with pytest.raises(ValueError, match=message):
        execute(video, **selection)

    assert video.trim_calls == []


@pytest.mark.parametrize("selection_mode", ["Time", "Frames"])
def test_whole_range_is_a_no_op_that_returns_the_original(selection_mode):
    video = FakeVideo()

    result = execute(video, selection_mode=selection_mode)

    assert result["result"] == (video,)
    assert video.trim_calls == []


def test_native_trim_rejection_is_actionable():
    video = FakeVideo(trimmed=False)

    with pytest.raises(ValueError, match="native video trim rejected"):
        execute(video, end_time=1.0)


def install_preview_modules(monkeypatch, temp_directory):
    comfy_api = ModuleType("comfy_api")
    util = ModuleType("comfy_api.util")
    util.VideoContainer = SimpleNamespace(MP4="mp4")
    util.VideoCodec = SimpleNamespace(H264="h264")
    monkeypatch.setitem(sys.modules, "comfy_api", comfy_api)
    monkeypatch.setitem(sys.modules, "comfy_api.util", util)
    monkeypatch.setitem(
        sys.modules,
        "folder_paths",
        SimpleNamespace(get_temp_directory=lambda: str(temp_directory)),
    )


def test_preview_uses_the_standard_video_descriptor_and_cache(monkeypatch, tmp_path):
    install_preview_modules(monkeypatch, tmp_path)
    video = FakeVideo()

    first = execute(video)
    second = execute(video)

    descriptor = first["ui"]["images"][0]
    assert first["ui"] == {
        "images": [descriptor],
        "animated": (True,),
        "video_cutter": [
            {
                "duration": 10.0,
                "reported_fps": 30.0,
                "nominal_frame_count": 300,
                "selection_start": 0.0,
                "selection_end": 10.0,
            }
        ],
    }
    assert second["ui"] == first["ui"]
    assert descriptor == {
        "filename": descriptor["filename"],
        "subfolder": "",
        "type": "temp",
    }
    assert Path(descriptor["filename"]).name == descriptor["filename"]
    assert (tmp_path / descriptor["filename"]).read_bytes() == b"bounded mp4 preview"
    assert video.save_calls == 1


def test_preview_cache_evicts_old_files(monkeypatch, tmp_path):
    install_preview_modules(monkeypatch, tmp_path)

    for _ in range(9):
        execute(FakeVideo())

    assert len(list(tmp_path.glob("lfgg_video_cutter_*.mp4"))) == 8


def test_preview_cache_serializes_duplicate_concurrent_encodes(monkeypatch, tmp_path):
    install_preview_modules(monkeypatch, tmp_path)
    video = FakeVideo()

    def slow_save(destination, **_options):
        video.save_calls += 1
        time.sleep(0.02)
        destination.write(b"bounded mp4 preview")

    video.save_to = slow_save
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _index: execute(video), range(4)))

    assert video.save_calls == 1
    assert len(list(tmp_path.glob("lfgg_video_cutter_*.mp4"))) == 1
    assert len({result["ui"]["images"][0]["filename"] for result in results}) == 1


def test_preview_failure_warns_without_losing_the_video(monkeypatch, tmp_path):
    install_preview_modules(monkeypatch, tmp_path)
    video = FakeVideo()
    video.save_to = lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("boom"))

    result = execute(video)

    assert result["result"] == (video,)
    assert result["ui"] == {
        "text": ["LFGG Video Cutter preview unavailable; the VIDEO output is valid."],
        "video_cutter": [
            {
                "duration": 10.0,
                "reported_fps": 30.0,
                "nominal_frame_count": 300,
                "selection_start": 0.0,
                "selection_end": 10.0,
            }
        ],
    }
    assert list(tmp_path.iterdir()) == []


def test_preview_byte_limit_warns_without_writing_a_partial_file(
    monkeypatch, tmp_path
):
    install_preview_modules(monkeypatch, tmp_path)
    video = FakeVideo()

    def oversized(destination, **_options):
        chunk = b"x" * (1024 * 1024)
        for _ in range(17):
            destination.write(chunk)

    video.save_to = oversized

    result = execute(video)

    assert result["result"] == (video,)
    assert "preview unavailable" in result["ui"]["text"][0]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "video",
    [
        FakeVideo(duration=31, fps=10, frames=310),
        FakeVideo(duration=30, fps=31, frames=930),
        FakeVideo(duration=1, fps=30, frames=30, dimensions=(1921, 1080)),
    ],
)
def test_preview_work_limits_warn_before_encoding(monkeypatch, tmp_path, video):
    install_preview_modules(monkeypatch, tmp_path)

    result = execute(video)

    assert result["result"] == (video,)
    assert "preview unavailable" in result["ui"]["text"][0]
    assert video.save_calls == 0
    assert list(tmp_path.iterdir()) == []


class FakeRequest:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode()
        self.content_length = len(self.body)
        self.content = self

    async def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]


class RawRequest:
    def __init__(self, body, content_length=None):
        self.body = body
        self.content_length = len(body) if content_length is None else content_length
        self.content = self

    async def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]


class StreamingRequest:
    content_length = None

    def __init__(self, body):
        self.body = body
        self.read_size = None
        self.content = self

    async def read(self, size):
        self.read_size = size
        return self.body[:size]


def install_metadata_modules(monkeypatch, input_root):
    monkeypatch.setitem(
        sys.modules,
        "folder_paths",
        SimpleNamespace(
            get_input_directory=lambda: str(input_root),
            get_annotated_filepath=lambda name: str(input_root / name),
        ),
    )
    stream = SimpleNamespace(
        average_rate=Fraction(30_000, 1_001),
        frames=300,
        duration=10_010,
        time_base=Fraction(1, 1_000),
    )
    class Container:
        streams = SimpleNamespace(video=[stream])
        duration = 10_010_000

        def decode(self, *_args):
            raise AssertionError("decoded video")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    container = Container()
    av = ModuleType("av")
    av.time_base = 1_000_000
    av.open = lambda _source, mode="r", **_options: container
    monkeypatch.setitem(sys.modules, "av", av)
    aiohttp = ModuleType("aiohttp")
    aiohttp.web = SimpleNamespace(
        json_response=lambda data, status=200: SimpleNamespace(status=status, data=data)
    )
    monkeypatch.setitem(sys.modules, "aiohttp", aiohttp)


def test_metadata_endpoint_is_bounded_and_does_not_decode(monkeypatch, tmp_path):
    (tmp_path / "source.mp4").write_bytes(b"video")
    install_metadata_modules(monkeypatch, tmp_path)
    from lfgg_nodes.video_cutter import video_metadata

    response = asyncio.run(video_metadata(FakeRequest({"input": "source.mp4"})))

    assert response.status == 200
    assert response.data == {
        "duration": pytest.approx(10.01),
        "reported_fps": pytest.approx(30_000 / 1_001),
        "nominal_frame_count": 300,
    }


def test_metadata_endpoint_rejects_playlist_before_pyav(monkeypatch, tmp_path):
    (tmp_path / "source.m3u8").write_text("https://example.invalid/segment.ts")
    install_metadata_modules(monkeypatch, tmp_path)
    sys.modules["av"].open = lambda *_args, **_kwargs: pytest.fail(
        "playlist reached PyAV"
    )
    from lfgg_nodes.video_cutter import video_metadata

    response = asyncio.run(video_metadata(FakeRequest({"input": "source.m3u8"})))

    assert response.status == 400
    assert response.data == {"error": "selected video format is unsupported"}


def test_metadata_endpoint_forces_safe_demuxer_options(monkeypatch, tmp_path):
    (tmp_path / "source.mp4").write_bytes(b"video")
    install_metadata_modules(monkeypatch, tmp_path)
    av = sys.modules["av"]
    original_open = av.open
    calls = []

    def recording_open(source, **options):
        calls.append(options)
        return original_open(source, mode=options["mode"])

    av.open = recording_open
    from lfgg_nodes.video_cutter import video_metadata

    response = asyncio.run(video_metadata(FakeRequest({"input": "source.mp4"})))

    assert response.status == 200
    assert calls == [
        {
            "mode": "r",
            "format": "mov",
            "options": {"protocol_whitelist": "pipe"},
        }
    ]


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        ({"input": "../outside.mp4"}, 400),
        ({"input": ""}, 400),
        ({"input": 7}, 400),
        ({"input": "\ud800"}, 400),
        ({"input": "a" * 1025}, 413),
        ({"input": "missing.mp4", "extra": True}, 400),
    ],
)
def test_metadata_endpoint_rejects_untrusted_identifiers(
    monkeypatch, tmp_path, payload, status
):
    install_metadata_modules(monkeypatch, tmp_path)
    from lfgg_nodes.video_cutter import video_metadata

    response = asyncio.run(video_metadata(FakeRequest(payload)))

    assert response.status == status
    assert set(response.data) == {"error"}


@pytest.mark.parametrize(
    ("fake_request", "status"),
    [
        (RawRequest(b"not-json"), 400),
        (RawRequest(b"{}", content_length=2049), 413),
    ],
)
def test_metadata_endpoint_rejects_malformed_or_oversized_bodies(
    monkeypatch, tmp_path, fake_request, status
):
    install_metadata_modules(monkeypatch, tmp_path)
    from lfgg_nodes.video_cutter import video_metadata

    response = asyncio.run(video_metadata(fake_request))

    assert response.status == status
    assert set(response.data) == {"error"}


def test_metadata_endpoint_caps_streaming_reads_without_content_length(
    monkeypatch, tmp_path
):
    install_metadata_modules(monkeypatch, tmp_path)
    from lfgg_nodes.video_cutter import METADATA_REQUEST_MAX_BYTES, video_metadata

    request = StreamingRequest(b"x" * (METADATA_REQUEST_MAX_BYTES + 100))
    response = asyncio.run(video_metadata(request))

    assert request.read_size == METADATA_REQUEST_MAX_BYTES + 1
    assert response.status == 413
    assert response.data == {"error": "request body is too large"}


def test_metadata_endpoint_bounds_reported_values(monkeypatch, tmp_path):
    (tmp_path / "source.mp4").write_bytes(b"video")
    install_metadata_modules(monkeypatch, tmp_path)
    sys.modules["av"].open(None).streams.video[0].average_rate = Fraction(1001)
    from lfgg_nodes.video_cutter import video_metadata

    response = asyncio.run(video_metadata(FakeRequest({"input": "source.mp4"})))

    assert response.status == 400
    assert response.data == {
        "error": "selected video metadata exceeds supported bounds"
    }


def test_metadata_route_registers_as_namespaced_post(monkeypatch):
    routes = SimpleNamespace(
        post=lambda path: lambda handler: registered.append((path, handler))
    )
    registered = []
    server = ModuleType("server")
    server.PromptServer = SimpleNamespace(instance=SimpleNamespace(routes=routes))
    monkeypatch.setitem(sys.modules, "server", server)
    import lfgg_nodes.video_cutter as module

    importlib.reload(module)

    assert registered == [("/lfgg/v1/video-metadata", module.video_metadata)]
