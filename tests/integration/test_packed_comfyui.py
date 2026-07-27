import json
import socket
import traceback
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[2]


def harness():
    try:
        return import_module("tests.integration.harness")
    except ModuleNotFoundError:
        pytest.fail("packed ComfyUI harness is not implemented")


@pytest.mark.parametrize("ref", ["master", "v0.28", "v0.28.0;echo unsafe"])
def test_rejects_non_release_comfyui_refs(ref):
    with pytest.raises(ValueError, match="exact stable tag"):
        harness().validate_comfy_ref(ref)


def test_accepts_an_exact_comfyui_release_tag():
    assert harness().validate_comfy_ref("v0.28.0") == "v0.28.0"


def test_registers_installed_comfyui_option():
    options = []

    class Parser:
        def addoption(self, *names, **settings):
            options.append((names, settings))

    import_module("tests.integration.conftest").pytest_addoption(Parser())

    assert any(names == ("--installed-comfyui",) for names, _ in options)


def test_rejects_installed_comfyui_with_comfy_ref():
    class Config:
        @staticmethod
        def getoption(name):
            return {
                "--comfy-ref": "v0.28.0",
                "--installed-comfyui": "/tmp/ComfyUI",
            }[name]

    with pytest.raises(pytest.UsageError, match="mutually exclusive"):
        import_module("tests.integration.conftest").pytest_configure(Config())


def _stub_installed_checkout(monkeypatch, tmp_path, *, tag="v0.28.0", root=None):
    checkout = tmp_path / "ComfyUI"
    (checkout / "custom_nodes" / "lfgg-nodes").mkdir(parents=True)
    python = checkout / ".venv" / (
        "Scripts/python.exe" if harness().sys.platform == "win32" else "bin/python"
    )
    python.parent.mkdir(parents=True)
    python.write_bytes(b"")
    python.chmod(0o755)

    def git_result(command, *, cwd=None):
        assert cwd is None
        if command[-1] == "--show-toplevel":
            return SimpleNamespace(stdout=f"{root or checkout}\n")
        if command[-2:] == ["--exact-match", "HEAD"]:
            return SimpleNamespace(stdout=f"{tag}\n")
        raise AssertionError(command)

    monkeypatch.setattr(harness(), "_run", git_result)
    return checkout, python


def test_validates_exact_installed_comfyui_checkout(monkeypatch, tmp_path):
    checkout, python = _stub_installed_checkout(monkeypatch, tmp_path)

    assert harness()._validate_installed_comfyui(checkout) == (
        checkout.resolve(),
        python,
    )


@pytest.mark.parametrize(
    ("tag", "root"),
    [
        ("v0.28.1", None),
        ("v0.28.0", "parent"),
    ],
)
def test_rejects_wrong_installed_comfyui_checkout(
    monkeypatch,
    tmp_path,
    tag,
    root,
):
    checkout, _ = _stub_installed_checkout(
        monkeypatch,
        tmp_path,
        tag=tag,
        root=tmp_path if root else None,
    )

    with pytest.raises(ValueError, match="exact v0.28.0 checkout"):
        harness()._validate_installed_comfyui(checkout)


def test_rejects_escaped_installed_comfyui_environment(monkeypatch, tmp_path):
    checkout, python = _stub_installed_checkout(
        monkeypatch,
        tmp_path / "workspace",
    )
    outside = tmp_path / "outside-environment"
    python.parent.parent.rename(outside)
    python.parent.parent.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="contained environment Python"):
        harness()._validate_installed_comfyui(checkout)


def test_rejects_escaped_installed_custom_nodes_root(monkeypatch, tmp_path):
    checkout, _ = _stub_installed_checkout(monkeypatch, tmp_path)
    custom_nodes = checkout / "custom_nodes"
    outside = tmp_path / "outside-custom-nodes"
    custom_nodes.rename(outside)
    custom_nodes.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="installed node beneath custom_nodes"):
        harness()._validate_installed_comfyui(checkout)


def test_rejects_escaped_installed_custom_node(monkeypatch, tmp_path):
    checkout, _ = _stub_installed_checkout(monkeypatch, tmp_path)
    custom_node = checkout / "custom_nodes" / "lfgg-nodes"
    outside = tmp_path / "outside-node"
    custom_node.rename(outside)
    custom_node.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="installed node beneath custom_nodes"):
        harness()._validate_installed_comfyui(checkout)


