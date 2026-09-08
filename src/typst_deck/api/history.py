"""История обращений к модели по всем колодам."""
from fastapi import APIRouter, Depends, Query

from ..service import DeckService
from .common import svc

router = APIRouter(prefix="/api/history")


@router.get("")
async def history(limit: int = Query(200, ge=1, le=1000), s: DeckService = Depends(svc)):
    return s.history(limit)
