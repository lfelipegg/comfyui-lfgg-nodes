"""LFGG Prompt Assistant: ask a user-run ``llama-server`` to write a prompt.

The node talks HTTP to an OpenAI-compatible ``llama-server`` that the user
starts and configures. It never installs, spawns, or stops that server. See
``docs/plans/2026-10-29-prompt-assistant-design.md`` for the accepted contract.
"""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import importlib
import io
import json
import logging
import posixpath
import re
import time
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit

from .prompt_composer import load_config_document

LOGGER = logging.getLogger("lfgg_nodes.prompt_assistant")
ERROR_PREFIX = "LFGG Prompt Assistant: "

DEFAULT_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_READ_TIMEOUT = 300
READ_TIMEOUT_RANGE = (10, 3600)
CONNECT_TIMEOUT = 5
DEFAULT_SKILLS = (
    "scenario-maker-sdxl",
    "scenario-maker-krea-2",
    "scenario-maker-illustrious",
    "scenario-maker-noobai",
    "scenario-maker-pony",
    "scenario-maker-wan",
    "scenario-maker-minimax-h3",
)


class PromptAssistantError(ValueError):
    """Actionable failure raised by the prompt assistant."""

    def __init__(self, message):
        super().__init__(f"{ERROR_PREFIX}{message}")


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class AssistantConfig:
    base_url: str
    api_key: str
    read_timeout: int
    skills_roots: tuple[str, ...]
    skills: tuple[str, ...] | None


def _validate_base_url(value):
    if not isinstance(value, str) or not value.strip():
        raise PromptAssistantError("server.base_url must be an http or https URL")
    try:
        parts = urlsplit(value.strip())
        port = parts.port
    except ValueError:
        raise PromptAssistantError(
            "server.base_url must be an http or https URL with a valid port"
        ) from None
    if parts.scheme not in {"http", "https"}:
        raise PromptAssistantError("server.base_url must use http or https")
    if not parts.hostname:
        raise PromptAssistantError("server.base_url must include a host")
    if parts.username is not None or parts.password is not None:
        raise PromptAssistantError("server.base_url must not embed credentials")
    if parts.path not in {"", "/"} or parts.query or parts.fragment:
        raise PromptAssistantError(
            "server.base_url must not include a path, query, or fragment"
        )
    host = parts.hostname if ":" not in parts.hostname else f"[{parts.hostname}]"
    netloc = host if port is None else f"{host}:{port}"
    return f"{parts.scheme}://{netloc}"


def _validate_read_timeout(value):
    if value is None:
        return DEFAULT_READ_TIMEOUT
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PromptAssistantError("server.read_timeout_seconds must be a number")
    low, high = READ_TIMEOUT_RANGE
    if not low <= value <= high:
        raise PromptAssistantError(
            f"server.read_timeout_seconds must be between {low} and {high}"
        )
    return int(value)


def _validate_server(section):
    if section is None:
        section = {}
    if not isinstance(section, dict) or not set(section) <= {
        "base_url",
        "api_key",
        "read_timeout_seconds",
    }:
        raise PromptAssistantError(
            "server must contain only base_url, api_key, and read_timeout_seconds"
        )
    base_url = _validate_base_url(section.get("base_url", DEFAULT_BASE_URL))
    api_key = section.get("api_key", "")
    if not isinstance(api_key, str) or any(c in api_key for c in "\r\n\x00"):
        raise PromptAssistantError("server.api_key must be a single-line string")
    read_timeout = _validate_read_timeout(section.get("read_timeout_seconds"))
    return base_url, api_key.strip(), read_timeout


def is_root_spec(value):
    """True when ``value`` is absolute on either OS or starts with ``~``."""
    if not isinstance(value, str) or not value.strip():
        return False
    value = value.strip()
    if value == "~" or value[:2] in {"~/", "~\\"}:
        return True
    return PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute()


def expand_root(value):
    """Expand a leading ``~`` for either separator style; absolute paths pass."""
    value = value.strip()
    if value == "~":
        return Path.home()
    if value[:2] in {"~/", "~\\"}:
        remainder = value[2:].replace("\\", "/").strip("/")
        return Path.home().joinpath(*PurePosixPath(remainder).parts)
    return Path(value)


def _validate_skill_name(value, label):
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or any(c in value for c in "/\\\x00\r\n")
        or value.startswith(".")
        or value != value.strip()
    ):
        raise PromptAssistantError(f"{label} must be a plain skill directory name")
    return value


def validate_assistant_section(section):
    """Validate the ``prompt_assistant`` section into an ``AssistantConfig``."""
    if not isinstance(section, dict) or not set(section) <= {
        "server",
        "skills_roots",
        "skills",
    }:
        raise PromptAssistantError(
            "prompt_assistant must contain only server, skills_roots, and skills"
        )
    base_url, api_key, read_timeout = _validate_server(section.get("server"))
    roots = section.get("skills_roots")
    if not isinstance(roots, list) or not all(is_root_spec(r) for r in roots):
        raise PromptAssistantError(
            "skills_roots must be a list of absolute paths or paths starting with ~"
        )
    skills = section.get("skills")
    if skills is not None:
        if not isinstance(skills, list):
            raise PromptAssistantError("skills must be a list of skill names")
        names = [_validate_skill_name(name, "skills entry") for name in skills]
        if len(set(names)) != len(names):
            raise PromptAssistantError("skills must not repeat a skill name")
        skills = tuple(names)
    return AssistantConfig(
        base_url=base_url,
        api_key=api_key,
        read_timeout=read_timeout,
        skills_roots=tuple(root.strip() for root in roots),
        skills=skills,
    )


def load_assistant_config():
    """Load and validate the ``prompt_assistant`` section of ``config.json``."""
    config, _ = load_config_document(
        "prompt assistant configuration", PromptAssistantError
    )
    if "prompt_assistant" not in config:
        raise PromptAssistantError(
            "configuration has no prompt_assistant section; add it to "
            "<ComfyUI user directory>/lfgg_nodes/config.json"
        )
    return validate_assistant_section(config["prompt_assistant"])



