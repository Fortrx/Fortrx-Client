import copy
import os

import pytest
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

from client.crypto.pq_keys import generate_kyber_keypair, kyber_decaps
from client.crypto.pqxdh import pqxdh_receiver, pqxdh_sender
from client.crypto.protocol_kdf import CURVE25519_F, PQXDH_INFO, X3DH_INFO, ZERO_SALT_256, hkdf_derive
from client.crypto.ratchet import init_ratchet_receiver, init_ratchet_sender, ratchet_decrypt, ratchet_encrypt
from client.crypto.sealed_sender import SEALED_SENDER_V2_MAGIC, seal, unseal
from client.crypto.x3dh import x3dh_receiver, x3dh_sender


def _raw_private(key: X25519PrivateKey) -> bytes:
    return key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())


def _raw_public(key: X25519PublicKey) -> bytes:
    return key.public_bytes(Encoding.Raw, PublicFormat.Raw)


def _exchange(private_bytes: bytes, public_bytes: bytes) -> bytes:
    private_key = X25519PrivateKey.from_private_bytes(private_bytes)
    public_key = X25519PublicKey.from_public_bytes(public_bytes)
    return private_key.exchange(public_key)


def test_x3dh_matches_signal_style_kdf_construction():
    alice_identity = X25519PrivateKey.generate()
    bob_identity = X25519PrivateKey.generate()
    bob_signed_prekey = X25519PrivateKey.generate()
    bob_one_time_prekey = X25519PrivateKey.generate()

    alice_identity_private = _raw_private(alice_identity)
    alice_identity_public = _raw_public(alice_identity.public_key())
    bob_identity_private = _raw_private(bob_identity)
    bob_identity_public = _raw_public(bob_identity.public_key())
    bob_signed_prekey_private = _raw_private(bob_signed_prekey)
    bob_signed_prekey_public = _raw_public(bob_signed_prekey.public_key())
    bob_one_time_prekey_private = _raw_private(bob_one_time_prekey)
    bob_one_time_prekey_public = _raw_public(bob_one_time_prekey.public_key())

    sender = x3dh_sender(
        ik_a_private=alice_identity_private,
        ik_b_public=bob_identity_public,
        spk_b_public=bob_signed_prekey_public,
        opk_b_public=bob_one_time_prekey_public,
    )
    receiver = x3dh_receiver(
        ik_b_private=bob_identity_private,
        spk_b_private=bob_signed_prekey_private,
        ik_a_public=alice_identity_public,
        ek_a_public=sender["ek_public"],
        opk_b_private=bob_one_time_prekey_private,
    )

    dh_material = b"".join(
        [
            _exchange(bob_signed_prekey_private, alice_identity_public),
            _exchange(bob_identity_private, sender["ek_public"]),
            _exchange(bob_signed_prekey_private, sender["ek_public"]),
            _exchange(bob_one_time_prekey_private, sender["ek_public"]),
        ]
    )
    manual = hkdf_derive(
        ikm=CURVE25519_F + dh_material,
        salt=ZERO_SALT_256,
        info=X3DH_INFO,
        length=32,
    )

    assert sender["shared_secret"] == receiver == manual


def test_pqxdh_matches_signal_style_hybrid_kdf_construction():
    try:
        bob_kyber = generate_kyber_keypair()
    except RuntimeError as exc:
        pytest.skip(str(exc))

    alice_identity = X25519PrivateKey.generate()
    bob_identity = X25519PrivateKey.generate()
    bob_signed_prekey = X25519PrivateKey.generate()
    bob_one_time_prekey = X25519PrivateKey.generate()

    alice_identity_private = _raw_private(alice_identity)
    alice_identity_public = _raw_public(alice_identity.public_key())
    bob_identity_private = _raw_private(bob_identity)
    bob_identity_public = _raw_public(bob_identity.public_key())
    bob_signed_prekey_private = _raw_private(bob_signed_prekey)
    bob_signed_prekey_public = _raw_public(bob_signed_prekey.public_key())
    bob_one_time_prekey_private = _raw_private(bob_one_time_prekey)
    bob_one_time_prekey_public = _raw_public(bob_one_time_prekey.public_key())

    sender = pqxdh_sender(
        ik_a_private=alice_identity_private,
        ik_b_public=bob_identity_public,
        spk_b_public=bob_signed_prekey_public,
        kyber_b_public=bob_kyber["public"],
        opk_b_public=bob_one_time_prekey_public,
    )
    receiver = pqxdh_receiver(
        ik_b_private=bob_identity_private,
        spk_b_private=bob_signed_prekey_private,
        kyber_b_private=bob_kyber["private"],
        ik_a_public=alice_identity_public,
        ek_a_public=sender["ek_public"],
        kyber_ciphertext=sender["kyber_ciphertext"],
        opk_b_private=bob_one_time_prekey_private,
    )

    hybrid_material = b"".join(
        [
            _exchange(bob_signed_prekey_private, alice_identity_public),
            _exchange(bob_identity_private, sender["ek_public"]),
            _exchange(bob_signed_prekey_private, sender["ek_public"]),
            _exchange(bob_one_time_prekey_private, sender["ek_public"]),
            kyber_decaps(bob_kyber["private"], sender["kyber_ciphertext"]),
        ]
    )
    manual = hkdf_derive(
        ikm=CURVE25519_F + hybrid_material,
        salt=ZERO_SALT_256,
        info=PQXDH_INFO,
        length=32,
    )

    assert sender["shared_secret"] == receiver == manual


