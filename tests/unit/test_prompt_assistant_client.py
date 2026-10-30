import asyncio
import json
import socket

import pytest
from prompt_assistant_fakes import FakeServer, chunk, sse

import lfgg_nodes.prompt_assistant as prompt_assistant
from lfgg_nodes.prompt_assistant import PromptAssistantError, ServerClient


def run(test, api_key="", read_timeout=5):
    async def main():
        server = await FakeServer().start()
        try:
            async with ServerClient(
                server.base_url, api_key, read_timeout
            ) as client:
                await test(server, client)
        finally:
            await server.stop()

    asyncio.run(main())


def test_health_sends_bearer_only_when_configured():
    async def scenario(server, client):
        await client.health()
        assert server.requests[-1]["authorization"] == "Bearer s3cret"

    run(scenario, api_key="s3cret")

    async def anonymous(server, client):
        await client.health()
        assert server.requests[-1]["authorization"] is None

    run(anonymous)


def test_health_reports_not_ready_and_unreachable_servers():
    async def not_ready(server, client):
        server.health_status = 503
        with pytest.raises(PromptAssistantError, match="not ready .*Loading model"):
            await client.health()

    run(not_ready)

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    async def refused():
        async with ServerClient(f"http://127.0.0.1:{port}") as client:
            with pytest.raises(PromptAssistantError, match="cannot reach") as caught:
                await client.health()
        assert f"http://127.0.0.1:{port}" in str(caught.value)
        assert "base_url" in str(caught.value)

    asyncio.run(refused())


def test_timeouts_and_redirects_are_actionable():
    async def slow(server, client):
        server.health_delay = 0.5
        with pytest.raises(PromptAssistantError, match="did not answer /health"):
            await client.health()

    run(slow, read_timeout=0.1)

    async def redirected(server, client):
        with pytest.raises(PromptAssistantError, match="redirects are not followed"):
            await client._json("GET", "/redirect")

    run(redirected)


def test_detects_router_and_single_model_modes():
    async def router(server, client):
        server.states = {"a": ["loaded"], "b": ["unloaded"]}
        models = await client.list_models()
        assert models.mode == "router"
        assert models.models == (
            {"id": "a", "status": "loaded"},
            {"id": "b", "status": "unloaded"},
        )
        assert models.loaded_ids() == ("a",)
        assert models.status_of("b") == "unloaded"
        assert models.status_of("missing") is None

    run(router)

    async def single(server, client):
        server.mode = "single"
        models = await client.list_models()
        assert models.mode == "single"
        assert models.models == ({"id": "single-model", "status": "loaded"},)
        assert [r["path"] for r in server.requests] == ["/models", "/v1/models"]

    run(single)


def test_reads_chunked_proxied_bodies_to_eof_under_the_cap(monkeypatch):
    async def scenario(server, client):
        server.chunked_props = True
        server.props = {"modalities": {"vision": True}, "pad": "x" * 500}
        assert await client.props("m") == server.props
        monkeypatch.setattr(prompt_assistant, "BODY_LIMIT", 100)
        with pytest.raises(PromptAssistantError, match="exceeds 100 bytes"):
            await client.props("m")

    run(scenario)


def test_vision_check_names_the_mmproj_flag():
    async def scenario(server, client):
        await client.check_vision("vision-model")
        assert server.requests[-1]["query"] == {"model": "vision-model"}
        await client.check_vision(None)
        assert server.requests[-1]["query"] == {}
        for props in ({"modalities": {"vision": False}}, {}, {"modalities": "x"}):
            server.props = props
            with pytest.raises(PromptAssistantError, match="--mmproj"):
                await client.check_vision("vision-model")

    run(scenario)


