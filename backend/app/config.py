"""App settings, read from backend/.env (see .env.example).  Owner: Pile 1 (Platform)."""

import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
DATA_DIR = BASE_DIR / "data"  # gitignored: SQLite DB + signing key live here
STATIC_DIR = BASE_DIR / "static"
ENV_FILE = BASE_DIR / ".env"
DEFAULT_BASE_URL = "http://localhost:8000"

_REAL_ENV_BASE_URL = os.environ.get("BASE_URL")  # captured BEFORE .env is loaded: a real env var
_REAL_ENV = dict(os.environ)                      # same idea for the other live settings
load_dotenv(ENV_FILE)


def _live_env(name: str, default: str = "") -> str:
    """Setting read LIVE: real environment variable > current backend/.env > default.

    Lets you paste e.g. SUPABASE_URL into .env while the server runs, without a restart.
    """
    if _REAL_ENV.get(name):
        return _REAL_ENV[name].strip()
    try:
        value = dotenv_values(ENV_FILE).get(name) if ENV_FILE.exists() else None
    except OSError:
        value = None
    return (value or default).strip()


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _path(name: str, default: Path) -> Path:
    p = Path(os.getenv(name, str(default)))
    return p if p.is_absolute() else BASE_DIR / p


class Settings:
    _base_url_override: str | None = None

    @property
    def BASE_URL(self) -> str:
        """Public URL used in QR codes and links. Read LIVE, not at startup.

        scripts/demo_tunnel.py rewrites .env with a new tunnel URL while the server runs, so the next
        QR the server makes points at it without a restart. Precedence: value assigned in code (tests)
        > real environment variable > current .env > default.
        """
        if self._base_url_override:
            return self._base_url_override.rstrip("/")
        if _REAL_ENV_BASE_URL:
            return _REAL_ENV_BASE_URL.rstrip("/")
        try:
            value = dotenv_values(ENV_FILE).get("BASE_URL") if ENV_FILE.exists() else None
        except OSError:
            value = None
        return (value or DEFAULT_BASE_URL).rstrip("/")

    @BASE_URL.setter
    def BASE_URL(self, value: str | None) -> None:
        self._base_url_override = value

    # Supabase Auth (register/login only; app data stays in SQLite). Public anon/publishable key only.
    @property
    def SUPABASE_URL(self) -> str:
        return _live_env("SUPABASE_URL").rstrip("/")

    @property
    def SUPABASE_ANON_KEY(self) -> str:
        return _live_env("SUPABASE_ANON_KEY")

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
        self.TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")
        self.OCR_MIN_CONF = float(os.getenv("OCR_MIN_CONF", "60"))
        self.MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "8"))
        self.ENABLE_EXTERNAL_AI = _bool("ENABLE_EXTERNAL_AI", False)
        self.BACKGROUND_TASKS = _bool("BACKGROUND_TASKS", True)


settings = Settings()
