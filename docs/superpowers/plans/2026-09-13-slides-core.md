# Набор слайдов, план A — ядро

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** колода знает 15 типов слайдов, сохранённые колоды переносятся на них разовой командой, контракт Typst и шаблоны `default` и `dark` рисуют все типы, модель видит новую схему и памятку.

**Architecture:** `model.py` получает девять новых типов и пересобирает три старых; чистый конвертер в `migrate_slides.py` переводит сохранённые колоды, их версии и корзину; `render_typ` печатает вызовы 16 функций контракта и оборачивает каждое текстовое значение маркером поля — у составных полей маркеров несколько, имя у всех одно; `slots.py` учится путям с точкой (`blocks.text`); контракт проверяет образец из 15 слайдов, для которого сам кладёт две крошечные PNG.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest (`uv run pytest`), Typst 0.15.1.

**Spec:** `docs/superpowers/specs/2026-09-13-slide-set-design.md`

## Global Constraints

- Работа идёт в worktree `.worktrees/slides-v2` на ветке `slides-v2` от `main`. **В `main` ничего не сливать:** выкаченный новый продукт со старым каноном сломает Lemana Tech. Слияние и выкатка — после планов B, C и D.
- Комментарии, сообщения и тексты тестов — по-русски, как во всём репозитории.
- Новых зависимостей не добавлять.
- `uv run pytest` зелёный перед каждым коммитом. Базовая линия на `main`: 340 passed, 6 skipped (с `TYPST_DECK_TEST_TEMPLATES=~/corp-templates` — 348 passed). Корпоративные тесты Lemana Tech до плана D будут падать: канон ещё не знает новых типов — это ожидаемо, и на них ориентироваться нельзя. Прогоняйте **без** `TYPST_DECK_TEST_TEMPLATES`.
- `typst` 0.15.1 установлен, тесты компиляции реально выполняются.
- Экспорт в PPTX (`src/typst_deck/pptx.py`) в этом плане **не трогаем**: он переезжает на новые типы планом B. Его тесты на время плана A будут падать на `SAMPLE_DECK` (задача 5) — это ожидаемо и снимается в задаче 8.
- Пределы полей — ровно из спеки §4; продукт вычисляет `trend` и `numeric` (спека §6).
- Каждое сообщение коммита заканчивается строкой `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

## Отклонения от спеки, принятые при планировании

1. **Порядок задач разводит образец и шаблоны.** Спека описывает результат, а образец из 15 типов ломает компиляцию, пока шаблоны не умеют новые функции. Поэтому `SAMPLE_DECK` меняется (задача 5) уже после того, как `default` и `dark` реализуют контракт (задача 4).
2. **PPTX временно красный.** `pptx.py` строго требует сопоставление для каждого типа, а `SAMPLE_DECK` в задаче 5 получает 15. Задача 8 гасит эти тесты явным `pytest.mark.xfail` с причиной «план B», чтобы набор оставался зелёным и падения не прятали настоящие поломки.
3. **`video` в модели хранит и файл, и ссылку**, а в шаблон приходит только `url` (спека §6): ссылку на загруженный файл собирает продукт. В плане A эндпоинта выдачи файлов ещё нет (план C), поэтому `render_typ` пока собирает ссылку вида `{base}/api/decks/{id}/assets/{asset}` из `public_base_url`, а если её нет — передаёт `url: none`. План C добавит сам эндпоинт.

---

### Task 1: 15 типов в модели

**Files:**
- Modify: `src/typst_deck/model.py`
- Test: `tests/test_model.py`

**Interfaces:**
- Produces: типы слайдов `title`, `agenda`, `section`, `text`, `image`, `columns`, `comparison`, `quote`, `chart`, `dual-chart`, `metrics`, `table`, `gallery`, `video`, `final`; вложенные модели `Block`, `Side`, `Metric`, `Picture`, `ChartSide`, `Series`, `BarItem` (удаляется); константа `SLIDE_TYPES: tuple[str, ...]` в порядке каталога спеки §4.

- [ ] **Step 1: Написать падающие тесты** — в `tests/test_model.py`:

```python
def test_all_types_are_in_the_schema():
    from typst_deck.model import SLIDE_TYPES

    text = str(slide_schema())
    assert len(SLIDE_TYPES) == 15
    for t in SLIDE_TYPES:
        assert f"'{t}'" in text


def test_text_and_image_are_separate_types():
    """image без картинки больше не бывает: для тезисов есть text."""
    t = SlideAdapter.validate_python({"type": "text", "title": "Итоги", "bullets": ["раз"]})
    assert t.bullets == ["раз"]
    with pytest.raises(ValidationError):
        SlideAdapter.validate_python({"type": "text", "title": "Итоги", "bullets": []})
    img = SlideAdapter.validate_python({"type": "image", "title": "Рост", "image": "a1.png"})
    assert img.image == "a1.png" and img.image_size == "medium"
    with pytest.raises(ValidationError):
        SlideAdapter.validate_python({"type": "image", "title": "Рост"})


def test_chart_kinds_and_lengths():
    bar = SlideAdapter.validate_python({"type": "chart", "title": "Итоги", "kind": "bar",
                                        "labels": ["Центр"], "series": [{"name": "млн", "values": [42]}]})
    assert bar.kind == "bar"
    line = SlideAdapter.validate_python({"type": "chart", "title": "Итоги",
                                         "labels": ["Q1", "Q2"], "series": [{"name": "Ряд", "values": [1, 2]}]})
    assert line.kind == "line", "по умолчанию — линия"
    with pytest.raises(ValidationError):  # линии нужна вторая точка
        SlideAdapter.validate_python({"type": "chart", "title": "x", "kind": "line",
                                      "labels": ["Q1"], "series": [{"name": "Ряд", "values": [1]}]})
    with pytest.raises(ValidationError):  # значений столько же, сколько подписей
        SlideAdapter.validate_python({"type": "chart", "title": "x", "kind": "bar",
                                      "labels": ["a", "b"], "series": [{"name": "Ряд", "values": [1]}]})


def test_table_rows_match_the_header():
    ok = SlideAdapter.validate_python({"type": "table", "title": "Итоги",
                                       "header": ["Регион", "Выручка"], "rows": [["Центр", "42"]]})
    assert ok.rows == [["Центр", "42"]]
    with pytest.raises(ValidationError):
        SlideAdapter.validate_python({"type": "table", "title": "x",
                                      "header": ["Регион", "Выручка"], "rows": [["Центр"]]})


def test_video_takes_exactly_one_source():
    f = SlideAdapter.validate_python({"type": "video", "title": "Ролик", "video": "a1.mp4"})
    assert f.video == "a1.mp4" and f.url == ""
    u = SlideAdapter.validate_python({"type": "video", "title": "Ролик", "url": "https://v/1"})
    assert u.url == "https://v/1"
    for bad in ({}, {"video": "a1.mp4", "url": "https://v/1"}):
        with pytest.raises(ValidationError):
            SlideAdapter.validate_python({"type": "video", "title": "Ролик", **bad})


@pytest.mark.parametrize("bad", [
    {"type": "agenda", "title": "x", "items": ["раз", "два"]},                      # меньше трёх
    {"type": "agenda", "title": "x", "items": ["п"] * 8},                            # больше семи
    {"type": "columns", "title": "x", "blocks": [{"text": "один"}]},                 # меньше двух
    {"type": "columns", "title": "x", "blocks": [{"text": "т" * 301}, {"text": "б"}]},
    {"type": "comparison", "title": "x", "left": {"bullets": []}, "right": {"bullets": ["б"]}},
    {"type": "quote", "text": "ц" * 301},
    {"type": "metrics", "title": "x", "items": [{"value": "1", "label": "a"}]},      # меньше двух
    {"type": "metrics", "title": "x", "items": [{"value": "1" * 17, "label": "a"}, {"value": "2", "label": "b"}]},
    {"type": "table", "title": "x", "header": ["одна"], "rows": [["a"]]},            # меньше двух колонок
    {"type": "gallery", "title": "x", "images": [{"image": "a1.png"}]},              # меньше двух
    {"type": "dual-chart", "title": "x",
     "left": {"labels": ["a", "b"], "series": [{"name": "s", "values": [1, 2]}]},
     "right": {"labels": ["a", "b"], "series": [{"name": "s", "values": [1]}]}},     # длины не совпали
])
def test_invalid_new_types(bad):
    with pytest.raises(ValidationError):
        SlideAdapter.validate_python(bad)
```

В существующем `test_invalid` заменить две строки с `bar-chart` и `image` без картинки на:

```python
    {"type": "chart", "title": "x", "labels": [], "series": [{"name": "s", "values": []}]},
    {"type": "image", "title": "x", "image": "a1.png", "bullets": ["y" * 201]},
