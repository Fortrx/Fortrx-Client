import base64
import copy
import hashlib
import hmac
import json
import os
import struct
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat


MAX_SKIP = 1000
NONCE_SIZE = 12


@dataclass
class RatchetState:
    root_key: bytes
    sending_chain_key: bytes | None
    recv_chain_key: bytes | None
    dh_sending_private: bytes
    dh_sending_public: bytes
    dh_remote_public: bytes | None
    send_count: int = 0
    recv_count: int = 0
    previous_send_count: int = 0
    skipped_message_keys: dict | None = None


def _hkdf(salt: bytes, input_key: bytes):
    out = HKDF(
        algorithm=hashes.SHA256(),
        length=64,
        salt=salt,
        info=b"Fortrx Ratchet",
    ).derive(input_key)
    return out[:32], out[32:]


def _encode_header(header: dict) -> bytes:
    return json.dumps(header, sort_keys=True, separators=(",", ":")).encode()


def _concat_ad(associated_data: bytes, header: dict) -> bytes:
    return struct.pack(">I", len(associated_data)) + associated_data + _encode_header(header)


def _gen_dh_keypair():
    priv = X25519PrivateKey.generate()
    pub = priv.public_key()
    return (
        priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()),
        pub.public_bytes(Encoding.Raw, PublicFormat.Raw),
    )


def _dh(priv_bytes: bytes, pub_bytes: bytes):
    priv = X25519PrivateKey.from_private_bytes(priv_bytes)
    pub = X25519PublicKey.from_public_bytes(pub_bytes)
    return priv.exchange(pub)


def _remote_key_id(public_key_bytes: bytes | None) -> str | None:
    if public_key_bytes is None:
        return None
    return base64.b64encode(public_key_bytes).decode()


def _header_message_number(header: dict) -> int:
    if "n" in header:
        return int(header["n"])
    return max(int(header.get("send_count", 1)) - 1, 0)


def _header_previous_chain_length(header: dict) -> int:
    if "pn" in header:
        return int(header["pn"])
    return int(header.get("recv_count", 0))


def _header_key(header: dict) -> tuple[str, int]:
    return header["dh_public"], _header_message_number(header)


def _clone_state(state: RatchetState) -> RatchetState:
    return copy.deepcopy(state)


def _commit_state(target: RatchetState, source: RatchetState):
    target.__dict__.clear()
    target.__dict__.update(source.__dict__)


def init_ratchet_sender(shared_secret: bytes, recipient_ratchet_public: bytes):
    priv, pub = _gen_dh_keypair()
    dh_out = _dh(priv, recipient_ratchet_public)
    root_key, sending_chain = _hkdf(shared_secret, dh_out)
    return RatchetState(
        root_key=root_key,
        sending_chain_key=sending_chain,
        recv_chain_key=None,
        dh_sending_private=priv,
        dh_sending_public=pub,
        dh_remote_public=recipient_ratchet_public,
        skipped_message_keys={},
    )


def init_ratchet_receiver(shared_secret: bytes, our_ratchet_private: bytes):
    priv = X25519PrivateKey.from_private_bytes(our_ratchet_private)
    pub = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return RatchetState(
        root_key=shared_secret,
        sending_chain_key=None,
        recv_chain_key=None,
        dh_sending_private=our_ratchet_private,
        dh_sending_public=pub,
        dh_remote_public=None,
        skipped_message_keys={},
    )


def derive_message_key(chain_key: bytes):
    msg_key = hmac.new(chain_key, b"\x01", hashlib.sha256).digest()
    next_chain = hmac.new(chain_key, b"\x02", hashlib.sha256).digest()
    return msg_key, next_chain


def _ratchet_send_key(state: RatchetState):
    if state.sending_chain_key is None:
        raise ValueError("sending chain key is not initialized")
    n = state.send_count
    msg_key, next_chain = derive_message_key(state.sending_chain_key)
    state.sending_chain_key = next_chain
    state.send_count += 1
    return n, msg_key


