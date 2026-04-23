import pytest
from cryptography.exceptions import InvalidTag

from client.crypto.keys import (
    generate_identity_keypair,
    generate_one_time_prekeys,
    generate_signed_prekey,
)
from client.crypto.ratchet import init_ratchet_sender, ratchet_decrypt, ratchet_encrypt
from client.crypto.x3dh import x3dh_sender
from client.services import messaging


def _b64e(data: bytes) -> str:
    return messaging.b64e(data)


def _storage_keys(user_id: int, identity: dict, signed_prekey: dict, otpks: list[dict]) -> dict:
    return {
        "user_id": user_id,
        "dh_private": _b64e(identity["dh_private"]),
        "dh_public": _b64e(identity["dh_public"]),
        "signed_prekey_private": _b64e(signed_prekey["private"]),
        "signed_prekey_public": _b64e(signed_prekey["public"]),
        "one_time_prekeys": [
            {"public": _b64e(kp["public"]), "private": _b64e(kp["private"])}
            for kp in otpks
        ],
    }


def _bootstrap_header(result: dict, sender_ik_public: bytes, recipient_otpk_public: bytes | None) -> dict:
    payload = {
        "ek_public": _b64e(result["ek_public"]),
        "ik_public": _b64e(sender_ik_public),
        "otpk_used": recipient_otpk_public is not None,
        "prekey_id": 1,
        "is_pqxdh": False,
    }
    if recipient_otpk_public is not None:
        payload["otpk_public"] = _b64e(recipient_otpk_public)
    return payload


def test_receiver_bootstrap_recovers_from_stale_local_session():
    alice_identity = generate_identity_keypair()
    alice_signed_prekey = generate_signed_prekey(alice_identity["signing_private"])
    alice_otpks = generate_one_time_prekeys(1)
    alice_keys = _storage_keys(1, alice_identity, alice_signed_prekey, alice_otpks)

    bob_identity = generate_identity_keypair()
    bob_signed_prekey = generate_signed_prekey(bob_identity["signing_private"])
    bob_otpks = generate_one_time_prekeys(1)

    alice_sender = x3dh_sender(
        ik_a_private=alice_identity["dh_private"],
        ik_b_public=bob_identity["dh_public"],
        spk_b_public=bob_signed_prekey["public"],
        opk_b_public=bob_otpks[0]["public"],
    )
    stale_state = init_ratchet_sender(
        shared_secret=alice_sender["shared_secret"],
        recipient_ratchet_public=bob_signed_prekey["public"],
    )
    stale_state.recipient_ik_public = bob_identity["dh_public"]

    bob_sender = x3dh_sender(
        ik_a_private=bob_identity["dh_private"],
        ik_b_public=alice_identity["dh_public"],
        spk_b_public=alice_signed_prekey["public"],
        opk_b_public=alice_otpks[0]["public"],
    )
    bob_state = init_ratchet_sender(
        shared_secret=bob_sender["shared_secret"],
        recipient_ratchet_public=alice_signed_prekey["public"],
    )
    bob_state.recipient_ik_public = alice_identity["dh_public"]

    associated_data = messaging._message_associated_data(
        bob_identity["dh_public"],
        alice_identity["dh_public"],
    )
    header, ciphertext = ratchet_encrypt(
        bob_state,
        b"fresh bootstrap wins",
        associated_data=associated_data,
        header_updates={
            "x3dh": _bootstrap_header(
                bob_sender,
                bob_identity["dh_public"],
                alice_otpks[0]["public"],
            )
        },
    )

    with pytest.raises(InvalidTag):
        ratchet_decrypt(
            stale_state,
            header,
            ciphertext,
            associated_data=associated_data,
        )

    recovered_state = messaging._bootstrap_receiver_state(
        alice_keys,
        bob_identity["dh_public"],
        header,
    )
    plaintext = ratchet_decrypt(
        recovered_state,
        header,
        ciphertext,
        associated_data=associated_data,
    )
    assert plaintext == b"fresh bootstrap wins"


def test_sync_inbox_continues_after_undecryptable_message(monkeypatch):
    entries = [{"id": 1}, {"id": 2}]
    calls = []

    monkeypatch.setattr(messaging, "fetch_inbox", lambda: entries)
    monkeypatch.setattr(messaging, "message_exists", lambda password, entry_id: False)

    def fake_receive(entry, storage_password):
        calls.append(entry["id"])
        if entry["id"] == 1:
            raise ValueError("sealed sender identity MAC verification failed")
        return {"message_id": entry["id"]}

    monkeypatch.setattr(messaging, "receive_one_from_entry", fake_receive)

    assert messaging.sync_inbox("iop") == [{"message_id": 2}]
    assert calls == [1, 2]
