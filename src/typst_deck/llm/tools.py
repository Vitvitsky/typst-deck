"""Инструменты, которыми LLM правит колоду. Каждый вызов — валидируемый патч."""
from __future__ import annotations

import re

from pydantic import ValidationError

from ..model import TEMPLATE_PATTERN, Deck, slide_schema
from ..slots import check_deck, check_slide, first_few


def _fn(name: str, description: str, params: dict) -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": params}}


def tool_specs(template_ids: list[str] | None = None) -> list[dict]:
    """Схемы инструментов в формате OpenAI function calling; set_template ограничен списком шаблонов, если он есть."""
    schema = slide_schema()
    defs = schema.pop("$defs", {})
    defs["Slide"] = schema
    slide_ref = {"$ref": "#/$defs/Slide"}

    def obj(props: dict, required: list[str]) -> dict:
        return {"type": "object", "properties": props, "required": required, "$defs": defs}

    template_param: dict = {"type": "string", "description": "id шаблона из списка доступных в системном промпте"}
    if template_ids:
        template_param["enum"] = template_ids
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
        _fn("set_template", "Сменить оформление колоды: выбрать шаблон по его id из списка в системном промпте.",
            obj({"template": template_param}, ["template"])),
        _fn("finish", "Завершить работу и кратко сказать пользователю, что сделано.",
            obj({"summary": {"type": "string"}}, ["summary"])),
    ]


def format_validation(e: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors())


class ToolExecutor:
    """Применяет вызовы инструментов к колоде; ошибки возвращает текстом, не исключением."""

    def __init__(self, deck: Deck, template_ids: list[str] | None = None,
                 limits: dict[str, tuple[dict, str]] | None = None):
        self.deck = deck
        self.template_ids = template_ids
        # id шаблона → (объявленная ёмкость, имя для сообщений) по всем шаблонам:
        # модель может сменить шаблон посреди прогона, и следующая правка обязана
        # проверяться пределами нового. Готовый словарь, а не реестр шаблонов.
        self.limits = limits or {}
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

    def _current(self) -> tuple[dict, str]:
        """Пределы шаблона, в котором колода сейчас, — ищутся при каждой проверке,
        поэтому после set_template действуют сразу, без отдельного состояния.
        Шаблона нет среди переданных — действуют глобальные пределы model.py."""
        return self.limits.get(self.deck.template, ({}, self.deck.template))

    def _fits(self, slide, before=None) -> str | None:
        """Нарушения пределов шаблона одной строкой или None."""
        declared, name = self._current()
        bad = check_slide(slide, declared, n=self.deck.index_of(slide.id) + 1,
                          template_name=name, before=before)
        return "; ".join(bad) if bad else None

    def _set_deck(self, title: str, slides: list[dict]) -> str:
        new = Deck(id=self.deck.id, title=title, slides=slides)
        declared, name = self._current()
        bad = check_deck(new, declared, name, before=self.deck)
        if bad:
            return "ERROR: " + "; ".join(first_few(bad))
        self.deck.title, self.deck.slides = new.title, new.slides
        self._done("set_deck", {"kind": "rebuilt", "count": len(self.deck.slides)})
        ids = ", ".join(f"{i + 1}={s.id}" for i, s in enumerate(self.deck.slides))
        return f"OK: {len(self.deck.slides)} слайдов; id: {ids}"

    def _update_slide(self, slide_id: str, patch: dict) -> str:
        old = self.deck.find(slide_id)
        slide = self.deck.apply_patch(slide_id, patch)
        bad = self._fits(slide, before=old)
        if bad:
            self.deck.slides[self.deck.index_of(slide_id)] = old  # правка не применяется целиком
            return f"ERROR: {bad}"
        self._done(f"update_slide {slide_id}", self._ref("updated", slide, fields=sorted(patch)))
        return f"OK: слайд {slide_id} обновлён"

    def _add_slide(self, slide: dict, after: str | None = None) -> str:
        s = self.deck.add_slide(slide, after)
        bad = self._fits(s)
        if bad:
            self.deck.remove_slide(s.id)
            return f"ERROR: {bad}"
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

    def _set_template(self, template: str) -> str:
        if self.template_ids and template not in self.template_ids:
            return f"ERROR: шаблон «{template}» не найден; доступны: {', '.join(self.template_ids)}"
        if not re.fullmatch(TEMPLATE_PATTERN, template):
            raise ValueError(f"некорректный id шаблона «{template}»")
        self.deck.template = template
        self._done(f"set_template {template}", {"kind": "template", "template_id": template})
        return f"OK: шаблон сменён на «{template}»"

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
