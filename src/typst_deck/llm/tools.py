"""Инструменты, которыми LLM правит колоду. Каждый вызов — валидируемый патч."""
from __future__ import annotations

from pydantic import ValidationError

from ..model import Deck, slide_schema


def _fn(name: str, description: str, params: dict) -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": params}}


def tool_specs() -> list[dict]:
    """Схемы шести инструментов в формате OpenAI function calling."""
    schema = slide_schema()
    defs = schema.pop("$defs", {})
    defs["Slide"] = schema
    slide_ref = {"$ref": "#/$defs/Slide"}

    def obj(props: dict, required: list[str]) -> dict:
        return {"type": "object", "properties": props, "required": required, "$defs": defs}

    return [
        _fn("set_deck",
            "Полностью задать презентацию: название и все слайды по порядку. Использовать при создании с нуля.",
            obj({"title": {"type": "string"}, "slides": {"type": "array", "items": slide_ref}}, ["title", "slides"])),
        _fn("update_slide",
            "Изменить отдельные поля существующего слайда. В patch только меняемые поля; type и id менять нельзя.",
            obj({"slide_id": {"type": "string"}, "patch": {"type": "object"}}, ["slide_id", "patch"])),
        _fn("add_slide", "Добавить слайд после слайда after (null — в конец).",
            obj({"slide": slide_ref, "after": {"type": ["string", "null"]}}, ["slide"])),
        _fn("remove_slide", "Удалить слайд.", obj({"slide_id": {"type": "string"}}, ["slide_id"])),
        _fn("move_slide", "Переставить слайд на позицию to_index (нумерация с нуля).",
            obj({"slide_id": {"type": "string"}, "to_index": {"type": "integer"}}, ["slide_id", "to_index"])),
        _fn("finish", "Завершить работу и кратко сказать пользователю, что сделано.",
            obj({"summary": {"type": "string"}}, ["summary"])),
    ]


def format_validation(e: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors())


class ToolExecutor:
    """Применяет вызовы инструментов к колоде; ошибки возвращает текстом, не исключением."""

    def __init__(self, deck: Deck):
        self.deck = deck
        self.changed = False
        self.ops: list[str] = []
        self.changes: list[dict] = []  # для интерфейса: что и с каким слайдом случилось
        self.finished = False
        self.summary = ""

    def call(self, name: str, args: dict) -> str:
        handler = getattr(self, f"_{name}", None) if not name.startswith("_") else None
        if handler is None:
            return f"ERROR: неизвестный инструмент {name}"
        try:
            return handler(**args)
        except TypeError as e:
            return f"ERROR: неверные аргументы: {e}"
        except ValidationError as e:
            return f"ERROR: {format_validation(e)}"
        except (KeyError, ValueError) as e:
            return f"ERROR: {e}"

    def _set_deck(self, title: str, slides: list[dict]) -> str:
        new = Deck(id=self.deck.id, title=title, slides=slides)
        self.deck.title, self.deck.slides = new.title, new.slides
        self._done("set_deck", {"kind": "rebuilt", "count": len(self.deck.slides)})
        ids = ", ".join(f"{i + 1}={s.id}" for i, s in enumerate(self.deck.slides))
        return f"OK: {len(self.deck.slides)} слайдов; id: {ids}"

    def _update_slide(self, slide_id: str, patch: dict) -> str:
        slide = self.deck.apply_patch(slide_id, patch)
        self._done(f"update_slide {slide_id}", self._ref("updated", slide, fields=sorted(patch)))
        return f"OK: слайд {slide_id} обновлён"

    def _add_slide(self, slide: dict, after: str | None = None) -> str:
        s = self.deck.add_slide(slide, after)
        self._done(f"add_slide {s.id}", self._ref("added", s))
        return f"OK: добавлен слайд {s.id} на позицию {self.deck.index_of(s.id) + 1}"

    def _remove_slide(self, slide_id: str) -> str:
        gone = self.deck.find(slide_id)
        self.deck.remove_slide(slide_id)
        self._done(f"remove_slide {slide_id}", self._ref("removed", gone))
        return f"OK: слайд {slide_id} удалён"

    def _move_slide(self, slide_id: str, to_index: int) -> str:
        self.deck.move_slide(slide_id, to_index)
        self._done(f"move_slide {slide_id}", self._ref("moved", self.deck.find(slide_id)))
        return f"OK: слайд {slide_id} теперь на позиции {self.deck.index_of(slide_id) + 1}"

    def _finish(self, summary: str = "") -> str:
        self.finished, self.summary = True, summary
        return "OK"

    def _ref(self, kind: str, slide, **extra) -> dict:
        return {"kind": kind, "slide_id": slide.id, "type": slide.type,
                "title": getattr(slide, "title", ""), **extra}

    def _done(self, op: str, change: dict) -> None:
        self.changed = True
        self.ops.append(op)
        self.changes.append(change)
