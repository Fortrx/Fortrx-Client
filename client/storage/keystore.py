import os,json,typer
from pathlib import Path
from rich.console import Console

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from client.config import settings
from client.network.auth import get_me

console = Console()

class StorageError(Exception):
    pass

def _derive_key(password:str,salt:bytes):
    kdf = PBKDF2HMAC(
        algorithm = hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    return kdf.derive(password.encode())

def _encrypt(data:bytes,password:str):
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _derive_key(password,salt)
    ciphertext = AESGCM(key).encrypt(nonce,data,None)
    return salt + nonce + ciphertext

def _decrypt(data:bytes,password:str):
    try:
        salt = data[:16]
        nonce = data[16:28]
        ciphertext = data[28:]
        key = _derive_key(password,salt)
        return AESGCM(key).decrypt(nonce,ciphertext,None)
    except Exception:
        raise StorageError("Wrong password or corrupted file")

def save_keys(keys:dict,password:str = None):
    password = password or settings.STORAGE_PASSWORD
    if not password:
        raise StorageError("No storage password set")
    # Save keys to a per-user file to avoid overwriting other accounts.
    user_id = keys.get("user_id")
    path_dir = Path(settings.LOCAL_STORAGE_PATH)
    path_dir.mkdir(parents=True,exist_ok=True)
    data = json.dumps(keys).encode()
    encrypted = _encrypt(data,password)
    if user_id:
        user_path = path_dir / f"keys_{user_id}.enc"
        user_path.write_bytes(encrypted)
    # Also save legacy path for compatibility
    legacy_path = Path(settings.KEYS_FILE)
    legacy_path.parent.mkdir(parents=True,exist_ok=True)
    legacy_path.write_bytes(encrypted)

def load_keys(password:str=None):
    password = password or settings.STORAGE_PASSWORD
    # Prefer a per-user key file when possible
    # Try to determine current user via API if token is set
    user_path = None
    try:
        me = get_me()
        uid = me.get("id")
        candidate = Path(settings.LOCAL_STORAGE_PATH) / f"keys_{uid}.enc"
        if candidate.exists():
            user_path = candidate
    except Exception:
        # ignore any errors; we'll try other fallbacks
        user_path = None

    if user_path and user_path.exists():
        encrypted = user_path.read_bytes()
    else:
        # fallback to legacy file
        legacy = Path(settings.KEYS_FILE)
        if legacy.exists():
            encrypted = legacy.read_bytes()
        else:
            # if there's exactly one per-user file, use it
            p = Path(settings.LOCAL_STORAGE_PATH)
            candidates = list(p.glob('keys_*.enc'))
            if len(candidates) == 1:
                encrypted = candidates[0].read_bytes()
            else:
                raise StorageError("No keys found. Run 'fortrx init' first.")

    data = _decrypt(encrypted,password)
    return json.loads(data)

def keys_exist():
    legacy = Path(settings.KEYS_FILE)
    if legacy.exists():
        return True
    p = Path(settings.LOCAL_STORAGE_PATH)
    return any(p.glob('keys_*.enc'))

def load_keys_or_exit(password:str=None):
    try:
        return load_keys(password)
    except StorageError as e:
        console.print(f"[red]❌ Cannot load keys:[/red] {e}")
        console.print("[dim] Run 'fortrx init' to set up your keys.[/din]")
        raise typer.Exit(1)