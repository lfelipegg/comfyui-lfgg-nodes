import re
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_release_workflows_keep_security_boundaries():
    qualify = (ROOT / ".github" / "workflows" / "qualify.yml").read_text()
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text()

    assert "pull_request_target" not in qualify + release
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
