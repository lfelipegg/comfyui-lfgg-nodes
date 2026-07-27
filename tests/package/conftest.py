from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--archive",
        default="node.zip",
        help="Registry candidate archive to inspect",
    )


@pytest.fixture
def archive_path(request):
    return Path(request.config.getoption("--archive")).resolve()
