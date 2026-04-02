import os,json,typer
from pathlib import Path
from rich.console import Console

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from client.config import settings

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
    path = Path(settings.KEYS_FILE)
    path.parent.mkdir(parents=True,exist_ok=True)
    data = json.dumps(keys).encode()
    encrypted = _encrypt(data,password)
    path.write_bytes(encrypted)

def load_keys(password:str=None):
    password = password or settings.STORAGE_PASSWORD
    path = Path(settings.KEYS_FILE)
    if not path.exists():
        raise StorageError("No keys found. Run 'fortrx init' first.")
    encrypted = path.read_bytes()
    data = _decrypt(encrypted,password)
    return json.loads(data)

def keys_exist():
    return Path(settings.KEYS_FILE).exists()

def load_keys_or_exit(password:str=None):
    try:
        return load_keys(password)
    except StorageError as e:
        console.print(f"[red]❌ Cannot load keys:[/red] {e}")
        console.print("[dim] Run 'fortrx init' to set up your keys.[/din]")
        raise typer.Exit(1)