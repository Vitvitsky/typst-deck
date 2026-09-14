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
    "notes": "Заметки докладчика", "image": "Картинка", "image_size": "Размер картинки",
    "items": "Пункты", "blocks": "Блоки текста", "left": "Левая колонка", "right": "Правая колонка",
    "text": "Текст", "header": "Шапка таблицы", "rows": "Строки таблицы", "images": "Картинки",
    "video": "Видео", "url": "Ссылка", "poster": "Обложка", "kind": "Вид графика",
}


def _by_type(schema: dict) -> dict:
    """тип слайда → его определение в $defs (через discriminator.mapping)."""
    mapping = schema.get("discriminator", {}).get("mapping", {})
    return {t: schema["$defs"][ref.rsplit("/", 1)[1]] for t, ref in mapping.items()}


# Схема статична (model.py — источник истины), поэтому считается один раз.
SCHEMA = slide_schema()
DEFS = _by_type(SCHEMA)


def _kind(prop: dict) -> str | None:
    """Вид поля по его JSON Schema: "text" — строка свободного текста, "strings" —
    список строк, "list" — список прочего (объекты data, series), None — всё иное.

    str | None (anyOf) — не строковое поле: в схеме у него нет maxLength, и предел
    ушёл бы в проверку, минуя модель. enum и const — выбор из готовых значений,
    а не текст, у которого бывает ёмкость.
    """
    if "enum" in prop or "const" in prop:
        return None
    if prop.get("type") == "string":
        return "text"
    if prop.get("type") == "array":
        items = prop.get("items")
        return "strings" if isinstance(items, dict) and items.get("type") == "string" else "list"
    return None


# Таблица применимости из спеки §3: ключ → виды полей, к которым он применим,
# и объяснение для лога, почему остальным он не подходит.
APPLIES = {
    "max": ({"text", "strings"}, "max применим только к строковым полям и спискам строк"),
    "lines": ({"text"}, "lines применим только к строковым полям"),
    "count": ({"strings", "list"}, "count применим только к спискам"),
}


def _ceiling(prop: dict, key: str) -> int | None:
    """Глобальный предел из model.py для этого ключа, если он там задан."""
    if key == "lines":
        return None  # числа строк в модели нет: ограничивать нечем
    if key == "count":
        return prop.get("maxItems") if prop.get("type") == "array" else None
    target = prop.get("items") if prop.get("type") == "array" else prop
    return target.get("maxLength") if isinstance(target, dict) else None


def _resolve(props: dict, defs: dict, path: str) -> dict | None:
    """Свойство по пути «поле» или «поле.подполе»: у массива объектов спускаемся в items.

    Один шаг вглубь достаточен: вложенные модели (Block, Side, ChartSide) сами не
    вкладывают других моделей, а table.rows — список списков строк без $ref, так что
    путь «rows.что-то» ничего не находит и не выдумывает несуществующий синтаксис.
    """
    head, _, tail = path.partition(".")
    prop = props.get(head)
    if prop is None or not tail:
        return prop
    target = prop.get("items", prop) if prop.get("type") == "array" else prop
    ref = target.get("$ref")
    if ref:
        target = defs.get(ref.rsplit("/", 1)[1], {})
    return target.get("properties", {}).get(tail)


def _resolve_mut(props: dict, defs: dict, path: str) -> dict | None:
    """Как _resolve, но при спуске в $ref разворачивает его на месте собственной
    копией определения, а не общим объектом из defs.

    apply_to_schema мутирует ровно то, что возвращает эта функция. Без копии
    сужение одной стороны, которая делит $ref с другой (comparison.left/right —
    оба «#/$defs/Side», dual-chart.left/right — оба «#/$defs/ChartSide»),
    просачивалось бы через общий $defs и в схему соседа, которого шаблон не
    сужал: модель увидела бы в промпте предел, которого check_slide не проверяет
    (нарушение инварианта из докстринга apply_to_schema).
    """
    head, _, tail = path.partition(".")
    prop = props.get(head)
    if prop is None or not tail:
        return prop
    container = prop["items"] if prop.get("type") == "array" else prop
    ref = container.get("$ref")
    if ref:
        target = copy.deepcopy(defs.get(ref.rsplit("/", 1)[1], {}))
        container.pop("$ref", None)
        container.update(target)
    return container.get("properties", {}).get(tail)