# --------------------------------------------------------------------------
# Skill discovery, selection, and attachment
# --------------------------------------------------------------------------

SKILL_FILE_NAME = "SKILL.md"
EXCLUDED_DIRECTORIES = frozenset({"evals", "docs", "tests", "scripts", "wildcards"})
FILE_LIMIT = 512 * 1024
ATTACHED_TOTAL_LIMIT = 256 * 1024
DISCOVERY_ENTRY_LIMIT = 10_000
# A path-like mention ending in ``.md``: markdown links, backticks, or bare text.
MARKDOWN_MENTION = re.compile(r"[A-Za-z0-9_./-]+\.md(?![A-Za-z0-9_])")


@dataclasses.dataclass(frozen=True)
class RootStatus:
    spec: str
    path: Path | None

    @property
    def available(self):
        return self.path is not None


@dataclasses.dataclass(frozen=True)
class Skill:
    name: str
    root: str
    path: Path


@dataclasses.dataclass(frozen=True)
class SkillFile:
    relative: str
    path: Path
    size: int


@dataclasses.dataclass
class Discovery:
    skills: dict[str, Skill]
    roots: list[RootStatus]
    allowlist: tuple[str, ...] | None
    warnings: list[str]

    @property
    def missing(self):
        if self.allowlist is None:
            return ()
        return tuple(name for name in self.allowlist if name not in self.skills)

    def roots_searched(self):
        if not self.roots:
            return "no skills_roots are configured"
        parts = []
        for root in self.roots:
            state = "" if root.available else " (missing)"
            parts.append(f"{root.spec}{state}")
        return "roots searched: " + ", ".join(parts)


def _is_plain_name(value):
    try:
        _validate_skill_name(value, "name")
    except PromptAssistantError:
        return False
    return True


def _contained(path, root):
    """Resolve ``path`` strictly and prove it lies inside the resolved ``root``."""
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None
    return resolved


def _resolve_root(spec):
    try:
        path = expand_root(spec).resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return None
    return path if path.is_dir() else None


def discover_skills(root_specs, allowlist):
    """Find allowlisted skill directories one level below each configured root."""
    allowlist = None if allowlist is None else tuple(allowlist)
    discovery = Discovery(skills={}, roots=[], allowlist=allowlist, warnings=[])
    for spec in root_specs:
        root = _resolve_root(spec)
        discovery.roots.append(RootStatus(spec=spec, path=root))
        if root is None:
            discovery.warnings.append(f"skills root {spec} is not a directory")
            continue
        try:
            children = sorted(root.iterdir(), key=lambda path: path.name)
        except OSError:
            discovery.warnings.append(f"skills root {spec} could not be listed")
            continue
        for child in children:
            name = child.name
            if not _is_plain_name(name):
                continue
            if allowlist is not None and name not in allowlist:
                continue
            directory = _contained(child, root)
            if directory is None or not directory.is_dir():
                if child.is_symlink():
                    discovery.warnings.append(
                        f"skill {name} under {spec} escapes its root and was ignored"
                    )
                continue
            skill_file = _contained(directory / SKILL_FILE_NAME, directory)
            if skill_file is None or not skill_file.is_file():
                continue
            existing = discovery.skills.get(name)
            if existing is not None:
                discovery.warnings.append(
                    f"skill {name} found in both {existing.root} and {spec}; "
                    f"using {existing.root}"
                )
                continue
            discovery.skills[name] = Skill(name=name, root=spec, path=directory)
    return discovery


def skill_files(skill):
    """List attachable ``.md`` files beneath a skill, excluding non-skill content."""
    files = []
    visited = 0
    stack = [(skill.path, ())]
    seen = {skill.path}
    while stack:
        directory, relative = stack.pop()
        try:
            children = sorted(directory.iterdir(), key=lambda path: path.name)
        except OSError:
            continue
        directories = []
        for child in children:
            visited += 1
            if visited > DISCOVERY_ENTRY_LIMIT:
                raise PromptAssistantError(
                    f"skill {skill.name} exceeds {DISCOVERY_ENTRY_LIMIT} entries"
                )
            name = child.name
            if name.startswith("."):
                continue
            resolved = _contained(child, skill.path)
            if resolved is None:
                continue
            if resolved.is_dir():
                if name in EXCLUDED_DIRECTORIES or resolved in seen:
                    continue
                seen.add(resolved)
                directories.append((child, (*relative, name)))
                continue
            if not resolved.is_file() or child.suffix.casefold() != ".md":
                continue
            if not relative and name == SKILL_FILE_NAME:
                continue
            try:
                size = resolved.stat().st_size
            except OSError:
                continue
            files.append(
                SkillFile(
                    relative=PurePosixPath(*relative, name).as_posix(),
                    path=resolved,
                    size=size,
                )
            )
        stack.extend(reversed(directories))
    return sorted(files, key=lambda item: item.relative)


@dataclasses.dataclass(frozen=True)
class SelectionEntry:
    skill: str
    file: str | None
    raw: str


def _file_parts(entry, relative):
    parts = tuple(relative.split("/"))
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise PromptAssistantError(
            f"selection entry {entry!r} must stay inside its skill directory"
        )
    if any(part.startswith(".") for part in parts):
        raise PromptAssistantError(
            f"selection entry {entry!r} points into a hidden directory"
        )
    excluded = [part for part in parts[:-1] if part in EXCLUDED_DIRECTORIES]
    if excluded:
        raise PromptAssistantError(
            f"selection entry {entry!r} points into the excluded directory "
            f"{excluded[0]}/"
        )
    if parts[-1] == SKILL_FILE_NAME and len(parts) == 1:
        raise PromptAssistantError(
            f"selection entry {entry!r} names SKILL.md, which is attached by the "
            "bare skill name"
        )
    if not parts[-1].casefold().endswith(".md") or parts[-1].casefold() == ".md":
        raise PromptAssistantError(
            f"selection entry {entry!r} must name a .md file"
        )
    return parts