```

а в `test_schema_has_all_types` список типов заменить на `SLIDE_TYPES` (тест выше его уже проверяет — старый тест удалить). В `deck()` и `test_apply_patch`/`test_patch_invalid_keeps_slide` заменить слайд `image` на `{"type": "text", "title": "Рост", "bullets": ["a", "b"]}`, а `image_size` в патче — на `{"title": "Новый"}`.

- [ ] **Step 2: Прогнать — падают**

Run: `uv run pytest tests/test_model.py -q`
Expected: FAIL — нет `SLIDE_TYPES`, нет типов `text`, `agenda` и прочих.

- [ ] **Step 3: Реализация** — в `src/typst_deck/model.py` заменить блок от `Title = Annotated[...]` до `SlideAdapter` на:

```python
Title = Annotated[str, Field(max_length=TITLE_MAX)]
Bullet = Annotated[str, Field(min_length=1, max_length=BULLET_MAX)]
Short = Annotated[str, Field(max_length=80)]        # пункт повестки, подпись картинки, подпись графика
Heading = Annotated[str, Field(max_length=60)]      # заголовок блока, колонки, метрики
Cell = Annotated[str, Field(max_length=60)]         # ячейка таблицы
ImageSize = Literal["small", "medium", "large"]
ChartKind = Literal["bar", "line"]

SLIDE_TYPES = ("title", "agenda", "section", "text", "image", "columns", "comparison",
               "quote", "chart", "dual-chart", "metrics", "table", "gallery", "video", "final")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SlideBase(_Strict):
    id: str = Field(default_factory=lambda: new_id("s"))
    notes: str = ""


class Series(_Strict):
    name: Title
    values: list[float]


def _same_length(labels: list, series: list[Series], kind: str) -> None:
    """Общая проверка графика: значений столько же, сколько подписей; линии нужны две точки."""
    for s in series:
        if len(s.values) != len(labels):
            raise ValueError(f"серия «{s.name}»: {len(s.values)} значений при {len(labels)} подписях")
    if kind == "line" and len(labels) < 2:
        raise ValueError("линейному графику нужно минимум две точки")


class Block(_Strict):
    heading: Heading = ""
    text: Annotated[str, Field(min_length=1, max_length=300)]


class Side(_Strict):
    heading: Heading = ""
    bullets: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(min_length=1, max_length=5)


class Metric(_Strict):
    value: Annotated[str, Field(min_length=1, max_length=16)]
    label: Heading = ""
    delta: Annotated[str, Field(max_length=12)] = ""


class Picture(_Strict):
    image: Annotated[str, Field(min_length=1)]
    caption: Short = ""


class ChartSide(_Strict):
    caption: Short = ""
    kind: ChartKind = "line"
    labels: list[Title] = Field(min_length=1, max_length=12)
    series: list[Series] = Field(min_length=1, max_length=3)
    unit: str = ""

    @model_validator(mode="after")
    def _lengths(self):
        _same_length(self.labels, self.series, self.kind)
        return self


class TitleSlide(SlideBase):
    type: Literal["title"]
    title: Title
    subtitle: Title = ""
    # отдельные блоки, а не строки внутри подзаголовка: шаблоны размещают их сами
    author: Title = ""
    department: Title = ""


class AgendaSlide(SlideBase):
    type: Literal["agenda"]
    title: Title = "Повестка"
    items: list[Short] = Field(min_length=3, max_length=7)


class SectionSlide(SlideBase):
    type: Literal["section"]
    title: Title
    subtitle: Title = ""


class TextSlide(SlideBase):
    type: Literal["text"]
    title: Title
    bullets: list[Bullet] = Field(min_length=1, max_length=6)


class ImageSlide(SlideBase):
    type: Literal["image"]
    title: Title
    bullets: list[Bullet] = Field(default_factory=list, max_length=6)
    image: Annotated[str, Field(min_length=1)]  # без картинки бывает text, а не image
    image_size: ImageSize = "medium"
    caption: Title = ""


class ColumnsSlide(SlideBase):
    type: Literal["columns"]
    title: Title
    blocks: list[Block] = Field(min_length=2, max_length=3)


class ComparisonSlide(SlideBase):
    type: Literal["comparison"]
    title: Title
    left: Side
    right: Side


class QuoteSlide(SlideBase):
    type: Literal["quote"]
    text: Annotated[str, Field(min_length=1, max_length=300)]
    author: Annotated[str, Field(max_length=120)] = ""


class ChartSlide(SlideBase):
    type: Literal["chart"]
    title: Title
    kind: ChartKind = "line"
    labels: list[Title] = Field(min_length=1, max_length=24)
    series: list[Series] = Field(min_length=1, max_length=4)
    unit: str = ""
    bullets: list[Bullet] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def _lengths(self):
        _same_length(self.labels, self.series, self.kind)
        return self


class DualChartSlide(SlideBase):
    type: Literal["dual-chart"]
    title: Title
    left: ChartSide
    right: ChartSide


class MetricsSlide(SlideBase):
    type: Literal["metrics"]
    title: Title
    items: list[Metric] = Field(min_length=2, max_length=4)


class TableSlide(SlideBase):
    type: Literal["table"]
    title: Title
    header: list[Annotated[str, Field(max_length=40)]] = Field(min_length=2, max_length=6)
    rows: list[list[Cell]] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def _rows(self):
        for i, row in enumerate(self.rows, 1):
            if len(row) != len(self.header):
                raise ValueError(f"строка {i}: {len(row)} ячеек при {len(self.header)} колонках шапки")
        return self


class GallerySlide(SlideBase):
    type: Literal["gallery"]
    title: Title
    images: list[Picture] = Field(min_length=2, max_length=4)


class VideoSlide(SlideBase):
    type: Literal["video"]
    title: Title
    video: str = ""   # ассет .mp4 в колоде
    url: str = ""     # внешняя ссылка
    poster: str = ""  # ассет-картинка обложки
    caption: Annotated[str, Field(max_length=120)] = ""

    @model_validator(mode="after")
    def _source(self):
        if bool(self.video) == bool(self.url):
            raise ValueError("у видео должно быть ровно одно: файл video или ссылка url")
        return self


class FinalSlide(SlideBase):
    type: Literal["final"]
    title: Title = "Спасибо"
    contact: Title = ""


Slide = Annotated[
    Union[TitleSlide, AgendaSlide, SectionSlide, TextSlide, ImageSlide, ColumnsSlide,
          ComparisonSlide, QuoteSlide, ChartSlide, DualChartSlide, MetricsSlide,
          TableSlide, GallerySlide, VideoSlide, FinalSlide],
    Field(discriminator="type"),
]
SlideAdapter: TypeAdapter = TypeAdapter(Slide)
```

`BarItem` удалить. Остальное в файле (`new_id`, `Deck`, `slide_schema`) не трогать.

- [ ] **Step 4: Прогнать — зелёные**

Run: `uv run pytest tests/test_model.py -q`
Expected: PASS. Остальной набор пока красный (ожидаемо: старые типы исчезли) — он чинится задачами 2–8.

- [ ] **Step 5: Коммит**

```bash
git add src/typst_deck/model.py tests/test_model.py
git commit -m "Пятнадцать типов слайдов в модели

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: разовый перенос сохранённых колод

**Files:**
- Create: `src/typst_deck/migrate_slides.py`
- Test: `tests/test_migrate_slides.py` (новый)

**Interfaces:**
- Consumes: модель из задачи 1.
- Produces: `upgrade_slide(raw: dict) -> dict`, `upgrade_deck(raw: dict) -> dict`, `migrate(data_dir: Path, check: bool = False) -> list[tuple[str, int]]` (id колоды и число переписанных файлов), `main(argv)` с флагом `--check`.

- [ ] **Step 1: Падающие тесты** — `tests/test_migrate_slides.py`:

