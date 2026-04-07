import asyncio
import contextlib
import inspect
import json

import websockets

from client.config import settings
from client.network.api import get_token


_WS_HEADERS_KWARG = (
    "additional_headers"
    if "additional_headers" in inspect.signature(websockets.connect).parameters
    else "extra_headers"
)


def _ws_url() -> str:
    if settings.SERVER_URL.startswith("https://"):
        return settings.SERVER_URL.replace("https://", "wss://", 1)
    return settings.SERVER_URL.replace("http://", "ws://", 1)


async def connect(user_id: int, token: str | None = None):
    token = token or get_token()
    if not token:
        raise ConnectionError("No token found, Login first.")
    uri = f"{_ws_url()}/ws/{user_id}"
    headers = {"Authorization": f"Bearer {token}"}
    kwargs = {
        _WS_HEADERS_KWARG: headers,
        "open_timeout": settings.REQUEST_TIMEOUT_SECONDS,
        "close_timeout": settings.REQUEST_TIMEOUT_SECONDS,
        "ping_interval": None,
    }
    return await websockets.connect(uri, **kwargs)


async def listen(user_id: int, on_message: callable, token: str | None = None):
    token = token or get_token()
    retry_delay = 2
    while True:
        try:
            async with await connect(user_id, token) as ws:
                retry_delay = 2
                keepalive_task = asyncio.create_task(keepalive(ws))
                try:
                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                        except Exception:
                            continue
                        if data == "pong":
                            continue
                        await on_message(data)
                finally:
                    keepalive_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await keepalive_task
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(retry_delay)
        retry_delay = min(retry_delay * 2, 10)


async def keepalive(ws, interval: int = 30):
    while True:
        await asyncio.sleep(interval)
        try:
            await ws.send("ping")
        except Exception:
            break
