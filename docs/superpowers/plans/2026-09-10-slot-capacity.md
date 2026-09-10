# Ёмкость слотов шаблона — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** дать шаблону объявить ёмкость своих слотов, довести объявленные пределы до модели ещё до генерации и проверять их при каждой правке — чтобы модель перестала писать текст, который проходит валидацию, но не помещается в вёрстку.

**Architecture:** новый модуль `src/typst_deck/slots.py` — единственное место, где живёт понятие объявленного слота: он читает и зажимает объявление из `template.json`, накладывает его на JSON Schema для промпта и считает нарушения на слайде. Модуль зависит только от `model.py`, поэтому им одинаково пользуются реестр шаблонов, слой LLM и сервис, и ни один из них не зависит от другого. Последний рубеж — автоподбор кегля в самих Typst-шаблонах.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, pytest (`uv run pytest`), Typst 0.15.

**Spec:** `docs/superpowers/specs/2026-09-09-slot-capacity-design.md`

## Global Constraints

- Комментарии, сообщения об ошибках и тексты тестов — по-русски, как во всём репозитории.
- Новых зависимостей не добавлять: только стандартная библиотека, Pydantic и то, что уже в `pyproject.toml`.
- `model.py` остаётся статическим источником истины: динамических Pydantic-моделей не создавать (спека §1).
- Объявленные пределы могут только **сузить** глобальные из `model.py`, но не расширить (спека §3.2). Глобальные пределы: `TITLE_MAX = 120`, `BULLET_MAX = 200`, `bullets` ≤ 6 на `image`, ≤ 4 на `bar-chart`/`chart`, `data` ≤ 12, `labels` ≤ 24, `series` ≤ 4.
- `lines` ограничивает **явные** переводы строки: `value.count("\n") + 1 <= lines` (спека §3.1). Никаких метрик шрифта в Python.
- `template.json` без раздела `slots` ведёт себя ровно как сегодня (спека §8). `default` и `dark` на этом этапе не меняются.
- Три ключа объявления, все необязательные: `max` (знаков), `lines` (строк), `count` (элементов).
- Прогон тестов: `uv run pytest`. Тесты, которым нужен `typst`, помечаются `@requires_typst` из `tests/conftest.py`.
- Каждая задача заканчивается зелёным `uv run pytest` целиком, а не только своим файлом.

**Отклонение от спеки, принятое сознательно.** Спека §10 перечисляет затрагиваемые файлы и нового модуля среди них не называет: проверка отнесена к `llm/tools.py`, а наложение на схему — к `llm/agent.py`. Но те же две операции нужны сервису (`service.py`: предупреждение при переезде и 422 на ручную правку), а спека §5 прямо требует, чтобы слой LLM не зависел от реестра шаблонов. Общий модуль `slots.py` — единственная развязка, при которой обе зависимости идут вниз, к `model.py`. Всё остальное по спеке.

---

### Task 1: `slots.py` — чтение и зажатие объявления

**Files:**
- Create: `src/typst_deck/slots.py`
- Modify: `src/typst_deck/templates.py` (`TemplateInfo`, `_info`)
- Test: `tests/test_slots.py` (создать), `tests/test_templates.py` (дополнить)

**Interfaces:**
- Consumes: `typst_deck.model.slide_schema()`.
- Produces:
  - `slots.SCHEMA: dict` — схема слайда, посчитанная один раз при импорте;
  - `slots.FIELD_RU: dict[str, str]` — русские имена полей для сообщений;
  - `slots.clamp(raw: object, where: str = "") -> dict` — проверенное и зажатое объявление вида `{тип слайда: {поле: {ключ: int}}}`;
  - `TemplateInfo.slots: dict` — то же объявление у каждого шаблона реестра.

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_slots.py`:

```python
from typst_deck.slots import clamp


def test_clamp_keeps_declared_limits():
    raw = {"title": {"title": {"max": 60, "lines": 2}, "subtitle": {"max": 90, "lines": 2}},
           "image": {"bullets": {"count": 5, "max": 90}}}
    assert clamp(raw) == raw


def test_clamp_narrows_to_global_ceiling(caplog):
    """Шаблон не может расширить глобальный предел: 300 при TITLE_MAX = 120 даёт 120."""
    with caplog.at_level("WARNING", logger="typst_deck.slots"):
        out = clamp({"title": {"title": {"max": 300}}, "image": {"bullets": {"count": 20, "max": 500}}}, "tight")
    assert out == {"title": {"title": {"max": 120}}, "image": {"bullets": {"count": 6, "max": 200}}}
    assert any("300" in r.getMessage() and "120" in r.getMessage() for r in caplog.records)


def test_clamp_drops_unknown_type_field_and_key(caplog):
    with caplog.at_level("WARNING", logger="typst_deck.slots"):
        out = clamp({"nope": {"title": {"max": 10}},
                     "title": {"bullets": {"max": 10}, "title": {"max": 0, "width": 5, "lines": 1}}}, "tight")
    assert out == {"title": {"title": {"lines": 1}}}
    assert len(caplog.records) == 4  # тип, поле, max=0, неизвестный ключ


def test_clamp_of_nothing_is_empty():
    assert clamp(None) == {} and clamp("не объект") == {} and clamp({}) == {}


def test_lines_has_no_global_ceiling():
    """У числа строк глобального предела в model.py нет — объявление проходит как есть."""
    assert clamp({"title": {"subtitle": {"lines": 9}}}) == {"title": {"subtitle": {"lines": 9}}}
```

- [ ] **Step 2: Прогнать тест и убедиться, что он падает**

Run: `uv run pytest tests/test_slots.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'typst_deck.slots'`

- [ ] **Step 3: Написать модуль**

Создать `src/typst_deck/slots.py`:

```python
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
        if stype not in DEFS or not isinstance(fields, dict):
            log.warning("шаблон %s: неизвестный тип слайда «%s» в slots — пропущен", where, stype)
            continue
        props = DEFS[stype].get("properties", {})
        for field, limits in fields.items():
            prop = props.get(field)
            if prop is None or not isinstance(limits, dict):
                log.warning("шаблон %s: у слайда «%s» нет поля «%s» — пропущено", where, stype, field)
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
```

- [ ] **Step 4: Прогнать тест и убедиться, что он проходит**

Run: `uv run pytest tests/test_slots.py -v`
Expected: PASS (5 тестов)

- [ ] **Step 5: Написать падающий тест на реестр**

Дописать в `tests/test_templates.py`:

```python
def test_registry_reads_and_clamps_slots(tmp_path):
    d = tmp_path / "templates" / "tight"
    d.mkdir(parents=True)
    (d / "deck.typ").write_text("// stub")
    (d / "template.json").write_text(json.dumps({
        "name": "Тесный",
        "slots": {"title": {"title": {"max": 60, "lines": 2}, "subtitle": {"max": 300}}},
    }, ensure_ascii=False))
    reg = TemplateRegistry(TEMPLATE_DIR, tmp_path / "templates")
    assert reg.get("tight").slots == {"title": {"title": {"max": 60, "lines": 2}, "subtitle": {"max": 120}}}


def test_registry_without_slots_declares_nothing(tmp_path):
    """template.json без slots — поведение ровно как сегодня, глобальные пределы."""
    d = tmp_path / "templates" / "plain"
    d.mkdir(parents=True)
    (d / "deck.typ").write_text("// stub")
    (d / "template.json").write_text(json.dumps({"name": "Простой"}))
    reg = TemplateRegistry(TEMPLATE_DIR, tmp_path / "templates")
    assert reg.get("plain").slots == {} and reg.get("default").slots == {}
    assert reg.get("plain").public() == {"id": "plain", "name": "Простой", "description": ""}