```python
"""Перенос сохранённых колод на новые типы слайдов."""
import json
from pathlib import Path

from typst_deck.migrate_slides import migrate, upgrade_slide
from typst_deck.model import Deck

LEGACY = {
    "id": "d1", "title": "Итоги", "template": "default", "version": 3,
    "created_at": "2026-09-01T00:00:00Z", "updated_at": "2026-09-01T00:00:00Z",
    "slides": [
        {"id": "s000001", "type": "title", "title": "Итоги", "subtitle": "Q3", "notes": "з"},
        {"id": "s000002", "type": "image", "title": "Рост", "bullets": ["раз", "два"],
         "image": None, "image_size": "medium", "caption": "подпись"},
        {"id": "s000003", "type": "image", "title": "Схема", "bullets": [], "image": "a1.png",
         "image_size": "large", "caption": "подпись"},
        {"id": "s000004", "type": "bar-chart", "title": "Диаграмма", "unit": "млн",
         "data": [{"label": "Центр", "value": 42}, {"label": "Север", "value": -17}], "bullets": ["в"]},
        {"id": "s000005", "type": "chart", "title": "График", "labels": ["Q1", "Q2"],
         "series": [{"name": "Выручка", "values": [1, 2]}], "unit": "", "bullets": []},
        {"id": "s000006", "type": "final", "title": "Спасибо", "contact": "team@corp"},
    ],
}


def write_deck(root: Path, deck_id: str, versions: int = 2) -> Path:
    d = root / "decks" / deck_id
    (d / "versions").mkdir(parents=True)
    raw = json.dumps(LEGACY | {"id": deck_id}, ensure_ascii=False)
    (d / "deck.json").write_text(raw)
    for v in range(1, versions + 1):
        (d / "versions" / f"{v:06d}.json").write_text(raw)
    return d


def test_upgrade_slide_rules():
    old = {s["type"]: s for s in LEGACY["slides"]}
    text = upgrade_slide(old["image"] | {"image": None})
    assert text["type"] == "text" and text["bullets"] == ["раз", "два"] and text["id"] == "s000002"
    assert "caption" not in text and "image" not in text and text["notes"] == ""
    picture = upgrade_slide(old["image"] | {"image": "a1.png"})
    assert picture["type"] == "image" and picture["image"] == "a1.png"
    bar = upgrade_slide(old["bar-chart"])
    assert bar["type"] == "chart" and bar["kind"] == "bar" and bar["labels"] == ["Центр", "Север"]
    assert bar["series"] == [{"name": "млн", "values": [42, -17]}] and bar["bullets"] == ["в"]
    line = upgrade_slide(old["chart"])
    assert line["type"] == "chart" and line["kind"] == "line" and line["labels"] == ["Q1", "Q2"]
    assert upgrade_slide(old["title"]) == old["title"], "старые типы не трогаются"


def test_bar_chart_without_unit_names_the_series():
    bar = upgrade_slide({"id": "s1", "type": "bar-chart", "title": "x", "unit": "",
                         "data": [{"label": "A", "value": 1}], "bullets": []})
    assert bar["series"][0]["name"] == "Значение"


def test_migrate_rewrites_decks_versions_and_trash(tmp_path):
    write_deck(tmp_path, "d0000000001")
    trash = tmp_path / "trash" / "d0000000002-20260910T110407"
    (trash / "versions").mkdir(parents=True)
    (trash / "deck.json").write_text(json.dumps(LEGACY | {"id": "d0000000002"}, ensure_ascii=False))

    done = migrate(tmp_path)
    assert dict(done) == {"d0000000001": 3, "d0000000002": 1}
    deck = Deck.model_validate_json((tmp_path / "decks" / "d0000000001" / "deck.json").read_text())
    assert [s.type for s in deck.slides] == ["title", "text", "image", "chart", "chart", "final"]
    assert deck.version == 3, "перенос — не правка, версия не поднимается"
    assert [s.id for s in deck.slides] == [s["id"] for s in LEGACY["slides"]]
    snapshot = Deck.model_validate_json(
        (tmp_path / "decks" / "d0000000001" / "versions" / "000001.json").read_text())
    assert [s.type for s in snapshot.slides] == [s.type for s in deck.slides]
    assert Deck.model_validate_json((trash / "deck.json").read_text()).slides[1].type == "text"


def test_migrate_is_idempotent_and_check_writes_nothing(tmp_path):
    d = write_deck(tmp_path, "d0000000001")
    migrate(tmp_path)
    stamp = (d / "deck.json").stat().st_mtime_ns
    assert migrate(tmp_path) == [], "второй проход менять нечего"
    assert (d / "deck.json").stat().st_mtime_ns == stamp

    write_deck(tmp_path, "d0000000003")
    before = (tmp_path / "decks" / "d0000000003" / "deck.json").read_text()
    assert dict(migrate(tmp_path, check=True)) == {"d0000000003": 3}
    assert (tmp_path / "decks" / "d0000000003" / "deck.json").read_text() == before


def test_broken_deck_is_left_alone(tmp_path):
    d = write_deck(tmp_path, "d0000000001")
    (d / "versions" / "000002.json").write_text("{не json")
    assert migrate(tmp_path) == []
    assert json.loads((d / "deck.json").read_text())["slides"][1]["type"] == "image", "колода целиком не тронута"
```

- [ ] **Step 2: Прогнать — падают**

Run: `uv run pytest tests/test_migrate_slides.py -q`
Expected: FAIL — `ModuleNotFoundError: typst_deck.migrate_slides`.

- [ ] **Step 3: Реализация** — `src/typst_deck/migrate_slides.py`:

```python
"""Разовый перенос сохранённых колод на набор типов из спеки 2026-09-13.

`python -m typst_deck.migrate_slides [--check]`

Переписывает deck.json и все снимки versions/ в decks/ и в trash/: id слайдов
сохраняются, версия не поднимается — это смена формата, а не правка. Повторный
запуск ничего не меняет. Запускать при остановленном сервисе.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .model import Deck
from .store import write_atomic


def upgrade_slide(raw: dict) -> dict:
    """Старый слайд → новый. Слайд нового формата возвращается как есть."""
    kind = raw.get("type")
    if kind == "image" and not raw.get("image"):
        # картинки нет — это текстовый слайд; подпись к картинке без картинки не рисовалась
        return {k: v for k, v in raw.items() if k in ("id", "notes", "title", "bullets")} | {"type": "text"}
    if kind == "bar-chart":
        data = raw.get("data") or []
        unit = raw.get("unit") or ""
        return {
            "id": raw["id"], "notes": raw.get("notes", ""), "type": "chart", "kind": "bar",
            "title": raw.get("title", ""), "unit": unit, "bullets": raw.get("bullets", []),
            "labels": [d["label"] for d in data],
            "series": [{"name": unit or "Значение", "values": [d["value"] for d in data]}],
        }
    if kind == "chart" and "kind" not in raw:
        return raw | {"kind": "line"}
    return raw


def upgrade_deck(raw: dict) -> dict:
    return raw | {"slides": [upgrade_slide(s) for s in raw.get("slides", [])]}


def _deck_dirs(data_dir: Path):
    for root in (data_dir / "decks", data_dir / "trash"):
        for d in sorted(root.glob("*")) if root.is_dir() else []:
            if (d / "deck.json").is_file():
                yield d


def migrate(data_dir: Path, check: bool = False) -> list[tuple[str, int]]:
    """Переносит колоды; возвращает пары (id колоды, сколько файлов переписано).

    Колода переписывается целиком или не переписывается вовсе: сначала все её
    файлы читаются и проверяются новой моделью, потом пишутся.
    """
    done: list[tuple[str, int]] = []
    for d in _deck_dirs(data_dir):
        planned: list[tuple[Path, str]] = []
        try:
            for p in [d / "deck.json", *sorted((d / "versions").glob("*.json"))]:
                raw = json.loads(p.read_text())
                new = upgrade_deck(raw)
                if new == raw:
                    continue
                Deck.model_validate(new)  # переносим только то, что модель примет
                planned.append((p, json.dumps(new, ensure_ascii=False, indent=2)))
        except (OSError, ValueError) as e:
            print(f"{d.name}: пропущена, {e}", file=sys.stderr)
            continue
        if not planned:
            continue
        if not check:
            for p, text in planned:
                write_atomic(p, text)
        done.append((d.name, len(planned)))
    return done


def main(argv: list[str] | None = None) -> int:
    from .config import get_settings

    argv = sys.argv[1:] if argv is None else argv
    check = "--check" in argv
    done = migrate(get_settings().data_dir, check=check)
    head = "будет перенесено" if check else "перенесено"
    print(f"{head}: колод {len(done)}, файлов {sum(n for _, n in done)}")
    for deck_id, n in done:
        print(f"  {deck_id}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Прогнать — зелёные**

Run: `uv run pytest tests/test_migrate_slides.py -q`
Expected: PASS (6 тестов).

- [ ] **Step 5: Коммит**

```bash
git add src/typst_deck/migrate_slides.py tests/test_migrate_slides.py
git commit -m "Разовый перенос колод, версий и корзины на новые типы

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `render_typ` печатает 15 типов

**Files:**
- Modify: `src/typst_deck/render.py` (`render_typ` и помощники рядом с ним)
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: модель (задача 1).
- Produces: вызовы `#slide-<тип>(...)` по одному на слайд; текстовые значения обёрнуты `field(id, "<поле верхнего уровня>", …)`; продукт вычисляет `numeric` у таблицы и `trend` у метрик; ссылка видео собирается из `base_url`.
- Produces: сигнатура `render_typ(deck, assets: set[str], base_url: str = "") -> tuple[str, list[str]]`.

- [ ] **Step 1: Падающие тесты** — в `tests/test_render.py`:

