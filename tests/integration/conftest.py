import pytest


def pytest_addoption(parser):
    parser.addoption("--comfy-ref", help="Exact stable ComfyUI tag to exercise")
    parser.addoption(
        "--installed-comfyui",
        help="Exact installed ComfyUI checkout to exercise",
    )
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


def pytest_configure(config):
    if config.getoption("--comfy-ref") and config.getoption("--installed-comfyui"):
        raise pytest.UsageError(
            "--comfy-ref and --installed-comfyui are mutually exclusive"
        )


@pytest.fixture
def integration_options(request):
    return {
        "comfy_ref": request.config.getoption("--comfy-ref"),
        "installed_comfyui": request.config.getoption("--installed-comfyui"),
        "device": request.config.getoption("--device"),
        "archive": request.config.getoption("--archive"),
    }
