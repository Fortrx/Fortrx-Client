from pqcrypto.kem.ml_kem_768 import generate_keypair,encrypt,decrypt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey,Ed25519PublicKey

def generate_kyber_keypair():
    public_key,private_key = generate_keypair()

    assert len(public_key)> 1000, "unexpected public key size"
    assert len(private_key) > 2000, "unexpected privare key size"
    
    return {
        "public": public_key,
        "private": private_key
    }

def kyber_encaps(kyber_public_bytes: bytes):
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
    shared_secret = decrypt(kyber_private_bytes,ciphertext)
    assert len(shared_secret) == 32
    return shared_secret

def sign_kyber_prekey(
    ed25519_signing_private_bytes: bytes,
    kyber_public_bytes: bytes
):
    signing_key = Ed25519PrivateKey.from_private_bytes(ed25519_signing_private_bytes)
    signature = signing_key.sign(kyber_public_bytes)

    assert len(signature) == 64
    return signature

def verify_kyber_prekey(
    ed25519_signing_public_bytes: bytes,
    kyber_public_bytes: bytes,
    signature: bytes
):
    try:
        verify_key = Ed25519PublicKey.from_public_bytes(ed25519_signing_public_bytes)
        verify_key.verify(signature,kyber_public_bytes)
        return True
    except Exception:
        return False