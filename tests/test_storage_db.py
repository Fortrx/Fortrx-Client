from client.config import settings
from client.storage.db import (
    list_conversation,
    load_keys,
    load_token,
    message_exists,
    save_incoming_message,
    save_keys,
)
from client.storage.token_store import save_token


def _configure_tmp_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path))
    monkeypatch.setattr(settings, "DB_FILE", str(tmp_path / "fortrx.db"))
    monkeypatch.setattr(settings, "TOKEN_FILE", str(tmp_path / "token"))
    monkeypatch.setattr(settings, "KEYS_FILE", str(tmp_path / "keys.enc"))
    monkeypatch.setattr(settings, "SESSION_FILE", str(tmp_path / "sessions.enc"))
    monkeypatch.setattr(settings, "VERIFIED_FILE", str(tmp_path / "verified.json"))
    monkeypatch.setattr(settings, "DAEMON_STATE_FILE", str(tmp_path / "daemon.json"))


def test_db_round_trip_for_token_and_keys(tmp_path, monkeypatch):
    _configure_tmp_storage(tmp_path, monkeypatch)
    password = "storage-pass"

    save_token("test-token", password=password)
    save_keys(
        password=password,
        keys={
            "user_id": 7,
            "dh_private": "priv",
            "dh_public": "pub",
            "signing_private": "sig-priv",
            "signing_public": "sig-pub",
            "signed_prekey_private": "spk-priv",
            "signed_prekey_public": "spk-pub",
            "signed_prekey_signature": "sig",
            "prekey_id": 1,
            "one_time_prekeys": [],
            "kyber_prekey_public": "kyber-pub",
            "kyber_prekey_private": "kyber-priv",
        },
    )

    assert load_token(password=password) == "test-token"
    assert load_keys(password=password, user_id=7)["dh_public"] == "pub"


def test_message_history_is_persisted_locally(tmp_path, monkeypatch):
    _configure_tmp_storage(tmp_path, monkeypatch)
    password = "storage-pass"

    save_incoming_message(
        password,
        {
            "server_message_id": 42,
            "contact_id": 99,
            "sender_id": 99,
            "recipient_id": 7,
            "message_number": 3,
            "plaintext": "hello from storage",
            "sealed_blob": "blob",
            "created_at": "2026-04-08T00:00:00+00:00",
            "status": "delivered",
        },
    )

    assert message_exists(password, 42) is True
    history = list_conversation(password, 99)
    assert len(history) == 1
    assert history[0]["plaintext"] == "hello from storage"
