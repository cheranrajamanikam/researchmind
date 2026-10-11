"""First-run setup and sign-in for the single local user."""
from __future__ import annotations

import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Project, User
from ..security import create_token, current_user, hash_password, verify_password
from .schemas import LoginIn, SetupIn

router = APIRouter(prefix="/auth", tags=["auth"])

_failures: dict[str, list[float]] = defaultdict(list)
MAX_FAILURES, WINDOW_S = 8, 300


def _check_rate(ip: str) -> None:
    now = time.time()
    _failures[ip] = [t for t in _failures[ip] if now - t < WINDOW_S]
    if len(_failures[ip]) >= MAX_FAILURES:
        raise HTTPException(429, "Too many failed attempts. Wait a few minutes and try again.")


@router.get("/status")
def status(db: Session = Depends(get_db)) -> dict:
    user = db.query(User).first()
    return {"setup_required": user is None, "user_name": user.name if user else None}


@router.post("/setup")
def setup(body: SetupIn, db: Session = Depends(get_db)) -> dict:
    if db.query(User).first():
        raise HTTPException(409, "This workspace is already set up. Sign in instead.")
    user = User(name=body.name.strip(), password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    db.add(Project(name="My first project", question=""))
    db.commit()
    return {"token": create_token(user.id), "user": {"id": user.id, "name": user.name}}


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> dict:
    ip = request.client.host if request.client else "local"
    _check_rate(ip)
    user = db.query(User).first()
    if not user:
        raise HTTPException(409, "Create your local workspace first.")
    if not verify_password(body.password, user.password_hash):
        _failures[ip].append(time.time())
        raise HTTPException(401, "That password is not correct.")
    _failures.pop(ip, None)
    return {"token": create_token(user.id), "user": {"id": user.id, "name": user.name}}


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return {"id": user.id, "name": user.name}
