import base64
import json

from client.crypto.x3dh import x3dh_sender, x3dh_receiver
from client.crypto.pqxdh import pqxdh_sender, pqxdh_receiver
from client.crypto.pq_keys import verify_kyber_prekey
from client.crypto.keys import verify_signed_prekey

from client.crypto.ratchet import (
    init_ratchet_sender,
    ratchet_encrypt,
    init_ratchet_receiver,
    ratchet_decrypt
)

from client.crypto.sealed_sender import seal, unseal
from client.crypto.protocol_kdf import encode_identity_associated_data

from client.network.keys import fetch_key_bundle
from client.network.auth import get_me, get_user
from client.network.api import FortrxAPIError
from client.network.messages import send_message as api_send
from client.network.messages import fetch_inbox, confirm_delivery
from client.network.presence import fetch_presence_contacts

from client.storage.session_store import load_session, save_session
from client.storage.verification_store import is_verified
from client.storage.keystore import load_keys
from client.storage.db import (
    list_conversation_summaries,
    message_exists,
    save_incoming_message,
    save_outgoing_message,
    upsert_contact,
)


# ────────────────────────────────────────────────
# Utils
# ────────────────────────────────────────────────

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
    else:
        return obj


def _find_otpk_private_from_header(keys: dict, x3dh_data: dict):
    if not x3dh_data.get("otpk_used"):
        return None
    otpk_public_b64 = x3dh_data.get("otpk_public")
    if not otpk_public_b64:
        return None
    for kp in keys.get("one_time_prekeys", []):
        if kp.get("public") == otpk_public_b64:
            return b64d(kp["private"])
    return None


def _message_associated_data(sender_ik_public: bytes, recipient_ik_public: bytes) -> bytes:
    return encode_identity_associated_data(sender_ik_public, recipient_ik_public)


def _bootstrap_receiver_state(keys: dict, sender_ik: bytes, header: dict):
    x3dh_data = header.get("x3dh", {})
    if "ek_public" not in x3dh_data:
        raise ValueError("missing x3dh bootstrap data")

    my_ik_private = b64d(keys["dh_private"])
    my_spk_private = b64d(keys["signed_prekey_private"])
    otpk_private = _find_otpk_private_from_header(keys, x3dh_data)

    if x3dh_data.get("is_pqxdh") and x3dh_data.get("kyber_ciphertext"):
        shared_secret = pqxdh_receiver(
            ik_b_private=my_ik_private,
            spk_b_private=my_spk_private,
            kyber_b_private=b64d(keys["kyber_prekey_private"]),
            ik_a_public=sender_ik,
            ek_a_public=b64d(x3dh_data["ek_public"]),
            kyber_ciphertext=b64d(x3dh_data["kyber_ciphertext"]),
            opk_b_private=otpk_private
        )
    else:
        shared_secret = x3dh_receiver(
            ik_b_private=my_ik_private,
            spk_b_private=my_spk_private,
            ik_a_public=sender_ik,
            ek_a_public=b64d(x3dh_data["ek_public"]),
            opk_b_private=otpk_private
        )

    state = init_ratchet_receiver(
        shared_secret=shared_secret,
        our_ratchet_private=my_spk_private
    )
    state.recipient_ik_public = sender_ik
    return state


# ────────────────────────────────────────────────
# SEND (PQ6 decision logic)
# ────────────────────────────────────────────────

