#!/usr/bin/env python3
"""ResearchMind launcher.

    python run.py              start everything (API + built frontend) on http://127.0.0.1:8000
    python run.py --check      diagnose this machine (Python, packages, Node, Ollama, database, frontend)
    python run.py --test       run the backend tests (and frontend tests if Node is available)
    python run.py --rebuild    reinstall frontend packages and rebuild the frontend
    python run.py --dev        API with auto-reload on :8000 plus the Vite dev server on :5173
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import signal
import subprocess
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
DIST = FRONTEND / "dist"

OK, WARN, FAIL = "  ok  ", " warn ", " FAIL "


def _line(tag: str, msg: str) -> None:
    print(f"[{tag}] {msg}")


def _node() -> tuple[str | None, str | None]:
    node, npm = shutil.which("node"), shutil.which("npm")
    return node, npm


def _node_major(node: str) -> int:
    try:
        out = subprocess.run([node, "-v"], capture_output=True, text=True, check=True).stdout.strip().lstrip("v")
        return int(out.split(".")[0])
    except (subprocess.SubprocessError, ValueError):
        return 0


def rebuild_frontend() -> bool:
    node, npm = _node()
    if not node or not npm:
        _line(FAIL, "Node.js 20+ is required to build the frontend (https://nodejs.org). The API still works without it.")
        return False
    if _node_major(node) < 20:
        _line(FAIL, f"Node 20+ required, found {subprocess.run([node, '-v'], capture_output=True, text=True).stdout.strip()}")
        return False
    print("Installing frontend packages…")
    if subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=FRONTEND).returncode != 0:
        _line(FAIL, "npm install failed")
        return False
    print("Building frontend…")
    if subprocess.run([npm, "run", "build"], cwd=FRONTEND).returncode != 0:
        _line(FAIL, "frontend build failed")
        return False
    _line(OK, f"frontend built → {DIST}")
    return True


def check() -> int:
    problems = 0
    sys.path.insert(0, str(BACKEND))

    v = sys.version_info
    if v >= (3, 11):
        _line(OK, f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        _line(FAIL, f"Python {v.major}.{v.minor} found; 3.11+ required")
        problems += 1

    missing = [m for m in ("fastapi", "uvicorn", "sqlalchemy", "alembic", "pydantic_settings", "pypdf", "pdfplumber",
                           "httpx", "numpy", "bcrypt", "jwt", "multipart") if importlib.util.find_spec(m) is None]
    if missing:
        _line(FAIL, f"missing Python packages: {', '.join(missing)} → pip install -r backend/requirements.txt")
        problems += 1
    else:
        _line(OK, "Python packages installed")

    node, npm = _node()
    if node and npm and _node_major(node) >= 20:
        _line(OK, f"Node {subprocess.run([node, '-v'], capture_output=True, text=True).stdout.strip()}")
    else:
        _line(WARN, "Node 20+ not found: you can run the API, but cannot build the frontend")

    if (DIST / "index.html").exists():
        _line(OK, "frontend is built")
    else:
        _line(WARN, "frontend not built yet → python run.py --rebuild")

    if not missing:
        try:
            from app.config import get_settings
            from app.db import SessionLocal, init_engine
            from app.migrate import upgrade_to_head
            from app.services import settings_store
            from app.services.ollama import OllamaClient, OllamaError, OllamaUnavailable

            cfg = get_settings()
            probe = cfg.data_dir / ".write-test"
            probe.write_text("x")
            probe.unlink()
            _line(OK, f"data folder is writable: {cfg.data_dir}")
            init_engine()
            upgrade_to_head(cfg.db_url)
            _line(OK, f"database ready ({cfg.db_url.split('://')[0]})")
            db = SessionLocal()
            try:
                s = settings_store.get_all(db)
            finally:
                db.close()
            client = OllamaClient(s["ollama_url"], s["answer_model"], s["embed_model"], timeout=4.0)
            try:
                version, models = client.version(), client.list_models()
                _line(OK, f"Ollama {version} reachable at {s['ollama_url']}")
                for label, name in (("answer", s["answer_model"]), ("embedding", s["embed_model"])):
                    have = any(m == name or (":" not in name and m.split(":")[0] == name) for m in models)
                    if have:
                        _line(OK, f"{label} model installed: {name}")
                    else:
                        _line(WARN, f"{label} model not installed → ollama pull {name}")
            except (OllamaUnavailable, OllamaError) as e:
                _line(WARN, f"Ollama not reachable at {s['ollama_url']} ({e}). Keyword search still works; start Ollama for answers and semantic search.")
        except Exception as e:  # noqa: BLE001 - this is a diagnostic; report anything
            _line(FAIL, f"backend self-check failed: {type(e).__name__}: {e}")
            problems += 1

    print("\nAll good." if not problems else f"\n{problems} problem(s) found.")
    return 1 if problems else 0


def run_tests() -> int:
    code = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=BACKEND).returncode
    node, npm = _node()
    if node and npm and (FRONTEND / "node_modules").exists() and (FRONTEND / "package.json").exists():
        import json

        scripts = json.loads((FRONTEND / "package.json").read_text()).get("scripts", {})
        if "test" in scripts:
            code = subprocess.run([npm, "test", "--silent"], cwd=FRONTEND).returncode or code
    return code


def serve(host: str, port: int, dev: bool, open_browser: bool) -> int:
    if not (DIST / "index.html").exists() and not dev:
        node, _ = _node()
        if node:
            print("Frontend is not built yet. Building it once (needs internet for npm)…")
            rebuild_frontend()
        else:
            print("Frontend is not built and Node.js is not installed; starting the API only.")
    env = {**os.environ, "RM_HOST": host, "RM_PORT": str(port)}
    cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", host, "--port", str(port)]
    if dev:
        cmd.append("--reload")
    procs: list[subprocess.Popen] = []

    def _on_term(signum: int, _frame: object) -> None:
        # `docker stop`, systemd and `kill` send SIGTERM: unwind through the finally block so the
        # server child is stopped too, instead of being left behind holding the port and database.
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _on_term)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, _on_term)
    try:
        procs.append(subprocess.Popen(cmd, cwd=BACKEND, env=env))
        if dev:
            _, npm = _node()
            if not npm:
                print("npm not found; cannot start the Vite dev server.")
            else:
                if not (FRONTEND / "node_modules").exists():
                    subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=FRONTEND)
                procs.append(subprocess.Popen([npm, "run", "dev", "--", "--host", "127.0.0.1"], cwd=FRONTEND, env=env))
            print("Dev mode: open http://localhost:5173 (API on http://%s:%d)" % (host, port))
        else:
            url = f"http://{host}:{port}"
            print(f"\nResearchMind is running at {url}   (Ctrl+C to stop)\n")
            if open_browser:
                webbrowser.open(url)
        return procs[0].wait()
    except KeyboardInterrupt:
        return 0
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=15)
            except subprocess.TimeoutExpired:
                p.kill()


def main() -> int:
    ap = argparse.ArgumentParser(description="ResearchMind launcher")
    ap.add_argument("--check", action="store_true", help="diagnose this machine")
    ap.add_argument("--test", action="store_true", help="run the tests")
    ap.add_argument("--rebuild", action="store_true", help="reinstall and rebuild the frontend")
    ap.add_argument("--dev", action="store_true", help="auto-reload API + Vite dev server")
    ap.add_argument("--host", default=os.environ.get("RM_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("RM_PORT", "8000")))
    ap.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    a = ap.parse_args()
    if a.check:
        return check()
    if a.test:
        return run_tests()
    if a.rebuild:
        return 0 if rebuild_frontend() else 1
    return serve(a.host, a.port, a.dev, not a.no_browser)


if __name__ == "__main__":
    raise SystemExit(main())
