from math import gcd

from .sizing import _bounded_int

MAX_IMAGE_PIXELS = 16_384**2
_WINDOWS_FILE_ATTRIBUTE_DIRECTORY = 0x10
_WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_WINDOWS_FILE_TYPE_DISK = 1


def _input_path(image, *, label="image"):
    from pathlib import Path, PureWindowsPath

    import folder_paths

    if not isinstance(image, str):
        raise ValueError(f"selected {label} identifier must be a string")
    if not image or "\x00" in image:
        raise ValueError(f"selected {label} identifier must be a non-empty string")
    if Path(image).is_absolute() or PureWindowsPath(image).is_absolute():
        raise ValueError(f"selected {label} identifier must be relative")
    try:
        root = Path(folder_paths.get_input_directory()).resolve(strict=True)
        path = Path(folder_paths.get_annotated_filepath(image)).resolve(strict=True)
    except (OSError, TypeError, ValueError):
        raise ValueError(f"selected {label} is unavailable") from None
    if not root.is_dir() or not path.is_file() or not path.is_relative_to(root):
        raise ValueError(
            f"selected {label} must stay inside the ComfyUI input directory"
        )
    return root, path


def _open_windows_handle(path):
    import ctypes
    import msvcrt
    import os
    from ctypes import wintypes

    class FileAttributeTagInfo(ctypes.Structure):
        _fields_ = (
            ("file_attributes", wintypes.DWORD),
            ("reparse_tag", wintypes.DWORD),
        )

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    get_attributes = kernel32.GetFileInformationByHandleEx
    get_attributes.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    get_attributes.restype = wintypes.BOOL
    get_file_type = kernel32.GetFileType
    get_file_type.argtypes = (wintypes.HANDLE,)
    get_file_type.restype = wintypes.DWORD
    get_final_path = kernel32.GetFinalPathNameByHandleW
    get_final_path.argtypes = (
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    )
    get_final_path.restype = wintypes.DWORD
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    handle = create_file(
        str(path),
        0x80000000,  # GENERIC_READ
        0x7,  # FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE
        None,
        3,  # OPEN_EXISTING
        0x00200000,  # FILE_FLAG_OPEN_REPARSE_POINT
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        information = FileAttributeTagInfo()
        if not get_attributes(
            handle,
            9,  # FileAttributeTagInfo
            ctypes.byref(information),
            ctypes.sizeof(information),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        file_type = get_file_type(handle)
        buffer = ctypes.create_unicode_buffer(32_768)
        length = get_final_path(handle, buffer, len(buffer), 0)
        if length == 0:
            raise ctypes.WinError(ctypes.get_last_error())
        if length >= len(buffer):
            raise OSError("opened image path exceeds the Windows path limit")

        descriptor = msvcrt.open_osfhandle(
            handle,
            os.O_RDONLY | os.O_BINARY | os.O_NOINHERIT,
        )
        handle = None
        try:
            source = os.fdopen(descriptor, "rb")
        except Exception:
            os.close(descriptor)
            raise
        return source, buffer.value, information.file_attributes, file_type
    finally:
        if handle is not None:
            close_handle(handle)


def _open_windows_input_file(root, path, *, label="image"):
    from pathlib import PureWindowsPath

    try:
        source, final_path, attributes, file_type = _open_windows_handle(path)
    except (AttributeError, OSError):
        raise ValueError(
            f"selected {label} could not be opened securely inside the "
            "ComfyUI input directory"
        ) from None

    if final_path.startswith("\\\\?\\UNC\\"):
        final_path = "\\\\" + final_path[8:]
    elif final_path.startswith("\\\\?\\"):
        final_path = final_path[4:]
    opened_path = PureWindowsPath(final_path)
    input_root = PureWindowsPath(root)
    unsafe = (
        attributes & _WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT
        or attributes & _WINDOWS_FILE_ATTRIBUTE_DIRECTORY
        or file_type != _WINDOWS_FILE_TYPE_DISK
        or not opened_path.is_relative_to(input_root)
    )
    if unsafe:
        source.close()
        raise ValueError(
            f"selected {label} could not be opened securely inside the "
            "ComfyUI input directory"
        )
    return source


def _open_input_file(image, *, label="image"):
    import os
    import stat

    root, path = (
        _input_path(image)
        if label == "image"
        else _input_path(image, label=label)
    )
    if os.name == "nt":
        return (
            _open_windows_input_file(root, path)
            if label == "image"
            else _open_windows_input_file(root, path, label=label)
        )
    if (
        not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_DIRECTORY")
        or os.open not in os.supports_dir_fd
    ):
        raise ValueError(
            f"secure selected-{label} access is unavailable on this platform"
        )

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_BINARY", 0)
    directory_fd = None
    file_fd = None
    try:
        directory_fd = os.open(root, directory_flags)
        parts = path.relative_to(root).parts
        for part in parts[:-1]:
            next_fd = os.open(part, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        file_fd = os.open(parts[-1], file_flags, dir_fd=directory_fd)
        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
            raise OSError("selected input is not a regular file")
        source = os.fdopen(file_fd, "rb")
        file_fd = None
        return source
    except OSError:
        raise ValueError(
            f"selected {label} changed or left the ComfyUI input directory "
            "before access"
        ) from None
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory_fd is not None:
            os.close(directory_fd)


def _content_hash(image):
    from hashlib import sha256

    digest = sha256()
    with _open_input_file(image) as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _largest_centered_crop(source_width, source_height, ratio_width, ratio_height):
    scale = min(source_width // ratio_width, source_height // ratio_height)
    if scale < 1:
        raise ValueError("crop ratio does not fit inside the source image")
    width = scale * ratio_width
    height = scale * ratio_height
    return (
        (source_width - width) // 2,
        (source_height - height) // 2,
        width,
        height,
    )


def resolve_crop(
    *,
    source_width,
    source_height,
    ratio_width,
    ratio_height,
    crop_x,
    crop_y,
    crop_width,
    crop_height,
    max_resolution,
):
    _bounded_int("source_width", source_width, 1, max_resolution)
    _bounded_int("source_height", source_height, 1, max_resolution)
    _bounded_int("ratio_width", ratio_width, 1, max_resolution)
    _bounded_int("ratio_height", ratio_height, 1, max_resolution)
    _bounded_int("crop_x", crop_x, 0, max_resolution)
    _bounded_int("crop_y", crop_y, 0, max_resolution)
    _bounded_int("crop_width", crop_width, 0, max_resolution)
    _bounded_int("crop_height", crop_height, 0, max_resolution)

    divisor = gcd(ratio_width, ratio_height)
    reduced_width = ratio_width // divisor
    reduced_height = ratio_height // divisor
    largest = _largest_centered_crop(
        source_width,
        source_height,
        reduced_width,
        reduced_height,
    )

    if crop_width == crop_height == 0:
        return (*largest, reduced_width, reduced_height)
    if crop_width < 1 or crop_height < 1:
        raise ValueError("crop dimensions must both be zero or both be positive")
    if crop_width * reduced_height != crop_height * reduced_width:
        return (*largest, reduced_width, reduced_height)
    if crop_x + crop_width > source_width or crop_y + crop_height > source_height:
        raise ValueError("crop rectangle must stay inside the source image")
    return (
        crop_x,
        crop_y,
        crop_width,
        crop_height,
        reduced_width,
        reduced_height,
    )


class LoadAndCropImage:
    CATEGORY = "LFGG/image"
    DESCRIPTION = (
        "Loads one still image from the ComfyUI input directory and crops it "
        "without resampling."
    )
    FUNCTION = "load_and_crop"
    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "mask")
    OUTPUT_TOOLTIPS = (
        "Selected source region without resampling.",
        "Alpha-derived mask cropped to the same region.",
    )

    @classmethod
    def INPUT_TYPES(cls):
        from pathlib import Path

        import folder_paths
        from nodes import MAX_RESOLUTION

        root = Path(folder_paths.get_input_directory()).resolve()
        images = sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and path.resolve().is_relative_to(root)
        )
        return {
            "required": {
                "image": (
                    "COMBO",
                    {
                        "options": images,
                        "image_upload": True,
                        "allow_batch": False,
                        "tooltip": "Still image beneath the ComfyUI input directory.",
                    },
                ),
                "ratio_width": (
                    "INT",
                    {
                        "default": 1,
                        "min": 1,
                        "max": MAX_RESOLUTION,
                        "tooltip": "Positive width component of the crop ratio.",
                    },
                ),
                "ratio_height": (
                    "INT",
                    {
                        "default": 1,
                        "min": 1,
                        "max": MAX_RESOLUTION,
                        "tooltip": "Positive height component of the crop ratio.",
                    },
                ),
                "crop_x": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": MAX_RESOLUTION,
                        "tooltip": "Left edge in oriented source-image pixels.",
                    },
                ),
                "crop_y": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": MAX_RESOLUTION,
                        "tooltip": "Top edge in oriented source-image pixels.",
                    },
                ),
                "crop_width": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": MAX_RESOLUTION,
                        "tooltip": (
                            "Crop width in source-image pixels. Zero width and height "
                            "initialize the largest centered crop."
                        ),
                    },
                ),
                "crop_height": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": MAX_RESOLUTION,
                        "tooltip": (
                            "Derived crop height in source-image pixels. Zero width "
                            "and "
                            "height initialize the largest centered crop."
                        ),
                    },
                ),
            }
        }

    def load_and_crop(
        self,
        image,
        ratio_width,
        ratio_height,
        crop_x,
        crop_y,
        crop_width,
        crop_height,
    ):
        import warnings

        import numpy as np
        import torch
        from nodes import MAX_RESOLUTION
        from PIL import Image, ImageOps

        try:
            with _open_input_file(image) as source, warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                decoded = Image.open(source)
                if getattr(decoded, "n_frames", 1) != 1:
                    raise ValueError("selected image must be a single still image")
                oriented = ImageOps.exif_transpose(decoded)
                width, height = oriented.size
                if width < 1 or height < 1:
                    raise ValueError("selected image has invalid dimensions")
                if width > MAX_RESOLUTION or height > MAX_RESOLUTION:
                    raise ValueError(
                        "selected image exceeds the maximum supported resolution"
                    )
                if width * height > MAX_IMAGE_PIXELS:
                    raise ValueError(
                        f"selected image exceeds the {MAX_IMAGE_PIXELS}-pixel limit"
                    )
                rgb = torch.from_numpy(
                    np.array(oriented.convert("RGB"), dtype=np.float32, copy=True)
                    / 255.0
                ).unsqueeze(0)
                if "A" in oriented.getbands():
                    alpha = torch.from_numpy(
                        np.array(
                            oriented.getchannel("A"),
                            dtype=np.float32,
                            copy=True,
                        )
                        / 255.0
                    )
                    mask = (1.0 - alpha).unsqueeze(0)
                else:
                    mask = torch.zeros((1, height, width), dtype=torch.float32)
        except (
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            Image.UnidentifiedImageError,
            OSError,
            SyntaxError,
        ):
            raise ValueError(
                "selected image could not be opened as a valid image"
            ) from None

        x, y, crop_width, crop_height, reduced_width, reduced_height = resolve_crop(
            source_width=width,
            source_height=height,
            ratio_width=ratio_width,
            ratio_height=ratio_height,
            crop_x=crop_x,
            crop_y=crop_y,
            crop_width=crop_width,
            crop_height=crop_height,
            max_resolution=MAX_RESOLUTION,
        )
        return {
            "ui": {
                "crop": [
                    {
                        "ratio_width": reduced_width,
                        "ratio_height": reduced_height,
                        "x": x,
                        "y": y,
                        "width": crop_width,
                        "height": crop_height,
                    }
                ]
            },
            "result": (
                rgb[:, y : y + crop_height, x : x + crop_width, :],
                mask[:, y : y + crop_height, x : x + crop_width],
            ),
        }

    @classmethod
    def IS_CHANGED(cls, image):
        return _content_hash(image)

    @classmethod
    def VALIDATE_INPUTS(cls, image):
        try:
            _input_path(image)
        except ValueError as error:
            return str(error)
        return True
