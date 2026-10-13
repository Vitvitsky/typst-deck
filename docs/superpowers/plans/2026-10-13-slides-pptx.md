# Набор слайдов, план B — экспорт PPTX

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** экспорт в редактируемый PPTX собирает все 15 типов слайдов на PowerPoint-мастере шаблона; `pptx.json` описывает все типы и новые ключи оформления; правило 7 контракта проверяет образец целиком.

**Architecture:** `pptx.py` остаётся одним модулем: сопоставление (`Mapping`) знает 15 типов, полнота проверяется по таблицам `PH_FIELDS`/`BODY_KEYS`, а сборка тела слайда идёт через словарь `BODIES` — по функции на тип. Общие куски (тезисы, колонки, картинка, подпись) переиспользуются; графики рисуются по `labels`/`series`/`unit` и потому годятся и для `chart`, и для сторон `dual-chart`. `numeric` и `trend` берутся из `render.py` — те же правила, что у Typst.

**Tech Stack:** Python 3.12, python-pptx 1.0.x (`<2`), Pillow, lxml, pytest (`uv run pytest`), Typst 0.15.1.

**Spec:** `docs/superpowers/specs/2026-09-13-slide-set-design.md` (§7 — экспорт; §9 — тесты; §11 — риски). Прежняя спека экспорта: `docs/superpowers/specs/2026-09-11-pptx-export-design.md`.

## Global Constraints

- Работа идёт в worktree `.worktrees/slides-v2` на ветке `slides-v2`. **В `main` ничего не сливать:** слияние и выкатка — после планов C и D, одним окном (спека §10).
- Комментарии, сообщения и тексты тестов — по-русски, как во всём репозитории.
- Новых зависимостей не добавлять: python-pptx, Pillow и lxml уже есть.
- `uv run pytest` зелёный перед каждым коммитом. Базовая линия ветки: 399 passed, 8 skipped, 12 xfailed. Прогонять **без** `TYPST_DECK_TEST_TEMPLATES`: канон Lemana Tech переводится планом D, его корпоративные тесты до тех пор красные.
- Корпоративного в `src/` нет: мастер, макеты и цвета приходят из шаблона.
- `pptx.json` описывает все 15 типов (спека §7); неизвестные ключи — ошибка (`extra="forbid"`), как и сейчас.
- Временные ключи оформления — ровно из спеки §7: `text.quote`, `text.metric`, `trend.up`, `trend.down`, `table.size`, `table.header_fill`, `table.stripe_fill`, `table.rule`. Они обязательны.
- Файл, который PowerPoint откроет без «восстановить», — главный риск (спека §9, ручная приёмка). XML пишется в порядке схемы OOXML: в `a:pPr` — `a:spcBef`, затем `a:buClr`, затем `a:buFont`/`a:buAutoNum`/`a:buChar`; в `a:tcPr` — линии `a:lnL`, `a:lnR`, `a:lnT`, `a:lnB` раньше заливки.
- Каждое сообщение коммита заканчивается строкой `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Отклонения от спеки, принятые при планировании

1. **У `columns` два варианта сопоставления, и они взаимоисключающие.** `ph.blocks` — список idx не короче трёх (столько блоков допускает `ColumnsSlide`), тогда `body` и `gap` запрещены; без `ph.blocks` обязательны `body` и `gap`. Спека говорит «либо зона», не уточняя, что ключи второго варианта в первом — ошибка.
2. **Заглушка обложки видео** рисуется Pillow: фон `table.header_fill`, треугольник «▶» цвета `text.bullet`. Спека говорит «цветами сопоставления», не называя каких.
3. **Рамка видео** вписывается в зону с пропорциями обложки, а без обложки — 16:9; подпись — под рамкой полосой `CAPTION_STRIP`, как у картинки.
4. **Высота строки таблицы** — зона, делённая на число строк, но не больше 15 мм: таблица из двух строк не растягивается на всю зону.
5. **Пропавшие файлы** (картинка галереи, ролик, обложка) не роняют экспорт: предупреждение в `warnings`, как у `image`. Ролика нет — ставится обложка без видео; клетка галереи без картинки остаётся пустой, сетка не сдвигается.

## Review Focus

1. **Пропавшие ассеты** — колода с видео, галереей и обложкой, у которой в `assets/` нет файлов (правило 7 и старые колоды): файл собирается, всё перечислено в `warnings`. Тест — задача 5.
2. **Управляющие символы и `\n` в новых текстовых полях** (блоки, стороны сравнения, цитата, метрики, ячейки таблицы, подписи галереи): в XML нет мусора `_x001F_`, перевод строки — разрыв строки. Тест — задачи 2 и 4.
3. **`&` и `<` в единице, именах рядов и подписях** у многорядной гистограммы и у `dual-chart`: файл открывается заново. Тест — задача 3.
4. **Меньше блоков, чем заполнителей** (2 блока при `ph.blocks` из трёх): лишний заполнитель удалён, а не показывает подсказку макета. Тест — задача 2.
5. **Таблица на пределах модели** (шапка 6 колонок, 8 строк, ячейки по 40 знаков) и **ссылка видео с `&` и `?`**: таблица целиком в зоне, ссылка цела. Тесты — задачи 4 и 5.

---

### Task 1: Сопоставление на 15 типов

**Files:**
- Modify: `src/typst_deck/pptx.py:37-207` (константы, модели сопоставления, `_completeness`, `open_master`, `_fill`, `export_pptx`)
- Modify: `tests/conftest.py:72-90` (`PPTX_MAPPING`)
- Test: `tests/test_pptx.py` (раздел «сопоставление», `BROKEN`)

**Interfaces:**
- Consumes: `typst_deck.model.SLIDE_TYPES` — кортеж 15 типов в порядке каталога.
- Produces:
  - `pptx.SLIDE_TYPES` — тот же кортеж (реэкспорт из `model`);
  - `pptx.ph_fields(stype: str) -> tuple[str, ...]` — поля, обязанные лежать в заполнителях;
  - `pptx.BLOCKS = 3`;
  - модели `TextStyle(size, bullet, caption, quote, metric)`, `TrendStyle(up, down)`, `TableStyle(size, header_fill, stripe_fill, rule)`, `Mapping(master, font, text, chart, trend, table, slides)`;
  - `SlideMap.ph: dict[str, int | list[int]]`, список допустим только у `columns.blocks`;
  - `BODIES: dict[str, Callable[[Ctx], set[int]]]` — тело слайда по типу; функция возвращает idx заполнителей, которые она заполнила сама (их `_fill` не удаляет);
  - `Ctx` — dataclass `slide, s, sm, m, assets, tmp, typst_bin, warnings, n`;
  - `_fill(slide, s, sm, keep: set[int] = frozenset())`.

- [ ] **Step 1: Синтетическое сопоставление на 15 типов** — в `tests/conftest.py` заменить `PPTX_MAPPING`:

```python
# Сопоставление синтетического мастера: макеты стандартного мастера python-pptx.
# «Title and Content» у image — нарочно: его idx 1 не сопоставлен, на нём
# проверяется удаление лишнего заполнителя. columns — вариант с зоной; вариант
# с заполнителями ph.blocks проверяется отдельно на макете «Comparison».
ZONE = [20, 80, 600, 260]
PPTX_MAPPING = {
    "master": "master.pptx",
    "text": {"size": 24, "bullet": "FFDE00", "caption": "666666", "quote": 40, "metric": 60},
    "chart": {"palette": ["FFDE00", "1E1E1E", "00FFE0"], "negative": "FF2E00"},
    "trend": {"up": "1E1E1E", "down": "FF2E00"},
    "table": {"size": 18, "header_fill": "DDDDDD", "stripe_fill": "F8F8F8", "rule": "BBBBBB"},
    "slides": {
        "title": {"layout": "Title Slide", "ph": {"title": 0, "subtitle": 1, "author": 21, "department": 21}},
        "agenda": {"layout": "Title Only", "ph": {"title": 0}, "body": ZONE},
        "section": {"layout": "Section Header", "ph": {"title": 0, "subtitle": 1}},
        "text": {"layout": "Title Only", "ph": {"title": 0}, "body": ZONE},
        "image": {"layout": "Title and Content", "ph": {"title": 0}, "body": ZONE,
                  "image_width": {"small": 30, "medium": 42, "large": 55}, "gap": 15},
        "columns": {"layout": "Title Only", "ph": {"title": 0}, "body": ZONE, "gap": 10},
        "comparison": {"layout": "Title Only", "ph": {"title": 0}, "body": ZONE, "gap": 20},
        "quote": {"layout": "Blank", "ph": {}, "body": ZONE},
        "chart": {"layout": "Title Only", "ph": {"title": 0}, "body": ZONE,
                  "text_width": 38, "gap": 12, "heading": "Выводы"},
        "dual-chart": {"layout": "Title Only", "ph": {"title": 0}, "body": ZONE, "gap": 20},
        "metrics": {"layout": "Title Only", "ph": {"title": 0}, "body": ZONE, "gap": 15},
        "table": {"layout": "Title Only", "ph": {"title": 0}, "body": ZONE},
        "gallery": {"layout": "Title Only", "ph": {"title": 0}, "body": ZONE, "gap": 12},
        "video": {"layout": "Title Only", "ph": {"title": 0}, "body": ZONE},
        "final": {"layout": "Title Slide", "ph": {"title": 0, "contact": 1}},
    },
}
```

- [ ] **Step 2: Падающие тесты сопоставления** — в `tests/test_pptx.py` дополнить `BROKEN` (старые случаи с `bar-chart` в словаре нет, `missing-type` уже про `final`):

```python
    "missing-new-type": (lambda m: m["slides"].pop("metrics"), "нет типа metrics"),
    "old-type": (lambda m: m["slides"].update({"bar-chart": m["slides"]["chart"]}), "bar-chart"),
    "no-trend": (lambda m: m.pop("trend"), "trend"),
    "no-table-style": (lambda m: m.pop("table"), "table"),
    "no-quote-size": (lambda m: m["text"].pop("quote"), "text.quote"),
    "quote-title-ph": (lambda m: m["slides"]["quote"]["ph"].update(title=0), "title не кладётся"),
    "no-gap": (lambda m: m["slides"]["metrics"].pop("gap"), "slides.metrics: нет gap"),
    "blocks-not-columns": (lambda m: m["slides"]["text"]["ph"].update(blocks=[1, 2, 3]), "blocks не кладётся"),
    "blocks-too-few": (lambda m: m["slides"]["columns"].update(
        layout="Comparison", ph={"title": 0, "blocks": [1, 2]}, body=None, gap=None),
        "нужно не меньше 3 заполнителей"),
    "blocks-and-zone": (lambda m: m["slides"]["columns"].update(
        layout="Comparison", ph={"title": 0, "blocks": [1, 2, 3]}),
        "slides.columns: body у этого типа не бывает"),
    "blocks-idx-missing": (lambda m: m["slides"]["columns"].update(
        layout="Comparison", ph={"title": 0, "blocks": [1, 2, 9]}, body=None, gap=None),
        "нет заполнителя idx 9"),
    "title-as-list": (lambda m: m["slides"]["text"]["ph"].update(title=[0]), "ожидается один idx"),
