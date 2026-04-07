from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SERVER_URL: str = "http://localhost:8000"
    LOCAL_STORAGE_PATH: str = ".fortrx"
    STORAGE_PASSWORD: str = ""
    REQUEST_TIMEOUT_SECONDS: float = 10.0
    ALLOW_INSECURE_STORAGE: bool = False

    @field_validator("SERVER_URL")
    @classmethod
    def _normalize_server_url(cls, value: str) -> str:
        value = value.strip()
        return value.rstrip("/")

    @field_validator("LOCAL_STORAGE_PATH")
    @classmethod
    def _normalize_storage_path(cls, value: str) -> str:
        value = value.strip()
        return value or ".fortrx"

    @property
    def TOKEN_FILE(self) -> str:
        return str(Path(self.LOCAL_STORAGE_PATH) / "token")

    @property
    def KEYS_FILE(self) -> str:
        return str(Path(self.LOCAL_STORAGE_PATH) / "keys.enc")

    @property
    def SESSION_FILE(self) -> str:
        return str(Path(self.LOCAL_STORAGE_PATH) / "sessions.enc")

    @property
    def DB_FILE(self) -> str:
        return str(Path(self.LOCAL_STORAGE_PATH) / "fortrx.db")

    @property
    def VERIFIED_FILE(self) -> str:
        return str(Path(self.LOCAL_STORAGE_PATH) / "verified.json")

    @property
    def DAEMON_STATE_FILE(self) -> str:
        return str(Path(self.LOCAL_STORAGE_PATH) / "daemon.json")


settings = Settings()
