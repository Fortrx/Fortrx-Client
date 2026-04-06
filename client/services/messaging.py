import base64
import asyncio
import json

from client.crypto.x3dh import x3dh_sender, x3dh_receiver
from client.crypto.pqxdh import pqxdh_sender, pqxdh_receiver   # ← NEW
from client.crypto.ratchet import (
    init_ratchet_sender,
    ratchet_encrypt,
    init_ratchet_receiver,
    ratchet_decrypt
)
from client.crypto.sealed_sender import seal, unseal

from client.network.keys import fetch_key_bundle
from client.network.messages import send_message as api_send
from client.network.messages import fetch_inbox, confirm_delivery

from client.storage.session_store import load_session, save_session
from client.storage.verification_store import is_verified
from client.storage.keystore import load_keys


def b64e(data: bytes) -> str:
    return base64.b64encode(data).decode()


def b64d(data: str) -> bytes:
    return base64.b64decode(data)


def encode_header(obj):
    if isinstance(obj, bytes):
        return b64e(obj)
    elif isinstance(obj, dict):
        return {k: encode_header(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [encode_header(i) for i in obj]
    elif isinstance(obj, tuple):
        return tuple(encode_header(i) for i in obj)
    else:
        return obj


# =========================
# SEND
# =========================

def send(recipient_id: int, plaintext: str, storage_password: str, ttl_seconds: int | None = None):
    keys = load_keys(password=storage_password)

    my_id = keys["user_id"]
    ik_private = b64d(keys["dh_private"])
    ik_public = b64d(keys["dh_public"])

    state = load_session(recipient_id, password=storage_password)
    is_new_session = state is None
    bundle = None

    if not is_new_session:
        try:
            bundle = fetch_key_bundle(recipient_id)
            recipient_ik = b64d(bundle["identity_key"])
            recipient_spk = b64d(bundle["signed_prekey"]) if bundle.get("signed_prekey") else None

            if recipient_ik != state.recipient_ik_public or recipient_spk != state.dh_remote_public:
                is_new_session = True
        except Exception:
            recipient_ik = state.recipient_ik_public

    if is_new_session:
        if bundle is None:
            bundle = fetch_key_bundle(recipient_id)

        recipient_ik = b64d(bundle["identity_key"])
        recipient_spk = b64d(bundle["signed_prekey"]) if bundle.get("signed_prekey") else None
        recipient_otpk = b64d(bundle["one_time_prekey"]) if bundle.get("one_time_prekey") else None

        # =========================
        # PQ DECISION
        # =========================
        if bundle.get("kyber_prekey_public"):
            # ---- PQXDH ----
            result = pqxdh_sender(
                ik_a_private=ik_private,
                ik_b_public=recipient_ik,
                spk_b_public=recipient_spk,
                kyber_b_public=b64d(bundle["kyber_prekey_public"]),
                opk_b_public=recipient_otpk
            )

            shared_secret = result["shared_secret"]
            ek_public = result["ek_public"]
            kyber_ciphertext = result["kyber_ciphertext"]

            state = init_ratchet_sender(
                shared_secret=shared_secret,
                recipient_ratchet_public=recipient_spk
            )

            state.is_pqxdh = True
            state.kyber_ciphertext = kyber_ciphertext

        else:
            # ---- CLASSIC ----
            x3dh = x3dh_sender(
                ik_a_private=ik_private,
                ik_b_public=recipient_ik,
                spk_b_public=recipient_spk,
                opk_b_public=recipient_otpk
            )

            shared_secret = x3dh["shared_secret"]
            ek_public = x3dh["ek_public"]

            state = init_ratchet_sender(
                shared_secret=shared_secret,
                recipient_ratchet_public=recipient_spk
            )

            state.is_pqxdh = False

        state.x3dh_ek_public = ek_public
        state.x3dh_ik_public = ik_public
        state.x3dh_otpk_used = recipient_otpk is not None
        state.x3dh_prekey_id = bundle.get("prekey_id")
        state.recipient_ik_public = recipient_ik

    else:
        recipient_ik = state.recipient_ik_public

    if not is_verified(recipient_id):
        print(f"⚠ Unverified contact {recipient_id}")

    header, ciphertext = ratchet_encrypt(state, plaintext.encode())

    if is_new_session:
        header["x3dh"] = {
            "ek_public": b64e(state.x3dh_ek_public),
            "ik_public": b64e(state.x3dh_ik_public),
            "otpk_used": state.x3dh_otpk_used,
            "prekey_id": state.x3dh_prekey_id,
            "otpk_public": b64e(recipient_otpk) if recipient_otpk else None
        }

        # ADD PQ FIELD
        if getattr(state, "is_pqxdh", False):
            header["x3dh"]["kyber_ciphertext"] = b64e(state.kyber_ciphertext)

    header_encoded = encode_header(header)
    json.dumps(header_encoded)

    sealed_bytes = seal(
        sender_id=my_id,
        sender_ik_public=ik_public,
        recipient_ik_public=recipient_ik,
        ciphertext=ciphertext,
        header=header_encoded
    )

    result = api_send(
        recipient_id=recipient_id,
        sealed_blob=b64e(sealed_bytes),
        message_number=state.send_count,
        ttl_seconds=ttl_seconds
    )

    save_session(recipient_id, state, password=storage_password)
    return result


# =========================
# RECEIVE
# =========================

def receive(storage_password: str):
    keys = load_keys(password=storage_password)

    my_ik_private = b64d(keys["dh_private"])
    my_spk_private = b64d(keys["signed_prekey_private"])
    my_kyber_private = b64d(keys.get("kyber_prekey_private", "")) if keys.get("kyber_prekey_private") else None

    otpk_lookup = {kp["public"]: b64d(kp["private"]) for kp in keys["one_time_prekeys"]}

    messages = fetch_inbox()
    if not messages:
        return []

    results = []

    for msg in messages:
        try:
            inner = unseal(my_ik_private, b64d(msg["sealed_blob"]))

            sender_id = inner["sender_id"]
            sender_ik_pub = b64d(inner["sender_ik_public"])
            ciphertext = b64d(inner["ciphertext"])
            header = inner["header"]

            x3dh_data = header.get("x3dh")
            is_new_session = x3dh_data is not None

            if is_new_session:
                ek_public = b64d(x3dh_data["ek_public"])
                otpk_used = x3dh_data["otpk_used"]
                otpk_public = x3dh_data.get("otpk_public")

                otpk_private = None
                if otpk_used and otpk_public:
                    otpk_private = otpk_lookup.get(otpk_public)

                # =========================
                # PQ DETECTION
                # =========================
                if x3dh_data.get("kyber_ciphertext") and my_kyber_private:
                    shared_secret = pqxdh_receiver(
                        ik_b_private=my_ik_private,
                        spk_b_private=my_spk_private,
                        kyber_b_private=my_kyber_private,
                        ik_a_public=sender_ik_pub,
                        ek_a_public=ek_public,
                        kyber_ciphertext=b64d(x3dh_data["kyber_ciphertext"]),
                        opk_b_private=otpk_private
                    )
                else:
                    shared_secret = x3dh_receiver(
                        ik_b_private=my_ik_private,
                        spk_b_private=my_spk_private,
                        ik_a_public=sender_ik_pub,
                        ek_a_public=ek_public,
                        opk_b_private=otpk_private
                    )

                state = init_ratchet_receiver(
                    shared_secret=shared_secret,
                    our_ratchet_private=my_spk_private
                )

                state.recipient_ik_public = sender_ik_pub

            else:
                state = load_session(sender_id, password=storage_password)
                if state is None:
                    continue

            plaintext = ratchet_decrypt(state, header, ciphertext).decode()

            save_session(sender_id, state, password=storage_password)
            confirm_delivery(msg["id"])

            results.append({
                "sender_id": sender_id,
                "plaintext": plaintext,
                "message_id": msg["id"],
                "message_number": msg["message_number"]
            })

        except Exception as e:
            results.append({
                "sender_id": "unknown",
                "plaintext": f"[decrypt error: {str(e)}]",
                "message_id": msg.get("id")
            })

    return results

async def receive_one(push_payload: dict, storage_password: str):
    keys = load_keys(password=storage_password)
    my_ik_private = b64d(keys["dh_private"])
    my_spk_private = b64d(keys["signed_prekey_private"])
    my_kyber_private = (
        b64d(keys["kyber_prekey_private"])
        if keys.get("kyber_prekey_private") else None
    )
    otpk_lookup = {
        kp["public"]: b64d(kp["private"])
        for kp in keys["one_time_prekeys"]
    }
    messages = fetch_inbox()
    msg = next(
        (m for m in messages if m.get("message_number") == push_payload.get("message_number")),
        None
    )
    if not msg:
        return None
    try:
        inner = unseal(my_ik_private, b64d(msg["sealed_blob"]))

        sender_id = inner["sender_id"]
        sender_ik_pub = b64d(inner["sender_ik_public"])
        ciphertext = b64d(inner["ciphertext"])
        header = inner["header"]

        x3dh_data = header.get("x3dh")
        is_new_session = x3dh_data is not None

        if is_new_session:
            ek_public = b64d(x3dh_data["ek_public"])
            otpk_used = x3dh_data["otpk_used"]
            otpk_public = x3dh_data.get("otpk_public")

            otpk_private = None
            if otpk_used and otpk_public:
                otpk_private = otpk_lookup.get(otpk_public)

            # PQ detection
            if x3dh_data.get("kyber_ciphertext") and my_kyber_private:
                shared_secret = pqxdh_receiver(
                    ik_b_private=my_ik_private,
                    spk_b_private=my_spk_private,
                    kyber_b_private=my_kyber_private,
                    ik_a_public=sender_ik_pub,
                    ek_a_public=ek_public,
                    kyber_ciphertext=b64d(x3dh_data["kyber_ciphertext"]),
                    opk_b_private=otpk_private
                )
            else:
                shared_secret = x3dh_receiver(
                    ik_b_private=my_ik_private,
                    spk_b_private=my_spk_private,
                    ik_a_public=sender_ik_pub,
                    ek_a_public=ek_public,
                    opk_b_private=otpk_private
                )

            state = init_ratchet_receiver(
                shared_secret=shared_secret,
                our_ratchet_private=my_spk_private
            )

            state.recipient_ik_public = sender_ik_pub

        else:
            state = load_session(sender_id, password=storage_password)
            if state is None:
                return {
                    "sender_id": "unknown",
                    "plaintext": "[session lost - cannot decrypt]",
                    "message_id": msg["id"]
                }

        plaintext = ratchet_decrypt(state, header, ciphertext).decode()

        save_session(sender_id, state, password=storage_password)
        confirm_delivery(msg["id"])

        return {
            "sender_id": sender_id,
            "plaintext": plaintext,
            "message_id": msg["id"],
            "message_number": msg["message_number"]
        }

    except Exception as e:
        return {
            "sender_id": "unknown",
            "plaintext": f"[decrypt error: {str(e)}]",
            "message_id": msg.get("id")
        }