```

и добавить тест, что вариант с заполнителями сам по себе годен:

```python
def test_columns_on_placeholders_is_a_good_mapping(tmp_path):
    check(make_pptx_template(tmp_path, mapping_edit=lambda m: m["slides"]["columns"].update(
        layout="Comparison", ph={"title": 0, "blocks": [1, 2, 3]}, body=None, gap=None)))
```

(`body=None, gap=None` пишется в JSON как `null` — модель принимает это как «не задано».)

- [ ] **Step 3: Убедиться, что падают**

Run: `uv run pytest tests/test_pptx.py -q -k "broken or good or columns_on"`
Expected: FAIL — `test_good_mapping_passes` падает на неизвестных типах (`agenda` нет в `Literal`), новые случаи `BROKEN` не находят своих текстов.

- [ ] **Step 4: Модели и полнота** — в `src/typst_deck/pptx.py`:

```python
from dataclasses import dataclass
from typing import Annotated, Callable, Literal

from .model import SLIDE_TYPES, Deck

MM = 36000  # EMU в миллиметре
# Поля, которые обязаны лежать в заполнителях, — в порядке модели: он же задаёт
# порядок абзацев, когда несколько полей делят один заполнитель. Типам, которых
# здесь нет, нужен только заголовок. Остальное идёт в зону body, notes — в заметки.
PH_FIELDS = {
    "title": ("title", "subtitle", "author", "department"),
    "section": ("title", "subtitle"),
    "final": ("title", "contact"),
    "quote": (),
}
# Ключи зоны тела: у типа из этого словаря они обязательны, у прочих запрещены.
BODY_KEYS = {
    "agenda": ("body",), "text": ("body",), "quote": ("body",),
    "table": ("body",), "video": ("body",),
    "image": ("body", "image_width", "gap"),
    "columns": ("body", "gap"),  # только без ph.blocks — см. _body_keys
    "comparison": ("body", "gap"), "dual-chart": ("body", "gap"),
    "metrics": ("body", "gap"), "gallery": ("body", "gap"),
    "chart": ("body", "text_width", "gap"),
}
OPTIONAL_KEYS = {"chart": ("heading",)}
BLOCKS = 3  # столько блоков допускает ColumnsSlide.blocks (max_length в model.py)


def ph_fields(stype: str) -> tuple[str, ...]:
    return PH_FIELDS.get(stype, ("title",))


def _body_keys(stype: str, sm: "SlideMap") -> tuple[str, ...]:
    if stype == "columns" and "blocks" in sm.ph:
        return ()  # блоки в заполнителях мастера — зона и зазор не нужны
    return BODY_KEYS.get(stype, ())
```

Модели:

```python
class TextStyle(_Strict):
    size: float = Field(gt=0)    # кегль тезисов, пт
    bullet: Hex                  # цвет маркера тезисов и номеров повестки
    caption: Hex                 # цвет подписей: картинки, автора цитаты, метрики
    quote: float = Field(gt=0)   # кегль цитаты, пт
    metric: float = Field(gt=0)  # кегль крупного числа метрики, пт


class TrendStyle(_Strict):
    up: Hex    # изменение метрики со знаком «+»
    down: Hex  # изменение со знаком «-» или тире


class TableStyle(_Strict):
    size: float = Field(gt=0)  # кегль ячеек, пт
    header_fill: Hex           # заливка шапки
    stripe_fill: Hex           # заливка чётных строк («зебра»)
    rule: Hex                  # цвет тонких линий


class SlideMap(_Strict):
    layout: str
    # поле → idx заполнителя; у заголовка 0. Список — только у columns.blocks
    ph: dict[str, int | list[int]]
    body: tuple[float, float, float, float] | None = None
    image_width: dict[Literal["small", "medium", "large"], Percent] | None = None
    text_width: Percent | None = None
    gap: float | None = Field(default=None, ge=0)
    heading: str | None = None


SlideType = Literal["title", "agenda", "section", "text", "image", "columns", "comparison",
                    "quote", "chart", "dual-chart", "metrics", "table", "gallery", "video", "final"]


class Mapping(_Strict):
    master: str
    font: str | None = Field(default=None, min_length=1)
    text: TextStyle
    chart: ChartStyle
    trend: TrendStyle
    table: TableStyle
    slides: dict[SlideType, SlideMap]
```

Рядом с `SlideType` — сторож расхождения с моделью (сработает при импорте, если тип добавят в одном месте):

```python
assert set(SlideType.__args__) == set(SLIDE_TYPES), "pptx.SlideType разошёлся с model.SLIDE_TYPES"
```

`_completeness` — проверки `ph` и ключей тела по новым таблицам (проверки ширин у `image` и `chart` остаются как были, у `chart` вместо `("bar-chart", "chart")` — только `"chart"`):

```python
def _completeness(m: Mapping) -> list[str]:
    """Правила полноты спеки §7, которые не выражаются типами."""
    problems = [f"slides: нет типа {t}" for t in SLIDE_TYPES if t not in m.slides]
    for stype, sm in m.slides.items():
        need = ph_fields(stype)
        allowed_ph = need + (("blocks",) if stype == "columns" else ())
        problems += [f"slides.{stype}.ph: нет поля {f}" for f in need if f not in sm.ph]
        for f, v in sm.ph.items():
            if f not in allowed_ph:
                problems.append(f"slides.{stype}.ph: поле {f} не кладётся в заполнитель")
            elif f == "blocks":
                if not isinstance(v, list) or len(v) < BLOCKS:
                    problems.append(f"slides.{stype}.ph.blocks: нужно не меньше {BLOCKS} заполнителей")
            elif isinstance(v, list):
                problems.append(f"slides.{stype}.ph.{f}: ожидается один idx, а не список")
        body = _body_keys(stype, sm)
        allowed = body + OPTIONAL_KEYS.get(stype, ())
        for key in ("body", "image_width", "text_width", "gap", "heading"):
            value = getattr(sm, key)
            if key in body and value is None:
                problems.append(f"slides.{stype}: нет {key}")
            elif key not in allowed and value is not None:
                problems.append(f"slides.{stype}: {key} у этого типа не бывает")
        # ... проверки image_width, ширины колонок image и chart — без изменений,
        # условие графика: if stype == "chart" and ...
    return problems
```

В `open_master` сверка idx — с разворачиванием списка:

```python
        for f, i in sm.ph.items():
            for idx in (i if isinstance(i, list) else [i]):
                if idx not in have:
                    problems.append(f"slides.{stype}.ph.{f}: в макете «{sm.layout}» нет заполнителя idx {idx}")
