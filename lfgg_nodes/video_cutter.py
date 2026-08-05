from collections import OrderedDict
from fractions import Fraction
from io import BytesIO
from math import ceil, floor, isfinite
from pathlib import Path
from threading import Lock
from uuid import uuid4

from .load_and_crop_image import _input_path, _open_input_file

PREVIEW_MAX_BYTES = 16 * 1024 * 1024
PREVIEW_CACHE_ENTRIES = 8
PREVIEW_MAX_DURATION_SECONDS = 30
PREVIEW_MAX_FRAMES = 900
PREVIEW_MAX_PIXELS = 1920 * 1080
METADATA_REQUEST_MAX_BYTES = 2 * 1024
METADATA_IDENTIFIER_MAX_BYTES = 1024
METADATA_MAX_DURATION_SECONDS = 24 * 60 * 60
METADATA_MAX_FPS = 1000
METADATA_MAX_FRAMES = 10_000_000
_VIDEO_DEMUXERS = {
    ".avi": "avi",
    ".m4v": "mov",
    ".mkv": "matroska",
    ".mov": "mov",
    ".mp4": "mov",
    ".webm": "matroska",
}
_preview_cache = OrderedDict()
_preview_lock = Lock()


class _BoundedBuffer(BytesIO):
    def write(self, data):
        if self.tell() + len(data) > PREVIEW_MAX_BYTES:
            raise ValueError("preview exceeds its byte limit")
        return super().write(data)


def _validate_preview_work(video, duration, fps):
    if duration <= 0 or duration > PREVIEW_MAX_DURATION_SECONDS:
        raise ValueError("preview duration exceeds its work limit")
    if ceil(duration * float(fps)) > PREVIEW_MAX_FRAMES:
        raise ValueError("preview frame count exceeds its work limit")
    dimensions = video.get_dimensions()
    if (
        not isinstance(dimensions, (tuple, list))
        or len(dimensions) != 2
        or any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in dimensions
        )
    ):
        raise ValueError("preview dimensions are unavailable")
    width, height = dimensions
    if width <= 0 or height <= 0 or width * height > PREVIEW_MAX_PIXELS:
        raise ValueError("preview pixel count exceeds its work limit")


def _preview_ui_unlocked(video, source, start, end, fps):
    import folder_paths
    from comfy_api.util import VideoCodec, VideoContainer

    root = Path(folder_paths.get_temp_directory()).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("ComfyUI temporary directory is unavailable")
    key = (str(root), id(source), start, end)
    cached = _preview_cache.pop(key, None)
    if cached is not None and cached[0] is source and cached[1].is_file():
        _preview_cache[key] = cached
        return {"images": [cached[2]], "animated": (True,)}

    _validate_preview_work(video, end - start, fps)
    buffer = _BoundedBuffer()
    video.save_to(
        buffer,
        format=VideoContainer.MP4,
        codec=VideoCodec.H264,
    )
    data = buffer.getvalue()
    if not data:
        raise ValueError("preview encoder returned no data")

    filename = f"lfgg_video_cutter_{uuid4().hex}.mp4"
    path = root / filename
    try:
        with path.open("xb") as output:
            output.write(data)
        if len(_preview_cache) >= PREVIEW_CACHE_ENTRIES:
            old_key, old_entry = _preview_cache.popitem(last=False)
            try:
                old_entry[1].unlink(missing_ok=True)
            except OSError:
                _preview_cache[old_key] = old_entry
                path.unlink(missing_ok=True)
                raise
    except Exception:
        path.unlink(missing_ok=True)
        raise
    descriptor = {"filename": filename, "subfolder": "", "type": "temp"}
    _preview_cache[key] = (source, path, descriptor)
    return {"images": [descriptor], "animated": (True,)}


def _preview_ui(video, source, start, end, fps):
    # ponytail: one global encoder lock; use per-key locks if throughput matters.
    with _preview_lock:
        return _preview_ui_unlocked(video, source, start, end, fps)


