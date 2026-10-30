"""Fake llama-server used by the prompt assistant unit tests."""

import asyncio
import json

from aiohttp import web


def sse(*events):
    return b"".join(
        b"data: " + (event if isinstance(event, bytes) else json.dumps(event).encode())
        + b"\n\n"
        for event in events
    )


def chunk(content=None, reasoning=None, finish=None):
    delta = {}
    if content is not None:
        delta["content"] = content
    if reasoning is not None:
        delta["reasoning_content"] = reasoning
    return {"choices": [{"delta": delta, "finish_reason": finish}]}


class FakeServer:
    def __init__(self):
        self.requests = []
        self.mode = "router"
        self.health_status = 200
        self.states = {"vision-model": ["loaded"]}
        self.props = {"modalities": {"vision": True}}
        self.chunked_props = False
        self.chat_status = 200
        self.chunks = [sse(chunk("Hello"), chunk(" world", finish="stop"), b"[DONE]")]
        self.chunk_delay = 0
        self.health_delay = 0
        self.disconnected = asyncio.Event()
        self.unloads = []

    def state(self, model_id):
        sequence = self.states[model_id]
        return sequence.pop(0) if len(sequence) > 1 else sequence[0]

    async def start(self):
        app = web.Application()
        app.router.add_get("/health", self.health)
        app.router.add_get("/models", self.models)
        app.router.add_get("/v1/models", self.v1_models)
        app.router.add_get("/props", self.props_route)
        app.router.add_post("/v1/chat/completions", self.chat)
        app.router.add_post("/models/unload", self.unload)
        app.router.add_get("/redirect", self.redirect)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.base_url = f"http://127.0.0.1:{port}"
        return self

    async def stop(self):
        await self.runner.cleanup()

    def record(self, request, body=None):
        self.requests.append(
            {
                "method": request.method,
                "path": request.path,
                "query": dict(request.query),
                "authorization": request.headers.get("Authorization"),
                "body": body,
            }
        )

    async def health(self, request):
        self.record(request)
        await asyncio.sleep(self.health_delay)
        if self.health_status == 503:
            return web.json_response(
                {"error": {"code": 503, "message": "Loading model"}}, status=503
            )
        return web.json_response({"status": "ok"}, status=self.health_status)

    async def models(self, request):
        self.record(request)
        if self.mode == "single":
            return web.json_response({"error": "not found"}, status=404)
        data = [
            {"id": model_id, "status": {"value": self.state(model_id)}}
            for model_id in list(self.states)
        ]
        return web.json_response({"data": data})

    async def v1_models(self, request):
        self.record(request)
        return web.json_response({"data": [{"id": "single-model", "object": "model"}]})

    async def props_route(self, request):
        self.record(request)
        if not self.chunked_props:
            return web.json_response(self.props)
        # Router mode proxies /props?model= as a chunked, connection-close body.
        payload = json.dumps(self.props).encode()
        response = web.StreamResponse(
            headers={"Content-Type": "application/json", "Connection": "close"}
        )
        response.enable_chunked_encoding()
        await response.prepare(request)
        for start in range(0, len(payload), 7):
            await response.write(payload[start : start + 7])
            await asyncio.sleep(0.005)
        await response.write_eof()
        return response

    async def chat(self, request):
        self.record(request, await request.json())
        if self.chat_status != 200:
            return web.json_response(
                {"error": {"message": "model failed"}}, status=self.chat_status
            )
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        try:
            for piece in self.chunks:
                await response.write(piece)
                await asyncio.sleep(self.chunk_delay)
            await response.write_eof()
        except (ConnectionResetError, ConnectionError, asyncio.CancelledError):
            self.disconnected.set()
            raise
        return response

    async def unload(self, request):
        body = await request.json()
        self.record(request, body)
        self.unloads.append(body["model"])
        return web.json_response({"success": True})

    async def redirect(self, request):
        self.record(request)
        raise web.HTTPFound("/health")


