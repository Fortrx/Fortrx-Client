from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey,X25519PublicKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat,PrivateFormat,NoEncryption
from cryptography.hazmat.primitives import hashes
from client.crypto.pq_keys import kyber_decaps,kyber_encaps

def _load_x22519_private(raw:bytes):
    return X25519PrivateKey.from_private_bytes(raw)

def _load_x25519_public(raw: bytes):
    return X25519PublicKey.from_public_bytes(raw)

def _dh(private_bytes: bytes,public_bytes: bytes):
    priv = _load_x22519_private(private_bytes)
    pub = _load_x25519_public(public_bytes)
    return priv.exchange(pub)

def _hkdf_derive(input_key_material: bytes, length: int = 32):
    return HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=b"\x00"*32,
        info=b"Fortrx PQXDH"
    ).derive(input_key_material)

def _generate_ephemeral():
    priv = X25519PrivateKey.generate()
    pub = priv.public_key()
    private_bytes = priv.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption())
    public_bytes = pub.public_bytes(Encoding.Raw,PublicFormat.Raw)
    return private_bytes,public_bytes

def pqxdh_sender(
    ik_a_private: bytes,
    ik_b_public: bytes,
    spk_b_public: bytes,
    kyber_b_public: bytes,
    opk_b_public: bytes
):
    ek_private, ek_public = _generate_ephemeral()
    DH1 = _dh(ik_a_private,spk_b_public)
    DH2 = _dh(ek_private,ik_b_public)
    DH3 = _dh(ek_private,spk_b_public)
    DH4 = _dh(ek_private,opk_b_public) if opk_b_public else b""
    classical_input = DH1 + DH2 + DH3 + DH4
    
    kem = kyber_encaps(kyber_b_public)
    kyber_ciphertext = kem["ciphertext"]
    kyber_secret = kem["shared_secret"]

    hybrid_input = classical_input + kyber_secret
    shared_secret = _hkdf_derive(hybrid_input)

    return {
        "shared_secret": shared_secret,
        "ek_public": ek_public,
        "kyber_ciphertext": kyber_ciphertext
    }

def pqxdh_receiver(
    ik_b_private: bytes,
    spk_b_private: bytes,
    kyber_b_private: bytes,
    ik_a_public: bytes,
    ek_a_public: bytes,
    kyber_ciphertext: bytes,
    opk_b_private: bytes |None = None
):
    DH1 = _dh(spk_b_private,ik_a_public)
    DH2 = _dh(ik_b_private,ek_a_public)
    DH3 = _dh(spk_b_private,ek_a_public)
    DH4 = _dh(opk_b_private,ek_a_public) if opk_b_private else b""
    
    classical_input = DH1 + DH2 + DH3 + DH4
    
    kyber_secret = kyber_decaps(
        kyber_b_private,kyber_ciphertext
    )
    hybrid_input = classical_input + kyber_secret
    shared_secret = _hkdf_derive(hybrid_input)

    return shared_secret