import json,base64
from pathlib import Path
from client.config import settings
from client.storage.keystore import _encrypt,_decrypt,StorageError
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
        "send_count": state.send_count,
        "recv_count": state.recv_count
    }

def deserialize_state(data:dict):
    return RatchetState(
        root_key = _b64d(data["root_key"]),
        sending_chain_key=_b64d(data["sending_chain_key"]),
        recv_chain_key=_b64d(data["recv_chain_key"]),
        dh_sending_private=_b64d(data["dh_sending_private"]),
        dh_sending_public=_b64d(data["dh_sending_public"]),
        dh_remote_public=_b64d(data["dh_remote_public"]),
        send_count=data["send_count"],
        recv_count=data["recv_count"]
    )

def save_sessions(sessions:dict,password:str=None):
    password = password or settings.STORAGE_PASSWORD
    if not password:
        raise StorageError("No storage password set")
    path = Path(settings.SESSION_FILE)
    path.parent.mkdir(parents=True,exist_ok=True)
    data = json.dumps(sessions).encode()
    encyrpted = _encrypt(data,password)
    path.write_bytes(encyrpted)

def load_sessions(password:str = None):
    password = password or settings.STORAGE_PASSWORD
    path = Path(settings.SESSION_FILE)
    if not path.exists():
        return {}
    encrypted = path.read_bytes()
    data = _decrypt(encrypted,password)
    return json.loads(data)

def save_session(other_user_id:int,state:RatchetState,password:str=None):
    sessions = load_sessions(password)
    sessions[str(other_user_id)] = serialize_state(state)
    save_sessions(sessions,password)

def load_session(other_user_id:int,password:str=None):
    sessions = load_sessions(password)
    if str(other_user_id) not in sessions:
        return None
    return deserialize_state(sessions[str(other_user_id)])