def send(recipient_id: int, plaintext: str, storage_password: str, ttl_seconds=None):
    keys = load_keys(password=storage_password)
    me = get_me()

    my_id = keys["user_id"]
    ik_private = b64d(keys["dh_private"])
    ik_public = b64d(keys["dh_public"])

    if recipient_id == my_id:
        upsert_contact(storage_password, my_id, me.get("username"))
        save_outgoing_message(
            storage_password,
            {
                "server_message_id": None,
                "contact_id": my_id,
                "sender_id": my_id,
                "recipient_id": my_id,
                "message_number": None,
                "plaintext": plaintext,
                "sealed_blob": None,
                "created_at": None,
                "expires_at": None,
                "status": "local",
                "delivered_at": None,
            },
        )
        return {
            "id": None,
            "recipient_id": my_id,
            "message_number": None,
            "created_at": None,
            "expires_at": None,
            "transport": "local",
        }

    state = load_session(recipient_id, password=storage_password)
    is_new_session = state is None
    bundle = None
    is_pqxdh = False

    if is_new_session:
        bundle = fetch_key_bundle(recipient_id)

        recipient_ik = b64d(bundle["identity_key"])
        recipient_signing_key = b64d(bundle["signing_public"])
        recipient_spk = b64d(bundle["signed_prekey"])
        recipient_spk_sig = b64d(bundle["signed_prekey_signature"])
        recipient_otpk = (
            b64d(bundle["one_time_prekey"])
            if bundle.get("one_time_prekey") else None
        )

        kyber_pub = bundle.get("kyber_prekey_public")
        kyber_sig = bundle.get("kyber_prekey_signature")
        if not verify_signed_prekey(
            signing_public_key_bytes=recipient_signing_key,
            signed_prekey_public_bytes=recipient_spk,
            signature=recipient_spk_sig
        ):
            raise ValueError("Signed prekey signature invalid")

        # ───── PQ DECISION ─────
        if kyber_pub and kyber_sig:
            valid = verify_kyber_prekey(
                ed25519_signing_public_bytes=recipient_signing_key,
                kyber_public_bytes=b64d(kyber_pub),
                signature=b64d(kyber_sig)
            )

            if not valid:
                raise ValueError("Kyber signature invalid — possible MITM")

            result = pqxdh_sender(
                ik_a_private=ik_private,
                ik_b_public=recipient_ik,
                spk_b_public=recipient_spk,
                kyber_b_public=b64d(kyber_pub),
                opk_b_public=recipient_otpk
            )
            is_pqxdh = True

        else:
            result = x3dh_sender(
                ik_a_private=ik_private,
                ik_b_public=recipient_ik,
                spk_b_public=recipient_spk,
                opk_b_public=recipient_otpk
            )
            print("Warning: falling back to X3DH")

        shared_secret = result["shared_secret"]
        ek_public = result["ek_public"]

        state = init_ratchet_sender(
            shared_secret=shared_secret,
            recipient_ratchet_public=recipient_spk
        )

        # metadata
        state.x3dh_ek_public = ek_public
        state.x3dh_ik_public = ik_public
        state.x3dh_otpk_used = recipient_otpk is not None
        state.x3dh_prekey_id = bundle["prekey_id"]
        state.x3dh_is_pqxdh = is_pqxdh
        state.recipient_ik_public = recipient_ik

        if is_pqxdh:
            state.x3dh_kyber_ct = result["kyber_ciphertext"]

    else:
        recipient_ik = state.recipient_ik_public

    if not is_verified(recipient_id, password=storage_password):
        print(f"Warning: unverified contact {recipient_id}")

    header_updates = None
    if is_new_session:
        header_updates = {"x3dh": {
            "ek_public": b64e(state.x3dh_ek_public),
            "ik_public": b64e(state.x3dh_ik_public),
            "otpk_used": state.x3dh_otpk_used,
            "prekey_id": state.x3dh_prekey_id,
            "is_pqxdh": state.x3dh_is_pqxdh
        }}

        if state.x3dh_otpk_used:
            header_updates["x3dh"]["otpk_public"] = b64e(recipient_otpk)

        if is_pqxdh:
            header_updates["x3dh"]["kyber_ciphertext"] = b64e(state.x3dh_kyber_ct)

    associated_data = _message_associated_data(ik_public, recipient_ik)
    header, ciphertext = ratchet_encrypt(
        state,
        plaintext.encode(),
        associated_data=associated_data,
        header_updates=header_updates,
    )
    header_encoded = encode_header(header)

    sealed = seal(
        sender_id=my_id,
        sender_ik_private=ik_private,
        sender_ik_public=ik_public,
        recipient_ik_public=recipient_ik,
        ciphertext=ciphertext,
        header=header_encoded
    )

    message_number = header.get("n", max(state.send_count - 1, 0))

    result = api_send(
        recipient_id=recipient_id,
        sealed_blob=b64e(sealed),
        message_number=message_number,
        ttl_seconds=ttl_seconds
    )

    save_session(recipient_id, state, password=storage_password)
    try:
        recipient = get_user(recipient_id)
        upsert_contact(storage_password, recipient_id, recipient.get("username"))
    except Exception:
        upsert_contact(storage_password, recipient_id)

    save_outgoing_message(
        storage_password,
        {
            "server_message_id": result["id"],
            "contact_id": recipient_id,
            "sender_id": my_id,
            "recipient_id": recipient_id,
            "message_number": message_number,
            "plaintext": plaintext,
            "sealed_blob": b64e(sealed),
            "created_at": result.get("created_at"),
            "expires_at": result.get("expires_at"),
            "status": "sent",
            "delivered_at": result.get("created_at"),
        },
    )
    return result