```

- [ ] **Step 5: Диспетчер тел и `_fill` с `keep`**

```python
@dataclass
class Ctx:
    """Всё, что нужно функции тела слайда; собирается в export_pptx на каждый слайд."""
    slide: object
    s: object
    sm: SlideMap
    m: Mapping
    assets: Path
    tmp: Path
    typst_bin: str
    warnings: list[str]
    n: int


def _fill(slide, s, sm: SlideMap, keep: frozenset[int] | set[int] = frozenset()) -> None:
    """Поля — в заполнители по idx; пустые и несопоставленные заполнители удаляются,
    иначе при правке в PowerPoint видна подсказка макета («Уровень текста 1…»).
    keep — заполнители, которые уже заполнила функция тела (блоки columns)."""
    groups: dict[int, list[str]] = {}
    for f in ph_fields(s.type):
        value = clean(getattr(s, f) or "")
        if value.strip():
            groups.setdefault(sm.ph[f], []).append(value)
    for ph in list(slide.placeholders):
        idx = ph.placeholder_format.idx
        if idx in keep:
            continue
        texts = groups.get(idx)
        # ... дальше без изменений
```

`_image_body` и `_chart_body` переписать на `Ctx` (тело прежнее; `_chart_body` в этой задаче рисует по-старому — линией, задача 3 его заменит):

```python
def _image_body(c: Ctx) -> set[int]:
    img = _image_file(c.s.image, c.assets, c.tmp, c.typst_bin, c.warnings, c.n)
    # ... прежнее тело _image_body с s → c.s, sm → c.sm, style → c.m.text
    return set()


def _chart_body(c: Ctx) -> set[int]:
    box = _mm_box(c.sm.body)
    if not c.s.bullets:
        _line_chart(c.slide, c.s, box, c.m.chart)
        return set()
    text_box, chart_box = _columns(box, c.sm.text_width, c.sm.gap)
    _bullets(c.slide, text_box, c.s.bullets, c.m.text, heading=c.sm.heading)
    _line_chart(c.slide, c.s, chart_box, c.m.chart)
    return set()


BODIES: dict[str, Callable[[Ctx], set[int]]] = {"image": _image_body, "chart": _chart_body}
```

`_image_file` принимает имя файла, а не слайд — его позовут и галерея, и видео:

```python
def _image_file(name: str, assets_dir: Path, tmp: Path, typst_bin: str,
                warnings: list[str], n: int) -> Path | None:
    """Файл картинки; SVG — растром. Пропавшая или нерастеризуемая — None и предупреждение,
    как у PDF: слайд собирается без неё."""
    if not name:
        return None
    # ... прежнее тело с s.image → name
```

Цикл в `export_pptx`:

```python
        for n, s in enumerate(deck.slides, 1):
            sm = m.slides[s.type]
            layout = layouts[sm.layout]
            slide = prs.slides.add_slide(layout)
            body = BODIES.get(s.type)
            keep = body(Ctx(slide, s, sm, m, Path(assets_dir), Path(tmp), typst_bin, warnings, n)) if body else set()
            _fill(slide, s, sm, keep)
            _slide_number(slide, layout, n)
            if s.notes.strip():
                slide.notes_slide.notes_text_frame.text = clean(s.notes)
```

Удалить `bar-chart` отовсюду в `pptx.py` и `_bar_chart` пока оставить — задача 3 перепишет его на новые поля.

- [ ] **Step 6: Тесты сопоставления зелёные**

Run: `uv run pytest tests/test_pptx.py -q -k "broken or good or columns_on or unreadable or mapping_path or broken_master"`
Expected: PASS.

- [ ] **Step 7: Весь набор**

Run: `uv run pytest -q`
Expected: зелёный; xfail-тесты экспорта по-прежнему xfail или xpass (`strict=False`) — снимаются в задачах 2–6.

- [ ] **Step 8: Коммит**

```bash
git add src/typst_deck/pptx.py tests/conftest.py tests/test_pptx.py
git commit -m "PPTX: сопоставление на 15 типов и новые ключи оформления

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Текстовые типы — повестка, тезисы, блоки, сравнение, цитата

**Files:**
- Modify: `src/typst_deck/pptx.py` (`_bullets`, новые `_agenda_body`, `_text_body`, `_columns_body`, `_comparison_body`, `_quote_body`, `_paragraph`, `_split`; `BODIES`)
- Test: `tests/test_pptx.py`

**Interfaces:**
- Consumes: `Ctx`, `BODIES`, `_fill(keep)` из задачи 1.
- Produces:
  - `_bullets(slide, box, items, style, heading=None, numbered=False)`;
  - `_split(box, n: int, gap_mm: float) -> list[tuple[int, int, int, int]]` — n равных колонок с зазором; ею пользуются задачи 3–5.

- [ ] **Step 1: Падающие тесты**

```python
def test_agenda_is_a_numbered_list_in_the_zone(tdir):
    deck = Deck(slides=[{"type": "agenda", "items": ["Итоги", "Планы", "Риски"]}])
    slide = export(tdir, deck).slides[0]
    assert by_idx(slide)[0] == ["Повестка"]
    [box] = boxes(slide)
    assert inside(box) and [p.text for p in box.text_frame.paragraphs] == ["Итоги", "Планы", "Риски"]
    for p in box.text_frame.paragraphs:
        assert p._p.xpath("./a:pPr/a:buAutoNum[@type='arabicPeriod']")
        assert p._p.xpath("./a:pPr/a:buClr/a:srgbClr[@val='FFDE00']")


def test_text_bullets_take_the_whole_zone(tdir):
    slide = export(tdir, Deck(slides=[{"type": "text", "title": "Т", "bullets": ["раз", "два"]}])).slides[0]
    [box] = boxes(slide)
    assert (box.left, box.top, box.width, box.height) == tuple(int(v * MM) for v in ZONE)
    assert [p.text for p in box.text_frame.paragraphs] == ["раз", "два"]


def test_columns_split_the_zone(tdir):
    deck = Deck(slides=[{"type": "columns", "title": "Т", "blocks": [
        {"heading": "Первый", "text": "раз"}, {"heading": "", "text": "два"}, {"heading": "Третий", "text": "три"}]}])
    cols = sorted(boxes(export(tdir, deck).slides[0]), key=lambda b: b.left)
    assert len(cols) == 3 and all(inside(b) for b in cols)
    assert cols[1].left - (cols[0].left + cols[0].width) == 10 * MM  # gap
    first = cols[0].text_frame.paragraphs
    assert [p.text for p in first] == ["Первый", "раз"] and first[0].runs[0].font.bold
    assert [p.text for p in cols[1].text_frame.paragraphs] == ["два"]  # пустой заголовок не печатается


def test_columns_on_placeholders_drop_the_spare_one(tmp_path):
    tdir = make_pptx_template(tmp_path, mapping_edit=lambda m: m["slides"]["columns"].update(
        layout="Comparison", ph={"title": 0, "blocks": [1, 2, 3]}, body=None, gap=None))
    deck = Deck(slides=[{"type": "columns", "title": "Т", "blocks": [
        {"heading": "Первый", "text": "раз"}, {"heading": "Второй", "text": "два"}]}])
    slide = export(tdir, deck).slides[0]
    got = by_idx(slide)
    assert got[1] == ["Первый", "раз"] and got[2] == ["Второй", "два"]
    assert 3 not in got and 4 not in got  # третьего блока нет, idx 4 не сопоставлен
    assert boxes(slide) == []


def test_comparison_two_columns_with_headings(tdir):
    deck = Deck(slides=[{"type": "comparison", "title": "Т",
                         "left": {"heading": "Было", "bullets": ["а"]},
                         "right": {"heading": "Стало", "bullets": ["б", "в"]}}])
    left, right = sorted(boxes(export(tdir, deck).slides[0]), key=lambda b: b.left)
    assert [p.text for p in left.text_frame.paragraphs] == ["Было", "а"]
    assert [p.text for p in right.text_frame.paragraphs] == ["Стало", "б", "в"]
    assert left.width == right.width and right.left - (left.left + left.width) == 20 * MM


def test_quote_is_centered_on_a_layout_without_title(tdir):
    deck = Deck(slides=[{"type": "quote", "text": "Мысль", "author": "Автор"}])
    slide = export(tdir, deck).slides[0]
    [box] = boxes(slide)
    assert inside(box) and box.text_frame.vertical_anchor == MSO_ANCHOR.MIDDLE
    quote, author = box.text_frame.paragraphs
    assert quote.alignment == PP_ALIGN.CENTER and quote.runs[0].font.size == Pt(40)
    assert author.text == "Автор" and str(author.runs[0].font.color.rgb) == "666666"
    assert set(by_idx(slide)) <= {12}  # кроме номера слайда заполнителей нет


def test_text_fields_drop_control_characters(tdir):
    deck = Deck(slides=[
        {"type": "columns", "title": "Т", "blocks": [{"text": "раз\x1f\nдва"}, {"text": "три"}]},
        {"type": "quote", "text": "мысль\x0b"},
    ])
    prs = export(tdir, deck)
    xml = b"".join(etree.tostring(s._element) for s in prs.slides)
    assert b"_x001F_" not in xml and b"_x000B_" not in xml
    first = sorted(boxes(prs.slides[0]), key=lambda b: b.left)[0]
    assert first._element.xpath(".//a:br")  # \n — разрыв строки внутри абзаца
```

