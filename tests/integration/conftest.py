import pytest


def pytest_addoption(parser):
    parser.addoption("--comfy-ref", help="Exact stable ComfyUI tag to exercise")
    parser.addoption(
        "--device",
        choices=("cpu", "cuda"),
        help="ComfyUI execution device",
    )
    parser.addoption(
        "--archive",
        default="node.zip",
        help="Registry candidate archive to install",
    )


@pytest.fixture
def integration_options(request):
    return {
        "comfy_ref": request.config.getoption("--comfy-ref"),
        "device": request.config.getoption("--device"),
        "archive": request.config.getoption("--archive"),
    }
