import re
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_release_workflows_keep_security_boundaries():
    qualify = (ROOT / ".github" / "workflows" / "qualify.yml").read_text()
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text()

    assert "pull_request_target" not in qualify + release
    assert "node --test tests/frontend/ratio_preview.test.mjs" in qualify
    assert "if: github.event_name != 'pull_request'" in qualify
    assert "runs-on: [self-hosted, linux, x64, cuda]" in qualify
    assert release.count("secrets.REGISTRY_ACCESS_TOKEN") == 1
    assert "environment: registry-release" in release
    assert release.index("needs: [qualify, tag]") < release.index(
        "secrets.REGISTRY_ACCESS_TOKEN"
    )

    for workflow in (qualify, release):
        assert "permissions:\n  contents: read" in workflow
        for action in re.findall(r"uses: (?!\./)([^@\s]+)@([^\s#]+)", workflow):
            assert re.fullmatch(r"[0-9a-f]{40}", action[1]), action


def test_release_exercises_the_exact_registry_installed_version():
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text()

    archive_download = release.index("Download exact published archive")
    archive_check = release.index(
        "python -m pytest -q tests/package --archive registry-node.zip"
    )
    fresh_workspace = release.index("Create fresh Registry workspace")
    comfy_install = release.index("install --version 0.28.0 --cpu")
    node_install = release.index(
        'node install "lfgg-nodes@${VERSION}" --exit-on-fail'
    )
    installed_integration = release.index("--installed-comfyui")

    assert (
        archive_download
        < archive_check
        < fresh_workspace
        < comfy_install
        < node_install
        < installed_integration
    )
    assert '"comfy-cli==1.12.0"' in release[fresh_workspace:comfy_install]
    assert (
        "REGISTRY_WORKSPACE: ${{ runner.temp }}/lfgg-registry-workspace"
        in release[fresh_workspace:comfy_install]
    )
    assert (
        "REGISTRY_TOOLS: ${{ runner.temp }}/lfgg-registry-tools"
        in release[fresh_workspace:comfy_install]
    )
    assert (
        '--workspace="$REGISTRY_WORKSPACE/ComfyUI"'
        in release[comfy_install:installed_integration]
    )
    assert "VERSION: ${{ needs.tag.outputs.version }}" in release
    assert (
        '"$REGISTRY_WORKSPACE/ComfyUI"'
        in release[installed_integration:]
    )
    assert "REGISTRY_ACCESS_TOKEN" not in release[fresh_workspace:]
    assert (
        '--changelog "Add the aspect-ratio preview and conditional '
        'custom-ratio controls."'
        in release
    )
    assert '--changelog "Add LFGG Save Image Dynamic."' not in release
    assert '--changelog "Initial sizing nodes release."' not in release
