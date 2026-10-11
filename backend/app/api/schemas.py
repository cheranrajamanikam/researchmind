"""Request bodies (validated by Pydantic). Responses are built by app.api.serializers."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SetupIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    question: str = Field(default="", max_length=2000)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    question: str | None = Field(default=None, max_length=2000)
    think_first: bool | None = None


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    mode: Literal["keyword", "semantic"] = "semantic"
    project_id: int | None = None
    k: int = Field(default=12, ge=1, le=50)


class ThreadIn(BaseModel):
    project_id: int
    title: str = Field(default="New thread", max_length=300)


class ThreadPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    starred: bool | None = None


class AskIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    reading_mode: bool = False


class CopilotIn(BaseModel):
    project_id: int
    question: str = Field(min_length=1, max_length=4000)
    reading_mode: bool = False


class SettingsIn(BaseModel):
    ollama_url: str | None = Field(default=None, max_length=300)
    answer_model: str | None = Field(default=None, max_length=120)
    embed_model: str | None = Field(default=None, max_length=120)
    online_discovery: bool | None = None
    think_first_default: bool | None = None
    tolerance: int | None = Field(default=None, ge=0, le=20)

    @field_validator("ollama_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().rstrip("/")
        if not v.startswith(("http://", "https://")):
            raise ValueError("Ollama URL must start with http:// or https://")
        return v


class OllamaTestIn(BaseModel):
    url: str | None = None


class DeleteAllIn(BaseModel):
    confirm: str


# ----------------------------------------------------------------- analysis / think-first


class FieldAction(BaseModel):
    action: Literal["confirm", "edit", "reject", "reset"]
    value: str | None = Field(default=None, max_length=2000)


class DiffIn(BaseModel):
    paper_ids: list[int] = Field(min_length=2, max_length=6)


class DiscoverIn(BaseModel):
    text: str = Field(min_length=3, max_length=4000)
    queries: list[str] | None = Field(default=None, max_length=5)

    @field_validator("queries")
    @classmethod
    def _short(cls, v: list[str] | None) -> list[str] | None:
        return [q.strip()[:200] for q in v if q and q.strip()] if v else None


class PriorWorkIn(BaseModel):
    idea: str = Field(min_length=5, max_length=4000)


class OverclaimIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


class DraftAuditIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    mapping: dict[str, int] = Field(default_factory=dict)  # reference number -> paper id


class ReadingIn(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    authors: str = Field(default="", max_length=500)
    year: int | None = Field(default=None, ge=1500, le=2200)
    venue: str = Field(default="", max_length=200)
    url: str = Field(default="", max_length=600)
    why: str = Field(default="", max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=8)
    paper_id: int | None = None


class ReadingPatch(BaseModel):
    status: Literal["to_read", "reading", "read"] | None = None
    note: str | None = Field(default=None, max_length=4000)
    tags: list[str] | None = Field(default=None, max_length=8)


class EvalRunIn(BaseModel):
    k: int = Field(default=10, ge=1, le=30)
    use_judge: bool = False


class EvidenceRef(BaseModel):
    paper_id: int
    page: int | None = Field(default=None, ge=1)
    quote: str = Field(min_length=1, max_length=1500)


class DecisionIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    rationale: str = Field(default="", max_length=4000)
    method: str = Field(default="", max_length=200)
    dataset: str = Field(default="", max_length=200)
    metric: str = Field(default="", max_length=120)
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=10)


class DecisionPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    rationale: str | None = Field(default=None, max_length=4000)
    method: str | None = Field(default=None, max_length=200)
    dataset: str | None = Field(default=None, max_length=200)
    metric: str | None = Field(default=None, max_length=120)


class PredictionIn(BaseModel):
    paper_ids: list[int] = Field(min_length=1, max_length=6)
    prediction: str = Field(min_length=10, max_length=4000)


class Mark(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class ProvDocIn(BaseModel):
    title: str = Field(default="Untitled notes", max_length=300)
    content: str = Field(default="", max_length=200000)


class ProvDocPatch(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    content: str | None = Field(default=None, max_length=200000)
    marks: list[Mark] | None = None


class ReflectionIn(BaseModel):
    reflection: str = Field(max_length=4000)
