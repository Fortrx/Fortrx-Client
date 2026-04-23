import secrets

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class StorageError(Exception):
    pass


FORMAT_V2_MAGIC = b"FRXENC2\x00"
LEGACY_SALT_SIZE = 16
SALT_SIZE = 32
NONCE_SIZE = 12


def _derive_key(password: str, salt: bytes):
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    return kdf.derive(password.encode())


def _encrypt(data: bytes, password: str):
    # Use the OS CSPRNG via secrets for a high-entropy, non-deterministic salt.
    salt = secrets.token_bytes(SALT_SIZE)
    nonce = secrets.token_bytes(NONCE_SIZE)
    key = _derive_key(password, salt)
    ciphertext = AESGCM(key).encrypt(nonce, data, None)
    return FORMAT_V2_MAGIC + salt + nonce + ciphertext


def _decrypt_v2(data: bytes, password: str):
    min_len = len(FORMAT_V2_MAGIC) + SALT_SIZE + NONCE_SIZE + 16
    if len(data) < min_len:
        raise StorageError("Wrong password or corrupted file")
    offset = len(FORMAT_V2_MAGIC)
    salt = data[offset : offset + SALT_SIZE]
    nonce = data[offset + SALT_SIZE : offset + SALT_SIZE + NONCE_SIZE]
    ciphertext = data[offset + SALT_SIZE + NONCE_SIZE :]
    key = _derive_key(password, salt)
    return AESGCM(key).decrypt(nonce, ciphertext, None)


def _decrypt_legacy(data: bytes, password: str):
    min_len = LEGACY_SALT_SIZE + NONCE_SIZE + 16
    if len(data) < min_len:
        raise StorageError("Wrong password or corrupted file")
    salt = data[:LEGACY_SALT_SIZE]
    nonce = data[LEGACY_SALT_SIZE : LEGACY_SALT_SIZE + NONCE_SIZE]
    ciphertext = data[LEGACY_SALT_SIZE + NONCE_SIZE :]
    key = _derive_key(password, salt)
    return AESGCM(key).decrypt(nonce, ciphertext, None)


def _decrypt(data: bytes, password: str):
    try:
        if data.startswith(FORMAT_V2_MAGIC):
            return _decrypt_v2(data, password)
        return _decrypt_legacy(data, password)
    except Exception as exc:
        raise StorageError("Wrong password or corrupted file") from exc