async def video_metadata(request):
    import json

    from aiohttp import web

    if (
        request.content_length is not None
        and request.content_length > METADATA_REQUEST_MAX_BYTES
    ):
        return web.json_response({"error": "request body is too large"}, status=413)
    try:
        body = await request.content.read(METADATA_REQUEST_MAX_BYTES + 1)
    except Exception:
        return web.json_response(
            {"error": "request body could not be read"}, status=400
        )
    if len(body) > METADATA_REQUEST_MAX_BYTES:
        return web.json_response({"error": "request body is too large"}, status=413)
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return web.json_response({"error": "request body must be JSON"}, status=400)
    if not isinstance(payload, dict) or set(payload) != {"input"}:
        return web.json_response(
            {"error": "request body must contain only input"}, status=400
        )
    identifier = payload["input"]
    if not isinstance(identifier, str) or not identifier:
        return web.json_response(
            {"error": "input must be a non-empty string"}, status=400
        )
    try:
        identifier_size = len(identifier.encode("utf-8"))
    except UnicodeEncodeError:
        return web.json_response({"error": "input identifier is invalid"}, status=400)
    if identifier_size > METADATA_IDENTIFIER_MAX_BYTES:
        return web.json_response({"error": "input identifier is too long"}, status=413)

    try:
        _, resolved_path = _input_path(identifier, label="video")
    except ValueError:
        return web.json_response(
            {"error": "selected video metadata is unavailable"}, status=400
        )
    demuxer = _VIDEO_DEMUXERS.get(resolved_path.suffix.lower())
    if demuxer is None:
        return web.json_response(
            {"error": "selected video format is unsupported"}, status=400
        )

    try:
        import av

        with _open_input_file(identifier, label="video") as source, av.open(
            source,
            mode="r",
            format=demuxer,
            options={"protocol_whitelist": "pipe"},
        ) as container:
            if not container.streams.video:
                raise ValueError("video stream is missing")
            stream = container.streams.video[0]
            if not stream.average_rate:
                raise ValueError("reported FPS is missing")
            fps = float(stream.average_rate)
            if stream.duration is not None and stream.time_base is not None:
                duration = float(stream.duration * stream.time_base)
            elif container.duration is not None:
                duration = float(container.duration / av.time_base)
            elif stream.frames:
                duration = float(stream.frames / stream.average_rate)
            else:
                raise ValueError("duration is missing")
            frame_count = (
                int(stream.frames)
                if stream.frames
                else int(floor(duration * fps + 0.5))
            )
    except Exception:
        return web.json_response(
            {"error": "selected video metadata is unavailable"}, status=400
        )
    if (
        not isfinite(duration)
        or duration <= 0
        or duration > METADATA_MAX_DURATION_SECONDS
        or not isfinite(fps)
        or fps <= 0
        or fps > METADATA_MAX_FPS
        or frame_count < 1
        or frame_count > METADATA_MAX_FRAMES
    ):
        return web.json_response(
            {"error": "selected video metadata exceeds supported bounds"}, status=400
        )
    return web.json_response(
        {
            "duration": duration,
            "reported_fps": fps,
            "nominal_frame_count": frame_count,
        }
    )


def _source_bounds(video):
    required = ("get_duration", "get_frame_rate", "get_frame_count", "as_trimmed")
    if any(not callable(getattr(video, name, None)) for name in required):
        raise ValueError("video must be a ComfyUI VIDEO value")
    try:
        duration = float(video.get_duration())
        fps = Fraction(video.get_frame_rate())
        frame_count = int(video.get_frame_count())
    except (ArithmeticError, TypeError, ValueError, ZeroDivisionError):
        raise ValueError("source video metadata is unavailable") from None
    if not isfinite(duration) or duration <= 0:
        raise ValueError("source video duration must be positive and finite")
    if fps <= 0 or not isfinite(float(fps)):
        raise ValueError("source video reported FPS must be positive and finite")
    if frame_count < 1:
        raise ValueError("source video must contain at least one frame")
    return duration, fps, frame_count


