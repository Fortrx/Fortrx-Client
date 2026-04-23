import struct

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


CURVE25519_KEY_PREFIX = b"\x05"
MLKEM768_KEY_PREFIX = b"\x08"
CURVE25519_F = b"\xff" * 32
SHA256_HASH_LEN = 32
ZERO_SALT_256 = b"\x00" * SHA256_HASH_LEN
X3DH_INFO = b"Fortrx"
PQXDH_INFO = b"Fortrx_CURVE25519_SHA-256_ML-KEM-768"


def hkdf_derive(*, ikm: bytes, salt: bytes, info: bytes, length: int) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=salt,
        info=info,
    ).derive(ikm)


def derive_x3dh_key_material(key_material: bytes, *, info: bytes) -> bytes:
    return hkdf_derive(
        ikm=CURVE25519_F + key_material,
        salt=ZERO_SALT_256,
        info=info,
        length=32,
    )


def encode_curve_public_key(public_key_bytes: bytes) -> bytes:
    return CURVE25519_KEY_PREFIX + public_key_bytes


def encode_mlkem_public_key(public_key_bytes: bytes) -> bytes:
    return MLKEM768_KEY_PREFIX + public_key_bytes


def encode_identity_associated_data(sender_ik_public: bytes, recipient_ik_public: bytes) -> bytes:
    sender = encode_curve_public_key(sender_ik_public)
    recipient = encode_curve_public_key(recipient_ik_public)
    return struct.pack(">H", len(sender)) + sender + recipient
