from pathlib import Path
from client.config import settings
from client.network.api import set_token

def save_token(token:str):
    path = Path(settings.TOKEN_FILE)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(token)

def load_token():
    path = Path(settings.TOKEN_FILE)
    if not path.exists():
        return None
    return path.read_text().strip()

def delete_token():
    path = Path(settings.TOKEN_FILE)
    if path.exists():
        path.unlink()

def load_and_set_token():
    token = load_token()
    if token:
        set_token(token)
        return True
    return False