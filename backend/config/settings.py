import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

_backend_dir = Path(__file__).resolve().parent.parent
load_dotenv(_backend_dir / ".env", override=True)


class Settings(BaseSettings):
    APP_NAME: str = "BotBeam"
    VERSION: str = "2.0.0"

    # Database (MySQL — same stack as kh / table-that)
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: str = os.getenv("DB_PORT", "3306")
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_NAME: str = os.getenv("DB_NAME", "botbeam")

    # Auth (JWT + bcrypt — the house pattern)
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "dev-insecure-secret-change-me")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7      # browser session: 7 days
    AGENT_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 365     # agent/skill token: 1 year

    PORT: int = int(os.getenv("PORT", "4888"))

    # Ledger (The Ledger Book; woodshed docs/ledger/). No windows, no timers:
    # statuses are stored (rev 18), expiry/sweep retired (rev 20), and the ⚡
    # is a declared open run, not a decaying clock (rev 21).
    # Test-only: enables POST /ledger/admin/reset (truncate the caller's ledger rows).
    LEDGER_ADMIN_RESET: bool = os.getenv("LEDGER_ADMIN_RESET", "false").lower() == "true"

    # Logging (mirrors the kh / table-that setup)
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "standard")  # "standard" | "json" (file handler)
    LOG_DIR: str = os.getenv("LOG_DIR", "logs")
    LOG_FILENAME_PREFIX: str = "botbeam"
    LOG_BACKUP_COUNT: int = 10
    LOG_PERFORMANCE_THRESHOLD_MS: int = 1000

    @property
    def DATABASE_URL(self) -> str:
        return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    class Config:
        env_file = ".env"
        case_sensitive = True
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
