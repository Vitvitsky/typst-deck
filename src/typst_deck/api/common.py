"""Общие ответы об ошибках, условные запросы и доступ к сервисному слою из маршрутов."""
import hashlib
from pathlib import Path

from fastapi import HTTPException, Request


class ApiError(HTTPException):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(status_code=status, detail={"code": code, "message": message})


def not_found(what: str) -> ApiError:
    return ApiError(404, "not_found", f"{what}: не найдено")


def svc(request: Request):
    return request.app.state.service


def file_etag(p: Path) -> str:
    """Та же формула, что у Starlette FileResponse, чтобы значение не разъезжалось."""
    st = p.stat()
    base = f"{st.st_mtime}-{st.st_size}"
    return f'"{hashlib.md5(base.encode(), usedforsecurity=False).hexdigest()}"'


def is_fresh(request: Request, etag: str) -> bool:
    """FileResponse отдаёт ETag, но условные запросы не обрабатывает: на жёсткой
    перезагрузке браузер шлёт If-None-Match и без этого получает файл целиком."""
    header = request.headers.get("if-none-match", "").strip()
    return header == "*" or etag in {t.strip() for t in header.split(",") if t.strip()}