# ────────────────────────────────────────────────
# RECEIVE FROM STREAM ENTRY (NEW)
# ────────────────────────────────────────────────

def receive_one_from_entry(entry: dict, storage_password: str):
    if message_exists(storage_password, entry["id"]):
        return None

    keys = load_keys(password=storage_password)

    my_ik_private = b64d(keys["dh_private"])
    my_ik_public = b64d(keys["dh_public"])

    sealed_bytes = b64d(entry["sealed_blob"])
    inner = unseal(my_ik_private, sealed_bytes)

    sender_id = inner["sender_id"]
    sender_ik = b64d(inner["sender_ik_public"])
    ciphertext = b64d(inner["ciphertext"])
    header = inner["header"]

    state = load_session(sender_id, password=storage_password)

    if state is None:
        state = _bootstrap_receiver_state(keys, sender_ik, header)
    else:
        state.recipient_ik_public = sender_ik

    associated_data = _message_associated_data(sender_ik, my_ik_public)
    try:
        plaintext = ratchet_decrypt(
            state,
            header,
            ciphertext,
            associated_data=associated_data,
        ).decode()
    except Exception:
        if state is None or "ek_public" not in header.get("x3dh", {}):
            raise
        recovered_state = _bootstrap_receiver_state(keys, sender_ik, header)
        plaintext = ratchet_decrypt(
            recovered_state,
            header,
            ciphertext,
            associated_data=associated_data,
        ).decode()
        state = recovered_state

    save_session(sender_id, state, password=storage_password)
    try:
        sender = get_user(sender_id)
        upsert_contact(storage_password, sender_id, sender.get("username"))
    except Exception:
        upsert_contact(storage_password, sender_id)

    save_incoming_message(
        storage_password,
        {
            "server_message_id": entry["id"],
            "contact_id": sender_id,
            "sender_id": sender_id,
            "recipient_id": keys["user_id"],
            "message_number": entry["message_number"],
            "plaintext": plaintext,
            "sealed_blob": entry["sealed_blob"],
            "created_at": entry.get("created_at"),
            "expires_at": entry.get("expires_at"),
            "status": "delivered",
        },
    )
    try:
        confirm_delivery(entry["id"])
    except FortrxAPIError as exc:
        if exc.status_code != 404:
            raise

    return {
        "sender_id": sender_id,
        "plaintext": plaintext,
        "message_id": entry["id"],
        "message_number": entry["message_number"]
    }


def sync_inbox(storage_password: str):
    results = []
    for entry in fetch_inbox():
        if message_exists(storage_password, entry["id"]):
            try:
                confirm_delivery(entry["id"])
            except FortrxAPIError as exc:
                if exc.status_code != 404:
                    raise
            continue
        try:
            result = receive_one_from_entry(entry, storage_password=storage_password)
        except Exception as exc:
            print(
                f"Skipping undecryptable message {entry['id']}: "
                f"{type(exc).__name__}: {exc}"
            )
            continue
        if result:
            results.append(result)
    return results


def refresh_presence_cache(storage_password: str):
    contacts = fetch_presence_contacts()
    for contact in contacts:
        upsert_contact(
            storage_password,
            contact["user_id"],
            contact.get("username"),
            bool(contact.get("is_online")),
        )
    return contacts




def conversation_summaries(storage_password: str, limit: int = 100):
    return list_conversation_summaries(storage_password, limit)
