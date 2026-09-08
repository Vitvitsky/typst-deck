import asyncio

import pytest

from typst_deck.jobs import JobConflict, JobRegistry


async def test_job_lifecycle():
    reg = JobRegistry()
    job = reg.create("d1")
    assert job.status == "queued" and reg.active_for("d1") is job
    ev = asyncio.Event()

    async def work():
        await ev.wait()
        return 7

    reg.start(job, work)
    await asyncio.sleep(0)
    assert reg.get(job.id).status == "running"
    with pytest.raises(JobConflict):
        reg.create("d1")
    ev.set()
    j = await reg.wait(job.id, timeout=1)
    assert j.status == "done" and j.deck_version == 7 and reg.active_for("d1") is None
    assert reg.last_for("d1") is j


async def test_job_failure():
    reg = JobRegistry()
    job = reg.create("d1")

    async def boom():
        raise RuntimeError("сломалось")

    reg.start(job, boom)
    j = await reg.wait(job.id, timeout=1)
    assert j.status == "failed" and "сломалось" in j.error


async def test_wait_timeout_returns_current_state():
    reg = JobRegistry()
    job = reg.create("d1")

    async def slow():
        await asyncio.sleep(5)

    reg.start(job, slow)
    j = await reg.wait(job.id, timeout=0.05)
    assert j.status == "running"
    assert reg.get("nope") is None
