"""Ёмкость слотов шаблона: объявление из template.json, схема для модели и проверка.

Понятие объявленного слота нужно трём слоям сразу: реестр шаблонов читает
объявление, слой LLM накладывает его на схему в промпте и проверяет вызовы
инструментов, сервис предупреждает о переезде в более тесный шаблон и отвечает
422 на ручную правку. Поэтому модуль не зависит ни от реестра, ни от LLM —
только от model.py, и обе зависимости идут вниз, а не поперёк.

Пределы шаблона могут только сузить глобальные из model.py: колода меняет
шаблон, и текст, написанный под расширенный предел, перестал бы проходить
валидацию в любом другом шаблоне.
"""
from __future__ import annotations

import copy
import logging

from .model import slide_schema

log = logging.getLogger(__name__)

KEYS = ("max", "lines", "count")

# Имена полей для сообщений пользователю и модели; те же слова, что в интерфейсе
# (static/api.js, FIELD_RU) — человек видит одно и то же название везде.
FIELD_RU = {
    "title": "Заголовок", "subtitle": "Подзаголовок", "bullets": "Тезисы",
    "caption": "Подпись к картинке", "contact": "Контакты", "author": "Автор",
    "department": "Подразделение", "unit": "Единица измерения",
    "labels": "Подписи по оси", "data": "Данные диаграммы", "series": "Ряды данных",
}


def _by_type(schema: dict) -> dict:
    """тип слайда → его определение в $defs (через discriminator.mapping)."""
    mapping = schema.get("discriminator", {}).get("mapping", {})
    return {t: schema["$defs"][ref.rsplit("/", 1)[1]] for t, ref in mapping.items()}


# Схема статична (model.py — источник истины), поэтому считается один раз.
SCHEMA = slide_schema()
DEFS = _by_type(SCHEMA)


def _ceiling(prop: dict, key: str) -> int | None:
    """Глобальный предел из model.py для этого ключа, если он там задан."""
    if key == "lines":
        return None  # числа строк в модели нет: ограничивать нечем
    if key == "count":
        return prop.get("maxItems") if prop.get("type") == "array" else None
    target = prop.get("items") if prop.get("type") == "array" else prop
    return target.get("maxLength") if isinstance(target, dict) else None


def clamp(raw: object, where: str = "") -> dict:
    """Объявление slots, очищенное от неизвестного и зажатое глобальным потолком.

    Всё отброшенное и зажатое пишется в лог: опечатка в template.json иначе
    молча ничего не ограничивает.
    """
    out: dict[str, dict[str, dict[str, int]]] = {}
    if not isinstance(raw, dict):
        if raw is not None:
            log.warning("шаблон %s: slots не объект — раздел пропущен", where)
        return out
    for stype, fields in raw.items():
        if stype not in DEFS:
            log.warning("шаблон %s: неизвестный тип слайда «%s» в slots — пропущен", where, stype)
            continue
        if not isinstance(fields, dict):
            log.warning("шаблон %s: %s — значение не объект, пропущено", where, stype)
            continue
        props = DEFS[stype].get("properties", {})
        for field, limits in fields.items():
            prop = props.get(field)
            if prop is None:
                log.warning("шаблон %s: у слайда «%s» нет поля «%s» — пропущено", where, stype, field)
                continue
            if not isinstance(limits, dict):
                log.warning("шаблон %s: %s.%s — значение не объект, пропущено", where, stype, field)
                continue
            clean: dict[str, int] = {}
            for key, value in limits.items():
                if key not in KEYS or not isinstance(value, int) or isinstance(value, bool) or value < 1:
                    log.warning("шаблон %s: %s.%s.%s — неизвестный ключ или не целое положительное число",
                                where, stype, field, key)
                    continue
                ceiling = _ceiling(prop, key)
                if ceiling is not None and value > ceiling:
                    log.warning("шаблон %s: %s.%s.%s=%d больше глобального предела %d — зажато",
                                where, stype, field, key, value, ceiling)
                    value = ceiling
                clean[key] = value
            if clean:
                out.setdefault(stype, {})[field] = clean
    return out


def apply_to_schema(declared: dict) -> dict:
    """Схема слайда, суженная объявлением шаблона: ровно её видит модель в промпте.

    Схема и проверка (check_slide) строятся из одного объявления, поэтому
    разъехаться не могут: модель не получит предел, которого не будет в проверке.
    """
    schema = copy.deepcopy(SCHEMA)
    defs = _by_type(schema)
    for stype, fields in declared.items():
        props = defs.get(stype, {}).get("properties", {})
        for field, limits in fields.items():
            prop = props.get(field)
            if prop is None:
                continue
            if "max" in limits:
                target = prop.get("items") if prop.get("type") == "array" else prop
                if isinstance(target, dict) and target.get("type") == "string":
                    target["maxLength"] = limits["max"]
            if "count" in limits and prop.get("type") == "array":
                prop["maxItems"] = limits["count"]
            if "lines" in limits:
                n = limits["lines"]
                note = ("одна строка, без переводов строки" if n == 1
                        else f"не больше {n} строк: переводов строки не больше {n - 1}")
                prop["description"] = f"{prop['description']} {note}" if prop.get("description") else note
    return schema
