import os
import stat
import subprocess
import sys
import warnings
from importlib import import_module
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

EXPECTED_PATHS = {
    "LICENSE",
    "README.md",
    "__init__.py",
    "lfgg_nodes/__init__.py",
    "lfgg_nodes/dimensions_by_aspect_ratio.py",
    "lfgg_nodes/image_dimensions.py",
    "lfgg_nodes/save_image_dynamic.py",
    "lfgg_nodes/sizing.py",
    "pyproject.toml",
    "web/ratio_preview.js",
    "web/ratio_preview.mjs",
    "workflows/save_image_dynamic.json",
    "workflows/sizing.json",
}


def archive_tools():
    try:
        return import_module("tests.package.archive")
    except ModuleNotFoundError:
        pytest.fail("safe archive inspection is not implemented")


def write_zip(path, members):
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, content in members:
            member = ZipInfo(name)
            member.create_system = 3
            member.compress_type = ZIP_DEFLATED
            member.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(member, content)


@pytest.mark.parametrize(
    "member",
    [
        "/absolute.py",
        "../traversal.py",
        "nested/../../traversal.py",
        r"..\windows-traversal.py",
        "C:/windows-absolute.py",
    ],
)
def test_rejects_absolute_and_traversal_members(tmp_path, member):
    candidate = tmp_path / "unsafe.zip"
    write_zip(candidate, [(member, b"unsafe")])

    with pytest.raises(ValueError, match="unsafe archive path"):
        archive_tools().inspect_archive(candidate)


def test_rejects_duplicate_normalized_members(tmp_path):
    candidate = tmp_path / "duplicate.zip"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        write_zip(candidate, [("nested/file.py", b"a"), (r"nested\file.py", b"b")])

    with pytest.raises(ValueError, match="duplicate archive path"):
        archive_tools().inspect_archive(candidate)