def parse_selection(text):
    """Parse the multiline ``skills`` widget into ordered selection entries."""
    if not isinstance(text, str):
        raise PromptAssistantError("skills must be a string")
    entries = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "\\" in line:
            raise PromptAssistantError(
                f"selection entry {line!r} must use / as the separator"
            )
        if any(character in line for character in "\x00"):
            raise PromptAssistantError(f"selection entry {line!r} is not valid")
        skill, _, relative = line.partition("/")
        if not _is_plain_name(skill):
            raise PromptAssistantError(
                f"selection entry {line!r} must start with a skill name"
            )
        if relative:
            _file_parts(line, relative)
            entries.append(SelectionEntry(skill=skill, file=relative, raw=line))
        else:
            entries.append(SelectionEntry(skill=skill, file=None, raw=line))
    return entries


def group_selection(entries):
    """Group entries by skill in first-seen order, deduplicating files."""
    grouped = {}
    for entry in entries:
        files = grouped.setdefault(entry.skill, [])
        if entry.file is not None and entry.file not in files:
            files.append(entry.file)
    return grouped


@dataclasses.dataclass(frozen=True)
class Attachment:
    skill: str
    relative: str
    path: Path


def _read_text(path, label):
    try:
        with path.open("rb") as source:
            content = source.read(FILE_LIMIT + 1)
    except OSError:
        raise PromptAssistantError(f"attachment {label} could not be read") from None
    if len(content) > FILE_LIMIT:
        raise PromptAssistantError(
            f"attachment {label} exceeds the {FILE_LIMIT // 1024} KiB file limit"
        )
    try:
        return content.decode("utf-8-sig"), len(content)
    except UnicodeDecodeError:
        raise PromptAssistantError(f"attachment {label} must be UTF-8") from None


def _mentioned_files(text, directory, available):
    """Yield attachable files ``text`` names, relative to its file or the skill."""
    for match in MARKDOWN_MENTION.finditer(text):
        mention = match.group(0)
        for anchor in (directory, ""):
            candidate = posixpath.normpath(posixpath.join(anchor, mention))
            if candidate in available:
                yield candidate
                break


def linked_references(skill, files):
    """Follow ``.md`` mentions from ``SKILL.md`` through the files they name.

    Only mentions that match one of ``files`` (the skill's attachable files) are
    followed, so links cannot reach outside the skill or into excluded content.
    """
    available = {item.relative: item.path for item in files}
    linked = []
    queue = [(SKILL_FILE_NAME, skill.path / SKILL_FILE_NAME)]
    seen = {SKILL_FILE_NAME}
    while queue:
        relative, path = queue.pop(0)
        text, _ = _read_text(path, f"{skill.name}/{relative}")
        directory = posixpath.dirname(relative)
        for mention in _mentioned_files(text, directory, available):
            if mention not in seen:
                seen.add(mention)
                linked.append(mention)
                queue.append((mention, available[mention]))
    return linked


def resolve_selection(entries, discovery):
    """Map parsed entries to files, raising actionable errors for bad entries.

    Each selected skill attaches its ``SKILL.md``, then every reference that
    ``SKILL.md`` links to (transitively), then any other selected files.
    """
    attachments = []
    for name, files in group_selection(entries).items():
        skill = discovery.skills.get(name)
        if skill is None:
            if discovery.allowlist is not None and name not in discovery.allowlist:
                raise PromptAssistantError(
                    f"skill {name} is not in the prompt_assistant.skills allowlist"
                )
            raise PromptAssistantError(
                f"skill {name} was not found; {discovery.roots_searched()}"
            )
        attachments.append(
            Attachment(
                skill=name, relative=SKILL_FILE_NAME, path=skill.path / SKILL_FILE_NAME
            )
        )
        available = skill_files(skill)
        paths = {item.relative: item.path for item in available}
        included = set()
        for relative in linked_references(skill, available):
            included.add(relative)
            attachments.append(
                Attachment(skill=name, relative=relative, path=paths[relative])
            )
        for relative in files:
            parts = _file_parts(f"{name}/{relative}", relative)
            if PurePosixPath(*parts).as_posix() in included:
                continue
            candidate = skill.path.joinpath(*parts)
            resolved = _contained(candidate, skill.path)
            if resolved is None:
                if candidate.exists() or candidate.is_symlink():
                    raise PromptAssistantError(
                        f"selection entry {name}/{relative} resolves outside skill "
                        f"{name}"
                    )
                raise PromptAssistantError(
                    f"selection entry {name}/{relative} was not found under "
                    f"{skill.root}"
                )
            if not resolved.is_file():
                raise PromptAssistantError(
                    f"selection entry {name}/{relative} is not a file"
                )
            attachments.append(
                Attachment(
                    skill=name,
                    relative=PurePosixPath(*parts).as_posix(),
                    path=resolved,
                )
            )
    return attachments


@dataclasses.dataclass(frozen=True)
class AttachedText:
    skill: str
    relative: str
    text: str
    size: int


def _read_attachment(attachment):
    text, size = _read_text(
        attachment.path, f"{attachment.skill}/{attachment.relative}"
    )
    return AttachedText(
        skill=attachment.skill, relative=attachment.relative, text=text, size=size
    )


def read_attachments(attachments):
    """Read every attachment, enforcing the per-file and total size caps."""
    attached = [_read_attachment(attachment) for attachment in attachments]
    total = sum(item.size for item in attached)
    if total > ATTACHED_TOTAL_LIMIT:
        largest = sorted(attached, key=lambda item: item.size, reverse=True)[:3]
        listing = ", ".join(
            f"{item.skill}/{item.relative} ({item.size // 1024} KiB)"
            for item in largest
        )
        raise PromptAssistantError(
            f"attached skills total {total // 1024} KiB, above the "
            f"{ATTACHED_TOTAL_LIMIT // 1024} KiB limit; largest: {listing}"
        )
    return attached