Импорты в начало файла: `from pptx.enum.text import MSO_ANCHOR, PP_ALIGN`, `from pptx.util import Mm, Pt`, `from tests.conftest import ZONE as _ZONE` не нужен — `ZONE` в тестах уже есть.

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/test_pptx.py -q -k "agenda or text_bullets or columns or comparison or quote or control_characters"`
Expected: FAIL — у типов нет тел, надписей на слайде нет.

- [ ] **Step 3: Реализация**

```python
def _split(box, n: int, gap_mm: float) -> list[tuple[int, int, int, int]]:
    """n равных колонок зоны с зазором gap_mm между ними."""
    x, y, w, h = box
    g = int(gap_mm * MM)
    cw = (w - g * (n - 1)) // n
    return [(x + i * (cw + g), y, cw, h) for i in range(n)]


def _paragraph(tf, k: int, text: str, size: float, *, bold=False, color: str | None = None,
               align=None, keep_newlines=True):
    """k-й абзац надписи: первый уже есть, остальные добавляются."""
    p = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
    text = clean(text)
    p.text = text.replace("\n", "\v") if keep_newlines else text.replace("\n", " ")
    if align is not None:
        p.alignment = align
    for r in p.runs:
        r.font.size = Pt(size)
        r.font.bold = bold or None
        if color:
            r.font.color.rgb = RGBColor.from_string(color.upper())
    return p


def _textbox(slide, box):
    x, y, w, h = box
    tf = slide.shapes.add_textbox(Emu(x), Emu(y), Emu(w), Emu(h)).text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    return tf
```

`_bullets` получает `numbered` и строит абзацы через `_paragraph`; маркер пишется в порядке схемы — `p.space_before` раньше `buClr`, `buClr` раньше `buAutoNum`/`buChar`:

```python
def _bullets(slide, box, items: list[str], style: TextStyle, heading: str | None = None,
             numbered: bool = False) -> None:
    """Тезисы надписью в зоне: маркер (или номер) цвета style.bullet, шрифт — из темы мастера."""
    tf = _textbox(slide, box)
    paras = ([(heading, False)] if heading else []) + [(i, True) for i in items]
    for k, (text, bullet) in enumerate(paras):
        p = _paragraph(tf, k, text, style.size, bold=not bullet)
        if k:
            p.space_before = Pt(style.size * 0.5)
        if bullet:
            ppr = p._p.get_or_add_pPr()
            ppr.set("marL", str(Mm(10 if numbered else 8)))
            ppr.set("indent", str(-Mm(10 if numbered else 8)))
            clr = etree.SubElement(ppr, qn("a:buClr"))
            etree.SubElement(clr, qn("a:srgbClr"), val=style.bullet.upper())
            if numbered:
                etree.SubElement(ppr, qn("a:buAutoNum"), type="arabicPeriod")
            else:
                etree.SubElement(ppr, qn("a:buChar"), char="•")
```

Тела:

```python
def _agenda_body(c: Ctx) -> set[int]:
    _bullets(c.slide, _mm_box(c.sm.body), c.s.items, c.m.text, numbered=True)
    return set()


def _text_body(c: Ctx) -> set[int]:
    _bullets(c.slide, _mm_box(c.sm.body), c.s.bullets, c.m.text)
    return set()


def _block_text(tf, block, style: TextStyle) -> None:
    """Блок columns: жирный заголовок (если есть), затем текст."""
    k = 0
    if block.heading.strip():
        _paragraph(tf, k, block.heading, style.size, bold=True)
        k += 1
    p = _paragraph(tf, k, block.text, style.size)
    if k:
        p.space_before = Pt(style.size * 0.5)


def _columns_body(c: Ctx) -> set[int]:
    idxs = c.sm.ph.get("blocks")
    if idxs:  # блоки в заполнителях мастера; лишние удалит _fill — их нет в keep
        by_idx = {ph.placeholder_format.idx: ph for ph in c.slide.placeholders}
        used = set()
        for block, idx in zip(c.s.blocks, idxs):
            tf = by_idx[idx].text_frame
            tf.clear()
            _block_text(tf, block, c.m.text)
            used.add(idx)
        return used
    for block, box in zip(c.s.blocks, _split(_mm_box(c.sm.body), len(c.s.blocks), c.sm.gap)):
        _block_text(_textbox(c.slide, box), block, c.m.text)
    return set()


def _comparison_body(c: Ctx) -> set[int]:
    left, right = _split(_mm_box(c.sm.body), 2, c.sm.gap)
    for side, box in ((c.s.left, left), (c.s.right, right)):
        _bullets(c.slide, box, side.bullets, c.m.text, heading=side.heading.strip() or None)
    return set()


def _quote_body(c: Ctx) -> set[int]:
    tf = _textbox(c.slide, _mm_box(c.sm.body))
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    _paragraph(tf, 0, c.s.text, c.m.text.quote, align=PP_ALIGN.CENTER)
    if c.s.author.strip():
        p = _paragraph(tf, 1, c.s.author, c.m.text.size, color=c.m.text.caption, align=PP_ALIGN.CENTER)
        p.space_before = Pt(c.m.text.size)
    return set()
```

`tf.clear()` в заполнителе оставляет один пустой абзац — `_paragraph(tf, 0, …)` пишет в него. Удаление неиспользованных заполнителей блоков делает `_fill`: их idx не в `keep` и не в `groups`.

Импорт: `from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN`. В `BODIES` добавить `agenda`, `text`, `columns`, `comparison`, `quote`.

- [ ] **Step 4: Тесты зелёные**

Run: `uv run pytest tests/test_pptx.py -q`
Expected: новые тесты PASS; старые тесты `image` и сопоставления PASS.

- [ ] **Step 5: Коммит**

```bash
git add src/typst_deck/pptx.py tests/test_pptx.py
git commit -m "PPTX: повестка, тезисы, блоки, сравнение и цитата

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Графики — `chart` с видом и `dual-chart`

**Files:**
- Modify: `src/typst_deck/pptx.py` (`_bar_chart`, `_line_chart`, `_chart_body`, новый `_dual_chart_body`)
- Test: `tests/test_pptx.py` (снять `xfail` с трёх тестов гистограммы, переписав их на `chart` с `kind: "bar"`)

**Interfaces:**
- Consumes: `Ctx`, `_split`, `_caption`, `CAPTION_STRIP` из задач 1–2.
- Produces: `_draw_chart(slide, src, box, cs: ChartStyle)` — `src` с полями `kind`, `labels`, `series`, `unit` (годится `ChartSlide` и `ChartSide`).

- [ ] **Step 1: Переписать xfail-тесты гистограммы и добавить новые**

Снять `@pytest.mark.xfail` с `test_bar_colors_follow_the_sign`, `test_bar_chart_survives_special_characters_in_unit`, `test_chart_takes_the_zone_or_shares_it_with_bullets` и заменить в них колоды:

```python
def bar(**kw) -> dict:
    return {"type": "chart", "kind": "bar", "title": "Итоги", "unit": "млн",
            "labels": ["Центр", "Север", "Юг"], "series": [{"name": "млн", "values": [42, -17, 28]}]} | kw


def test_bar_colors_follow_the_sign(tdir):
    chart = chart_of(export(tdir, Deck(slides=[bar()])).slides[0])
    assert colors(chart, ".//c:dPt//a:srgbClr") == ["FFDE00", "FF2E00", "FFDE00"]
    assert chart._chartSpace.xpath(".//c:invertIfNegative[@val='0']")
    assert chart.plots[0].data_labels.number_format == 'General" млн"'
    assert not chart.has_legend


def test_bar_chart_survives_special_characters_in_unit(tdir):
    deck = Deck(slides=[bar(unit="R&D <x>\x01", labels=["Центр"], series=[{"name": "R&D", "values": [42]}])])
    chart = chart_of(export(tdir, deck).slides[0])
    assert chart.plots[0].data_labels.number_format == 'General" R&D <x>"'


def test_chart_takes_the_zone_or_shares_it_with_bullets(tdir):
    alone, shared = export(tdir, Deck(slides=[bar(), bar(bullets=["Рост"])])).slides
    # ... тело теста без изменений
```

Новые:

