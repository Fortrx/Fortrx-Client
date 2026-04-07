from client.config import settings
from client.storage.db import (
    is_verified as db_is_verified,
    load_verifications as db_load_verifications,
    save_verification as db_save_verification,
)

FILE = settings.VERIFIED_FILE


def load_verifications(password: str | None = None):
    password = password or settings.STORAGE_PASSWORD
    return db_load_verifications(password)


def save_verification(user_id: int, safety_number: str, password: str | None = None):
    password = password or settings.STORAGE_PASSWORD
    db_save_verification(password, user_id, safety_number)


def is_verified(user_id: int, password: str | None = None) -> bool:
    password = password or settings.STORAGE_PASSWORD
    return db_is_verified(password, user_id)
