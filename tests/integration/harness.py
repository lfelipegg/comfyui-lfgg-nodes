import json
import os
import re
import socket
import subprocess
import sys
import time
from ipaddress import ip_address
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from tests.package.archive import inspect_archive

COMFYUI_REPOSITORY = "https://github.com/Comfy-Org/ComfyUI.git"
COMMAND_TIMEOUT = 1800
HTTP_TIMEOUT = 15
STARTUP_TIMEOUT = 180
WORKFLOW_TIMEOUT = 180
MAX_REGISTRY_RESPONSE_BYTES = 64 * 1024
MAX_ARCHIVE_BYTES = 10 * 1024 * 1024


def validate_comfy_ref(ref):
    if not isinstance(ref, str) or re.fullmatch(r"v\d+\.\d+\.\d+", ref) is None:
        raise ValueError("ComfyUI ref must be an exact stable tag such as v0.28.0")
    return ref


def reserve_loopback_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def assert_object_info_matches_manifest(object_info, manifest):
    actual_ids = sorted(
        node_id for node_id in object_info if node_id.startswith("LFGG_")
    )
    expected_ids = sorted(manifest["nodes"])
    assert actual_ids == expected_ids, "registered LFGG IDs do not match manifest"

    fields = (
        "display_name",
        "description",
        "category",
        "input",
        "output",
        "output_name",
        "output_tooltips",
    )
    for node_id, expected in manifest["nodes"].items():
        actual = object_info[node_id]
        for section, inputs in expected["input"].items():
            assert actual["input_order"][section] == list(inputs), (
                f"{node_id} {section} input order does not match manifest"
            )
        for field in fields:
            assert actual[field] == expected[field], (
                f"{node_id} {field} does not match manifest"
            )


def redact(text, *, secrets=(), paths=()):
    replacements = [str(secret) for secret in secrets if secret]
    for path in paths:
        value = str(path)
        replacements.extend((value, value.replace("\\", "/"), value.replace("/", "\\")))
    for value in sorted(set(replacements), key=len, reverse=True):
        text = text.replace(value, "<redacted>")
    return text


def history_succeeded(history):
    status = history.get("status", {})
    return status.get("completed") is True and status.get("status_str") == "success"


def _public_https_url(url):
    if not isinstance(url, str):
        raise ValueError("Registry download URL must be public HTTPS")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Registry download URL must be public HTTPS")
    try:
        address = ip_address(parsed.hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("Registry download URL must be public HTTPS")
    return url


def _read_limited(response, limit):
    content_length = response.headers.get("Content-Length")
    if content_length is not None:
        try:
            content_length = int(content_length)
        except ValueError as error:
            raise ValueError("Registry returned an invalid Content-Length") from error
        if content_length < 0:
            raise ValueError("Registry returned an invalid Content-Length")
        if content_length > limit:
            raise ValueError("Registry response is too large")
    body = response.read(limit + 1)
    if len(body) > limit:
        raise ValueError("Registry response is too large")
    return body


def download_registry_archive(
    node_id,
    version,
    destination,
    *,
    timeout_seconds=180,
):
    if (
        not isinstance(node_id, str)
        or re.fullmatch(r"[a-z0-9][a-z0-9-]*", node_id) is None
    ):
        raise ValueError("Registry node ID is invalid")
    if not isinstance(version, str) or re.fullmatch(r"\d+\.\d+\.\d+", version) is None:
        raise ValueError("Registry version must be exact SemVer")

    api_url = f"https://api.comfy.org/nodes/{node_id}/install?version={version}"
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            with urlopen(api_url, timeout=HTTP_TIMEOUT) as response:
                _public_https_url(response.geturl())
                record = json.loads(
                    _read_limited(response, MAX_REGISTRY_RESPONSE_BYTES)
                )
            if not isinstance(record, dict) or record.get("version") != version:
                raise LookupError(f"Registry version {version} is not active")
            download_url = _public_https_url(record.get("downloadUrl"))
            break
        except (
            HTTPError,
            URLError,
            TimeoutError,
            LookupError,
            json.JSONDecodeError,
        ) as error:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Registry version {node_id} {version} did not become active"
                ) from error
            time.sleep(1)

    destination = Path(destination)
    created = False
    try:
        with urlopen(download_url, timeout=HTTP_TIMEOUT) as response:
            _public_https_url(response.geturl())
            archive = _read_limited(response, MAX_ARCHIVE_BYTES)
        with destination.open("xb") as file:
            created = True
            file.write(archive)
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise
    return destination


def _run(command, *, cwd=None):
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT,
    )


def _environment_python(environment):
    executable = "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    return environment / executable


