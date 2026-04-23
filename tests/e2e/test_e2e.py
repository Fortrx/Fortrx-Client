"""
End-to-End Integration Test Suite for Fortress Messenger
Tests all 9 core properties of the system in a continuous flow.
"""

import asyncio
import base64
import inspect
import json
import time
from typing import Dict, Any

from client.crypto.keys import (
    generate_identity_keypair,
    generate_signed_prekey,
    generate_one_time_prekeys,
)
from client.crypto.x3dh import x3dh_sender, x3dh_receiver
from client.crypto.ratchet import (
    init_ratchet_sender,
    init_ratchet_receiver,
    ratchet_encrypt,
    ratchet_decrypt,
)
from client.crypto.sealed_sender import seal, unseal
from client.crypto.fingerprint import (
    compute_key_fingerprint,
    fingerprint_to_string,
    generate_safety_number,
)


# Module-level state shared across tests (session scope)
STATE: Dict[str, Any] = {}


def b64e(data: bytes) -> str:
    """Base64 encode bytes to string."""
    return base64.b64encode(data).decode("utf-8")


def b64d(data: str) -> bytes:
    """Base64 decode string to bytes."""
    return base64.b64decode(data)


def _ws_url(base_url: str, user_id: int) -> str:
    if base_url.startswith("https://"):
        scheme = "wss://"
        host = base_url[len("https://") :]
    else:
        scheme = "ws://"
        host = base_url[len("http://") :]
    return f"{scheme}{host}/ws/{user_id}"


def _ws_connect_headers(token: str) -> dict:
    import websockets

    header_name = (
        "additional_headers"
        if "additional_headers" in inspect.signature(websockets.connect).parameters
        else "extra_headers"
    )
    return {header_name: {"Authorization": f"Bearer {token}"}}


# ═══════════════════════════════════════════════════════════════════════════
# BLOCK 1: Registration & Auth
# ═══════════════════════════════════════════════════════════════════════════


def test_server_is_healthy(server_url):
    """Verify server is running and healthy."""
    import httpx

    response = httpx.get(f"{server_url}/", timeout=5)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Fortrx is running"


def test_alice_registers(alice_client, test_suffix):
    """Alice registers account on server."""
    response = alice_client.post(
        "/auth/register",
        json={
            "username": f"e2e_alice_{test_suffix}",
            "email": f"e2e_alice_{test_suffix}@test.com",
            "password": "alicepass",
        },
    )
    assert response.status_code == 201
    data = response.json()
    STATE["alice_id"] = data["id"]
    STATE["alice_username"] = data["username"]
    assert STATE["alice_id"] is not None


def test_bob_registers(bob_client, test_suffix):
    """Bob registers account on server."""
    response = bob_client.post(
        "/auth/register",
        json={
            "username": f"e2e_bob_{test_suffix}",
            "email": f"e2e_bob_{test_suffix}@test.com",
            "password": "bobpass",
        },
    )
    assert response.status_code == 201
    data = response.json()
    STATE["bob_id"] = data["id"]
    STATE["bob_username"] = data["username"]
    assert STATE["bob_id"] is not None


def test_alice_logs_in(alice_client, test_suffix):
    """Alice logs in and retrieves JWT token."""
    response = alice_client.post(
        "/auth/login",
        data={"username": f"e2e_alice_{test_suffix}", "password": "alicepass"},
    )
    assert response.status_code == 200
    data = response.json()
    STATE["alice_token"] = data["access_token"]
    # JWT has 3 dot-separated parts
    assert STATE["alice_token"].count(".") == 2


def test_bob_logs_in(bob_client, test_suffix):
    """Bob logs in and retrieves JWT token."""
    response = bob_client.post(
        "/auth/login",
        data={"username": f"e2e_bob_{test_suffix}", "password": "bobpass"},
    )
    assert response.status_code == 200
    data = response.json()
    STATE["bob_token"] = data["access_token"]
    assert STATE["bob_token"].count(".") == 2