def _number(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    value = float(value)
    if not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return value


def _frame(name, value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _snap(value, fps):
    return float(Fraction(floor(value * float(fps) + 0.5), 1) / fps)


class VideoCutter:
    CATEGORY = "LFGG/video"
    DESCRIPTION = (
        "Selects one frame-aligned segment from a ComfyUI video while keeping "
        "its primary video and audio synchronized."
    )
    FUNCTION = "cut"
    RETURN_TYPES = ("VIDEO",)
    RETURN_NAMES = ("video",)
    OUTPUT_TOOLTIPS = ("Selected contiguous video segment.",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("VIDEO", {"tooltip": "Source ComfyUI video."}),
                "selection_mode": (
                    "COMBO",
                    {
                        "options": ["Time", "Frames"],
                        "default": "Time",
                        "tooltip": "Representation used to select the segment.",
                    },
                ),
                "start_time": (
                    "FLOAT",
                    {
                        "default": 0.0,
                        "min": -1.0,
                        "max": 1_000_000_000.0,
                        "step": 0.001,
                        "tooltip": "Inclusive start in seconds.",
                    },
                ),
                "end_time": (
                    "FLOAT",
                    {
                        "default": -1.0,
                        "min": -1.0,
                        "max": 1_000_000_000.0,
                        "step": 0.001,
                        "tooltip": "Exclusive end in seconds, or -1 for source end.",
                    },
                ),
                "first_frame": (
                    "INT",
                    {
                        "default": 0,
                        "min": -1,
                        "max": 2_147_483_647,
                        "tooltip": "Inclusive zero-based first frame index.",
                    },
                ),
                "last_frame": (
                    "INT",
                    {
                        "default": -1,
                        "min": -1,
                        "max": 2_147_483_647,
                        "tooltip": (
                            "Inclusive zero-based last frame index, or -1 for "
                            "source end."
                        ),
                    },
                ),
            }
        }

    def cut(
        self,
        video,
        selection_mode,
        start_time,
        end_time,
        first_frame,
        last_frame,
    ):
        duration, fps, frame_count = _source_bounds(video)
        if selection_mode == "Time":
            start = _number("start_time", start_time)
            end = _number("end_time", end_time)
            if start < 0:
                raise ValueError("start_time must be non-negative")
            if end < 0 and end != -1:
                raise ValueError("end_time must be -1 or non-negative")
            if start >= duration:
                raise ValueError("start_time exceeds the source duration")
            if end != -1 and end > duration:
                raise ValueError("end_time exceeds the source duration")
            start = _snap(start, fps)
            end = duration if end == -1 or end == duration else _snap(end, fps)
            if start >= duration:
                raise ValueError(
                    "start_time exceeds the source duration after snapping"
                )
            if end > duration:
                raise ValueError("end_time exceeds the source duration after snapping")
            if end <= start:
                raise ValueError(
                    "end_time must be after start_time by at least one frame"
                )
        elif selection_mode == "Frames":
            first = _frame("first_frame", first_frame)
            last = _frame("last_frame", last_frame)
            if first < 0:
                raise ValueError("first_frame must be non-negative")
            if last < 0 and last != -1:
                raise ValueError("last_frame must be -1 or non-negative")
            if first >= frame_count:
                raise ValueError("first_frame exceeds the source frame range")
            if last != -1 and last >= frame_count:
                raise ValueError("last_frame exceeds the source frame range")
            if last != -1 and last < first:
                raise ValueError("last_frame must not be before first_frame")
            start = float(Fraction(first, 1) / fps)
            end = (
                duration
                if last == -1 or last == frame_count - 1
                else float(Fraction(last + 1, 1) / fps)
            )
            if end > duration:
                raise ValueError("last_frame exceeds the source duration")
            if end <= start:
                raise ValueError("selected frame range must end after it starts")
        else:
            raise ValueError("selection_mode must be Time or Frames")

        selected = video
        if start != 0 or end != duration:
            selected = video.as_trimmed(start, end - start, strict_duration=True)
            if selected is None or selected is False:
                raise ValueError("native video trim rejected the selected segment")
        try:
            ui = _preview_ui(selected, video, start, end, fps)
        except Exception:
            ui = {
                "text": [
                    "LFGG Video Cutter preview unavailable; the VIDEO output is valid."
                ]
            }
        ui["video_cutter"] = [
            {
                "duration": duration,
                "reported_fps": float(fps),
                "nominal_frame_count": frame_count,
                "selection_start": start,
                "selection_end": end,
            }
        ]
        return {"ui": ui, "result": (selected,)}


try:
    from server import PromptServer
except ModuleNotFoundError as error:
    if error.name != "server":
        raise
else:
    PromptServer.instance.routes.post("/lfgg/v1/video-metadata")(video_metadata)


__all__ = ["VideoCutter", "video_metadata"]
