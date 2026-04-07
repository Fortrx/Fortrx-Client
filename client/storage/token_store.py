from pathlib import Path

from client.config import settings
from client.network.api import set_token
from client.storage.db import delete_token as db_delete_token
from client.storage.db import load_token as db_load_token
from client.storage.db import save_token as db_save_token

def save_token(token:str, password: str | None = None):
    password = password or settings.STORAGE_PASSWORD
    if password:
        db_save_token(password, token)
        return
    path = Path(settings.TOKEN_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token)

def load_token(password: str | None = None):
    password = password or settings.STORAGE_PASSWORD
    if password:
        token = db_load_token(password)
        if token:
            return token
    path = Path(settings.TOKEN_FILE)
    if not path.exists():
        return None
    return path.read_text().strip()

def delete_token(password: str | None = None):
    password = password or settings.STORAGE_PASSWORD
    if password:
        db_delete_token(password)
    path = Path(settings.TOKEN_FILE)
    if path.exists():
        path.unlink()

def load_and_set_token(password: str | None = None):
    token = load_token(password)
    if token:
        set_token(token)
        return True
    return False
