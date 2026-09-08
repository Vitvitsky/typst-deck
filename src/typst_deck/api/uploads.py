"""Загрузка файлов до создания колоды."""
from fastapi import APIRouter, Depends, UploadFile

from ..service import DeckService
from .common import svc

router = APIRouter(prefix="/api/uploads")


@router.post("")
async def upload(file: UploadFile, s: DeckService = Depends(svc)):
    name, data, text = s.ingest_file(file.filename or "file", await file.read())
    uid = s.store.stage_upload(name, data, text)
    return {"upload_id": uid, "name": name, "kind": "text" if text is not None else "image",
            "chars": len(text or "")}