def clamp(raw: object, where: str = "") -> dict:
    """Объявление slots, очищенное от неизвестного и зажатое глобальным потолком.

    Остаются только ключи, применимые к виду поля (таблица спеки §3): тогда
    каждый оставшийся ключ и попадает в схему (apply_to_schema), и проверяется
    (check_slide). Всё отброшенное и зажатое пишется в лог: опечатка в
    template.json иначе молча ничего не ограничивает.
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
            prop = _resolve(props, SCHEMA["$defs"], field)
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
                kinds, why = APPLIES[key]
                if _kind(prop) not in kinds:
                    # иначе ключ попал бы в схему и не в проверку или наоборот (спека §4)
                    log.warning("шаблон %s: %s.%s.%s — ключ не применим к этому полю (%s), пропущено",
                                where, stype, field, key, why)
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
            prop = _resolve_mut(props, schema["$defs"], field)
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

    «max» у списка строк сюда не входит: его элементы судятся поштучно (_excess).
    """
    if isinstance(value, str):
        return {"max": len(value), "lines": value.count("\n") + 1}
    if isinstance(value, list):
        return {"count": len(value)}
    return {}


def _excess(key: str, limit: int, now: object, was: object) -> int | None:
    """Замер, который нарушает предел и стал хуже прежнего; None — нарушения нет.

    was — значение поля до правки (None, если сравнивать не с чем).
    """
    if key == "max" and isinstance(now, list):
        # Элементы списка судятся поштучно, а не по самому длинному: иначе новый
        # длинный тезис рядом со старым проходил бы — самый длинный ведь не вырос.
        # Длинные элементы до и после сортируются и сопоставляются попарно:
        # каждому новому нужен свой старый не короче его (спека §8 — сокращённый
        # старый тезис проходит), а длинных не может стать больше, чем было.
        over = sorted((len(x) for x in now if isinstance(x, str) and len(x) > limit), reverse=True)
        kept = sorted((len(x) for x in was if isinstance(x, str) and len(x) > limit),
                      reverse=True) if isinstance(was, list) else []
        bad = [n for i, n in enumerate(over) if i >= len(kept) or n > kept[i]]
        return max(bad) if bad else None
    actual = _measures(now).get(key)
    if actual is None or actual <= limit:
        return None
    prev = _measures(was).get(key)
    if prev is not None and actual <= prev:
        return None
    return actual


def _value(slide, path: str):
    """Значение поля по пути: у массива объектов — список значений подполя,
    у вложенного объекта (left.bullets) — само его подполе."""
    head, _, tail = path.partition(".")
    value = getattr(slide, head, None)
    if not tail or value is None:
        return value
    if isinstance(value, list):
        return [getattr(x, tail, None) for x in value]
    return getattr(value, tail, None)


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
        now = _value(slide, field)
        was = _value(before, field) if same_type else None
        for key, limit in limits.items():
            actual = _excess(key, limit, now, was)
            if actual is None:
                continue
            label = FIELD_RU.get(field.partition(".")[0], field)
            out.append(f"слайд {n}, поле «{label}»: "
                       f"{_phrase(key, actual)} при пределе {limit} в шаблоне «{template_name}»")
    return out


def first_few(messages: list[str], limit: int = 5) -> list[str]:
    """Первые limit сообщений и «и ещё N», если их больше.

    Большая колода, созданная до пределов, иначе давала бы стену текста: и в
    ERROR модели, и в плашке предупреждений, которая склеивает их в строку.
    """
    if len(messages) <= limit:
        return list(messages)
    return messages[:limit] + [f"и ещё {len(messages) - limit}"]


def check_deck(deck, declared: dict, template_name: str, before=None) -> list[str]:
    """Нарушения объявленных пределов по всей колоде, слайд за слайдом.

    before — та же колода до правки (set_deck переписывает её целиком). Слайды
    сопоставляются по id: у найденной пары действует та же скидка «не стало
    хуже», что check_slide уже даёт update_slide (спека §8); слайд без пары в
    before — новый, скидки не получает.
    """
    by_id = {s.id: s for s in before.slides} if before is not None else {}
    out: list[str] = []
    for i, s in enumerate(deck.slides, 1):
        out += check_slide(s, declared, n=i, template_name=template_name, before=by_id.get(s.id))
    return out
