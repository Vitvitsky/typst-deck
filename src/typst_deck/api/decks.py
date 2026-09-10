"""Колоды: создание, чтение сборки, ручные правки, версии, чат."""
import json

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from ..service import DeckService
from .common import ApiError, file_etag, is_fresh, not_found, svc

router = APIRouter(prefix="/api/decks")


class CreateBody(BaseModel):
    brief: str = ""
    upload_ids: list[str] = []
    template: str = "default"


class PatchBody(BaseModel):
    patch: dict


class AddBody(BaseModel):
    slide: dict
    after: str | None = None


class MoveBody(BaseModel):
    to_index: int


class RevertBody(BaseModel):
    version: int


class MessageBody(BaseModel):
    text: str


class RenameBody(BaseModel):
    title: str


class TemplateBody(BaseModel):
    template: str


@router.post("", status_code=202)
async def create(body: CreateBody, s: DeckService = Depends(svc)):
    files = []
    for uid in body.upload_ids:
        try:
            files.append(s.store.take_upload(uid))
        except KeyError:
            raise not_found(f"загрузка {uid}")
    deck, job = s.new_deck_from_brief(body.brief, files, body.template)
    return {"deck_id": deck.id, "job_id": job.id}


@router.get("")
async def list_decks(s: DeckService = Depends(svc)):
    return s.list_decks()


@router.get("/{deck_id}")
async def get(deck_id: str, s: DeckService = Depends(svc)):
    return s.deck_response(deck_id)


@router.patch("/{deck_id}")
async def rename(deck_id: str, body: RenameBody, s: DeckService = Depends(svc)):
    return await s.rename(deck_id, body.title)


@router.post("/{deck_id}/template")
async def change_template(deck_id: str, body: TemplateBody, s: DeckService = Depends(svc)):
    return await s.change_template(deck_id, body.template)


@router.delete("/{deck_id}", status_code=204)
async def delete(deck_id: str, s: DeckService = Depends(svc)):
    s.delete_deck(deck_id)


@router.post("/{deck_id}/uploads")
async def add_material(deck_id: str, file: UploadFile, s: DeckService = Depends(svc)):
    return s.add_material(deck_id, file.filename or "file", await file.read())


@router.get("/{deck_id}/slides/{n}.svg")
async def svg(request: Request, deck_id: str, n: int, s: DeckService = Depends(svc)):
    p = s.store.deck_dir(deck_id) / "build" / f"slide-{n}.svg"
    if not s.store.exists(deck_id) or not p.exists():
        raise not_found("страница")
    # URL версионирован (?v=), значит содержимое под ним не меняется. no-store
    # заставлял браузер тянуть все слайды заново после каждой правки — на боевой
    # колоде это 705 КБ несжатого SVG. private: колоды за Basic Auth, общим
    # прокси их кэшировать нельзя.
    headers = {"Cache-Control": "private, max-age=31536000, immutable"}
    etag = file_etag(p)
    if is_fresh(request, etag):
        return Response(status_code=304, headers={**headers, "ETag": etag})
    return FileResponse(p, media_type="image/svg+xml", headers={**headers, "ETag": etag})


@router.get("/{deck_id}/deck.pdf")
async def pdf(deck_id: str, s: DeckService = Depends(svc)):
    deck = s.load(deck_id)
    p = await s.pdf(deck_id)
    return FileResponse(p, media_type="application/pdf", filename=f"{deck.title[:60] or 'deck'}.pdf")


@router.get("/{deck_id}/positions")
async def positions(deck_id: str, s: DeckService = Depends(svc)):
    s.load(deck_id)
    p = s.store.deck_dir(deck_id) / "build" / "positions.json"
    return json.loads(p.read_text()) if p.exists() else []


@router.patch("/{deck_id}/slides/{slide_id}")
async def patch(deck_id: str, slide_id: str, body: PatchBody, s: DeckService = Depends(svc)):
    return await s.manual(deck_id, lambda d: d.apply_patch(slide_id, body.patch))


@router.post("/{deck_id}/slides")
async def add(deck_id: str, body: AddBody, s: DeckService = Depends(svc)):
    return await s.manual(deck_id, lambda d: d.add_slide(body.slide, body.after))


@router.delete("/{deck_id}/slides/{slide_id}")
async def remove(deck_id: str, slide_id: str, s: DeckService = Depends(svc)):
    return await s.manual(deck_id, lambda d: d.remove_slide(slide_id))


@router.post("/{deck_id}/slides/{slide_id}/move")
async def move(deck_id: str, slide_id: str, body: MoveBody, s: DeckService = Depends(svc)):
    return await s.manual(deck_id, lambda d: d.move_slide(slide_id, body.to_index))


@router.post("/{deck_id}/assets")
async def asset(deck_id: str, file: UploadFile, s: DeckService = Depends(svc)):
    s.load(deck_id)
    data = await file.read()
    if len(data) > s.settings.max_upload_mb * 1024 * 1024:
        raise ApiError(413, "too_large", f"файл больше {s.settings.max_upload_mb} МБ")
    try:
        return {"asset_id": s.store.add_asset(deck_id, file.filename or "", data)}
    except ValueError as e:
        raise ApiError(422, "validation", str(e))


@router.get("/{deck_id}/versions")
async def versions(deck_id: str, s: DeckService = Depends(svc)):
    s.load(deck_id)
    out = []
    for v in s.store.list_versions(deck_id):
        d = s.store.load_version(deck_id, v)
        out.append({"version": v, "updated_at": d.updated_at.isoformat(), "slide_count": len(d.slides)})
    return out


@router.post("/{deck_id}/revert")
async def revert(deck_id: str, body: RevertBody, s: DeckService = Depends(svc)):
    def fn(d):
        old = s.store.load_version(deck_id, body.version)
        d.title, d.slides = old.title, old.slides

    # откат возвращает версию, которая уже собиралась: пределы шаблона её не судят
    return await s.manual(deck_id, fn, check_slots=False)


@router.post("/{deck_id}/messages", status_code=202)
async def message(deck_id: str, body: MessageBody, s: DeckService = Depends(svc)):
    return {"job_id": s.submit_message(deck_id, body.text).id}


@router.get("/{deck_id}/chat")
async def chat(deck_id: str, s: DeckService = Depends(svc)):
    s.load(deck_id)
    return s.store.read_chat(deck_id)