def _request_json(base_url, path, *, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    request = Request(
        f"{base_url}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="GET" if body is None else "POST",
    )
    with urlopen(request, timeout=HTTP_TIMEOUT) as response:
        return json.load(response)


def _wait_for_server(base_url):
    deadline = time.monotonic() + STARTUP_TIMEOUT
    last_error = None
    while time.monotonic() < deadline:
        try:
            return _request_json(base_url, "/object_info")
        except (HTTPError, URLError, TimeoutError, ConnectionError) as error:
            last_error = error
            time.sleep(0.25)
    raise TimeoutError(f"ComfyUI did not start: {last_error}")


def _wait_for_history(base_url, prompt_id):
    deadline = time.monotonic() + WORKFLOW_TIMEOUT
    while time.monotonic() < deadline:
        history = _request_json(base_url, f"/history/{prompt_id}")
        if prompt_id in history:
            return history[prompt_id]
        time.sleep(0.25)
    raise TimeoutError(f"workflow did not finish: {prompt_id}")


def _install_comfyui(python, checkout, device):
    pip = [str(python), "-m", "pip"]
    _run([*pip, "install", "--upgrade", "pip", "setuptools", "wheel"])
    if device == "cpu":
        _run(
            [
                *pip,
                "install",
                "torch",
                "torchvision",
                "torchaudio",
                "--index-url",
                "https://download.pytorch.org/whl/cpu",
            ]
        )
    _run([*pip, "install", "-r", str(checkout / "requirements.txt")])


def _failure_log(log_path, workspace):
    if not log_path.exists():
        return ""
    text = log_path.read_text(errors="replace")[-16_000:]
    secrets = [
        os.environ.get(name)
        for name in (
            "REGISTRY_ACCESS_TOKEN",
            "COMFY_API_KEY",
            "COMFY_CLOUD_API_KEY",
            "GITHUB_TOKEN",
        )
    ]
    return redact(text, secrets=secrets, paths=[workspace])


def run_packed_comfyui(
    *,
    comfy_ref,
    archive,
    device,
    workspace,
    manifest,
    workflow,
):
    validate_comfy_ref(comfy_ref)
    if device not in {"cpu", "cuda"}:
        raise ValueError("device must be cpu or cuda")

    workspace = Path(workspace).resolve()
    checkout = workspace / "ComfyUI"
    environment = workspace / "environment"
    custom_node = checkout / "custom_nodes" / "lfgg-nodes"
    output = workspace / "output"
    input_directory = workspace / "input"
    temp_directory = workspace / "temp"
    user_directory = workspace / "user"
    log_path = workspace / "comfyui.log"
    for directory in (output, input_directory, temp_directory, user_directory):
        directory.mkdir(parents=True, exist_ok=True)

    _run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            comfy_ref,
            COMFYUI_REPOSITORY,
            str(checkout),
        ]
    )
    _run([sys.executable, "-m", "venv", str(environment)])
    python = _environment_python(environment)
    _install_comfyui(python, checkout, device)
    inspect_archive(archive, extract_to=custom_node)
    _run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--no-build-isolation",
            str(custom_node),
        ]
    )
    if device == "cuda":
        _run(
            [
                str(python),
                "-c",
                "import torch; assert torch.cuda.is_available(), 'CUDA unavailable'",
            ]
        )

    port = reserve_loopback_port()
    base_url = f"http://127.0.0.1:{port}"
    command = [
        str(python),
        "main.py",
        "--disable-auto-launch",
        "--disable-api-nodes",
        "--listen",
        "127.0.0.1",
        "--port",
        str(port),
        "--input-directory",
        str(input_directory),
        "--output-directory",
        str(output),
        "--temp-directory",
        str(temp_directory),
        "--user-directory",
        str(user_directory),
        "--database-url",
        "sqlite:///:memory:",
        "--log-stdout",
    ]
    if device == "cpu":
        command.append("--cpu")
    else:
        command.extend(("--cuda-device", "0"))

    server_environment = os.environ.copy()
    for name in (
        "REGISTRY_ACCESS_TOKEN",
        "COMFY_API_KEY",
        "COMFY_CLOUD_API_KEY",
        "GITHUB_TOKEN",
    ):
        server_environment.pop(name, None)

    process = None
    try:
        with log_path.open("w") as log:
            process = subprocess.Popen(
                command,
                cwd=checkout,
                env=server_environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
        object_info = _wait_for_server(base_url)
        assert_object_info_matches_manifest(object_info, manifest)
        serialized_info = json.dumps(object_info)
        assert str(workspace) not in serialized_info

        submitted = _request_json(base_url, "/prompt", payload={"prompt": workflow})
        if "error" in submitted or submitted.get("node_errors"):
            raise AssertionError(f"workflow rejected: {submitted}")
        prompt_id = submitted["prompt_id"]
        history = _wait_for_history(base_url, prompt_id)
        if not history_succeeded(history):
            raise AssertionError(f"workflow failed: {history.get('status')}")
        assert str(workspace) not in json.dumps(history)

        files = sorted(
            path.relative_to(output).as_posix()
            for path in output.rglob("*.latent")
            if path.resolve().is_relative_to(output.resolve())
        )
        return {
            "registered_ids": sorted(manifest["nodes"]),
            "output_files": files,
        }
    except Exception as error:
        logs = _failure_log(log_path, workspace)
        if logs:
            raise AssertionError(f"{error}\nComfyUI log:\n{logs}") from error
        raise
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