def strip_frontmatter(text):
    """Remove a leading YAML frontmatter block delimited by ``---`` lines."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[index + 1 :])
    return text


def unattached_references(attachments, discovery):
    """List the attachable files of each attached skill that were left out."""
    attached = {(item.skill, item.relative) for item in attachments}
    missing = []
    for name in dict.fromkeys(item.skill for item in attachments):
        for item in skill_files(discovery.skills[name]):
            if (name, item.relative) not in attached:
                missing.append(f"{name}/{item.relative}")
    return missing


ATTACHMENT_NOTE = (
    "# Attached skill files\n\n"
    "You cannot open files or run scripts. Every file you can use is attached "
    "in full below. When a skill says to read or consult a file, use the "
    "section headed with that skill and file path."
)


def build_system_message(master_prompt, attached, unattached=()):
    """Compose the system message; ``None`` when there is nothing to send."""
    if not isinstance(master_prompt, str):
        raise PromptAssistantError("master_prompt must be a string")
    sections = []
    master = master_prompt.strip()
    if master:
        sections.append(master)
    if attached:
        note = ATTACHMENT_NOTE
        if unattached:
            note += (
                " These files are not attached, so do not assume their "
                f"contents: {', '.join(unattached)}."
            )
        sections.append(note)
    for item in attached:
        if item.relative == SKILL_FILE_NAME:
            body = strip_frontmatter(item.text).strip()
            sections.append(f"# Skill: {item.skill}\n\n{body}")
        else:
            sections.append(f"## {item.skill}/{item.relative}\n\n{item.text.strip()}")
    if not sections:
        return None
    return "\n\n".join(sections)


# --------------------------------------------------------------------------
# Images and message assembly
# --------------------------------------------------------------------------

MAX_IMAGES = 8
IMAGE_LONG_SIDE = 1024
IMAGE_PIXEL_LIMIT = 268_435_456
JPEG_QUALITY = 92
TEXT_LIMIT = 1024 * 1024
SERVER_DEFAULT_MODEL = "server default"
SEED_MODULUS = 2**32


@dataclasses.dataclass(frozen=True)
class EncodedImage:
    media_type: str
    data: bytes
    width: int
    height: int

    def data_url(self):
        encoded = base64.b64encode(self.data).decode("ascii")
        return f"data:{self.media_type};base64,{encoded}"


def _validate_image_tensor(image, slot):
    shape = getattr(image, "shape", None)
    if shape is None or len(shape) != 4 or shape[3] not in {1, 3, 4}:
        raise PromptAssistantError(
            f"image_{slot} must be an IMAGE shaped [B,H,W,C] with 1, 3, or 4 channels"
        )
    if not image.is_floating_point():
        raise PromptAssistantError(f"image_{slot} values must have a float dtype")
    if shape[0] < 1 or shape[1] < 1 or shape[2] < 1:
        raise PromptAssistantError(f"image_{slot} must contain at least one pixel")
    if shape[1] * shape[2] > IMAGE_PIXEL_LIMIT:
        raise PromptAssistantError(
            f"image_{slot} frames must contain at most {IMAGE_PIXEL_LIMIT} pixels"
        )


def collect_frames(images):
    """Return every frame of every connected slot, in slot then batch order."""
    frames = []
    for slot, image in enumerate(images, 1):
        if image is None:
            continue
        _validate_image_tensor(image, slot)
        frames.extend(image[index] for index in range(image.shape[0]))
    if len(frames) > MAX_IMAGES:
        raise PromptAssistantError(
            f"{len(frames)} images are connected; at most {MAX_IMAGES} are allowed "
            "across image_1 to image_4, counting every batch frame"
        )
    return frames


def _scaled_size(width, height):
    longest = max(width, height)
    if longest <= IMAGE_LONG_SIDE:
        return width, height
    scale = IMAGE_LONG_SIDE / longest
    return max(1, round(width * scale)), max(1, round(height * scale))


def encode_frame(frame):
    """Encode one ``[H,W,C]`` float frame as JPEG, or PNG when it has alpha."""
    import numpy
    from PIL import Image

    height, width, channels = frame.shape
    pixels = frame.detach().to("cpu").float().clamp(0, 1).mul(255).round()
    array = pixels.numpy().astype(numpy.uint8)
    mode = {1: "L", 3: "RGB", 4: "RGBA"}[channels]
    if channels == 1:
        array = array[:, :, 0]
    image = Image.fromarray(numpy.ascontiguousarray(array), mode)
    target = _scaled_size(width, height)
    if target != (width, height):
        image = image.resize(target, Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    if channels == 4:
        image.save(buffer, format="PNG")
        media_type = "image/png"
    else:
        image.save(buffer, format="JPEG", quality=JPEG_QUALITY)
        media_type = "image/jpeg"
    return EncodedImage(
        media_type=media_type, data=buffer.getvalue(), width=target[0], height=target[1]
    )


def encode_images(images):
    """Validate, count, and encode the frames of the optional image inputs."""
    return [encode_frame(frame) for frame in collect_frames(images)]


def _validate_text(value, label):
    if not isinstance(value, str):
        raise PromptAssistantError(f"{label} must be a string")
    if len(value) > TEXT_LIMIT or len(value.encode("utf-8")) > TEXT_LIMIT:
        raise PromptAssistantError(f"{label} exceeds the 1 MiB limit")
    return value


def build_messages(system, request, encoded):
    """Build the chat messages: optional system, then images and the request."""
    request = _validate_text(request, "request").strip()
    if not request and not encoded:
        raise PromptAssistantError(
            "request is empty and no image is connected; write a request or "
            "connect an image"
        )
    content = []
    total = len(encoded)
    for index, image in enumerate(encoded, 1):
        content.append({"type": "text", "text": f"Image {index} of {total}"})
        content.append({"type": "image_url", "image_url": {"url": image.data_url()}})
    if request:
        content.append({"type": "text", "text": request})
    messages = []
    if system is not None:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": content})
    return messages


def build_request_body(messages, model, seed, temperature, max_tokens):
    """Build the streamed chat-completion body with validated sampling values."""
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**64:
        raise PromptAssistantError("seed must be an unsigned 64-bit integer")
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        raise PromptAssistantError("temperature must be a number")
    if not 0 <= temperature <= 2:
        raise PromptAssistantError("temperature must be between 0 and 2")
    if (
        isinstance(max_tokens, bool)
        or not isinstance(max_tokens, int)
        or not 1 <= max_tokens <= 32768
    ):
        raise PromptAssistantError("max_tokens must be between 1 and 32768")
    if not isinstance(model, str) or not model.strip():
        raise PromptAssistantError("model must be a model id or 'server default'")
    body = {
        "messages": messages,
        "stream": True,
        "seed": seed % SEED_MODULUS,
        "temperature": float(temperature),
        "max_tokens": max_tokens,
    }
    if model.strip() != SERVER_DEFAULT_MODEL:
        body["model"] = model.strip()
    return body


# --------------------------------------------------------------------------
# llama-server client
# --------------------------------------------------------------------------

# llama-server wraps every token in an SSE JSON chunk of roughly 200-400
# bytes, so the streamed-body cap grows with the requested max_tokens.
STREAM_LIMIT = 1024 * 1024
STREAM_BYTES_PER_TOKEN = 1024
BODY_LIMIT = 256 * 1024
UNLOAD_DEADLINE = 30.0
UNLOAD_POLL_INTERVAL = 0.5
ERROR_SNIPPET = 200


@dataclasses.dataclass(frozen=True)
class ServerModels:
    mode: str
    models: tuple[dict, ...]

    def status_of(self, model_id):
        for model in self.models:
            if model["id"] == model_id:
                return model["status"]
        return None

    def loaded_ids(self):
        return tuple(m["id"] for m in self.models if m["status"] == "loaded")


def _snippet(content):
    text = content[:ERROR_SNIPPET].decode("utf-8", "replace")
    return " ".join(text.split())


class ServerClient:
    """Bounded aiohttp client for one user-run ``llama-server``.

    Network behavior: every call goes to ``base_url`` only, with a 5 s connect
    timeout, the configured read timeout, one attempt, no redirects, a 256 KiB
    cap on plain bodies, and a 1 MiB cap on streamed bodies.
    """

    def __init__(self, base_url, api_key="", read_timeout=DEFAULT_READ_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.read_timeout = read_timeout
        self._session = None

    async def __aenter__(self):
        import aiohttp

        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        self._session = aiohttp.ClientSession(
            headers=headers,
            timeout=aiohttp.ClientTimeout(
                total=None,
                connect=CONNECT_TIMEOUT,
                sock_connect=CONNECT_TIMEOUT,
                sock_read=self.read_timeout,
            ),
            auto_decompress=True,
        )
        return self

    async def __aexit__(self, *exc_info):
        session, self._session = self._session, None
        if session is not None:
            await session.close()

    def _url(self, path):
        return f"{self.base_url}{path}"

    def _unreachable(self, path, error):
        reason = error.__class__.__name__
        return PromptAssistantError(
            f"cannot reach llama-server at {self.base_url} ({reason} on {path}); "
            "start llama-server and check prompt_assistant.server.base_url"
        )

    def _timeout(self, path):
        return PromptAssistantError(
            f"llama-server at {self.base_url} did not answer {path} within "
            f"{self.read_timeout} s; raise server.read_timeout_seconds, lower "
            "max_tokens, or check the server log"
        )

    def _open(self, method, path, **kwargs):
        if self._session is None:
            raise PromptAssistantError("server client is not open")
        return self._session.request(
            method, self._url(path), allow_redirects=False, **kwargs
        )

    async def _json(self, method, path, *, json_body=None, params=None, ok=(200,)):
        import aiohttp

        try:
            async with self._open(
                method, path, json=json_body, params=params
            ) as response:
                content = await _read_capped(response.content, BODY_LIMIT)
                status = response.status
        except _connect_timeout_errors() as error:
            raise self._unreachable(path, error) from None
        except asyncio.TimeoutError:
            raise self._timeout(path) from None
        except aiohttp.ClientError as error:
            raise self._unreachable(path, error) from None
        if content is None:
            raise PromptAssistantError(
                f"{path} response from {self.base_url} exceeds {BODY_LIMIT} bytes"
            )
        if status not in ok:
            if 300 <= status < 400:
                raise PromptAssistantError(
                    f"{self.base_url} redirected {path}; redirects are not followed, "
                    "point base_url at llama-server directly"
                )
            raise PromptAssistantError(
                f"{self.base_url} returned HTTP {status} for {path}: "
                f"{_snippet(content) or 'empty body'}"
            )
        if not content.strip():
            return status, None
        try:
            return status, json.loads(content)
        except ValueError:
            raise PromptAssistantError(
                f"{self.base_url} returned invalid JSON for {path}"
            ) from None

    async def health(self):
        """Fail fast when the server is unreachable or still loading."""
        status, payload = await self._json("GET", "/health", ok=(200, 503))
        if status == 503:
            raise PromptAssistantError(
                f"llama-server at {self.base_url} is not ready (HTTP 503: "
                f"{_describe_error(payload)}); wait for the model to load"
            )

    async def list_models(self):
        """Router-mode ``GET /models``; a 404 means single-model mode."""
        status, payload = await self._json("GET", "/models", ok=(200, 404))
        if status == 404:
            _, payload = await self._json("GET", "/v1/models")
            return ServerModels(
                mode="single",
                models=tuple(
                    {"id": item["id"], "status": "loaded"}
                    for item in _model_items(payload, "/v1/models")
                ),
            )
        models = []
        for item in _model_items(payload, "/models"):
            state = item.get("status")
            value = state.get("value") if isinstance(state, dict) else state
            models.append({"id": item["id"], "status": str(value or "unknown")})
        return ServerModels(mode="router", models=tuple(models))

    async def props(self, model=None):
        params = {"model": model} if model else None
        _, payload = await self._json("GET", "/props", params=params)
        return payload if isinstance(payload, dict) else {}

    async def check_vision(self, model=None):
        """Raise unless ``/props`` reports ``modalities.vision``."""
        payload = await self.props(model)
        modalities = payload.get("modalities")
        vision = modalities.get("vision") if isinstance(modalities, dict) else None
        if vision is not True:
            raise PromptAssistantError(
                "the selected model does not report vision support; start "
                "llama-server with --mmproj for a vision model or disconnect the "
                "image inputs"
            )

    async def stream_chat(self, body, *, on_delta=None, check_interrupt=None):
        """POST a streamed chat completion and return the reply content."""
        import aiohttp

        path = "/v1/chat/completions"
        parser = _StreamParser(body.get("max_tokens"))
        try:
            async with self._open("POST", path, json=body) as response:
                if response.status != 200:
                    content = await _read_capped(response.content, ERROR_SNIPPET)
                    raise PromptAssistantError(
                        f"{self.base_url} returned HTTP {response.status} for "
                        f"{path}: {_snippet(content or b'') or 'empty body'}"
                    )
                try:
                    async for chunk in response.content.iter_any():
                        if check_interrupt is not None:
                            check_interrupt()
                        parser.feed(chunk)
                        for snapshot in parser.drain():
                            if on_delta is not None:
                                on_delta(snapshot)
                        if parser.done:
                            break
                except BaseException:
                    response.close()
                    raise
        except _connect_timeout_errors() as error:
            raise self._unreachable(path, error) from None
        except asyncio.TimeoutError:
            raise self._timeout(path) from None
        except aiohttp.ClientError as error:
            raise self._unreachable(path, error) from None
        return parser.finish()

    async def unload_model(
        self,
        model_id,
        *,
        deadline=UNLOAD_DEADLINE,
        poll_interval=UNLOAD_POLL_INTERVAL,
        sleep=asyncio.sleep,
        monotonic=time.monotonic,
    ):
        """``POST /models/unload`` then poll ``GET /models`` until unloaded.

        Returns True when the model reports ``unloaded`` within ``deadline``.
        """
        await self._json("POST", "/models/unload", json_body={"model": model_id})
        started = monotonic()
        while True:
            models = await self.list_models()
            if models.status_of(model_id) in {None, "unloaded"}:
                return True
            if monotonic() - started >= deadline:
                return False
            await sleep(poll_interval)


async def _read_capped(stream, limit):
    """Read a body to EOF; return None once it grows past ``limit`` bytes."""
    buffer = bytearray()
    while True:
        chunk = await stream.read(64 * 1024)
        if not chunk:
            return bytes(buffer)
        buffer.extend(chunk)
        if len(buffer) > limit:
            return None


def _connect_timeout_errors():
    import aiohttp

    # aiohttp >= 3.10 distinguishes connect timeouts; older builds raise the
    # generic asyncio.TimeoutError, which is then reported as a read timeout.
    error = getattr(aiohttp, "ConnectionTimeoutError", None)
    return (error,) if error is not None else ()


def _describe_error(payload):
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"][:ERROR_SNIPPET]
        if isinstance(error, str):
            return error[:ERROR_SNIPPET]
    return "no detail"


def _model_items(payload, path):
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise PromptAssistantError(f"{path} did not return a model list")
    items = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            items.append(item)
    return items


class _StreamParser:
    """Parse OpenAI-style SSE chat chunks under the streamed-body cap."""

    def __init__(self, max_tokens=None):
        tokens = max_tokens if isinstance(max_tokens, int) else 0
        self._limit = STREAM_LIMIT + max(tokens, 0) * STREAM_BYTES_PER_TOKEN
        self._buffer = bytearray()
        self._parts = []
        self._received = 0
        self.saw_reasoning = False
        self.finish_reason = None
        self.done = False
        self._snapshots = []

    def feed(self, chunk):
        self._received += len(chunk)
        if self._received > self._limit:
            raise PromptAssistantError(
                f"streamed reply exceeds {self._limit} bytes; check the server "
                "log for a model that ignores max_tokens or repeats itself"
            )
        self._buffer.extend(chunk)
        while True:
            newline = self._buffer.find(b"\n")
            if newline < 0:
                return
            line = bytes(self._buffer[:newline]).rstrip(b"\r")
            del self._buffer[: newline + 1]
            self._line(line)
            if self.done:
                return

    def _line(self, line):
        if not line.startswith(b"data:"):
            return
        payload = line[5:].strip()
        if payload == b"[DONE]":
            self.done = True
            return
        try:
            event = json.loads(payload)
        except ValueError:
            raise PromptAssistantError("llama-server sent an invalid stream chunk")
        if not isinstance(event, dict):
            raise PromptAssistantError("llama-server sent an invalid stream chunk")
        if "error" in event:
            raise PromptAssistantError(
                f"llama-server reported an error while generating: "
                f"{_describe_error(event)}"
            )
        choices = event.get("choices")
        if not isinstance(choices, list) or not choices:
            return
        choice = choices[0] if isinstance(choices[0], dict) else {}
        delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
        content = delta.get("content")
        if isinstance(content, str) and content:
            self._parts.append(content)
            self._snapshots.append(self.text())
        reasoning = delta.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning:
            self.saw_reasoning = True
        if choice.get("finish_reason"):
            self.finish_reason = choice["finish_reason"]

    def text(self):
        return "".join(self._parts)

    def drain(self):
        """Return the accumulated text after each new content delta."""
        snapshots, self._snapshots = self._snapshots, []
        return snapshots

    def finish(self):
        if not self.done and self.finish_reason is None:
            raise PromptAssistantError(
                "llama-server closed the stream before the reply finished; check "
                "the server log"
            )
        prompt = self.text().strip()
        if not prompt:
            if self.saw_reasoning:
                raise PromptAssistantError(
                    "the reply contained only reasoning and no content; raise "
                    "max_tokens so a reasoning model can finish thinking, or use "
                    "a model without reasoning"
                )
            raise PromptAssistantError(
                "the reply was empty; raise max_tokens or check that the model "
                "is a chat model (reasoning models may spend all tokens thinking)"
            )
        return prompt


# --------------------------------------------------------------------------
# VRAM policy
# --------------------------------------------------------------------------

VRAM_POLICIES = ("share", "keep_llm_loaded", "off")


def _mebibytes(value):
    return f"{int(value) // (1024 * 1024)} MiB"


def release_comfy_models(model_management, *, model_size=0):
    """Move ComfyUI's loaded models to RAM before the language model runs.

    Every call into ``comfy.model_management`` is guarded: that module is an
    internal API, so a changed signature or a failure degrades to a warning
    and the node continues. Returns the warnings to log.
    """
    warnings = []
    if model_management is None:
        return ["comfy.model_management is unavailable; models stay in VRAM"]
    try:
        import torch

        device = model_management.get_torch_device()
        in_use = model_management.get_total_memory(
            device
        ) - model_management.get_free_memory(device)
        free_ram = model_management.get_free_memory(torch.device("cpu"))
        needed = in_use + model_size
        if free_ram < needed:
            warnings.append(
                f"free RAM {_mebibytes(free_ram)} is below the VRAM in use plus the "
                f"language model ({_mebibytes(needed)}); moving models to RAM may "
                "fail"
            )
    except Exception as error:  # noqa: BLE001 - internal API, degrade to warning
        warnings.append(f"memory check skipped: {error!s}")
    try:
        model_management.unload_all_models()
        model_management.soft_empty_cache()
    except Exception as error:  # noqa: BLE001 - internal API, degrade to warning
        warnings.append(f"could not move ComfyUI models to RAM: {error!s}")
    return warnings


async def release_llm(client, model_id):
    """Release the language model from the server after the reply.

    Router mode unloads ``model_id`` (or every loaded model when the server
    default was used) and waits for ``unloaded``. Single-model mode can only
    warn. Returns the warnings to log; failures never discard the reply.
    """
    try:
        models = await client.list_models()
    except PromptAssistantError as error:
        return [f"could not query loaded models after the reply: {error!s}"]
    if models.mode == "single":
        return [
            "llama-server runs in single-model mode, so the language model stays "
            "in VRAM; start it in router mode (--models-dir or --models-preset) "
            "or with --sleep-idle-seconds to release it"
        ]
    targets = (model_id,) if model_id else models.loaded_ids()
    warnings = []
    for target in targets:
        try:
            released = await client.unload_model(target)
        except PromptAssistantError as error:
            warnings.append(f"could not unload {target}: {error!s}")
            continue
        if not released:
            warnings.append(
                f"model {target} did not report unloaded within "
                f"{int(UNLOAD_DEADLINE)} s; VRAM may still be held"
            )
    return warnings


# --------------------------------------------------------------------------
# Node and routes (ComfyUI boundary)
# --------------------------------------------------------------------------

DEFAULT_MASTER_PROMPT = (
    "You write prompts for image and video generation models. Follow the "
    "attached\nskill exactly. Reply with the final prompt only, no explanation."
)


def _model_management():
    try:
        return importlib.import_module("comfy.model_management")
    except Exception:  # noqa: BLE001 - optional internal module
        return None


def _interrupt_check():
    check = getattr(
        _model_management(), "throw_exception_if_processing_interrupted", None
    )
    return check if callable(check) else None


def _send_progress(unique_id, text):
    if unique_id is None:
        return
    try:
        from server import PromptServer

        PromptServer.instance.send_progress_text(text, unique_id)
    except Exception as error:  # noqa: BLE001 - progress is best effort
        LOGGER.debug("progress text not delivered: %s", error)


def _log_warnings(warnings):
    for warning in warnings:
        LOGGER.warning("%s", warning)


def skills_catalog(config):
    """Describe allowlisted skills for the picker: roots, files, and sizes."""
    discovery = discover_skills(config.skills_roots, config.skills)
    skills = []
    warnings = list(discovery.warnings)
    for name, skill in discovery.skills.items():
        try:
            skill_size = (skill.path / SKILL_FILE_NAME).stat().st_size
        except OSError:
            skill_size = 0
        files = skill_files(skill)
        try:
            linked = set(linked_references(skill, files))
        except PromptAssistantError as error:
            linked = set()
            warnings.append(str(error).removeprefix(ERROR_PREFIX))
        skills.append(
            {
                "name": name,
                "root": skill.root,
                "available": True,
                "skill_size": skill_size,
                "files": [
                    {
                        "path": item.relative,
                        "size": item.size,
                        "linked": item.relative in linked,
                    }
                    for item in files
                ],
            }
        )
    for name in discovery.missing:
        skills.append(
            {
                "name": name,
                "root": None,
                "available": False,
                "skill_size": 0,
                "files": [],
            }
        )
    return {
        "roots": [
            {"path": root.spec, "available": root.available} for root in discovery.roots
        ],
        "skills": skills,
        "warnings": warnings,
        "limits": {"total": ATTACHED_TOTAL_LIMIT, "file": FILE_LIMIT},
    }


class PromptAssistant:
    DESCRIPTION = (
        "Asks a user-run llama-server to write a generation prompt from a master "
        "prompt, attached skills, a request, and optional images."
    )
    CATEGORY = "LFGG/text"
    FUNCTION = "generate"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    OUTPUT_TOOLTIPS = (
        "Generated prompt: the model's reply with surrounding whitespace trimmed.",
    )

    @classmethod
    def INPUT_TYPES(cls):
        image = (
            "IMAGE",
            {
                "tooltip": (
                    "Optional reference images; every batch frame is sent, at most "
                    "eight across all four inputs."
                )
            },
        )
        return {
            "required": {
                "master_prompt": (
                    "STRING",
                    {
                        "default": DEFAULT_MASTER_PROMPT,
                        "multiline": True,
                        "tooltip": (
                            "Reusable standing instructions sent as the system "
                            "message before the attached skills."
                        ),
                    },
                ),
                "request": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "placeholder": "Describe the prompt to write…",
                        "tooltip": (
                            "What to write now. May be empty only when an image "
                            "is connected."
                        ),
                    },
                ),
                "skills": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "placeholder": "skill-name\nskill-name/references/file.md",
                        "tooltip": (
                            "One entry per line: a skill name attaches its SKILL.md; "
                            "skill-name/relative/file.md also attaches that "
                            "reference."
                        ),
                    },
                ),
                "model": (
                    [SERVER_DEFAULT_MODEL],
                    {
                        "default": SERVER_DEFAULT_MODEL,
                        "tooltip": (
                            "Model id on the llama-server; refresh the list from "
                            "the server or keep the server default."
                        ),
                    },
                ),
                "vram_policy": (
                    list(VRAM_POLICIES),
                    {
                        "default": "share",
                        "tooltip": (
                            "share moves ComfyUI models to RAM before the call and "
                            "unloads the language model after it (router mode); "
                            "keep_llm_loaded skips the unload; off does nothing."
                        ),
                    },
                ),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 2**64 - 1,
                        "control_after_generate": True,
                        "tooltip": "Sampler seed; the low 32 bits are sent.",
                    },
                ),
                "temperature": (
                    "FLOAT",
                    {
                        "default": 0.7,
                        "min": 0.0,
                        "max": 2.0,
                        "step": 0.05,
                        "tooltip": "Sampling temperature.",
                    },
                ),
                "max_tokens": (
                    "INT",
                    {
                        "default": 1024,
                        "min": 1,
                        "max": 32768,
                        "tooltip": "Maximum reply tokens, including any reasoning.",
                    },
                ),
            },
            "optional": {
                "image_1": image,
                "image_2": image,
                "image_3": image,
                "image_4": image,
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    @classmethod
    def VALIDATE_INPUTS(cls, model):
        # The model list is populated from the server at runtime, so any
        # non-empty id is accepted here and verified by the server itself.
        if not isinstance(model, str) or not model.strip():
            return "model must be a model id or 'server default'"
        return True

    async def generate(
        self,
        master_prompt,
        request,
        skills,
        model,
        vram_policy,
        seed,
        temperature,
        max_tokens,
        unique_id=None,
        image_1=None,
        image_2=None,
        image_3=None,
        image_4=None,
    ):
        if vram_policy not in VRAM_POLICIES:
            raise PromptAssistantError(
                f"vram_policy must be one of {', '.join(VRAM_POLICIES)}"
            )
        _validate_text(master_prompt, "master_prompt")
        _validate_text(skills, "skills")
        config = await asyncio.to_thread(load_assistant_config)
        entries = parse_selection(skills)
        discovery = await asyncio.to_thread(
            discover_skills, config.skills_roots, config.skills
        )
        _log_warnings(discovery.warnings)
        attachments = await asyncio.to_thread(resolve_selection, entries, discovery)
        unattached = await asyncio.to_thread(
            unattached_references, attachments, discovery
        )
        attached = await asyncio.to_thread(read_attachments, attachments)
        system = build_system_message(master_prompt, attached, unattached)
        encoded = await asyncio.to_thread(
            encode_images, [image_1, image_2, image_3, image_4]
        )
        messages = build_messages(system, request, encoded)
        body = build_request_body(messages, model, seed, temperature, max_tokens)
        model_id = body.get("model")

        async with ServerClient(
            config.base_url, config.api_key, config.read_timeout
        ) as client:
            await client.health()
            if encoded:
                await client.check_vision(model_id)
            if vram_policy in {"share", "keep_llm_loaded"}:
                _log_warnings(
                    await asyncio.to_thread(release_comfy_models, _model_management())
                )
            prompt = await client.stream_chat(
                body,
                on_delta=lambda text: _send_progress(unique_id, text),
                check_interrupt=_interrupt_check(),
            )
            if vram_policy == "share":
                _log_warnings(await release_llm(client, model_id))
        return {"ui": {"text": [prompt]}, "result": (prompt,)}


async def prompt_assistant_models(_request):
    from aiohttp import web

    try:
        config = await asyncio.to_thread(load_assistant_config)
        async with ServerClient(
            config.base_url, config.api_key, config.read_timeout
        ) as client:
            models = await client.list_models()
    except PromptAssistantError as error:
        return web.json_response({"error": str(error)}, status=502)
    return web.json_response({"mode": models.mode, "models": list(models.models)})


async def prompt_assistant_skills(_request):
    from aiohttp import web

    try:
        config = await asyncio.to_thread(load_assistant_config)
        catalog = await asyncio.to_thread(skills_catalog, config)
    except PromptAssistantError as error:
        return web.json_response({"error": str(error)}, status=400)
    return web.json_response(catalog)


try:
    from server import PromptServer
except ModuleNotFoundError as error:
    if error.name != "server":
        raise
else:
    PromptServer.instance.routes.get("/lfgg/v1/prompt-assistant/models")(
        prompt_assistant_models
    )
    PromptServer.instance.routes.get("/lfgg/v1/prompt-assistant/skills")(
        prompt_assistant_skills
    )

__all__ = [
    "AssistantConfig",
    "PromptAssistant",
    "PromptAssistantError",
    "ServerClient",
    "build_messages",
    "build_request_body",
    "build_system_message",
    "encode_images",
    "discover_skills",
    "load_assistant_config",
    "parse_selection",
    "prompt_assistant_models",
    "prompt_assistant_skills",
    "read_attachments",
    "release_comfy_models",
    "release_llm",
    "resolve_selection",
    "skill_files",
    "skills_catalog",
    "validate_assistant_section",
]
