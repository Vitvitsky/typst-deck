# typst-deck v1 — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сервис, который из задания и файлов собирает презентацию в Typst-шаблоне, показывает превью, даёт править через LLM-чат и кликом по слайду, отдаёт PDF, и доступен чат-боту по REST.

**Architecture:** JSON-модель колоды (Pydantic) — источник истины; `render.py` детерминированно порождает `deck.typ` и вызывает `typst`; LLM работает только через инструменты-патчи; FastAPI отдаёт один API для веб-интерфейса и бота; колоды и версии лежат на диске.

**Tech Stack:** Python 3.12, uv, FastAPI, Pydantic v2, httpx, pytest + pytest-asyncio + respx, Typst 0.15 CLI, python-docx, openpyxl, статический фронтенд на ES-модулях.

**Spec:** `docs/superpowers/specs/2026-09-08-typst-deck-design.md`

## Global Constraints

- Python `>=3.12`; окружение и запуск через `uv` (`uv run pytest`, `uv run uvicorn`).
- Typst `>=0.15`; позиции полей только через `typst eval 'query(<edit>).map(it => it.value)'`, не `typst query`.
- LLM никогда не пишет Typst; рендерер не использует `@preview`-пакеты.
- Идентификаторы: колода — 12 символов `[a-z0-9]`; слайд — `s` + 6; ассет — `a` + 6 + расширение.
- Лимиты: заголовок/подпись ≤ 120 символов, буллет ≤ 200, буллетов ≤ 6 (image) и ≤ 4 (charts), `data` 1..12, `labels` 2..24, `series` 1..4.
- Запись файлов состояния — через временный файл и `os.replace`; сборка — в `build.tmp/`, затем подмена `build/`.
- Каждая функция слайда шаблона создаёт ровно одну страницу; после компиляции число SVG-страниц == число слайдов.
- Переменные окружения с префиксом `TYPST_DECK_`; `DEEPSEEK_API_KEY/API_BASE/MODEL` — синонимы для LLM.
- Комментарии, docstring-и, коммиты — на русском.

---

## Файлы

| Файл | Ответственность |
|------|-----------------|
| `pyproject.toml`, `.python-version`, `.gitignore` | окружение uv, pytest |
| `src/typst_deck/config.py` | `Settings`, `get_settings()` |
| `src/typst_deck/model.py` | модели слайдов и колоды, патчи, схема |
| `src/typst_deck/render.py` | `render_typ`, `compile_deck`, `CompileResult`, `CompileError` |
| `src/typst_deck/typst/fields.typ` | маркер `field` |
| `template/deck.typ` | заглушка шаблона по контракту |
| `src/typst_deck/store.py` | `DeckStore`: колоды, версии, ассеты, загрузки, чат, блокировки |
| `src/typst_deck/extract.py` | текст из docx/xlsx/csv/txt/md, распознавание картинок |
| `src/typst_deck/llm/client.py` | `LLM`, `Completion`, `ToolCall`, `FakeLLM`, `OpenAICompatLLM` |
| `src/typst_deck/llm/tools.py` | схемы инструментов, `ToolExecutor` |
| `src/typst_deck/llm/agent.py`, `prompt.md` | цикл агента, системный промпт |
| `src/typst_deck/jobs.py` | `JobRegistry`, `Job` |
| `src/typst_deck/app.py` | `create_app`, статика и страницы |
| `src/typst_deck/api/{uploads,decks,jobs,agent}.py` | маршруты |
| `src/typst_deck/static/*` | веб-интерфейс |
| `Dockerfile` | образ с typst |
| `tests/*` | по модулю на файл, `conftest.py` с фикстурами |

---

### Task 1: Каркас проекта и конфигурация

**Files:**
- Create: `pyproject.toml`, `.python-version`, `src/typst_deck/__init__.py`, `src/typst_deck/config.py`, `tests/conftest.py`, `tests/test_config.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `Settings` (поля из спеки §10), `get_settings() -> Settings` с подстановкой `DEEPSEEK_*`.

- [ ] **Step 1: Инициализировать окружение**

```bash
cd ~/projects/typst-deck
uv python pin 3.12
```

`pyproject.toml`:

```toml
[project]
name = "typst-deck"
version = "0.1.0"
description = "Корпоративный генератор презентаций: LLM + Typst"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "pydantic>=2.8",
  "pydantic-settings>=2.4",
  "httpx>=0.27",
  "python-multipart>=0.0.9",
  "python-docx>=1.1",
  "openpyxl>=3.1",
]

