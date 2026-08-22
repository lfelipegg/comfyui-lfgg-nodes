import asyncio
import csv
import hashlib
import io
import json
import random
import re
from pathlib import Path, PurePosixPath

CONFIG_LIMIT = 64 * 1024
STYLES_LIMIT = 4 * 1024 * 1024
CSV_FIELD_LIMIT = 128 * 1024
WILDCARD_LIMIT = 1024 * 1024
WILDCARD_TOTAL_LIMIT = 64 * 1024 * 1024
WILDCARD_COUNT_LIMIT = 10_000
OUTPUT_LIMIT = 1024 * 1024
_TOKEN = re.compile(
    r"\\(?P<escaped>__(?:(?!__).)+__|\[\[style:(?:(?!\]\]).)+\]\])"
    r"|__(?P<wildcard>(?:(?!__).)+)__"
    r"|\[\[style:(?P<style>(?:(?!\]\]).)+)\]\]"
)
_catalog_task = None


class PromptComposerError(ValueError):
    pass


def _read_bytes(path, limit, label):
    try:
        with path.open("rb") as source:
            content = source.read(limit + 1)
    except OSError:
        raise PromptComposerError(f"{label} is unavailable") from None
    if len(content) > limit:
        raise PromptComposerError(f"{label} exceeds its size limit")
    return content


def _decode(content, label):
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise PromptComposerError(f"{label} must be UTF-8") from None


def _reject_duplicate_json_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise PromptComposerError("configuration contains a repeated key")
        value[key] = item
    return value


def _resolve_configured_path(value, *, directory, label):
    if not isinstance(value, str) or not value or not Path(value).is_absolute():
        raise PromptComposerError(f"{label} must be an absolute path")
    try:
        path = Path(value).resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise PromptComposerError(f"{label} is unavailable") from None
    if (directory and not path.is_dir()) or (not directory and not path.is_file()):
        raise PromptComposerError(f"{label} has the wrong file type")
    return path


