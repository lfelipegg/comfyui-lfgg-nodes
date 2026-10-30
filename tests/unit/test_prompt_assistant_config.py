import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from lfgg_nodes.prompt_assistant import (
    PromptAssistantError,
    expand_root,
    load_assistant_config,
    validate_assistant_section,
)
from lfgg_nodes.prompt_composer import PromptComposerError, load_config_document


def write_config(monkeypatch, tmp_path, config):
    user = tmp_path / "user"
    (user / "lfgg_nodes").mkdir(parents=True, exist_ok=True)
    path = user / "lfgg_nodes" / "config.json"
    path.write_text(
        config if isinstance(config, str) else json.dumps(config), encoding="utf-8"
    )
    monkeypatch.setitem(
        sys.modules,
        "folder_paths",
        SimpleNamespace(get_user_directory=lambda: str(user)),
    )
    return path


def test_shared_document_accepts_either_or_both_sections(monkeypatch, tmp_path):
    write_config(monkeypatch, tmp_path, {"prompt_assistant": {"skills_roots": []}})
    config, content = load_config_document("label", PromptComposerError)
    assert set(config) == {"prompt_assistant"}
    assert json.loads(content) == config

    write_config(
        monkeypatch,
        tmp_path,
        {"prompt_composer": {}, "prompt_assistant": {"skills_roots": []}},
    )
    config, _ = load_config_document("label", PromptAssistantError)
    assert set(config) == {"prompt_composer", "prompt_assistant"}

    write_config(monkeypatch, tmp_path, {})
    assert load_config_document("label", PromptAssistantError)[0] == {}


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ('{"prompt_assistant": {}, "other": 1}', "only the prompt_composer and"),
        ('{"prompt_assistant": {}, "prompt_assistant": {}}', "repeated key"),
        ("[]", "only the prompt_composer and"),
        ("{", "not valid JSON"),
    ],
)
def test_shared_document_rejects_unknown_or_repeated_keys(
    monkeypatch, tmp_path, document, message
):
    write_config(monkeypatch, tmp_path, document)
    with pytest.raises(PromptAssistantError, match=message) as caught:
        load_config_document("prompt assistant configuration", PromptAssistantError)
    assert str(caught.value).startswith("LFGG Prompt Assistant: ")
    with pytest.raises(PromptComposerError, match=message):
        load_config_document("prompt composer configuration", PromptComposerError)


def test_missing_document_names_the_user_directory(monkeypatch, tmp_path):
    monkeypatch.setitem(
        sys.modules,
        "folder_paths",
        SimpleNamespace(get_user_directory=lambda: str(tmp_path)),
    )
    with pytest.raises(PromptAssistantError, match="ComfyUI user directory"):
        load_assistant_config()


def test_assistant_section_defaults_and_normalization(monkeypatch, tmp_path):
    write_config(
        monkeypatch,
        tmp_path,
        {
            "prompt_composer": {"styles_csv": "/x.csv", "wildcards": "/w"},
            "prompt_assistant": {
                "server": {
                    "base_url": "https://Example.test:8443/",
                    "api_key": " secret ",
                    "read_timeout_seconds": 42,
                },
                "skills_roots": ["~/.agents/skills", "C:/Users/name/.agents/skills"],
                "skills": ["scenario-maker-sdxl", "scenario-maker-wan"],
            },
        },
    )
    config = load_assistant_config()
    assert config.base_url == "https://example.test:8443"
    assert config.api_key == "secret"
    assert config.read_timeout == 42
    assert config.skills_roots == ("~/.agents/skills", "C:/Users/name/.agents/skills")
    assert config.skills == ("scenario-maker-sdxl", "scenario-maker-wan")

    minimal = validate_assistant_section({"skills_roots": []})
    assert minimal.base_url == "http://127.0.0.1:8080"
    assert minimal.api_key == ""
    assert minimal.read_timeout == 300
    assert minimal.skills is None


def test_missing_assistant_section_is_actionable(monkeypatch, tmp_path):
    write_config(monkeypatch, tmp_path, {"prompt_composer": {}})
    with pytest.raises(PromptAssistantError, match="no prompt_assistant section"):
        load_assistant_config()


@pytest.mark.parametrize(
    "base_url",
    [
        "ftp://host",
        "host:8080",
        "http://",
        "http://host/v1",
        "http://host?x=1",
        "http://host#frag",
        "http://user:pw@host",
        "http://host:99999",
        "",
        7,
    ],
)
def test_rejects_invalid_base_url_forms(base_url):
    with pytest.raises(PromptAssistantError, match="server.base_url"):
        validate_assistant_section(
            {"server": {"base_url": base_url}, "skills_roots": []}
        )


@pytest.mark.parametrize("base_url", ["http://127.0.0.1:8080", "http://[::1]:8080"])
def test_accepts_plain_host_forms(base_url):
    config = validate_assistant_section(
        {"server": {"base_url": base_url}, "skills_roots": []}
    )
    assert config.base_url == base_url


@pytest.mark.parametrize("value", [9, 3601, "300", True, -1])
def test_rejects_out_of_range_timeouts(value):
    with pytest.raises(PromptAssistantError, match="read_timeout_seconds"):
        validate_assistant_section(
            {"server": {"read_timeout_seconds": value}, "skills_roots": []}
        )


@pytest.mark.parametrize(
    ("section", "message"),
    [
        ({"skills_roots": [], "extra": 1}, "only server, skills_roots, and skills"),
        ({"server": {"host": "x"}, "skills_roots": []}, "server must contain only"),
        ({"server": {"api_key": "a\nb"}, "skills_roots": []}, "api_key"),
        ({}, "skills_roots must be a list"),
        ({"skills_roots": ["relative/path"]}, "skills_roots must be a list"),
        ({"skills_roots": [""]}, "skills_roots must be a list"),
        ({"skills_roots": "~/skills"}, "skills_roots must be a list"),
        ({"skills_roots": [], "skills": "sdxl"}, "skills must be a list"),
        ({"skills_roots": [], "skills": ["a/b"]}, "plain skill directory name"),
        ({"skills_roots": [], "skills": [".hidden"]}, "plain skill directory name"),
        ({"skills_roots": [], "skills": ["a", "a"]}, "must not repeat"),
        ([], "only server, skills_roots, and skills"),
    ],
)
def test_rejects_invalid_section_shapes(section, message):
    with pytest.raises(PromptAssistantError, match=message):
        validate_assistant_section(section)


def test_root_specs_accept_both_os_styles_and_expand_home(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    config = validate_assistant_section(
        {
            "skills_roots": [
                "~",
                "~/.agents/skills",
                "~\\.agents\\skills",
                "C:\\Users\\name\\.agents",
                "/srv/skills",
            ]
        }
    )
    assert len(config.skills_roots) == 5
    assert expand_root("~") == tmp_path
    assert expand_root("~/.agents/skills") == tmp_path / ".agents" / "skills"
    assert expand_root("~\\.agents\\skills") == tmp_path / ".agents" / "skills"
    assert expand_root("/srv/skills") == Path("/srv/skills")
    assert expand_root("C:/Users/name") == Path("C:/Users/name")
