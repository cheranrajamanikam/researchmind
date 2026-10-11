"""Single-user local authentication: bcrypt password + signed JWT."""
from __future__ import annotations

import secrets
import time
from pathlib import Path

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User

ALGO = "HS256"


def get_secret_key() -> str:
    s = get_settings()
    if s.secret_key:
        return s.secret_key
    path: Path = s.data_dir / ".secret"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(48))
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return path.read_text().strip()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except ValueError:
        return False


def create_token(user_id: int) -> str:
    now = int(time.time())
    payload = {"sub": str(user_id), "iat": now, "exp": now + get_settings().token_ttl_hours * 3600}
    return jwt.encode(payload, get_secret_key(), algorithm=ALGO)


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    # PDF/file endpoints opened in a new tab cannot send headers; allow ?token= for GET only.
    if request.method == "GET":
        return request.query_params.get("token")
    return None


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _extract_token(request)
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required", headers={"WWW-Authenticate": "Bearer"})
    if not token:
        raise unauthorized
    try:
        payload = jwt.decode(token, get_secret_key(), algorithms=[ALGO])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized from None
    user = db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise unauthorized
    return user