```

- [ ] **Step 6: Прогнать и убедиться, что падает**

Run: `uv run pytest tests/test_templates.py -k slots -v`
Expected: FAIL — `TypeError: TemplateInfo.__init__() got an unexpected keyword argument 'slots'` либо `AttributeError: 'TemplateInfo' object has no attribute 'slots'`

- [ ] **Step 7: Прокинуть slots в реестр**

В `src/typst_deck/templates.py` заменить импорт dataclass и `TemplateInfo`:

```python
from dataclasses import dataclass, field
```

```python
@dataclass
class TemplateInfo:
    id: str
    name: str
    description: str
    path: Path
    # объявленная ёмкость слотов; пусто — действуют глобальные пределы model.py
    slots: dict = field(default_factory=dict)

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "description": self.description}
```

Добавить импорт рядом с `from .model import Deck`:

```python
from .slots import clamp
```

и в `_info` вернуть объявление:

```python
        name = meta.get("name") or ("Корпоративный" if tid == "default" else tid)
        return TemplateInfo(tid, name, meta.get("description", ""), path, clamp(meta.get("slots"), tid))
```

- [ ] **Step 8: Прогнать тесты**

Run: `uv run pytest tests/test_slots.py tests/test_templates.py -v && uv run pytest`
Expected: PASS, ни один старый тест не сломан

- [ ] **Step 9: Коммит**

```bash
git add src/typst_deck/slots.py src/typst_deck/templates.py tests/test_slots.py tests/test_templates.py
git commit -m "Объявленная ёмкость слотов: раздел slots в template.json и зажатие глобальным потолком"
```

---

### Task 2: пределы в схеме, которую видит модель

**Files:**
- Modify: `src/typst_deck/slots.py` (добавить `apply_to_schema`)
- Modify: `src/typst_deck/llm/agent.py` (`build_system_prompt`, `run_agent`)
- Modify: `src/typst_deck/llm/prompt.md` (убрать зашитые числа)
- Test: `tests/test_slots.py`, `tests/test_agent.py`

**Interfaces:**
- Consumes: `slots.clamp` из Task 1, `slots.SCHEMA`.
- Produces:
  - `slots.apply_to_schema(declared: dict) -> dict` — копия схемы слайда, суженная объявлением;
  - `build_system_prompt(deck, assets, templates=None, slots=None) -> str`;
  - `run_agent(..., slots: dict | None = None, template_name: str = "")`.

- [ ] **Step 1: Написать падающий тест на схему**

Дописать в `tests/test_slots.py`:

```python
from typst_deck.slots import SCHEMA, apply_to_schema, clamp


def _props(schema: dict, stype: str) -> dict:
    ref = schema["discriminator"]["mapping"][stype].rsplit("/", 1)[1]
    return schema["$defs"][ref]["properties"]


def test_schema_narrowed_by_declared_limits():
    declared = clamp({"title": {"title": {"max": 60}}, "image": {"bullets": {"count": 5, "max": 90}}})
    s = apply_to_schema(declared)
    assert _props(s, "title")["title"]["maxLength"] == 60
    assert _props(s, "image")["bullets"]["maxItems"] == 5
    assert _props(s, "image")["bullets"]["items"]["maxLength"] == 90
    # соседей не задело
    assert _props(s, "section")["title"]["maxLength"] == 120
    assert _props(s, "chart")["bullets"]["maxItems"] == 4


def test_schema_without_slots_is_the_model_schema():
    assert apply_to_schema({}) == SCHEMA


def test_apply_to_schema_does_not_mutate_source():
    apply_to_schema(clamp({"title": {"title": {"max": 10}}}))
    assert _props(SCHEMA, "title")["title"]["maxLength"] == 120


def test_lines_reaches_the_model_as_description():
    """Число строк средствами JSON Schema не выразить — модель читает описание."""
    s = apply_to_schema(clamp({"title": {"subtitle": {"lines": 2}, "author": {"lines": 1}}}))
    assert "2 строк" in _props(s, "title")["subtitle"]["description"]
    assert "без переводов строки" in _props(s, "title")["author"]["description"]


def test_count_on_list_of_objects():
    """У data и series ограничивается только число элементов: их элементы не строки."""
    s = apply_to_schema(clamp({"bar-chart": {"data": {"count": 6, "max": 30}}}))
    assert _props(s, "bar-chart")["data"]["maxItems"] == 6
    assert "maxLength" not in _props(s, "bar-chart")["data"].get("items", {})
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `uv run pytest tests/test_slots.py -k schema -v`
Expected: FAIL — `ImportError: cannot import name 'apply_to_schema'`

- [ ] **Step 3: Написать наложение на схему**

Дописать в `src/typst_deck/slots.py`:

```python
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
```

- [ ] **Step 4: Прогнать тест схемы**

Run: `uv run pytest tests/test_slots.py -v`
Expected: PASS

- [ ] **Step 5: Написать падающий тест на промпт**

Дописать в `tests/test_agent.py`:

```python
def test_system_prompt_uses_template_limits():
    from typst_deck.slots import clamp

    d = Deck(title="T", slides=[{"type": "title", "title": "A"}])
    declared = clamp({"title": {"title": {"max": 60, "lines": 1}}})
    p = build_system_prompt(d, [], slots=declared)
    assert '"maxLength":60' in p.replace(" ", "") and "без переводов строки" in p
    assert '"maxLength":120' in p.replace(" ", "")  # у остальных полей предел прежний


def test_system_prompt_without_slots_shows_global_limits():
    d = Deck(title="T", slides=[{"type": "title", "title": "A"}])
    p = build_system_prompt(d, [])
    assert '"maxLength":120' in p.replace(" ", "") and '"maxLength":60' not in p.replace(" ", "")


async def test_run_agent_passes_limits_to_prompt_and_executor():
    from typst_deck.slots import clamp

    d = Deck(title="T", slides=[{"type": "title", "title": "Итоги"}])
    sid = d.slides[0].id
    llm = FakeLLM([
        Completion("", [ToolCall("c1", "update_slide", {"slide_id": sid, "patch": {"title": "Э" * 80}})]),
        Completion("", [ToolCall("c2", "finish", {"summary": "готово"})]),
    ])
    out = await run_agent(llm, d, "правь", [], [], [], slots=clamp({"title": {"title": {"max": 60}}}),
                          template_name="Тесный")
    assert out.deck.slides[0].title == "Итоги"  # правка отвергнута пределом шаблона
    assert '"maxLength":60' in llm.calls[0][0]["content"].replace(" ", "")
```

`FakeLLM.calls` — список списков сообщений одного вызова, поэтому `calls[0][0]` — системный
промпт первого обращения; так же он читается в соседних тестах `tests/test_api.py`.

- [ ] **Step 6: Прогнать и убедиться, что падает**

Run: `uv run pytest tests/test_agent.py -k limits -v`
Expected: FAIL — `TypeError: build_system_prompt() got an unexpected keyword argument 'slots'`

- [ ] **Step 7: Прокинуть пределы в промпт и агент**

В `src/typst_deck/llm/agent.py` заменить импорт и две функции:

```python
from ..model import Deck
from ..slots import apply_to_schema
```

(`slide_schema` из импортов убрать — вместо неё теперь `apply_to_schema`.)

```python
def build_system_prompt(deck: Deck, assets: list[str], templates: list[dict] | None = None,
                        slots: dict | None = None) -> str:
    return (
        PROMPT
        .replace("{{SCHEMA}}", json.dumps(apply_to_schema(slots or {}), ensure_ascii=False))
        .replace("{{ASSETS}}", ", ".join(assets) if assets else "(нет)")
        .replace("{{TEMPLATES}}", _template_list(templates))
        .replace("{{DECK_JSON}}", deck.model_dump_json(include={"title", "template", "slides"}))
    )
```

