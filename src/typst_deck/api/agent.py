"""Тонкие синхронные обёртки для чат-бота: создать, доработать, получить."""
import base64
import binascii

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..service import DeckService
from .common import ApiError, svc

router = APIRouter(prefix="/api/agent")


class FileIn(BaseModel):
    name: str
    content_base64: str


class CreateIn(BaseModel):
    brief: str = ""
    files: list[FileIn] = []
    template: str = "default"
    wait_seconds: int = Field(default=180, ge=0, le=600)


class ReviseIn(BaseModel):
    deck_id: str
    request: str
    wait_seconds: int = Field(default=180, ge=0, le=600)


@router.post("/create_deck")
async def create_deck(body: CreateIn, s: DeckService = Depends(svc)):
    files = []
    for f in body.files:
        try:
            data = base64.b64decode(f.content_base64, validate=True)
        except (binascii.Error, ValueError):
            raise ApiError(422, "validation", f"файл {f.name}: содержимое не в base64")
        files.append(s.ingest_file(f.name, data))
    deck, job = s.new_deck_from_brief(body.brief, files, body.template)
    await s.jobs.wait(job.id, body.wait_seconds)
    return s.agent_response(deck.id)


@router.post("/revise_deck")
async def revise_deck(body: ReviseIn, s: DeckService = Depends(svc)):
    job = s.submit_message(body.deck_id, body.request)
    await s.jobs.wait(job.id, body.wait_seconds)
    return s.agent_response(body.deck_id)


@router.get("/decks/{deck_id}")
async def get_deck(deck_id: str, s: DeckService = Depends(svc)):
    return s.agent_response(deck_id)