def test_installed_comfyui_reuses_server_runner(monkeypatch, tmp_path):
    checkout, python = _stub_installed_checkout(monkeypatch, tmp_path)
    expected = {"registered_ids": ["LFGG_Test"]}
    exercised = []
    monkeypatch.setattr(
        harness(),
        "_exercise_comfyui",
        lambda **arguments: exercised.append(arguments) or expected,
    )

    result = harness().run_installed_comfyui(
        installed_comfyui=checkout,
        device="cpu",
        workspace=tmp_path / "exercise",
        manifest={"nodes": {"LFGG_Test": {}}},
        workflows={"test": {"1": {"class_type": "LFGG_Test"}}},
    )

    assert result == expected
    assert exercised[0]["checkout"] == checkout.resolve()
    assert exercised[0]["python"] == python


def test_reserves_a_loopback_port():
    port = harness().reserve_loopback_port()

    assert 0 < port < 65_536
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


def test_compares_object_info_with_input_order():
    manifest = {
        "nodes": {
            "LFGG_Test": {
                "display_name": "LFGG Test",
                "description": "Test node.",
                "category": "LFGG/test",
                "input": {
                    "required": {
                        "first": ["INT", {"default": 1}],
                        "second": ["STRING", {}],
                    }
                },
                "output": ["INT"],
                "output_name": ["value"],
                "output_tooltips": ["Value."],
            }
        }
    }
    object_info = {
        "LFGG_Test": {
            **manifest["nodes"]["LFGG_Test"],
            "input_order": {"required": ["first", "second"]},
            "name": "LFGG_Test",
        }
    }

    harness().assert_object_info_matches_manifest(object_info, manifest)
    object_info["LFGG_Test"]["input_order"]["required"].reverse()
    with pytest.raises(AssertionError, match="input order"):
        harness().assert_object_info_matches_manifest(object_info, manifest)


def test_rejects_missing_or_extra_lfgg_object_info():
    manifest = {"nodes": {"LFGG_Expected": {}}}

    with pytest.raises(AssertionError, match="registered LFGG IDs"):
        harness().assert_object_info_matches_manifest(
            {"LFGG_Unexpected": {}},
            manifest,
        )


def test_redacts_credentials_and_local_paths():
    text = "token=secret-token checkout=/private/checkout/file.py"

    assert (
        harness().redact(
            text,
            secrets=["secret-token"],
            paths=[Path("/private/checkout")],
        )
        == "token=<redacted> checkout=<redacted>/file.py"
    )


def test_redacts_successful_response_disclosures():
    credential = "active-credential"
    metadata = json.dumps({"workflow": "private-metadata"})
    workspace = Path("/private/workspace")
    text = (
        f"credential={credential} metadata={metadata} "
        f"native={workspace} windows={str(workspace).replace('/', chr(92))}"
    )

    sanitized = harness().redact(
        text,
        secrets=[credential],
        metadata=[metadata],
        paths=[workspace],
    )

    assert credential not in sanitized
    assert metadata not in sanitized
    assert str(workspace) not in sanitized
    assert str(workspace).replace("/", "\\") not in sanitized


def test_redacts_json_escaped_disclosures():
    credential = 'credential"\\雪\n'
    metadata = json.dumps({"workflow": 'private"\\雪\n'})
    workspace = Path('/private/work"\\雪\nspace')
    serialized = json.dumps(
        {
            "credential": credential,
            "metadata": metadata,
            "workspace": str(workspace),
        }
    )

    sanitized = harness().redact(
        serialized,
        secrets=[credential],
        metadata=[metadata],
        paths=[workspace],
    )

    for protected in (credential, metadata, str(workspace)):
        assert json.dumps(protected)[1:-1] not in sanitized