В сигнатуру `run_agent` добавить два параметра и передать их дальше:

```python
async def run_agent(
    llm: LLM, deck: Deck, user_message: str, files: list[tuple[str, str]],
    history: list[dict], assets: list[str], templates: list[dict] | None = None,
    slots: dict | None = None, template_name: str = "",
    max_iter: int = 12,
) -> Outcome:
    template_ids = [t["id"] for t in templates] if templates else None
    ex = ToolExecutor(deck, template_ids, slots=slots, template_name=template_name)
    tools = tool_specs(template_ids)
    messages: list[dict] = [{"role": "system",
                             "content": build_system_prompt(deck, assets, templates, slots)}]
```

(`ToolExecutor` примет эти аргументы в Task 3; пока добавить их в его `__init__` как принимаемые и складываемые в поля — это делается там же, в Step 3 задачи 3. Чтобы Task 2 был зелёным сам по себе, добавить в `ToolExecutor.__init__` строки `slots` и `template_name` уже сейчас: см. следующий шаг.)

- [ ] **Step 8: Принять аргументы в ToolExecutor (без проверки, она в Task 3)**

В `src/typst_deck/llm/tools.py`:

```python
    def __init__(self, deck: Deck, template_ids: list[str] | None = None,
                 slots: dict | None = None, template_name: str = ""):
        self.deck = deck
        self.template_ids = template_ids
        self.slots = slots or {}
        self.template_name = template_name
        self.changed = False
```

- [ ] **Step 9: Убрать зашитые числа из промпта**

В `src/typst_deck/llm/prompt.md` заменить строку

```
- Заголовки до 120 символов, буллеты до 200 — тезисы, не абзацы.
  На слайде image не больше 6 буллетов, на графиках не больше 4.
```

на

```
- Пределы длины и количества зависят от шаблона и указаны в схеме ниже
  (maxLength, maxItems, описания полей). Не превышай их: заголовок — одна
  мысль, буллеты — тезисы, а не абзацы. Переводы строки внутри поля
  добавляй, только если это разрешено описанием поля.
```

- [ ] **Step 10: Прогнать тесты**

Run: `uv run pytest tests/test_agent.py tests/test_slots.py -v && uv run pytest`
Expected: PASS. Тест `test_run_agent_passes_limits_to_prompt_and_executor` пока проверяет только промпт — вторая половина (правка отвергнута) станет зелёной в Task 3; если она падает, временно закомментировать **только** строку с `assert out.deck.slides[0].title == "Итоги"` и снять комментарий в Task 3, Step 4.

- [ ] **Step 11: Коммит**

```bash
git add src/typst_deck/slots.py src/typst_deck/llm/agent.py src/typst_deck/llm/tools.py src/typst_deck/llm/prompt.md tests/test_slots.py tests/test_agent.py
git commit -m "Пределы шаблона доезжают до модели: схема в промпте сужается объявлением slots"
```

---

### Task 3: проверка пределов в `ToolExecutor`

**Files:**
- Modify: `src/typst_deck/slots.py` (добавить `check_slide`, `check_deck`)
- Modify: `src/typst_deck/llm/tools.py` (`_set_deck`, `_update_slide`, `_add_slide`)
- Modify: `src/typst_deck/service.py` (передать пределы в `run_agent`)
- Test: `tests/test_slots.py`, `tests/test_agent.py`

**Interfaces:**
- Consumes: `slots.clamp`, `TemplateInfo.slots`, `ToolExecutor(..., slots=, template_name=)` из Task 2.
- Produces:
  - `slots.check_slide(slide, declared, *, n: int, template_name: str, before=None) -> list[str]`;
  - `slots.check_deck(deck, declared, template_name) -> list[str]`;
  - `DeckService._slots(deck) -> tuple[dict, str]` — объявление и имя шаблона колоды.

- [ ] **Step 1: Написать падающий тест на проверку**

Дописать в `tests/test_slots.py`:

```python
import pytest

from typst_deck.model import Deck
from typst_deck.slots import check_deck, check_slide, clamp

TIGHT = clamp({"title": {"title": {"max": 60}, "subtitle": {"lines": 2, "max": 90}},
               "image": {"bullets": {"count": 3, "max": 40}}})


def _slide(**kw):
    return Deck(slides=[kw]).slides[0]


def test_check_reports_chars_field_and_template():
    s = _slide(type="title", title="Э" * 80)
    msgs = check_slide(s, TIGHT, n=1, template_name="Тесный")
    assert msgs == ["слайд 1, поле «Заголовок»: 80 знаков при пределе 60 в шаблоне «Тесный»"]


def test_check_counts_explicit_line_breaks():
    """Порог 2026-09-09: три перевода собирались, четыре — нет."""
    ok = _slide(type="title", title="A", subtitle="а\nб")
    bad = _slide(type="title", title="A", subtitle="а\nб\nв\nг")
    assert check_slide(ok, TIGHT, n=1, template_name="Тесный") == []
    assert check_slide(bad, TIGHT, n=1, template_name="Тесный") == [
        "слайд 1, поле «Подзаголовок»: 4 строки при пределе 2 в шаблоне «Тесный»"
    ]


def test_check_counts_list_items_and_longest_item():
    s = _slide(type="image", title="A", bullets=["раз", "два", "три", "Э" * 50])
    msgs = check_slide(s, TIGHT, n=2, template_name="Тесный")
    assert msgs == [
        "слайд 2, поле «Тезисы»: 4 элемента при пределе 3 в шаблоне «Тесный»",
        "слайд 2, поле «Тезисы»: 50 знаков при пределе 40 в шаблоне «Тесный»",
    ]


def test_check_without_declaration_finds_nothing():
    assert check_slide(_slide(type="title", title="Э" * 119), {}, n=1, template_name="Простой") == []


def test_check_lets_through_an_edit_that_reduces_the_violation():
    """Иначе колода, созданная до появления пределов, стала бы нередактируемой."""
    was = _slide(type="title", title="Э" * 110)
    now = _slide(type="title", title="Э" * 100)
    assert check_slide(now, TIGHT, n=1, template_name="Тесный", before=was) == []
    worse = _slide(type="title", title="Э" * 111)
    assert check_slide(worse, TIGHT, n=1, template_name="Тесный", before=was) != []


def test_check_deck_numbers_slides_from_one():
    d = Deck(slides=[{"type": "final"}, {"type": "title", "title": "Э" * 80}])
    assert check_deck(d, TIGHT, "Тесный") == [
        "слайд 2, поле «Заголовок»: 80 знаков при пределе 60 в шаблоне «Тесный»"
    ]


@pytest.mark.parametrize("n,word", [(1, "знак"), (2, "знака"), (5, "знаков"), (11, "знаков"), (21, "знак")])
def test_plural_of_measures(n, word):
    from typst_deck.slots import _phrase

    assert _phrase("max", n) == f"{n} {word}"
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `uv run pytest tests/test_slots.py -k check -v`
Expected: FAIL — `ImportError: cannot import name 'check_slide'`

- [ ] **Step 3: Написать проверку**

Дописать в `src/typst_deck/slots.py`:

```python
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
```

Порядок ключей в сообщениях определяется порядком в объявлении (`{"count": ..., "max": ...}`), поэтому в `test_check_counts_list_items_and_longest_item` объявление написано в том же порядке — `count`, потом `max`.

- [ ] **Step 4: Прогнать тест проверки**

Run: `uv run pytest tests/test_slots.py -v`
Expected: PASS

- [ ] **Step 5: Написать падающий тест на исполнитель инструментов**

Дописать в `tests/test_agent.py`:

```python
TIGHT = {"title": {"title": {"max": 60}, "subtitle": {"lines": 2}},
         "image": {"bullets": {"count": 3}}}


