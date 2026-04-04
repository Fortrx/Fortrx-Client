import base64
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,PublicFormat,NoEncryption

from client.storage import session_store
from client.crypto import sealed_sender


def test_session_serialize_deserialize_roundtrip():
    # create a dummy RatchetState
    from client.crypto.ratchet import RatchetState

    state = RatchetState(
        root_key=b"rkey1234567890123456789012345",
        sending_chain_key=b"skey123456789012345678901234",
        recv_chain_key=b"rckey12345678901234567890123",
        dh_sending_private=b"privbytes012345678901234567890",
        dh_sending_public=b"pubbytes012345678901234567890",
        dh_remote_public=b"remotepubbytes012345678901234",
        send_count=5,
        recv_count=2
    )
    state.recipient_ik_public = b"recipient_public_bytes"

    ser = session_store.serialize_state(state)
    deser = session_store.deserialize_state(ser)

    assert deser.root_key == state.root_key
    assert deser.dh_sending_public == state.dh_sending_public
    assert deser.recipient_ik_public == state.recipient_ik_public


def test_seal_unseal_roundtrip():
    # generate recipient keypair
    recipient_priv = X25519PrivateKey.generate()
    recipient_priv_bytes = recipient_priv.private_bytes(encoding=Encoding.Raw, format=PrivateFormat.Raw, encryption_algorithm=NoEncryption())
    recipient_pub_bytes = recipient_priv.public_key().public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)

    # generate sender ik public
    sender_priv = X25519PrivateKey.generate()
    sender_pub_bytes = sender_priv.public_key().public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)

    header = {"meta": b"data"}
    ciphertext = b"top secret payload"

    sealed = sealed_sender.seal(
        sender_id=99,
        sender_ik_public=sender_pub_bytes,
        recipient_ik_public=recipient_pub_bytes,
        ciphertext=ciphertext,
        header=header
    )

    out = sealed_sender.unseal(recipient_priv_bytes, sealed)

    # ciphertext and sender_ik_public are base64-encoded in the inner JSON
    decoded_cipher = base64.b64decode(out["ciphertext"])
    decoded_sender_pub = base64.b64decode(out["sender_ik_public"])

    assert decoded_cipher == ciphertext
    assert decoded_sender_pub == sender_pub_bytes
