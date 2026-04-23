import secrets

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from client.storage.crypto import (
    FORMAT_V2_MAGIC,
    LEGACY_SALT_SIZE,
    NONCE_SIZE,
    SALT_SIZE,
    StorageError,
    _decrypt,
    _derive_key,
    _encrypt,
)


def test_encrypt_uses_versioned_high_entropy_format():
    payload = _encrypt(b"hello", "password123")

    assert payload.startswith(FORMAT_V2_MAGIC)
    assert len(payload) > len(FORMAT_V2_MAGIC) + SALT_SIZE + NONCE_SIZE


def test_encrypt_round_trip():
    plaintext = b"top secret"

    encrypted = _encrypt(plaintext, "password123")

    assert _decrypt(encrypted, "password123") == plaintext


def test_encrypt_is_non_deterministic_for_same_input():
    plaintext = b"same input"

    first = _encrypt(plaintext, "password123")
    second = _encrypt(plaintext, "password123")

    assert first != second
    assert _decrypt(first, "password123") == plaintext
    assert _decrypt(second, "password123") == plaintext


def test_decrypt_legacy_payload():
    plaintext = b"legacy payload"
    salt = secrets.token_bytes(LEGACY_SALT_SIZE)
    nonce = secrets.token_bytes(NONCE_SIZE)
    key = _derive_key("password123", salt)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    legacy_blob = salt + nonce + ciphertext

    assert _decrypt(legacy_blob, "password123") == plaintext


def test_decrypt_rejects_short_payload():
    with pytest.raises(StorageError):
        _decrypt(b"tiny", "password123")
