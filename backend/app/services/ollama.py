"""Thin Ollama HTTP client with explicit offline handling."""
from __future__ import annotations

import json
import re
from typing import Any, Protocol

import httpx


class OllamaUnavailable(Exception):
    """Ollama cannot be reached (not running, wrong URL, timeout)."""


class OllamaError(Exception):
    """Ollama responded with an error (e.g. model not installed)."""


class LLMClient(Protocol):
    answer_model: str
    embed_model: str

    def version(self) -> str: ...
    def list_models(self) -> list[str]: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def chat_json(self, system: str, user: str, schema: dict[str, Any]) -> str: ...


class OllamaClient:
    def __init__(self, base_url: str, answer_model: str, embed_model: str, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.answer_model = answer_model
        self.embed_model = embed_model
        self.timeout = timeout

    # -- helpers -----------------------------------------------------------
    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            with httpx.Client(timeout=kwargs.pop("timeout", self.timeout)) as client:
                resp = client.request(method, f"{self.base_url}{path}", **kwargs)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
            raise OllamaUnavailable(f"Cannot reach Ollama at {self.base_url} ({type(e).__name__}).") from e
        except httpx.InvalidURL as e:
            raise OllamaUnavailable(f"Invalid Ollama URL: {self.base_url}") from e
        return resp

    @staticmethod
    def _err(resp: httpx.Response) -> OllamaError:
        try:
            msg = resp.json().get("error", resp.text)
        except ValueError:
            msg = resp.text
        return OllamaError(f"Ollama error {resp.status_code}: {msg}")

    # -- API ---------------------------------------------------------------
    def version(self) -> str:
        resp = self._request("GET", "/api/version", timeout=5)
        if resp.status_code != 200:
            raise self._err(resp)
        return str(resp.json().get("version", "unknown"))

    def list_models(self) -> list[str]:
        resp = self._request("GET", "/api/tags", timeout=5)
        if resp.status_code != 200:
            raise self._err(resp)
        return sorted(m["name"] for m in resp.json().get("models", []))

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self._request("POST", "/api/embed", json={"model": self.embed_model, "input": texts})
        if resp.status_code == 404 and "not found" not in resp.text.lower():
            # very old Ollama: no /api/embed, use the legacy endpoint
            out = []
            for t in texts:
                r = self._request("POST", "/api/embeddings", json={"model": self.embed_model, "prompt": t})
                if r.status_code != 200:
                    raise self._err(r)
                out.append(r.json()["embedding"])
            return out
        if resp.status_code != 200:
            raise self._err(resp)
        return resp.json()["embeddings"]

    def chat_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        body: dict[str, Any] = {
            "model": self.answer_model,
            "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": 0.1},
            "format": schema,
        }
        resp = self._request("POST", "/api/chat", json=body)
        if resp.status_code == 400:  # older servers: no JSON-schema support, fall back to plain json mode
            body["format"] = "json"
            resp = self._request("POST", "/api/chat", json=body)
        if resp.status_code != 200:
            raise self._err(resp)
        return resp.json()["message"]["content"]


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_json_object(raw: str) -> dict[str, Any] | None:
    """Parse a JSON object from model output, tolerating surrounding prose / code fences."""
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else None
    except (ValueError, TypeError):
        pass
    m = _JSON_RE.search(raw or "")
    if m:
        try:
            val = json.loads(m.group(0))
            return val if isinstance(val, dict) else None
        except ValueError:
            return None
    return None