def test_failure_traceback_redacts_error_and_log(monkeypatch, tmp_path):
    secret = "active-credential"
    workspace = tmp_path / "private-workspace"
    monkeypatch.setenv("GITHUB_TOKEN", secret)

    def fail_start(*_args, stdout, **_kwargs):
        stdout.write(f"log secret={secret} workspace={workspace}")
        stdout.flush()
        raise RuntimeError(f"start failed: {secret} {workspace}")

    monkeypatch.setattr(harness(), "reserve_loopback_port", lambda: 8188)
    monkeypatch.setattr(harness().subprocess, "Popen", fail_start)

    with pytest.raises(Exception) as caught:
        harness()._exercise_comfyui(
            checkout=tmp_path / "checkout",
            python=tmp_path / "environment" / "bin" / "python",
            device="cpu",
            workspace=workspace,
            manifest={"nodes": {}},
            workflows={},
        )

    rendered = "".join(
        traceback.format_exception(caught.type, caught.value, caught.tb)
    )
    assert caught.type is AssertionError
    assert secret not in rendered
    assert str(workspace) not in rendered
    assert "ComfyUI log:" in rendered


def test_failure_traceback_redacts_error_without_log(monkeypatch, tmp_path):
    secret = "active-credential"
    workspace = tmp_path / "private-workspace"
    log_path = workspace / "comfyui.log"
    original_open = Path.open
    monkeypatch.setenv("GITHUB_TOKEN", secret)

    def fail_before_log(path, *args, **kwargs):
        if path == log_path:
            raise RuntimeError(f"start failed: {secret} {workspace}")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(harness(), "reserve_loopback_port", lambda: 8188)
    monkeypatch.setattr(Path, "open", fail_before_log)

    with pytest.raises(Exception) as caught:
        harness()._exercise_comfyui(
            checkout=tmp_path / "checkout",
            python=tmp_path / "environment" / "bin" / "python",
            device="cpu",
            workspace=workspace,
            manifest={"nodes": {}},
            workflows={},
        )

    rendered = "".join(
        traceback.format_exception(caught.type, caught.value, caught.tb)
    )
    assert caught.type is AssertionError
    assert secret not in rendered
    assert str(workspace) not in rendered
    assert "<redacted>" in rendered


@pytest.mark.parametrize(
    ("suffix", "label"),
    [("latent", "latent"), ("png", "PNG")],
)
def test_rejects_discovered_output_symlink_escape(tmp_path, suffix, label):
    output = tmp_path / "output"
    output.mkdir()
    target = tmp_path / f"outside.{suffix}"
    target.write_bytes(b"file")
    link = output / f"escape.{suffix}"
    try:
        link.symlink_to(target)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlinks unavailable: {type(error).__name__}")

    with pytest.raises(
        AssertionError,
        match=f"discovered {label} escaped output root",
    ):
        harness()._confined_files(output, f"*.{suffix}", label)


def test_rejects_nonstandard_or_escaped_image_descriptors(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    escaped = {
        "outputs": {
            "1": {
                "images": [
                    {
                        "filename": "image.png",
                        "subfolder": str(tmp_path),
                        "type": "output",
                    }
                ]
            }
        }
    }
    extra = {
        "outputs": {
            "1": {
                "images": [
                    {
                        "filename": "image.png",
                        "subfolder": "",
                        "type": "output",
                        "absolute_path": "/private/image.png",
                    }
                ]
            }
        }
    }

    with pytest.raises(AssertionError, match="descriptor escaped"):
        harness()._descriptor_files([escaped], "images", output, "image")
    with pytest.raises(AssertionError, match="standard fields"):
        harness()._descriptor_files([extra], "images", output, "image")


def test_history_status_requires_success():
    successful = {"status": {"completed": True, "status_str": "success"}}
    failed = {"status": {"completed": True, "status_str": "error"}}

    assert harness().history_succeeded(successful)
    assert not harness().history_succeeded(failed)


@pytest.mark.parametrize("hostname", ["localhost", "subdomain.localhost"])
def test_rejects_localhost_registry_urls(monkeypatch, hostname):
    monkeypatch.setattr(
        harness().socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )

    with pytest.raises(ValueError, match="public HTTPS"):
        harness()._public_https_url(f"https://{hostname}/archive.zip")


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.1.1",
        "224.0.0.1",
        "240.0.0.1",
        "0.0.0.0",
        "fec0::1",
    ],
)
def test_rejects_registry_hosts_with_any_non_public_address(monkeypatch, address):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    monkeypatch.setattr(
        harness().socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (family, socket.SOCK_STREAM, 6, "", (address, 443)),
        ],
    )

    with pytest.raises(ValueError, match="public HTTPS"):
        harness()._public_https_url("https://cdn.example/archive.zip")


