"""Password hashing, JWT session tokens and at-rest encryption of third-party tokens."""
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

JWT_ALGORITHM = "HS256"
SESSION_COOKIE = "hub_session"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


class EncryptionNotConfigured(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = get_settings().encryption_key
    if not key:
        raise EncryptionNotConfigured("ENCRYPTION_KEY is not set in backend/.env")
    return Fernet(key.encode("utf-8"))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise EncryptionNotConfigured("Stored secret cannot be decrypted with ENCRYPTION_KEY") from exc
