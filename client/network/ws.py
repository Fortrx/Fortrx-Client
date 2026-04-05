import asyncio
import json
import websockets
from client.config import settings
from client.storage.token_store import load_token

async def connect(user_id:int, token:str=None):
    if not token:
        token = load_token()
    if not token:
        raise ConnectionError("No token found, Login first.")
    uri = f"{settings.SERVER_URL.replace('http','ws')}/ws/{user_id}?token={token}"
    return await websockets.connect(uri)

async def listen(user_id:int, on_messaage:callable, token:str=None):
    if not token:
        token = load_token()
    MAX_RETRIES = 50
    retry_delay = 2
    for attempt in range(MAX_RETRIES):
        try:
            async with await connect(user_id, token) as ws:
                retry_delay = 2
                await ws.send("ping")
                async for raw in ws:
                    try:
                        data = json.loads(raw)
                    except Exception:
                        continue
                    if data == "pong":
                        continue
                    if data.get("type") == "new_message":
                        await on_messaage(data)
        except websockets.exceptions.ConnectionClosedOK:
            break
        except websockets.exceptions.ConnectionClosedError:
            pass
        except Exception:
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