def _tight_executor(deck=None):
    return ToolExecutor(deck if deck is not None else Deck(), slots=TIGHT, template_name="Тесный")


def test_executor_rejects_text_over_the_declared_limit():
    ex = _tight_executor(Deck(slides=[{"type": "title", "title": "Итоги"}]))
    sid = ex.deck.slides[0].id
    r = ex.call("update_slide", {"slide_id": sid, "patch": {"title": "Э" * 80}})
    assert r.startswith("ERROR") and "«Заголовок»" in r and "60" in r and "Тесный" in r
    assert ex.deck.slides[0].title == "Итоги" and not ex.changed and ex.ops == []


def test_executor_rejects_four_line_breaks_in_subtitle():
    """Ровно та правка, которая уронила боевую колоду 2026-09-09, — до рендера."""
    ex = _tight_executor(Deck(slides=[{"type": "title", "title": "Итоги", "subtitle": "Q3"}]))
    sid = ex.deck.slides[0].id
    assert ex.call("update_slide", {"slide_id": sid, "patch": {"subtitle": "а\nб\nв\nг"}}).startswith("ERROR")
    assert ex.deck.slides[0].subtitle == "Q3"
    assert ex.call("update_slide", {"slide_id": sid, "patch": {"subtitle": "а\nб"}}).startswith("OK")
    assert ex.deck.slides[0].subtitle == "а\nб"


def test_executor_rejects_extra_bullets_and_rolls_back_added_slide():
    ex = _tight_executor(Deck(slides=[{"type": "final"}]))
    r = ex.call("add_slide", {"slide": {"type": "image", "title": "A",
                                        "bullets": ["раз", "два", "три", "четыре"]}, "after": None})
    assert r.startswith("ERROR") and "«Тезисы»" in r
    assert len(ex.deck.slides) == 1 and ex.changes == []


def test_executor_set_deck_rejects_whole_deck_and_keeps_the_old_one():
    ex = _tight_executor(Deck(title="Старое", slides=[{"type": "final"}]))
    r = ex.call("set_deck", {"title": "Новое", "slides": [
        {"type": "title", "title": "Ок"}, {"type": "title", "title": "Э" * 80}]})
    assert r.startswith("ERROR") and "слайд 2" in r
    assert ex.deck.title == "Старое" and len(ex.deck.slides) == 1


def test_executor_without_slots_keeps_global_limits():
    ex = ToolExecutor(Deck(slides=[{"type": "title", "title": "Итоги"}]))
    sid = ex.deck.slides[0].id
    assert ex.call("update_slide", {"slide_id": sid, "patch": {"title": "Э" * 80}}).startswith("OK")
    assert ex.call("update_slide", {"slide_id": sid, "patch": {"title": "Э" * 500}}).startswith("ERROR")
```

- [ ] **Step 6: Прогнать и убедиться, что падает**

Run: `uv run pytest tests/test_agent.py -k executor -v`
Expected: FAIL — правка применяется, `assert ex.deck.slides[0].title == "Итоги"` не выполняется

- [ ] **Step 7: Проверять пределы в исполнителе**

В `src/typst_deck/llm/tools.py` добавить импорт:

```python
from ..slots import check_deck, check_slide
```

и правки в трёх обработчиках (проверка стоит сразу после Pydantic-валидации, в том же пути, который уже возвращает модели `ERROR`):

```python
    def _fits(self, slide, before=None) -> str | None:
        """Нарушения пределов шаблона одной строкой или None."""
        bad = check_slide(slide, self.slots, n=self.deck.index_of(slide.id) + 1,
                          template_name=self.template_name, before=before)
        return "; ".join(bad) if bad else None

    def _set_deck(self, title: str, slides: list[dict]) -> str:
        new = Deck(id=self.deck.id, title=title, slides=slides)
        bad = check_deck(new, self.slots, self.template_name)
        if bad:
            return "ERROR: " + "; ".join(bad[:5])
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
```

- [ ] **Step 8: Прогнать тесты исполнителя**

Run: `uv run pytest tests/test_agent.py -v`
Expected: PASS (включая раскомментированную строку из Task 2, Step 10)

- [ ] **Step 9: Написать падающий тест на передачу пределов из сервиса**

Дописать в `tests/test_api.py`:

```python
@requires_typst
async def test_generate_gives_the_model_template_limits(client, fake_llm, monkeypatch):
    """Сервис обязан передать агенту объявление шаблона колоды, а не пустое."""
    from typst_deck.model import Deck

    seen = {}
    import typst_deck.service as service_module
    real = service_module.run_agent

    async def spy(*a, **kw):
        seen.update(kw)
        return await real(*a, **kw)

    monkeypatch.setattr(service_module, "run_agent", spy)
    store = client.app.state.store
    d = store.create(Deck(title="T", template="dark", slides=[{"type": "final"}]))
    fake_llm._queue += [Completion("", [ToolCall("c1", "finish", {"summary": "готово"})])]
    r = await client.post(f"/api/decks/{d.id}/messages", json={"text": "привет"})
    await wait_job(client, r.json()["job_id"])
    assert seen["template_name"] == "Тёмный" and seen["slots"] == {}
```

- [ ] **Step 10: Прогнать и убедиться, что падает**

Run: `uv run pytest tests/test_api.py -k template_limits -v`
Expected: FAIL — `KeyError: 'template_name'`

- [ ] **Step 11: Передать пределы из сервиса**

В `src/typst_deck/service.py` добавить метод в `DeckService` (рядом с `template_dir`):

```python
    def _slots(self, deck: Deck) -> tuple[dict, str]:
        """Объявленная ёмкость слотов шаблона колоды и его имя для сообщений.
        Пропавший шаблон не должен ломать правку: без объявления действуют глобальные пределы."""
        try:
            t = self.templates.get(deck.template)
        except TemplateNotFound:
            return {}, deck.template
        return t.slots, t.name
```

и в `generate` передать их в агента:

```python
                declared, template_name = self._slots(deck)
                out = await run_agent(llm, deck, message, files, history, self.store.assets(deck_id),
                                      templates=[t.public() for t in self.templates.list()],
                                      slots=declared, template_name=template_name)
```

- [ ] **Step 12: Прогнать всё**

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 13: Коммит**

```bash
git add src/typst_deck/slots.py src/typst_deck/llm/tools.py src/typst_deck/service.py tests/test_slots.py tests/test_agent.py tests/test_api.py
git commit -m "Правка сверх ёмкости слота возвращается модели ошибкой, а не падает на рендере"
```

---

### Task 4: ручная правка сверх предела — 422 тем же текстом

**Files:**
- Modify: `src/typst_deck/service.py` (`manual`)
- Modify: `src/typst_deck/api/decks.py` (`revert`)
- Modify: `tests/conftest.py` (фикстура тесного шаблона)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `slots.check_slide`, `DeckService._slots` из Task 3.
- Produces: `DeckService.manual(deck_id, fn, check_slots: bool = True)` — при нарушении поднимает `ApiError(422, "validation", ...)` с тем же текстом, что видит модель.

- [ ] **Step 1: Добавить фикстуру тесного шаблона**

В `tests/conftest.py` дописать (после фикстуры `settings`):

```python
@pytest.fixture
def tight_settings(tmp_path):
    """Клиент с шаблоном, у которого объявлена ёмкость слотов.

    Шаблон — копия default: важна не вёрстка, а объявление в template.json.
    """
    import json
    import shutil as sh

    from typst_deck.config import Settings

    root = tmp_path / "templates"
    tight = root / "tight"
    tight.mkdir(parents=True)
    sh.copy(TEMPLATE_DIR / "deck.typ", tight / "deck.typ")
    (tight / "template.json").write_text(json.dumps({
        "name": "Тесный",
        "slots": {"title": {"title": {"max": 60}, "subtitle": {"lines": 2}},
                  "image": {"bullets": {"count": 3}}},
    }, ensure_ascii=False))
    return Settings(data_dir=tmp_path / "data", template_dir=TEMPLATE_DIR, templates_dir=str(root),
                    public_base_url="http://t", llm_model="deepseek-chat")


