import asyncio
import contextlib
import os
import signal
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from client.network.auth import get_me
from client.network.api import get_token
from client.network.ws import listen
from client.services.messaging import refresh_presence_cache, sync_inbox
from client.storage.db import load_daemon_state, save_daemon_state, upsert_contact
from client.storage.token_store import load_and_set_token


HEARTBEAT_INTERVAL_SECONDS = 20


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def _status_payload(status: str, **extra):
    data = {"status": status, "updated_at": _utcnow(), **extra}
    save_daemon_state(data)
    return data


def _error_payload(stage: str, exc: Exception, **extra):
    return _status_payload(
        "error",
        stage=stage,
        error_type=type(exc).__name__,
        error=str(exc),
        traceback=traceback.format_exc(),
        **extra,
    )


async def _heartbeat_loop(storage_password: str):
    from client.network.presence import heartbeat

    while True:
        try:
            heartbeat()
            refresh_presence_cache(storage_password)
            _status_payload("running", last_heartbeat_at=_utcnow())
        except Exception as exc:
            _error_payload("heartbeat", exc)
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)


async def _handle_event(event: dict, storage_password: str):
    try:
        event_type = event.get("type")
        if event_type == "message_available":
            sync_inbox(storage_password)
        elif event_type == "presence_changed":
            upsert_contact(
                storage_password,
                int(event["user_id"]),
                event.get("username"),
                bool(event.get("is_online")),
            )
        elif event_type == "sync_hint":
            sync_inbox(storage_password)
    except Exception as exc:
        _error_payload("event", exc, event=event)


async def run_daemon_async(storage_password: str):
    try:
        if not load_and_set_token(storage_password):
            raise RuntimeError("No saved token found. Run 'fortrx login' first.")

        me = get_me()
        token = get_token()
        if not token:
            raise RuntimeError("No token available after unlock. Log in again.")
        _status_payload("starting", pid=os.getpid(), user_id=me["id"], username=me["username"])
        sync_inbox(storage_password)
        refresh_presence_cache(storage_password)

        heartbeat_task = asyncio.create_task(_heartbeat_loop(storage_password))
        try:
            _status_payload("running", pid=os.getpid(), user_id=me["id"], username=me["username"])
            await listen(
                me["id"],
                lambda event: _handle_event(event, storage_password),
                token=token,
            )
        finally:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await heartbeat_task
    except Exception as exc:
        _error_payload("startup", exc, pid=os.getpid())
        raise
    finally:
        state = load_daemon_state() or {}
        if state.get("status") != "error":
            _status_payload("stopped", pid=os.getpid(), user_id=state.get("user_id"), username=state.get("username"))


def run_daemon(storage_password: str):
    asyncio.run(run_daemon_async(storage_password))


def start_daemon(storage_password: str):
    state = daemon_status()
    if state.get("is_running"):
        return state

    env = os.environ.copy()
    env["FORTRX_DAEMON_PASSWORD"] = storage_password
    cmd = [sys.executable, "run.py", "daemon", "run"]

    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
        proc = subprocess.Popen(
            cmd,
            cwd=str(Path(__file__).resolve().parents[2]),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
        )
    else:
        proc = subprocess.Popen(
            cmd,
            cwd=str(Path(__file__).resolve().parents[2]),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )

    _status_payload("starting", pid=proc.pid)
    return {"is_running": True, "pid": proc.pid, "status": "starting"}


def daemon_status():
    state = load_daemon_state() or {"status": "stopped"}
    pid = state.get("pid")
    is_running = False
    if pid:
        try:
            os.kill(int(pid), 0)
            is_running = True
        except OSError:
            is_running = False
    state["is_running"] = is_running
    return state


def stop_daemon():
    state = daemon_status()
    pid = state.get("pid")
    if not pid or not state.get("is_running"):
        return {"stopped": False, "reason": "not_running"}

    try:
        os.kill(int(pid), signal.SIGTERM)
    except OSError as exc:
        return {"stopped": False, "reason": str(exc)}

    _status_payload("stopped", pid=pid)
    return {"stopped": True, "pid": pid}
