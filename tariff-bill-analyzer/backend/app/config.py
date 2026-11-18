import os, base64, hashlib

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
TOKEN_HOURS = int(os.getenv("TOKEN_HOURS", "12"))
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
# Fernet key derived from SECRET_KEY unless FERNET_KEY is supplied
FERNET_KEY = os.getenv("FERNET_KEY") or base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest())
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