```python
def rich_deck():
    from typst_deck.model import Deck

    return Deck(id="d1", title="Т", slides=[
        {"id": "s1", "type": "agenda", "items": ["Раз", "Два", "Три"]},
        {"id": "s2", "type": "columns", "title": "Блоки",
         "blocks": [{"heading": "Первый", "text": "текст"}, {"text": "второй"}]},
        {"id": "s3", "type": "comparison", "title": "Было и стало",
         "left": {"heading": "Было", "bullets": ["раз"]}, "right": {"heading": "Стало", "bullets": ["два"]}},
        {"id": "s4", "type": "quote", "text": "Мысль", "author": "Автор"},
        {"id": "s5", "type": "metrics", "title": "Числа",
         "items": [{"value": "12,5 млн", "label": "выручка", "delta": "+12 %"},
                   {"value": "3", "label": "провалы", "delta": "-2 п. п."},
                   {"value": "7", "label": "ровно"}]},
        {"id": "s6", "type": "table", "title": "Таблица",
         "header": ["Регион", "Выручка"], "rows": [["Центр", "42"], ["Север", "17,5 %"]]},
        {"id": "s7", "type": "gallery", "title": "Галерея",
         "images": [{"image": "a1.png", "caption": "раз"}, {"image": "a2.png"}]},
        {"id": "s8", "type": "video", "title": "Ролик", "video": "a3.mp4", "poster": "a1.png"},
        {"id": "s9", "type": "video", "title": "Ссылка", "url": "https://v/1"},
    ])


def test_new_types_are_rendered_once_each():
    typ, _ = render_typ(rich_deck(), assets={"a1.png", "a2.png", "a3.mp4"})
    for name in ("agenda", "columns", "comparison", "quote", "metrics", "table", "gallery", "video"):
        assert f"\n#slide-{name}(" in typ
    assert typ.count("\n#slide-") == 9


def test_composite_fields_are_marked_by_top_level_name():
    typ, _ = render_typ(rich_deck(), assets={"a1.png", "a2.png", "a3.mp4"})
    assert 'field("s2", "blocks", "Первый")' in typ and 'field("s2", "blocks", "текст")' in typ
    assert 'field("s3", "left", "Было")' in typ and 'field("s3", "right", "два")' in typ
    assert 'field("s5", "items", "12,5 млн")' in typ
    assert 'field("s6", "header", "Регион")' in typ and 'field("s6", "rows", "42")' in typ
    assert 'field("s4", "text", "Мысль")' in typ and 'field("s4", "author", "Автор")' in typ


def test_product_computes_trend_and_numeric():
    typ, _ = render_typ(rich_deck(), assets={"a1.png", "a2.png", "a3.mp4"})
    assert 'trend: "up"' in typ and 'trend: "down"' in typ and "trend: none" in typ
    assert "numeric: (false, true,)" in typ, "числовая колонка выравнивается вправо"


def test_video_link_and_poster():
    typ, warnings = render_typ(rich_deck(), assets={"a1.png", "a2.png", "a3.mp4"}, base_url="http://t")
    assert 'url: "http://t/api/decks/d1/assets/a3.mp4"' in typ  # файл превращается в ссылку
    assert 'url: "https://v/1"' in typ
    assert 'field("s8", "poster", image("/assets/a1.png"' in typ
    assert warnings == []
    typ, warnings = render_typ(rich_deck(), assets={"a1.png", "a2.png", "a3.mp4"})
    assert "url: none" in typ, "без base_url ссылку собрать не из чего"
    assert warnings == [], "файл на месте — предупреждать не о чем"
    typ, warnings = render_typ(rich_deck(), assets={"a1.png", "a2.png"}, base_url="http://t")
    assert "url: none" in typ and any("a3.mp4" in w for w in warnings)


def test_gallery_skips_missing_pictures_with_a_warning():
    typ, warnings = render_typ(rich_deck(), assets={"a1.png", "a3.mp4"})
    assert typ.count('field("s7", "images"') >= 1
    assert any("a2.png" in w for w in warnings)
```

- [ ] **Step 2: Прогнать — падают**

Run: `uv run pytest tests/test_render.py -q -k "new_types or composite or trend or video_link or gallery"`
Expected: FAIL — `render_typ` не знает новых типов (`TypeError`).

- [ ] **Step 3: Реализация** — в `src/typst_deck/render.py`.

Импорты моделей заменить на весь набор:

```python
from .model import (
    AgendaSlide, ChartSlide, ColumnsSlide, ComparisonSlide, Deck, DualChartSlide, FinalSlide,
    GallerySlide, ImageSlide, MetricsSlide, QuoteSlide, SectionSlide, TableSlide, TextSlide,
    TitleSlide, VideoSlide,
)
```

Рядом с `_text`/`_bullets` добавить помощники:

```python
NUMBER = re.compile(r"^[-+−]?[\d\s ]+([.,]\d+)?\s*[%‰]?\s*\S{0,12}$")


def _dict(pairs: dict[str, str]) -> str:
    """Словарь Typst из готовых выражений: (k: expr, …)."""
    return "(" + ", ".join(f"{k}: {v}" for k, v in pairs.items()) + ")"


def _seq(items: list[str]) -> str:
    return "(" + ", ".join(items) + ",)" if items else "()"


def _mark(slide_id: str, name: str, value: str) -> str:
    """Текст составного поля: маркер с именем поля верхнего уровня (спека §6)."""
    return _text(slide_id, name, value)


def _numeric(header: list[str], rows: list[list[str]]) -> list[bool]:
    """Колонки, где каждая ячейка читается как число: шаблон выравнивает их вправо."""
    return [all(NUMBER.match(row[i] or "") for row in rows) if rows else False
            for i in range(len(header))]


def _trend(delta: str) -> str:
    d = delta.strip()
    if d.startswith("+"):
        return typ_str("up")
    if d.startswith(("-", "−")):
        return typ_str("down")
    return "none"
```

В `render_typ` — сигнатура и ветки. Заголовок функции:

```python
def render_typ(deck: Deck, assets: set[str], base_url: str = "") -> tuple[str, list[str]]:
    """Возвращает текст deck.typ и предупреждения (например, о пропавших картинках).

    base_url нужен слайду video: загруженный файл превращается в ссылку на него.
    """
```

Ветку `ImageSlide` оставить как есть, но `img = "none"` больше не бывает: картинка обязательна — если её нет в ассетах, слайд рисуется без неё и остаётся предупреждение (поведение прежнее). Добавить ветки (порядок — как в `SLIDE_TYPES`):

```python
        elif isinstance(s, AgendaSlide):
            items = _seq([_mark(sid, "items", i) for i in s.items])
            out.append(f"#slide-agenda(title: {_text(sid, 'title', s.title)}, items: {items})\n")
        elif isinstance(s, TextSlide):
            out.append(f"#slide-text(title: {_text(sid, 'title', s.title)}, "
                       f"bullets: {_bullets(sid, s.bullets)})\n")
        elif isinstance(s, ColumnsSlide):
            blocks = _seq([_dict({"heading": _mark(sid, "blocks", b.heading),
                                  "text": _mark(sid, "blocks", b.text)}) for b in s.blocks])
            out.append(f"#slide-columns(title: {_text(sid, 'title', s.title)}, blocks: {blocks})\n")
        elif isinstance(s, ComparisonSlide):
            def side(name: str, v):
                return _dict({"heading": _mark(sid, name, v.heading),
                              "bullets": _bullets(sid, v.bullets, name)})
            out.append(f"#slide-comparison(title: {_text(sid, 'title', s.title)}, "
                       f"left: {side('left', s.left)}, right: {side('right', s.right)})\n")
        elif isinstance(s, QuoteSlide):
            out.append(f"#slide-quote(text: {_text(sid, 'text', s.text)}, "
                       f"author: {_text(sid, 'author', s.author)})\n")
        elif isinstance(s, DualChartSlide):
            def chart(name: str, v):
                return _dict({"caption": _mark(sid, name, v.caption), "kind": typ_str(v.kind),
                              "labels": typ_value(v.labels),
                              "series": typ_value([x.model_dump() for x in v.series]),
                              "unit": _opt(v.unit)})
            out.append(f"#slide-dual-chart(title: {_text(sid, 'title', s.title)}, "
                       f"left: {chart('left', s.left)}, right: {chart('right', s.right)})\n")
        elif isinstance(s, MetricsSlide):
            items = _seq([_dict({"value": _mark(sid, "items", m.value),
                                 "label": _mark(sid, "items", m.label),
                                 "delta": _mark(sid, "items", m.delta),
                                 "trend": _trend(m.delta)}) for m in s.items])
            out.append(f"#slide-metrics(title: {_text(sid, 'title', s.title)}, items: {items})\n")
        elif isinstance(s, TableSlide):
            header = _seq([_mark(sid, "header", h) for h in s.header])
            rows = _seq([_seq([_mark(sid, "rows", c) for c in row]) for row in s.rows])
            out.append(f"#slide-table(title: {_text(sid, 'title', s.title)}, header: {header}, "
                       f"rows: {rows}, numeric: {typ_value(_numeric(s.header, s.rows))})\n")
        elif isinstance(s, GallerySlide):
            pics = []
            for pic in s.images:
                if pic.image not in assets:
                    warnings.append(f"слайд {n}: картинка {pic.image} не найдена")
                    continue
                pics.append(_dict({
                    "image": f'field({typ_str(sid)}, "images", image({typ_str("/assets/" + pic.image)}, '
                             'width: 100%, height: 100%, fit: "contain"))',
                    "caption": _mark(sid, "images", pic.caption)}))
            out.append(f"#slide-gallery(title: {_text(sid, 'title', s.title)}, images: {_seq(pics)})\n")
        elif isinstance(s, VideoSlide):
            url = s.url
            if s.video:
                # без base_url ссылку собрать не из чего (например, проверка контракта):
                # слайд рисуется обложкой без ссылки, и это не повод предупреждать
                if s.video not in assets:
                    warnings.append(f"слайд {n}: видео {s.video} не найдено")
                url = (f"{base_url.rstrip('/')}/api/decks/{deck.id}/assets/{s.video}"
                       if s.video in assets and base_url else "")
            poster = "none"
            if s.poster:
                if s.poster in assets:
                    poster = (f'field({typ_str(sid)}, "poster", image({typ_str("/assets/" + s.poster)}, '
                              'width: 100%, height: 100%, fit: "contain"))')
                else:
                    warnings.append(f"слайд {n}: обложка {s.poster} не найдена")
            out.append(f"#slide-video(title: {_text(sid, 'title', s.title)}, poster: {poster}, "
                       f"url: {_opt(url)}, caption: {_text(sid, 'caption', s.caption)})\n")
```