def test_accepts_registry_host_only_when_all_addresses_are_public(monkeypatch):
    calls = []

    def public_addresses(host, port, *, type):
        calls.append((host, port, type))
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (
                socket.AF_INET6,
                socket.SOCK_STREAM,
                6,
                "",
                ("2606:2800:220:1:248:1893:25c8:1946", 443, 0, 0),
            ),
        ]

    monkeypatch.setattr(harness().socket, "getaddrinfo", public_addresses)

    url = "https://cdn.example/archive.zip"
    assert harness()._public_https_url(url) == url
    assert calls == [("cdn.example", 443, socket.SOCK_STREAM)]


def test_rejects_non_public_registry_redirect_before_following(monkeypatch):
    monkeypatch.setattr(
        harness().socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
        ],
    )
    redirect_handler = harness()._PublicHTTPSRedirectHandler()

    with pytest.raises(ValueError, match="public HTTPS"):
        redirect_handler.redirect_request(
            harness().Request("https://api.comfy.org/archive.zip"),
            None,
            302,
            "Found",
            {},
            "https://private.example/archive.zip",
        )


def test_registry_opener_uses_public_https_redirect_handler():
    assert any(
        isinstance(handler, harness()._PublicHTTPSRedirectHandler)
        for handler in harness()._REGISTRY_OPENER.handlers
    )


def test_rejects_private_initial_registry_api_before_open(monkeypatch, tmp_path):
    opened = []
    monkeypatch.setattr(
        harness().socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443))
        ],
    )

    def record_open(url, **_kwargs):
        opened.append(url)
        raise AssertionError("unsafe Registry API URL was opened")

    monkeypatch.setattr(harness()._REGISTRY_OPENER, "open", record_open)

    with pytest.raises(ValueError, match="public HTTPS"):
        harness().download_registry_archive(
            "lfgg-nodes",
            "1.0.0",
            tmp_path / "registry-node.zip",
        )

    assert opened == []


class Response:
    def __init__(self, body, url, *, content_length=None):
        self.body = body
        self.url = url
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def geturl(self):
        return self.url

    def read(self, size=-1):
        if not self.body:
            return b""
        if size < 0:
            size = len(self.body)
        chunk, self.body = self.body[:size], self.body[size:]
        return chunk


def stub_registry_responses(monkeypatch, responses):
    monkeypatch.setattr(
        harness().socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )
    responses = iter(responses)
    monkeypatch.setattr(
        harness()._REGISTRY_OPENER,
        "open",
        lambda *_, **__: next(responses),
    )


def test_retries_transient_initial_registry_dns_failure(monkeypatch, tmp_path):
    dns_attempts = []
    opened = []
    sleeps = []
    times = iter([10, 10])

    def resolve_public_after_failure(*_args, **_kwargs):
        dns_attempts.append(None)
        if len(dns_attempts) == 1:
            raise socket.gaierror("temporary DNS failure")
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ]

    responses = iter(
        [
            Response(
                json.dumps(
                    {
                        "version": "1.0.0",
                        "downloadUrl": "https://cdn.example/lfgg-nodes.zip",
                    }
                ).encode(),
                "https://api.comfy.org/nodes/lfgg-nodes/install?version=1.0.0",
            ),
            Response(b"candidate", "https://cdn.example/lfgg-nodes.zip"),
        ]
    )

    def open_response(url, **_kwargs):
        opened.append(url)
        return next(responses)

    monkeypatch.setattr(harness().socket, "getaddrinfo", resolve_public_after_failure)
    monkeypatch.setattr(harness()._REGISTRY_OPENER, "open", open_response)
    monkeypatch.setattr(harness().time, "monotonic", lambda: next(times))
    monkeypatch.setattr(harness().time, "sleep", sleeps.append)

    destination = tmp_path / "registry-node.zip"
    harness().download_registry_archive(
        "lfgg-nodes",
        "1.0.0",
        destination,
        timeout_seconds=1,
    )

    assert destination.read_bytes() == b"candidate"
    assert len(opened) == 2
    assert sleeps == [1]