def _try_skipped_message_key(state: RatchetState, header: dict):
    skipped = state.skipped_message_keys or {}
    key = _header_key(header)
    msg_key = skipped.pop(key, None)
    if state.skipped_message_keys is None:
        state.skipped_message_keys = skipped
    return msg_key


def _skip_message_keys(state: RatchetState, until: int):
    if state.recv_count + MAX_SKIP < until:
        raise ValueError("too many skipped message keys requested")
    if state.recv_chain_key is None or state.dh_remote_public is None:
        return
    remote_key_id = _remote_key_id(state.dh_remote_public)
    while state.recv_count < until:
        msg_key, next_chain = derive_message_key(state.recv_chain_key)
        state.recv_chain_key = next_chain
        if state.skipped_message_keys is None:
            state.skipped_message_keys = {}
        state.skipped_message_keys[(remote_key_id, state.recv_count)] = msg_key
        if len(state.skipped_message_keys) > MAX_SKIP:
            raise ValueError("too many skipped message keys stored")
        state.recv_count += 1


def dh_ratchet_step(state: RatchetState, their_new_public: bytes):
    dh_out = _dh(state.dh_sending_private, their_new_public)
    new_root, new_recv_chain = _hkdf(state.root_key, dh_out)
    new_priv, new_pub = _gen_dh_keypair()
    dh_out2 = _dh(new_priv, their_new_public)
    new_root2, new_send_chain = _hkdf(new_root, dh_out2)

    state.previous_send_count = state.send_count
    state.send_count = 0
    state.recv_count = 0
    state.root_key = new_root2
    state.recv_chain_key = new_recv_chain
    state.sending_chain_key = new_send_chain
    state.dh_sending_private = new_priv
    state.dh_sending_public = new_pub
    state.dh_remote_public = their_new_public
    if state.skipped_message_keys is None:
        state.skipped_message_keys = {}
    return state


def ratchet_encrypt(
    state: RatchetState,
    plaintext: bytes,
    associated_data: bytes = b"",
    header_updates: dict | None = None,
):
    n, msg_key = _ratchet_send_key(state)
    header = {
        "dh_public": base64.b64encode(state.dh_sending_public).decode(),
        "pn": state.previous_send_count,
        "n": n,
        # Legacy compatibility for older stored headers and tests.
        "send_count": n + 1,
        "recv_count": state.recv_count,
    }
    if header_updates:
        header.update(header_updates)

    nonce = os.urandom(NONCE_SIZE)
    ciphertext = AESGCM(msg_key).encrypt(nonce, plaintext, _concat_ad(associated_data, header))
    return header, nonce + ciphertext


def ratchet_decrypt(
    state: RatchetState,
    header: dict,
    ciphertext: bytes,
    associated_data: bytes = b"",
):
    if len(ciphertext) < NONCE_SIZE + 16:
        raise ValueError("ciphertext too short")

    candidate = _clone_state(state)
    msg_key = _try_skipped_message_key(candidate, header)
    their_pub = base64.b64decode(header["dh_public"])

    if msg_key is None:
        if candidate.dh_remote_public != their_pub:
            _skip_message_keys(candidate, _header_previous_chain_length(header))
            dh_ratchet_step(candidate, their_pub)

        target = _header_message_number(header)
        _skip_message_keys(candidate, target)
        if candidate.recv_chain_key is None:
            raise ValueError("receiving chain key is not initialized")
        msg_key, next_chain = derive_message_key(candidate.recv_chain_key)
        candidate.recv_chain_key = next_chain
        candidate.recv_count += 1

    nonce = ciphertext[:NONCE_SIZE]
    data = ciphertext[NONCE_SIZE:]
    plaintext = AESGCM(msg_key).decrypt(nonce, data, _concat_ad(associated_data, header))
    _commit_state(state, candidate)
    return plaintext
