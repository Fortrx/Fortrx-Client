from client.config import settings
from client.network.api import set_token
from client.storage.crypto import StorageError
from client.storage.db import delete_token as db_delete_token
from client.storage.db import load_token as db_load_token
from client.storage.db import save_token as db_save_token

def save_token(token:str, password: str | None = None):
    password = password or settings.STORAGE_PASSWORD
    if not password:
        raise StorageError("A storage password is required to save the token securely.")
    db_save_token(password, token)

def load_token(password: str | None = None):
    password = password or settings.STORAGE_PASSWORD
    if not password:
        return None
    return db_load_token(password)

def delete_token(password: str | None = None):
    password = password or settings.STORAGE_PASSWORD
    if not password:
        return
    db_delete_token(password)

def load_and_set_token(password: str | None = None):
    token = load_token(password)
    if token:
        set_token(token)
        return True
    return False
