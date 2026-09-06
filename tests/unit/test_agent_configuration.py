import ast
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 only
    import tomli as tomllib


ROOT = Path(__file__).parents[2]
CODEX_PROFILE_SETTINGS = {
    "explorer": ("gpt-5.6-terra", "medium", "read-only"),
    "reviewer": ("gpt-5.6-sol", "high", "read-only"),
    "worker": ("gpt-5.6-terra", "high", "workspace-write"),
}
RETURN_FIELDS = {
    "status",
    "files inspected",
    "files changed",
    "implementation or findings",
    "checks run with exact results",
    "assumptions",
    "residual risks",
    "recommended next action",
}


def load_toml(path):
    with path.open("rb") as file:
        return tomllib.load(file)


def load_mapping_yaml(path):
    root = {}
    stack = [(-1, root)]

    for raw_line in path.read_text().splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip())
        key, separator, raw_value = stripped.partition(":")
        assert separator, f"invalid mapping line: {raw_line!r}"
        while indent <= stack[-1][0]:
            stack.pop()

        target = stack[-1][1]
        raw_value = raw_value.strip()
        if raw_value:
            target[key] = (
                ast.literal_eval(raw_value)
                if raw_value[0] in "\"'"
                else int(raw_value)
            )
            continue

        child = {}
        target[key] = child
        stack.append((indent, child))

    return root


def test_omp_uses_bundled_agents_with_project_routing():
    assert load_mapping_yaml(ROOT / ".omp" / "config.yml") == {
        "task": {
            "maxConcurrency": 3,
            "maxRecursionDepth": 1,
            "agentModelOverrides": {
                "sonic": "@smol",
                "scout": "@smol",
                "task": "@task",
                "reviewer": "@plan",
                "security-reviewer": "@plan",
            },
        }
    }
    assert (ROOT / ".omp" / "AGENTS.md").read_text().strip() == "@../AGENTS.md"
    assert not (ROOT / ".omp" / "agents").exists()


def test_codex_keeps_only_lean_compatibility_profiles():
    config = load_toml(ROOT / ".codex" / "config.toml")
    agents = config["agents"]
    assert agents["max_concurrent_threads_per_session"] == 3
    assert agents["default_subagent_model"] == "gpt-5.6-terra"
    assert agents["default_subagent_reasoning_effort"] == "medium"

    profiles = {
        path.stem: load_toml(path)
        for path in (ROOT / ".codex" / "agents").glob("*.toml")
    }
    assert profiles.keys() == CODEX_PROFILE_SETTINGS.keys()

    for name, profile in profiles.items():
        assert profile["name"] == name
        assert profile["description"].strip()
        assert profile["developer_instructions"].strip()
        assert RETURN_FIELDS <= set(
            profile["developer_instructions"].lower().splitlines()
        )
        assert (
            profile["model"],
            profile["model_reasoning_effort"],
            profile["sandbox_mode"],
        ) == CODEX_PROFILE_SETTINGS[name]

    for name in {"explorer", "reviewer"}:
        assert "do not modify files or external state" in profiles[name][
            "developer_instructions"
        ].lower()


def test_shared_guidance_points_to_omp_orchestration():
    root_guidance = (ROOT / "AGENTS.md").read_text()
    orchestration_path = ROOT / "docs" / "agents" / "orchestration.md"

    assert "docs/agents/orchestration.md" in root_guidance
    assert "agents/orchestrator.md" not in root_guidance
    assert orchestration_path.is_file()