```python
def test_bar_with_several_series_takes_the_palette_and_a_legend(tdir):
    deck = Deck(slides=[bar(series=[{"name": "2025 & <план>", "values": [1, -2, 3]},
                                    {"name": "2026", "values": [2, 3, 4]}])])
    chart = chart_of(export(tdir, deck).slides[0])
    assert colors(chart, ".//c:ser/c:spPr/a:solidFill/a:srgbClr") == ["FFDE00", "1E1E1E"]
    assert not chart._chartSpace.xpath(".//c:dPt")  # по знаку красится только одна серия
    assert chart.has_legend and chart.legend.position == XL_LEGEND_POSITION.TOP
    assert [s.name for s in chart.plots[0].series] == ["2025 & <план>", "2026"]


def test_line_kind_draws_lines(tdir):
    deck = Deck(slides=[bar(kind="line")])
    chart = chart_of(export(tdir, deck).slides[0])
    assert chart.chart_type == XL_CHART_TYPE.LINE_MARKERS


def test_dual_chart_two_charts_with_captions(tdir):
    side = {"labels": ["Q1", "Q2"], "series": [{"name": "Ряд", "values": [1, 2]}]}
    deck = Deck(slides=[{"type": "dual-chart", "title": "Т",
                         "left": side | {"caption": "Динамика & <рост>"},
                         "right": side | {"caption": "", "kind": "bar", "unit": "%"}}])
    slide = export(tdir, deck).slides[0]
    frames = sorted((sh for sh in slide.shapes if sh.has_chart), key=lambda sh: sh.left)
    assert len(frames) == 2 and all(inside(f) for f in frames)
    assert frames[0].chart.chart_type == XL_CHART_TYPE.LINE_MARKERS
    assert frames[1].chart.chart_type == XL_CHART_TYPE.COLUMN_CLUSTERED
    assert frames[1].left - (frames[0].left + frames[0].width) == 20 * MM
    [cap] = boxes(slide)  # у правой подписи нет — полосы под неё тоже
    assert cap.text_frame.text == "Динамика & <рост>" and cap.top < frames[0].top
    assert frames[1].top == int(ZONE[1] * MM)  # без подписи график начинается с верха зоны


def test_chart_with_zero_values_exports(tdir):
    deck = Deck(slides=[bar(labels=["A"], series=[{"name": "x", "values": [0]}])])
    assert len(export(tdir, deck).slides) == 1
```

Импорт: `from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION`.

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/test_pptx.py -q -k "bar or line_kind or dual or zero_values or shares"`
Expected: FAIL — гистограммы нет, всё рисуется линией; `dual-chart` без тела.

- [ ] **Step 3: Реализация**

```python
def _chart_data(src) -> CategoryChartData:
    data = CategoryChartData()
    data.categories = [clean(lb) for lb in src.labels]
    for ser in src.series:
        data.add_series(clean(ser.name), ser.values)
    return data


def _bar_chart(slide, src, box, cs: ChartStyle) -> None:
    """Гистограмма. Одна серия — цвет столбца по знаку (рост palette[0], падение negative),
    подписи значений с единицей; несколько — серии по палитре и легенда сверху.

    number_format не идёт в CategoryChartData: python-pptx пишет его в
    <c:formatCode> текстовым узлом без экранирования, и «&», «<» в unit ломают
    XML графика. plot.data_labels.number_format — атрибут, его экранирует lxml."""
    x, y, w, h = box
    chart = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Emu(x), Emu(y), Emu(w), Emu(h),
                                   _chart_data(src)).chart
    chart.value_axis.has_major_gridlines = False
    plot = chart.plots[0]
    if len(src.series) == 1:
        chart.has_legend = False
        plot.has_data_labels = True
        plot.data_labels.number_format = _number_format(clean(src.unit))
        plot.data_labels.number_format_is_linked = False
        plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
        series = plot.series[0]
        series.invert_if_negative = False
        for i, v in enumerate(src.series[0].values):
            fill = series.points[i].format.fill
            fill.solid()
            fill.fore_color.rgb = RGBColor.from_string((cs.negative if v < 0 else cs.palette[0]).upper())
        return
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.TOP
    chart.legend.include_in_layout = False
    for i, series in enumerate(plot.series):
        series.invert_if_negative = False
        series.format.fill.solid()
        series.format.fill.fore_color.rgb = RGBColor.from_string(cs.palette[i % len(cs.palette)].upper())


def _line_chart(slide, src, box, cs: ChartStyle) -> None:
    """Линейный график: серии по палитре по кругу, легенда сверху, единица — подпись оси."""
    x, y, w, h = box
    chart = slide.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Emu(x), Emu(y), Emu(w), Emu(h),
                                   _chart_data(src)).chart
    # ... остальное тело прежнее, s → src


def _draw_chart(slide, src, box, cs: ChartStyle) -> None:
    (_bar_chart if src.kind == "bar" else _line_chart)(slide, src, box, cs)


def _chart_body(c: Ctx) -> set[int]:
    box = _mm_box(c.sm.body)
    if not c.s.bullets:
        _draw_chart(c.slide, c.s, box, c.m.chart)
        return set()
    text_box, chart_box = _columns(box, c.sm.text_width, c.sm.gap)
    _bullets(c.slide, text_box, c.s.bullets, c.m.text, heading=c.sm.heading)
    _draw_chart(c.slide, c.s, chart_box, c.m.chart)
    return set()


def _dual_chart_body(c: Ctx) -> set[int]:
    """Два графика рядом; над каждым — подпись стороны полосой CAPTION_STRIP, если она есть."""
    for side, (x, y, w, h) in zip((c.s.left, c.s.right), _split(_mm_box(c.sm.body), 2, c.sm.gap)):
        if side.caption.strip():
            strip = int(CAPTION_STRIP * MM)
            _caption(c.slide, side.caption, x, y, w, c.m.text, italic=False)
            y, h = y + strip, h - strip
        _draw_chart(c.slide, side, (x, y, w, h), c.m.chart)
    return set()
```

`_caption` получает `italic: bool = True` (подпись к картинке остаётся курсивом, подпись графика — прямым). Порядок серий в `_chart_data` совпадает с моделью — это и даёт цвета палитры по кругу. В `BODIES` добавить `"dual-chart": _dual_chart_body`.

- [ ] **Step 4: Тесты зелёные**

Run: `uv run pytest tests/test_pptx.py -q`
Expected: PASS; три бывших xfail-теста гистограммы проходят без отметки.

- [ ] **Step 5: Коммит**

```bash
git add src/typst_deck/pptx.py tests/test_pptx.py
git commit -m "PPTX: график с видом bar/line, многорядная гистограмма, два графика

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Метрики и таблица

**Files:**
- Modify: `src/typst_deck/render.py:143-158` (`_numeric` → `numeric_columns`, `_trend` на основе новой `trend_of`)
- Modify: `src/typst_deck/pptx.py` (новые `_metrics_body`, `_table_body`, `_cell_rules`)
- Test: `tests/test_pptx.py`, `tests/test_render.py`

**Interfaces:**
- Produces:
  - `render.numeric_columns(header: list[str], rows: list[list[str]]) -> list[bool]` — прежняя `_numeric`, переименованная;
  - `render.trend_of(delta: str) -> Literal["up", "down"] | None` — правило знака из `_trend`;
  - `render._trend(delta)` остаётся и печатает Typst-строку по `trend_of`.

- [ ] **Step 1: Падающие тесты**

В `tests/test_render.py`:

```python
def test_trend_and_numeric_are_shared_with_pptx():
    from typst_deck.render import numeric_columns, trend_of

    assert [trend_of(d) for d in ("+12 %", "-3", "−1", "–2", "—4", "17", "")] == [
        "up", "down", "down", "down", "down", None, None]
    assert numeric_columns(["Регион", "Выручка"], [["Центр", "1 200,5"], ["Юг", "28 %"]]) == [False, True]
```

В `tests/test_pptx.py` (импорт `from pptx.enum.text import PP_ALIGN` уже есть после задачи 2):

