import asyncio
import json
import websockets
from client.config import settings
from client.network.api import get_token
from client.storage.token_store import load_token

async def connect(user_id:int, token:str=None):
    if not token:
        token = get_token() or load_token()
    if not token:
        raise ConnectionError("No token found, Login first.")
    uri = f"{settings.SERVER_URL.replace('http','ws')}/ws/{user_id}?token={token}"
    return await websockets.connect(uri)

async def listen(user_id:int, on_message:callable, token:str=None):
    if not token:
        token = get_token() or load_token()
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
        except Exception as exc:
            exc_name = type(exc).__name__
            if exc_name not in {"ConnectionClosedOK", "ConnectionClosedError"}:
                pass
        finally:
            pass
        await asyncio.sleep(retry_delay)
        retry_delay = min(retry_delay*2,10)

async def keepalive(ws,interval: int= 30):
    while True:
        await asyncio.sleep(interval)
        try:
            await ws.send("ping")
        except:
            break
