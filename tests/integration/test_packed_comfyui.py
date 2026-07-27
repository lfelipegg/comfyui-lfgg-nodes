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
