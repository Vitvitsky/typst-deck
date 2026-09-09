"""Операции над колодой, общие для веб-интерфейса и агентского API."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Callable

from pydantic import ValidationError

from .api.common import ApiError, not_found
from .config import Settings
from .extract import UnsupportedFile, extract
from .jobs import Job, JobConflict, JobRegistry
from .llm.agent import run_agent
from .llm.client import LLM
from .llm.tools import format_validation
from .logs import log_event
from .model import Deck, utcnow
from .render import CompileError, CompileResult, compile_deck, page_size
from .store import DeckNotFound, DeckStore
from .templates import SAMPLE_DECK, TemplateNotFound, TemplateRegistry

# (имя, байты, извлечённый текст или None для картинок)
IngestedFile = tuple[str, bytes, str | None]

log = logging.getLogger(__name__)


def _ms(started_ns: int) -> int:
    return (time.perf_counter_ns() - started_ns) // 1_000_000


class TokenMeter:
    """Расход токенов за время жизни процесса; при рестарте обнуляется.
    Полная история лежит в chat.jsonl каждой колоды."""

    def __init__(self):
        self.tokens_in = self.tokens_out = self.tokens_cached = self.requests = 0
        self.since = utcnow()

    def add(self, tokens_in: int, tokens_out: int, tokens_cached: int, requests: int) -> None:
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        self.tokens_cached += tokens_cached
        self.requests += requests

    def public(self) -> dict:
        return {"in": self.tokens_in, "out": self.tokens_out,
                "cached": self.tokens_cached, "requests": self.requests}


class DeckService:
    def __init__(self, store: DeckStore, jobs: JobRegistry, llm: LLM | None, settings: Settings):
        self.store, self.jobs, self.llm, self.settings = store, jobs, llm, settings
        self.templates = TemplateRegistry(settings.template_dir, settings.templates_dirs)
        self.meter = TokenMeter()
        self._preview_locks: dict[str, asyncio.Lock] = {}

    # --- шаблоны
    def template_dir(self, tid: str):
        try:
            return self.templates.dir_for(tid)
        except TemplateNotFound:
            raise ApiError(422, "validation", f"шаблон «{tid}» не найден")

    async def template_preview(self, tid: str, n: int):
        """SVG n-й страницы образца в шаблоне; рендер кешируется в data/template-previews/<id>/.
        Компиляция уходит в поток по той же причине, что и в render()."""
        tdir = self.template_dir(tid)
        out = self.settings.data_dir / "template-previews" / tid
        stamp = out / "build" / "stamp.txt"
        newest = max((p.stat().st_mtime for p in tdir.rglob("*") if p.is_file()), default=0)
        # рендер в потоке, поэтому два первых превью одного шаблона больше не
        # сериализуются сами собой и подрались бы за build.tmp
        async with self._preview_locks.setdefault(tid, asyncio.Lock()):
            if not stamp.exists() or stamp.read_text() != str(newest):
                out.mkdir(parents=True, exist_ok=True)
                try:
                    await asyncio.to_thread(
                        compile_deck, SAMPLE_DECK.model_copy(update={"template": tid}), out, tdir,
                        self.settings.typst_bin,
                    )
                except CompileError as e:
                    raise ApiError(500, "render", f"шаблон «{tid}» не собрался: {e.stderr[:1500]}")
                stamp.write_text(str(newest))
        p = out / "build" / f"slide-{n}.svg"
        if not p.exists():
            raise not_found("страница образца")
        return p

    # --- история обращений по всем колодам
    def history(self, limit: int = 200) -> list[dict]:
        items = []
        for d in self.store.list_decks():
            for m in self.store.read_chat(d.id):
                if m.get("role") == "user":
                    items.append({"deck_id": d.id, "deck_title": d.title, "text": m["content"], "ts": m.get("ts", ""),
                                  "version": m.get("version")})
        items.sort(key=lambda x: x["ts"], reverse=True)
        return items[:limit]

    # --- чтение
    def load(self, deck_id: str) -> Deck:
        try:
            return self.store.load(deck_id)
        except DeckNotFound:
            raise not_found("колода")

    def deck_response(self, deck_id: str) -> dict:
        deck = self.load(deck_id)
        active, last = self.jobs.active_for(deck_id), self.jobs.last_for(deck_id)
        status = "generating" if active else ("failed" if last and last.status == "failed" else "ready")
        build = self.store.deck_dir(deck_id) / "build"
        wp = build / "warnings.json"
        warnings = json.loads(wp.read_text()) if wp.exists() else []
        base = self.settings.public_base_url.rstrip("/")
        try:
            template = self.templates.get(deck.template).public()
        except TemplateNotFound:
            template = {"id": deck.template, "name": deck.template, "description": "шаблон не найден"}
        return {
            "deck": deck.model_dump(mode="json"),
            "template": template,
            "status": status,
            "job": active.public() if active else None,
            "version": deck.version,
            "slide_count": len(deck.slides),
            "pdf_url": f"{base}/api/decks/{deck_id}/deck.pdf",
            "edit_url": f"{base}/d/{deck_id}",
            "warnings": warnings,
            "last_error": last.error if last else None,
            "has_build": (build / "deck.pdf").exists(),
            # размер страницы отсюда, чтобы фронт не качал slide-1.svg целиком ради viewBox
            "page": page_size(build / "slide-1.svg"),
        }

    def list_decks(self) -> list[dict]:
        out = []
        for d in self.store.list_decks():
            active, last = self.jobs.active_for(d.id), self.jobs.last_for(d.id)
            status = "generating" if active else ("failed" if last and last.status == "failed" else "ready")
            out.append({
                "id": d.id, "title": d.title, "slide_count": len(d.slides), "version": d.version,
                "created_at": d.created_at.isoformat(), "updated_at": d.updated_at.isoformat(),
                "status": status, "has_build": (self.store.deck_dir(d.id) / "build" / "deck.pdf").exists(),
            })
        return out

    def outline(self, deck: Deck) -> list[dict]:
        return [{"n": i + 1, "type": s.type, "title": getattr(s, "title", "")} for i, s in enumerate(deck.slides)]

    def agent_response(self, deck_id: str) -> dict:
        r = self.deck_response(deck_id)
        replies = [m for m in self.store.read_chat(deck_id) if m["role"] == "assistant"]
        return {
            "deck_id": deck_id, "status": r["status"], "pdf_url": r["pdf_url"], "edit_url": r["edit_url"],
            "outline": self.outline(self.load(deck_id)),
            "reply": replies[-1]["content"] if replies else "",
            "last_error": r["last_error"],
        }

    # --- рендер
    async def render(self, deck: Deck) -> CompileResult:
        """typst — блокирующий subprocess, поэтому уходит в поток: иначе на время
        компиляции встаёт весь сервер, включая статику и превью чужих колод."""
        try:
            return await asyncio.to_thread(
                compile_deck, deck, self.store.deck_dir(deck.id),
                self.template_dir(deck.template), self.settings.typst_bin,
            )
        except CompileError as e:
            raise ApiError(500, "render", f"{e}: {e.stderr[:2000]}")

    # --- ручные правки
    async def manual(self, deck_id: str, fn: Callable[[Deck], object]) -> dict:
        """Под блокировкой: fn правит колоду, новая версия, рендер; при ошибке рендера — откат."""
        t0 = time.perf_counter_ns()
        async with self.store.lock(deck_id):
            deck = self.load(deck_id)
            prev = deck.version
            try:
                fn(deck)
            except ValidationError as e:
                raise ApiError(422, "validation", format_validation(e))
            except KeyError as e:
                raise not_found(str(e).strip("'"))
            except ValueError as e:
                raise ApiError(422, "validation", str(e))
            self.store.save(deck)
            try:
                await self.render(deck)
            except ApiError:
                self.store.revert(deck_id, prev)
                log_event(log, "manual.failed", deck=deck_id, v=prev, ms=_ms(t0), level=logging.WARNING)
                raise
        log_event(log, "manual.done", deck=deck_id, v=deck.version, slides=len(deck.slides), ms=_ms(t0))
        return self.deck_response(deck_id)

    # --- файлы и генерация
    def require_llm(self) -> LLM:
        if self.llm is None:
            raise ApiError(503, "llm_unavailable", "LLM не настроена: задайте TYPST_DECK_LLM_API_KEY")
        return self.llm

    def ingest_file(self, name: str, data: bytes) -> IngestedFile:
        if len(data) > self.settings.max_upload_mb * 1024 * 1024:
            raise ApiError(413, "too_large", f"файл {name} больше {self.settings.max_upload_mb} МБ")
        try:
            ex = extract(name, data)
        except UnsupportedFile as e:
            raise ApiError(422, "validation", str(e))
        return name, data, (ex.text if ex.kind == "text" else None)

    def new_deck_from_brief(self, brief: str, files: list[IngestedFile], template: str = "default") -> tuple[Deck, Job]:
        self.require_llm()
        self.template_dir(template)
        first_line = (brief.strip().splitlines() or [""])[0].strip()
        deck = self.store.create(Deck(title=first_line[:120] or "Презентация", template=template))
        for name, data, text in files:
            if text is None:
                self.store.add_asset(deck.id, name, data)
            self.store.add_upload(deck.id, name, data, text)
        job = self.jobs.create(deck.id)
        self.jobs.start(job, lambda: self.generate(deck.id, brief, first=True))
        return deck, job

    def submit_message(self, deck_id: str, text: str) -> Job:
        self.require_llm()
        self.load(deck_id)
        try:
            job = self.jobs.create(deck_id)
        except JobConflict as e:
            raise ApiError(409, "conflict", str(e))
        self.jobs.start(job, lambda: self.generate(deck_id, text, first=False))
        return job

    async def generate(self, deck_id: str, message: str, first: bool) -> int:
        llm = self.require_llm()
        job = self.jobs.active_for(deck_id)
        job_id = job.id if job else None
        t0 = time.perf_counter_ns()
        log_event(log, "job.start", deck=deck_id, job=job_id, first=first)
        async with self.store.lock(deck_id):
            if job:
                job.phase = "reading"
            t_read = time.perf_counter_ns()
            deck = self.store.load(deck_id)
            prev = deck.version  # агент правит эту же колоду на месте, а save поднимет version
            files = self.store.list_uploads(deck_id)  # исходники нужны и при правках: кеш промпта делает это дёшево
            history = [m for m in self.store.read_chat(deck_id) if m["role"] in ("user", "assistant")]
            self._chat(deck_id, "user", message, deck.version)
            log_event(log, "stage.reading", deck=deck_id, job=job_id, files=len(files),
                      chars=sum(len(t) for _, t in files), history=len(history), ms=_ms(t_read))
            try:
                if job:
                    job.phase = "model"
                out = await run_agent(llm, deck, message, files, history, self.store.assets(deck_id),
                                      templates=[t.public() for t in self.templates.list()])
                if out.changed:
                    if job:
                        job.phase = "render"
                    self.store.save(out.deck)
                    try:
                        await self.render(out.deck)
                    except Exception:
                        # как в manual: колода, которая не собирается, не остаётся сохранённой
                        self.store.revert(deck_id, prev)
                        raise
            except Exception as e:
                self._chat(deck_id, "error", f"{type(e).__name__}: {e}", deck.version)
                log_event(log, "job.failed", deck=deck_id, job=job_id, err=f"{type(e).__name__}: {e}",
                          ms=_ms(t0), level=logging.ERROR)
                raise
            self.meter.add(out.tokens_in, out.tokens_out, out.tokens_cached, out.iterations)
            self._chat(deck_id, "assistant", out.reply, out.deck.version, ops=out.ops, changes=out.changes,
                       tokens_in=out.tokens_in, tokens_out=out.tokens_out, tokens_cached=out.tokens_cached,
                       iterations=out.iterations, llm_ms=out.llm_ms)
            log_event(log, "job.done", deck=deck_id, job=job_id, v=out.deck.version,
                      slides=len(out.deck.slides), tok_in=out.tokens_in, tok_out=out.tokens_out,
                      cached=out.tokens_cached, iter=out.iterations, ms=_ms(t0))
            return out.deck.version

    # --- материалы, удаление, переименование
    def add_material(self, deck_id: str, name: str, data: bytes) -> dict:
        """Файл из чата: картинка становится ассетом, документ — материалом для модели."""
        self.load(deck_id)
        name, data, text = self.ingest_file(name, data)
        if text is None:
            aid = self.store.add_asset(deck_id, name, data)
            self.store.add_upload(deck_id, name, data, None)
            return {"name": name, "kind": "image", "asset_id": aid}
        self.store.add_upload(deck_id, name, data, text)
        return {"name": name, "kind": "text", "chars": len(text)}

    def delete_deck(self, deck_id: str) -> None:
        self.load(deck_id)
        if self.jobs.active_for(deck_id):
            raise ApiError(409, "conflict", "колода сейчас собирается; дождитесь окончания")
        self.store.delete(deck_id)

    async def rename(self, deck_id: str, title: str) -> dict:
        def fn(d: Deck):
            d.title = title
        return await self.manual(deck_id, fn)

    async def change_template(self, deck_id: str, template: str) -> dict:
        """Сменить шаблон колоды; рендер и откат при ошибке — как в manual."""
        self.template_dir(template)
        return await self.manual(deck_id, lambda d: setattr(d, "template", template))

    def _chat(self, deck_id: str, role: str, content: str, version: int, **extra) -> None:
        self.store.append_chat(deck_id, {"role": role, "content": content, "version": version,
                                         "ts": utcnow().isoformat(), **extra})