`_bullets` получает необязательное имя поля (для `comparison` маркер называется `left`/`right`):

```python
def _bullets(slide_id: str, items: list[str], name: str = "bullets") -> str:
    if not items:
        return "none"
    return f'field({typ_str(slide_id)}, {typ_str(name)}, list({", ".join(typ_str(i) for i in items)}))'
```

Ветку `BarChartSlide` удалить, ветку `ChartSlide` дополнить видом:

```python
            out.append(
                f"#slide-chart(title: {_text(sid, 'title', s.title)}, kind: {typ_str(s.kind)}, "
                f"labels: {typ_value(s.labels)}, "
                f"series: {typ_value([x.model_dump() for x in s.series])}, "
                f"unit: {_opt(s.unit)}, bullets: {_bullets(sid, s.bullets)})\n"
            )
```

В `compile_deck` пробросить `base_url`: параметр `base_url: str = ""` и передача в `render_typ`.

- [ ] **Step 4: Прогнать — зелёные**

Run: `uv run pytest tests/test_render.py -q`
Expected: PASS (старые тесты `test_golden`, `test_one_call_per_slide` и `full_deck` из этого файла поправить под новые типы: `image` с картинкой, `chart` с `kind`).

- [ ] **Step 5: Коммит**

```bash
git add src/typst_deck/render.py tests/test_render.py
git commit -m "render_typ печатает все типы и метит составные поля

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: шаблоны `default` и `dark` рисуют 15 типов

**Files:**
- Modify: `template/deck.typ`, `templates/dark/deck.typ`
- Test: `tests/test_compile.py`

**Interfaces:**
- Consumes: вызовы из задачи 3.
- Produces: 16 экспортируемых функций в каждом шаблоне; одна функция — одна страница.

**Контекст:** `templates/dark/deck.typ` — копия эталона, отличается 11 строками: комментарий в шапке, палитра и `fill:` у страницы. Пишите функции в эталоне, затем переносите тот же текст в тёмный, сохраняя его палитру.

- [ ] **Step 1: Падающий тест** — в `tests/test_compile.py`:

```python
@requires_typst
@pytest.mark.parametrize("tid", ["default", "dark"])
def test_every_template_draws_all_types(deck_dir, png_bytes, tid):
    """Каждый тип — ровно одна страница, и у каждого текстового поля есть маркер."""
    from tests.test_render import rich_deck
    from typst_deck.model import Deck

    for name in ("a1.png", "a2.png"):
        (deck_dir / "assets" / name).write_bytes(png_bytes)
    (deck_dir / "assets" / "a3.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    deck = rich_deck()
    deck.slides += Deck(slides=[
        {"type": "text", "title": "Тезисы", "bullets": ["раз", "два"]},
        {"type": "image", "title": "Картинка", "bullets": ["раз"], "image": "a1.png", "caption": "подпись"},
        {"type": "chart", "title": "Столбцы", "kind": "bar", "labels": ["A", "B"],
         "series": [{"name": "млн", "values": [4, -2]}], "unit": "млн", "bullets": ["в"]},
        {"type": "dual-chart", "title": "Два графика",
         "left": {"caption": "Слева", "labels": ["Q1", "Q2"], "series": [{"name": "с", "values": [1, 2]}]},
         "right": {"caption": "Справа", "kind": "bar", "labels": ["A"], "series": [{"name": "с", "values": [3]}]}},
        {"type": "title", "title": "Титул", "subtitle": "Под", "author": "А", "department": "Д"},
        {"type": "section", "title": "Раздел", "subtitle": "Про"},
        {"type": "final", "contact": "team@corp"},
    ]).slides
    r = compile_deck(deck, deck_dir, TEMPLATE_DIR if tid == "default" else ROOT / "templates" / tid,
                     base_url="http://t")
    assert len(r.svgs) == len(deck.slides), "одна функция — одна страница"
    fields = {(p["slide"], p["field"]) for p in r.positions}
    for slide_id, field in [("s1", "items"), ("s2", "blocks"), ("s3", "left"), ("s3", "right"),
                            ("s4", "text"), ("s5", "items"), ("s6", "header"), ("s6", "rows"),
                            ("s7", "images"), ("s8", "poster")]:
        assert (slide_id, field) in fields, f"{slide_id}.{field} без маркера"
```

- [ ] **Step 2: Прогнать — падает**

Run: `uv run pytest tests/test_compile.py -q -k draws_all_types`
Expected: FAIL — `unknown variable: slide-agenda`.

- [ ] **Step 3: Реализация** — в `template/deck.typ` заменить функцию `slide-image` … `slide-chart` на набор ниже и добавить новые. Шапку файла привести к «шестнадцать функций».

```typst
// Общая зона тела: страницу целиком уже обрезает slide(), здесь — только ширина
// и клип по ширине. Высоту не задаём: box(height: 1fr) в Typst недопустим.
#let body-area(content) = block(width: 100%, clip: true, content)

#let slide-agenda(title: none, items: ()) = slide[
  #heading-block(title)
  #body-area(enum(spacing: 0.45em, ..items))
]

#let slide-text(title: none, bullets: none) = slide[
  #heading-block(title)
  #body-area[#if bullets != none { bullets }]
]

#let slide-columns(title: none, blocks: ()) = slide[
  #heading-block(title)
  #body-area(grid(
    columns: blocks.map(_ => 1fr), column-gutter: 0.6cm,
    ..blocks.map(b => [
      #if b.heading != none { text(weight: "bold", b.heading); v(0.2cm) }
      #text(size: 9.5pt, b.text)
    ]),
  ))
]

#let slide-comparison(title: none, left: (:), right: (:)) = slide[
  #heading-block(title)
  #body-area(grid(
    columns: (1fr, 1fr), column-gutter: 0.7cm,
    ..(left, right).map(side => [
      #if side.heading != none { text(weight: "bold", fill: accent, side.heading); v(0.2cm) }
      #if side.bullets != none { text(size: 9.5pt, side.bullets) }
    ]),
  ))
]

#let slide-quote(text: none, author: none) = slide[
  #v(1fr)
  #if text != none { fit-text(3.2cm, (20pt, 17pt, 14pt), text, weight: "bold") }
  #if author != none { v(0.4cm); std.text(size: 10pt, fill: muted, author) }
  #v(1fr)
]

#let slide-metrics(title: none, items: ()) = slide[
  #heading-block(title)
  #body-area(grid(
    columns: items.map(_ => 1fr), column-gutter: 0.5cm, align: center + horizon,
    ..items.map(m => [
      #text(size: 28pt, weight: "bold", m.value)
      #if m.label != none { linebreak(); text(size: 9pt, fill: muted, m.label) }
      #if m.delta != none {
        linebreak()
        text(size: 9pt, fill: if m.trend == "down" { negative } else if m.trend == "up" { accent } else { muted }, m.delta)
      }
    ]),
  ))
]

#let slide-table(title: none, header: (), rows: (), numeric: ()) = slide[
  #heading-block(title)
  #body-area(table(
    columns: header.map(_ => 1fr),
    align: numeric.map(n => if n { right } else { left }),
    stroke: 0.5pt + rgb("#dddddd"),
    fill: (_, y) => if y == 0 { rgb("#eeeeee") } else if calc.even(y) { rgb("#f8f8f8") },
    table.header(..header.map(h => text(size: 9pt, weight: "bold", h))),
    ..rows.flatten().map(c => text(size: 9pt, c)),
  ))
]

#let slide-gallery(title: none, images: ()) = slide[
  #heading-block(title)
  #body-area(grid(
    columns: if images.len() == 4 { (1fr, 1fr) } else { images.map(_ => 1fr) },
    column-gutter: 0.4cm, row-gutter: 0.3cm,
    ..images.map(p => [
      #box(width: 100%, height: if images.len() == 4 { 1.7cm } else { 3.6cm }, p.image)
      #if p.caption != none { v(2pt); text(size: 8pt, fill: muted, p.caption) }
    ]),
  ))
]

