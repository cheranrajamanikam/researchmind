"""FastAPI application: API under /api, built frontend served from /."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import __version__
from .config import get_settings
from .db import get_engine, init_engine
from .logging_setup import setup_logging
from .migrate import upgrade_to_head
from .services import extraction, pipeline, think

log = logging.getLogger("researchmind")


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    setup_logging()
    cfg = get_settings()
    init_engine()
    upgrade_to_head(cfg.db_url)
    get_engine()
    resumed = pipeline.resume_pending()
    log.info("ResearchMind %s started; resumed %s unfinished paper(s)", __version__, resumed)
    yield
    pipeline.shutdown()


def create_app() -> FastAPI:
    from .api import analysis, auth, papers, projects, search, system, threads

    cfg = get_settings()
    app = FastAPI(title="ResearchMind", version=__version__, lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(
        CORSMiddleware, allow_origins=cfg.cors_list, allow_credentials=False, allow_methods=["*"], allow_headers=["*"]
    )

    api = APIRouter(prefix="/api")
    api.include_router(system.public)
    api.include_router(auth.router)
    for mod in (system, projects, papers, search, threads, analysis):
        api.include_router(mod.router)
    app.include_router(api)

    # Work that runs once a paper is searchable. Registration is idempotent (keyed by name).
    pipeline.register_post_process("extraction", extraction.after_paper_ready)
    pipeline.register_post_process("decision-alerts", think.check_decisions_for_paper)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(x) for x in first.get("loc", []) if x not in ("body", "query"))
        msg = first.get("msg", "Invalid request")
        return JSONResponse(status_code=422, content={"detail": f"{loc}: {msg}" if loc else msg})

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, HTTPException):
            raise exc
        log.exception("unhandled error")
        return JSONResponse(status_code=500, content={"detail": "Something went wrong on the server. Check the server log."})

    _mount_frontend(app, cfg.frontend_dist)
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    index = dist / "index.html"
    if not index.exists():

        @app.get("/", include_in_schema=False)
        def no_frontend() -> JSONResponse:
            return JSONResponse(
                {"message": "API is running. Frontend is not built yet: run `python run.py --rebuild` (needs Node 20+)."}
            )

        return

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and str(candidate).startswith(str(dist.resolve())):
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()
