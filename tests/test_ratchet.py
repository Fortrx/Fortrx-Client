import os
from client.crypto.ratchet import (
    RatchetState, derive_message_key, ratchet_encrypt, ratchet_decrypt
)
from client.services.messaging import b64d, b64e


def make_state_with_chain(chain_key: bytes, dh_pub: bytes = b"p"*32):
    # create a minimal RatchetState with specified chain keys
    return RatchetState(
        root_key=b"r"*32,
        sending_chain_key=chain_key,
        recv_chain_key=b"\x00"*32,
        dh_sending_private=b"s"*32,
        dh_sending_public=dh_pub,
        dh_remote_public=dh_pub,
        send_count=0,
        recv_count=0,
        skipped_message_keys={}
    )


def test_derive_message_key_consistency():
    ck = os.urandom(32)
    mk1, next1 = derive_message_key(ck)
    mk2, next2 = derive_message_key(ck)
    assert mk1 == mk2
    assert next1 == next2
    assert mk1 != next1


def test_encrypt_decrypt_pair():
    chain = os.urandom(32)
    sender = make_state_with_chain(chain)
    receiver = make_state_with_chain(chain)
    receiver.recv_chain_key = chain
    receiver.recv_chain_key = chain
    receiver.recv_chain_key = chain
    receiver.recv_chain_key = chain
    # receiver's recv_chain_key should start equal to sender's sending chain
    receiver.recv_chain_key = chain

    header, blob = ratchet_encrypt(sender, b"hello")
    # receiver should be able to decrypt
    pt = ratchet_decrypt(receiver, header, blob)
    assert pt == b"hello"


def test_multiple_messages_ordered():
    chain = os.urandom(32)
    sender = make_state_with_chain(chain)
    receiver = make_state_with_chain(chain)
    receiver.recv_chain_key = chain

    msgs = []
    for i in range(3):
        h,b = ratchet_encrypt(sender, f"msg{i}".encode())
        msgs.append((h,b))

    for h,b in msgs:
        pt = ratchet_decrypt(receiver,h,b)
        assert pt.decode().startswith("msg")