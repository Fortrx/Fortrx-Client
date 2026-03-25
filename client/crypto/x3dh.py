from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey

def _hkdf_derive(input_bytes:bytes):
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"\x00"*32,
        info=b"Fortrx X3DH"
    ).derive(input_bytes)
    
def x3dh_sender(
    ik_a_private: bytes,
    ik_b_public:bytes,
    spk_b_public:bytes,
    opk_b_public:bytes,
):
    ik_a = X25519PrivateKey.from_private_bytes(ik_a_private)
    ik_b = X25519PublicKey.from_public_bytes(ik_b_public)
    spk_b = X25519PublicKey.from_public_bytes(spk_b_public)
    
    ek_a = X25519PrivateKey.generate()
    ek_a_public_bytes = ek_a.public_key().public_bytes(
        encoding=Encoding.Raw,
        format=PublicFormat.Raw
    )
    
    dh1 = ik_a.exchange(spk_b)
    dh2 = ek_a.exchange(ik_b)
    dh3 = ek_a.exchange(spk_b)
    
    dh_parts = [dh1,dh2,dh3]
    
    if opk_b_public is not None:
        opk_b_ = X25519PublicKey.from_public_bytes(opk_b_public)
        dh4 = ek_a.exchange(opk_b_)
        dh_parts.append(dh4)
    
    dh_input = b"".join(dh_parts)
    
    shared_secret = _hkdf_derive(dh_input)
    
    return {
        "shared_secret":shared_secret,
        "ek_public": ek_a_public_bytes
    }

def x3dh_receiver(
    ik_b_private:bytes,
    spk_b_private:bytes,
    ik_a_public:bytes,
    ek_a_public:bytes,
    opk_b_private:bytes|None
):
    ik_b = X25519PrivateKey.from_private_bytes(ik_b_private)
    spk_b = X25519PrivateKey.from_private_bytes(spk_b_private)
    ik_a = X25519PublicKey.from_public_bytes(ik_a_public)
    ek_a = X25519PublicKey.from_public_bytes(ek_a_public)
    
    dh1 = spk_b.exchange(ik_a)
    dh2 = ik_b.exchange(ek_a)
    dh3 = spk_b.exchange(ek_a)
    
    dh_parts = [dh1,dh2,dh3]
    
    if opk_b_private is not None:
        opk_b = X25519PrivateKey.from_private_bytes(opk_b_private)
        dh4 = opk_b.exchange(ek_a)
        dh_parts.append(dh4)
        
    dh_input = b"".join(dh_parts)
    return _hkdf_derive(dh_input)