"""User-editable settings persisted in the database, with typed defaults."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import AppSetting


def _defaults() -> dict[str, Any]:
    s = get_settings()
    return {
        "ollama_url": s.ollama_url,
        "answer_model": s.answer_model,
        "embed_model": s.embed_model,
        "online_discovery": False,
        "think_first_default": False,
        "tolerance": 5,
    }


def get_all(db: Session) -> dict[str, Any]:
    out = _defaults()
    for row in db.query(AppSetting).all():
        if row.key in out:
            default = out[row.key]
            if isinstance(default, bool):
                out[row.key] = row.value == "true"
            elif isinstance(default, int):
                try:
                    out[row.key] = int(row.value)
                except ValueError:
                    pass
            else:
                out[row.key] = row.value
    return out


def update(db: Session, values: dict[str, Any]) -> dict[str, Any]:
    allowed = _defaults().keys()
    for key, value in values.items():
        if key not in allowed or value is None:
            continue
        text = ("true" if value else "false") if isinstance(value, bool) else str(value)
        row = db.get(AppSetting, key)
        if row:
            row.value = text
        else:
            db.add(AppSetting(key=key, value=text))
    db.commit()
    return get_all(db)
