import asyncio
from types import SimpleNamespace

import torch

from lfgg_nodes.prompt_assistant import (
    PromptAssistantError,
    ServerModels,
    release_comfy_models,
    release_llm,
)


def stub_model_management(calls, *, free_ram=8 * 1024**3, fail=None):
    def get_free_memory(device):
        calls.append(("get_free_memory", str(device)))
        if str(device) == "cpu":
            return free_ram
        return 2 * 1024**3

    def unload_all_models():
        calls.append(("unload_all_models",))
        if fail == "unload":
            raise RuntimeError("signature changed")

    def soft_empty_cache():
        calls.append(("soft_empty_cache",))

    def get_torch_device():
        if fail == "device":
            raise AttributeError("no device")
        return torch.device("cuda")

    return SimpleNamespace(
        get_torch_device=get_torch_device,
        get_total_memory=lambda device: 8 * 1024**3,
        get_free_memory=get_free_memory,
        unload_all_models=unload_all_models,
        soft_empty_cache=soft_empty_cache,
    )


def test_pre_request_step_moves_models_to_ram_and_warns_on_low_ram():
    calls = []
    assert release_comfy_models(stub_model_management(calls)) == []
    assert calls[-2:] == [("unload_all_models",), ("soft_empty_cache",)]

    calls = []
    warnings = release_comfy_models(
        stub_model_management(calls, free_ram=1024**3), model_size=4 * 1024**3
    )
    assert len(warnings) == 1
    assert "free RAM 1024 MiB is below" in warnings[0]
    assert "10240 MiB" in warnings[0]
    assert calls[-2:] == [("unload_all_models",), ("soft_empty_cache",)]


def test_pre_request_step_degrades_to_warnings_when_the_internal_api_breaks():
    calls = []
    warnings = release_comfy_models(stub_model_management(calls, fail="unload"))
    assert warnings == ["could not move ComfyUI models to RAM: signature changed"]
    assert ("soft_empty_cache",) not in calls

    calls = []
    warnings = release_comfy_models(stub_model_management(calls, fail="device"))
    assert warnings == ["memory check skipped: no device"]
    assert calls[-2:] == [("unload_all_models",), ("soft_empty_cache",)]

    assert release_comfy_models(None) == [
        "comfy.model_management is unavailable; models stay in VRAM"
    ]


class FakeClient:
    def __init__(self, mode="router", loaded=("a", "b"), released=True, fail=None):
        self.models = ServerModels(
            mode=mode,
            models=tuple({"id": name, "status": "loaded"} for name in loaded),
        )
        self.released = released
        self.fail = fail
        self.unloaded = []

    async def list_models(self):
        if self.fail == "list":
            raise PromptAssistantError("cannot reach")
        return self.models

    async def unload_model(self, model_id):
        if self.fail == "unload":
            raise PromptAssistantError("HTTP 500")
        self.unloaded.append(model_id)
        return self.released


def test_post_reply_step_unloads_in_router_mode_and_warns_otherwise():
    client = FakeClient()
    assert asyncio.run(release_llm(client, "a")) == []
    assert client.unloaded == ["a"]

    client = FakeClient()
    assert asyncio.run(release_llm(client, None)) == []
    assert client.unloaded == ["a", "b"]

    client = FakeClient(mode="single")
    warnings = asyncio.run(release_llm(client, "a"))
    assert client.unloaded == []
    assert len(warnings) == 1
    assert "--sleep-idle-seconds" in warnings[0]
    assert "router mode" in warnings[0]

    client = FakeClient(released=False)
    warnings = asyncio.run(release_llm(client, "a"))
    assert warnings == [
        "model a did not report unloaded within 30 s; VRAM may still be held"
    ]

    client = FakeClient(fail="list")
    assert asyncio.run(release_llm(client, "a")) == [
        "could not query loaded models after the reply: "
        "LFGG Prompt Assistant: cannot reach"
    ]

    client = FakeClient(fail="unload")
    assert asyncio.run(release_llm(client, "a")) == [
        "could not unload a: LFGG Prompt Assistant: HTTP 500"
    ]