@pytest.mark.parametrize("content_length", ["invalid", -1])
def test_rejects_invalid_registry_content_length(content_length):
    response = Response(
        b"candidate",
        "https://cdn.example/archive.zip",
        content_length=content_length,
    )

    with pytest.raises(ValueError, match="invalid Content-Length"):
        harness()._read_limited(response, 1024)


def test_rejects_chunked_registry_body_larger_than_limit():
    response = Response(b"candidate", "https://cdn.example/archive.zip")

    with pytest.raises(ValueError, match="too large"):
        harness()._read_limited(response, len(b"candidate") - 1)


def test_downloads_exact_public_registry_archive(monkeypatch, tmp_path):
    stub_registry_responses(
        monkeypatch,
        [
            Response(
                json.dumps(
                    {
                        "version": "1.0.0",
                        "downloadUrl": "https://cdn.example/lfgg-nodes.zip",
                    }
                ).encode(),
                "https://api.comfy.org/nodes/lfgg-nodes/install?version=1.0.0",
            ),
            Response(
                b"candidate",
                "https://cdn.example/lfgg-nodes.zip",
                content_length=9,
            ),
        ],
    )

    destination = tmp_path / "registry-node.zip"
    harness().download_registry_archive("lfgg-nodes", "1.0.0", destination)

    assert destination.read_bytes() == b"candidate"


def test_rejects_unsafe_registry_download_url(monkeypatch, tmp_path):
    response = Response(
        json.dumps(
            {
                "version": "1.0.0",
                "downloadUrl": "http://127.0.0.1/private.zip",
            }
        ).encode(),
        "https://api.comfy.org/nodes/lfgg-nodes/install?version=1.0.0",
    )
    stub_registry_responses(monkeypatch, [response])

    with pytest.raises(ValueError, match="public HTTPS"):
        harness().download_registry_archive(
            "lfgg-nodes",
            "1.0.0",
            tmp_path / "registry-node.zip",
        )


def test_bounds_registry_archive_download(monkeypatch, tmp_path):
    stub_registry_responses(
        monkeypatch,
        [
            Response(
                json.dumps(
                    {
                        "version": "1.0.0",
                        "downloadUrl": "https://cdn.example/lfgg-nodes.zip",
                    }
                ).encode(),
                "https://api.comfy.org/nodes/lfgg-nodes/install?version=1.0.0",
            ),
            Response(
                b"",
                "https://cdn.example/lfgg-nodes.zip",
                content_length=harness().MAX_ARCHIVE_BYTES + 1,
            ),
        ],
    )

    with pytest.raises(ValueError, match="too large"):
        harness().download_registry_archive(
            "lfgg-nodes",
            "1.0.0",
            tmp_path / "registry-node.zip",
        )


def test_registry_download_preserves_existing_destination(monkeypatch, tmp_path):
    stub_registry_responses(
        monkeypatch,
        [
            Response(
                json.dumps(
                    {
                        "version": "1.0.0",
                        "downloadUrl": "https://cdn.example/lfgg-nodes.zip",
                    }
                ).encode(),
                "https://api.comfy.org/nodes/lfgg-nodes/install?version=1.0.0",
            ),
            Response(b"candidate", "https://cdn.example/lfgg-nodes.zip"),
        ],
    )
    destination = tmp_path / "registry-node.zip"
    destination.write_bytes(b"approved")

    with pytest.raises(FileExistsError):
        harness().download_registry_archive("lfgg-nodes", "1.0.0", destination)

    assert destination.read_bytes() == b"approved"


def test_registry_version_mismatch_times_out(monkeypatch, tmp_path):
    attempts = []
    sleeps = []
    times = iter([10, 10, 11])

    monkeypatch.setattr(
        harness().socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )

    def mismatched_response(*_args, **_kwargs):
        attempts.append(None)
        return Response(
            json.dumps({"version": "0.9.0"}).encode(),
            "https://api.comfy.org/nodes/lfgg-nodes/install?version=1.0.0",
        )

    monkeypatch.setattr(harness()._REGISTRY_OPENER, "open", mismatched_response)
    monkeypatch.setattr(harness().time, "monotonic", lambda: next(times))
    monkeypatch.setattr(harness().time, "sleep", sleeps.append)

    with pytest.raises(TimeoutError, match="did not become active"):
        harness().download_registry_archive(
            "lfgg-nodes",
            "1.0.0",
            tmp_path / "registry-node.zip",
            timeout_seconds=1,
        )

    assert len(attempts) == 2
    assert sleeps == [1]