```python
def test_metrics_columns_with_trend_colors(tdir):
    deck = Deck(slides=[{"type": "metrics", "title": "Т", "items": [
        {"value": "12,5 млн", "label": "выручка", "delta": "+12 %"},
        {"value": "3,4 %", "label": "доля", "delta": "–1 п. п."},
        {"value": "17", "label": "проектов\x1f"}]}])
    cols = sorted(boxes(export(tdir, deck).slides[0]), key=lambda b: b.left)
    assert len(cols) == 3 and all(inside(b) for b in cols)
    value, label, delta = cols[0].text_frame.paragraphs
    assert value.text == "12,5 млн" and value.runs[0].font.size == Pt(60) and value.runs[0].font.bold
    assert label.text == "выручка" and str(label.runs[0].font.color.rgb) == "666666"
    assert str(delta.runs[0].font.color.rgb) == "1E1E1E"  # рост — trend.up
    assert str(cols[1].text_frame.paragraphs[2].runs[0].font.color.rgb) == "FF2E00"  # «–» — падение
    assert [p.text for p in cols[2].text_frame.paragraphs] == ["17", "проектов"]  # без delta — два абзаца


def table_of(slide):
    return next(sh for sh in slide.shapes if sh.has_table)


def test_table_is_native_with_header_stripes_and_numeric_alignment(tdir):
    deck = Deck(slides=[{"type": "table", "title": "Т", "header": ["Регион", "Выручка"],
                         "rows": [["Центр", "42"], ["Север\nи запад", "17,5"], ["Юг", "28 %"]]}])
    frame = table_of(export(tdir, deck).slides[0])
    tbl = frame.table
    assert (len(tbl.rows), len(tbl.columns)) == (4, 2) and inside(frame)
    head = tbl.cell(0, 0)
    assert head.text == "Регион" and head.text_frame.paragraphs[0].runs[0].font.bold
    assert head._tc.xpath("./a:tcPr/a:solidFill/a:srgbClr[@val='DDDDDD']")
    assert tbl.cell(2, 0)._tc.xpath("./a:tcPr/a:solidFill/a:srgbClr[@val='F8F8F8']")  # вторая строка данных
    assert tbl.cell(1, 0)._tc.xpath("./a:tcPr/a:noFill")
    assert tbl.cell(1, 1).text_frame.paragraphs[0].alignment == PP_ALIGN.RIGHT  # числа вправо
    assert tbl.cell(1, 0).text_frame.paragraphs[0].alignment != PP_ALIGN.RIGHT
    assert tbl.cell(2, 0)._tc.xpath(".//a:br")
    # линии раньше заливки — иначе PowerPoint предложит восстановить файл
    tags = [etree.QName(e).localname for e in tbl.cell(0, 0)._tc.tcPr]
    assert tags[:4] == ["lnL", "lnR", "lnT", "lnB"] and tags[4] == "solidFill"
    assert not frame._element.xpath(".//a:tblPr[@bandRow='1' or @firstRow='1']")


def test_table_at_model_limits_fits_the_zone(tdir):
    cell = "x" * 40
    deck = Deck(slides=[{"type": "table", "title": "Т", "header": ["h" * 40] * 6, "rows": [[cell] * 6] * 8}])
    frame = table_of(export(tdir, deck).slides[0])
    assert inside(frame) and frame.height <= int(ZONE[3] * MM)


def test_short_table_rows_are_capped(tdir):
    deck = Deck(slides=[{"type": "table", "title": "Т", "header": ["a", "b"], "rows": [["1", "2"]]}])
    frame = table_of(export(tdir, deck).slides[0])
    assert frame.table.rows[0].height == 15 * MM and frame.height == 30 * MM
```

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/test_render.py tests/test_pptx.py -q -k "trend or metrics or table"`
Expected: FAIL — `ImportError: numeric_columns`, у метрик и таблицы нет тел.

- [ ] **Step 3: `render.py`**

```python
def numeric_columns(header: list[str], rows: list[list[str]]) -> list[bool]:
    """Колонки, где каждая ячейка читается как число: шаблон и PPTX выравнивают их вправо."""
    return [all(NUMBER.match(row[i] or "") for row in rows) if rows else False
            for i in range(len(header))]


def trend_of(delta: str) -> Literal["up", "down"] | None:
    # Тире пишет модель, по-русски: кроме дефиса (U+002D) и минуса (U+2212) там
    # бывают короткое (U+2013) и длинное (U+2014) тире — «–12 %» читается падением.
    d = delta.strip()
    if d.startswith("+"):
        return "up"
    if d.startswith(("-", "−", "–", "—")):
        return "down"
    return None


def _trend(delta: str) -> str:
    t = trend_of(delta)
    return typ_str(t) if t else "none"
