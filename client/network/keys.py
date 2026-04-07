from client.network.api import get,post,raise_for_status

def upload_key_bundle(
    identity_key:str,
    signing_public: str,
    signed_prekey: str,
    signed_prekey_signature: str,
    prekey_id:int,
    one_time_prekeys: list[str],
    kyber_prekey_public: str | None = None,
    kyber_prekey_signature: str | None = None
):
    body = {
            "identity_key": identity_key,
            "signing_public": signing_public,
            "signed_prekey": signed_prekey,
            "signed_prekey_signature": signed_prekey_signature,
            "prekey_id": prekey_id,
            "one_time_prekeys": one_time_prekeys
        }
    if kyber_prekey_public:
        body["kyber_prekey_public"] = kyber_prekey_public
    if kyber_prekey_signature:
        body["kyber_prekey_signature"] = kyber_prekey_signature
    response = post("/keys/upload", json=body)
    raise_for_status(response,context="upload_key_bundle")
    return response.json()

def fetch_key_bundle(user_id:int):
    response = get(f"/keys/{user_id}")
    raise_for_status(response,context="fetch_key_bundle")
    return response.json()
