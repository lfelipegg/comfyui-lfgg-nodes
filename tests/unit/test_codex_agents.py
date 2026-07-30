from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 only
    import tomli as tomllib


ROOT = Path(__file__).parents[2]
AGENT_NAMES = {
    "planner",
    "explorer",
    "worker",
    "qa",
    "critical_worker",
    "reviewer",
}
PROFILE_SETTINGS = {
    "planner": ("gpt-5.6-sol", "high", "read-only"),
    "explorer": ("gpt-5.6-terra", "medium", "read-only"),
    "worker": ("gpt-5.6-terra", "high", "workspace-write"),
    "qa": ("gpt-5.6-terra", "high", "workspace-write"),
    "critical_worker": ("gpt-5.6-sol", "xhigh", "workspace-write"),
    "reviewer": ("gpt-5.6-sol", "high", "read-only"),
}
RETURN_FIELDS = {
    "status",
    "files inspected",
    "files changed",
    "implementation or findings",
    "checks run",
    "assumptions",
    "residual risks",
    "recommended next action",
}


def load_toml(path):
    with path.open("rb") as file:
        return tomllib.load(file)


def test_codex_agent_profiles_match_the_approved_contract():
    config = load_toml(ROOT / ".codex" / "config.toml")
    agents = config["agents"]
    assert agents["max_concurrent_threads_per_session"] == 3
    assert agents["default_subagent_model"] == "gpt-5.6-terra"
    assert agents["default_subagent_reasoning_effort"] == "medium"

    profiles = {
        path.stem: load_toml(path)
        for path in (ROOT / ".codex" / "agents").glob("*.toml")
    }
    assert profiles.keys() == AGENT_NAMES

    for profile in profiles.values():
        assert profile["name"].strip()
        assert profile["description"].strip()
        assert profile["developer_instructions"].strip()
        assert profile["model"] in {"gpt-5.6-sol", "gpt-5.6-terra"}
        assert profile["reasoning_effort"] in {"medium", "high", "xhigh"}
        assert profile["sandbox_mode"] in {"read-only", "workspace-write"}
        instructions = profile["developer_instructions"].lower()
        assert RETURN_FIELDS <= set(instructions.splitlines())
        assert "stop" in instructions

    assert {
        name: (
            profile["model"],
            profile["reasoning_effort"],
            profile["sandbox_mode"],
        )
        for name, profile in profiles.items()
    } == PROFILE_SETTINGS
