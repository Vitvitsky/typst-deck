"""Сборка FastAPI-приложения: API, статика, страницы."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import agent as agent_api
from .api import decks, history, templates, uploads
from .api import jobs as jobs_api
from .config import Settings, get_settings
from .jobs import JobRegistry
from .llm.client import LLM, OpenAICompatLLM
from .logs import log_event, setup_logging
from .service import DeckService
from .store import DeckStore

STATIC = Path(__file__).parent / "static"
_UNSET = object()
# health дёргает Docker каждые 30 с — в логе это 80% строк и ноль пользы
QUIET_PATHS = {"/api/health"}

log = logging.getLogger(__name__)


class RevalidatingStatic(StaticFiles):
    """Статика без сборки и без хэшей в именах: браузер обязан перепроверять файл при каждой загрузке.
    Иначе после деплоя новый HTML может подхватить старый deck.js или style.css из кэша."""

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
        return resp


def create_app(settings: Settings | None = None, llm: LLM | None | object = _UNSET) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level, settings.log_format)
    if llm is _UNSET:
        llm = (
            OpenAICompatLLM(settings.llm_api_base, settings.llm_api_key, settings.llm_model,
                            settings.llm_max_tokens, settings.llm_tool_mode)
            if settings.llm_api_key else None
        )
    app = FastAPI(title="typst-deck")
    store = DeckStore(settings.data_dir)
    jobs = JobRegistry()
    app.state.settings, app.state.store, app.state.jobs, app.state.llm = settings, store, jobs, llm
    app.state.service = DeckService(store, jobs, llm, settings)  # type: ignore[arg-type]

    if settings.check_templates_on_start:
        # смонтированные шаблоны сборка образа не видит — сервис проверяет их сам,
        # в фоне: typst собирает образец каждым шаблоном, а старт ждать не должен
        threading.Thread(target=app.state.service.check_templates, name="template-check", daemon=True).start()

    @app.middleware("http")
    async def _timing(request: Request, call_next):
        t0 = time.perf_counter_ns()
        response = await call_next(request)
        if request.url.path not in QUIET_PATHS:
            log_event(log, "http", method=request.method, path=request.url.path,
                      status=response.status_code, ms=(time.perf_counter_ns() - t0) // 1_000_000)
        return response

    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "error", "message": str(exc.detail)}
        return JSONResponse({"error": detail}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        msg = "; ".join(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors())
        return JSONResponse({"error": {"code": "validation", "message": msg}}, status_code=422)

    for r in (uploads.router, decks.router, jobs_api.router, agent_api.router, templates.router, history.router):
        app.include_router(r)
    app.mount("/static", RevalidatingStatic(directory=STATIC), name="static")

    @app.get("/api/health")
    async def health():
        meter = app.state.service.meter
        return {"ok": True, "llm": llm is not None,
                "model": settings.llm_model if llm is not None else None,
                "tokens": meter.public(), "since": meter.since.isoformat(),
                "templates": app.state.service.templates_health()}

    def page(name: str) -> FileResponse:
        return FileResponse(STATIC / name, headers={"Cache-Control": "no-cache, must-revalidate"})

    @app.get("/")
    async def index():
        return page("index.html")

    @app.get("/d/{deck_id}")
    async def deck_page(deck_id: str):
        return page("deck.html")

    for route, name in (("/decks", "decks.html"), ("/history", "history.html"), ("/templates", "templates.html")):
        app.add_api_route(route, (lambda name=name: (lambda: page(name)))(), methods=["GET"])

    return app
