from pydantic_settings import BaseSettings
class Settings(BaseSettings):
    SERVER_URL: str = "http://localhost:8000"
    LOCAL_STORAGE_PATH: str = ".fortrx"
    TOKEN_FILE: str = ".fortrx/token"
    KEYS_FILE: str = ".fortrx/keys.enc"
    SESSION_FILE: str = '.fortrx/sessions.enc'
    DB_FILE: str = ".fortrx/fortrx.db"
    VERIFIED_FILE: str = ".fortrx/verified.json"
    DAEMON_STATE_FILE: str = ".fortrx/daemon.json"
    STORAGE_PASSWORD: str = ""
    
settings = Settings()