```

Вызовы `_numeric(` в `render.py` заменить на `numeric_columns(`; добавить `Literal` в импорт `typing`.

- [ ] **Step 4: `pptx.py`**

```python
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN

from .render import CompileError, inside_template, numeric_columns, rasterize_svg, trend_of

ROW_MAX = 15  # мм — предел высоты строки таблицы: короткая таблица не тянется на всю зону
RULE_W = 6350  # EMU — 0.5 пт, тонкая линия таблицы


def _metrics_body(c: Ctx) -> set[int]:
    """Равные колонки: крупное число, подпись цветом подписи, изменение цветом тренда."""
    st = c.m.text
    for item, box in zip(c.s.items, _split(_mm_box(c.sm.body), len(c.s.items), c.sm.gap)):
        tf = _textbox(c.slide, box)
        _paragraph(tf, 0, item.value, st.metric, bold=True, align=PP_ALIGN.CENTER, keep_newlines=False)
        k = 1
        for text, color in ((item.label, st.caption),
                            (item.delta, {"up": c.m.trend.up, "down": c.m.trend.down}.get(trend_of(item.delta), st.caption))):
            if clean(text).strip():
                _paragraph(tf, k, text, st.size, color=color, align=PP_ALIGN.CENTER)
                k += 1
    return set()


def _cell_rules(cell, color: str) -> None:
    """Тонкие линии со всех сторон. Пишутся до заливки: в a:tcPr линии идут раньше
    заливки по схеме, а python-pptx вставляет заливку на её место сам."""
    tcpr = cell._tc.get_or_add_tcPr()
    for tag in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
        ln = etree.SubElement(tcpr, qn(tag), w=str(RULE_W))
        fill = etree.SubElement(ln, qn("a:solidFill"))
        etree.SubElement(fill, qn("a:srgbClr"), val=color.upper())


def _table_body(c: Ctx) -> set[int]:
    """Нативная таблица: жирная шапка на заливке, «зебра», тонкие линии, числа вправо."""
    st = c.m.table
    x, y, w, h = _mm_box(c.sm.body)
    nrows, ncols = len(c.s.rows) + 1, len(c.s.header)
    rh = min(h // nrows, ROW_MAX * MM)
    tbl = c.slide.shapes.add_table(nrows, ncols, Emu(x), Emu(y), Emu(w), Emu(rh * nrows)).table
    tbl.first_row = False      # стиль таблицы по умолчанию не красит шапку и полосы —
    tbl.horz_banding = False   # это делает сопоставление
    numeric = numeric_columns(c.s.header, c.s.rows)
    for r, row in enumerate([c.s.header, *c.s.rows]):
        tbl.rows[r].height = Emu(rh)
        for col, text in enumerate(row):
            cell = tbl.cell(r, col)
            _cell_rules(cell, st.rule)
            if r == 0:
                fill = st.header_fill
            elif r % 2 == 0:
                fill = st.stripe_fill
            else:
                fill = None
            if fill:
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor.from_string(fill.upper())
            else:
                cell.fill.background()
            align = PP_ALIGN.RIGHT if r and numeric[col] else None
            _paragraph(cell.text_frame, 0, text, st.size, bold=(r == 0), align=align)
    return set()
```

В `BODIES` добавить `metrics` и `table`.

- [ ] **Step 5: Тесты зелёные**

Run: `uv run pytest tests/test_render.py tests/test_pptx.py -q`
Expected: PASS.

- [ ] **Step 6: Коммит**

```bash
git add src/typst_deck/render.py src/typst_deck/pptx.py tests/test_render.py tests/test_pptx.py
git commit -m "PPTX: метрики с цветом тренда и нативная таблица

numeric и trend — общие с рендером Typst: numeric_columns и trend_of.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Галерея и видео

**Files:**
- Modify: `src/typst_deck/pptx.py` (новые `_fit`, `_gallery_body`, `_video_body`, `_placeholder_poster`)
- Test: `tests/test_pptx.py`

**Interfaces:**
- Consumes: `_image_file(name, …)` (задача 1), `_split`, `_caption` (задачи 2–3).
- Produces: `GRID = {2: (1, 2), 3: (1, 3), 4: (2, 2)}` — строки и колонки галереи.

- [ ] **Step 1: Падающие тесты**

```python
def gallery(n, caption="Подпись"):
    return Deck(slides=[{"type": "gallery", "title": "Г",
                         "images": [{"image": f"p{i}.png", "caption": caption} for i in range(n)]}])


@pytest.mark.parametrize("n,rows,cols", [(2, 1, 2), (3, 1, 3), (4, 2, 2)])
def test_gallery_grid(tdir, tmp_path, n, rows, cols):
    (tmp_path / "a").mkdir()
    for i in range(n):
        png(tmp_path / "a" / f"p{i}.png")
    slide = export(tdir, gallery(n), assets=tmp_path / "a").slides[0]
    pics = pictures(slide)
    assert len(pics) == n and all(inside(p) for p in pics)
    assert len({p.left for p in pics}) == cols and len({p.top for p in pics}) == rows
    assert all(abs(p.width / p.height - 2) < 0.01 for p in pics)
    caps = boxes(slide)
    assert len(caps) == n and all(inside(b) for b in caps)


def test_gallery_missing_picture_keeps_the_grid(tdir, tmp_path):
    (tmp_path / "a").mkdir()
    png(tmp_path / "a" / "p0.png")
    warnings: list[str] = []
    slide = export(tdir, gallery(2), assets=tmp_path / "a", warnings=warnings).slides[0]
    [pic] = pictures(slide)
    assert pic.left < int((ZONE[0] + ZONE[2] / 2) * MM)  # осталась левая, правая клетка пустая
    assert any("p1.png не найдена" in w for w in warnings)


def video_deck(**kw):
    return Deck(slides=[{"type": "video", "title": "В", "caption": "Ролик"} | kw])


def test_uploaded_video_is_embedded_with_its_poster(tdir, tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "clip.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    png(tmp_path / "a" / "cover.png", 320, 240)
    slide = export(tdir, video_deck(video="clip.mp4", poster="cover.png"), assets=tmp_path / "a").slides[0]
    [movie] = [sh for sh in slide.shapes if sh.shape_type == MSO_SHAPE_TYPE.MEDIA]
    assert inside(movie) and abs(movie.width / movie.height - 4 / 3) < 0.01
    rels = [r.reltype for r in slide.part.rels.values()]
    assert RT.VIDEO in rels and RT.MEDIA in rels
    [cap] = boxes(slide)
    assert cap.text_frame.text == "Ролик" and cap.top >= movie.top + movie.height


def test_link_video_is_a_poster_with_a_hyperlink(tdir):
    url = "https://example.com/watch?v=1&t=2"
    slide = export(tdir, video_deck(url=url)).slides[0]
    [pic] = pictures(slide)
    assert pic.click_action.hyperlink.address == url
    assert abs(pic.width / pic.height - 16 / 9) < 0.01  # заглушка 16:9
    assert not [sh for sh in slide.shapes if sh.shape_type == MSO_SHAPE_TYPE.MEDIA]


def test_placeholder_poster_takes_the_mapping_colors(tdir):
    slide = export(tdir, video_deck(url="https://example.com")).slides[0]
    [pic] = pictures(slide)
    with Image.open(io.BytesIO(pic.image.blob)) as im:
        assert im.getpixel((5, 5)) == (0xDD, 0xDD, 0xDD)  # table.header_fill
        assert im.getpixel((im.width // 2, im.height // 2)) == (0xFF, 0xDE, 0x00)  # «▶» — text.bullet


def test_missing_video_file_leaves_the_poster_and_warns(tdir, tmp_path):
    warnings: list[str] = []
    slide = export(tdir, video_deck(video="gone.mp4", poster="gone.png"), assets=tmp_path,
                   warnings=warnings).slides[0]
    assert len(pictures(slide)) == 1
    assert not [sh for sh in slide.shapes if sh.shape_type == MSO_SHAPE_TYPE.MEDIA]
    assert any("видео gone.mp4 не найдено" in w for w in warnings)
    assert any("gone.png не найдена" in w for w in warnings)


def test_video_cannot_escape_assets(tdir, tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "secret.mp4").write_bytes(b"x")
    warnings: list[str] = []
    slide = export(tdir, video_deck(video="../secret.mp4"), assets=tmp_path / "a", warnings=warnings).slides[0]
    assert not [sh for sh in slide.shapes if sh.shape_type == MSO_SHAPE_TYPE.MEDIA]
    assert any("не найдено" in w for w in warnings)
```

`../secret.mp4` модель пропускает (проверено: `VideoSlide` смотрит только на расширение), поэтому защита — в экспорте, как у картинок.

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/test_pptx.py -q -k "gallery or video or poster"`
Expected: FAIL — у типов нет тел.

- [ ] **Step 3: Реализация**

```python
from PIL import Image, ImageDraw

GRID = {2: (1, 2), 3: (1, 3), 4: (2, 2)}  # картинок → (строк, колонок)
POSTER = (1600, 900)  # заглушка обложки, 16:9


def _rgb(hex6: str) -> tuple[int, int, int]:
    return tuple(int(hex6[i:i + 2], 16) for i in (0, 2, 4))


def _fit(box, aspect: float) -> tuple[int, int, int, int]:
    """Наибольший прямоугольник с пропорцией aspect (w/h) в box: по центру, к верху."""
    x, y, w, h = box
    pw, ph = (w, int(w / aspect)) if w / h < aspect else (int(h * aspect), h)
    return x + (w - pw) // 2, y, pw, ph


def _gallery_body(c: Ctx) -> set[int]:
    """Сетка: 2 и 3 — в ряд, 4 — 2×2; картинка вписана в клетку, подпись под ней."""
    rows, cols = GRID[len(c.s.images)]
    x, y, w, h = _mm_box(c.sm.body)
    g = int(c.sm.gap * MM)
    ch = (h - g * (rows - 1)) // rows
    cells = [cell for r in range(rows) for cell in _split((x, y + r * (ch + g), w, ch), cols, c.sm.gap)]
    has_caption = any(p.caption.strip() for p in c.s.images)
    strip = int(CAPTION_STRIP * MM) if has_caption else 0
    for pic, (cx, cy, cw, chh) in zip(c.s.images, cells):
        img = _image_file(pic.image, c.assets, c.tmp, c.typst_bin, c.warnings, c.n)
        if img is None:
            continue  # клетка остаётся пустой, сетка не сдвигается
        bottom = _picture(c.slide, img, (cx, cy, cw, chh - strip))
        if pic.caption.strip():
            _caption(c.slide, pic.caption, cx, bottom + int(2 * MM), cw, c.m.text)
    return set()


def _placeholder_poster(m: Mapping, tmp: Path) -> Path:
    """Заглушка обложки: фон table.header_fill, по центру «▶» цвета text.bullet."""
    w, h = POSTER
    im = Image.new("RGB", POSTER, _rgb(m.table.header_fill))
    r = h // 6
    ImageDraw.Draw(im).polygon([(w / 2 - r * 0.8, h / 2 - r), (w / 2 - r * 0.8, h / 2 + r), (w / 2 + r, h / 2)],
                               fill=_rgb(m.text.bullet))
    path = tmp / "poster-placeholder.png"
    im.save(path)
    return path


def _video_file(name: str, assets: Path, warnings: list[str], n: int) -> Path | None:
    if not name:
        return None
    src = Path(assets) / name
    if Path(name).name != name or not src.is_file():  # «..»-путь — за пределы assets/
        warnings.append(f"слайд {n}: видео {name} не найдено")
        return None
    return src


def _video_body(c: Ctx) -> set[int]:
    """Файл — встроенный ролик с обложкой; ссылка — обложка с гиперссылкой. Подпись — под рамкой."""
    poster = _image_file(c.s.poster, c.assets, c.tmp, c.typst_bin, c.warnings, c.n) or _placeholder_poster(c.m, c.tmp)
    with Image.open(poster) as im:
        aspect = im.width / im.height
    x, y, w, h = _mm_box(c.sm.body)
    strip = int(CAPTION_STRIP * MM) if c.s.caption.strip() else 0
    fx, fy, fw, fh = _fit((x, y, w, h - strip), aspect)
    video = _video_file(c.s.video, c.assets, c.warnings, c.n)
    if video is not None:
        c.slide.shapes.add_movie(str(video), Emu(fx), Emu(fy), Emu(fw), Emu(fh),
                                 poster_frame_image=str(poster), mime_type="video/mp4")
    else:
        pic = c.slide.shapes.add_picture(str(poster), Emu(fx), Emu(fy), Emu(fw), Emu(fh))
        if c.s.url:
            pic.click_action.hyperlink.address = c.s.url
    if strip:
        _caption(c.slide, c.s.caption, fx, fy + fh + int(2 * MM), fw, c.m.text)
    return set()
```

В `BODIES` добавить `gallery` и `video`.

- [ ] **Step 4: Тесты зелёные**

Run: `uv run pytest tests/test_pptx.py -q`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add src/typst_deck/pptx.py tests/test_pptx.py
git commit -m "PPTX: галерея сеткой и видео — встроенный ролик или обложка со ссылкой

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Правило 7 целиком, сквозные тесты и документация

**Files:**
- Modify: `src/typst_deck/contract.py:353-377` (`_rule_pptx`)
- Modify: `tests/test_pptx.py` (снять оставшиеся `xfail`)
- Modify: `tests/test_templates.py` (тесты правила 7 — рядом с прочими тестами контракта)
- Modify: `docs/template-contract.md` (раздел «PowerPoint-мастер»)

**Interfaces:**
- Consumes: всё из задач 1–5; `write_sample_assets(deck_dir)` из `contract.py`.

- [ ] **Step 1: Снять оставшиеся `xfail` и переписать сквозные тесты**

С тестов `test_every_type_lands_on_its_layout_at_the_masters_size`, `test_fields_fill_placeholders_and_share_one_in_model_order`, `test_empty_and_unmapped_placeholders_are_removed`, `test_slide_number_is_a_field`, `test_titles_shrink_on_edit`, `test_control_characters_dropped_and_newline_breaks_the_line`, `test_text_at_global_limits_exports`, `test_template_font_replaces_explicit_latin_faces`, `test_without_font_the_master_keeps_its_faces` снять отметку и комментарий над первой из них. Переписать:

```python
def test_every_type_lands_on_its_layout_at_the_masters_size(tdir):
    from tests.conftest import PPTX_MAPPING

    prs = export(tdir, SAMPLE_DECK)
    assert [s.slide_layout.name for s in prs.slides] == [
        PPTX_MAPPING["slides"][s.type]["layout"] for s in SAMPLE_DECK.slides]
    assert len(prs.slides) == 15
    assert (prs.slide_width, prs.slide_height) == (Mm(677), Mm(381))
    assert by_idx(prs.slides[0])[0] == ["Название презентации"]


def test_empty_and_unmapped_placeholders_are_removed(tdir, tmp_path):
    (tmp_path / "a").mkdir()
    png(tmp_path / "a" / "pic.png")
    deck = Deck(slides=[{"type": "title", "title": "Итоги"},
                        {"type": "image", "title": "Рост", "image": "pic.png"}])
    prs = export(tdir, deck, assets=tmp_path / "a")
    assert set(by_idx(prs.slides[0])) == {0, 12}
    assert set(by_idx(prs.slides[1])) == {0, 12}


def test_slide_number_is_a_field(tdir):
    for n, slide in enumerate(export(tdir, SAMPLE_DECK).slides, 1):
        nums = [sh for sh in slide.placeholders if sh.placeholder_format.idx == 12]
        assert len(nums) == 1, n  # у «Blank» номер тоже есть
        assert nums[0]._element.xpath(".//a:fld[@type='slidenum']"), n
        assert nums[0].text_frame.text == str(n)


def test_titles_shrink_on_edit(tdir):
    for slide in export(tdir, SAMPLE_DECK).slides:
        if slide.shapes.title is not None:  # у цитаты заголовка нет
            assert slide.shapes.title._element.xpath(".//a:bodyPr/a:normAutofit")


def test_control_characters_dropped_and_newline_breaks_the_line(tdir):
    deck = Deck(slides=[{"type": "title", "title": "\x0bИтоги\x1f", "subtitle": "первая\nвторая"},
                        {"type": "text", "title": "T", "bullets": ["тезис\nпродолжение"]}])
    # ... проверки прежние


def test_text_at_global_limits_exports(tdir):
    """Каждый тип на глобальных пределах модели собирается и открывается заново."""
    from typst_deck.model import SLIDE_TYPES as ALL

    deck = Deck(slides=[filled_slide(t, {"title": {"max": 120, "lines": 2}} if t not in ("quote",) else {})
                        for t in ALL])
    assert len(export(tdir, deck).slides) == len(ALL)
```

`filled_slide` заполняет обязательные поля короткими значениями и каждое объявленное — по пределу (см. её докстринг в `contract.py`); если для какого-то типа она не даёт валидный слайд — это находка, а не повод исключить тип из теста.

- [ ] **Step 2: Тест правила 7 на целом образце** — в `tests/test_templates.py`, рядом с прочими тестами правила 7 (импорт `make_pptx_template`, `requires_typst` из `tests.conftest`):

```python
@requires_typst
def test_rule_pptx_exports_the_whole_sample(tmp_path):
    from typst_deck.contract import _rule_pptx

    d = make_pptx_template(tmp_path)
    assert _rule_pptx(d, {"pptx": "pptx.json"}, "typst", tmp_path / "work") == []


def test_rule_pptx_fails_a_mapping_without_new_types(tmp_path):
    from typst_deck.contract import _rule_pptx

    d = make_pptx_template(tmp_path, mapping_edit=lambda m: m["slides"].pop("gallery"))
    [msg] = _rule_pptx(d, {"pptx": "pptx.json"}, "typst", tmp_path / "work")
    assert "нет типа gallery" in msg
```

Run: `uv run pytest tests/ -q -k "rule_pptx or lands_on or global_limits"`
Expected: оба теста правила 7 проходят уже сейчас — `load_mapping` требует все 15 типов с задачи 1, а сужение пропускает все типы образца. Они остаются сторожами: первый ловит возврат сужения, второй — ослабление полноты. Сквозные тесты экспорта (`lands_on`, `global_limits`) проходят после снятия отметок.

- [ ] **Step 3: Снять сужение в `_rule_pptx`**

```python
def _rule_pptx(path: Path, meta: dict, typst_bin: str, work_dir: Path) -> list[str]:
    """Правило 7: сопоставление читается, мастер с ним сходится, образец из 15 типов
    экспортируется — с картинками и роликом образца, чтобы встроенное видео и
    сетка галереи тоже проходили через python-pptx."""
    if "pptx" not in meta:
        return []
    try:
        load_mapping(path, meta["pptx"])
    except MappingError as e:
        return [f"pptx: {e}"]
    deck_dir = work_dir / "pptx-sample"
    write_sample_assets(deck_dir)
    try:
        data = export_pptx(SAMPLE_DECK, path, meta["pptx"], deck_dir / "assets", typst_bin)
        n = len(Presentation(io.BytesIO(data)).slides)
    except MappingError as e:
        return [f"pptx: {e}"]
    except Exception as e:  # сбой python-pptx на мастере или на повторном открытии — нарушение, а не падение проверки
        return [f"pptx: образец не экспортируется: {type(e).__name__}: {e}"]
    if n != len(SAMPLE_DECK.slides):
        return [f"pptx: в файле {n} слайдов при {len(SAMPLE_DECK.slides)} в образце"]
    return []
```

- [ ] **Step 4: Весь набор — ни одного xfail**

Run: `uv run pytest -q`
Expected: зелёный, `xfailed` в итоге нет. `grep -n "xfail" tests/test_pptx.py` — пусто.

- [ ] **Step 5: Документация контракта** — в `docs/template-contract.md`, раздел «PowerPoint-мастер»:

1. Пример `pptx.json` — на все 15 типов, с ключами `trend` и `table`, `text.quote` и `text.metric`; раскладка типов — из спеки §7 («Раскладка Lemana Tech»), `title`, `section`, `image`, `chart` (бывший `bar-chart` с `heading`), `final` — как в нынешнем примере.
2. Таблица ключей: добавить `text.quote`, `text.metric`, `trend.up`, `trend.down`, `table.size`, `table.header_fill`, `table.stripe_fill`, `table.rule`; у `body` — список типов из `BODY_KEYS`; у `gap` — типы, где он нужен; `ph.blocks` у `columns` — «список idx не короче трёх; тогда `body` и `gap` не задаются».
3. Абзац о полях в `ph`: «у `quote` — ничего; у остальных — `title`».
4. Абзац «Как рисуются типы» — список из спеки §7 («Как рисуется») плюс отклонения 2–5 этого плана: заглушка обложки, рамка видео, высота строки таблицы, пропавшие файлы.

- [ ] **Step 6: Образец для ручной приёмки** — выгрузить файл на синтетическом мастере и положить в scratchpad (в репозиторий не коммитить):

```sh
uv run python -c "
import sys; sys.path.insert(0, '.')
from pathlib import Path
from tests.conftest import make_pptx_template
from typst_deck.contract import SAMPLE_DECK, write_sample_assets
from typst_deck.pptx import export_pptx
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
t = make_pptx_template(out); write_sample_assets(out / 'deck')
w = []
(out / 'sample-15.pptx').write_bytes(export_pptx(SAMPLE_DECK, t, 'pptx.json', out / 'deck' / 'assets', 'typst', w))
print(out / 'sample-15.pptx', w)
" <scratchpad>/pptx-acceptance
```

Файл передаётся пользователю на ручную приёмку (спека §9): открывается в PowerPoint без предложения восстановить, таблица, галерея и обложки на месте. Ролик образца — заглушка из 12 байт, он не проиграется; проигрывание проверяется на колоде с настоящим mp4 после плана C.

- [ ] **Step 7: Коммит**

```bash
git add src/typst_deck/contract.py tests/ docs/template-contract.md
git commit -m "PPTX: правило 7 на всём образце, xfail сняты, контракт описывает 15 типов

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## После плана

- В `main`: в `docs/backlog.md` отметить план B сделанным в ветке (раздел «В работе»), пункт «снять 12 xfail и сужение в `_rule_pptx`» закрыть.
- Ручная приёмка файла из задачи 6 — за пользователем; на настоящем мастере Lemana Tech — в плане D.