[dependency-groups]
dev = ["pytest>=8", "pytest-asyncio>=0.24", "respx>=0.21"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/typst_deck"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

`.gitignore` дополнить: `.python-version` НЕ игнорировать; добавить `uv.lock` оставить в git; `data/`, `.venv/`, `__pycache__/`, `*.pyc`, `build.tmp/`.

- [ ] **Step 2: Тест конфигурации**

`tests/test_config.py`:

```python
from typst_deck.config import get_settings


def test_defaults(monkeypatch):
    for k in list(__import__("os").environ):
        if k.startswith("TYPST_DECK_") or k.startswith("DEEPSEEK_"):
            monkeypatch.delenv(k)
    s = get_settings()
    assert s.typst_bin == "typst"
    assert s.llm_tool_mode == "tools"
    assert s.llm_api_key == ""


def test_deepseek_synonyms(monkeypatch):
    monkeypatch.delenv("TYPST_DECK_LLM_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    s = get_settings()
    assert s.llm_api_key == "sk-x"
    assert s.llm_model == "deepseek-chat"
    assert s.llm_api_base == "https://api.deepseek.com"


def test_prefix_wins(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
    monkeypatch.setenv("TYPST_DECK_LLM_API_KEY", "sk-y")
    assert get_settings().llm_api_key == "sk-y"
```

- [ ] **Step 3: Прогнать — падает (нет модуля)**

`uv run pytest tests/test_config.py -v` → ImportError.

- [ ] **Step 4: Реализация**

`src/typst_deck/config.py`:

```python
"""Настройки сервиса из окружения."""
import os
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TYPST_DECK_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    template_dir: Path = Path("template")
    typst_bin: str = "typst"
    public_base_url: str = ""
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_max_tokens: int = 4096
    llm_tool_mode: Literal["tools", "json"] = "tools"
    max_upload_mb: int = 20


def get_settings() -> Settings:
    """Собирает настройки; DEEPSEEK_* из стека принимаются как синонимы LLM_*."""
    s = Settings()
    if not s.llm_api_key:
        s.llm_api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not s.llm_api_base:
        s.llm_api_base = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    if not s.llm_model:
        s.llm_model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    return s
```

`tests/conftest.py` — пока пустой файл с docstring; фикстуры добавятся в задачах 4 и 10.

- [ ] **Step 5: Прогнать — проходит; коммит**

```bash
uv run pytest -v
git add -A && git commit -m "Каркас проекта: uv, pytest, настройки"
```

---

### Task 2: Модель колоды

**Files:**
- Create: `src/typst_deck/model.py`, `tests/test_model.py`

**Interfaces:**
- Produces: `Deck`, `Slide` (union), `SlideAdapter: TypeAdapter`, `TitleSlide`, `SectionSlide`, `ImageSlide`, `BarChartSlide`, `ChartSlide`, `FinalSlide`, `BarItem`, `Series`, `new_id(prefix: str, n: int) -> str`, `slide_schema() -> dict`; методы `Deck.find(slide_id) -> Slide`, `Deck.index_of(slide_id) -> int`, `Deck.apply_patch(slide_id, patch: dict) -> Slide`, `Deck.add_slide(data: dict, after: str | None) -> Slide`, `Deck.remove_slide(slide_id)`, `Deck.move_slide(slide_id, to_index: int)`. Ошибки: `KeyError` (нет слайда), `pydantic.ValidationError`, `ValueError` (патч меняет `type`/`id`).

- [ ] **Step 1: Тесты**

```python
import pytest
from pydantic import ValidationError

from typst_deck.model import Deck, SlideAdapter, slide_schema, new_id


def deck():
    return Deck(title="Тест", slides=[
        {"type": "title", "title": "Итоги", "subtitle": "Q3"},
        {"type": "image", "title": "Рост", "bullets": ["a", "b"]},
        {"type": "final"},
    ])


def test_ids_generated():
    d = deck()
    assert len(d.id) == 12 and d.id.isalnum() and d.id.islower()
    assert all(s.id.startswith("s") and len(s.id) == 7 for s in d.slides)
    assert len({s.id for s in d.slides}) == 3


def test_discriminator_and_defaults():
    s = SlideAdapter.validate_python({"type": "final"})
    assert s.title == "Спасибо" and s.contact == ""
    img = SlideAdapter.validate_python({"type": "image", "title": "x"})
    assert img.image is None and img.image_size == "medium" and img.bullets == []


@pytest.mark.parametrize("bad", [
    {"type": "image", "title": "x" * 121},
    {"type": "image", "title": "x", "bullets": ["y" * 201]},
    {"type": "image", "title": "x", "bullets": ["1", "2", "3", "4", "5", "6", "7"]},
    {"type": "image", "title": "x", "image_size": "huge"},
    {"type": "bar-chart", "title": "x", "data": []},
    {"type": "chart", "title": "x", "labels": ["a", "b"], "series": [{"name": "s", "values": [1]}]},
    {"type": "chart", "title": "x", "labels": ["a"], "series": [{"name": "s", "values": [1]}]},
    {"type": "unknown", "title": "x"},
    {"type": "title", "title": "x", "extra": 1},
])
def test_invalid(bad):
    with pytest.raises(ValidationError):
        SlideAdapter.validate_python(bad)


def test_apply_patch():
    d = deck()
    sid = d.slides[1].id
    s = d.apply_patch(sid, {"title": "Новый", "image_size": "large"})
    assert s.title == "Новый" and s.image_size == "large" and s.bullets == ["a", "b"]
    assert d.slides[1] is s and s.id == sid


def test_patch_cannot_change_type_or_id():
    d = deck()
    with pytest.raises(ValueError):
        d.apply_patch(d.slides[1].id, {"type": "final"})
    with pytest.raises(ValueError):
        d.apply_patch(d.slides[1].id, {"id": "s000000"})


def test_patch_invalid_keeps_slide():
    d = deck()
    sid = d.slides[1].id
    with pytest.raises(ValidationError):
        d.apply_patch(sid, {"title": "x" * 500})
    assert d.find(sid).title == "Рост"


def test_add_remove_move():
    d = deck()
    s = d.add_slide({"type": "section", "title": "Раздел"}, after=d.slides[0].id)
    assert d.index_of(s.id) == 1
    s2 = d.add_slide({"type": "section", "title": "В конец"}, after=None)
    assert d.index_of(s2.id) == 4
    d.move_slide(s2.id, 0)
    assert d.slides[0] is s2
    d.remove_slide(s2.id)
    assert len(d.slides) == 4
    with pytest.raises(KeyError):
        d.find("s_nope")


def test_schema_has_all_types():
    schema = slide_schema()
    text = str(schema)
    for t in ["title", "section", "image", "bar-chart", "chart", "final"]:
        assert f"'{t}'" in text


def test_roundtrip_json():
    d = deck()
    d2 = Deck.model_validate_json(d.model_dump_json())
    assert d2 == d
```

- [ ] **Step 2: Прогнать — падает**

- [ ] **Step 3: Реализация**

```python
"""Модель колоды — источник истины для рендера, LLM и правок."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
TITLE_MAX = 120
BULLET_MAX = 200


def new_id(prefix: str = "", n: int = 6) -> str:
    return prefix + "".join(secrets.choice(ALPHABET) for _ in range(n))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


Title = Annotated[str, Field(max_length=TITLE_MAX)]
Bullet = Annotated[str, Field(min_length=1, max_length=BULLET_MAX)]
ImageSize = Literal["small", "medium", "large"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SlideBase(_Strict):
    id: str = Field(default_factory=lambda: new_id("s"))
    notes: str = ""


class TitleSlide(SlideBase):
    type: Literal["title"]
    title: Title
    subtitle: Title = ""


class SectionSlide(SlideBase):
    type: Literal["section"]
    title: Title
    subtitle: Title = ""


class ImageSlide(SlideBase):
    type: Literal["image"]
    title: Title
    bullets: list[Bullet] = Field(default_factory=list, max_length=6)
    image: str | None = None
    image_size: ImageSize = "medium"
    caption: Title = ""


class BarItem(_Strict):
    label: Title
    value: float


class BarChartSlide(SlideBase):
    type: Literal["bar-chart"]
    title: Title
    data: list[BarItem] = Field(min_length=1, max_length=12)
    unit: str = ""
    bullets: list[Bullet] = Field(default_factory=list, max_length=4)


class Series(_Strict):
    name: Title
    values: list[float]


class ChartSlide(SlideBase):
    type: Literal["chart"]
    title: Title
    labels: list[Title] = Field(min_length=2, max_length=24)
    series: list[Series] = Field(min_length=1, max_length=4)
    unit: str = ""
    bullets: list[Bullet] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def _lengths(self):
        for s in self.series:
            if len(s.values) != len(self.labels):
                raise ValueError(f"серия «{s.name}»: {len(s.values)} значений при {len(self.labels)} подписях")
        return self


class FinalSlide(SlideBase):
    type: Literal["final"]
    title: Title = "Спасибо"
    contact: Title = ""


Slide = Annotated[
    Union[TitleSlide, SectionSlide, ImageSlide, BarChartSlide, ChartSlide, FinalSlide],
    Field(discriminator="type"),
]
SlideAdapter: TypeAdapter = TypeAdapter(Slide)


def slide_schema() -> dict:
    return SlideAdapter.json_schema()


class Deck(_Strict):
    id: str = Field(default_factory=lambda: new_id("", 12))
    title: Title = "Презентация"
    slides: list[Slide] = Field(default_factory=list)
    version: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    def index_of(self, slide_id: str) -> int:
        for i, s in enumerate(self.slides):
            if s.id == slide_id:
                return i
        raise KeyError(slide_id)

    def find(self, slide_id: str):
        return self.slides[self.index_of(slide_id)]

    def apply_patch(self, slide_id: str, patch: dict):
        i = self.index_of(slide_id)
        old = self.slides[i]
        if "type" in patch and patch["type"] != old.type:
            raise ValueError("тип слайда нельзя менять патчем; удалите слайд и добавьте новый")
        if "id" in patch and patch["id"] != old.id:
            raise ValueError("id слайда нельзя менять")
        new = SlideAdapter.validate_python(old.model_dump() | patch)
        self.slides[i] = new
        return new

    def add_slide(self, data: dict, after: str | None = None):
        slide = SlideAdapter.validate_python(data)
        pos = len(self.slides) if after is None else self.index_of(after) + 1
        self.slides.insert(pos, slide)
        return slide

    def remove_slide(self, slide_id: str) -> None:
        del self.slides[self.index_of(slide_id)]

    def move_slide(self, slide_id: str, to_index: int) -> None:
        s = self.slides.pop(self.index_of(slide_id))
        self.slides.insert(max(0, min(to_index, len(self.slides))), s)
```

- [ ] **Step 4: Прогнать — проходит; коммит** `Модель колоды и слайдов`

---

### Task 3: Рендер `.typ` из модели

**Files:**
- Create: `src/typst_deck/render.py` (только `render_typ` и вспомогательные), `src/typst_deck/typst/fields.typ`, `tests/test_render.py`, `tests/golden/full.typ`

**Interfaces:**
- Consumes: `Deck`, слайды из Task 2.
- Produces: `typ_str(s: str) -> str` (литерал строки Typst), `typ_value(v) -> str` (str/int/float/bool/list/dict → Typst), `render_typ(deck: Deck, assets: set[str]) -> tuple[str, list[str]]` (текст и предупреждения).

Правила рендера:
- Строки — всегда литералы `"..."` (экранируются `\` и `"`, перевод строки → `\n`); в разметку они попадают как `#"..."` или как аргументы функций, поэтому спецсимволы разметки не нужны.
- Текстовое поле: `field("<slide_id>", "<name>", "<строка>")`; пустая строка → `none` (без маркера).
- Буллеты: `field("<id>", "bullets", list("a", "b"))`; пустой список → `none`.
- Картинка: `field("<id>", "image", image("/assets/<asset>"))`, если ассет есть; иначе `none` и предупреждение `слайд N: картинка <id> не найдена`.
- `data`: `((label: "…", value: 1.0), …)`; `labels`: `("a", "b",)`; `series`: `((name: "…", values: (1.0, 2.0,)),)`. Одноэлементные массивы — с запятой на конце.
- Заголовок файла:

```typst
#import "/template/deck.typ": *
#import "/fields.typ": field
#show: deck.with(title: "…")
```

`fields.typ`:

```typst
// Маркер редактируемого поля: пишет в метаданные положение и размер содержимого.
#let field(slide, name, body) = layout(sz => context {
  let pos = here().position()
  let m = measure(width: sz.width, body)
  [#metadata((slide: slide, field: name, page: pos.page,
              x: pos.x.pt(), y: pos.y.pt(), w: m.width.pt(), h: m.height.pt())) <edit>]
  body
})
```

- [ ] **Step 1: Тесты**

```python
from pathlib import Path

from typst_deck.model import Deck
from typst_deck.render import render_typ, typ_str, typ_value

GOLDEN = Path(__file__).parent / "golden" / "full.typ"


def full_deck():
    return Deck(id="deck00000001", title="Полная", slides=[
        {"id": "s000001", "type": "title", "title": "Итоги", "subtitle": "Q3 2026"},
        {"id": "s000002", "type": "section", "title": "Финансы"},
        {"id": "s000003", "type": "image", "title": "Рост", "bullets": ["Первый", "Второй"],
         "image": "a000001.png", "image_size": "large", "caption": "Рис. 1"},
        {"id": "s000004", "type": "bar-chart", "title": "Регионы", "unit": "млн",
         "data": [{"label": "Центр", "value": 42}, {"label": "Север", "value": 17.5}]},
        {"id": "s000005", "type": "chart", "title": "Динамика", "labels": ["Q1", "Q2"],
         "series": [{"name": "Выручка", "values": [1, 2]}], "bullets": ["Рост"]},
        {"id": "s000006", "type": "final", "contact": "team@corp"},
    ])


def test_typ_str_escapes():
    assert typ_str('a"b\\c\nd') == '"a\\"b\\\\c\\nd"'
    assert typ_str("#not *markup* <x>") == '"#not *markup* <x>"'


def test_typ_value():
    assert typ_value(["a"]) == '("a",)'
    assert typ_value([1, 2.5]) == "(1, 2.5,)"
    assert typ_value({"label": "x", "value": 1}) == '(label: "x", value: 1)'
    assert typ_value(True) == "true"


def test_golden():
    typ, warnings = render_typ(full_deck(), assets={"a000001.png"})
    assert warnings == []
    if not GOLDEN.exists():
        GOLDEN.write_text(typ)
    assert typ == GOLDEN.read_text()


def test_missing_image_warns():
    typ, warnings = render_typ(full_deck(), assets=set())
    assert "image: none" in typ
    assert warnings == ["слайд 3: картинка a000001.png не найдена"]


def test_empty_fields_are_none():
    d = Deck(slides=[{"id": "s000001", "type": "title", "title": "Только заголовок"}])
    typ, _ = render_typ(d, assets=set())
    assert "subtitle: none" in typ
    assert 'field("s000001", "title", "Только заголовок")' in typ


def test_one_call_per_slide():
    typ, _ = render_typ(full_deck(), assets={"a000001.png"})
    assert typ.count("\n#slide-") == 6
```

- [ ] **Step 2: Прогнать — падает**

- [ ] **Step 3: Реализация `render.py` (часть 1)**

```python
"""Порождение deck.typ из модели и компиляция через typst."""
from __future__ import annotations

from pathlib import Path

from .model import BarChartSlide, ChartSlide, Deck, FinalSlide, ImageSlide, SectionSlide, TitleSlide

HEADER = '#import "/template/deck.typ": *\n#import "/fields.typ": field\n'


def typ_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def typ_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return typ_str(v)
    if isinstance(v, (list, tuple)):
        return "(" + ", ".join(typ_value(x) for x in v) + ",)" if v else "()"
    if isinstance(v, dict):
        return "(" + ", ".join(f"{k}: {typ_value(x)}" for k, x in v.items()) + ")"
    raise TypeError(type(v))


def _text(slide_id: str, name: str, value: str) -> str:
    return "none" if not value else f'field({typ_str(slide_id)}, {typ_str(name)}, {typ_str(value)})'


def _bullets(slide_id: str, items: list[str]) -> str:
    if not items:
        return "none"
    return f'field({typ_str(slide_id)}, "bullets", list({", ".join(typ_str(i) for i in items)}))'


def render_typ(deck: Deck, assets: set[str]) -> tuple[str, list[str]]:
    """Возвращает текст deck.typ и предупреждения (например, о пропавших картинках)."""
    out = [HEADER, f"#show: deck.with(title: {typ_str(deck.title)})\n"]
    warnings: list[str] = []
    for n, s in enumerate(deck.slides, 1):
        sid = s.id
        if isinstance(s, TitleSlide):
            out.append(f"#slide-title(title: {_text(sid, 'title', s.title)}, subtitle: {_text(sid, 'subtitle', s.subtitle)})\n")
        elif isinstance(s, SectionSlide):
            out.append(f"#slide-section(title: {_text(sid, 'title', s.title)}, subtitle: {_text(sid, 'subtitle', s.subtitle)})\n")
        elif isinstance(s, ImageSlide):
            img = "none"
            if s.image:
                if s.image in assets:
                    img = f'field({typ_str(sid)}, "image", image({typ_str("/assets/" + s.image)}))'
                else:
                    warnings.append(f"слайд {n}: картинка {s.image} не найдена")
            out.append(
                f"#slide-image(title: {_text(sid, 'title', s.title)}, bullets: {_bullets(sid, s.bullets)}, "
                f"image: {img}, image-size: {typ_str(s.image_size)}, caption: {_text(sid, 'caption', s.caption)})\n"
            )
        elif isinstance(s, BarChartSlide):
            data = typ_value([i.model_dump() for i in s.data])
            out.append(
                f"#slide-bar-chart(title: {_text(sid, 'title', s.title)}, data: {data}, "
                f"unit: {typ_str(s.unit) if s.unit else 'none'}, bullets: {_bullets(sid, s.bullets)})\n"
            )
        elif isinstance(s, ChartSlide):
            out.append(
                f"#slide-chart(title: {_text(sid, 'title', s.title)}, labels: {typ_value(s.labels)}, "
                f"series: {typ_value([x.model_dump() for x in s.series])}, "
                f"unit: {typ_str(s.unit) if s.unit else 'none'}, bullets: {_bullets(sid, s.bullets)})\n"
            )
        elif isinstance(s, FinalSlide):
            out.append(f"#slide-final(title: {_text(sid, 'title', s.title)}, contact: {_text(sid, 'contact', s.contact)})\n")
        else:  # pragma: no cover
            raise TypeError(type(s))
    return "".join(out), warnings
```

- [ ] **Step 4: Прогнать — первый прогон создаёт golden; проверить его глазами; повторный прогон проходит. Коммит** `Рендер deck.typ из модели`

---

### Task 4: Заглушка шаблона и компиляция

**Files:**
- Create: `template/deck.typ`, `tests/test_compile.py`
- Modify: `src/typst_deck/render.py` (добавить `CompileResult`, `CompileError`, `compile_deck`), `tests/conftest.py`

**Interfaces:**
- Produces: `compile_deck(deck: Deck, deck_dir: Path, template_dir: Path, typst_bin: str = "typst", timeout: int = 60) -> CompileResult`; `CompileResult(pdf: Path, svgs: list[Path], positions: list[dict], warnings: list[str], typ: str)`; `CompileError(Exception)` с атрибутом `stderr: str`. Ассеты берутся из `deck_dir / "assets"`. Результат в `deck_dir / "build"`: `deck.typ`, `deck.pdf`, `slide-1.svg…`, `positions.json`, `warnings.json`.

- [ ] **Step 1: Заглушка шаблона** — `template/deck.typ` реализует все семь функций контракта простыми средствами: страница 16:9 (`width: 16cm, height: 9cm`), нейтральный шрифт, цветная полоса сверху, бар-чарт из `rect` в `grid`, линейный график через `curve`/`line` в `box` с фиксированной высотой. Каждая функция слайда — `page[...]`. `deck(title, body)` делает `set page(...)`, `set text(...)` и `set document(title: title)`. Пример bar-chart:

```typst
#let slide-bar-chart(title: none, data: (), unit: none, bullets: none) = page[
  #heading-block(title)
  #let maxv = calc.max(..data.map(d => d.value), 1)
  #box(height: 4.5cm, width: 100%)[
    #grid(columns: data.len(), column-gutter: 0.4cm, align: bottom + center,
      ..data.map(d => stack(dir: btt, spacing: 2pt,
        text(size: 9pt, d.label),
        rect(width: 100%, height: 4cm * d.value / maxv, fill: rgb("#3b6ea5")),
        text(size: 8pt, str(d.value) + if unit != none { " " + unit } else { "" }))))
  ]
  #if bullets != none { bullets }
]
```

- [ ] **Step 2: Тесты**

`tests/conftest.py`:

```python
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "template"
HAS_TYPST = shutil.which("typst") is not None
requires_typst = pytest.mark.skipif(not HAS_TYPST, reason="typst не установлен")


@pytest.fixture
def deck_dir(tmp_path: Path) -> Path:
    d = tmp_path / "deck"
    (d / "assets").mkdir(parents=True)
    return d


@pytest.fixture
def png_bytes() -> bytes:
    import base64
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )
```

`tests/test_compile.py`:

```python
import json

import pytest

from tests.conftest import TEMPLATE_DIR, requires_typst
from tests.test_render import full_deck
from typst_deck.render import CompileError, compile_deck

pytestmark = requires_typst


def test_compile_full_deck(deck_dir, png_bytes):
    (deck_dir / "assets" / "a000001.png").write_bytes(png_bytes)
    r = compile_deck(full_deck(), deck_dir, TEMPLATE_DIR)
    assert r.pdf.exists() and len(r.svgs) == 6
    assert r.warnings == []
    fields = {(p["slide"], p["field"]) for p in r.positions}
    assert ("s000001", "title") in fields and ("s000003", "bullets") in fields
    assert ("s000003", "image") in fields and ("s000006", "contact") in fields
    p = next(p for p in r.positions if p["slide"] == "s000003" and p["field"] == "title")
    assert p["page"] == 3 and p["w"] > 0 and p["h"] > 0
    assert json.loads((deck_dir / "build" / "positions.json").read_text()) == r.positions
    assert (deck_dir / "build" / "template").is_symlink()


def test_compile_missing_image_is_warning(deck_dir):
    r = compile_deck(full_deck(), deck_dir, TEMPLATE_DIR)
    assert len(r.svgs) == 6 and r.warnings


def test_compile_replaces_previous_build(deck_dir):
    from typst_deck.model import Deck
    compile_deck(full_deck(), deck_dir, TEMPLATE_DIR)
    r = compile_deck(Deck(slides=[{"type": "final"}]), deck_dir, TEMPLATE_DIR)
    assert len(r.svgs) == 1
    assert not (deck_dir / "build" / "slide-2.svg").exists()
    assert not (deck_dir / "build.tmp").exists()


def test_compile_error_surfaces_stderr(deck_dir, tmp_path):
    bad_tpl = tmp_path / "tpl"
    bad_tpl.mkdir()
    (bad_tpl / "deck.typ").write_text("#let deck(title: none, body) = body\n")
    with pytest.raises(CompileError) as e:
        compile_deck(full_deck(), deck_dir, bad_tpl)
    assert "slide-title" in e.value.stderr
```

- [ ] **Step 3: Прогнать — падает**

- [ ] **Step 4: Реализация `compile_deck`** (дописать в `render.py`)

```python
import json, os, shutil, subprocess
from dataclasses import dataclass, field

FIELDS_TYP = Path(__file__).parent / "typst" / "fields.typ"


class CompileError(Exception):
    def __init__(self, message: str, stderr: str = ""):
        super().__init__(message)
        self.stderr = stderr


@dataclass
class CompileResult:
    pdf: Path
    svgs: list[Path]
    positions: list[dict]
    warnings: list[str] = field(default_factory=list)
    typ: str = ""


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as e:
        raise CompileError(f"typst не найден: {cmd[0]}") from e
    except subprocess.TimeoutExpired as e:
        raise CompileError(f"typst не уложился в {timeout} с") from e


def compile_deck(deck: Deck, deck_dir: Path, template_dir: Path, typst_bin: str = "typst", timeout: int = 60) -> CompileResult:
    assets_dir = deck_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    assets = {p.name for p in assets_dir.iterdir() if p.is_file()}
    typ, warnings = render_typ(deck, assets)

    tmp = deck_dir / "build.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    os.symlink(template_dir.resolve(), tmp / "template")
    os.symlink(assets_dir.resolve(), tmp / "assets")
    shutil.copy(FIELDS_TYP, tmp / "fields.typ")
    (tmp / "deck.typ").write_text(typ)

    base = [typst_bin]
    fonts = template_dir / "fonts"
    font_args = ["--font-path", str(fonts)] if fonts.is_dir() else []
    src = str(tmp / "deck.typ")
    for target in ["deck.pdf", "slide-{p}.svg"]:
        r = _run(base + ["compile", "--root", str(tmp), *font_args, src, str(tmp / target)], timeout)
        if r.returncode != 0:
            raise CompileError("ошибка компиляции", r.stderr)
    svgs = sorted(tmp.glob("slide-*.svg"), key=lambda p: int(p.stem.split("-")[1]))
    if len(svgs) != len(deck.slides):
        raise CompileError(f"страниц {len(svgs)}, слайдов {len(deck.slides)}: шаблон нарушает контракт «одна функция — одна страница»")
    r = _run(base + ["eval", "query(<edit>).map(it => it.value)", "--root", str(tmp), *font_args, "--in", src, "--format", "json"], timeout)
    if r.returncode != 0:
        raise CompileError("ошибка запроса позиций", r.stderr)
    positions = json.loads(r.stdout)
    (tmp / "positions.json").write_text(json.dumps(positions, ensure_ascii=False))
    (tmp / "warnings.json").write_text(json.dumps(warnings, ensure_ascii=False))

    build = deck_dir / "build"
    old = deck_dir / "build.old"
    shutil.rmtree(old, ignore_errors=True)
    if build.exists():
        os.rename(build, old)
    os.rename(tmp, build)
    shutil.rmtree(old, ignore_errors=True)
    return CompileResult(
        pdf=build / "deck.pdf",
        svgs=[build / p.name for p in svgs],
        positions=positions, warnings=warnings, typ=typ,
    )
```

- [ ] **Step 5: Прогнать; открыть `deck.pdf` глазами (конвертировать первую страницу в PNG через `typst compile --format png` и посмотреть). Коммит** `Заглушка шаблона и компиляция колоды`

---

### Task 5: Хранилище

**Files:**
- Create: `src/typst_deck/store.py`, `tests/test_store.py`

**Interfaces:**
- Produces: `DeckStore(data_dir: Path)` с методами `deck_dir(deck_id) -> Path`, `create(deck: Deck) -> Deck`, `load(deck_id) -> Deck`, `exists(deck_id) -> bool`, `save(deck: Deck) -> Deck` (version += 1, снимок), `list_versions(deck_id) -> list[int]`, `load_version(deck_id, version) -> Deck`, `revert(deck_id, version) -> Deck`, `add_asset(deck_id, filename, data) -> str`, `asset_path(deck_id, asset_id) -> Path`, `add_upload(deck_id, name, data, text: str | None) -> Path`, `list_uploads(deck_id) -> list[tuple[str, str]]` (имя, текст), `append_chat(deck_id, entry: dict)`, `read_chat(deck_id) -> list[dict]`, `stage_upload(name, data, text) -> str`, `take_upload(upload_id) -> tuple[str, bytes, str | None]`, `lock(deck_id) -> asyncio.Lock`. Ошибки: `DeckNotFound(KeyError)`, `ValueError` для запрещённого расширения ассета.

- [ ] **Step 1: Тесты**

```python
import json

import pytest

from typst_deck.model import Deck
from typst_deck.store import DeckNotFound, DeckStore


@pytest.fixture
def store(tmp_path):
    return DeckStore(tmp_path / "data")


def test_create_load(store):
    d = store.create(Deck(title="A", slides=[{"type": "final"}]))
    assert d.version == 1
    assert store.load(d.id).title == "A"
    assert store.list_versions(d.id) == [1]
    with pytest.raises(DeckNotFound):
        store.load("nope")


def test_save_bumps_version_and_snapshots(store):
    d = store.create(Deck(slides=[{"type": "final"}]))
    d.title = "B"
    d = store.save(d)
    assert d.version == 2 and store.list_versions(d.id) == [1, 2]
    assert store.load_version(d.id, 1).title == "Презентация"
    assert d.updated_at > d.created_at


def test_revert_creates_new_version(store):
    d = store.create(Deck(title="v1", slides=[{"type": "final"}]))
    d.title = "v2"
    store.save(d)
    r = store.revert(d.id, 1)
    assert r.title == "v1" and r.version == 3
    assert store.load(d.id).title == "v1"


def test_assets(store, png_bytes):
    d = store.create(Deck())
    aid = store.add_asset(d.id, "Фото.PNG", png_bytes)
    assert aid.startswith("a") and aid.endswith(".png") and len(aid) == 11
    assert store.asset_path(d.id, aid).read_bytes() == png_bytes
    with pytest.raises(ValueError):
        store.add_asset(d.id, "x.exe", b"MZ")


def test_uploads_and_chat(store):
    d = store.create(Deck())
    store.add_upload(d.id, "brief.txt", b"hello", "hello")
    assert store.list_uploads(d.id) == [("brief.txt", "hello")]
    store.append_chat(d.id, {"role": "user", "content": "привет"})
    store.append_chat(d.id, {"role": "assistant", "content": "готово"})
    assert [m["role"] for m in store.read_chat(d.id)] == ["user", "assistant"]


def test_staged_uploads(store):
    uid = store.stage_upload("a.txt", b"x", "x")
    assert store.take_upload(uid) == ("a.txt", b"x", "x")
    with pytest.raises(KeyError):
        store.take_upload("nope")


def test_atomic_write_leaves_no_tmp(store):
    d = store.create(Deck())
    files = {p.name for p in store.deck_dir(d.id).iterdir()}
    assert "deck.json" in files and not any(n.endswith(".tmp") for n in files)


def test_lock_is_per_deck(store):
    assert store.lock("a") is store.lock("a") and store.lock("a") is not store.lock("b")
```

- [ ] **Step 2: Прогнать — падает**

- [ ] **Step 3: Реализация**

```python
"""Колоды на диске: deck.json, версии, ассеты, загрузки, чат."""
from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from pathlib import Path

from .model import Deck, new_id, utcnow

ASSET_EXT = {".png", ".jpg", ".jpeg", ".svg"}
SAFE_NAME = re.compile(r"[^\w.\- ]", re.UNICODE)


class DeckNotFound(KeyError):
    pass


def write_atomic(path: Path, data: str | bytes) -> None:
    mode = "wb" if isinstance(data, bytes) else "w"
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, mode) as f:
            f.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def safe_name(name: str) -> str:
    return SAFE_NAME.sub("_", Path(name).name) or "file"


class DeckStore:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self._locks: dict[str, asyncio.Lock] = {}

    # --- пути
    def deck_dir(self, deck_id: str) -> Path:
        return self.data_dir / "decks" / deck_id

    def exists(self, deck_id: str) -> bool:
        return (self.deck_dir(deck_id) / "deck.json").exists()

    def lock(self, deck_id: str) -> asyncio.Lock:
        return self._locks.setdefault(deck_id, asyncio.Lock())

    # --- колода и версии
    def create(self, deck: Deck) -> Deck:
        d = self.deck_dir(deck.id)
        for sub in ("versions", "assets", "uploads"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        return self.save(deck)

    def load(self, deck_id: str) -> Deck:
        p = self.deck_dir(deck_id) / "deck.json"
        if not p.exists():
            raise DeckNotFound(deck_id)
        return Deck.model_validate_json(p.read_text())

    def save(self, deck: Deck) -> Deck:
        deck.version += 1
        deck.updated_at = utcnow()
        data = deck.model_dump_json(indent=2)
        d = self.deck_dir(deck.id)
        write_atomic(d / "versions" / f"{deck.version:06d}.json", data)
        write_atomic(d / "deck.json", data)
        return deck

    def list_versions(self, deck_id: str) -> list[int]:
        return sorted(int(p.stem) for p in (self.deck_dir(deck_id) / "versions").glob("*.json"))

    def load_version(self, deck_id: str, version: int) -> Deck:
        p = self.deck_dir(deck_id) / "versions" / f"{version:06d}.json"
        if not p.exists():
            raise DeckNotFound(f"{deck_id}@{version}")
        return Deck.model_validate_json(p.read_text())

    def revert(self, deck_id: str, version: int) -> Deck:
        old = self.load_version(deck_id, version)
        cur = self.load(deck_id)
        cur.title, cur.slides = old.title, old.slides
        return self.save(cur)

    # --- ассеты
    def add_asset(self, deck_id: str, filename: str, data: bytes) -> str:
        ext = Path(filename).suffix.lower()
        if ext == ".jpeg":
            ext = ".jpg"
        if ext not in ASSET_EXT:
            raise ValueError(f"недопустимое расширение картинки: {ext or '(нет)'}")
        aid = new_id("a") + ext
        write_atomic(self.deck_dir(deck_id) / "assets" / aid, data)
        return aid

    def asset_path(self, deck_id: str, asset_id: str) -> Path:
        return self.deck_dir(deck_id) / "assets" / asset_id

    def assets(self, deck_id: str) -> list[str]:
        return sorted(p.name for p in (self.deck_dir(deck_id) / "assets").iterdir() if p.is_file())

    # --- загрузки
    def add_upload(self, deck_id: str, name: str, data: bytes, text: str | None) -> Path:
        p = self.deck_dir(deck_id) / "uploads" / safe_name(name)
        write_atomic(p, data)
        if text is not None:
            write_atomic(p.with_name(p.name + ".txt"), text)
        return p

    def list_uploads(self, deck_id: str) -> list[tuple[str, str]]:
        d = self.deck_dir(deck_id) / "uploads"
        return [(p.name[:-4], p.read_text()) for p in sorted(d.glob("*.txt"))]

    def stage_upload(self, name: str, data: bytes, text: str | None) -> str:
        uid = new_id("u", 10)
        d = self.data_dir / "uploads" / uid
        d.mkdir(parents=True)
        write_atomic(d / "meta.json", json.dumps({"name": name}))
        write_atomic(d / "data", data)
        if text is not None:
            write_atomic(d / "text.txt", text)
        return uid

    def take_upload(self, upload_id: str) -> tuple[str, bytes, str | None]:
        d = self.data_dir / "uploads" / upload_id
        if not d.is_dir():
            raise KeyError(upload_id)
        name = json.loads((d / "meta.json").read_text())["name"]
        text = (d / "text.txt").read_text() if (d / "text.txt").exists() else None
        return name, (d / "data").read_bytes(), text

    # --- чат
    def append_chat(self, deck_id: str, entry: dict) -> None:
        with open(self.deck_dir(deck_id) / "chat.jsonl", "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def read_chat(self, deck_id: str) -> list[dict]:
        p = self.deck_dir(deck_id) / "chat.jsonl"
        if not p.exists():
            return []
        return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
```

- [ ] **Step 4: Прогнать; коммит** `Хранилище колод: версии, ассеты, загрузки, чат`

---

### Task 6: Извлечение текста из файлов

**Files:**
- Create: `src/typst_deck/extract.py`, `tests/test_extract.py`

**Interfaces:**
- Produces: `Extracted(kind: Literal["text", "image"], text: str = "", truncated: bool = False)`, `extract(name: str, data: bytes, limit: int = 60_000) -> Extracted`, `UnsupportedFile(ValueError)`.

- [ ] **Step 1: Тесты**

```python
import io

import pytest

from typst_deck.extract import UnsupportedFile, extract


def test_txt_md_csv():
    assert extract("a.txt", "привет".encode()).text == "привет"
    assert extract("a.md", b"# H").text == "# H"
    t = extract("a.csv", "a,b\n1,2\n".encode()).text
    assert "| a | b |" in t and "| 1 | 2 |" in t


def test_docx():
    import docx
    d = docx.Document()
    d.add_paragraph("Первый абзац")
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "к1", "к2"
    buf = io.BytesIO(); d.save(buf)
    out = extract("doc.docx", buf.getvalue()).text
    assert "Первый абзац" in out and "| к1 | к2 |" in out


def test_xlsx_limits_rows():
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Лист"
    for i in range(300):
        ws.append([i, i * 2])
    buf = io.BytesIO(); wb.save(buf)
    out = extract("t.xlsx", buf.getvalue()).text
    assert "## Лист" in out and "| 199 | 398 |" in out and "| 250 |" not in out


def test_truncate():
    e = extract("a.txt", b"x" * 100, limit=10)
    assert e.truncated and len(e.text) < 100 and "усечено" in e.text


def test_images_and_unknown(png_bytes):
    assert extract("p.png", png_bytes).kind == "image"
    with pytest.raises(UnsupportedFile):
        extract("x.exe", b"MZ")
```

- [ ] **Step 2: Прогнать — падает**

- [ ] **Step 3: Реализация**

```python
"""Текст из загруженных файлов для контекста LLM."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".svg"}
MAX_ROWS = 200


class UnsupportedFile(ValueError):
    pass


@dataclass
class Extracted:
    kind: Literal["text", "image"]
    text: str = ""
    truncated: bool = False


def _md_table(rows: list[list[str]]) -> str:
    rows = [[str(c) if c is not None else "" for c in r] for r in rows]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(lines)


def _docx(data: bytes) -> str:
    import docx
    d = docx.Document(io.BytesIO(data))
    parts = [p.text for p in d.paragraphs if p.text.strip()]
    for t in d.tables:
        parts.append(_md_table([[c.text for c in r.cells] for r in t.rows]))
    return "\n\n".join(parts)


def _xlsx(data: bytes) -> str:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    parts = []
    for ws in wb.worksheets:
        rows = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= MAX_ROWS:
                rows.append(["…"])
                break
            rows.append(list(row))
        parts.append(f"## {ws.title}\n\n{_md_table(rows)}")
    return "\n\n".join(parts)


def _csv(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    return _md_table(list(csv.reader(io.StringIO(text)))[: MAX_ROWS + 1])


def extract(name: str, data: bytes, limit: int = 60_000) -> Extracted:
    ext = Path(name).suffix.lower()
    if ext in IMAGE_EXT:
        return Extracted("image")
    if ext in (".txt", ".md"):
        text = data.decode("utf-8", errors="replace")
    elif ext == ".docx":
        text = _docx(data)
    elif ext == ".xlsx":
        text = _xlsx(data)
    elif ext == ".csv":
        text = _csv(data)
    else:
        raise UnsupportedFile(f"формат {ext or '(без расширения)'} не поддерживается")
    truncated = len(text) > limit
    if truncated:
        text = text[:limit] + "\n\n[… усечено: файл длиннее лимита]"
    return Extracted("text", text, truncated)
```

- [ ] **Step 4: Прогнать; коммит** `Извлечение текста из docx, xlsx, csv, txt`

---

### Task 7: Клиент LLM

**Files:**
- Create: `src/typst_deck/llm/__init__.py`, `src/typst_deck/llm/client.py`, `tests/test_llm_client.py`

**Interfaces:**
- Produces: `ToolCall(id: str, name: str, arguments: dict)`, `Completion(text: str, tool_calls: list[ToolCall])`, протокол `LLM` с `async complete(messages: list[dict], tools: list[dict]) -> Completion`, `FakeLLM(completions: list[Completion])` с полем `calls: list[list[dict]]`, `OpenAICompatLLM(base_url, api_key, model, max_tokens=4096, tool_mode="tools", timeout=120)`, `LLMError(Exception)`.
- Формат сообщений — OpenAI chat: `system/user/assistant/tool`; вызовы инструментов в `assistant` как `tool_calls: [{id, type: "function", function: {name, arguments: <json str>}}]`, результаты как `{"role": "tool", "tool_call_id", "content"}`.
- Режим `json`: инструменты описываются в дополнительном системном сообщении; ответ модели должен быть JSON `{"tool": name, "args": {...}}` либо `{"reply": "текст"}`; `assistant`-сообщения с `tool_calls` и `tool`-сообщения переписываются в текст (`assistant`: JSON вызова; `tool` → `user` с префиксом `Результат <name>:`), ответ извлекается из первого `{…}` в тексте.

- [ ] **Step 1: Тесты** (`respx` перехватывает httpx)

```python
import json

import httpx
import pytest
import respx

from typst_deck.llm.client import Completion, FakeLLM, LLMError, OpenAICompatLLM, ToolCall

TOOLS = [{"type": "function", "function": {"name": "finish", "parameters": {"type": "object", "properties": {"summary": {"type": "string"}}}}}]


async def test_fake_llm_records_and_replays():
    llm = FakeLLM([Completion("a", []), Completion("b", [])])
    assert (await llm.complete([{"role": "user", "content": "x"}], [])).text == "a"
    assert (await llm.complete([], [])).text == "b"
    assert llm.calls[0][0]["content"] == "x"
    with pytest.raises(LLMError):
        await llm.complete([], [])


@respx.mock
async def test_tools_mode_parses_tool_calls():
    route = respx.post("https://llm.test/v1/chat/completions").mock(return_value=httpx.Response(200, json={
        "choices": [{"message": {"content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "finish", "arguments": "{\"summary\": \"ok\"}"}}]}}]}))
    llm = OpenAICompatLLM("https://llm.test/v1", "k", "m")
    c = await llm.complete([{"role": "user", "content": "hi"}], TOOLS)
    assert c.text == "" and c.tool_calls == [ToolCall("c1", "finish", {"summary": "ok"})]
    body = json.loads(route.calls[0].request.content)
    assert body["model"] == "m" and body["tools"] == TOOLS and body["messages"][0]["content"] == "hi"
    assert route.calls[0].request.headers["authorization"] == "Bearer k"


@respx.mock
async def test_json_mode_rewrites_messages_and_parses():
    route = respx.post("https://llm.test/v1/chat/completions").mock(return_value=httpx.Response(200, json={
        "choices": [{"message": {"content": "Вот: {\"tool\": \"finish\", \"args\": {\"summary\": \"ok\"}}"}}]}))
    llm = OpenAICompatLLM("https://llm.test/v1", "k", "m", tool_mode="json")
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c0", "type": "function", "function": {"name": "finish", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c0", "content": "done"},
    ]
    c = await llm.complete(msgs, TOOLS)
    assert c.tool_calls[0].name == "finish" and c.tool_calls[0].arguments == {"summary": "ok"}
    body = json.loads(route.calls[0].request.content)
    assert "tools" not in body
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["system", "system", "assistant", "user"]
    assert "finish" in body["messages"][1]["content"]
    assert body["messages"][3]["content"].startswith("Результат finish:")


@respx.mock
async def test_json_mode_reply():
    respx.post("https://llm.test/v1/chat/completions").mock(return_value=httpx.Response(200, json={
        "choices": [{"message": {"content": "{\"reply\": \"готово\"}"}}]}))
    llm = OpenAICompatLLM("https://llm.test/v1", "k", "m", tool_mode="json")
    c = await llm.complete([{"role": "user", "content": "x"}], TOOLS)
    assert c.text == "готово" and c.tool_calls == []


@respx.mock
async def test_http_error():
    respx.post("https://llm.test/v1/chat/completions").mock(return_value=httpx.Response(500, text="boom"))
    llm = OpenAICompatLLM("https://llm.test/v1", "k", "m")
    with pytest.raises(LLMError):
        await llm.complete([{"role": "user", "content": "x"}], TOOLS)
```

- [ ] **Step 2: Прогнать — падает**

- [ ] **Step 3: Реализация**

```python
"""Клиент к OpenAI-совместимому chat completions API и заглушка для тестов."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Protocol

import httpx


class LLMError(Exception):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Completion:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLM(Protocol):
    async def complete(self, messages: list[dict], tools: list[dict]) -> Completion: ...


class FakeLLM:
    """Отдаёт заранее заготовленные ответы по очереди и запоминает входящие сообщения."""

    def __init__(self, completions: list[Completion]):
        self._queue = list(completions)
        self.calls: list[list[dict]] = []

    async def complete(self, messages: list[dict], tools: list[dict]) -> Completion:
        self.calls.append(messages)
        if not self._queue:
            raise LLMError("FakeLLM: ответы закончились")
        return self._queue.pop(0)


JSON_MODE_HINT = (
    "Инструменты недоступны напрямую. Отвечай ТОЛЬКО одним JSON-объектом без пояснений: "
    '{"tool": "<имя>", "args": {...}} чтобы вызвать инструмент, или {"reply": "<текст>"} чтобы ответить. '
    "Доступные инструменты (JSON Schema):\n"
)


class OpenAICompatLLM:
    def __init__(self, base_url: str, api_key: str, model: str, max_tokens: int = 4096,
                 tool_mode: str = "tools", timeout: float = 120, client: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.tool_mode = tool_mode
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def complete(self, messages: list[dict], tools: list[dict]) -> Completion:
        body: dict = {"model": self.model, "max_tokens": self.max_tokens}
        if self.tool_mode == "json":
            body["messages"] = self._rewrite_for_json(messages, tools)
        else:
            body["messages"] = messages
            if tools:
                body["tools"] = tools
        try:
            r = await self._client.post(f"{self.base_url}/chat/completions", json=body,
                                        headers={"Authorization": f"Bearer {self.api_key}"})
        except httpx.HTTPError as e:
            raise LLMError(f"LLM недоступна: {e}") from e
        if r.status_code != 200:
            raise LLMError(f"LLM вернула {r.status_code}: {r.text[:500]}")
        msg = r.json()["choices"][0]["message"]
        if self.tool_mode == "json":
            return self._parse_json_mode(msg.get("content") or "")
        calls = [ToolCall(tc["id"], tc["function"]["name"], _args(tc["function"].get("arguments")))
                 for tc in msg.get("tool_calls") or []]
        return Completion(msg.get("content") or "", calls)

    @staticmethod
    def _rewrite_for_json(messages: list[dict], tools: list[dict]) -> list[dict]:
        out: list[dict] = []
        names = {}
        for m in messages:
            if m["role"] == "assistant" and m.get("tool_calls"):
                parts = []
                for tc in m["tool_calls"]:
                    names[tc["id"]] = tc["function"]["name"]
                    parts.append(json.dumps({"tool": tc["function"]["name"], "args": _args(tc["function"].get("arguments"))}, ensure_ascii=False))
                out.append({"role": "assistant", "content": "\n".join(parts)})
            elif m["role"] == "tool":
                out.append({"role": "user", "content": f"Результат {names.get(m.get('tool_call_id'), '?')}: {m['content']}"})
            else:
                out.append(m)
        hint = {"role": "system", "content": JSON_MODE_HINT + json.dumps(tools, ensure_ascii=False)}
        idx = 1 if out and out[0]["role"] == "system" else 0
        out.insert(idx, hint)
        return out

    @staticmethod
    def _parse_json_mode(text: str) -> Completion:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return Completion(text.strip(), [])
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            return Completion(text.strip(), [])
        if "tool" in obj:
            return Completion("", [ToolCall("json-1", obj["tool"], obj.get("args") or {})])
        return Completion(str(obj.get("reply", "")), [])


def _args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise LLMError(f"аргументы инструмента не JSON: {raw[:200]}") from e
```

- [ ] **Step 4: Прогнать; коммит** `Клиент LLM: tool calling и JSON-режим`

---

### Task 8: Инструменты и цикл агента

**Files:**
- Create: `src/typst_deck/llm/tools.py`, `src/typst_deck/llm/agent.py`, `src/typst_deck/llm/prompt.md`, `tests/test_agent.py`

**Interfaces:**
- Produces: `tool_specs() -> list[dict]` (6 инструментов: `set_deck`, `update_slide`, `add_slide`, `remove_slide`, `move_slide`, `finish`), `ToolExecutor(deck: Deck)` с `call(name: str, args: dict) -> str`, полями `changed: bool`, `ops: list[str]`, `finished: bool`, `summary: str`; `Outcome(reply: str, changed: bool, ops: list[str], deck: Deck)`; `async run_agent(llm: LLM, deck: Deck, user_message: str, files: list[tuple[str, str]], history: list[dict], assets: list[str], max_iter: int = 12) -> Outcome`; `build_system_prompt(deck, assets) -> str`.
- Правила `ToolExecutor.call`: ошибки валидации и неизвестные слайды возвращаются строкой `ERROR: …` (не исключением); успех — `OK: …` с кратким описанием; `set_deck` заменяет заголовок и все слайды; `finish` ставит `finished` и запоминает `summary`.

- [ ] **Step 1: Тесты**

```python
import json

import pytest

from typst_deck.llm.agent import Outcome, build_system_prompt, run_agent
from typst_deck.llm.client import Completion, FakeLLM, ToolCall
from typst_deck.llm.tools import ToolExecutor, tool_specs
from typst_deck.model import Deck


def test_tool_specs_shape():
    specs = tool_specs()
    names = [s["function"]["name"] for s in specs]
    assert names == ["set_deck", "update_slide", "add_slide", "remove_slide", "move_slide", "finish"]
    assert all(s["type"] == "function" and "parameters" in s["function"] for s in specs)
    assert "bar-chart" in json.dumps(specs)


def test_executor_set_and_update():
    ex = ToolExecutor(Deck())
    r = ex.call("set_deck", {"title": "T", "slides": [{"type": "title", "title": "A"}, {"type": "final"}]})
    assert r.startswith("OK") and ex.changed and len(ex.deck.slides) == 2
    sid = ex.deck.slides[0].id
    assert ex.call("update_slide", {"slide_id": sid, "patch": {"title": "B"}}).startswith("OK")
    assert ex.deck.slides[0].title == "B"
    assert ex.call("update_slide", {"slide_id": "s_nope", "patch": {}}).startswith("ERROR")
    assert ex.call("update_slide", {"slide_id": sid, "patch": {"title": "x" * 500}}).startswith("ERROR")
    assert ex.call("nope", {}).startswith("ERROR")
    assert ex.ops[:2] == ["set_deck", f"update_slide {sid}"]


def test_executor_add_remove_move_finish():
    ex = ToolExecutor(Deck(slides=[{"type": "final"}]))
    fid = ex.deck.slides[0].id
    ex.call("add_slide", {"slide": {"type": "section", "title": "S"}, "after": None})
    ex.call("move_slide", {"slide_id": ex.deck.slides[1].id, "to_index": 0})
    assert ex.deck.slides[0].type == "section"
    ex.call("remove_slide", {"slide_id": fid})
    assert len(ex.deck.slides) == 1
    assert ex.call("finish", {"summary": "готово"}) == "OK"
    assert ex.finished and ex.summary == "готово"


def test_system_prompt_mentions_schema_deck_assets():
    d = Deck(title="T", slides=[{"type": "final"}])
    p = build_system_prompt(d, ["a1.png"])
    assert "bar-chart" in p and '"T"' in p and "a1.png" in p and d.slides[0].id in p


async def test_run_agent_create_flow():
    llm = FakeLLM([
        Completion("", [ToolCall("c1", "set_deck", {"title": "T", "slides": [{"type": "title", "title": "A"}]})]),
        Completion("", [ToolCall("c2", "finish", {"summary": "Собрал 1 слайд"})]),
    ])
    out = await run_agent(llm, Deck(), "сделай", files=[("brief.txt", "текст задания")], history=[], assets=[])
    assert isinstance(out, Outcome) and out.changed and out.reply == "Собрал 1 слайд"
    assert out.deck.title == "T" and out.ops == ["set_deck"]
    first = llm.calls[0]
    assert first[0]["role"] == "system" and "brief.txt" in first[-1]["content"] and "текст задания" in first[-1]["content"]
    second = llm.calls[1]
    assert second[-2]["role"] == "assistant" and second[-1]["role"] == "tool" and second[-1]["content"].startswith("OK")


async def test_run_agent_error_feedback_then_fix():
    d = Deck(slides=[{"type": "title", "title": "A"}])
    sid = d.slides[0].id
    llm = FakeLLM([
        Completion("", [ToolCall("c1", "update_slide", {"slide_id": sid, "patch": {"title": "x" * 500}})]),
        Completion("", [ToolCall("c2", "update_slide", {"slide_id": sid, "patch": {"title": "Короткий"}})]),
        Completion("Поправил заголовок", []),
    ])
    out = await run_agent(llm, d, "поправь", files=[], history=[], assets=[])
    assert out.deck.slides[0].title == "Короткий" and out.reply == "Поправил заголовок"
    assert llm.calls[1][-1]["content"].startswith("ERROR")


async def test_run_agent_iteration_limit():
    d = Deck(slides=[{"type": "title", "title": "A"}])
    sid = d.slides[0].id
    llm = FakeLLM([Completion("", [ToolCall(f"c{i}", "update_slide", {"slide_id": sid, "patch": {"title": f"T{i}"}})]) for i in range(3)])
    out = await run_agent(llm, d, "x", files=[], history=[], assets=[], max_iter=2)
    assert out.deck.slides[0].title == "T1" and "лимит" in out.reply.lower()


async def test_run_agent_uses_history():
    llm = FakeLLM([Completion("ок", [])])
    await run_agent(llm, Deck(), "ещё", files=[], history=[{"role": "user", "content": "раньше"}, {"role": "assistant", "content": "ответ"}], assets=[])
    roles = [m["role"] for m in llm.calls[0]]
    assert roles == ["system", "user", "assistant", "user"]
```

- [ ] **Step 2: Прогнать — падает**

- [ ] **Step 3: Реализация `tools.py`**

```python
"""Инструменты, которыми LLM правит колоду. Каждый вызов — валидируемый патч."""
from __future__ import annotations

from pydantic import ValidationError

from ..model import Deck, SlideAdapter, slide_schema


def _fn(name: str, description: str, params: dict) -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": params}}


def tool_specs() -> list[dict]:
    schema = slide_schema()
    defs = schema.pop("$defs", {})
    slide_ref = {"$ref": "#/$defs/Slide"}
    defs["Slide"] = schema
    obj = lambda props, required: {"type": "object", "properties": props, "required": required, "$defs": defs}
    return [
        _fn("set_deck", "Полностью задать презентацию: название и все слайды по порядку. Использовать при создании с нуля.",
            obj({"title": {"type": "string"}, "slides": {"type": "array", "items": slide_ref}}, ["title", "slides"])),
        _fn("update_slide", "Изменить отдельные поля существующего слайда. В patch только меняемые поля; type и id менять нельзя.",
            obj({"slide_id": {"type": "string"}, "patch": {"type": "object"}}, ["slide_id", "patch"])),
        _fn("add_slide", "Добавить слайд после слайда after (null — в конец).",
            obj({"slide": slide_ref, "after": {"type": ["string", "null"]}}, ["slide"])),
        _fn("remove_slide", "Удалить слайд.", obj({"slide_id": {"type": "string"}}, ["slide_id"])),
        _fn("move_slide", "Переставить слайд на позицию to_index (с нуля).",
            obj({"slide_id": {"type": "string"}, "to_index": {"type": "integer"}}, ["slide_id", "to_index"])),
        _fn("finish", "Завершить работу и кратко сказать пользователю, что сделано.",
            obj({"summary": {"type": "string"}}, ["summary"])),
    ]


def _fmt_validation(e: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors())


class ToolExecutor:
    def __init__(self, deck: Deck):
        self.deck = deck
        self.changed = False
        self.ops: list[str] = []
        self.finished = False
        self.summary = ""

    def call(self, name: str, args: dict) -> str:
        try:
            handler = getattr(self, f"_{name}")
        except AttributeError:
            return f"ERROR: неизвестный инструмент {name}"
        try:
            result = handler(**args)
        except TypeError as e:
            return f"ERROR: неверные аргументы: {e}"
        except ValidationError as e:
            return f"ERROR: {_fmt_validation(e)}"
        except (KeyError, ValueError) as e:
            return f"ERROR: {e}"
        return result

    def _set_deck(self, title: str, slides: list[dict]) -> str:
        new = Deck(id=self.deck.id, title=title, slides=slides, version=self.deck.version, created_at=self.deck.created_at)
        self.deck.title, self.deck.slides = new.title, new.slides
        self._done("set_deck")
        return f"OK: {len(self.deck.slides)} слайдов; id: " + ", ".join(f"{i+1}={s.id}" for i, s in enumerate(self.deck.slides))

    def _update_slide(self, slide_id: str, patch: dict) -> str:
        self.deck.apply_patch(slide_id, patch)
        self._done(f"update_slide {slide_id}")
        return f"OK: слайд {slide_id} обновлён"

    def _add_slide(self, slide: dict, after: str | None = None) -> str:
        s = self.deck.add_slide(slide, after)
        self._done(f"add_slide {s.id}")
        return f"OK: добавлен слайд {s.id} на позицию {self.deck.index_of(s.id) + 1}"

    def _remove_slide(self, slide_id: str) -> str:
        self.deck.remove_slide(slide_id)
        self._done(f"remove_slide {slide_id}")
        return f"OK: слайд {slide_id} удалён"

    def _move_slide(self, slide_id: str, to_index: int) -> str:
        self.deck.move_slide(slide_id, to_index)
        self._done(f"move_slide {slide_id}")
        return f"OK: слайд {slide_id} теперь на позиции {self.deck.index_of(slide_id) + 1}"

    def _finish(self, summary: str = "") -> str:
        self.finished, self.summary = True, summary
        return "OK"

    def _done(self, op: str) -> None:
        self.changed = True
        self.ops.append(op)
```

- [ ] **Step 4: `prompt.md`** — системный промпт с плейсхолдерами `{{SCHEMA}}`, `{{DECK_JSON}}`, `{{ASSETS}}`:

```
Ты собираешь корпоративные презентации. Ты не пишешь код и не оформляешь
слайды: внешний вид задаёт шаблон. Ты заполняешь структуру через инструменты.

Правила:
- Работай только инструментами. Создание с нуля — один вызов set_deck.
  Правка — update_slide с минимальным patch. Закончив, вызови finish с
  коротким итогом для пользователя (1–2 предложения, по-русски).
- Заголовки до 120 символов, буллеты до 200 — тезисы, не абзацы.
  На слайде image не больше 6 буллетов, на графиках не больше 4.
- Структура типичной презентации: title → section/image/графики → final.
  Раздели длинный материал на разделы (section).
- Данные для bar-chart и chart бери из файлов пользователя; не выдумывай
  числа. Если данных нет — сделай слайд image с тезисами.
- Картинки: только из списка доступных ассетов; если подходящих нет,
  оставь image = null.
- Если инструмент вернул ERROR, исправь и повтори.
- Если просьба непонятна, всё равно сделай разумный вариант и скажи об
  этом в finish.

Схема слайда (JSON Schema):
{{SCHEMA}}

Доступные ассеты (id для поля image): {{ASSETS}}

Текущая колода (JSON; id слайдов используй в update_slide/remove_slide/move_slide):
{{DECK_JSON}}
```

- [ ] **Step 5: Реализация `agent.py`**

```python
"""Цикл агента: сообщение пользователя → вызовы инструментов → новая колода и ответ."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..model import Deck, slide_schema
from .client import LLM, LLMError
from .tools import ToolExecutor, tool_specs

PROMPT = (Path(__file__).parent / "prompt.md").read_text()


@dataclass
class Outcome:
    reply: str
    changed: bool
    ops: list[str]
    deck: Deck


def build_system_prompt(deck: Deck, assets: list[str]) -> str:
    return (PROMPT
            .replace("{{SCHEMA}}", json.dumps(slide_schema(), ensure_ascii=False))
            .replace("{{ASSETS}}", ", ".join(assets) if assets else "(нет)")
            .replace("{{DECK_JSON}}", deck.model_dump_json(include={"title", "slides"})))


def _user_content(message: str, files: list[tuple[str, str]]) -> str:
    parts = [message.strip() or "Сделай презентацию по приложенным материалам."]
    for name, text in files:
        parts.append(f"Файл «{name}»:\n```\n{text}\n```")
    return "\n\n".join(parts)


async def run_agent(llm: LLM, deck: Deck, user_message: str, files: list[tuple[str, str]],
                    history: list[dict], assets: list[str], max_iter: int = 12) -> Outcome:
    ex = ToolExecutor(deck)
    tools = tool_specs()
    messages: list[dict] = [{"role": "system", "content": build_system_prompt(deck, assets)}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": _user_content(user_message, files)})

    reply = ""
    for _ in range(max_iter):
        c = await llm.complete(messages, tools)
        if not c.tool_calls:
            reply = c.text.strip()
            break
        messages.append({"role": "assistant", "content": c.text or None, "tool_calls": [
            {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}
            for tc in c.tool_calls]})
        for tc in c.tool_calls:
            result = ex.call(tc.name, tc.arguments)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
        if ex.finished:
            reply = ex.summary
            break
    else:
        reply = "Достигнут лимит шагов; применены правки: " + (", ".join(ex.ops) or "нет")
    return Outcome(reply=reply or ("Готово." if ex.changed else ""), changed=ex.changed, ops=ex.ops, deck=ex.deck)
```

- [ ] **Step 6: Прогнать; коммит** `Инструменты LLM и цикл агента`

---

### Task 9: Реестр задач

**Files:**
- Create: `src/typst_deck/jobs.py`, `tests/test_jobs.py`

**Interfaces:**
- Produces: `Job(id, deck_id, status: Literal["queued","running","done","failed"], error: str | None, deck_version: int | None, created_at)`, `JobConflict(Exception)`, `JobRegistry` с `create(deck_id) -> Job` (JobConflict, если по колоде есть queued/running), `start(job, coro_factory) -> None` (запускает `asyncio.create_task`; результат корутины — новая версия колоды `int` → `deck_version`; исключение → `failed` с текстом), `get(job_id) -> Job | None`, `active_for(deck_id) -> Job | None`, `last_for(deck_id) -> Job | None`, `async wait(job_id, timeout: float) -> Job` (возвращает текущее состояние по таймауту).

- [ ] **Step 1: Тесты**

```python
import asyncio

import pytest

from typst_deck.jobs import JobConflict, JobRegistry


async def test_job_lifecycle():
    reg = JobRegistry()
    job = reg.create("d1")
    assert job.status == "queued" and reg.active_for("d1") is job
    ev = asyncio.Event()

    async def work():
        await ev.wait()
        return 7

    reg.start(job, work)
    await asyncio.sleep(0)
    assert reg.get(job.id).status == "running"
    with pytest.raises(JobConflict):
        reg.create("d1")
    ev.set()
    j = await reg.wait(job.id, timeout=1)
    assert j.status == "done" and j.deck_version == 7 and reg.active_for("d1") is None
    assert reg.last_for("d1") is j


async def test_job_failure():
    reg = JobRegistry()
    job = reg.create("d1")

    async def boom():
        raise RuntimeError("сломалось")

    reg.start(job, boom)
    j = await reg.wait(job.id, timeout=1)
    assert j.status == "failed" and "сломалось" in j.error


async def test_wait_timeout_returns_current_state():
    reg = JobRegistry()
    job = reg.create("d1")

    async def slow():
        await asyncio.sleep(5)

    reg.start(job, slow)
    j = await reg.wait(job.id, timeout=0.05)
    assert j.status == "running"
    assert reg.get("nope") is None
```

- [ ] **Step 2: Прогнать — падает**

- [ ] **Step 3: Реализация**

```python
"""Фоновые задачи генерации в том же процессе. Одна активная задача на колоду."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Awaitable, Callable, Literal

from .model import new_id, utcnow

log = logging.getLogger(__name__)


class JobConflict(Exception):
    pass


@dataclass
class Job:
    id: str
    deck_id: str
    status: Literal["queued", "running", "done", "failed"] = "queued"
    error: str | None = None
    deck_version: int | None = None
    created_at: datetime = field(default_factory=utcnow)
    done_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)


class JobRegistry:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._tasks: set[asyncio.Task] = set()

    def create(self, deck_id: str) -> Job:
        if self.active_for(deck_id):
            raise JobConflict(f"по колоде {deck_id} уже идёт задача")
        job = Job(id=new_id("j", 10), deck_id=deck_id)
        self._jobs[job.id] = job
        return job

    def start(self, job: Job, coro_factory: Callable[[], Awaitable[int | None]]) -> None:
        async def runner():
            job.status = "running"
            try:
                job.deck_version = await coro_factory()
                job.status = "done"
            except Exception as e:  # noqa: BLE001 — любая ошибка задачи идёт в статус
                log.exception("задача %s упала", job.id)
                job.status, job.error = "failed", f"{type(e).__name__}: {e}"
            finally:
                job.done_event.set()
        t = asyncio.create_task(runner())
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def active_for(self, deck_id: str) -> Job | None:
        for j in self._jobs.values():
            if j.deck_id == deck_id and j.status in ("queued", "running"):
                return j
        return None

    def last_for(self, deck_id: str) -> Job | None:
        js = [j for j in self._jobs.values() if j.deck_id == deck_id]
        return max(js, key=lambda j: j.created_at) if js else None

    async def wait(self, job_id: str, timeout: float) -> Job:
        job = self._jobs[job_id]
        try:
            await asyncio.wait_for(job.done_event.wait(), timeout)
        except asyncio.TimeoutError:
            pass
        return job
```

- [ ] **Step 4: Прогнать; коммит** `Реестр фоновых задач`

---

### Task 10: HTTP API колод

**Files:**
- Create: `src/typst_deck/app.py`, `src/typst_deck/api/__init__.py`, `src/typst_deck/api/common.py`, `src/typst_deck/api/uploads.py`, `src/typst_deck/api/decks.py`, `src/typst_deck/api/jobs.py`, `src/typst_deck/service.py`, `tests/test_api.py`
- Modify: `tests/conftest.py` (фикстуры `app`, `client`)

**Interfaces:**
- Produces: `create_app(settings: Settings | None = None, llm: LLM | None = None) -> FastAPI`; на `app.state`: `settings`, `store: DeckStore`, `jobs: JobRegistry`, `llm: LLM | None`.
- `service.py`: `DeckService(store, jobs, llm, settings)` с методами `deck_response(deck_id) -> dict`, `async generate(deck_id, message, files) -> int` (агент + save + compile + chat; возвращает версию), `render(deck) -> CompileResult` (compile с откатом версии при ошибке), `async manual(deck_id, fn: Callable[[Deck], None]) -> dict` (под блокировкой: fn правит колоду, save, render, ответ), `new_deck_from_brief(brief, upload_ids) -> tuple[Deck, Job]`, `submit_message(deck_id, text) -> Job`.
- Ответ колоды: `{"deck": {...}, "status": "generating"|"ready"|"failed", "version": int, "pdf_url": str, "edit_url": str, "warnings": [...], "last_error": str | None, "slide_count": int}`; `status = "generating"` при активной задаче, `"failed"` если последняя задача упала, иначе `"ready"`.
- Ошибки: `{"error": {"code": "not_found"|"validation"|"conflict"|"llm_unavailable"|"render", "message": str}}` с кодами 404/422/409/503/500.

Маршруты (спека §8, кроме `/api/agent/*`):

```
POST /api/uploads                      multipart file → {upload_id, name, kind, chars}
POST /api/decks                        {brief, upload_ids} → 202 {deck_id, job_id}
GET  /api/decks/{id}                   deck_response
GET  /api/decks/{id}/slides/{n}.svg    image/svg+xml
GET  /api/decks/{id}/deck.pdf          application/pdf, Content-Disposition с названием
GET  /api/decks/{id}/positions         [...]
PATCH /api/decks/{id}/slides/{sid}     {patch} → deck_response
POST /api/decks/{id}/slides            {slide, after} → deck_response
DELETE /api/decks/{id}/slides/{sid}    → deck_response
POST /api/decks/{id}/slides/{sid}/move {to_index} → deck_response
POST /api/decks/{id}/assets            multipart → {asset_id}
GET  /api/decks/{id}/versions          [{version, updated_at, slide_count}]
POST /api/decks/{id}/revert            {version} → deck_response
POST /api/decks/{id}/messages          {text} → 202 {job_id}
GET  /api/decks/{id}/chat              [{role, content, version, ts}]
GET  /api/jobs/{job_id}                {id, deck_id, status, error, deck_version}
```

Генерация без LLM (`app.state.llm is None`): `POST /api/decks` и `/messages` → 503 `llm_unavailable`; всё остальное работает.

- [ ] **Step 1: Фикстуры в `conftest.py`**

```python
@pytest.fixture
def settings(tmp_path):
    from typst_deck.config import Settings
    return Settings(data_dir=tmp_path / "data", template_dir=TEMPLATE_DIR, public_base_url="http://t")


@pytest.fixture
def fake_llm():
    from typst_deck.llm.client import FakeLLM
    return FakeLLM([])


@pytest.fixture
async def client(settings, fake_llm):
    import httpx
    from typst_deck.app import create_app
    app = create_app(settings, llm=fake_llm)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        c.app = app
        yield c
```

- [ ] **Step 2: Тесты** (`tests/test_api.py`, все под `requires_typst`, кроме первых двух)

```python
import asyncio

import pytest

from tests.conftest import requires_typst
from typst_deck.llm.client import Completion, ToolCall


async def wait_job(client, job_id):
    for _ in range(200):
        j = (await client.get(f"/api/jobs/{job_id}")).json()
        if j["status"] in ("done", "failed"):
            return j
        await asyncio.sleep(0.02)
    raise AssertionError("задача не завершилась")


async def test_upload_and_errors(client):
    r = await client.post("/api/uploads", files={"file": ("brief.txt", b"hello", "text/plain")})
    assert r.status_code == 200 and r.json()["kind"] == "text" and r.json()["chars"] == 5
    r = await client.post("/api/uploads", files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation"
    assert (await client.get("/api/decks/nope")).status_code == 404


async def test_create_without_llm_is_503(settings):
    import httpx
    from typst_deck.app import create_app
    app = create_app(settings, llm=None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/decks", json={"brief": "x", "upload_ids": []})
        assert r.status_code == 503 and r.json()["error"]["code"] == "llm_unavailable"


@requires_typst
async def test_full_flow(client, fake_llm, png_bytes):
    fake_llm._queue += [
        Completion("", [ToolCall("c1", "set_deck", {"title": "Итоги", "slides": [
            {"type": "title", "title": "Итоги", "subtitle": "Q3"},
            {"type": "image", "title": "Рост", "bullets": ["a", "b"]},
            {"type": "final"}]})]),
        Completion("", [ToolCall("c2", "finish", {"summary": "Готово: 3 слайда"})]),
    ]
    up = (await client.post("/api/uploads", files={"file": ("brief.txt", b"данные", "text/plain")})).json()
    r = await client.post("/api/decks", json={"brief": "сделай", "upload_ids": [up["upload_id"]]})
    assert r.status_code == 202
    deck_id, job_id = r.json()["deck_id"], r.json()["job_id"]
    assert (await client.get(f"/api/decks/{deck_id}")).json()["status"] == "generating"
    job = await wait_job(client, job_id)
    assert job["status"] == "done", job
    d = (await client.get(f"/api/decks/{deck_id}")).json()
    assert d["status"] == "ready" and d["slide_count"] == 3 and d["edit_url"] == f"http://t/d/{deck_id}"
    assert "данные" in fake_llm.calls[0][-1]["content"]
    chat = (await client.get(f"/api/decks/{deck_id}/chat")).json()
    assert [m["role"] for m in chat] == ["user", "assistant"] and chat[1]["content"] == "Готово: 3 слайда"

    assert (await client.get(f"/api/decks/{deck_id}/slides/2.svg")).headers["content-type"].startswith("image/svg+xml")
    assert (await client.get(f"/api/decks/{deck_id}/slides/9.svg")).status_code == 404
    pdf = await client.get(f"/api/decks/{deck_id}/deck.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    pos = (await client.get(f"/api/decks/{deck_id}/positions")).json()
    assert any(p["field"] == "bullets" for p in pos)

    sid = d["deck"]["slides"][1]["id"]
    r = await client.patch(f"/api/decks/{deck_id}/slides/{sid}", json={"patch": {"title": "Новый"}})
    assert r.status_code == 200 and r.json()["deck"]["slides"][1]["title"] == "Новый" and r.json()["version"] == 3
    r = await client.patch(f"/api/decks/{deck_id}/slides/{sid}", json={"patch": {"title": "x" * 500}})
    assert r.status_code == 422

    a = await client.post(f"/api/decks/{deck_id}/assets", files={"file": ("p.png", png_bytes, "image/png")})
    aid = a.json()["asset_id"]
    r = await client.patch(f"/api/decks/{deck_id}/slides/{sid}", json={"patch": {"image": aid}})
    assert r.json()["warnings"] == []

    r = await client.post(f"/api/decks/{deck_id}/slides", json={"slide": {"type": "section", "title": "Р"}, "after": sid})
    assert r.json()["slide_count"] == 4 and r.json()["deck"]["slides"][2]["type"] == "section"
    new_id_ = r.json()["deck"]["slides"][2]["id"]
    r = await client.post(f"/api/decks/{deck_id}/slides/{new_id_}/move", json={"to_index": 0})
    assert r.json()["deck"]["slides"][0]["id"] == new_id_
    r = await client.delete(f"/api/decks/{deck_id}/slides/{new_id_}")
    assert r.json()["slide_count"] == 3

    versions = (await client.get(f"/api/decks/{deck_id}/versions")).json()
    assert [v["version"] for v in versions][:2] == [1, 2]
    r = await client.post(f"/api/decks/{deck_id}/revert", json={"version": 2})
    assert r.json()["deck"]["slides"][1]["title"] == "Рост"

    fake_llm._queue += [
        Completion("", [ToolCall("c3", "update_slide", {"slide_id": sid, "patch": {"title": "Через чат"}})]),
        Completion("Поменял", []),
    ]
    r = await client.post(f"/api/decks/{deck_id}/messages", json={"text": "поменяй заголовок"})
    assert r.status_code == 202
    r2 = await client.post(f"/api/decks/{deck_id}/messages", json={"text": "ещё"})
    assert r2.status_code == 409
    job = await wait_job(client, r.json()["job_id"])
    assert job["status"] == "done"
    d = (await client.get(f"/api/decks/{deck_id}")).json()
    assert d["deck"]["slides"][1]["title"] == "Через чат"
    assert d["deck"]["id"] in fake_llm.calls[-1][0]["content"]


@requires_typst
async def test_failed_generation_reports(client, fake_llm):
    r = await client.post("/api/decks", json={"brief": "x", "upload_ids": []})
    job = await wait_job(client, r.json()["job_id"])
    assert job["status"] == "failed" and "FakeLLM" in job["error"]
    d = (await client.get(f"/api/decks/{r.json()['deck_id']}")).json()
    assert d["status"] == "failed" and d["last_error"]
```

- [ ] **Step 3: Прогнать — падает**

- [ ] **Step 4: Реализация `api/common.py`**

```python
"""Общие ответы об ошибках и доступ к состоянию приложения."""
from fastapi import HTTPException, Request


class ApiError(HTTPException):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(status_code=status, detail={"code": code, "message": message})


def not_found(what: str) -> ApiError:
    return ApiError(404, "not_found", f"{what} не найдено")


def svc(request: Request):
    return request.app.state.service
```

- [ ] **Step 5: Реализация `service.py`**

```python
"""Операции над колодой, общие для веб-интерфейса и агентского API."""
from __future__ import annotations

import json
from typing import Callable

from pydantic import ValidationError

from .api.common import ApiError, not_found
from .config import Settings
from .extract import UnsupportedFile, extract
from .jobs import Job, JobConflict, JobRegistry
from .llm.agent import run_agent
from .llm.client import LLM
from .model import Deck, utcnow
from .render import CompileError, CompileResult, compile_deck
from .store import DeckNotFound, DeckStore


class DeckService:
    def __init__(self, store: DeckStore, jobs: JobRegistry, llm: LLM | None, settings: Settings):
        self.store, self.jobs, self.llm, self.settings = store, jobs, llm, settings

    # --- чтение
    def load(self, deck_id: str) -> Deck:
        try:
            return self.store.load(deck_id)
        except DeckNotFound:
            raise not_found("колода")

    def deck_response(self, deck_id: str) -> dict:
        deck = self.load(deck_id)
        active, last = self.jobs.active_for(deck_id), self.jobs.last_for(deck_id)
        status = "generating" if active else ("failed" if last and last.status == "failed" else "ready")
        build = self.store.deck_dir(deck_id) / "build"
        warnings = json.loads((build / "warnings.json").read_text()) if (build / "warnings.json").exists() else []
        base = self.settings.public_base_url.rstrip("/")
        return {
            "deck": deck.model_dump(mode="json"), "status": status, "version": deck.version,
            "pdf_url": f"{base}/api/decks/{deck_id}/deck.pdf", "edit_url": f"{base}/d/{deck_id}",
            "warnings": warnings, "last_error": last.error if last else None, "slide_count": len(deck.slides),
            "has_build": (build / "deck.pdf").exists(),
        }

    def outline(self, deck: Deck) -> list[dict]:
        return [{"n": i + 1, "type": s.type, "title": getattr(s, "title", "")} for i, s in enumerate(deck.slides)]

    # --- рендер
    def render(self, deck: Deck) -> CompileResult:
        try:
            return compile_deck(deck, self.store.deck_dir(deck.id), self.settings.template_dir, self.settings.typst_bin)
        except CompileError as e:
            raise ApiError(500, "render", f"{e}: {e.stderr[:2000]}")

    # --- ручные правки
    async def manual(self, deck_id: str, fn: Callable[[Deck], None]) -> dict:
        async with self.store.lock(deck_id):
            deck = self.load(deck_id)
            prev = deck.version
            try:
                fn(deck)
            except ValidationError as e:
                raise ApiError(422, "validation", "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()))
            except KeyError as e:
                raise not_found(f"слайд {e}")
            except ValueError as e:
                raise ApiError(422, "validation", str(e))
            self.store.save(deck)
            try:
                self.render(deck)
            except ApiError:
                self.store.revert(deck_id, prev)
                raise
        return self.deck_response(deck_id)

    # --- генерация
    def require_llm(self) -> LLM:
        if self.llm is None:
            raise ApiError(503, "llm_unavailable", "LLM не настроена: задайте TYPST_DECK_LLM_API_KEY")
        return self.llm

    def ingest_file(self, name: str, data: bytes) -> tuple[str, bytes, str | None]:
        try:
            ex = extract(name, data)
        except UnsupportedFile as e:
            raise ApiError(422, "validation", str(e))
        return name, data, (ex.text if ex.kind == "text" else None)

    def new_deck_from_brief(self, brief: str, files: list[tuple[str, bytes, str | None]]) -> tuple[Deck, Job]:
        self.require_llm()
        deck = self.store.create(Deck(title=(brief.strip().splitlines() or ["Презентация"])[0][:120] or "Презентация"))
        for name, data, text in files:
            if text is None:
                aid = self.store.add_asset(deck.id, name, data)
                self.store.add_upload(deck.id, name, data, None)
            else:
                self.store.add_upload(deck.id, name, data, text)
        job = self.jobs.create(deck.id)
        self.jobs.start(job, lambda: self.generate(deck.id, brief, first=True))
        return deck, job

    def submit_message(self, deck_id: str, text: str) -> Job:
        self.require_llm()
        self.load(deck_id)
        try:
            job = self.jobs.create(deck_id)
        except JobConflict as e:
            raise ApiError(409, "conflict", str(e))
        self.jobs.start(job, lambda: self.generate(deck_id, text, first=False))
        return job

    async def generate(self, deck_id: str, message: str, first: bool) -> int:
        llm = self.require_llm()
        async with self.store.lock(deck_id):
            deck = self.store.load(deck_id)
            files = self.store.list_uploads(deck_id) if first else []
            history = [m for m in self.store.read_chat(deck_id) if m["role"] in ("user", "assistant")]
            self.store.append_chat(deck_id, {"role": "user", "content": message, "version": deck.version, "ts": utcnow().isoformat()})
            try:
                out = await run_agent(llm, deck, message, files, history, self.store.assets(deck_id))
                if out.changed:
                    self.store.save(out.deck)
                    self.render(out.deck)
            except Exception as e:
                self.store.append_chat(deck_id, {"role": "error", "content": f"{type(e).__name__}: {e}", "version": deck.version, "ts": utcnow().isoformat()})
                raise
            self.store.append_chat(deck_id, {"role": "assistant", "content": out.reply, "ops": out.ops, "version": out.deck.version, "ts": utcnow().isoformat()})
            return out.deck.version
```

- [ ] **Step 6: Реализация маршрутов** — `api/uploads.py`, `api/decks.py`, `api/jobs.py` по таблице выше, каждый обработчик 3–10 строк, вся логика в `DeckService`. Пример `decks.py`:

```python
from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..service import DeckService
from .common import not_found, svc

router = APIRouter(prefix="/api/decks")


class CreateBody(BaseModel):
    brief: str = ""
    upload_ids: list[str] = []


class PatchBody(BaseModel):
    patch: dict


class AddBody(BaseModel):
    slide: dict
    after: str | None = None


class MoveBody(BaseModel):
    to_index: int


class RevertBody(BaseModel):
    version: int


class MessageBody(BaseModel):
    text: str


@router.post("", status_code=202)
async def create(body: CreateBody, s: DeckService = Depends(svc)):
    files = []
    for uid in body.upload_ids:
        try:
            name, data, text = s.store.take_upload(uid)
        except KeyError:
            raise not_found(f"загрузка {uid}")
        files.append((name, data, text))
    deck, job = s.new_deck_from_brief(body.brief, files)
    return {"deck_id": deck.id, "job_id": job.id}


@router.get("/{deck_id}")
async def get(deck_id: str, s: DeckService = Depends(svc)):
    return s.deck_response(deck_id)


@router.get("/{deck_id}/slides/{n}.svg")
async def svg(deck_id: str, n: int, s: DeckService = Depends(svc)):
    p = s.store.deck_dir(deck_id) / "build" / f"slide-{n}.svg"
    if not s.store.exists(deck_id) or not p.exists():
        raise not_found("страница")
    return FileResponse(p, media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@router.get("/{deck_id}/deck.pdf")
async def pdf(deck_id: str, s: DeckService = Depends(svc)):
    deck = s.load(deck_id)
    p = s.store.deck_dir(deck_id) / "build" / "deck.pdf"
    if not p.exists():
        raise not_found("PDF")
    return FileResponse(p, media_type="application/pdf", filename=f"{deck.title[:60] or 'deck'}.pdf")


@router.get("/{deck_id}/positions")
async def positions(deck_id: str, s: DeckService = Depends(svc)):
    s.load(deck_id)
    p = s.store.deck_dir(deck_id) / "build" / "positions.json"
    return json.loads(p.read_text()) if p.exists() else []


@router.patch("/{deck_id}/slides/{slide_id}")
async def patch(deck_id: str, slide_id: str, body: PatchBody, s: DeckService = Depends(svc)):
    return await s.manual(deck_id, lambda d: d.apply_patch(slide_id, body.patch))


@router.post("/{deck_id}/slides")
async def add(deck_id: str, body: AddBody, s: DeckService = Depends(svc)):
    return await s.manual(deck_id, lambda d: d.add_slide(body.slide, body.after))


@router.delete("/{deck_id}/slides/{slide_id}")
async def remove(deck_id: str, slide_id: str, s: DeckService = Depends(svc)):
    return await s.manual(deck_id, lambda d: d.remove_slide(slide_id))


@router.post("/{deck_id}/slides/{slide_id}/move")
async def move(deck_id: str, slide_id: str, body: MoveBody, s: DeckService = Depends(svc)):
    return await s.manual(deck_id, lambda d: d.move_slide(slide_id, body.to_index))


@router.post("/{deck_id}/assets")
async def asset(deck_id: str, file: UploadFile, s: DeckService = Depends(svc)):
    s.load(deck_id)
    data = await file.read()
    try:
        return {"asset_id": s.store.add_asset(deck_id, file.filename or "", data)}
    except ValueError as e:
        raise ApiError(422, "validation", str(e))


@router.get("/{deck_id}/versions")
async def versions(deck_id: str, s: DeckService = Depends(svc)):
    s.load(deck_id)
    out = []
    for v in s.store.list_versions(deck_id):
        d = s.store.load_version(deck_id, v)
        out.append({"version": v, "updated_at": d.updated_at.isoformat(), "slide_count": len(d.slides)})
    return out


@router.post("/{deck_id}/revert")
async def revert(deck_id: str, body: RevertBody, s: DeckService = Depends(svc)):
    def fn(d):
        old = s.store.load_version(deck_id, body.version)
        d.title, d.slides = old.title, old.slides
    return await s.manual(deck_id, fn)


@router.post("/{deck_id}/messages", status_code=202)
async def message(deck_id: str, body: MessageBody, s: DeckService = Depends(svc)):
    return {"job_id": s.submit_message(deck_id, body.text).id}


@router.get("/{deck_id}/chat")
async def chat(deck_id: str, s: DeckService = Depends(svc)):
    s.load(deck_id)
    return s.store.read_chat(deck_id)
```

(`revert` через `manual` вместо `store.revert`, чтобы получить рендер и единый ответ; `DeckNotFound` из `load_version` перехватывается как `KeyError` → 404.)

`app.py`:

```python
"""Сборка FastAPI-приложения."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import agent as agent_api, decks, jobs as jobs_api, uploads
from .config import Settings, get_settings
from .jobs import JobRegistry
from .llm.client import LLM, OpenAICompatLLM
from .service import DeckService
from .store import DeckStore

STATIC = Path(__file__).parent / "static"
_UNSET = object()


def create_app(settings: Settings | None = None, llm: LLM | None | object = _UNSET) -> FastAPI:
    settings = settings or get_settings()
    if llm is _UNSET:
        llm = OpenAICompatLLM(settings.llm_api_base, settings.llm_api_key, settings.llm_model,
                              settings.llm_max_tokens, settings.llm_tool_mode) if settings.llm_api_key else None
    app = FastAPI(title="typst-deck")
    store = DeckStore(settings.data_dir)
    app.state.settings, app.state.store, app.state.jobs, app.state.llm = settings, store, JobRegistry(), llm
    app.state.service = DeckService(store, app.state.jobs, llm, settings)

    @app.exception_handler(HTTPException)
    async def _err(request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "error", "message": str(exc.detail)}
        return JSONResponse({"error": detail}, status_code=exc.status_code)

    for r in (uploads.router, decks.router, jobs_api.router, agent_api.router):
        app.include_router(r)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/d/{deck_id}")
    async def deck_page(deck_id: str):
        return FileResponse(STATIC / "deck.html")

    @app.get("/api/health")
    async def health():
        return {"ok": True, "llm": llm is not None}

    return app
```

В Task 10 `agent_api` ещё нет — создать `api/agent.py` с пустым `router = APIRouter(prefix="/api/agent")`; наполнение в Task 11. Также создать `static/index.html` и `static/deck.html` с заглушкой «typst-deck» — наполнение в Task 12. Валидационные ошибки FastAPI (RequestValidationError) тоже завернуть в `{"error": {"code": "validation", ...}}` со статусом 422.

- [ ] **Step 7: Прогнать; коммит** `HTTP API колод: создание, правки, рендер, чат`

---

### Task 11: Агентское API для чат-бота

**Files:**
- Create: `tests/test_agent_api.py`
- Modify: `src/typst_deck/api/agent.py`, `src/typst_deck/service.py` (метод `agent_response(deck_id) -> dict`)

**Interfaces:**
- `POST /api/agent/create_deck` `{brief: str, files: [{name, content_base64}], wait_seconds: int = 180}` → `{deck_id, status, pdf_url, edit_url, outline, reply}`
- `POST /api/agent/revise_deck` `{deck_id, request, wait_seconds = 180}` → то же
- `GET /api/agent/decks/{deck_id}` → то же
- `reply` — последний ответ ассистента из чата; `status` как в `deck_response`. Ожидание — `jobs.wait(job.id, wait_seconds)`; по таймауту `status: "generating"`.

- [ ] **Step 1: Тесты**

```python
import base64

from tests.conftest import requires_typst
from typst_deck.llm.client import Completion, ToolCall

pytestmark = requires_typst


async def test_agent_create_and_revise(client, fake_llm):
    fake_llm._queue += [
        Completion("", [ToolCall("c1", "set_deck", {"title": "T", "slides": [{"type": "title", "title": "A"}, {"type": "final"}]})]),
        Completion("", [ToolCall("c2", "finish", {"summary": "Собрано"})]),
    ]
    r = await client.post("/api/agent/create_deck", json={
        "brief": "презентацию", "files": [{"name": "d.txt", "content_base64": base64.b64encode("цифры".encode()).decode()}]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "ready" and j["reply"] == "Собрано" and j["outline"] == [
        {"n": 1, "type": "title", "title": "A"}, {"n": 2, "type": "final", "title": "Спасибо"}]
    assert j["pdf_url"].endswith(f"/api/decks/{j['deck_id']}/deck.pdf") and j["edit_url"].endswith(f"/d/{j['deck_id']}")
    assert "цифры" in fake_llm.calls[0][-1]["content"]

    sid = None
    d = (await client.get(f"/api/decks/{j['deck_id']}")).json()
    sid = d["deck"]["slides"][0]["id"]
    fake_llm._queue += [
        Completion("", [ToolCall("c3", "update_slide", {"slide_id": sid, "patch": {"title": "B"}})]),
        Completion("Заменил", []),
    ]
    r = await client.post("/api/agent/revise_deck", json={"deck_id": j["deck_id"], "request": "замени заголовок"})
    assert r.json()["outline"][0]["title"] == "B" and r.json()["reply"] == "Заменил"
    g = await client.get(f"/api/agent/decks/{j['deck_id']}")
    assert g.json()["outline"][0]["title"] == "B"


async def test_agent_timeout_returns_generating(client, fake_llm):
    import asyncio
    from typst_deck.llm.client import Completion

    class Slow:
        async def complete(self, messages, tools):
            await asyncio.sleep(0.5)
            return Completion("ок", [])

    client.app.state.service.llm = Slow()
    r = await client.post("/api/agent/create_deck", json={"brief": "x", "files": [], "wait_seconds": 0})
    assert r.status_code == 200 and r.json()["status"] == "generating"


async def test_agent_bad_file(client):
    r = await client.post("/api/agent/create_deck", json={"brief": "x", "files": [{"name": "x.exe", "content_base64": "TVo="}]})
    assert r.status_code == 422
```

- [ ] **Step 2: Прогнать — падает**

- [ ] **Step 3: Реализация**

`service.py` добавить:

```python
    def agent_response(self, deck_id: str) -> dict:
        r = self.deck_response(deck_id)
        chat = [m for m in self.store.read_chat(deck_id) if m["role"] == "assistant"]
        return {"deck_id": deck_id, "status": r["status"], "pdf_url": r["pdf_url"], "edit_url": r["edit_url"],
                "outline": self.outline(self.load(deck_id)), "reply": chat[-1]["content"] if chat else "",
                "last_error": r["last_error"]}
```

`api/agent.py`:

```python
"""Тонкие синхронные обёртки для чат-бота: создать, доработать, получить."""
import base64
import binascii

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..service import DeckService
from .common import ApiError, svc

router = APIRouter(prefix="/api/agent")


class FileIn(BaseModel):
    name: str
    content_base64: str


class CreateIn(BaseModel):
    brief: str = ""
    files: list[FileIn] = []
    wait_seconds: int = 180


class ReviseIn(BaseModel):
    deck_id: str
    request: str
    wait_seconds: int = 180


@router.post("/create_deck")
async def create_deck(body: CreateIn, s: DeckService = Depends(svc)):
    files = []
    for f in body.files:
        try:
            data = base64.b64decode(f.content_base64, validate=True)
        except (binascii.Error, ValueError):
            raise ApiError(422, "validation", f"файл {f.name}: не base64")
        files.append(s.ingest_file(f.name, data))
    deck, job = s.new_deck_from_brief(body.brief, files)
    await s.jobs.wait(job.id, body.wait_seconds)
    return s.agent_response(deck.id)


@router.post("/revise_deck")
async def revise_deck(body: ReviseIn, s: DeckService = Depends(svc)):
    job = s.submit_message(body.deck_id, body.request)
    await s.jobs.wait(job.id, body.wait_seconds)
    return s.agent_response(body.deck_id)


@router.get("/decks/{deck_id}")
async def get_deck(deck_id: str, s: DeckService = Depends(svc)):
    return s.agent_response(deck_id)
```

- [ ] **Step 4: Прогнать; коммит** `Агентское API: create_deck, revise_deck, get`

---

### Task 12: Веб-интерфейс

**Files:**
- Create/replace: `src/typst_deck/static/index.html`, `deck.html`, `style.css`, `api.js`, `index.js`, `deck.js`
- Test: `tests/test_pages.py` (страницы отдаются, статика доступна, относительные пути)

**Interfaces:**
- Consumes: весь API из Task 10. Все URL в JS строятся относительно `document.baseURI` через `api.js`: `const BASE = new URL('.', location.href)` для `/`, а для `/d/{id}` — `new URL('../', location.href)`; в `deck.html` `<base href="../">`, в `index.html` `<base href="./">`, чтобы работать под префиксом за Nginx.

- [ ] **Step 1: Тест страниц**

```python
async def test_pages_and_static(client):
    r = await client.get("/")
    assert r.status_code == 200 and "typst-deck" in r.text and 'href="./"' in r.text
    r = await client.get("/d/abc")
    assert r.status_code == 200 and 'href="../"' in r.text
    assert (await client.get("/static/deck.js")).status_code == 200
    assert (await client.get("/api/health")).json()["ok"] is True
```

- [ ] **Step 2: `index.html` + `index.js`** — заголовок, textarea задания, `<input type=file multiple>`, список загруженных (имя, символов), кнопка «Создать презентацию» → `POST /api/uploads` по файлу → `POST /api/decks` → опрос `GET /api/jobs/{id}` раз в секунду с текстом статуса → переход на `d/{deck_id}`. Ошибки — в блок `.error`.

- [ ] **Step 3: `deck.html` + `deck.js`** — двухколоночная раскладка (`grid-template-columns: 1fr 2fr`):
  - слева: заголовок колоды, чат (`.messages` с ролями user/assistant/error), поле ввода, кнопка «Отправить», кнопки «Скачать PDF», «Добавить слайд» (выбор типа из шести), «История» (список версий с кнопкой «Вернуть»);
  - справа: `.pages` — для каждого слайда `<div class="page">` с `<img src="api/decks/{id}/slides/{n}.svg?v={version}">` и `<div class="overlay">` с зонами из `positions` (проценты от viewBox: `left = x / W * 100%`, где `W = 453.54`, `H = 255.12` считываются из `viewBox` SVG через `fetch` первой страницы один раз); над каждой страницей номер и кнопки «↑», «↓», «✕»;
  - клик по зоне → `openEditor(slideId, field)`: всплывающая панель у зоны; для `title/subtitle/caption/contact` — `<input>`, для `bullets` — `<textarea>` (строка = пункт), для `image` — `<select image_size>` + `<input type=file>` (загрузка в `POST assets`, затем patch `{image}`); «Сохранить» → `PATCH` → `refresh()`;
  - клик по странице вне зон → панель «Все поля слайда» из `deck.slides[n]` (рендер формы по ключам, кроме `id/type`; списки — textarea по строке; числа/`data`/`labels`/`series` — textarea с JSON и валидация ответом 422);
  - `refresh()`: `GET deck` → при `status === "generating"` показывать индикатор и опрашивать раз в секунду; иначе перерисовать страницы (с `?v=version` против кэша), затем `GET positions` и построить зоны; `warnings` показывать полосой над превью;
  - чат: `POST messages` → `202` → опрос `GET jobs/{id}`; по `done`/`failed` → `GET chat` и `refresh()`.
  - `style.css`: нейтральная светлая тема, зоны `outline: 1px dashed transparent` → при наведении `rgba(59,110,165,.6)`, панель редактора с тенью, страницы с рамкой и тенью, ширина превью по колонке.

- [ ] **Step 4: Прогнать тест; запустить сервер вручную и пройти сценарий в браузере с `FakeLLM` не выйдет — проверить на реальном ключе из `~/stack/.env` (`DEEPSEEK_API_KEY`) один раз: создать колоду из трёх абзацев текста, кликнуть заголовок, поменять, скачать PDF. Зафиксировать результат в README (раздел «Проверено»). Коммит** `Веб-интерфейс: создание, превью, правка кликом, чат`

---

### Task 13: Dockerfile, запуск, README

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `scripts/dev.sh`
- Modify: `README.md` (раздел «Запуск», «Проверено», «Подключение шаблона»), `.gitignore`

- [ ] **Step 1: `Dockerfile`**

```dockerfile
FROM python:3.12-slim
ARG TYPST_VERSION=0.15.1
RUN apt-get update && apt-get install -y --no-install-recommends curl xz-utils ca-certificates \
 && curl -fsSL "https://github.com/typst/typst/releases/download/v${TYPST_VERSION}/typst-x86_64-unknown-linux-musl.tar.xz" \
    | tar -xJ -C /tmp && install -m755 /tmp/typst-x86_64-unknown-linux-musl/typst /usr/local/bin/typst \
 && rm -rf /tmp/typst-* /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY template ./template
RUN uv sync --frozen --no-dev
ENV TYPST_DECK_DATA_DIR=/data TYPST_DECK_TEMPLATE_DIR=/app/template PATH="/app/.venv/bin:$PATH"
VOLUME /data
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["uvicorn", "typst_deck.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: `scripts/dev.sh`** — `uv run uvicorn typst_deck.app:create_app --factory --reload --port 8000`; чтение `DEEPSEEK_*` из `~/stack/.env` через `grep`, не `source`.

- [ ] **Step 3: Собрать образ, запустить с `-v $PWD/data:/data`, проверить `/api/health` и создание колоды через `/api/agent/create_deck` с `curl`. Обновить README: как запустить локально и в Docker, как положить корпоративный шаблон (контракт из спеки §4 — краткая версия со ссылкой), как подключить к стеку (`compose.yaml` и `/deck/` в Nginx — уже описано). Коммит** `Dockerfile и инструкция запуска`

---

## Самопроверка плана

- Спека §3 модель → Task 2; §4 контракт и `fields.typ` → Task 3–4; §5 рендер → 3–4; §6 хранилище → 5; §7 LLM, извлечение → 6–8; §8 API → 10–11; §9 UI → 12; §10 конфиг → 1; §11 тесты — в каждой задаче; §12 структура → 1, 13; §13 риски: JSON-режим → 7, таймаут агентских обёрток → 11, запасная панель полей → 12, без `@preview` → 4.
- Имена согласованы: `compile_deck`, `render_typ`, `DeckStore.*`, `run_agent`, `ToolExecutor.call`, `JobRegistry.create/start/wait/active_for/last_for`, `DeckService.manual/generate/new_deck_from_brief/submit_message/deck_response/agent_response`.
- Загрузка картинок по ссылке из интернета — вне первой версии (спека §1), в плане отсутствует намеренно.
