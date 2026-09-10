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


CHARS = ("знак", "знака", "знаков")
LINES = ("строка", "строки", "строк")
ITEMS = ("элемент", "элемента", "элементов")


def _plural(n: int, forms: tuple[str, str, str]) -> str:
    tail = abs(n) % 100
    if 11 <= tail <= 14:
        return forms[2]
    return {1: forms[0], 2: forms[1], 3: forms[1], 4: forms[1]}.get(tail % 10, forms[2])


def _phrase(key: str, n: int) -> str:
    forms = {"max": CHARS, "lines": LINES}.get(key, ITEMS)
    return f"{n} {_plural(n, forms)}"


def _measures(value: object) -> dict[str, int]:
    """Замеры значения поля по тем же ключам, что и в объявлении.

    У списка строк «max» — длина самого длинного элемента: сообщение всё равно
    называет поле целиком, а модель правит его целиком.
    """
    if isinstance(value, str):
        return {"max": len(value), "lines": value.count("\n") + 1}
    if isinstance(value, list):
        m = {"count": len(value)}
        if value and all(isinstance(x, str) for x in value):
            m["max"] = max(len(x) for x in value)
        return m
    return {}


def check_slide(slide, declared: dict, *, n: int, template_name: str, before=None) -> list[str]:
    """Нарушения объявленных пределов на одном слайде; пусто — всё в порядке.

    before — тот же слайд до правки. Нарушение, которое не стало хуже прежнего,
    пропускается: текст, сохранённый до появления пределов, иначе нельзя было бы
    даже сократить (спека §8).
    """
    fields = declared.get(slide.type, {})
    if not fields:
        return []
    same_type = before is not None and before.type == slide.type
    out: list[str] = []
    for field, limits in fields.items():
        got = _measures(getattr(slide, field, None))
        was = _measures(getattr(before, field, None)) if same_type else {}
        for key, limit in limits.items():
            actual = got.get(key)
            if actual is None or actual <= limit:
                continue
            if was.get(key) is not None and actual <= was[key]:
                continue
            out.append(f"слайд {n}, поле «{FIELD_RU.get(field, field)}»: "
                       f"{_phrase(key, actual)} при пределе {limit} в шаблоне «{template_name}»")
    return out


def check_deck(deck, declared: dict, template_name: str) -> list[str]:
    """Нарушения по всей колоде: для предупреждения о переезде в тесный шаблон."""
    out: list[str] = []
    for i, s in enumerate(deck.slides, 1):
        out += check_slide(s, declared, n=i, template_name=template_name)
    return out