def test_rejects_symlink_members(tmp_path):
    candidate = tmp_path / "symlink.zip"
    link = ZipInfo("link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with ZipFile(candidate, "w") as archive:
        archive.writestr(link, "target")

    with pytest.raises(ValueError, match="symlink"):
        archive_tools().inspect_archive(candidate)


def test_rejects_nonzero_mode_without_member_type(tmp_path):
    candidate = tmp_path / "ambiguous-type.zip"
    member = ZipInfo("ambiguous")
    member.create_system = 3
    member.external_attr = 0o644 << 16
    with ZipFile(candidate, "w") as archive:
        archive.writestr(member, b"ambiguous")

    with pytest.raises(ValueError, match="unsafe archive member type: ambiguous"):
        archive_tools().inspect_archive(candidate)


def test_rejects_member_limit(tmp_path, monkeypatch):
    candidate = tmp_path / "members.zip"
    write_zip(candidate, [("one.py", b"1"), ("two.py", b"2")])
    monkeypatch.setattr(archive_tools(), "MAX_MEMBERS", 1)

    with pytest.raises(ValueError, match="archive size limit"):
        archive_tools().inspect_archive(candidate)


def test_rejects_total_limit(tmp_path, monkeypatch):
    candidate = tmp_path / "total.zip"
    write_zip(candidate, [("one.py", b"12"), ("two.py", b"34")])
    monkeypatch.setattr(archive_tools(), "MAX_TOTAL_BYTES", 3)

    with pytest.raises(ValueError, match="archive size limit"):
        archive_tools().inspect_archive(candidate)


@pytest.mark.parametrize(
    "mode", [stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR, stat.S_IFBLK]
)
def test_rejects_unsafe_member_type(tmp_path, mode):
    candidate = tmp_path / "unsafe-type.zip"
    member = ZipInfo("unsafe")
    member.create_system = 3
    member.external_attr = (mode | 0o644) << 16
    with ZipFile(candidate, "w") as archive:
        archive.writestr(member, b"unsafe")

    with pytest.raises(ValueError, match="unsafe archive member type: unsafe"):
        archive_tools().inspect_archive(candidate)


@pytest.mark.parametrize(
    "member",
    [
        ".env",
        ".git/config",
        "AGENTS.md",
        "docs/private.md",
        "tests/test_private.py",
        "__pycache__/cache.pyc",
        "coverage.xml",
    ],
)
def test_rejects_development_or_private_members(tmp_path, member):
    candidate = tmp_path / "private.zip"
    write_zip(candidate, [(member, b"private")])

    with pytest.raises(ValueError, match="forbidden archive member"):
        archive_tools().inspect_archive(candidate)


def test_rejects_oversized_archives(tmp_path):
    candidate = tmp_path / "large.zip"
    write_zip(candidate, [("large.bin", b"x" * (5 * 1024 * 1024 + 1))])

    with pytest.raises(ValueError, match="archive size limit"):
        archive_tools().inspect_archive(candidate)


def test_extracts_only_after_every_member_passes_inspection(tmp_path):
    candidate = tmp_path / "safe.zip"
    destination = tmp_path / "extracted"
    write_zip(candidate, [("package/module.py", b"VALUE = 1\n")])

    entries = archive_tools().inspect_archive(candidate, extract_to=destination)

    assert [entry.path for entry in entries] == ["package/module.py"]
    assert (destination / "package" / "module.py").read_bytes() == b"VALUE = 1\n"


def test_candidate_matches_the_approved_content_manifest(archive_path):
    assert archive_path.exists(), f"candidate archive not found: {archive_path}"

    entries = archive_tools().inspect_archive(archive_path)
    assert {entry.path for entry in entries} == EXPECTED_PATHS
    expected_manifest = Path(__file__).parents[2] / "release" / "1.2.0-archive.sha256"
    assert expected_manifest.exists(), "approved archive manifest is not implemented"
    assert archive_tools().format_manifest(entries) == expected_manifest.read_text()


def test_candidate_has_no_sensitive_content(archive_path):
    assert archive_path.exists(), f"candidate archive not found: {archive_path}"
    archive_tools().inspect_archive(archive_path)
    with ZipFile(archive_path) as archive:
        content = b"".join(archive.read(member) for member in archive.infolist())

    assert str(Path(__file__).parents[2].resolve()).encode() not in content
    for name in (
        "REGISTRY_ACCESS_TOKEN",
        "COMFY_API_KEY",
        "COMFY_CLOUD_API_KEY",
        "GITHUB_TOKEN",
    ):
        if value := os.environ.get(name):
            assert value.encode() not in content


def test_sensitive_scan_validates_before_reading_members(tmp_path, monkeypatch):
    candidate = tmp_path / "oversized.zip"
    write_zip(candidate, [("oversized.bin", b"12")])
    monkeypatch.setattr(archive_tools(), "MAX_MEMBER_BYTES", 1)
    original_read = ZipFile.read
    reads = []

    def record_read(archive, member, *args, **kwargs):
        reads.append(member)
        return original_read(archive, member, *args, **kwargs)

    monkeypatch.setattr(ZipFile, "read", record_read)

    with pytest.raises(ValueError, match="archive size limit"):
        test_candidate_has_no_sensitive_content(candidate)

    assert reads == []


def test_candidate_builds_and_installs_non_editably(archive_path, tmp_path):
    tools = archive_tools()
    extracted = tmp_path / "source"
    tools.inspect_archive(archive_path, extract_to=extracted)
    wheels = tmp_path / "wheels"
    wheels.mkdir()

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-build-isolation",
            "--no-deps",
            "--wheel-dir",
            str(wheels),
            str(extracted),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    environment = tmp_path / "environment"
    subprocess.run(
        [sys.executable, "-m", "venv", str(environment)],
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(wheels.glob("*.whl"))
    python_path = "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    python = environment / python_path
    subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", str(wheel)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [str(python), "-c", "import lfgg_nodes.sizing"],
        check=True,
        capture_output=True,
        text=True,
    )