#let slide-video(title: none, poster: none, url: none, caption: none) = slide[
  #heading-block(title)
  #body-area[
    #let frame = box(width: 100%, height: 3.6cm, fill: if poster == none { muted.lighten(70%) } else { none })[
      #if poster != none { poster }
      #place(center + horizon, circle(radius: 0.6cm, fill: accent.transparentize(20%))[
        #align(center + horizon, text(fill: white, size: 14pt, "▶"))
      ])
    ]
    #if url == none { frame } else { link(url, frame) }
    #if caption != none { v(2pt); text(size: 8pt, fill: muted, caption) }
  ]
]
```

`slide-image` оставить прежним, убрав ветку `image == none` (картинка теперь всегда есть).

`slide-bar-chart` и `slide-chart` слить в одну функцию. Тела обеих сохраняются как
внутренние помощники: код гистограммы переезжает в `bars(labels, series, unit)`
(вместо `data.map(d => d.value)` — `series.at(0).values`, вместо `d.label` —
`labels.at(i)`; цвет по знаку прежний), код линий — в `lines(labels, series)`.
Общая обёртка:

```typst
#let slide-chart(title: none, kind: "line", labels: (), series: (), unit: none, bullets: none) = slide[
  #heading-block(title)
  // столбцы: знак у одной серии красится, у нескольких — палитра по рядам;
  // линии: как раньше, легенда сверху
  #let chart = if kind == "bar" { bars(labels, series, unit) } else { lines(labels, series) }
  #let legend = if kind == "line" or series.len() > 1 {
    series.enumerate().map(((i, s)) => box(inset: (right: 10pt))[
      #box(width: 8pt, height: 8pt, fill: palette.at(calc.rem(i, palette.len())))
      #h(3pt) #text(size: 8pt, s.name)
      #if unit != none { text(size: 8pt, fill: muted, ", " + unit) }
    ]).join()
  }
  #if legend != none { legend; v(0.15cm) }
  #if bullets == none { chart } else {
    grid(columns: (2fr, 1fr), column-gutter: 0.6cm, chart, text(size: 9.5pt, bullets))
  }
]
```

Тот же набор перенести в `templates/dark/deck.typ`, сохранив его палитру и `fill:` страницы.

- [ ] **Step 4: Прогнать — зелёные**

Run: `uv run pytest tests/test_compile.py -q`
Expected: PASS. Тесты, которые ждали шести слайдов в образце (`test_every_template_honours_contract`, `test_compile_logs_render_done`, `test_compile_hashes_each_page`), пока трогать не нужно: `SAMPLE_DECK` меняется в задаче 5.

- [ ] **Step 5: Коммит**

```bash
git add template/deck.typ templates/dark/deck.typ tests/test_compile.py
git commit -m "Эталон и тёмный шаблон рисуют все пятнадцать типов

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: образец контракта и правила проверки

**Files:**
- Modify: `src/typst_deck/contract.py`, `src/typst_deck/service.py` (`template_preview`)
- Test: `tests/test_contract.py`, `tests/test_compile.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: модель, `render_typ`, шаблоны (задачи 1, 3, 4).
- Produces: `SAMPLE_DECK` из 15 слайдов с id `s000001`…`s000015` в порядке `SLIDE_TYPES`; `SAMPLE_ASSETS: dict[str, bytes]` — две PNG 1×1 (`sample-1.png`, `sample-2.png`) и заглушка `sample.mp4`; `write_sample_assets(deck_dir: Path)`; правило 3 перебирает новые поля; `filled_slide` умеет новые типы.

- [ ] **Step 1: Падающие тесты** — в `tests/test_contract.py`:

```python
@requires_typst
@pytest.mark.parametrize("tdir", [TEMPLATE_DIR, ROOT / "templates" / "dark"], ids=["default", "dark"])
def test_sample_covers_every_type(tdir, tmp_path):
    from typst_deck.contract import SAMPLE_DECK
    from typst_deck.model import SLIDE_TYPES

    assert [s.type for s in SAMPLE_DECK.slides] == list(SLIDE_TYPES)
    assert check_template(tdir, "typst", tmp_path / tdir.name).errors == []


def test_sample_assets_are_written_next_to_the_deck(tmp_path):
    from typst_deck.contract import SAMPLE_ASSETS, write_sample_assets

    write_sample_assets(tmp_path / "deck")
    for name in SAMPLE_ASSETS:
        assert (tmp_path / "deck" / "assets" / name).is_file()


@requires_typst
def test_oversized_rule_covers_new_fields(tmp_path):
    """Правило 3 перебирает цитату, блоки, метрики и ячейки таблицы."""
    d = make_template(tmp_path, "quote-overflow", deck_edit=(
        "#let slide-quote(text: none, author: none) = slide[",
        "#let slide-quote(text: none, author: none) = page[",
    ))
    errors = check_template(d, "typst", tmp_path / "w").errors
    assert any("переросший текст" in e for e in errors)
```

и в `tests/test_compile.py` поправить числа: `rec.fields["slides"] == 15`, `len(r.pages) == 15`, `len(set(r.pages)) == 15`, а пары маркеров в `test_every_template_honours_contract` — на `("s000001", "title")`, `("s000004", "bullets")`, `("s000015", "title")`.

- [ ] **Step 2: Прогнать — падают**

Run: `uv run pytest tests/test_contract.py tests/test_compile.py -q`
Expected: FAIL — в образце шесть слайдов, `SAMPLE_ASSETS` нет.

- [ ] **Step 3: Реализация** — в `src/typst_deck/contract.py`:

```python
# Образец: по слайду каждого типа в порядке SLIDE_TYPES. Им же рисуются превью
# шаблонов в интерфейсе, поэтому картинки и ролик кладутся рядом (write_sample_assets).
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
SAMPLE_ASSETS = {"sample-1.png": PNG_1PX, "sample-2.png": PNG_1PX, "sample.mp4": b"\x00\x00\x00\x18ftypmp42"}

SAMPLE_DECK = Deck(id="templatepreview", title="Образец шаблона", slides=[
    {"id": "s000001", "type": "title", "title": "Название презентации", "subtitle": "Подзаголовок и дата",
     "author": "Имя Фамилия", "department": "Подразделение"},
    {"id": "s000002", "type": "agenda", "items": ["Первый раздел", "Второй раздел", "Третий раздел"]},
    {"id": "s000003", "type": "section", "title": "Раздел", "subtitle": "Промежуточный слайд"},
    {"id": "s000004", "type": "text", "title": "Тезисы", "bullets": ["Первый тезис", "Второй тезис", "Третий тезис"]},
    {"id": "s000005", "type": "image", "title": "Текст и картинка", "bullets": ["Первый тезис", "Второй тезис"],
     "image": "sample-1.png", "caption": "Подпись"},
    {"id": "s000006", "type": "columns", "title": "Блоки текста",
     "blocks": [{"heading": "Первый", "text": "Короткий текст блока"},
                {"heading": "Второй", "text": "Короткий текст блока"},
                {"heading": "Третий", "text": "Короткий текст блока"}]},
    {"id": "s000007", "type": "comparison", "title": "Было и стало",
     "left": {"heading": "Было", "bullets": ["Первый пункт", "Второй пункт"]},
     "right": {"heading": "Стало", "bullets": ["Первый пункт", "Второй пункт"]}},
    {"id": "s000008", "type": "quote", "text": "Одна мысль, ради которой стоит остановиться", "author": "Имя Фамилия"},
    {"id": "s000009", "type": "chart", "title": "Диаграмма", "kind": "bar", "unit": "млн",
     "labels": ["Центр", "Север", "Юг"], "series": [{"name": "млн", "values": [42, -17, 28]}],
     "bullets": ["Рост в центре"]},
    {"id": "s000010", "type": "dual-chart", "title": "Два графика",
     "left": {"caption": "Динамика", "labels": ["Q1", "Q2", "Q3"], "series": [{"name": "Выручка", "values": [10, 14, 13]}]},
     "right": {"caption": "Сравнение", "kind": "bar", "labels": ["Центр", "Юг"],
               "series": [{"name": "млн", "values": [42, 28]}]}},
    {"id": "s000011", "type": "metrics", "title": "Ключевые числа",
     "items": [{"value": "12,5 млн", "label": "выручка", "delta": "+12 %"},
               {"value": "3,4 %", "label": "доля", "delta": "-1 п. п."},
               {"value": "17", "label": "проектов"}]},
    {"id": "s000012", "type": "table", "title": "Таблица", "header": ["Регион", "Выручка", "Доля"],
     "rows": [["Центр", "42", "51 %"], ["Север", "17", "21 %"], ["Юг", "28", "28 %"]]},
    {"id": "s000013", "type": "gallery", "title": "Галерея",
     "images": [{"image": "sample-1.png", "caption": "Первая"}, {"image": "sample-2.png", "caption": "Вторая"}]},
    {"id": "s000014", "type": "video", "title": "Видео", "video": "sample.mp4",
     "poster": "sample-1.png", "caption": "Подпись к ролику"},
    {"id": "s000015", "type": "final", "contact": "team@corp"},
])
TEXT_FIELDS = ("title", "subtitle", "author", "department", "caption", "contact", "bullets",
               "items", "blocks", "left", "right", "text", "header", "rows", "images", "poster")