def test_ratchet_preserves_skipped_keys_across_dh_ratchet():
    shared_secret = os.urandom(32)
    bob_initial = X25519PrivateKey.generate()
    bob_initial_private = _raw_private(bob_initial)
    bob_initial_public = _raw_public(bob_initial.public_key())

    alice = init_ratchet_sender(shared_secret, bob_initial_public)
    bob = init_ratchet_receiver(shared_secret, bob_initial_private)

    header0, ciphertext0 = ratchet_encrypt(alice, b"message-0")
    header1, ciphertext1 = ratchet_encrypt(alice, b"message-1")

    assert ratchet_decrypt(bob, header1, ciphertext1) == b"message-1"

    reply_header, reply_ciphertext = ratchet_encrypt(bob, b"reply-0")
    assert ratchet_decrypt(alice, reply_header, reply_ciphertext) == b"reply-0"

    header2, ciphertext2 = ratchet_encrypt(alice, b"message-2")
    assert ratchet_decrypt(bob, header2, ciphertext2) == b"message-2"

    # Delayed delivery from the previous sending chain must still decrypt.
    assert ratchet_decrypt(bob, header0, ciphertext0) == b"message-0"


def test_ratchet_does_not_commit_state_on_auth_failure():
    shared_secret = os.urandom(32)
    bob_initial = X25519PrivateKey.generate()
    bob_initial_private = _raw_private(bob_initial)
    bob_initial_public = _raw_public(bob_initial.public_key())

    alice = init_ratchet_sender(shared_secret, bob_initial_public)
    bob = init_ratchet_receiver(shared_secret, bob_initial_private)

    header, ciphertext = ratchet_encrypt(alice, b"authenticated")
    tampered = ciphertext[:-1] + bytes([ciphertext[-1] ^ 0x01])
    snapshot = copy.deepcopy(bob)

    with pytest.raises(Exception):
        ratchet_decrypt(bob, header, tampered)

    assert bob.__dict__ == snapshot.__dict__
    assert ratchet_decrypt(bob, header, ciphertext) == b"authenticated"


def test_sealed_sender_v2_round_trip_and_legacy_fallback():
    recipient_private = X25519PrivateKey.generate()
    sender_private = X25519PrivateKey.generate()

    recipient_private_bytes = _raw_private(recipient_private)
    recipient_public_bytes = _raw_public(recipient_private.public_key())
    sender_private_bytes = _raw_private(sender_private)
    sender_public_bytes = _raw_public(sender_private.public_key())

    upgraded = seal(
        sender_id=7,
        sender_ik_private=sender_private_bytes,
        sender_ik_public=sender_public_bytes,
        recipient_ik_public=recipient_public_bytes,
        ciphertext=b"ciphertext",
        header={"meta": "v2"},
    )
    assert upgraded.startswith(SEALED_SENDER_V2_MAGIC)
    upgraded_payload = unseal(recipient_private_bytes, upgraded)
    assert upgraded_payload["sender_id"] == 7
    assert unseal(recipient_private_bytes, upgraded)["header"]["meta"] == "v2"

    legacy = seal(
        sender_id=7,
        sender_ik_public=sender_public_bytes,
        recipient_ik_public=recipient_public_bytes,
        ciphertext=b"ciphertext",
        header={"meta": "legacy"},
    )
    assert not legacy.startswith(SEALED_SENDER_V2_MAGIC)
    legacy_payload = unseal(recipient_private_bytes, legacy)
    assert legacy_payload["sender_id"] == 7
    assert legacy_payload["header"]["meta"] == "legacy"
