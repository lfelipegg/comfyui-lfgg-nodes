from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--archive",
        default="node.zip",
        help="Registry candidate archive to inspect",
    )
    parser.addoption(
        "--approved-release-manifest",
        help="Additionally require the exact immutable approved release manifest",
    )


@pytest.fixture
def archive_path(request):
    return Path(request.config.getoption("--archive")).resolve()


@pytest.fixture
def approved_release_manifest(request):
    value = request.config.getoption("--approved-release-manifest")
    return Path(value).resolve() if value else None
