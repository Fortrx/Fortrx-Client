import base64
from client.config import settings
from client.storage.crypto import StorageError
from client.storage.db import load_session_blob, load_sessions_map, save_session_blob
from client.crypto.ratchet import RatchetState

def _b64e(b:bytes|None):
    return base64.b64encode(b).decode() if b else None

def _b64d(s:str|None):
    return base64.b64decode(s) if s else None

def serialize_state(state:RatchetState):
    return {
        "root_key": _b64e(state.root_key),
        "sending_chain_key":_b64e(state.sending_chain_key),
        "recv_chain_key": _b64e(state.recv_chain_key),
        "dh_sending_private":_b64e(state.dh_sending_private),
        "dh_sending_public":_b64e(state.dh_sending_public),
        "dh_remote_public":_b64e(state.dh_remote_public),
        "recipient_ik_public":_b64e(getattr(state,"recipient_ik_public",None)),
        "send_count": state.send_count,
        "recv_count": state.recv_count,
    }

def deserialize_state(data:dict):
    state = RatchetState(
        root_key = _b64d(data["root_key"]),
        sending_chain_key=_b64d(data["sending_chain_key"]),
        recv_chain_key=_b64d(data["recv_chain_key"]),
        dh_sending_private=_b64d(data["dh_sending_private"]),
        dh_sending_public=_b64d(data["dh_sending_public"]),
        dh_remote_public=_b64d(data["dh_remote_public"]),
        send_count=data["send_count"],
        recv_count=data["recv_count"],
    )
    state.recipient_ik_public = _b64d(data.get("recipient_ik_public"))
    return state

def save_sessions(sessions:dict,password:str=None):
    password = password or settings.STORAGE_PASSWORD
    if not password:
        raise StorageError("No storage password set")
    for contact_id, state in sessions.items():
        save_session_blob(password, int(contact_id), state)

def load_sessions(password:str = None):
    password = password or settings.STORAGE_PASSWORD
    return load_sessions_map(password)

def save_session(other_user_id:int,state:RatchetState,password:str=None):
    password = password or settings.STORAGE_PASSWORD
    save_session_blob(password, other_user_id, serialize_state(state))

def load_session(other_user_id:int,password:str=None):
    password = password or settings.STORAGE_PASSWORD
    data = load_session_blob(password, other_user_id)
    if data is None:
        return None
    return deserialize_state(data)
