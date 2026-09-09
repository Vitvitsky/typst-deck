"""Событийное логирование: одна точка вызова, два формата вывода.

`log_event(log, "llm.done", deck=…, ms=…)` кладёт поля на запись, а форматтер
решает, показать их человеку (`ms=341`) или отдать машине (JSON-строкой).
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any

HANDLER_MARK = "_typst_deck_handler"
# httpx повторяет каждый вызов модели (у нас есть llm.done), uvicorn.access — каждый
# запрос, но без времени ответа (у нас есть http). Ошибки от них по-прежнему видны.
NOISY = ("httpx", "httpcore", "uvicorn.access")


def log_event(log: logging.Logger, event: str, level: int = logging.INFO, **fields: Any) -> None:
    """Событие с именем `event` и произвольными полями."""
    log.log(level, event, extra={"fields": fields})


def _render_value(v: Any) -> str:
    s = "" if v is None else str(v)
    return f'"{s}"' if (" " in s or s == "") else s


class TextFormatter(logging.Formatter):
    """`14:55:44 INFO  llm.done       deck=d1 ms=341`"""

    def format(self, record: logging.LogRecord) -> str:
        fields = getattr(record, "fields", None) or {}
        parts = [
            self.formatTime(record, "%H:%M:%S"),
            f"{record.levelname:<5}",
            f"{record.getMessage():<14}",
        ]
        if fields:
            parts.append(" ".join(f"{k}={_render_value(v)}" for k, v in fields.items()))
        out = " ".join(parts).rstrip()
        if record.exc_info:
            out += "\n" + self.formatException(record.exc_info)
        return out


class JsonFormatter(logging.Formatter):
    """Одна строка — один JSON-объект; несериализуемое приводится к строке."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "lvl": record.levelname,
            "ev": record.getMessage(),
            **(getattr(record, "fields", None) or {}),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO", fmt: str = "text") -> None:
    """Ставит единственный обработчик на корень; повторный вызов заменяет прежний."""
    root = logging.getLogger()
    for h in [h for h in root.handlers if getattr(h, HANDLER_MARK, False)]:
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    setattr(handler, HANDLER_MARK, True)
    root.addHandler(handler)
    root.setLevel(level.upper())
    for name in NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)
