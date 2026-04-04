import base64
from client.crypto.x3dh import x3dh_sender
from client.crypto.ratchet import init_ratchet_sender, ratchet_encrypt
from client.crypto.sealed_sender import seal
from client.network.keys import fetch_key_bundle
from client.network.messages import send_message as api_send
from client.storage.session_store import load_session, save_session
from client.storage.keystore import load_keys
import json

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


def send(
    recipient_id: int,
    plaintext: str,
    storage_password: str,
    ttl_seconds: int | None = None
):
    keys = load_keys(password=storage_password)

    my_id = keys["user_id"]
    ik_private = b64d(keys["dh_private"])
    ik_public = b64d(keys["dh_public"])

    state = load_session(recipient_id, password=storage_password)
    is_new_session = state is None

    if is_new_session:
        bundle = fetch_key_bundle(recipient_id)

        recipient_ik = b64d(bundle["identity_key"])
        recipient_spk = b64d(bundle["signed_prekey"])
        recipient_otpk = (
            b64d(bundle["one_time_prekey"])
            if bundle["one_time_prekey"] else None
        )

        x3dh = x3dh_sender(
            ik_a_private=ik_private,
            ik_b_public=recipient_ik,
            spk_b_public=recipient_spk,
            opk_b_public=recipient_otpk
        )

        state = init_ratchet_sender(
            shared_secret=x3dh["shared_secret"],
            recipient_ratchet_public=recipient_spk
        )

        state.x3dh_ek_public = x3dh["ek_public"]
        state.x3dh_ik_public = ik_public
        state.x3dh_otpk_used = recipient_otpk is not None
        state.x3dh_prekey_id = bundle["prekey_id"]
        state.recipient_ik_public = recipient_ik

    else:
        recipient_ik = state.recipient_ik_public

    header, ciphertext = ratchet_encrypt(state, plaintext.encode())

    if is_new_session:
        header["x3dh"] = {
            "ek_public": b64e(state.x3dh_ek_public),
            "ik_public": b64e(state.x3dh_ik_public),
            "otpk_used": state.x3dh_otpk_used,
            "prekey_id": state.x3dh_prekey_id
        }

    header_encoded = encode_header(header)
    try:
        json.dumps(header_encoded)
    except Exception as e:
        print("❌ HEADER NOT SERIALIZABLE:")
        print(header_encoded)
        raise e
    sealed_bytes = seal(
        sender_id=my_id,
        sender_ik_public=ik_public,        
        recipient_ik_public=recipient_ik,  
        ciphertext=ciphertext,             
        header=header_encoded              
    )

    sealed_blob = b64e(sealed_bytes)

    result = api_send(
        recipient_id=recipient_id,
        sealed_blob=sealed_blob,
        message_number=state.send_count,
        ttl_seconds=ttl_seconds
    )

    save_session(recipient_id, state, password=storage_password)

    return result