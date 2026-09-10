"""Same-origin Kit signaling bridge; the deployment proxy supplies TLS/auth."""
import asyncio
import logging
import os
import json
from urllib.request import urlopen
from urllib.parse import urlencode

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/kit-stream/sign_in")
@router.websocket("/ovrtx-stream/sign_in")
async def signaling(socket: WebSocket):
    # Explicit opt-in, browser origin check, fixed upstream: never an open proxy.
    allowed = os.getenv("CAD_UI_PUBLIC_ORIGIN", "").rstrip("/")
    if not allowed or socket.headers.get("origin") != allowed:
        await socket.close(code=1008)
        return
    ovrtx = socket.url.path.startswith('/ovrtx-stream/')
    if ovrtx:
        def current_asset():
            with urlopen('http://127.0.0.1:8081/healthz', timeout=2) as response:
                return json.loads(response.read(16384))
        try:
            health = await asyncio.to_thread(current_asset)
            if (not socket.query_params.get('workflow_id') or
                health.get('workflow_id') != socket.query_params.get('workflow_id') or
                health.get('asset_id') != socket.query_params.get('asset_id') or
                health.get('status') != 'ready'):
                await socket.close(code=1008); return
        except (OSError, ValueError):
            await socket.close(code=1011); return
    upstream = ('ws://127.0.0.1:49200/sign_in' if socket.url.path.startswith('/ovrtx-stream/')
                else 'ws://127.0.0.1:49100/sign_in')
    query = urlencode([(k,v) for k,v in socket.query_params.multi_items()
                       if not ovrtx or k not in {'workflow_id','asset_id'}])
    if query:
        upstream += "?" + query
    tasks = []
    close_code = 1000
    protocols = socket.scope.get("subprotocols", [])
    try:
        # Do not forward browser cookies, bearer credentials, or proxy headers.
        async with connect(
            upstream, open_timeout=5, max_size=4 * 1024 * 1024,
            subprotocols=protocols or None,
        ) as kit:
            await socket.accept(subprotocol=kit.subprotocol)

            async def to_kit():
                while True:
                    message = await socket.receive()
                    if message["type"] == "websocket.disconnect":
                        return
                    data = message.get("text")
                    await kit.send(data if data is not None else message["bytes"])

            async def to_browser():
                async for message in kit:
                    if isinstance(message, str):
                        await socket.send_text(message)
                    else:
                        await socket.send_bytes(message)

            tasks = [asyncio.create_task(to_kit()), asyncio.create_task(to_browser())]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
    except (OSError, InvalidHandshake):
        close_code = 1011
        logger.warning("Kit signaling upstream unavailable")
    except (ConnectionClosed, WebSocketDisconnect):
        pass
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await socket.close(code=close_code)
        except (RuntimeError, WebSocketDisconnect):
            pass
