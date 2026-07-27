import json
import socket
from importlib import import_module
from pathlib import Path

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
    ],
)
def test_rejects_registry_hosts_with_any_non_public_address(monkeypatch, address):
    monkeypatch.setattr(
        harness().socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)),
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
        manifest=json.loads((ROOT / "release" / "1.0.0-schema.json").read_text()),
        workflow=json.loads((ROOT / "workflows" / "sizing.json").read_text()),
    )

    assert result["registered_ids"] == [
        "LFGG_DimensionsByAspectRatio",
        "LFGG_ImageDimensionsByLongSide",
        "LFGG_ImageDimensionsByPixelBudget",
    ]
    assert result["output_files"] == [
        "lfgg/sizing/aspect_ratio_00001_.latent",
        "lfgg/sizing/long_side_00001_.latent",
        "lfgg/sizing/pixel_budget_00001_.latent",
    ]