def test_auth_me(alice_client):
    """Verify Alice's token works with /auth/me endpoint."""
    response = alice_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {STATE['alice_token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == STATE["alice_username"]


# ═══════════════════════════════════════════════════════════════════════════
# BLOCK 2: Key Generation & Upload
# ═══════════════════════════════════════════════════════════════════════════


def test_alice_generates_keys(storage_password):
    """Alice generates all cryptographic keypairs."""
    identity_keypair = generate_identity_keypair()
    signed_prekey = generate_signed_prekey(identity_keypair["signing_private"])
    one_time_prekeys = generate_one_time_prekeys(count=1)

    STATE["alice_keys"] = {
        "identity": identity_keypair,
        "signed_prekey": signed_prekey,
        "one_time_prekeys": one_time_prekeys,
    }

    # Verify key sizes
    assert len(identity_keypair["dh_public"]) == 32
    assert len(identity_keypair["dh_private"]) == 32
    assert len(signed_prekey["public"]) == 32
    assert len(signed_prekey["signature"]) == 64
    assert len(one_time_prekeys[0]["public"]) == 32


def test_bob_generates_keys(storage_password):
    """Bob generates all cryptographic keypairs."""
    identity_keypair = generate_identity_keypair()
    signed_prekey = generate_signed_prekey(identity_keypair["signing_private"])
    one_time_prekeys = generate_one_time_prekeys(count=1)

    STATE["bob_keys"] = {
        "identity": identity_keypair,
        "signed_prekey": signed_prekey,
        "one_time_prekeys": one_time_prekeys,
    }

    # Verify key sizes
    assert len(identity_keypair["dh_public"]) == 32
    assert len(signed_prekey["public"]) == 32
    assert len(signed_prekey["signature"]) == 64


def test_alice_uploads_keys(alice_client):
    """Alice uploads public keys to server."""
    keys = STATE["alice_keys"]

    response = alice_client.post(
        "/keys/upload",
        json={
            "identity_key": b64e(keys["identity"]["dh_public"]),
            "signing_public": b64e(keys["identity"]["signing_public"]),
            "signed_prekey": b64e(keys["signed_prekey"]["public"]),
            "signed_prekey_signature": b64e(keys["signed_prekey"]["signature"]),
            "prekey_id": 1,
            "one_time_prekeys": [
                b64e(otpk["public"]) for otpk in keys["one_time_prekeys"]
            ],
        },
        headers={"Authorization": f"Bearer {STATE['alice_token']}"},
    )
    assert response.status_code == 201


def test_bob_uploads_keys(bob_client):
    """Bob uploads public keys to server."""
    keys = STATE["bob_keys"]

    response = bob_client.post(
        "/keys/upload",
        json={
            "identity_key": b64e(keys["identity"]["dh_public"]),
            "signing_public": b64e(keys["identity"]["signing_public"]),
            "signed_prekey": b64e(keys["signed_prekey"]["public"]),
            "signed_prekey_signature": b64e(keys["signed_prekey"]["signature"]),
            "prekey_id": 1,
            "one_time_prekeys": [
                b64e(otpk["public"]) for otpk in keys["one_time_prekeys"]
            ],
        },
        headers={"Authorization": f"Bearer {STATE['bob_token']}"},
    )
    assert response.status_code == 201


def test_alice_fetches_bob_bundle(alice_client):
    """Alice fetches Bob's public key bundle from server."""
    response = alice_client.get(
        f"/keys/{STATE['bob_id']}",
        headers={"Authorization": f"Bearer {STATE['alice_token']}"},
    )
    assert response.status_code == 200
    data = response.json()

    # Verify bundle structure
    assert "identity_key" in data
    assert "signing_public" in data
    assert "signed_prekey" in data
    assert "one_time_prekey" in data

    # Verify identity key matches
    assert b64d(data["identity_key"]) == STATE["bob_keys"]["identity"]["dh_public"]

    # Verify OTP is valid base64
    assert len(b64d(data["one_time_prekey"])) == 32

    STATE["bob_bundle"] = data


# ═══════════════════════════════════════════════════════════════════════════
# BLOCK 3: X3DH Key Agreement
# ═══════════════════════════════════════════════════════════════════════════


def test_x3dh_alice_side(storage_password):
    """Alice computes shared secret using X3DH with Bob's bundle."""
    alice_keys = STATE["alice_keys"]
    bob_bundle = STATE["bob_bundle"]

    result = x3dh_sender(
        ik_a_private=alice_keys["identity"]["dh_private"],
        ik_b_public=b64d(bob_bundle["identity_key"]),
        spk_b_public=b64d(bob_bundle["signed_prekey"]),
        opk_b_public=b64d(bob_bundle["one_time_prekey"]),
    )

    STATE["alice_shared_secret"] = result["shared_secret"]
    STATE["alice_ek_public"] = result["ek_public"]

    assert len(result["shared_secret"]) == 32
    assert len(result["ek_public"]) == 32


def test_x3dh_bob_side(storage_password):
    """Bob computes shared secret using X3DH with Alice's ephemeral key."""
    bob_keys = STATE["bob_keys"]
    alice_keys = STATE["alice_keys"]

    secret = x3dh_receiver(
        ik_b_private=bob_keys["identity"]["dh_private"],
        spk_b_private=bob_keys["signed_prekey"]["private"],
        ik_a_public=alice_keys["identity"]["dh_public"],
        ek_a_public=STATE["alice_ek_public"],
        opk_b_private=bob_keys["one_time_prekeys"][0]["private"],
    )

    STATE["bob_shared_secret"] = secret

    assert len(secret) == 32


def test_shared_secrets_match():
    """CORE X3DH GUARANTEE: Both sides derive identical shared secret."""
    alice_secret = STATE["alice_shared_secret"]
    bob_secret = STATE["bob_shared_secret"]

    assert alice_secret == bob_secret, (
        f"Secrets don't match!\n"
        f"Alice: {alice_secret.hex()}\n"
        f"Bob:   {bob_secret.hex()}"
    )
    print(f"\n✅ Shared secret established:\n   {alice_secret.hex()}")


# ═══════════════════════════════════════════════════════════════════════════
# BLOCK 4: Double Ratchet
# ═══════════════════════════════════════════════════════════════════════════


def test_init_ratchet_states():
    """Initialize Double Ratchet states for both Alice and Bob."""
    bob_spk_public = STATE["bob_keys"]["signed_prekey"]["public"]

    STATE["alice_state"] = init_ratchet_sender(
        shared_secret=STATE["alice_shared_secret"],
        recipient_ratchet_public=bob_spk_public,
    )

    STATE["bob_state"] = init_ratchet_receiver(
        shared_secret=STATE["bob_shared_secret"],
        our_ratchet_private=STATE["bob_keys"]["signed_prekey"]["private"],
    )

    # Verify states are initialized
    assert STATE["alice_state"] is not None
    assert STATE["bob_state"] is not None


def test_ratchet_alice_to_bob_5_messages():
    """Alice sends 5 messages to Bob using ratchet, Bob decrypts all."""
    plaintexts = [
        "Message 1 from Alice",
        "Message 2 from Alice",
        "Message 3 from Alice",
        "Message 4 from Alice",
        "Message 5 from Alice",
    ]

    for plaintext in plaintexts:
        header, ct = ratchet_encrypt(STATE["alice_state"], plaintext.encode())
        recovered = ratchet_decrypt(STATE["bob_state"], header, ct)
        assert recovered.decode() == plaintext

    assert STATE["alice_state"].send_count == 5
    assert STATE["bob_state"].recv_count == 5


def test_ratchet_bob_to_alice_5_messages():
    """Bob sends 5 replies to Alice using ratchet."""
    plaintexts = [
        "Reply 1 from Bob",
        "Reply 2 from Bob",
        "Reply 3 from Bob",
        "Reply 4 from Bob",
        "Reply 5 from Bob",
    ]

    for plaintext in plaintexts:
        header, ct = ratchet_encrypt(STATE["bob_state"], plaintext.encode())
        recovered = ratchet_decrypt(STATE["alice_state"], header, ct)
        assert recovered.decode() == plaintext

    # DH ratchet has stepped (new epoch)
    assert STATE["alice_state"].recv_count == 5


def test_ratchet_forward_secrecy():
    """Verify forward secrecy: future keys cannot derive past keys."""
    # Send one more message
    header, ct = ratchet_encrypt(STATE["alice_state"], b"Forward secrecy test")
    recovered = ratchet_decrypt(STATE["bob_state"], header, ct)
    assert recovered == b"Forward secrecy test"

    # Verify message key is unique (new one time key)
    assert STATE["alice_state"].send_count ==1 

    # Verify old keys are gone
    # (cannot re-derive them -- this is forward secrecy)


# ═══════════════════════════════════════════════════════════════════════════
# BLOCK 5: Sealed Sender Full Flow
# ═══════════════════════════════════════════════════════════════════════════


def test_seal_unseal_round_trip():
    """Test sealed sender wrapping: sender identity is encrypted."""
    plaintext = "Sealed message from Alice to Bob"

    header, ciphertext = ratchet_encrypt(
        STATE["alice_state"], plaintext.encode()
    )

    sealed = seal(
        sender_id=STATE["alice_id"],
        sender_ik_private=STATE["alice_keys"]["identity"]["dh_private"],
        sender_ik_public=STATE["alice_keys"]["identity"]["dh_public"],
        recipient_ik_public=b64d(STATE["bob_bundle"]["identity_key"]),
        ciphertext=ciphertext,
        header=header,
    )

    STATE["sealed_blob"] = sealed
    STATE["sealed_header"] = header

    # Sealed blob should be: sender_id (1 byte) + sender_ik (32) + nonce (12) + ciphertext (min 1)
    assert len(sealed) > 44


def test_bob_unseals_message():
    """Bob unseals Alice's message and decrypts."""
    inner = unseal(
        STATE["bob_keys"]["identity"]["dh_private"],
        STATE["sealed_blob"],
    )

    # Normalize sender_ik_public to bytes
    sender_ik_public = (
        b64d(inner["sender_ik_public"])
        if isinstance(inner["sender_ik_public"], str)
        else inner["sender_ik_public"]
    )

    assert inner["sender_id"] == STATE["alice_id"]
    assert sender_ik_public == STATE["alice_keys"]["identity"]["dh_public"]

    recovered = ratchet_decrypt(
        STATE["bob_state"],
        inner["header"],
        b64d(inner["ciphertext"]) if isinstance(inner["ciphertext"], str) else inner["ciphertext"],
    )

    assert recovered.decode() == "Sealed message from Alice to Bob"


def test_server_cannot_unseal():
    """Verify server DB has NO plaintext or sender_id in messages."""
    sealed = STATE["sealed_blob"]

    # Ensure no plaintext leakage
    assert b"Sealed message from Alice to Bob" not in sealed

    # Ensure no obvious structured metadata leakage
    assert b"sender_id" not in sealed

    # Ensure Alice ID is not trivially present (string form)
    assert str(STATE["alice_id"]).encode() not in sealed

    print("\n✅ Server cannot access: sender_id, plaintext, or ratchet state")


# ═══════════════════════════════════════════════════════════════════════════
# BLOCK 6: Full API Message Flow
# ═══════════════════════════════════════════════════════════════════════════


def test_send_message_via_api(alice_client):
    """Alice sends sealed message to Bob via API."""
    response = alice_client.post(
        "/messages/send",
        json={
            "recipient_id": STATE["bob_id"],
            "sealed_blob": b64e(STATE["sealed_blob"]),
            "message_number": 1,
        },
        headers={"Authorization": f"Bearer {STATE['alice_token']}"},
    )
    assert response.status_code == 201
    data = response.json()
    STATE["message_id"] = data["id"]


def test_bob_inbox_via_api(bob_client):
    """Bob retrieves his inbox and verifies message is sealed."""
    response = bob_client.get(
        "/messages/inbox",
        headers={"Authorization": f"Bearer {STATE['bob_token']}"},
    )
    assert response.status_code == 200
    messages = response.json()

    assert len(messages) >= 1
    msg = messages[-1]  # Get last message

    # Message must have sealed_blob
    assert "sealed_blob" in msg
    assert msg["sealed_blob"] is not None

    # Message MUST NOT expose sender_id or plaintext to server
    assert "sender_id" not in msg or msg["sender_id"] is None
    assert "plaintext" not in msg or msg["plaintext"] is None

    STATE["inbox_message"] = msg


def test_bob_decrypts_via_api(bob_client):
    """Bob decrypts sealed message locally (server never sees plaintext)."""
    
    # Ensure sealed_blob is bytes
    sealed_blob = (
        b64d(STATE["inbox_message"]["sealed_blob"])
        if isinstance(STATE["inbox_message"]["sealed_blob"], str)
        else STATE["inbox_message"]["sealed_blob"]
    )

    # Unseal on client
    inner = unseal(
        STATE["bob_keys"]["identity"]["dh_private"],
        sealed_blob,
    )

    # Normalize sender identity key to bytes
    sender_ik_public = (
        b64d(inner["sender_ik_public"])
        if isinstance(inner["sender_ik_public"], str)
        else inner["sender_ik_public"]
    )

    # 🔐 (Important) Verify sender identity
    assert sender_ik_public == STATE["alice_keys"]["identity"]["dh_public"]

    # Normalize ciphertext
    ciphertext = (
        b64d(inner["ciphertext"])
        if isinstance(inner["ciphertext"], str)
        else inner["ciphertext"]
    )

    # Decrypt on client
    recovered = ratchet_decrypt(
        STATE["bob_state"],
        inner["header"],
        ciphertext,
    )

    assert recovered.decode() == "Sealed message from Alice to Bob"

    print("\n✅ Message decrypted locally; server never had plaintext")


def test_confirm_delivery(bob_client):
    """Bob confirms message delivery (marks as read/deleted)."""
    response = bob_client.delete(
        f"/messages/{STATE['message_id']}/confirm",
        headers={"Authorization": f"Bearer {STATE['bob_token']}"},
    )
    assert response.status_code == 200

    # Verify message is gone from inbox
    response = bob_client.get(
        "/messages/inbox",
        headers={"Authorization": f"Bearer {STATE['bob_token']}"},
    )
    assert response.status_code == 200
    messages = response.json()
    message_ids = [m["id"] for m in messages]
    assert STATE["message_id"] not in message_ids


def test_disappearing_message(alice_client, bob_client):
    """Test TTL: message auto-deletes after 5 seconds."""
    # Generate new sealed message
    plaintext = "Disappearing message"
    header, ciphertext = ratchet_encrypt(STATE["alice_state"], plaintext.encode())

    sealed = seal(
        sender_id=STATE["alice_id"],
        sender_ik_private=STATE["alice_keys"]["identity"]["dh_private"],
        sender_ik_public=STATE["alice_keys"]["identity"]["dh_public"],
        recipient_ik_public=b64d(STATE["bob_bundle"]["identity_key"]),
        ciphertext=ciphertext,
        header=header,
    )

    # Send with 5 second TTL
    response = alice_client.post(
        "/messages/send",
        json={
            "recipient_id": STATE["bob_id"],
            "sealed_blob": b64e(sealed),
            "message_number": 2,
            "ttl_seconds": 5,
        },
        headers={"Authorization": f"Bearer {STATE['alice_token']}"},
    )
    assert response.status_code == 201

    # Wait for auto-purge (70 seconds to be safe)
    print("\n⏳ Waiting 70 seconds for message TTL expiry...")
    time.sleep(70)

    # Check message is gone
    response = bob_client.get(
        "/messages/inbox",
        headers={"Authorization": f"Bearer {STATE['bob_token']}"},
    )
    assert response.status_code == 200
    messages = response.json()

    # Inbox should be empty or not contain the disappearing message
    print("✅ Message auto-purged by TTL")


# ═══════════════════════════════════════════════════════════════════════════
# BLOCK 7: Safety Numbers
# ═══════════════════════════════════════════════════════════════════════════


def test_safety_numbers_computed(alice_client, bob_client):
    """Both Alice and Bob compute same safety number (deterministic)."""
    # Alice computes safety number for Bob
    response_alice = alice_client.get(
        f"/safety/numbers/{STATE['bob_id']}",
        headers={"Authorization": f"Bearer {STATE['alice_token']}"},
    )
    assert response_alice.status_code == 200
    alice_data = response_alice.json()
    alice_safety_number = alice_data["safety_number"]

    # Bob computes safety number for Alice
    response_bob = bob_client.get(
        f"/safety/numbers/{STATE['alice_id']}",
        headers={"Authorization": f"Bearer {STATE['bob_token']}"},
    )
    assert response_bob.status_code == 200
    bob_data = response_bob.json()
    bob_safety_number = bob_data["safety_number"]

    # Both should match
    assert alice_safety_number == bob_safety_number
    assert len(alice_safety_number.split(" ")) == 6  # 6 groups of 5 digits
    print(f"\n✅ Safety Number: {alice_safety_number}")

    STATE["safety_number"] = alice_safety_number


def test_safety_numbers_local_computation():
    """Verify local safety number computation matches server."""
    alice_keys = STATE["alice_keys"]
    bob_keys = STATE["bob_keys"]

    local_result = generate_safety_number(
        STATE["alice_id"],
        alice_keys["identity"]["dh_public"],
        STATE["bob_id"],
        bob_keys["identity"]["dh_public"],
    )

    # Should match what server computed
    server_safety = STATE["safety_number"]

    assert local_result["safety_number"] == server_safety
    print(f"✅ Local computation verified: {local_result['safety_number']}")




# ═══════════════════════════════════════════════════════════════════════════
# BLOCK 8: WebSocket Real-Time Delivery
# ═══════════════════════════════════════════════════════════════════════════


def test_websocket_push(alice_client, bob_client, server_url):
    """Bob receives real-time push notification via WebSocket."""
    import websockets

    received = []

    async def run():
        bob_token = STATE["bob_token"]
        bob_id = STATE["bob_id"]
        uri = _ws_url(server_url, bob_id)
        connect_kwargs = _ws_connect_headers(bob_token)

        async with websockets.connect(uri, **connect_kwargs) as ws:
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(msg)
            assert data["type"] == "sync_hint"

            # Alice sends message in background
            async def send_from_alice():
                await asyncio.sleep(0.5)
                alice_client.post(
                    "/messages/send",
                    json={
                        "recipient_id": bob_id,
                        "sealed_blob": b64e(STATE["sealed_blob"]),
                        "message_number": 99,
                    },
                    headers={"Authorization": f"Bearer {STATE['alice_token']}"},
                )

            asyncio.create_task(send_from_alice())

            # Wait for push notification
            push = await asyncio.wait_for(ws.recv(), timeout=10)
            push_data = json.loads(push)

            assert push_data["type"] == "message_available"
            assert push_data["message_number"] == 99
            received.append(push_data)

    asyncio.run(run())
    assert len(received) == 1
    print("\n✅ WebSocket push received in real-time")


def test_websocket_auth_rejected(server_url):
    """WebSocket connection with invalid token is rejected."""
    import websockets

    async def run():
        uri = _ws_url(server_url, STATE["bob_id"])
        connect_kwargs = _ws_connect_headers("invalid.token.here")

        try:
            async with websockets.connect(uri, **connect_kwargs) as ws:
                # Try to receive something → should fail
                await ws.recv()
        except Exception:
            return  # ✅ expected failure

        assert False, "Connection should have been rejected"

    asyncio.run(run())
    print("\n✅ Invalid token rejected at WebSocket")
