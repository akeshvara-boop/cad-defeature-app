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

def relay_close_code(code):
    # Preserve application handoff codes (notably NVIDIA's 4001). Reserved
    # synthetic codes such as 1005/1006 must never be emitted on the wire.
    if code in {1000,1001,1002,1003,1007,1008,1009,1010,1011,1012,1013,1014}:
        return code
    return code if isinstance(code,int) and 3000 <= code <= 4999 else 1011

def relay_close_reason(reason):
    return str(reason or '').encode('utf-8')[:123].decode('utf-8',errors='ignore')


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
    close_reason = ''
    protocols = socket.scope.get("subprotocols", [])
    try:
        # Do not forward browser cookies, bearer credentials, or proxy headers.
        async with connect(
            upstream, open_timeout=5, max_size=4 * 1024 * 1024,
            subprotocols=protocols or None,
        ) as kit:
            await socket.accept(subprotocol=kit.subprotocol)

            async def to_kit():
                nonlocal close_code, close_reason
                while True:
                    message = await socket.receive()
                    if message["type"] == "websocket.disconnect":
                        close_code=relay_close_code(message.get('code'))
                        close_reason=relay_close_reason(message.get('reason'))
                        logger.info('Streaming signaling browser close code=%s path=%s',close_code,socket.url.path)
                        await kit.close(code=close_code,reason=close_reason)
                        return
                    data = message.get("text")
                    await kit.send(data if data is not None else message["bytes"])

            async def to_browser():
                nonlocal close_code, close_reason
                async for message in kit:
                    if isinstance(message, str):
                        await socket.send_text(message)
                    else:
                        await socket.send_bytes(message)
                close_code=relay_close_code(kit.close_code)
                close_reason=relay_close_reason(kit.close_reason)

            tasks = [asyncio.create_task(to_kit()), asyncio.create_task(to_browser())]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
    except (OSError, InvalidHandshake):
        close_code = 1011
        logger.warning("Kit signaling upstream unavailable")
    except ConnectionClosed as error:
        if error.rcvd:
            close_code=relay_close_code(error.rcvd.code)
            close_reason=relay_close_reason(error.rcvd.reason)
    except WebSocketDisconnect as error:
        close_code=relay_close_code(error.code)
        close_reason=relay_close_reason(error.reason)
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await socket.close(code=close_code,reason=close_reason)
        except (RuntimeError, WebSocketDisconnect):
            pass
