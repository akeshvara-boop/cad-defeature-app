import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from cad_defeature.api import stream_proxy


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CAD_UI_PUBLIC_ORIGIN", "https://viewer.example")
    app = FastAPI()
    app.include_router(stream_proxy.router)
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize("origin", [None, "https://untrusted.example"])
def test_rejects_other_origins(client, origin):
    headers = {"origin": origin} if origin else {}
    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect("/kit-stream/sign_in", headers=headers):
            pass
    assert error.value.code == 1008


def test_proxy_disabled_without_origin(client, monkeypatch):
    monkeypatch.delenv("CAD_UI_PUBLIC_ORIGIN")
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/kit-stream/sign_in", headers={"origin": "https://viewer.example"}):
            pass


def test_frontend_advertises_proxy_when_enabled(monkeypatch):
    from cad_defeature.api.app import frontend_config
    monkeypatch.setenv("CAD_UI_PUBLIC_ORIGIN", "https://viewer.example")
    assert frontend_config()["kit_stream"]["signaling_path"] == "/kit-stream"


def test_roundtrip_fixed_upstream_and_cleanup(client, monkeypatch):
    calls = []

    class Echo:
        def __init__(self):
            self.queue = asyncio.Queue()
            self.closed = False
            self.subprotocol = "x-nv-sessionid.test"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            self.closed = True

        async def send(self, data):
            await self.queue.put(data)

        def __aiter__(self):
            return self

        async def __anext__(self):
            return await self.queue.get()

    echo = Echo()

    def connect(url, **kwargs):
        calls.append((url, kwargs))
        return echo

    monkeypatch.setattr(stream_proxy, "connect", connect)
    with client.websocket_connect(
        "/kit-stream/sign_in?peer_id=test&version=2",
        headers={"origin": "https://viewer.example", "cookie": "private=never-forward"},
        subprotocols=["x-nv-sessionid.test"],
    ) as socket:
        assert socket.accepted_subprotocol == "x-nv-sessionid.test"
        socket.send_text("hello")
        assert socket.receive_text() == "hello"
        socket.send_bytes(b"binary")
        assert socket.receive_bytes() == b"binary"
        socket.close()
        assert socket.receive()["type"] == "websocket.close"
    assert calls[0][0] == "ws://127.0.0.1:49100/sign_in?peer_id=test&version=2"
    assert "additional_headers" not in calls[0][1]
    assert calls[0][1]["subprotocols"] == ["x-nv-sessionid.test"]
    assert echo.closed