@pytest.fixture
async def tight_client(tight_settings, fake_llm):
    import httpx

    from typst_deck.app import create_app

    app = create_app(tight_settings, llm=fake_llm)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        c.app = app
        yield c
```

- [ ] **Step 2: Написать падающие тесты API**

Дописать в `tests/test_api.py`:

```python
@requires_typst
async def test_manual_edit_over_limit_is_422_with_the_same_text(tight_client):
    from typst_deck.model import Deck

    store = tight_client.app.state.store
    d = store.create(Deck(title="T", template="tight", slides=[{"type": "title", "title": "Итоги"}]))
    sid = d.slides[0].id
    r = await tight_client.patch(f"/api/decks/{d.id}/slides/{sid}", json={"patch": {"title": "Э" * 80}})
    assert r.status_code == 422
    msg = r.json()["detail"]["message"]
    assert "«Заголовок»" in msg and "80 знаков при пределе 60" in msg and "Тесный" in msg
    assert (await tight_client.get(f"/api/decks/{d.id}")).json()["deck"]["slides"][0]["title"] == "Итоги"


@requires_typst
async def test_manual_edit_that_reduces_an_old_violation_passes(tight_client):
    """Колода, созданная до появления пределов, обязана оставаться редактируемой."""
    from typst_deck.model import Deck

    store = tight_client.app.state.store
    d = store.create(Deck(title="T", template="tight", slides=[{"type": "title", "title": "Э" * 110}]))
    sid = d.slides[0].id
    r = await tight_client.patch(f"/api/decks/{d.id}/slides/{sid}", json={"patch": {"title": "Э" * 100}})
    assert r.status_code == 200
    r = await tight_client.patch(f"/api/decks/{d.id}/slides/{sid}", json={"patch": {"title": "Э" * 105}})
    assert r.status_code == 422


@requires_typst
async def test_revert_is_not_blocked_by_limits(tight_client):
    """Откат возвращает состояние, которое уже собиралось; запирать его нельзя."""
    from typst_deck.model import Deck

    store = tight_client.app.state.store
    d = store.create(Deck(title="T", template="tight", slides=[{"type": "title", "title": "Э" * 110}]))
    sid = d.slides[0].id
    assert (await tight_client.patch(f"/api/decks/{d.id}/slides/{sid}",
                                     json={"patch": {"title": "Коротко"}})).status_code == 200
    v = (await tight_client.get(f"/api/decks/{d.id}/versions")).json()[0]["version"]
    r = await tight_client.post(f"/api/decks/{d.id}/revert", json={"version": v})
    assert r.status_code == 200


@requires_typst
async def test_rename_and_move_are_not_affected_by_limits(tight_client):
    from typst_deck.model import Deck

    store = tight_client.app.state.store
    d = store.create(Deck(title="T", template="tight",
                          slides=[{"type": "title", "title": "Э" * 110}, {"type": "final"}]))
    assert (await tight_client.patch(f"/api/decks/{d.id}", json={"title": "Новое"})).status_code == 200
    sid = d.slides[1].id
    assert (await tight_client.post(f"/api/decks/{d.id}/slides/{sid}/move",
                                    json={"to_index": 0})).status_code == 200
```

Заметка про `revert`: версия для отката берётся из списка версий — первая в нём. Если в списке порядок другой, взять версию с наибольшим номером **меньше** текущей; проверить фактический порядок по `store.list_versions`.

- [ ] **Step 3: Прогнать и убедиться, что падает**

Run: `uv run pytest tests/test_api.py -k "limit or revert_is_not_blocked" -v`
Expected: FAIL — правка сверх предела отвечает 200

- [ ] **Step 4: Проверять пределы в `manual`**

В `src/typst_deck/service.py` добавить импорт:

```python
from .slots import check_deck, check_slide
```

и переписать `manual`:

```python
    async def manual(self, deck_id: str, fn: Callable[[Deck], object], check_slots: bool = True) -> dict:
        """Под блокировкой: fn правит колоду, новая версия, рендер; при ошибке рендера — откат.

        check_slots=False у отката и смены шаблона: откат возвращает состояние,
        которое уже собиралось, а переезд в тесный шаблон даёт предупреждение,
        а не отказ (спека §7) — иначе колода застревает между шаблонами.
        """
        t0 = time.perf_counter_ns()
        async with self.store.lock(deck_id):
            deck = self.load(deck_id)
            prev = deck.version
            before = deck.model_copy(deep=True) if check_slots else None
            try:
                fn(deck)
            except ValidationError as e:
                raise ApiError(422, "validation", format_validation(e))
            except KeyError as e:
                raise not_found(str(e).strip("'"))
            except ValueError as e:
                raise ApiError(422, "validation", str(e))
            if before is not None:
                declared, template_name = self._slots(deck)
                old = {s.id: s for s in before.slides}
                bad: list[str] = []
                for i, s in enumerate(deck.slides, 1):
                    bad += check_slide(s, declared, n=i, template_name=template_name, before=old.get(s.id))
                if bad:
                    raise ApiError(422, "validation", "; ".join(bad))
            self.store.save(deck)
```

(дальше `manual` не меняется)

- [ ] **Step 5: Исключить откат из проверки**

В `src/typst_deck/api/decks.py`:

```python
@router.post("/{deck_id}/revert")
async def revert(deck_id: str, body: RevertBody, s: DeckService = Depends(svc)):
    def fn(d):
        old = s.store.load_version(deck_id, body.version)
        d.title, d.slides = old.title, old.slides

    # откат возвращает версию, которая уже собиралась: пределы шаблона её не судят
    return await s.manual(deck_id, fn, check_slots=False)
```

- [ ] **Step 6: Прогнать тесты**

Run: `uv run pytest tests/test_api.py -v && uv run pytest`
Expected: PASS

- [ ] **Step 7: Коммит**

```bash
git add src/typst_deck/service.py src/typst_deck/api/decks.py tests/conftest.py tests/test_api.py
git commit -m "Ручная правка сверх ёмкости слота отвечает 422 тем же текстом, что видит модель"
```

---

### Task 5: предупреждение при переезде в более тесный шаблон

**Files:**
- Modify: `src/typst_deck/service.py` (`deck_response`, `change_template`)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `slots.check_deck`, `DeckService.manual(..., check_slots=False)` из Task 4.
- Produces: поле `warnings` ответа колоды дополняется нарушениями пределов текущего шаблона; блокировки нет.

- [ ] **Step 1: Написать падающий тест**

Дописать в `tests/test_api.py`:

```python
@requires_typst
async def test_moving_to_a_tighter_template_warns_but_is_allowed(tight_client):
    """Блокировать нельзя: колода застрянет — ни остаться, ни переехать."""
    from typst_deck.model import Deck

    store = tight_client.app.state.store
    d = store.create(Deck(title="T", template="default", slides=[{"type": "title", "title": "Э" * 100}]))
    r = await tight_client.post(f"/api/decks/{d.id}/template", json={"template": "tight"})
    assert r.status_code == 200 and r.json()["deck"]["template"] == "tight"
    assert any("«Заголовок»" in w and "Тесный" in w for w in r.json()["warnings"])
    # предупреждение живёт, пока живёт причина, и снимается вместе с ней
    sid = d.slides[0].id
    r = await tight_client.patch(f"/api/decks/{d.id}/slides/{sid}", json={"patch": {"title": "Коротко"}})
    assert r.status_code == 200 and r.json()["warnings"] == []


