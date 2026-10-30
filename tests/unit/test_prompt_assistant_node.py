import asyncio
import inspect
import json
import logging
import socket
import sys
from types import SimpleNamespace

import pytest
import torch
from prompt_assistant_fakes import FakeServer, chunk, sse

from lfgg_nodes.prompt_assistant import (
    DEFAULT_MASTER_PROMPT,
    PromptAssistant,
    PromptAssistantError,
    prompt_assistant_models,
    prompt_assistant_skills,
)

SKILL_MD = "---\nname: {name}\n---\n# {name}\n\nBody.\n"


class Interrupted(BaseException):
    pass


class Harness:
    """Fake server, user config, skills root, and stubbed ComfyUI modules."""

    def __init__(self, monkeypatch, tmp_path, *, api_key="", interrupt_after=None):
        self.order = []
        self.progress = []
        self.logs = []
        self.user = tmp_path / "user"
        self.root = tmp_path / "skills"
        (self.user / "lfgg_nodes").mkdir(parents=True)
        for name in ("scenario-maker-sdxl", "scenario-maker-wan"):
            skill = self.root / name
            (skill / "references").mkdir(parents=True)
            (skill / "SKILL.md").write_text(SKILL_MD.format(name=name), "utf-8")
            (skill / "references" / "ref.md").write_text("Ref body\n", "utf-8")
            (skill / "references" / "data.csv").write_text("a,b\n", "utf-8")
        self.api_key = api_key
        self.monkeypatch = monkeypatch
        self.interrupt_after = interrupt_after
        monkeypatch.setitem(
            sys.modules,
            "folder_paths",
            SimpleNamespace(get_user_directory=lambda: str(self.user)),
        )
        model_management = SimpleNamespace(
            get_torch_device=lambda: torch.device("cpu"),
            get_total_memory=lambda device: 8 * 1024**3,
            get_free_memory=lambda device: 4 * 1024**3,
            unload_all_models=lambda: self.order.append("unload_all_models"),
            soft_empty_cache=lambda: self.order.append("soft_empty_cache"),
            throw_exception_if_processing_interrupted=self.check_interrupt,
        )
        monkeypatch.setitem(sys.modules, "comfy.model_management", model_management)
        monkeypatch.setitem(
            sys.modules,
            "server",
            SimpleNamespace(
                PromptServer=SimpleNamespace(
                    instance=SimpleNamespace(send_progress_text=self.send_progress)
                )
            ),
        )

    def check_interrupt(self):
        limit = self.interrupt_after
        if limit is not None and len(self.progress) >= limit:
            raise Interrupted()

    def send_progress(self, text, node_id):
        self.progress.append((node_id, text))

    def write_config(
        self, base_url, skills=("scenario-maker-sdxl", "scenario-maker-wan")
    ):
        config = {
            "prompt_assistant": {
                "server": {"base_url": base_url, "api_key": self.api_key},
                "skills_roots": [str(self.root), str(self.user / "missing")],
            }
        }
        if skills is not None:
            config["prompt_assistant"]["skills"] = list(skills)
        (self.user / "lfgg_nodes" / "config.json").write_text(json.dumps(config))

    async def run(self, test):
        server = await FakeServer().start()
        original_record = server.record

        def record(request, body=None):
            if request.path == "/v1/chat/completions":
                self.order.append("chat")
            original_record(request, body)

        server.record = record
        self.write_config(server.base_url)
        try:
            return await test(server)
        finally:
            await server.stop()


def generate(server_or_none=None, **overrides):
    arguments = dict(
        master_prompt="Master",
        request="Write a prompt",
        skills="scenario-maker-sdxl/references/ref.md",
        model="vision-model",
        vram_policy="share",
        seed=7,
        temperature=0.5,
        max_tokens=64,
        unique_id="12",
    )
    arguments.update(overrides)
    return PromptAssistant().generate(**arguments)


def paths(server):
    return [(r["method"], r["path"]) for r in server.requests]


def test_schema_matches_the_accepted_contract():
    assert PromptAssistant.CATEGORY == "LFGG/text"
    assert PromptAssistant.FUNCTION == "generate"
    assert PromptAssistant.RETURN_TYPES == ("STRING",)
    assert PromptAssistant.RETURN_NAMES == ("prompt",)
    assert not hasattr(PromptAssistant, "IS_CHANGED")
    assert not getattr(PromptAssistant, "OUTPUT_NODE", False)
    assert inspect.iscoroutinefunction(PromptAssistant.generate)
    schema = PromptAssistant.INPUT_TYPES()
    assert list(schema["required"]) == [
        "master_prompt",
        "request",
        "skills",
        "model",
        "vram_policy",
        "seed",
        "temperature",
        "max_tokens",
    ]
    assert list(schema["optional"]) == ["image_1", "image_2", "image_3", "image_4"]
    assert schema["hidden"] == {"unique_id": "UNIQUE_ID"}
    assert schema["required"]["master_prompt"][1]["default"] == DEFAULT_MASTER_PROMPT
    assert schema["required"]["model"][0] == ["server default"]
    assert schema["required"]["vram_policy"][0] == ["share", "keep_llm_loaded", "off"]
    assert schema["required"]["vram_policy"][1]["default"] == "share"
    assert schema["required"]["seed"][1]["max"] == 2**64 - 1
    assert schema["required"]["temperature"][1] == {
        "default": 0.7, "min": 0.0, "max": 2.0, "step": 0.05,
        "tooltip": "Sampling temperature.",
    }
    assert schema["required"]["max_tokens"][1]["max"] == 32768
    assert all(value[0] == "IMAGE" for value in schema["optional"].values())
    assert PromptAssistant.VALIDATE_INPUTS("any-model-id") is True
    assert "model must be" in PromptAssistant.VALIDATE_INPUTS("")


