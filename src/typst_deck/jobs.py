"""Фоновые задачи генерации в том же процессе. Одна активная задача на колоду."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Awaitable, Callable, Literal

from .model import new_id, utcnow

log = logging.getLogger(__name__)


class JobConflict(Exception):
    pass


@dataclass
class Job:
    id: str
    deck_id: str
    status: Literal["queued", "running", "done", "failed"] = "queued"
    error: str | None = None
    deck_version: int | None = None
    created_at: datetime = field(default_factory=utcnow)
    done_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    def public(self) -> dict:
        return {"id": self.id, "deck_id": self.deck_id, "status": self.status,
                "error": self.error, "deck_version": self.deck_version}


class JobRegistry:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._tasks: set[asyncio.Task] = set()

    def create(self, deck_id: str) -> Job:
        if self.active_for(deck_id):
            raise JobConflict(f"по колоде {deck_id} уже идёт задача")
        job = Job(id=new_id("j", 10), deck_id=deck_id)
        self._jobs[job.id] = job
        return job

    def start(self, job: Job, coro_factory: Callable[[], Awaitable[int | None]]) -> None:
        async def runner():
            job.status = "running"
            try:
                job.deck_version = await coro_factory()
                job.status = "done"
            except Exception as e:  # noqa: BLE001 — любая ошибка задачи идёт в статус
                log.exception("задача %s упала", job.id)
                job.status, job.error = "failed", f"{type(e).__name__}: {e}"
            finally:
                job.done_event.set()

        t = asyncio.create_task(runner())
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def active_for(self, deck_id: str) -> Job | None:
        for j in self._jobs.values():
            if j.deck_id == deck_id and j.status in ("queued", "running"):
                return j
        return None

    def last_for(self, deck_id: str) -> Job | None:
        js = [j for j in self._jobs.values() if j.deck_id == deck_id]
        return max(js, key=lambda j: j.created_at) if js else None

    async def wait(self, job_id: str, timeout: float) -> Job:
        job = self._jobs[job_id]
        try:
            await asyncio.wait_for(job.done_event.wait(), timeout)
        except asyncio.TimeoutError:
            pass
        return job
