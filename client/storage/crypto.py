import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class StorageError(Exception):
    pass


def _derive_key(password: str, salt: bytes):
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    return kdf.derive(password.encode())


def _encrypt(data: bytes, password: str):
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _derive_key(password, salt)
    ciphertext = AESGCM(key).encrypt(nonce, data, None)
    return salt + nonce + ciphertext


def _decrypt(data: bytes, password: str):
    try:
        salt = data[:16]
        nonce = data[16:28]
        ciphertext = data[28:]
        key = _derive_key(password, salt)
        return AESGCM(key).decrypt(nonce, ciphertext, None)
    except Exception as exc:
        raise StorageError("Wrong password or corrupted file") from exc
