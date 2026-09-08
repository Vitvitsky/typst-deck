"""Статус фоновых задач."""
from fastapi import APIRouter, Depends

from ..service import DeckService
from .common import not_found, svc

router = APIRouter(prefix="/api/jobs")


@router.get("/{job_id}")
async def get_job(job_id: str, s: DeckService = Depends(svc)):
    job = s.jobs.get(job_id)
    if job is None:
        raise not_found("задача")
    return job.public()
