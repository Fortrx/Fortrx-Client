import typer
from pathlib import Path
from rich.console import Console

from client.config import settings
from client.network.auth import get_me
from client.storage.crypto import StorageError
from client.storage.db import keys_exist as db_keys_exist
from client.storage.db import load_keys as db_load_keys
from client.storage.db import save_keys as db_save_keys

console = Console()

def has_kyber_keys(keys:dict):
    return (
        "kyber_prekey_public" in keys and
        keys["kyber_prekey_public"] is not None
    )

def save_keys(keys:dict,password:str = None):
    password = password or settings.STORAGE_PASSWORD
    if not password:
        raise StorageError("No storage password set")
    db_save_keys(password=password, keys=keys)

def load_keys(password:str=None):
    password = password or settings.STORAGE_PASSWORD
    user_id = None
    try:
        me = get_me()
        user_id = me.get("id")
    except Exception:
        user_id = None
    return db_load_keys(password=password, user_id=user_id)

def keys_exist():
    return db_keys_exist(settings.STORAGE_PASSWORD or None)

def load_keys_or_exit(password:str=None):
    try:
        keys = load_keys(password)
        if not has_kyber_keys(keys):
            console.print("[yellow]⚠ No post-quantum keys found[/yellow]")
            console.print("[dim]Run 'fortress init --force' to upgrade[/dim]")
        return keys
    except StorageError as e:
        console.print(f"[red]❌ Cannot load keys:[/red] {e}")
        console.print("[dim] Run 'fortrx init' to set up your keys.[/din]")
        raise typer.Exit(1)