@requires_typst
async def test_deck_without_declared_slots_has_no_such_warnings(client):
    from typst_deck.model import Deck

    store = client.app.state.store
    d = store.create(Deck(title="T", slides=[{"type": "title", "title": "Э" * 110}]))
    r = await client.post(f"/api/decks/{d.id}/template", json={"template": "dark"})
    assert r.status_code == 200 and r.json()["warnings"] == []
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `uv run pytest tests/test_api.py -k tighter -v`
Expected: FAIL — `warnings` пуст

- [ ] **Step 3: Считать предупреждения в ответе колоды**

В `src/typst_deck/service.py`, `deck_response`, заменить блок чтения предупреждений и шаблона:

```python
        build = self.store.deck_dir(deck_id) / "build"
        wp = build / "warnings.json"
        warnings = json.loads(wp.read_text()) if wp.exists() else []
        base = self.settings.public_base_url.rstrip("/")
        try:
            info = self.templates.get(deck.template)
            template = info.public()
            # пределы проверяются на лету, а не запоминаются: предупреждение
            # исчезает вместе с причиной, как только текст сократили
            warnings = warnings + check_deck(deck, info.slots, info.name)
        except TemplateNotFound:
            template = {"id": deck.template, "name": deck.template, "description": "шаблон не найден"}
```

- [ ] **Step 4: Не блокировать смену шаблона**

В `src/typst_deck/service.py`:

```python
    async def change_template(self, deck_id: str, template: str) -> dict:
        """Сменить шаблон колоды; рендер и откат при ошибке — как в manual.

        Пределы нового шаблона проверяются не здесь: переезд даёт предупреждение
        в ответе колоды, а не отказ (спека §7).
        """
        self.template_dir(template)
        return await self.manual(deck_id, lambda d: setattr(d, "template", template), check_slots=False)
```

- [ ] **Step 5: Прогнать тесты**

Run: `uv run pytest tests/test_api.py -v && uv run pytest`
Expected: PASS

- [ ] **Step 6: Коммит**

```bash
git add src/typst_deck/service.py tests/test_api.py
git commit -m "Переезд в тесный шаблон предупреждает, а не запрещает"
```

---

### Task 6: автоподбор кегля в трёх шаблонах

**Files:**
- Modify: `template/deck.typ` (`fit-text`, `heading-block`, `slide-title`, `slide-section`)
- Modify: `templates/dark/deck.typ` (то же)
- Modify: `templates/lmru-hr/deck.typ` (`fit-text`, `slot`, `slide-title`)
- Test: `tests/test_compile.py`

**Interfaces:**
- Consumes: ничего из предыдущих задач (Typst-слой независим).
- Produces: `#let fit-text(h, sizes, body, ..args)` в каждом из трёх `deck.typ` — первый из размеров, при котором содержимое влезает в высоту `h`, иначе последний.

- [ ] **Step 1: Написать падающий тест**

Дописать в `tests/test_compile.py`:

```python
MM = 2.83465  # мм в пунктах: зоны в шаблонах заданы в мм, positions отдаёт пункты
LONG_TITLE = ("Итоги квартала по направлению данных и аналитики и планы полугодия " * 2)[:120]


def _field(positions, name):
    return next(p for p in positions if p["field"] == name)


def test_long_title_shrinks_into_its_zone(deck_dir):
    """Автокегль: длинный заголовок укладывается в зону, а не растёт пропорционально длине.

    Замер 2026-09-10 на этом шаблоне: короткий заголовок 21.3 pt, длинный
    с автокеглем 60.8 pt при зоне 68.0 pt, без автокегля — 139.7 pt.
    """
    short = compile_deck(Deck(slides=[{"type": "title", "title": "Итоги"}]), deck_dir, TEMPLATE_DIR)
    one_line = _field(short.positions, "title")["h"]
    long_ = compile_deck(Deck(slides=[{"type": "title", "title": LONG_TITLE}]), deck_dir, TEMPLATE_DIR)
    h = _field(long_.positions, "title")["h"]
    assert h > one_line        # длиннее одной строки — иначе тест ничего не проверяет
    assert h <= 24 * MM        # но в зону 2.4cm укладывается
    assert len([p for p in long_.positions if p["field"] == "title"]) == 1  # measure не задвоил маркер


@pytest.mark.parametrize("tid", sorted(p.name for p in (TEMPLATE_DIR.parent / "templates").iterdir() if (p / "deck.typ").exists()))
def test_long_section_title_stays_on_one_page(deck_dir, tid):
    r = compile_deck(Deck(slides=[{"type": "section", "title": LONG_TITLE, "subtitle": LONG_TITLE}]),
                     deck_dir, TEMPLATE_DIR.parent / "templates" / tid)
    assert len(r.svgs) == 1


def test_lmru_long_title_fits_the_slot_instead_of_being_clipped(deck_dir):
    """Замер 2026-09-10: заголовок в 120 знаков — 163.2 pt с автокеглем при слоте
    60mm (170.1 pt) и 380.0 pt без него, то есть больше половины текста обрезалось."""
    lmru = TEMPLATE_DIR.parent / "templates" / "lmru-hr"
    if not (lmru / "deck.typ").exists():
        pytest.skip("канон lmru-hr не подтянут")
    r = compile_deck(Deck(slides=[{"type": "title", "title": LONG_TITLE, "subtitle": "Q3 2026"}]),
                     deck_dir, lmru)
    assert len(r.svgs) == 1
    assert _field(r.positions, "title")["h"] <= 60 * MM
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `uv run pytest tests/test_compile.py -k "shrink or fits_the_slot" -v`
Expected: FAIL — высота заголовка растёт пропорционально длине: 139.7 pt при зоне 68.0 pt в `default` и 380.0 pt при слоте 170.1 pt в lmru-hr

- [ ] **Step 3: Автокегль в `template/deck.typ`**

Заменить `heading-block` и добавить перед ним `fit-text`:

```typst
// Кегль по месту: первый из размеров, при котором содержимое влезает в высоту h,
// иначе последний. Пределы из template.json приблизительны — широкие знаки всё
// равно вылезают, и это последний рубеж перед обрезкой.
#let fit-text(h, sizes, body, ..args) = layout(sz => context {
  let pick = sizes.last()
  for s in sizes {
    if measure(width: sz.width, text(size: s, ..args, body)).height <= h {
      pick = s
      break
    }
  }
  text(size: pick, ..args, body)
})

// Заголовок слайда: если в 19pt не помещается в полторы строки, уменьшается до 15pt.
#let heading-block(title) = {
  block(width: 100%, inset: (bottom: 5pt), stroke: (bottom: 1.2pt + accent))[
    #if title == none { v(19pt) } else { fit-text(19pt * 1.5, (19pt, 15pt), title, weight: "bold") }
  ]
  v(0.3cm)
}
```

Заменить титульный и разделительный слайды:

```typst
#let slide-title(title: none, subtitle: none, author: none, department: none) = slide(
  background: place(top, rect(width: 100%, height: 1.1cm, fill: accent)),
)[
  #v(1fr)
  #if title != none { fit-text(2.4cm, (28pt, 22pt, 17pt), title, weight: "bold") }
  #v(0.35cm)
  #if subtitle != none { fit-text(1.1cm, (14pt, 12pt, 10pt), subtitle, fill: muted) }
  #v(1.4fr)
  // автор и департамент — отдельные блоки контракта, прижаты к низу слайда;
  // порядок подписи: сначала человек, потом подразделение
  #if author != none { text(size: 10pt, fill: muted, author); linebreak() }
  #if department != none { text(size: 10pt, fill: muted, department) }
]