def test_share_policy_sequences_unload_stream_and_release(monkeypatch, tmp_path):
    harness = Harness(monkeypatch, tmp_path, api_key="k")

    async def scenario(server):
        server.states = {"vision-model": ["loaded", "loaded", "unloaded"]}
        server.chunks = [sse(chunk("A "), chunk("prompt\n", finish="stop"), b"[DONE]")]
        result = await generate()
        assert result == {"ui": {"text": ["A prompt"]}, "result": ("A prompt",)}
        assert harness.order == ["unload_all_models", "soft_empty_cache", "chat"]
        assert harness.progress == [("12", "A "), ("12", "A prompt\n")]
        assert paths(server) == [
            ("GET", "/health"),
            ("POST", "/v1/chat/completions"),
            ("GET", "/models"),
            ("POST", "/models/unload"),
            ("GET", "/models"),
            ("GET", "/models"),
        ]
        chat = server.requests[1]
        assert chat["authorization"] == "Bearer k"
        body = chat["body"]
        assert body["model"] == "vision-model"
        assert body["stream"] is True
        assert body["seed"] == 7
        assert body["max_tokens"] == 64
        assert body["messages"][0]["role"] == "system"
        system = body["messages"][0]["content"]
        assert system.startswith("Master\n\n# Skill: scenario-maker-sdxl\n\n")
        assert "## scenario-maker-sdxl/references/ref.md\n\nRef body" in system
        assert body["messages"][1] == {
            "role": "user",
            "content": [{"type": "text", "text": "Write a prompt"}],
        }
        assert server.requests[3]["body"] == {"model": "vision-model"}

    asyncio.run(harness.run(scenario))


def test_other_policies_and_single_mode_warning(monkeypatch, tmp_path, caplog):
    harness = Harness(monkeypatch, tmp_path)

    async def keep(server):
        await generate(vram_policy="keep_llm_loaded")
        assert harness.order == ["unload_all_models", "soft_empty_cache", "chat"]
        assert ("POST", "/models/unload") not in paths(server)

    asyncio.run(harness.run(keep))

    harness = Harness(monkeypatch, tmp_path / "off")

    async def off(server):
        await generate(vram_policy="off")
        assert harness.order == ["chat"]
        assert paths(server) == [("GET", "/health"), ("POST", "/v1/chat/completions")]

    asyncio.run(harness.run(off))

    harness = Harness(monkeypatch, tmp_path / "single")

    async def single(server):
        server.mode = "single"
        with caplog.at_level(logging.WARNING, logger="lfgg_nodes.prompt_assistant"):
            await generate(model="server default")
        assert ("POST", "/models/unload") not in paths(server)
        assert any("--sleep-idle-seconds" in r.message for r in caplog.records)
        assert "model" not in server.requests[1]["body"]

    asyncio.run(harness.run(single))


def test_guarded_model_management_failure_still_generates(
    monkeypatch, tmp_path, caplog
):
    harness = Harness(monkeypatch, tmp_path)

    async def scenario(server):
        def broken():
            raise RuntimeError("renamed")

        sys.modules["comfy.model_management"].unload_all_models = broken
        with caplog.at_level(logging.WARNING, logger="lfgg_nodes.prompt_assistant"):
            result = await generate(vram_policy="keep_llm_loaded")
        assert result["result"] == ("Hello world",)
        assert any("renamed" in r.message for r in caplog.records)

    asyncio.run(harness.run(scenario))


def test_images_require_vision_and_are_sent_before_the_request(
    monkeypatch, tmp_path
):
    harness = Harness(monkeypatch, tmp_path)
    image = torch.rand(2, 8, 8, 3)

    async def scenario(server):
        await generate(image_2=image, request="", vram_policy="off")
        assert paths(server) == [
            ("GET", "/health"),
            ("GET", "/props"),
            ("POST", "/v1/chat/completions"),
        ]
        assert server.requests[1]["query"] == {"model": "vision-model"}
        content = server.requests[2]["body"]["messages"][1]["content"]
        assert [part["type"] for part in content] == [
            "text", "image_url", "text", "image_url",
        ]
        assert content[0]["text"] == "Image 1 of 2"
        assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")

        server.props = {"modalities": {"vision": False}}
        server.requests.clear()
        with pytest.raises(PromptAssistantError, match="--mmproj"):
            await generate(image_1=image, vram_policy="off")
        assert ("POST", "/v1/chat/completions") not in paths(server)

    asyncio.run(harness.run(scenario))


