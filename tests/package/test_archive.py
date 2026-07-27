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
    "lfgg_nodes/sizing.py",
    "pyproject.toml",
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
            archive.writestr(name, content)


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
    expected_manifest = Path(__file__).parents[2] / "release" / "1.0.0-archive.sha256"
    assert expected_manifest.exists(), "approved archive manifest is not implemented"
    assert archive_tools().format_manifest(entries) == expected_manifest.read_text()


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
