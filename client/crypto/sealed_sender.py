import base64
import hmac
import json
import os

from cryptography.hazmat.primitives import hashes, hmac as crypto_hmac
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from client.crypto.protocol_kdf import hkdf_derive


SEALED_SENDER_V2_MAGIC = b"FSS2"
IDENTITY_KEY_SIZE = 32
NONCE_SIZE = 12
MAC_SIZE = 32
CTR_IV = b"\x00" * 16
UNIDENTIFIED_DELIVERY_LABEL = b"UnidentifiedDelivery"


def _json_safe(obj):
    if isinstance(obj, (bytes, bytearray)):
        return base64.b64encode(bytes(obj)).decode()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(i) for i in obj]
    if hasattr(obj, "public_bytes"):
        return base64.b64encode(
            obj.public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
        ).decode()
    return obj


def _legacy_seal(
    sender_id: int,
    sender_ik_public: bytes,
    recipient_ik_public: bytes,
    ciphertext: bytes,
    header: dict,
):
    ek_private = X25519PrivateKey.generate()
    ek_public = ek_private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    recipient_pub = X25519PublicKey.from_public_bytes(recipient_ik_public)
    dh_out = ek_private.exchange(recipient_pub)

    key = hkdf_derive(
        ikm=dh_out,
        salt=b"\x00" * 32,
        info=b"Fortrx Sealed Sender",
        length=32,
    )
    inner = json.dumps(
        {
            "sender_id": sender_id,
            "sender_ik_public": base64.b64encode(sender_ik_public).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode(),
            "header": _json_safe(header),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    nonce = os.urandom(NONCE_SIZE)
    encrypted = AESGCM(key).encrypt(nonce, inner, None)
    return ek_public + nonce + encrypted


def _legacy_unseal(recipient_ik_private: bytes, sealed_blob: bytes):
    ek_public = sealed_blob[:IDENTITY_KEY_SIZE]
    nonce = sealed_blob[IDENTITY_KEY_SIZE : IDENTITY_KEY_SIZE + NONCE_SIZE]
    encrypted = sealed_blob[IDENTITY_KEY_SIZE + NONCE_SIZE :]

    recipient_priv = X25519PrivateKey.from_private_bytes(recipient_ik_private)
    ek_pub = X25519PublicKey.from_public_bytes(ek_public)
    dh_out = recipient_priv.exchange(ek_pub)

    key = hkdf_derive(
        ikm=dh_out,
        salt=b"\x00" * 32,
        info=b"Fortrx Sealed Sender",
        length=32,
    )
    inner = AESGCM(key).decrypt(nonce, encrypted, None)
    return json.loads(inner)


def _aes_ctr_crypt(key: bytes, data: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.CTR(CTR_IV))
    ctx = cipher.encryptor()
    return ctx.update(data) + ctx.finalize()


def _hmac_sha256(key: bytes, data: bytes) -> bytes:
    mac = crypto_hmac.HMAC(key, hashes.SHA256())
    mac.update(data)
    return mac.finalize()


def seal(
    sender_id: int,
    sender_ik_public: bytes,
    recipient_ik_public: bytes,
    ciphertext: bytes,
    header: dict,
    sender_ik_private: bytes | None = None,
):
    if sender_ik_private is None:
        return _legacy_seal(
            sender_id=sender_id,
            sender_ik_public=sender_ik_public,
            recipient_ik_public=recipient_ik_public,
            ciphertext=ciphertext,
            header=header,
        )

    sender_private = X25519PrivateKey.from_private_bytes(sender_ik_private)
    derived_public = sender_private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    if derived_public != sender_ik_public:
        raise ValueError("sender identity private/public key mismatch")

    recipient_pub = X25519PublicKey.from_public_bytes(recipient_ik_public)

    ephemeral_private = X25519PrivateKey.generate()
    ephemeral_public = ephemeral_private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ephemeral_shared_secret = ephemeral_private.exchange(recipient_pub)
    ephemeral_material = hkdf_derive(
        ikm=ephemeral_shared_secret,
        salt=UNIDENTIFIED_DELIVERY_LABEL + recipient_ik_public + ephemeral_public,
        info=b"",
        length=96,
    )
    e_chain = ephemeral_material[:32]
    e_cipher_key = ephemeral_material[32:64]
    e_mac_key = ephemeral_material[64:96]
    e_ciphertext = _aes_ctr_crypt(e_cipher_key, sender_ik_public)
    e_mac = _hmac_sha256(e_mac_key, e_ciphertext)

    sender_shared_secret = sender_private.exchange(recipient_pub)
    sender_material = hkdf_derive(
        ikm=sender_shared_secret,
        salt=e_chain + e_ciphertext + e_mac,
        info=b"",
        length=64,
    )
    s_cipher_key = sender_material[:32]
    s_mac_key = sender_material[32:64]
    inner = json.dumps(
        {
            "sender_id": sender_id,
            "ciphertext": base64.b64encode(ciphertext).decode(),
            "header": _json_safe(header),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    s_ciphertext = _aes_ctr_crypt(s_cipher_key, inner)
    s_mac = _hmac_sha256(s_mac_key, s_ciphertext)
    return SEALED_SENDER_V2_MAGIC + ephemeral_public + e_ciphertext + e_mac + s_ciphertext + s_mac


def _unseal_v2(recipient_ik_private: bytes, sealed_blob: bytes):
    offset = len(SEALED_SENDER_V2_MAGIC)
    ephemeral_public = sealed_blob[offset : offset + IDENTITY_KEY_SIZE]
    offset += IDENTITY_KEY_SIZE
    e_ciphertext = sealed_blob[offset : offset + IDENTITY_KEY_SIZE]
    offset += IDENTITY_KEY_SIZE
    e_mac = sealed_blob[offset : offset + MAC_SIZE]
    offset += MAC_SIZE
    s_ciphertext = sealed_blob[offset:-MAC_SIZE]
    s_mac = sealed_blob[-MAC_SIZE:]

    recipient_private = X25519PrivateKey.from_private_bytes(recipient_ik_private)
    recipient_public = recipient_private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ephemeral_pub = X25519PublicKey.from_public_bytes(ephemeral_public)

    ephemeral_shared_secret = recipient_private.exchange(ephemeral_pub)
    ephemeral_material = hkdf_derive(
        ikm=ephemeral_shared_secret,
        salt=UNIDENTIFIED_DELIVERY_LABEL + recipient_public + ephemeral_public,
        info=b"",
        length=96,
    )
    e_chain = ephemeral_material[:32]
    e_cipher_key = ephemeral_material[32:64]
    e_mac_key = ephemeral_material[64:96]
    expected_e_mac = _hmac_sha256(e_mac_key, e_ciphertext)
    if not hmac.compare_digest(expected_e_mac, e_mac):
        raise ValueError("sealed sender identity MAC verification failed")
    sender_ik_public = _aes_ctr_crypt(e_cipher_key, e_ciphertext)

    sender_public = X25519PublicKey.from_public_bytes(sender_ik_public)
    sender_shared_secret = recipient_private.exchange(sender_public)
    sender_material = hkdf_derive(
        ikm=sender_shared_secret,
        salt=e_chain + e_ciphertext + e_mac,
        info=b"",
        length=64,
    )
    s_cipher_key = sender_material[:32]
    s_mac_key = sender_material[32:64]
    expected_s_mac = _hmac_sha256(s_mac_key, s_ciphertext)
    if not hmac.compare_digest(expected_s_mac, s_mac):
        raise ValueError("sealed sender message MAC verification failed")
    inner = _aes_ctr_crypt(s_cipher_key, s_ciphertext)
    payload = json.loads(inner)
    payload["sender_ik_public"] = base64.b64encode(sender_ik_public).decode()
    return payload


def unseal(recipient_ik_private: bytes, sealed_blob: bytes):
    if sealed_blob.startswith(SEALED_SENDER_V2_MAGIC):
        return _unseal_v2(recipient_ik_private, sealed_blob)
    return _legacy_unseal(recipient_ik_private, sealed_blob)