def _load_config():
    import folder_paths

    try:
        user_root = Path(folder_paths.get_user_directory()).resolve(strict=True)
        config_path = (user_root / "lfgg_nodes" / "config.json").resolve(strict=True)
        config_path.relative_to(user_root)
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        raise PromptComposerError(
            "prompt composer configuration is unavailable in the ComfyUI user directory"
        ) from None
    content = _read_bytes(config_path, CONFIG_LIMIT, "prompt composer configuration")
    try:
        config = json.loads(
            _decode(content, "prompt composer configuration"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except json.JSONDecodeError:
        raise PromptComposerError(
            "prompt composer configuration is not valid JSON"
        ) from None
    if not isinstance(config, dict) or set(config) != {"prompt_composer"}:
        raise PromptComposerError(
            "configuration must contain only the prompt_composer section"
        )
    section = config["prompt_composer"]
    if not isinstance(section, dict) or set(section) != {"styles_csv", "wildcards"}:
        raise PromptComposerError(
            "prompt_composer must contain only styles_csv and wildcards"
        )
    styles_path = _resolve_configured_path(
        section["styles_csv"], directory=False, label="styles CSV"
    )
    wildcard_root = _resolve_configured_path(
        section["wildcards"], directory=True, label="wildcard root"
    )
    return styles_path, wildcard_root, content


def _load_styles(path):
    content = _read_bytes(path, STYLES_LIMIT, "styles CSV")
    try:
        rows = csv.reader(
            io.StringIO(_decode(content, "styles CSV"), newline=""), strict=True
        )
        header = next(rows)
    except StopIteration:
        raise PromptComposerError("styles CSV must have a header") from None
    except csv.Error as error:
        if "field larger than field limit" in str(error):
            raise PromptComposerError(
                "styles CSV field exceeds the 128 KiB limit"
            ) from None
        raise PromptComposerError("styles CSV is malformed") from None
    if header != ["name", "prompt", "negative_prompt"]:
        raise PromptComposerError(
            "styles CSV header must be name,prompt,negative_prompt"
        )

    styles = []
    names = set()
    try:
        for row_number, row in enumerate(rows, 2):
            if not row or not any(row):
                continue
            if any(len(field.encode("utf-8")) > CSV_FIELD_LIMIT for field in row):
                raise PromptComposerError("styles CSV field exceeds the 128 KiB limit")
            if len(row) > 3:
                raise PromptComposerError(
                    f"styles CSV row {row_number} has too many columns"
                )
            row += [""] * (3 - len(row))
            name = row[0].strip()
            if not name:
                raise PromptComposerError(
                    f"styles CSV row {row_number} has an empty name"
                )
            if "]]" in name or any(character in name for character in "\x00\r\n"):
                raise PromptComposerError(
                    f"styles CSV row {row_number} has an unsupported name"
                )
            if name in names:
                raise PromptComposerError(f"styles CSV repeats style {name!r}")
            names.add(name)
            styles.append(
                {
                    "name": name,
                    "prompt": row[1],
                    "negative_prompt": row[2],
                    "disabled": not row[1].strip() and not row[2].strip(),
                }
            )
    except csv.Error as error:
        if "field larger than field limit" in str(error):
            raise PromptComposerError(
                "styles CSV field exceeds the 128 KiB limit"
            ) from None
        raise PromptComposerError("styles CSV is malformed") from None
    return styles, content


def _contained(path, root, label):
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        raise PromptComposerError(f"{label} escapes the wildcard root") from None
    return resolved


def _wildcard_lines(path, name):
    content = _read_bytes(path, WILDCARD_LIMIT, f"wildcard __{name}__")
    text = _decode(content, f"wildcard __{name}__")
    return [line.strip() for line in text.splitlines() if line.strip()], content


def _scan_wildcards(root):
    entries = []
    names = set()
    total = 0
    visited = 0
    stack = [(root, (), frozenset())]
    while stack:
        directory, relative, ancestors = stack.pop()
        resolved_directory = _contained(directory, root, "wildcard directory")
        if resolved_directory in ancestors:
            raise PromptComposerError("wildcard library contains a directory cycle")
        try:
            children = []
            for child in directory.iterdir():
                visited += 1
                if visited > WILDCARD_COUNT_LIMIT:
                    raise PromptComposerError(
                        "wildcard library exceeds its entry limit"
                    )
                children.append(child)
            children.sort(key=lambda path: (path.name.casefold(), path.name))
        except OSError:
            raise PromptComposerError("wildcard library is unavailable") from None
        next_ancestors = ancestors | {resolved_directory}
        directories = []
        for child in children:
            resolved = _contained(child, root, "wildcard entry")
            if resolved.is_dir():
                directories.append((child, (*relative, child.name), next_ancestors))
                continue
            if not resolved.is_file() or child.suffix.casefold() != ".txt":
                continue
            name = PurePosixPath(*relative, child.name[:-4]).as_posix()
            _wildcard_parts(name)
            if name in names:
                raise PromptComposerError(f"wildcard library repeats {name!r}")
            names.add(name)
            lines, content = _wildcard_lines(resolved, name)
            total += len(content)
            if total > WILDCARD_TOTAL_LIMIT:
                raise PromptComposerError(
                    "wildcard library exceeds its total size limit"
                )
            entries.append({"name": name, "disabled": not lines})
        stack.extend(reversed(directories))
    return sorted(entries, key=lambda item: (item["name"].casefold(), item["name"]))


def _wildcard_parts(name):
    if (
        not isinstance(name, str)
        or not name
        or "\\" in name
        or "__" in name
        or any(character in name for character in "\x00\r\n")
    ):
        raise PromptComposerError(f"invalid wildcard token __{name}__")
    path = PurePosixPath(name)
    if path.is_absolute() or path.as_posix() != name or any(
        part in {"", ".", ".."} for part in path.parts
    ):
        raise PromptComposerError(f"invalid wildcard token __{name}__")
    return path.parts


def _find_wildcard(root, name):
    parts = _wildcard_parts(name)
    current = root
    for part in parts[:-1]:
        try:
            matches = [child for child in current.iterdir() if child.name == part]
        except OSError:
            matches = []
        if len(matches) != 1:
            raise PromptComposerError(f"wildcard __{name}__ is unavailable")
        current = _contained(matches[0], root, f"wildcard __{name}__")
        if not current.is_dir():
            raise PromptComposerError(f"wildcard __{name}__ is unavailable")
    try:
        matches = [
            child
            for child in current.iterdir()
            if child.name[:-4] == parts[-1] and child.suffix.casefold() == ".txt"
        ]
    except OSError:
        matches = []
    if len(matches) != 1:
        raise PromptComposerError(f"wildcard __{name}__ is unavailable")
    path = _contained(matches[0], root, f"wildcard __{name}__")
    if not path.is_file():
        raise PromptComposerError(f"wildcard __{name}__ is unavailable")
    return path


def library_catalog():
    styles_path, wildcard_root, _ = _load_config()
    styles, _ = _load_styles(styles_path)
    return {
        "styles": [
            {"name": style["name"], "disabled": style["disabled"]}
            for style in styles
        ],
        "wildcards": _scan_wildcards(wildcard_root),
    }


def _validate_inputs(prompt_template, seed):
    if not isinstance(prompt_template, str):
        raise PromptComposerError("prompt_template must be a string")
    if len(prompt_template) > OUTPUT_LIMIT or len(
        prompt_template.encode("utf-8")
    ) > OUTPUT_LIMIT:
        raise PromptComposerError("prompt_template exceeds the 1 MiB limit")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**64:
        raise PromptComposerError("seed must be an unsigned 64-bit integer")


def _runtime_sources(prompt_template):
    styles_path, wildcard_root, config_content = _load_config()
    styles, styles_content = _load_styles(styles_path)
    wildcard_sources = {}
    wildcard_bytes = 0
    for match in _TOKEN.finditer(prompt_template):
        name = match.group("wildcard")
        if name is not None and name not in wildcard_sources:
            path = _find_wildcard(wildcard_root, name)
            wildcard_sources[name] = _wildcard_lines(path, name)
            wildcard_bytes += len(wildcard_sources[name][1])
            if len(wildcard_sources) > WILDCARD_COUNT_LIMIT:
                raise PromptComposerError("prompt exceeds its wildcard file limit")
            if wildcard_bytes > WILDCARD_TOTAL_LIMIT:
                raise PromptComposerError(
                    "referenced wildcards exceed their total size limit"
                )
    return styles, wildcard_sources, config_content, styles_content


class PromptComposer:
    DESCRIPTION = (
        "Composes positioned style and file-wildcard tokens from configured local "
        "libraries with reproducible wildcard choices."
    )
    CATEGORY = "LFGG/text"
    FUNCTION = "compose"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("prompt", "negative_prompt")
    OUTPUT_TOOLTIPS = (
        "Resolved positive prompt in the authored token order.",
        "Negative style fragments joined in token order.",
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt_template": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "dynamicPrompts": True,
                        "placeholder": "Write a prompt and insert styles or wildcards…",
                        "tooltip": (
                            "Prompt template. File wildcards use __folder/name__; "
                            "styles use [[style:Exact Name]]."
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
                        "tooltip": "Seed for reproducible file-wildcard choices.",
                    },
                ),
            }
        }

    def compose(self, prompt_template, seed):
        _validate_inputs(prompt_template, seed)
        styles, wildcard_sources, _, _ = _runtime_sources(prompt_template)
        style_map = {style["name"]: style for style in styles}
        negative = []
        negative_size = 0
        generator = random.Random(seed)

        def replace(match):
            nonlocal negative_size
            escaped = match.group("escaped")
            if escaped is not None:
                return escaped
            wildcard = match.group("wildcard")
            if wildcard is not None:
                lines, _ = wildcard_sources[wildcard]
                if not lines:
                    raise PromptComposerError(f"wildcard __{wildcard}__ is empty")
                return generator.choice(lines)
            name = match.group("style")
            style = style_map.get(name)
            if style is None:
                raise PromptComposerError(f"style [[style:{name}]] is unavailable")
            if style["disabled"]:
                raise PromptComposerError(f"style [[style:{name}]] is a heading")
            fragment = style["negative_prompt"].strip(" \t\r\n,")
            if fragment:
                negative_size += len(fragment.encode("utf-8")) + (
                    2 if negative else 0
                )
                if negative_size > OUTPUT_LIMIT:
                    raise PromptComposerError(
                        "resolved prompt exceeds the 1 MiB limit"
                    )
                negative.append(fragment)
            return style["prompt"]

        parts = []
        prompt_size = 0
        cursor = 0
        for match in _TOKEN.finditer(prompt_template):
            for fragment in (prompt_template[cursor : match.start()], replace(match)):
                prompt_size += len(fragment.encode("utf-8"))
                if prompt_size + negative_size > OUTPUT_LIMIT:
                    raise PromptComposerError(
                        "resolved prompt exceeds the 1 MiB limit"
                    )
                parts.append(fragment)
            cursor = match.end()
        tail = prompt_template[cursor:]
        prompt_size += len(tail.encode("utf-8"))
        if prompt_size + negative_size > OUTPUT_LIMIT:
            raise PromptComposerError("resolved prompt exceeds the 1 MiB limit")
        parts.append(tail)
        prompt = "".join(parts)
        negative_prompt = ", ".join(negative)
        return prompt, negative_prompt

    @classmethod
    def IS_CHANGED(cls, prompt_template, seed):
        try:
            _validate_inputs(prompt_template, seed)
            _, wildcard_sources, config_content, styles_content = _runtime_sources(
                prompt_template
            )
        except PromptComposerError as error:
            return f"error:{error}"
        digest = hashlib.sha256(config_content)
        digest.update(styles_content)
        for name, (_, content) in wildcard_sources.items():
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(content)
        return digest.hexdigest()


async def _load_catalog():
    global _catalog_task

    try:
        return await asyncio.to_thread(library_catalog)
    finally:
        _catalog_task = None


async def prompt_composer_libraries(_request):
    from aiohttp import web

    global _catalog_task
    try:
        if _catalog_task is None:
            _catalog_task = asyncio.create_task(_load_catalog())
        catalog = await asyncio.shield(_catalog_task)
        return web.json_response({"ok": True, **catalog})
    except PromptComposerError as error:
        return web.json_response({"ok": False, "error": str(error)}, status=400)


try:
    from server import PromptServer
except ModuleNotFoundError as error:
    if error.name != "server":
        raise
else:
    PromptServer.instance.routes.get("/lfgg/v1/prompt-composer/libraries")(
        prompt_composer_libraries
    )


__all__ = ["PromptComposer", "PromptComposerError", "library_catalog"]
