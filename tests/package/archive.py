import stat
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

MAX_MEMBERS = 1000
MAX_MEMBER_BYTES = 5 * 1024 * 1024
MAX_TOTAL_BYTES = 10 * 1024 * 1024
FORBIDDEN_NAMES = {
    ".env",
    ".git",
    ".github",
    ".pytest_cache",
    ".ruff_cache",
    "AGENTS.md",
    "CONTEXT.md",
    "__pycache__",
    "build",
    "coverage.xml",
    "dist",
    "docs",
    "node.zip",
    "reference",
    "release",
    "tests",
}


@dataclass(frozen=True)
class ArchiveEntry:
    path: str
    sha256: str
    size: int


def _safe_path(name):
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or any(part in {"", ".", ".."} for part in path.parts)
        or (path.parts and path.parts[0].endswith(":"))
    ):
        raise ValueError(f"unsafe archive path: {name}")
    return path


def _forbidden(path):
    return any(
        part in FORBIDDEN_NAMES or part.endswith(".egg-info")
        for part in path.parts
    )


def inspect_archive(archive_path, *, extract_to=None):
    entries = []
    seen = set()
    total_bytes = 0

    with ZipFile(archive_path) as archive:
        members = archive.infolist()
        if len(members) > MAX_MEMBERS:
            raise ValueError("archive size limit exceeded")

        inspected = []
        for member in members:
            path = _safe_path(member.filename)
            normalized = path.as_posix()
            if normalized in seen:
                raise ValueError(f"duplicate archive path: {normalized}")
            seen.add(normalized)

            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError(f"symlink archive member: {normalized}")
            if member.is_dir():
                continue
            if _forbidden(path):
                raise ValueError(f"forbidden archive member: {normalized}")

            total_bytes += member.file_size
            if (
                member.file_size > MAX_MEMBER_BYTES
                or total_bytes > MAX_TOTAL_BYTES
            ):
                raise ValueError("archive size limit exceeded")
            inspected.append((member, path))

        destination = Path(extract_to).resolve() if extract_to is not None else None
        if destination is not None:
            destination.mkdir(parents=True, exist_ok=True)

        for member, path in inspected:
            content = archive.read(member)
            entries.append(
                ArchiveEntry(
                    path=path.as_posix(),
                    sha256=sha256(content).hexdigest(),
                    size=len(content),
                )
            )
            if destination is not None:
                target = (destination / path.as_posix()).resolve()
                if not target.is_relative_to(destination):
                    raise ValueError(f"unsafe archive path: {path}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as output:
                    output.write(content)

    return sorted(entries, key=lambda entry: entry.path)


def format_manifest(entries):
    return "".join(f"{entry.sha256}  {entry.path}\n" for entry in entries)
