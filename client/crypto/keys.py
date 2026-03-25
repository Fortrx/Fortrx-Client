import base64
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey,X25519PublicKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey,Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,PublicFormat,NoEncryption

def generate_identity_keypair():
    dh_private = X25519PrivateKey.generate()
    dh_public = dh_private.public_key()
    signing_private = Ed25519PrivateKey.generate()
    signing_public = signing_private.public_key()
    return {
        "dh_private" : dh_private.private_bytes(encoding=Encoding.Raw,format=PrivateFormat.Raw,encryption_algorithm=NoEncryption()),
        "dh_public" : dh_public.public_bytes(encoding=Encoding.Raw,format=PublicFormat.Raw),
        "signing_private" : signing_private.private_bytes(encoding=Encoding.Raw,format=PrivateFormat.Raw,encryption_algorithm=NoEncryption()),
        "signing_public" : signing_public.public_bytes(encoding=Encoding.Raw,format=PublicFormat.Raw)
    }
    
def generate_signed_prekey(signing_private_key_bytes:bytes):
    signing_private = Ed25519PrivateKey.from_private_bytes(signing_private_key_bytes)
    
    prekey_private = X25519PrivateKey.generate()
    prekey_public = prekey_private.public_key()
    
    public_bytes = prekey_public.public_bytes(encoding=Encoding.Raw,format=PublicFormat.Raw)
    
    signature = signing_private.sign(public_bytes)
    
    return {
        "private": prekey_private.private_bytes(encoding=Encoding.Raw,format=PrivateFormat.Raw,encryption_algorithm=NoEncryption()),
        "public": public_bytes,
        "signature":signature
    }

def generate_one_time_prekeys(count:int = 10):
    keys = []
    for _ in range(count):
        private = X25519PrivateKey.generate()
        public = private.public_key()
        
        keys.append({
            "private": private.private_bytes(
                encoding=Encoding.Raw,format=PrivateFormat.Raw,encryption_algorithm=NoEncryption()
            ),
            "public" : public.public_bytes(
                encoding=Encoding.Raw,format=PublicFormat.Raw
            )
        })
    return keys

def encode_public_key(raw_bytes:bytes):
    return base64.b64encode(raw_bytes).decode()
    
def decode_public_key(b64_str:str):
    return base64.b64decode(b64_str)
