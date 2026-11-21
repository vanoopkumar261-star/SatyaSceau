"""App settings, read from backend/.env (see .env.example).  Owner: Pile 1 (Platform)."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
DATA_DIR = BASE_DIR / "data"  # gitignored: SQLite DB + signing key live here
STATIC_DIR = BASE_DIR / "static"

load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _path(name: str, default: Path) -> Path:
    p = Path(os.getenv(name, str(default)))
    return p if p.is_absolute() else BASE_DIR / p


class Settings:
    def __init__(self) -> None:
        self.APP_VERSION = "0.1.0"
        self.STATIC_DIR = STATIC_DIR  # also reachable as settings.* (WORK_SPLIT lists them with settings)
        self.DATA_DIR = DATA_DIR
        self.DATABASE_URL = os.getenv(
            "DATABASE_URL", f"sqlite:///{(DATA_DIR / 'satyasceau.db').as_posix()}"
        )
        self.SIGNING_KEY_PATH = _path("SIGNING_KEY_PATH", DATA_DIR / "signing_key.pem")
        self.MATCH_WINDOW_MIN = int(os.getenv("MATCH_WINDOW_MIN", "5"))
        self.RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "7"))
        self.BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
        self.TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")
        self.OCR_MIN_CONF = float(os.getenv("OCR_MIN_CONF", "60"))
        self.MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "8"))
        self.ENABLE_EXTERNAL_AI = _bool("ENABLE_EXTERNAL_AI", False)
        self.BACKGROUND_TASKS = _bool("BACKGROUND_TASKS", True)


settings = Settings()