#let slide-section(title: none, subtitle: none) = slide(fill: accent)[
  #set text(fill: white)
  #v(1fr)
  #if title != none { fit-text(2.4cm, (26pt, 20pt, 16pt), title, weight: "bold") }
  #if subtitle != none { v(0.3cm); fit-text(1.0cm, (13pt, 11pt), subtitle) }
  #v(1fr)
]
```

- [ ] **Step 4: Тот же автокегль в `templates/dark/deck.typ`**

Внести в `templates/dark/deck.typ` ровно те же четыре правки, что в Step 3: `fit-text` перед `heading-block`, новый `heading-block`, новые `slide-title` и `slide-section`. Файл — тёмный вариант той же заглушки, различаются только цвета (`accent`, `ink`, `muted`), поэтому код блоков совпадает посимвольно.

- [ ] **Step 5: Автокегль в `templates/lmru-hr/deck.typ`**

Добавить `fit-text` после `body-box` и расширить `slot`:

```typst
// Кегль по месту: первый из размеров канона, при котором текст влезает в слот.
// Канон это предусматривает — size-h1 и size-h1-compact объявлены им самим.
#let fit-text(h, sizes, body, ..args) = layout(sz => context {
  let pick = sizes.last()
  for s in sizes {
    if measure(width: sz.width, text(size: s, ..args, body)).height <= h {
      pick = s
      break
    }
  }
  text(size: pick, ..args, body)
})

// Слот титульного слайда с потолком по высоте. Сам title-slide — это вызов
// page(), обернуть его в box(clip: true) нельзя, поэтому границу держим на входе.
// Пустое значение остаётся пустой строкой: канон проверяет `subtitle != ""`, и
// бокс нулевого содержимого всё равно занял бы свою высоту.
// sizes — лесенка кеглей канона: текст сначала пробует набраться крупным.
#let slot(h, x, sizes: none, ..args) = if x == none or x == "" { "" } else {
  box(width: 100%, height: h, clip: true,
      if sizes == none { x } else { fit-text(h, sizes, x, ..args) })
}
```

и в `slide-title` передать лесенки:

```typst
  title-slide(
    title: slot(60mm, title, sizes: (size-title, size-h1, size-h1-compact),
                weight: "bold", font: title-font),
    subtitle: slot(30mm, subtitle, sizes: (size-h2, size-body), font: title-font),
    department: slot(12mm, author),   // верхняя строка подписи
    author: slot(12mm, department),   // нижняя строка подписи
  )
