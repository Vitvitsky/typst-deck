"""Шаблоны: список и превью образца."""
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from ..service import DeckService
from .common import svc

router = APIRouter(prefix="/api/templates")


@router.get("")
async def list_templates(s: DeckService = Depends(svc)):
    return [t.public() for t in s.templates.list()]


@router.get("/{tid}/schema")
async def schema(tid: str, s: DeckService = Depends(svc)):
    """Схема слайда, суженная slots шаблона, — та же, что видит модель: панель
    проверяет по ней длины до отправки."""
    return s.template_schema(tid)


@router.get("/{tid}/preview/{n}.svg")
async def preview(tid: str, n: int, s: DeckService = Depends(svc)):
    return FileResponse(await s.template_preview(tid, n), media_type="image/svg+xml", headers={"Cache-Control": "max-age=60"})
