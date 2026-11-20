import os, base64, hashlib
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
_DB = Path(__file__).resolve().parents[1] / "app.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_DB.as_posix()}")
TOKEN_HOURS = int(os.getenv("TOKEN_HOURS", "12"))
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
# Fernet key derived from SECRET_KEY unless FERNET_KEY is supplied
FERNET_KEY = os.getenv("FERNET_KEY") or base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest())
CORS_ORIGINS = [o.strip().rstrip("/") for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",") if o.strip()]
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
RESET_MINUTES = int(os.getenv("RESET_MINUTES", "30"))
SMTP_HOST = os.getenv("SMTP_HOST", "")          # leave empty = print link in terminal
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "") or SMTP_USER
