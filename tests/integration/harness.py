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
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

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


def redact(text, *, secrets=(), metadata=(), paths=()):
    replacements = [str(value) for value in (*secrets, *metadata) if value]
    for path in paths:
        value = str(path)
        replacements.extend((value, value.replace("\\", "/"), value.replace("/", "\\")))
    replacements = sorted(set(replacements), key=len, reverse=True)
    for value in replacements:
        text = text.replace(value, "<redacted>")
    assert not any(value in text for value in replacements), (
        "protected disclosure remained after redaction"
    )
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
    host = parsed.hostname
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("Registry download URL must be public HTTPS")
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    resolved = [ip_address(address[4][0]) for address in addresses]
    if not resolved or any(
        not address.is_global
        or address.is_multicast
        or (address.version == 6 and address.is_site_local)
        for address in resolved
    ):
        raise ValueError("Registry download URL must be public HTTPS")
    return url


class _PublicHTTPSRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        _public_https_url(new_url)
        return super().redirect_request(
            request,
            file,
            code,
            message,
            headers,
            new_url,
        )


_REGISTRY_OPENER = build_opener(_PublicHTTPSRedirectHandler())


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
            _public_https_url(api_url)
            with _REGISTRY_OPENER.open(api_url, timeout=HTTP_TIMEOUT) as response:
                _public_https_url(response.geturl())
                record = json.loads(
                    _read_limited(response, MAX_REGISTRY_RESPONSE_BYTES)
                )
            if not isinstance(record, dict) or record.get("version") != version:
                raise LookupError(f"Registry version {version} is not active")
            download_url = _public_https_url(record.get("downloadUrl"))
            break
        except (
            OSError,
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
        with _REGISTRY_OPENER.open(download_url, timeout=HTTP_TIMEOUT) as response:
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


def _failure_log(log_path, workspace, *, metadata=()):
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
    return redact(text, secrets=secrets, metadata=metadata, paths=[workspace])


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
    credentials = [
        os.environ.get(name)
        for name in (
            "REGISTRY_ACCESS_TOKEN",
            "COMFY_API_KEY",
            "COMFY_CLOUD_API_KEY",
            "GITHUB_TOKEN",
        )
    ]
    serialized_workflow = json.dumps(workflow, sort_keys=True)
    disclosures = {
        "secrets": credentials,
        "metadata": [serialized_workflow],
        "paths": [workspace],
    }
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
        redact(json.dumps(object_info, sort_keys=True), **disclosures)
        assert_object_info_matches_manifest(object_info, manifest)

        submitted = _request_json(base_url, "/prompt", payload={"prompt": workflow})
        serialized_submission = redact(
            json.dumps(submitted, sort_keys=True),
            **disclosures,
        )
        if "error" in submitted or submitted.get("node_errors"):
            raise AssertionError(f"workflow rejected: {serialized_submission}")
        prompt_id = submitted["prompt_id"]
        history = _wait_for_history(base_url, prompt_id)
        serialized_history = redact(
            json.dumps(history, sort_keys=True),
            **disclosures,
        )
        if not history_succeeded(history):
            raise AssertionError(f"workflow failed: {serialized_history}")

        output_root = output.resolve()
        files = sorted(
            path.resolve()
            for path in output.rglob("*.latent")
            if path.resolve().is_relative_to(output_root)
        )
        described_files = []
        for node_output in history.get("outputs", {}).values():
            for descriptor in node_output.get("latents", ()):
                assert descriptor.get("type") == "output", (
                    "SaveLatent descriptor is not an output"
                )
                path = (
                    output_root
                    / descriptor.get("subfolder", "")
                    / descriptor["filename"]
                ).resolve()
                assert path.is_relative_to(output_root), (
                    "SaveLatent descriptor escaped the output root"
                )
                described_files.append(path)
        assert sorted(described_files) == files, (
            "SaveLatent descriptors do not match confined output files"
        )
        assert all(path.stat().st_size > 0 for path in files), (
            "SaveLatent produced an empty file"
        )

        shape_reader = """
import json
import sys
from safetensors import safe_open

shapes = []
for filename in sys.argv[1:]:
    with safe_open(filename, framework="pt", device="cpu") as tensors:
        shapes.append(list(tensors.get_slice("latent_tensor").get_shape()))
print(json.dumps(shapes))
"""
        shapes = json.loads(
            _run(
                [str(python), "-c", shape_reader, *(str(path) for path in files)]
            ).stdout
        )
        relative_files = [path.relative_to(output_root).as_posix() for path in files]
        output_shapes = dict(zip(relative_files, shapes, strict=True))
        _failure_log(log_path, workspace, metadata=[serialized_workflow])
        return {
            "registered_ids": sorted(manifest["nodes"]),
            "output_files": relative_files,
            "output_shapes": output_shapes,
        }
    except Exception as error:
        logs = _failure_log(log_path, workspace, metadata=[serialized_workflow])
        if logs:
            safe_error = redact(str(error), **disclosures)
            raise AssertionError(f"{safe_error}\nComfyUI log:\n{logs}") from error
        raise
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