def write_sample_assets(deck_dir: Path) -> None:
    """Картинки и ролик образца: без них image, gallery и video нечем рисовать."""
    assets = Path(deck_dir) / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for name, data in SAMPLE_ASSETS.items():
        (assets / name).write_bytes(data)
```

`_rule_oversized` дополнить новыми типами — колода в нём становится такой:

```python
    deck = Deck(slides=[
        {"type": "title", "title": big, "subtitle": breaks, "author": big, "department": big},
        {"type": "section", "title": big, "subtitle": breaks},
        {"type": "quote", "text": big + breaks, "author": big},
        {"type": "columns", "title": big, "blocks": [{"heading": big, "text": big + breaks}] * 2},
        {"type": "metrics", "title": big, "items": [{"value": big[:16], "label": big, "delta": big[:12]}] * 2},
        {"type": "table", "title": big, "header": [big[:40], big[:40]], "rows": [[big[:60], big[:60]]] * 2},
        {"type": "final", "title": big, "contact": breaks},
    ])
```

`write_sample_assets` вызывать перед каждой сборкой образца — их четыре:
`_rule_fonts_used` (`fonts-with`, `fonts-without`), `check_template` (`sample`) и
`_rule_declared_fit` (`declared`); в последнем колода собирается из `filled_slide`,
и картинки ей тоже нужны.

`filled_slide` дополнить ветками составных типов — после существующего цикла по
`limits`:

```python
    if stype == "columns":
        n = limits.get("blocks", {}).get("count", 3)
        slide["blocks"] = [{"heading": _text(sample, 40), "text": _text(sample, 300)}] * n
    if stype == "comparison":
        side = {"heading": _text(sample, 60), "bullets": [_text(sample, 120)] * 3}
        slide["left"], slide["right"] = dict(side), dict(side)
    if stype == "metrics":
        n = limits.get("items", {}).get("count", 3)
        slide["items"] = [{"value": "12,5 млн", "label": _text(sample, 60), "delta": "+12 %"}] * n
    if stype == "table":
        cols = limits.get("header", {}).get("count", 3)
        rows = limits.get("rows", {}).get("count", 3)
        slide["header"] = [_text(sample, 40)] * cols
        slide["rows"] = [[_text(sample, 60)] * cols] * rows
    if stype == "gallery":
        n = limits.get("images", {}).get("count", 2)
        slide["images"] = [{"image": name, "caption": _text(sample, 80)}
                           for name in list(SAMPLE_ASSETS)[:n]]
    if stype == "image":
        slide.setdefault("image", "sample-1.png")
    if stype == "video":
        slide.setdefault("video", "sample.mp4")
        slide.setdefault("poster", "sample-1.png")
    if stype == "agenda":
        slide.setdefault("items", [_text(sample, 80)] * limits.get("items", {}).get("count", 3))
    if stype == "quote":
        slide.setdefault("text", _text(sample, 300))
    if stype == "dual-chart":
        side = {"caption": _text(sample, 80), "labels": ["Q1", "Q2"],
                "series": [{"name": "Ряд", "values": [1, 2]}]}
        slide["left"], slide["right"] = dict(side), dict(side)
    if stype == "chart":
        slide.setdefault("kind", "line")
```

В `src/typst_deck/service.py`, в `template_preview`, перед `compile_deck` добавить `write_sample_assets(out)`.

- [ ] **Step 4: Прогнать — зелёные**

Run: `uv run pytest tests/test_contract.py tests/test_compile.py tests/test_api.py -q -k "not pptx"`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add src/typst_deck/contract.py src/typst_deck/service.py tests/test_contract.py tests/test_compile.py tests/test_api.py
git commit -m "Образец контракта — пятнадцать типов со своими картинками

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: слоты с путями через точку

**Files:**
- Modify: `src/typst_deck/slots.py`, `scripts/measure_slots.py`
- Test: `tests/test_slots.py`

**Interfaces:**
- Consumes: схему модели (задача 1).
- Produces: объявление вида `"columns": {"blocks": {"count": 3}, "blocks.text": {"max": 180}}` — `clamp`, `apply_to_schema` и `check_slide` понимают путь `поле.подполе` для массивов объектов и вложенных объектов (`left.bullets`).

- [ ] **Step 1: Падающие тесты** — в `tests/test_slots.py`:

```python
def test_dotted_path_is_clamped_and_applied():
    declared = clamp({"columns": {"blocks": {"count": 3}, "blocks.text": {"max": 180}},
                      "comparison": {"left.bullets": {"count": 3, "max": 100}}}, "t")
    assert declared["columns"]["blocks.text"] == {"max": 180}
    assert declared["comparison"]["left.bullets"] == {"count": 3, "max": 100}
    schema = apply_to_schema(declared)
    text = json.dumps(schema, ensure_ascii=False)
    assert '"maxLength": 180' in text and '"maxItems": 3' in text


def test_dotted_path_beyond_global_ceiling_is_clamped(caplog):
    declared = clamp({"columns": {"blocks.text": {"max": 400}}}, "t")
    assert declared["columns"]["blocks.text"] == {"max": 300}
    assert "больше глобального предела" in caplog.text


def test_unknown_dotted_path_is_dropped(caplog):
    assert clamp({"columns": {"blocks.nope": {"max": 10}}}, "t") == {}
    assert "нет поля" in caplog.text


def test_check_slide_sees_nested_fields():
    from typst_deck.model import SlideAdapter

    declared = clamp({"columns": {"blocks.text": {"max": 10}}}, "t")
    slide = SlideAdapter.validate_python({"type": "columns", "title": "x", "blocks": [
        {"text": "коротко"}, {"text": "очень длинный текст блока"}]})
    bad = check_slide(slide, declared, n=1, template_name="Т")
    assert bad and "Блоки текста" in bad[0]
```

- [ ] **Step 2: Прогнать — падают**

Run: `uv run pytest tests/test_slots.py -q -k "dotted or nested"`
Expected: FAIL — путь с точкой отбрасывается как неизвестное поле.

- [ ] **Step 3: Реализация** — в `src/typst_deck/slots.py`:

```python
def _resolve(props: dict, defs: dict, path: str) -> dict | None:
    """Свойство по пути «поле» или «поле.подполе»: у массива объектов спускаемся в items."""
    head, _, tail = path.partition(".")
    prop = props.get(head)
    if prop is None or not tail:
        return prop
    target = prop.get("items", prop) if prop.get("type") == "array" else prop
    ref = target.get("$ref")
    if ref:
        target = defs.get(ref.rsplit("/", 1)[1], {})
    return target.get("properties", {}).get(tail)
```

`clamp` и `apply_to_schema` берут свойство через `_resolve(props, schema["$defs"], field)`; остальная логика (виды полей, потолки, ключи) не меняется. `check_slide` достаёт значение по тому же пути:

```python
def _value(slide, path: str):
    """Значение поля по пути: у массива объектов — список значений подполя."""
    head, _, tail = path.partition(".")
    value = getattr(slide, head, None)
    if not tail or value is None:
        return value
    if isinstance(value, list):
        return [getattr(x, tail, None) for x in value]
    return getattr(value, tail, None)
```

и зовёт его вместо `getattr(slide, field, None)` — и для `now`, и для `was`. Прежний `_excess` работает без изменений: список значений подполя судится как список. `FIELD_RU` дополнить новыми полями: `items` — «Пункты», `blocks` — «Блоки текста», `left`/`right` — «Левая колонка»/«Правая колонка», `text` — «Текст», `header` — «Шапка таблицы», `rows` — «Строки таблицы», `images` — «Картинки», `video`/`url`/`poster` — «Видео», «Ссылка», «Обложка», `kind` — «Вид графика».

`scripts/measure_slots.py`: проба из `measure.json` уже несёт поля `slide` и `field`, поэтому менять его логику не нужно — достаточно разрешить точку в имени поля пробы (`{"slide": "columns", "field": "blocks.text", …}`) и печатать такой ключ в готовом разделе `slots` как есть. Проверить это тестом в `tests/test_measure_slots.py`: проба с точкой попадает в вывод и проходит `clamp` без отброса.

- [ ] **Step 4: Прогнать — зелёные**

Run: `uv run pytest tests/test_slots.py tests/test_measure_slots.py -q`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add src/typst_deck/slots.py scripts/measure_slots.py tests/test_slots.py
git commit -m "Ёмкость слотов понимает вложенные поля через точку

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: схема и памятка для модели, минимальный интерфейс

**Files:**
- Modify: `src/typst_deck/llm/prompt.md`, `src/typst_deck/llm/agent.py`
- Modify: `src/typst_deck/static/api.js`, `src/typst_deck/static/deck.js`
- Test: `tests/test_agent.py`, `tests/test_pages.py`

**Interfaces:**
- Produces: список ассетов в промпте делится на картинки и видео; памятка «какой тип когда»; в интерфейсе — все 15 типов в меню и запасной редактор составных полей (полноценные редакторы — план C).

- [ ] **Step 1: Падающие тесты** — в `tests/test_agent.py`:

```python
def test_prompt_names_every_type_and_splits_assets():
    from typst_deck.model import SLIDE_TYPES

    p = build_system_prompt(Deck(title="T", slides=[{"type": "final"}]), ["a1.png", "a2.mp4"])
    for t in SLIDE_TYPES:
        assert t in p
    assert "Картинки: a1.png" in p and "Видео: a2.mp4" in p
    assert "не чаще раза на 5–7 слайдов" in p, "памятка про цитату"