def test_registry_download_removes_new_partial_destination(monkeypatch, tmp_path):
    stub_registry_responses(
        monkeypatch,
        [
            Response(
                json.dumps(
                    {
                        "version": "1.0.0",
                        "downloadUrl": "https://cdn.example/lfgg-nodes.zip",
                    }
                ).encode(),
                "https://api.comfy.org/nodes/lfgg-nodes/install?version=1.0.0",
            ),
            Response(b"candidate", "https://cdn.example/lfgg-nodes.zip"),
        ],
    )
    destination = tmp_path / "registry-node.zip"
    original_open = Path.open

    class FailingWrite:
        def __enter__(self):
            self.file = original_open(destination, "xb")
            return self

        def __exit__(self, *args):
            self.file.close()

        def write(self, body):
            self.file.write(body[:1])
            self.file.flush()
            raise OSError("disk write failed")

    monkeypatch.setattr(Path, "open", lambda *_args, **_kwargs: FailingWrite())

    with pytest.raises(OSError, match="disk write failed"):
        harness().download_registry_archive("lfgg-nodes", "1.0.0", destination)

    assert not destination.exists()


def _assert_sizing_result(result):
    assert result["registered_ids"] == [
        "LFGG_DimensionsByAspectRatio",
        "LFGG_ImageDimensionsByLongSide",
        "LFGG_ImageDimensionsByPixelBudget",
        "LFGG_SaveImageDynamic",
    ]
    assert result["output_files"] == [
        "lfgg/sizing/aspect_ratio_00001_.latent",
        "lfgg/sizing/long_side_00001_.latent",
        "lfgg/sizing/pixel_budget_00001_.latent",
    ]
    assert result["output_shapes"] == {
        "lfgg/sizing/aspect_ratio_00001_.latent": [1, 4, 72, 128],
        "lfgg/sizing/long_side_00001_.latent": [2, 4, 36, 64],
        "lfgg/sizing/pixel_budget_00001_.latent": [2, 4, 27, 48],
    }


def _assert_dynamic_save_result(result):
    expected_files = [
        "lfgg/dynamic/metadata_off_00001_.png",
        "lfgg/dynamic/metadata_off_00002_.png",
        "lfgg/dynamic/metadata_on_00001_.png",
        "lfgg/dynamic/metadata_on_00002_.png",
    ]
    assert result["image_files"] == expected_files
    assert result["image_details"] == {
        filename: {
            "mode": "RGB",
            "size": [3, 2],
            "pixel": [0, 0, 0],
            "text_keys": (
                ["prompt", "workflow"] if "metadata_on" in filename else []
            ),
        }
        for filename in expected_files
    }


def release_workflows():
    return {
        name: json.loads((ROOT / "workflows" / f"{name}.json").read_text())
        for name in ("sizing", "save_image_dynamic")
    }


def test_packed_comfyui_schema_and_workflow(integration_options, tmp_path):
    if not integration_options["comfy_ref"] or not integration_options["device"]:
        pytest.skip("requires --comfy-ref and --device")

    archive = Path(integration_options["archive"]).resolve()
    assert archive.exists(), f"candidate archive not found: {archive}"
    result = harness().run_packed_comfyui(
        comfy_ref=integration_options["comfy_ref"],
        archive=archive,
        device=integration_options["device"],
        workspace=tmp_path,
        manifest=json.loads((ROOT / "release" / "1.2.0-schema.json").read_text()),
        workflows=release_workflows(),
    )

    _assert_sizing_result(result)
    _assert_dynamic_save_result(result)


def test_installed_comfyui_schema_and_workflow(integration_options, tmp_path):
    if (
        not integration_options["installed_comfyui"]
        or not integration_options["device"]
    ):
        pytest.skip("requires --installed-comfyui and --device")

    result = harness().run_installed_comfyui(
        installed_comfyui=integration_options["installed_comfyui"],
        device=integration_options["device"],
        workspace=tmp_path,
        manifest=json.loads((ROOT / "release" / "1.2.0-schema.json").read_text()),
        workflows=release_workflows(),
    )

    _assert_sizing_result(result)
    _assert_dynamic_save_result(result)