```

Разделительный слайд lmru-hr не трогаем: он целиком канонический (`divider-slide-black`), уже переживает переросший заголовок (`test_template_survives_oversized_section_slide`), а лезть внутрь канона запрещает его README.

- [ ] **Step 6: Прогнать тесты компиляции**

Run: `uv run pytest tests/test_compile.py -v`
Expected: PASS. `measure` внутри `fit-text` маркеры `<edit>` не задваивает — это проверено на обоих шаблонах 2026-09-10 (по одному маркеру `title` до и после правки), но `assert len(...) == 1` в тесте оставить: он сторожит именно это.

- [ ] **Step 7: Посмотреть глазами**

```bash
uv run python -m typst_deck.templates
```
Expected: `каждый шаблон собирает образец`

- [ ] **Step 8: Прогнать всё и закоммитить**

Run: `uv run pytest`

```bash
git add template/deck.typ templates/dark/deck.typ templates/lmru-hr/deck.typ tests/test_compile.py
git commit -m "Автоподбор кегля на титульных и разделительных слайдах трёх шаблонов"
```

---

### Task 7: реальные значения `slots` для lmru-hr

**Files:**
- Create: `scripts/measure_slots.py`
- Modify: `templates/lmru-hr/template.json`
- Modify: `README.md` (раздел про шаблон Lemana Tech)
- Test: `tests/test_slots.py`, `tests/test_compile.py`

**Interfaces:**
- Consumes: `slots.clamp` (Task 1), автокегль из Task 6 (пороги меряются уже с ним).
- Produces: раздел `slots` в `templates/lmru-hr/template.json` с измеренными, а не угаданными значениями.

- [ ] **Step 1: Написать скрипт замера**

Создать `scripts/measure_slots.py`:

```python
#!/usr/bin/env python
"""Ёмкость слота в знаках: не угадывается, а измеряется typst'ом.

Скрипт просит typst померить высоту текста настоящим шрифтом шаблона при разной
длине и бинарным поиском находит наибольшую длину, которая ещё влезает в высоту
слота. Тем же способом меряется допустимое число явных строк.

Запуск:  uv run python scripts/measure_slots.py lmru-hr
Вывод — готовый раздел slots для template.json.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = "Итоги квартала по направлению данных и аналитики Лемана Тех "

# Слот: (тип слайда, поле, ширина зоны, высота зоны, высота одного элемента,
# кегль, начертание, шрифт). Все размеры — из deck.typ шаблона и его канона.
# lmru-hr: страница 677mm, поля 30+30; на титульном слайде колонка текста ещё
# уже на стрелку 47mm и gutter 18mm → 552mm. Высоты — аргументы slot().
# У содержательных слайдов тело — body-box высотой 250mm, ширина колонки
# тезисов: image — (617-15)*58% ≈ 349mm, chart — (617-12)*38% ≈ 230mm.
PROBES = {
    "lmru-hr": [
        ("title", "title", "552mm", "60mm", None, "size-title", "bold", "title-font"),
        ("title", "subtitle", "552mm", "30mm", None, "size-h2", "regular", "title-font"),
        ("title", "author", "552mm", "12mm", None, "size-body", "regular", "body-font"),
        ("title", "department", "552mm", "12mm", None, "size-body", "regular", "body-font"),
        ("image", "title", "617mm", "50mm", None, "size-h1-compact", "bold", "title-font"),
        ("image", "bullets", "349mm", "250mm", "40mm", "size-body", "regular", "body-font"),
        ("chart", "title", "617mm", "50mm", None, "size-h1-compact", "bold", "title-font"),
        ("chart", "bullets", "230mm", "200mm", "40mm", "size-body", "regular", "body-font"),
    ],
}

PROBE_TYP = """#import "slides_template.typ": *
#set page(width: {width}, height: auto, margin: 0pt)
#let base = "{sample}"
#let sample(n) = {{ let s = ""; while s.clusters().len() < n {{ s = s + base }}; s.clusters().slice(0, n).join() }}
#let lines(k) = range(k).map(i => "Строка").join("\\n")
#let h(body) = measure(width: {width}, text(size: {size}, weight: "{weight}", font: {font}, body)).height.mm()
#context [#metadata((
  chars: {chars}.map(n => (n, h(sample(n)))),
  lines: {lines}.map(k => (k, h(lines(k)))),
)) <probe>]
"""


def measure(tdir: Path, probe: tuple) -> dict:
    """Высоты текста в мм для набора длин и для набора числа строк."""
    _stype, _field, width, _cap, _item, size, weight, font = probe
    chars = list(range(10, 401, 5))
    lines = list(range(1, 13))
    src = tdir / "_measure.typ"
    src.write_text(PROBE_TYP.format(width=width, sample=SAMPLE, size=size, weight=weight,
                                    font=font, chars=chars, lines=lines))
    try:
        fonts = tdir / "fonts"
        cmd = ["typst", "eval", "query(<probe>).map(it => it.value)", "--root", str(tdir), "--in", str(src),
               "--format", "json"]
        if fonts.is_dir():
            cmd[2:2] = []  # порядок аргументов typst: --font-path идёт после подкоманды
            cmd += ["--font-path", str(fonts)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"typst не смог померить {probe[0]}.{probe[1]}:\n{r.stderr}")
        return json.loads(r.stdout)[0]
    finally:
        src.unlink(missing_ok=True)


def largest_fitting(pairs: list[list], cap_mm: float) -> int:
    """Наибольшее значение, при котором высота ещё не превысила потолок."""
    ok = [n for n, h in pairs if h <= cap_mm]
    return max(ok) if ok else 0


def main(tid: str) -> int:
    tdir = ROOT / "templates" / tid
    if not (tdir / "deck.typ").exists():
        raise SystemExit(f"шаблона {tid} нет в templates/")
    out: dict[str, dict[str, dict[str, int]]] = {}
    for probe in PROBES[tid]:
        stype, fld, _w, cap, item, *_ = probe
        m = measure(tdir, probe)
        cap_mm = float(cap.removesuffix("mm"))
        item_mm = float(item.removesuffix("mm")) if item else cap_mm
        limits: dict[str, int] = {}
        chars = largest_fitting(m["chars"], item_mm)
        limits["max"] = max(chars - chars % 5, 5)
        if item:
            limits["count"] = max(int(cap_mm // item_mm), 1)
        else:
            limits["lines"] = max(largest_fitting(m["lines"], cap_mm), 1)
        out.setdefault(stype, {})[fld] = limits
        print(f"{stype}.{fld}: {limits}", file=sys.stderr)
    print(json.dumps({"slots": out}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "lmru-hr"))
```

- [ ] **Step 2: Запустить замер**

Run: `uv run python scripts/measure_slots.py lmru-hr`
Expected: на stderr — по строке на слот, на stdout — JSON с разделом `slots`. Ожидаемый порядок величин (по контрольному замеру 2026-09-10: 60 знаков заголовка = 57.9mm при слоте 60mm): `title.title` около 60–75 знаков и 2 строк.

Если typst ругается на аргументы — свериться с вызовом в `src/typst_deck/render.py`, там та же связка `typst eval --root --in --format json` с `--font-path`, и повторить её порядок.

- [ ] **Step 3: Записать измеренное в template.json**

Заменить `templates/lmru-hr/template.json`, подставив полученные значения (числа ниже — ориентир из спеки §3, **заменить выводом скрипта**):

```json
{
  "name": "Lemana Tech",
  "description": "Корпоративный шаблон Лемана Тех: жёлтый титул, канонические компоненты, TT Interphases Pro",
  "slots": {
    "title": {
      "title": {"max": 60, "lines": 2},
      "subtitle": {"max": 90, "lines": 2},
      "author": {"max": 60, "lines": 1},
      "department": {"max": 60, "lines": 1}
    },
    "image": {
      "title": {"max": 70, "lines": 2},
      "bullets": {"count": 5, "max": 90}
    },
    "chart": {
      "title": {"max": 70, "lines": 2},
      "bullets": {"count": 3, "max": 80}
    }
  }
}
```

- [ ] **Step 4: Написать тест-воспроизведение бага 2026-09-09**

Дописать в `tests/test_slots.py`:

```python
def test_lmru_declaration_rejects_the_2026_09_09_incident():
    """Четыре перевода строки в подзаголовке титульного слайда — отказ до рендера."""
    import json
    from pathlib import Path

    from typst_deck.slots import check_slide, clamp

    root = Path(__file__).resolve().parents[1] / "templates" / "lmru-hr" / "template.json"
    declared = clamp(json.loads(root.read_text()).get("slots"), "lmru-hr")
    assert declared, "у lmru-hr должен быть объявлен раздел slots"
    bad = Deck(slides=[{"type": "title", "title": "Итоги квартала",
                        "subtitle": "«Лемана ПРО»" + "\n" * 4 + "хвост"}]).slides[0]
    assert check_slide(bad, declared, n=1, template_name="Lemana Tech")
    ok = Deck(slides=[{"type": "title", "title": "Итоги квартала",
                       "subtitle": "«Лемана ПРО»\nQ3 2026"}]).slides[0]
    assert check_slide(ok, declared, n=1, template_name="Lemana Tech") == []
```

- [ ] **Step 5: Написать тест, что объявленные пределы действительно собираются**

Дописать в `tests/test_compile.py`:

```python
def test_lmru_text_at_declared_limits_fits_on_one_page(deck_dir):
    """Предел, который сам не помещается в вёрстку, — не предел, а ложное обещание."""
    import json

    lmru = TEMPLATE_DIR.parent / "templates" / "lmru-hr"
    if not (lmru / "deck.typ").exists():
        pytest.skip("канон lmru-hr не подтянут")
    slots = json.loads((lmru / "template.json").read_text())["slots"]["title"]
    fill = lambda n: ("Итоги квартала " * 40)[:n]
    r = compile_deck(Deck(slides=[{"type": "title",
                                   "title": fill(slots["title"]["max"]),
                                   "subtitle": fill(slots["subtitle"]["max"]),
                                   "author": fill(slots["author"]["max"]),
                                   "department": fill(slots["department"]["max"])}]), deck_dir, lmru)
    assert len(r.svgs) == 1
```

- [ ] **Step 6: Прогнать всё**

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 7: Дописать README**

В `README.md`, в раздел «Шаблон Lemana Tech (`templates/lmru-hr`)», добавить абзац:

```markdown
### Ёмкость слотов

`template.json` объявляет разделом `slots`, сколько знаков и строк вмещает
каждое поле каждого типа слайда. Эти пределы попадают в схему, которую видит
модель, и проверяются при каждой правке — чата и панели свойств одинаково.
Объявление может только сузить глобальные пределы `model.py`, но не расширить:
колода переезжает между шаблонами, и текст, написанный под расширенный предел,
не прошёл бы в другом шаблоне.

Значения не угадываются: `uv run python scripts/measure_slots.py lmru-hr`
меряет высоту текста настоящим шрифтом шаблона и печатает готовый раздел
`slots`. Последний рубеж — автоподбор кегля в `deck.typ`: текст, уложившийся в
предел, но набранный широкими знаками, набирается меньшим кеглем из лесенки
канона (`size-title` → `size-h1` → `size-h1-compact`).
```

- [ ] **Step 8: Коммит**

```bash
git add scripts/measure_slots.py templates/lmru-hr/template.json README.md tests/test_slots.py tests/test_compile.py
git commit -m "Измеренная ёмкость слотов lmru-hr: скрипт замера и объявление в template.json"
```

---

## Проверка после всех задач

- [ ] `uv run pytest` — зелено целиком.
- [ ] `uv run python -m typst_deck.templates` — каждый шаблон собирает образец.
- [ ] Ручная проверка на боевом сценарии: колода в lmru-hr, просьба «сделай отступы на титульном слайде». Модель должна получить `ERROR` про строки и исправиться сама, а не уронить четыре генерации подряд.
- [ ] Предупредить пользователей перед выкаткой: автокегль визуально меняет уже существующие колоды — заголовок, который сейчас переливается или обрезается, станет мельче (спека §11).

## Что этот план сознательно не делает

- Каталог типов слайдов (`agenda`, `two-column`, `dual-chart`) — второй этап, отдельная спека; он опирается на понятие объявленного слота, которое вводится здесь.
- `slots` для `default` и `dark` — по §8 они остаются без объявления, пока значения для них не подобраны тем же скриптом.
- Пределы в миллиметрах и учёт автоматического переноса строк — §3.1: рубеж закрывают автокегль и проверка переполнения при рендере.