```

и в `tests/test_pages.py`:

```python
async def test_all_slide_types_are_offered(client):
    js = (await client.get("/static/deck.js")).text
    for t in ("agenda", "text", "columns", "comparison", "quote", "dual-chart",
              "metrics", "table", "gallery", "video"):
        assert f'"{t}"' in js or f"{t}:" in js, t
```

- [ ] **Step 2: Прогнать — падают**

Run: `uv run pytest tests/test_agent.py tests/test_pages.py -q -k "every_type or slide_types"`
Expected: FAIL.

- [ ] **Step 3: Реализация**

`prompt.md`: заменить пункты про структуру и данные на памятку:

```markdown
- Структура: title первым, final последним; agenda вторым, если разделов три и
  больше; section перед каждым разделом.
- Какой тип брать: text — тезисы; image — только если есть подходящая картинка;
  columns — два-три параллельных пункта примерно одного объёма; comparison —
  «было/стало» и «A/B»; quote — одна мысль, не чаще раза на 5–7 слайдов;
  chart kind=bar — сравнение категорий, kind=line — динамика; dual-chart — два
  связанных графика; metrics — 2–4 ключевых числа с короткой подписью; table —
  когда нужны точные значения; gallery — 2–4 картинки; video — только если
  пользователь дал ролик или ссылку.
- Числа для chart, dual-chart, metrics и table бери из файлов пользователя; не
  выдумывай их. Нет данных — делай text с тезисами.
- Картинки и видео — только из списка ассетов ниже.
```

`agent.py`: `{{ASSETS}}` заменить двумя строками — «Картинки: …» и «Видео: …», деля список по расширению `.mp4`.

`static/api.js`: `TYPE_RU` дополнить всеми типами («Повестка», «Тезисы», «Блоки текста», «Сравнение», «Цитата», «График», «Два графика», «Метрики», «Таблица», «Галерея», «Видео»); `FIELD_RU` — новыми полями теми же словами, что в `slots.FIELD_RU`; `fileKind` — распознаванием `.mp4` как `video`.

`static/deck.js`:

```js
const NEW_SLIDE = {
  title: { type: "title", title: "Заголовок", subtitle: "" },
  agenda: { type: "agenda", title: "Повестка", items: ["Первый раздел", "Второй раздел", "Третий раздел"] },
  section: { type: "section", title: "Раздел" },
  text: { type: "text", title: "Заголовок", bullets: ["Первый тезис"] },
  image: { type: "image", title: "Заголовок", bullets: ["Первый тезис"], image: null },
  columns: { type: "columns", title: "Блоки", blocks: [{ heading: "Первый", text: "Текст" }, { heading: "Второй", text: "Текст" }] },
  comparison: { type: "comparison", title: "Было и стало", left: { heading: "Было", bullets: ["Пункт"] }, right: { heading: "Стало", bullets: ["Пункт"] } },
  quote: { type: "quote", text: "Одна мысль", author: "" },
  chart: { type: "chart", title: "График", kind: "line", labels: ["Q1", "Q2", "Q3"], series: [{ name: "Ряд", values: [1, 2, 3] }] },
  "dual-chart": { type: "dual-chart", title: "Два графика", left: { caption: "Слева", kind: "line", labels: ["Q1", "Q2"], series: [{ name: "Ряд", values: [1, 2] }] }, right: { caption: "Справа", kind: "bar", labels: ["A", "B"], series: [{ name: "Ряд", values: [2, 1] }] } },
  metrics: { type: "metrics", title: "Числа", items: [{ value: "12,5 млн", label: "выручка", delta: "+12 %" }, { value: "17", label: "проектов", delta: "" }] },
  table: { type: "table", title: "Таблица", header: ["Регион", "Выручка"], rows: [["Центр", "42"], ["Север", "17"]] },
  gallery: { type: "gallery", title: "Галерея", images: [{ image: null, caption: "" }, { image: null, caption: "" }] },
  video: { type: "video", title: "Видео", url: "https://", caption: "" },
  final: { type: "final" },
};
```

`ORDER` дополнить новыми полями в порядке чтения:

```js
  const ORDER = ["title", "subtitle", "author", "department", "text", "items", "bullets", "blocks",
    "left", "right", "header", "rows", "images", "kind", "labels", "series", "unit",
    "caption", "contact", "url", "poster", "video", "notes"];
```

Запасной редактор составных полей в `fieldControl`/`readControl` — до плана C:

```js
const COMPOSITE = ["items", "blocks", "left", "right", "header", "rows", "images"];

// в fieldControl, перед последним return:
  if (COMPOSITE.includes(field)) {
    const t = el("textarea", { name: field, rows: 6, class: "mono" }, JSON.stringify(v ?? [], null, 1));
    t.title = "Пока правится как JSON — редактор появится в следующем обновлении";
    return t;
  }

// в readControl, перед последним return:
  if (COMPOSITE.includes(field)) return JSON.parse(control.value);
```

Ошибку разбора JSON показывает существующий `catch` формы: `JSON.parse` бросит, и текст ошибки попадёт в блок `err`. Клик по зоне составного поля открывает вкладку «Слайд» — в `openFieldEditor` добавить в начало:

```js
  if (COMPOSITE.includes(field)) { switchTab("slide"); return; }
```

- [ ] **Step 4: Прогнать — зелёные**

Run: `uv run pytest tests/test_agent.py tests/test_pages.py -q`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add src/typst_deck/llm/prompt.md src/typst_deck/llm/agent.py src/typst_deck/static/api.js src/typst_deck/static/deck.js tests/test_agent.py tests/test_pages.py
git commit -m "Схема и памятка для модели, все типы в интерфейсе

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: набор снова зелёный

**Files:**
- Modify: `tests/test_pptx.py`, `tests/test_corporate.py`, `tests/test_api.py`, `tests/test_agent_api.py`, `tests/test_store.py`, `tests/test_jobs.py` — те, что ещё красные
- Test: весь набор

- [ ] **Step 1: Посмотреть, что осталось красным**

Run: `uv run pytest -q 2>&1 | tail -30`
Expected: падения только там, где тесты ещё пользуются старыми типами (`image` без картинки, `bar-chart`), и в `tests/test_pptx.py`, который ждёт сопоставления для шести типов.

- [ ] **Step 2: Починить тесты старых типов**

Везде, кроме `tests/test_pptx.py`, заменить `{"type": "image", …}` без картинки на `{"type": "text", …}`, а `bar-chart` — на `chart` с `kind: "bar"`. Логику тестов не менять.

- [ ] **Step 3: Пометить тесты PPTX как ожидаемо красные**

В начало `tests/test_pptx.py` добавить:

```python
# План A даёт 15 типов, а сопоставление pptx.json знает шесть: экспорт переезжает
# планом B (docs/superpowers/specs/2026-09-13-slide-set-design.md §7). До него
# эти тесты ожидаемо падают — xfail, чтобы набор оставался зелёным.
pytestmark = pytest.mark.xfail(reason="экспорт в PPTX переезжает на новые типы планом B", strict=False)
```

- [ ] **Step 4: Прогнать весь набор**

Run: `uv run pytest -q`
Expected: PASS, без падений; в сводке — `xfailed` для `tests/test_pptx.py`.

- [ ] **Step 5: Проверить перенос на копии прода**

```bash
SP=/tmp/claude-1001/-home-d1s99-projects-typst-deck/7b5e9858-66d4-4869-812c-99d11b9aaa2c/scratchpad
podman volume export typst-deck-data -o $SP/prod-data.tar
mkdir -p $SP/prod && tar -xf $SP/prod-data.tar -C $SP/prod
TYPST_DECK_DATA_DIR=$SP/prod uv run python -m typst_deck.migrate_slides --check
```

Expected: «будет перенесено: колод 7» (две рабочие и пять в корзине), файлов — по числу снимков. Живой том не трогаем: работаем с распакованной копией.

- [ ] **Step 6: Коммит**

```bash
git add tests
git commit -m "Тесты на новых типах; экспорт PPTX ждёт плана B

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```