def test_streams_deltas_and_discards_reasoning():
    async def scenario(server, client):
        server.chunks = [
            sse(chunk(reasoning="thinking"), chunk("  Hello")),
            sse(chunk(" world", reasoning="more")),
            b"data: " + json.dumps(chunk("!", finish="stop")).encode(),
            b"\n\ndata: [DONE]\n\n",
        ]
        seen = []
        body = {"messages": [], "stream": True}
        prompt = await client.stream_chat(body, on_delta=seen.append)
        assert prompt == "Hello world!"
        assert seen == ["  Hello", "  Hello world", "  Hello world!"]
        request = server.requests[-1]
        assert request["path"] == "/v1/chat/completions"
        assert request["body"] == body

    run(scenario)


def test_stream_failures_are_actionable(monkeypatch):
    async def reasoning_only(server, client):
        server.chunks = [sse(chunk(reasoning="hmm", finish="length"), b"[DONE]")]
        with pytest.raises(PromptAssistantError, match="max_tokens.*reasoning"):
            await client.stream_chat({})

    run(reasoning_only)

    async def empty(server, client):
        server.chunks = [sse(chunk("", finish="stop"), b"[DONE]")]
        with pytest.raises(PromptAssistantError, match="reply was empty.*max_tokens"):
            await client.stream_chat({})

    run(empty)

    async def http_error(server, client):
        server.chat_status = 400
        with pytest.raises(PromptAssistantError, match="HTTP 400 .*model failed"):
            await client.stream_chat({})

    run(http_error)

    async def stream_error(server, client):
        server.chunks = [sse(chunk("partial"), {"error": {"message": "slot died"}})]
        with pytest.raises(PromptAssistantError, match="slot died"):
            await client.stream_chat({})

    run(stream_error)

    async def truncated(server, client):
        server.chunks = [sse(chunk("partial"))]
        with pytest.raises(PromptAssistantError, match="closed the stream"):
            await client.stream_chat({})

    run(truncated)

    async def finished_without_done(server, client):
        server.chunks = [sse(chunk("ok", finish="stop"))]
        assert await client.stream_chat({}) == "ok"

    run(finished_without_done)

    async def invalid(server, client):
        server.chunks = [b"data: {not json\n\n"]
        with pytest.raises(PromptAssistantError, match="invalid stream chunk"):
            await client.stream_chat({})

    run(invalid)

    async def capped(server, client):
        monkeypatch.setattr(prompt_assistant, "STREAM_LIMIT", 64)
        server.chunks = [sse(chunk("x" * 40)), sse(chunk("y" * 40)), sse(b"[DONE]")]
        with pytest.raises(PromptAssistantError, match="exceeds 64 bytes"):
            await client.stream_chat({})

    run(capped)


def test_interruption_closes_the_connection():
    class Interrupted(BaseException):
        pass

    async def scenario(server, client):
        server.chunks = [sse(chunk("a"))] * 50
        server.chunk_delay = 0.05
        calls = []

        def check():
            calls.append(1)
            if len(calls) == 2:
                raise Interrupted()

        with pytest.raises(Interrupted):
            await client.stream_chat({}, check_interrupt=check)
        await asyncio.wait_for(server.disconnected.wait(), 5)

    run(scenario)


def test_unload_polls_until_unloaded_within_the_deadline():
    async def scenario(server, client):
        server.states = {"m": ["loaded", "loading", "unloaded"]}
        sleeps = []

        async def sleep(seconds):
            sleeps.append(seconds)

        assert await client.unload_model("m", sleep=sleep, poll_interval=0.25)
        assert server.unloads == ["m"]
        assert sleeps == [0.25, 0.25]

    run(scenario)

    async def stuck(server, client):
        server.states = {"m": ["loaded"]}
        clock = [0.0]

        async def sleep(seconds):
            clock[0] += seconds

        released = await client.unload_model(
            "m", sleep=sleep, monotonic=lambda: clock[0], deadline=30, poll_interval=10
        )
        assert released is False
        assert clock[0] == 30
        polls = [r for r in server.requests if r["path"] == "/models"]
        assert len(polls) == 4

    run(stuck)
