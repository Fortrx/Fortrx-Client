import os,json,base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey,X25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat

def _json_safe(obj):
    if isinstance(obj, (bytes, bytearray)):
        return base64.b64encode(bytes(obj)).decode()
    elif isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [_json_safe(i) for i in obj]
    elif hasattr(obj, "public_bytes"):
        return base64.b64encode(
            obj.public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
        ).decode()
    else:
        return obj

def seal(
    sender_id:int,
    sender_ik_public:bytes,
    recipient_ik_public:bytes,
    ciphertext:bytes,
    header:dict
):
    ek_private = X25519PrivateKey.generate()
    ek_public = ek_private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    
    recipient_pub = X25519PublicKey.from_public_bytes(recipient_ik_public)
    dh_out = ek_private.exchange(recipient_pub)
    
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"\x00"*32,
        info = b"Fortrx Sealed Sender",
    ).derive(dh_out)
    inner = json.dumps({
        "sender_id":sender_id,
        "sender_ik_public":base64.b64encode(sender_ik_public).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(),
        "header": _json_safe(header)
    }).encode()
    nonce = os.urandom(12)
    encrypted = AESGCM(key).encrypt(nonce,inner,None)
    return ek_public + nonce + encrypted

def unseal(
    recipient_ik_private:bytes,
    sealed_blob:bytes
):
    ek_public = sealed_blob[:32]
    nonce = sealed_blob[32:44]
    encrypted = sealed_blob[44:]
    
    recipient_priv = X25519PrivateKey.from_private_bytes(recipient_ik_private)
    ek_pub = X25519PublicKey.from_public_bytes(ek_public)
    dh_out = recipient_priv.exchange(ek_pub)
    
    key = HKDF(
        algorithm=hashes.SHA256(),
        length = 32,
        salt=b"\x00"*32,
        info = b"Fortrx Sealed Sender",
    ).derive(dh_out)
    inner = AESGCM(key).decrypt(nonce,encrypted,None)
    return json.loads(inner)