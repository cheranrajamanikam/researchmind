"""Health, Ollama status, user settings, and whole-workspace export / deletion."""
from __future__ import annotations

import io
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from .. import __version__
from ..config import get_settings
from ..db import Base, get_db, get_engine
from ..models import User
from ..security import current_user
from ..services import settings_store
from ..services.llm import get_llm
from ..services.ollama import OllamaClient, OllamaError, OllamaUnavailable
from ..services.retrieval import VECTOR_CACHE
from .schemas import DeleteAllIn, OllamaTestIn, SettingsIn

public = APIRouter(tags=["system"])
router = APIRouter(tags=["system"], dependencies=[Depends(current_user)])


def ollama_status(db: Session, url: str | None = None) -> dict[str, Any]:
    cfg = settings_store.get_all(db)
    client = OllamaClient(url or cfg["ollama_url"], cfg["answer_model"], cfg["embed_model"])
    out: dict[str, Any] = {
        "url": client.base_url, "reachable": False, "version": None, "models": [],
        "answer_model": cfg["answer_model"], "embed_model": cfg["embed_model"],
        "answer_model_installed": False, "embed_model_installed": False, "error": None,
    }
    try:
        out["version"] = client.version()
        out["models"] = client.list_models()
        out["reachable"] = True
    except OllamaUnavailable as e:
        out["error"] = str(e)
        return out
    except OllamaError as e:
        out["error"] = str(e)
        return out

    def installed(name: str) -> bool:
        base = name.split(":")[0]
        return any(m == name or m.split(":")[0] == base and ":" not in name for m in out["models"])

    out["answer_model_installed"] = installed(cfg["answer_model"])
    out["embed_model_installed"] = installed(cfg["embed_model"])
    return out


@public.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "version": __version__,
        "database": "ok" if db_ok else "error",
        "setup_required": db.query(User).first() is None if db_ok else None,
    }


@router.get("/system/ollama")
def get_ollama(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ollama_status(db)


@router.post("/system/ollama/test")
def test_ollama(body: OllamaTestIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    url = body.url.strip().rstrip("/") if body.url else None
    if url and not url.startswith(("http://", "https://")):
        raise HTTPException(422, "Ollama URL must start with http:// or https://")
    return ollama_status(db, url)


@router.get("/settings")
def get_settings_api(db: Session = Depends(get_db)) -> dict[str, Any]:
    return settings_store.get_all(db)


@router.put("/settings")
def put_settings(body: SettingsIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    out = settings_store.update(db, body.model_dump(exclude_none=True))
    VECTOR_CACHE.bump()
    return out


@router.post("/data/export")
def export_all(db: Session = Depends(get_db)) -> StreamingResponse:
    """Zip with a JSON dump of every table (embeddings omitted) plus the original PDFs."""
    cfg = get_settings()
    buf = io.BytesIO()
    insp = inspect(get_engine())
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for table in Base.metadata.sorted_tables:
            if table.name in ("users",) or not insp.has_table(table.name):
                continue
            rows = []
            for r in db.execute(table.select()).mappings():
                row = {}
                for k, v in r.items():
                    if isinstance(v, bytes):
                        continue
                    row[k] = v.isoformat() if isinstance(v, datetime) else v
                rows.append(row)
            z.writestr(f"data/{table.name}.json", json.dumps(rows, ensure_ascii=False, indent=2))
        for pdf in sorted(Path(cfg.papers_dir).glob("*.pdf")):
            z.write(pdf, f"papers/{pdf.name}")
        z.writestr("README.txt", "ResearchMind export. data/*.json are table dumps; papers/ holds the original PDFs.\n")
    buf.seek(0)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(
        buf, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="researchmind-export-{stamp}.zip"'}
    )


@router.delete("/data")
def delete_everything(body: DeleteAllIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Irreversibly remove all rows (including the user) and all stored PDFs. Requires typing DELETE."""
    if body.confirm != "DELETE":
        raise HTTPException(422, "Type DELETE to confirm.")
    cfg = get_settings()
    db.execute(text("PRAGMA foreign_keys=OFF"))
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()
    db.execute(text("PRAGMA foreign_keys=ON"))
    try:
        db.execute(text("INSERT INTO chunk_fts(chunk_fts) VALUES ('rebuild')"))
        db.commit()
    except Exception:  # noqa: BLE001 - FTS table absent on non-SQLite
        db.rollback()
    removed = 0
    for pdf in Path(cfg.papers_dir).glob("*"):
        if pdf.is_file():
            pdf.unlink(missing_ok=True)
            removed += 1
        elif pdf.is_dir():
            shutil.rmtree(pdf, ignore_errors=True)
    VECTOR_CACHE.bump()
    return {"deleted": True, "files_removed": removed}


__all__ = ["get_llm", "public", "router"]
