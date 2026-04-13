import asyncio
import contextlib
import os
import signal
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from client.config import settings
from client.network.auth import get_me
from client.network.api import get_token
from client.network.ws import listen
from client.services.messaging import refresh_presence_cache, sync_inbox
from client.storage.db import load_daemon_state, save_daemon_state, upsert_contact
from client.storage.token_store import load_and_set_token

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
        **extra,
    )


def _bootstrap_dir() -> Path:
    return Path(settings.LOCAL_STORAGE_PATH) / "runtime"


def _cleanup_stale_bootstrap_secrets(max_age_seconds: int = 300):
    bootstrap_dir = _bootstrap_dir()
    if not bootstrap_dir.exists():
        return
    cutoff = datetime.now(timezone.utc).timestamp() - max_age_seconds
    for path in bootstrap_dir.glob("daemon-*.secret"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except Exception:
            continue


def _write_bootstrap_secret(storage_password: str) -> Path:
    _cleanup_stale_bootstrap_secrets()
    bootstrap_dir = _bootstrap_dir()
    bootstrap_dir.mkdir(parents=True, exist_ok=True)
    path = bootstrap_dir / f"daemon-{uuid.uuid4().hex}.secret"
    path.write_text(storage_password, encoding="utf-8")
    with contextlib.suppress(Exception):
        os.chmod(path, 0o600)
    return path


def consume_bootstrap_secret(path_value: str | None) -> str | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    finally:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()


async def _handle_event(event: dict, storage_password: str):
    try:
        event_type = event.get("type")
        if event_type == "message_available":
            await asyncio.to_thread(sync_inbox, storage_password)
        elif event_type == "presence_changed":
            await asyncio.to_thread(
                upsert_contact,
                storage_password,
                int(event["user_id"]),
                event.get("username"),
                bool(event.get("is_online")),
            )
        elif event_type == "sync_hint":
            await asyncio.to_thread(sync_inbox, storage_password)
            if event.get("refresh_presence"):
                await asyncio.to_thread(refresh_presence_cache, storage_password)
            _status_payload("running", last_sync_at=_utcnow(), sync_reason=event.get("reason"))
    except Exception as exc:
        _error_payload("event", exc, event=event)


async def run_daemon_async(storage_password: str):
    try:
        if not await asyncio.to_thread(load_and_set_token, storage_password):
            raise RuntimeError("No saved token found. Run 'fortrx login' first.")

        me = await asyncio.to_thread(get_me)
        token = get_token()
        if not token:
            raise RuntimeError("No token available after unlock. Log in again.")
        _status_payload("starting", pid=os.getpid(), user_id=me["id"], username=me["username"])
        await asyncio.to_thread(sync_inbox, storage_password)
        await asyncio.to_thread(refresh_presence_cache, storage_password)
        _status_payload("running", pid=os.getpid(), user_id=me["id"], username=me["username"])
        await listen(
            me["id"],
            lambda event: _handle_event(event, storage_password),
            token=token,
        )
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
    bootstrap_path = _write_bootstrap_secret(storage_password)
    cmd = [sys.executable, "run.py", "daemon", "run", "--password-file", str(bootstrap_path)]

    try:
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
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            bootstrap_path.unlink()
        raise

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
