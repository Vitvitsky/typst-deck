"""Общие ответы об ошибках и доступ к сервисному слою из маршрутов."""
from fastapi import HTTPException, Request


class ApiError(HTTPException):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(status_code=status, detail={"code": code, "message": message})


def not_found(what: str) -> ApiError:
    return ApiError(404, "not_found", f"{what}: не найдено")


def svc(request: Request):
    return request.app.state.service