def test_validation_errors_happen_before_any_network_call(monkeypatch, tmp_path):
    harness = Harness(monkeypatch, tmp_path)

    async def scenario(server):
        cases = [
            (dict(vram_policy="auto"), "vram_policy must be one of"),
            (dict(request=""), "request is empty"),
            (dict(skills="unknown-skill"), "unknown-skill is not in the prompt"),
            (dict(skills="scenario-maker-sdxl/references/data.csv"), "must name a .md"),
            (dict(seed=-1), "seed must be"),
            (dict(image_1=torch.zeros(9, 2, 2, 3)), "9 images are connected"),
            (dict(master_prompt=3), "master_prompt must be a string"),
        ]
        for overrides, message in cases:
            with pytest.raises(PromptAssistantError, match=message):
                await generate(**overrides)
        assert server.requests == []
        assert harness.order == []

        harness.write_config(server.base_url, skills=("scenario-maker-wan",))
        with pytest.raises(PromptAssistantError, match="not in the prompt_assistant"):
            await generate()

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        harness.write_config(f"http://127.0.0.1:{port}")
        with pytest.raises(PromptAssistantError, match="cannot reach") as caught:
            await generate()
        assert f"http://127.0.0.1:{port}" in str(caught.value)
        assert harness.order == []

    asyncio.run(harness.run(scenario))


def test_interruption_propagates_and_skips_release(monkeypatch, tmp_path):
    harness = Harness(monkeypatch, tmp_path, interrupt_after=1)

    async def scenario(server):
        server.chunks = [sse(chunk("a"))] * 40
        server.chunk_delay = 0.05
        with pytest.raises(Interrupted):
            await generate()
        await asyncio.wait_for(server.disconnected.wait(), 5)
        assert ("POST", "/models/unload") not in paths(server)

    asyncio.run(harness.run(scenario))


def test_routes_report_models_and_skills_without_secrets(monkeypatch, tmp_path):
    harness = Harness(monkeypatch, tmp_path, api_key="topsecret")
    responses = []

    def json_response(payload, status=200):
        responses.append((payload, status))
        return payload

    monkeypatch.setitem(
        sys.modules,
        "aiohttp.web",
        SimpleNamespace(json_response=json_response),
    )
    monkeypatch.setattr(
        sys.modules["aiohttp"], "web", sys.modules["aiohttp.web"], raising=False
    )

    async def scenario(server):
        server.states = {"m": ["loaded"], "n": ["unloaded"]}
        await prompt_assistant_models(None)
        assert responses[-1] == (
            {
                "mode": "router",
                "models": [
                    {"id": "m", "status": "loaded"},
                    {"id": "n", "status": "unloaded"},
                ],
            },
            200,
        )
        assert server.requests[-1]["authorization"] == "Bearer topsecret"

        await prompt_assistant_skills(None)
        catalog, status = responses[-1]
        assert status == 200
        assert catalog["roots"] == [
            {"path": str(harness.root), "available": True},
            {"path": str(harness.user / "missing"), "available": False},
        ]
        assert [skill["name"] for skill in catalog["skills"]] == [
            "scenario-maker-sdxl",
            "scenario-maker-wan",
        ]
        sdxl = catalog["skills"][0]
        assert sdxl["available"] is True
        assert sdxl["root"] == str(harness.root)
        assert sdxl["skill_size"] > 0
        assert sdxl["files"] == [{"path": "references/ref.md", "size": 9}]
        assert catalog["limits"] == {"total": 256 * 1024, "file": 512 * 1024}
        assert any("missing" in warning for warning in catalog["warnings"])

        harness.write_config(server.base_url, skills=("scenario-maker-wan", "absent"))
        await prompt_assistant_skills(None)
        catalog, _ = responses[-1]
        assert [(s["name"], s["available"]) for s in catalog["skills"]] == [
            ("scenario-maker-wan", True),
            ("absent", False),
        ]

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        harness.write_config(f"http://127.0.0.1:{port}")
        await prompt_assistant_models(None)
        payload, status = responses[-1]
        assert status == 502
        assert "cannot reach" in payload["error"]
        assert "topsecret" not in json.dumps(responses)

        (harness.user / "lfgg_nodes" / "config.json").write_text("{}")
        await prompt_assistant_skills(None)
        payload, status = responses[-1]
        assert status == 400
        assert "no prompt_assistant section" in payload["error"]

    asyncio.run(harness.run(scenario))
