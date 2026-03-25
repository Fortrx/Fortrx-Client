import os,hashlib,hmac,base64
from dataclasses import dataclass
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey,X25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,PublicFormat,NoEncryption

@dataclass
class RatchetState:
    root_key: bytes
    sending_chain_key:bytes
    recv_chain_key:bytes
    dh_sending_private:bytes
    dh_sending_public:bytes
    dh_remote_public:bytes
    send_count: int = 0
    recv_count: int = 0
    
def _hkdf(salt:bytes,input_key:bytes):
    out = HKDF(
        algorithm=hashes.SHA256(),
        length=64,
        salt=salt,
        info=b"Fortrx Ratchet"
    ).derive(input_key)
    return out[:32],out[32:]

def _gen_dh_keypair():
    priv = X25519PrivateKey.generate()
    pub = priv.public_key()
    
    return (
        priv.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()),
        pub.public_bytes(Encoding.Raw,PublicFormat.Raw)
    )
    
def _dh(priv_bytes:bytes,pub_bytes:bytes):
    priv = X25519PrivateKey.from_private_bytes(priv_bytes)
    pub = X25519PublicKey.from_public_bytes(pub_bytes)
    return priv.exchange(pub)

def init_ratchet_sender(shared_secret:bytes,recipient_ratchet_public:bytes):
    priv,pub = _gen_dh_keypair()
    dh_out = _dh(priv,recipient_ratchet_public)
    root_key,sending_chain = _hkdf(shared_secret,dh_out)
    return RatchetState(
        root_key=root_key,
        sending_chain_key=sending_chain,
        recv_chain_key=b"\x00"*32,
        dh_sending_private=priv,
        dh_sending_public = pub,
        dh_remote_public = recipient_ratchet_public
    )

def init_ratchet_receiver(shared_secret:bytes,our_ratchet_private:bytes):
    priv = X25519PrivateKey.from_private_bytes(our_ratchet_private)
    pub = priv.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
    return RatchetState(
        root_key=shared_secret,
        sending_chain_key=b"\x00"*32,
        recv_chain_key=b"\x00"*32,
        dh_sending_private=our_ratchet_private,
        dh_sending_public=pub,
        dh_remote_public=None
    )

def derive_message_key(chain_key:bytes):
    msg_key = hmac.new(chain_key,b"\x01",hashlib.sha256).digest()
    next_chain = hmac.new(chain_key,b"x02",hashlib.sha256).digest()
    return msg_key,next_chain

def dh_ratchet_step(state:RatchetState,their_new_public:bytes):
    dh_out = _dh(state.dh_sending_private,their_new_public)
    new_root, new_recv_chain = _hkdf(state.root_key,dh_out)
    
    new_priv,new_pub = _gen_dh_keypair()
    
    dh_out2 = _dh(new_priv,their_new_public)
    new_root2,new_send_chain = _hkdf(new_root,dh_out2)
    
    state.root_key = new_root2
    state.recv_chain_key = new_recv_chain
    state.sending_chain_key = new_send_chain
    state.dh_sending_private = new_priv
    state.dh_sending_public = new_pub
    state.dh_remote_public = their_new_public
    state.recv_count = 0
    state.send_count = 0
    return state

def ratchet_encrypt(state:RatchetState,plaintext:bytes):
    msg_key,next_chain = derive_message_key(state.sending_chain_key)
    state.sending_chain_key = next_chain
    state.send_count += 1
    
    aes = AESGCM(msg_key)
    nonce = os.urandom(12)
    ciphertext = aes.encrypt(nonce,plaintext,None)
    
    header = {
        "dh_public": base64.b64encode(state.dh_sending_public).decode(),
        "send_sount":state.send_count,
        "recv_count":state.recv_count
    }
    return header, nonce + ciphertext

def ratchet_decrypt(state:RatchetState,header:dict,ciphertext:bytes):
    their_pub = base64.b64decode(header["dh_public"])
    
    if state.dh_remote_public != their_pub:
        dh_ratchet_step(state,their_pub)
        
    msg_key,next_chain = derive_message_key(state.recv_chain_key)
    state.recv_chain_key = next_chain
    state.recv_count += 1
    
    nonce = ciphertext[:12]
    data = ciphertext[12:]
    aes = AESGCM(msg_key)
    plaintext = aes.decrypt(nonce,data,None)
    return plaintext