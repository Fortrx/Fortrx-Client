from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey,Ed25519PublicKey
from client.crypto.protocol_kdf import encode_mlkem_public_key

try:
    from pqcrypto.kem.ml_kem_768 import decrypt, encrypt, generate_keypair
except ImportError:  # pragma: no cover - dependency availability is environment-specific
    decrypt = None
    encrypt = None
    generate_keypair = None


def _require_pqcrypto():
    if not all((generate_keypair, encrypt, decrypt)):
        raise RuntimeError(
            "pqcrypto with ml_kem_768 support is required for PQXDH operations"
        )

def generate_kyber_keypair():
    _require_pqcrypto()
    public_key,private_key = generate_keypair()

    assert len(public_key)> 1000, "unexpected public key size"
    assert len(private_key) > 2000, "unexpected private key size"
    
    return {
        "public": public_key,
        "private": private_key
    }

def kyber_encaps(kyber_public_bytes: bytes):
    _require_pqcrypto()
    ciphertext, shared_secret = encrypt(kyber_public_bytes)
    assert len(shared_secret) == 32
    
    return {
        "ciphertext": ciphertext,
        "shared_secret": shared_secret
    }

def kyber_decaps(
    kyber_private_bytes: bytes,
    ciphertext: bytes
):
    _require_pqcrypto()
    shared_secret = decrypt(kyber_private_bytes,ciphertext)
    assert len(shared_secret) == 32
    return shared_secret

def sign_kyber_prekey(
    ed25519_signing_private_bytes: bytes,
    kyber_public_bytes: bytes
):
    signing_key = Ed25519PrivateKey.from_private_bytes(ed25519_signing_private_bytes)
    signature = signing_key.sign(encode_mlkem_public_key(kyber_public_bytes))

    assert len(signature) == 64
    return signature

def verify_kyber_prekey(
    ed25519_signing_public_bytes: bytes,
    kyber_public_bytes: bytes,
    signature: bytes
):
    verify_key = Ed25519PublicKey.from_public_bytes(ed25519_signing_public_bytes)
    messages = (
        encode_mlkem_public_key(kyber_public_bytes),
        kyber_public_bytes,
    )
    for message in messages:
        try:
            verify_key.verify(signature, message)
            return True
        except Exception:
            continue
    return False
