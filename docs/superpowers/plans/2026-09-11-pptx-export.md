# Экспорт колоды в редактируемый PPTX — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** кнопка «Скачать PPTX» и `pptx_url` для бота: колода собирается в редактируемый .pptx на PowerPoint-мастере шаблона — текст в заполнителях и зонах мастера, нативные графики, заметки докладчика.

**Architecture:** новый модуль `src/typst_deck/pptx.py` на python-pptx читает сопоставление `pptx.json` из шаблона (макет на тип слайда, заполнитель на поле, зона тела в мм, цвета) и строит слайды на макетах мастера. Реестр шаблонов знает путь к сопоставлению, контракт получает правило 7, сервис отдаёт файл на лету без кэша. Продукт ничего корпоративного не знает: мастер и раскладка Lemana Tech — коммит в репозиторий канона.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, python-pptx 1.0.2 (тянет lxml, Pillow, XlsxWriter), pytest (`uv run pytest`), Typst 0.15.1, rootless podman + Quadlet.

**Spec:** `docs/superpowers/specs/2026-09-11-pptx-export-design.md`

## Global Constraints

- Комментарии, сообщения и тексты тестов — по-русски, как во всём репозитории.
- Новая зависимость одна: `python-pptx>=1.0.2,<2` (код опирается на её внутренние `_sldIdLst`, `_spTree`, `_next_shape_id`, `drop_rel` — отсюда верхняя граница). `src/typst_deck/model.py` не менять.
- `uv run pytest` зелёный перед каждым коммитом (сейчас 281 passed, 6 skipped); `typst` 0.15.1 установлен. Начиная с задачи 7 — ещё и `TYPST_DECK_TEST_TEMPLATES=~/corp-templates uv run pytest`.
- В `src/` нет ничего корпоративного: ни имён макетов Lemana Tech, ни её цветов. Они живут только в `pptx.json` канона.
- Ответы с ошибкой имеют форму `{"error": {"code", "message"}}` (`ApiError` из `api/common.py`).
- Экспорт PPTX не пишет в хранилище: ни новой версии, ни записи в чате, `build/` не трогается.
- Канон Lemana Tech: `~/projects/lmru--hr-analytics--design-template`, remote нет, ветка `main`, рабочее дерево чистое. Правится только в задаче 7 и только так, как в ней написано. `~/corp-templates/lemana-tech` — ссылка на него.
- Каждое сообщение коммита заканчивается строкой `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

## Отклонения от спеки, принятые при планировании

Всё ниже проверено прототипом 2026-09-11 (python-pptx 1.0.2): синтетический мастер и мастер Lemana Tech, 30 тестов задач 2–3 зелёные на прототипе.

1. **`TemplateInfo.pptx` — `str | None`** (значение поля из `template.json`), а не `Path`: `load_mapping` проверяет путь «внутрь шаблона» по относительному значению.
2. **Управляющие символы.** Спека (§3) говорила, что lxml на них падает. python-pptx 1.0 не падает, а вставляет в текст видимый мусор `_x001F_`. Вычистка остаётся, меняется только причина.
3. **Кэша нет и не будет:** колода из 24 слайдов на мастере Lemana Tech собирается за 0,26 с, файл 199 КБ (мастер 2 МБ: слайды-образцы с картинками в файл не попадают). Риск спеки §12 «время сборки» закрыт.
4. **`/api/health` → `templates.pptx_off`** — там видна причина выключения PPTX (спека §7 говорила «видна в `/api/health`», не называя ключ).
5. **`export_pptx` принимает необязательный `warnings: list[str]`**: туда падают пропавшие картинки и SVG, которые не растеризовались; сервис пишет их в лог.
6. **Детали оформления, которых нет в спеке:** линия серии 3 пт, маркеры цвета серии, интервал перед тезисом — половина кегля, отступ маркера 8 мм, подпись к картинке — через 2 мм под картинкой, высотой 13 мм.

---

### Task 1: общий помощник пути и растеризация SVG в `render.py`

**Files:**
- Modify: `src/typst_deck/render.py:45-54` (`resolve_fonts`) и конец файла
- Test: `tests/test_render.py`

**Interfaces:**
- Produces: `inside_template(template_dir: Path, rel: object, name: str) -> Path` — `ValueError(f"{name}={rel!r}: путь должен вести внутрь шаблона")` для пустого, не строки, абсолютного пути и пути с `..`; иначе `Path(template_dir) / rel` (существование не проверяет).
- Produces: `rasterize_svg(svg: Path, out: Path, typst_bin: str = "typst", ppi: int = 200, timeout: int = 60) -> Path` — PNG в `out`; `CompileError` при сбое typst.

- [ ] **Step 1: Написать падающие тесты** — в конец `tests/test_render.py`; в импорты файла добавить `inside_template`, `rasterize_svg`, `resolve_fonts`, `CompileError` из `typst_deck.render`, `requires_typst` из `tests.conftest` и `from PIL import Image` (тех, что ещё нет).

```python
def test_inside_template_keeps_paths_inside(tmp_path):
    assert inside_template(tmp_path, "typst-deck/pptx.json", "pptx") == tmp_path / "typst-deck/pptx.json"
    for bad in ("../x.json", "/etc/x.json", "", None, 5):
        with pytest.raises(ValueError, match=r"pptx=.*путь должен вести внутрь шаблона"):
            inside_template(tmp_path, bad, "pptx")


def test_resolve_fonts_message_is_unchanged(tmp_path):
    with pytest.raises(ValueError, match=r"^fonts='\.\./x': путь должен вести внутрь шаблона$"):
        resolve_fonts(tmp_path, "../x")


@requires_typst
def test_rasterize_svg_keeps_proportions(tmp_path):
    svg = tmp_path / "vec.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="300" height="100">'
                   '<rect width="300" height="100" fill="#00FFE0"/></svg>')
    out = rasterize_svg(svg, tmp_path / "vec.png")
    with Image.open(out) as im:
        assert im.format == "PNG" and abs(im.width / im.height - 3) < 0.05


@requires_typst
def test_rasterize_broken_svg_is_a_compile_error(tmp_path):
    svg = tmp_path / "bad.svg"
    svg.write_text("<svg")
    with pytest.raises(CompileError):
        rasterize_svg(svg, tmp_path / "bad.png")
```

Pillow в окружении проекта появится только с python-pptx (задача 2), поэтому этот шаг ставит зависимость заранее:

```bash
uv add "python-pptx>=1.0.2,<2"
```

- [ ] **Step 2: Прогнать — падают**

Run: `uv run pytest tests/test_render.py -q -k "inside_template or resolve_fonts_message or rasterize"`
Expected: FAIL — `ImportError: cannot import name 'inside_template'`.

- [ ] **Step 3: Реализация** — `resolve_fonts` в `render.py` заменить целиком:

```python
def inside_template(template_dir: Path, rel: object, name: str) -> Path:
    """Путь из template.json от корня шаблона; name — имя поля для сообщения.

    Путь наружу — ValueError: в контейнере шаблон смонтирован, и цели снаружи
    там нет. Существование не проверяется — это дело вызывающего.
    """
    if not isinstance(rel, str) or not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
        raise ValueError(f"{name}={rel!r}: путь должен вести внутрь шаблона")
    return Path(template_dir) / rel


def resolve_fonts(template_dir: Path, rel: object = "fonts") -> Path | None:
    """Каталог шрифтов шаблона: rel — поле fonts из template.json, от корня шаблона.

    None — каталога нет, typst обойдётся системными шрифтами.
    """
    d = inside_template(template_dir, rel, "fonts")
    return d if d.is_dir() else None
```

В конец `render.py`:

```python
RASTER_TYP = '#set page(width: auto, height: auto, margin: 0pt)\n#image("image.svg")\n'


def rasterize_svg(svg: Path, out: Path, typst_bin: str = "typst", ppi: int = 200, timeout: int = 60) -> Path:
    """SVG → PNG средствами typst: python-pptx SVG не вставляет, а колода их принимает.

    typst уже есть в образе, так что растеризатор не тянет новых зависимостей.
    Рабочий каталог — рядом с out: песочница typst видит только его.
    """
    work = out.parent / f"{out.stem}.raster"
    work.mkdir(parents=True, exist_ok=True)
    shutil.copy(svg, work / "image.svg")
    (work / "raster.typ").write_text(RASTER_TYP)
    r, _ = _run([typst_bin, "compile", "--root", str(work), "--format", "png", "--ppi", str(ppi),
                 str(work / "raster.typ"), str(out)], timeout)
    if r.returncode != 0:
        raise CompileError("SVG не растеризуется", r.stderr)
    return out
```

- [ ] **Step 4: Прогнать — зелёные, и весь набор**

Run: `uv run pytest tests/test_render.py -q && uv run pytest -q`
Expected: всё зелёное (старые тесты `resolve_fonts` и контракта не заметили замены).

- [ ] **Step 5: Коммит**

```bash
git add pyproject.toml uv.lock src/typst_deck/render.py tests/test_render.py
git commit -m "Путь внутрь шаблона — общий помощник; SVG растеризуется через typst

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: сопоставление шаблона с мастером — `pptx.py`, часть 1

**Files:**
- Create: `src/typst_deck/pptx.py`
- Modify: `tests/conftest.py` (фикстура синтетического мастера)
- Test: `tests/test_pptx.py` (новый)

**Interfaces:**
- Consumes: `inside_template` (задача 1).
- Produces: `MappingError(ValueError)`; pydantic-модели `Mapping`, `SlideMap`, `TextStyle`, `ChartStyle`; `SLIDE_TYPES`, `PH_FIELDS`; `load_mapping(template_dir: Path, rel: object) -> Mapping`; `open_master(template_dir: Path, m: Mapping) -> Presentation`; `_layouts(prs) -> dict[str, SlideLayout]`.
- Produces (tests): `tests.conftest.PPTX_MAPPING`, `build_master(path)`, `make_pptx_template(parent, name="withpptx", mapping_edit=None) -> Path` — копия `template/` с `master.pptx`, `pptx.json` и `"pptx": "pptx.json"` в `template.json`.

- [ ] **Step 1: Фикстура** — в `tests/conftest.py` после `make_template`:

```python
# Сопоставление синтетического мастера: макеты стандартного мастера python-pptx.
# «Title and Content» у image — нарочно: его idx 1 не сопоставлен, на нём
# проверяется удаление лишнего заполнителя.
PPTX_MAPPING = {
    "master": "master.pptx",
    "text": {"size": 24, "bullet": "FFDE00", "caption": "666666"},
    "chart": {"palette": ["FFDE00", "1E1E1E", "00FFE0"], "negative": "FF2E00"},
    "slides": {
        "title": {"layout": "Title Slide", "ph": {"title": 0, "subtitle": 1, "author": 21, "department": 21}},
        "section": {"layout": "Section Header", "ph": {"title": 0, "subtitle": 1}},
        "image": {"layout": "Title and Content", "ph": {"title": 0}, "body": [20, 80, 600, 260],
                  "image_width": {"small": 30, "medium": 42, "large": 55}, "gap": 15},
        "bar-chart": {"layout": "Title Only", "ph": {"title": 0}, "body": [20, 80, 600, 260],
                      "text_width": 38, "gap": 12, "heading": "Выводы"},
        "chart": {"layout": "Title Only", "ph": {"title": 0}, "body": [20, 80, 600, 260],
                  "text_width": 38, "gap": 12},
        "final": {"layout": "Title Slide", "ph": {"title": 0, "contact": 1}},
    },
}


def build_master(path: Path) -> None:
    """Синтетический PowerPoint-мастер: стандартный мастер python-pptx, слайд 677×381 мм
    (нестандартный размер ловит зашитый 4:3), в «Title Slide» — заполнитель idx 21,
    в презентации — один слайд-образец, который экспорт обязан убрать.
    Корпоративные мастера в репозиторий не попадают."""
    import copy

    from pptx import Presentation
    from pptx.oxml.ns import qn
    from pptx.util import Mm

    prs = Presentation()
    prs.slide_width, prs.slide_height = Mm(677), Mm(381)
    layout = next(lay for lay in prs.slide_layouts if lay.name == "Title Slide")
    sub = next(ph for ph in layout.placeholders if ph.placeholder_format.idx == 1)
    el = copy.deepcopy(sub._element)
    cnv = el.find(qn("p:nvSpPr")).find(qn("p:cNvPr"))
    cnv.set("id", "100")
    cnv.set("name", "Author and Date")
    ph = el.find(".//" + qn("p:ph"))
    ph.set("type", "body")
    ph.set("idx", "21")
    layout.shapes._spTree.append(el)
    prs.slides.add_slide(layout)
    prs.save(path)


def make_pptx_template(parent: Path, name: str = "withpptx", mapping_edit=None) -> Path:
    """Копия эталона template/ с синтетическим мастером и сопоставлением pptx.json.

    mapping_edit(mapping) правит хорошее сопоставление перед записью: сломанные
    варианты выводятся из рабочего и не расходятся с ним.
    """
    import copy
    import json

    d = make_template(parent, name, meta={"name": "С мастером", "pptx": "pptx.json"})
    build_master(d / "master.pptx")
    mapping = copy.deepcopy(PPTX_MAPPING)
    if mapping_edit is not None:
        mapping_edit(mapping)
    (d / "pptx.json").write_text(json.dumps(mapping, ensure_ascii=False))
    return d
```

- [ ] **Step 2: Падающие тесты** — `tests/test_pptx.py`:

```python
"""Экспорт в PPTX: сопоставление шаблона и сборка файла на синтетическом мастере."""
import re

import pytest

from tests.conftest import make_pptx_template
from typst_deck.pptx import MappingError, load_mapping, open_master


# --- сопоставление

def check(tdir):
    open_master(tdir, load_mapping(tdir, "pptx.json"))


def test_good_mapping_passes(tmp_path):
    check(make_pptx_template(tmp_path))


BROKEN = {
    "master-outside": (lambda m: m.update(master="../master.pptx"), "внутрь шаблона"),
    "master-missing": (lambda m: m.update(master="nope.pptx"), "нет файла nope.pptx"),
    "unknown-key": (lambda m: m.update(colour="FFFFFF"), "colour"),
    "missing-type": (lambda m: m["slides"].pop("final"), "нет типа final"),
    "missing-ph-field": (lambda m: m["slides"]["title"]["ph"].pop("department"), "нет поля department"),
    "extra-ph-field": (lambda m: m["slides"]["image"]["ph"].update(caption=1), "caption не кладётся"),
    "no-body": (lambda m: m["slides"]["image"].pop("body"), "нет body"),
    "body-on-title": (lambda m: m["slides"]["title"].update(body=[0, 0, 10, 10]), "body у этого типа не бывает"),
    "bad-color": (lambda m: m["chart"].update(negative="red"), "chart.negative"),
    "no-layout": (lambda m: m["slides"]["section"].update(layout="Нет такого"), "нет макета «Нет такого»"),
    "no-idx": (lambda m: m["slides"]["title"]["ph"].update(author=42), "нет заполнителя idx 42"),
    "zone-outside": (lambda m: m["slides"]["chart"].update(body=[600, 80, 200, 260]), "выходит за слайд"),
}


@pytest.mark.parametrize("case", BROKEN)
def test_broken_mapping_is_named(case, tmp_path):
    edit, text = BROKEN[case]
    d = make_pptx_template(tmp_path, mapping_edit=edit)
    with pytest.raises(MappingError, match=re.escape(text)):
        check(d)


def test_unreadable_mapping_is_named(tmp_path):
    d = make_pptx_template(tmp_path)
    (d / "pptx.json").write_text("{")
    with pytest.raises(MappingError, match="не читается"):
        load_mapping(d, "pptx.json")


def test_mapping_path_stays_inside_the_template(tmp_path):
    d = make_pptx_template(tmp_path)
    with pytest.raises(MappingError, match="внутрь шаблона"):
        load_mapping(d, "../pptx.json")
    with pytest.raises(MappingError, match="нет файла missing.json"):
        load_mapping(d, "missing.json")


def test_broken_master_file_is_named(tmp_path):
    d = make_pptx_template(tmp_path)
    (d / "master.pptx").write_bytes(b"not a zip")
    with pytest.raises(MappingError, match="не открывается"):
        check(d)
```

- [ ] **Step 3: Прогнать — падают**

Run: `uv run pytest tests/test_pptx.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'typst_deck.pptx'`.

- [ ] **Step 4: Реализация** — `src/typst_deck/pptx.py`:

```python
"""Экспорт колоды в редактируемый PPTX на PowerPoint-мастере шаблона.

Спека: docs/superpowers/specs/2026-09-11-pptx-export-design.md. Сопоставление
(pptx.json в шаблоне, путь — поле pptx в template.json) говорит, на какой макет
мастера ложится каждый тип слайда, в какой заполнитель — каждое поле и где зона
тела. Продукт ничего корпоративного не знает: мастер, макеты и цвета приходят
из шаблона. Контракт (правило 7) и сам экспорт проверяют сопоставление одними
и теми же load_mapping и open_master.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

from pptx import Presentation
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .render import inside_template

MM = 36000  # EMU в миллиметре
SLIDE_TYPES = ("title", "section", "image", "bar-chart", "chart", "final")
# Поля, которые обязаны лежать в заполнителях, — в порядке модели: он же задаёт
# порядок абзацев, когда несколько полей делят один заполнитель. Остальное
# (тезисы, картинка, подпись, график) идёт в зону body, notes — в заметки.
PH_FIELDS = {
    "title": ("title", "subtitle", "author", "department"),
    "section": ("title", "subtitle"),
    "image": ("title",),
    "bar-chart": ("title",),
    "chart": ("title",),
    "final": ("title", "contact"),
}
BODY_KEYS = {"image": ("body", "image_width", "gap"),
             "bar-chart": ("body", "text_width", "gap"),
             "chart": ("body", "text_width", "gap")}
OPTIONAL_KEYS = {"bar-chart": ("heading",), "chart": ("heading",)}

Hex = Annotated[str, Field(pattern=r"^[0-9A-Fa-f]{6}$")]
Percent = Annotated[float, Field(ge=1, le=90)]


class MappingError(ValueError):
    """Сопоставление или мастер шаблона не годятся; текст — для человека."""


class _Strict(BaseModel):
    # опечатка в ключе не должна тихо выключать настройку
    model_config = ConfigDict(extra="forbid")


class TextStyle(_Strict):
    size: float = Field(gt=0)  # кегль тезисов, пт
    bullet: Hex                # цвет маркера тезисов
    caption: Hex               # цвет подписи к картинке


class ChartStyle(_Strict):
    palette: list[Hex] = Field(min_length=1)  # серии по кругу; первый — рост у гистограммы
    negative: Hex                             # столбцы с отрицательным значением


class SlideMap(_Strict):
    layout: str                                   # имя макета мастера (<p:cSld name>)
    ph: dict[str, int]                            # поле → idx заполнителя; у заголовка 0
    body: tuple[float, float, float, float] | None = None  # зона тела x, y, w, h в мм
    image_width: dict[Literal["small", "medium", "large"], Percent] | None = None
    text_width: Percent | None = None
    gap: float | None = Field(default=None, ge=0)  # зазор между колонками, мм
    heading: str | None = None                     # заголовок колонки тезисов у графиков


class Mapping(_Strict):
    master: str
    text: TextStyle
    chart: ChartStyle
    slides: dict[Literal["title", "section", "image", "bar-chart", "chart", "final"], SlideMap]


def _completeness(m: Mapping) -> list[str]:
    """Правила полноты спеки §4.3, которые не выражаются типами."""
    problems = [f"slides: нет типа {t}" for t in SLIDE_TYPES if t not in m.slides]
    for stype, sm in m.slides.items():
        need = PH_FIELDS[stype]
        problems += [f"slides.{stype}.ph: нет поля {f}" for f in need if f not in sm.ph]
        problems += [f"slides.{stype}.ph: поле {f} не кладётся в заполнитель" for f in sm.ph if f not in need]
        body = BODY_KEYS.get(stype, ())
        allowed = body + OPTIONAL_KEYS.get(stype, ())
        for key in ("body", "image_width", "text_width", "gap", "heading"):
            value = getattr(sm, key)
            if key in body and value is None:
                problems.append(f"slides.{stype}: нет {key}")
            elif key not in allowed and value is not None:
                problems.append(f"slides.{stype}: {key} у этого типа не бывает")
        if sm.image_width is not None and len(sm.image_width) != 3:
            problems.append(f"slides.{stype}.image_width: нужны small, medium и large")
    return problems


def load_mapping(template_dir: Path, rel: object) -> Mapping:
    """Сопоставление из шаблона: структура, полнота и путь к мастеру; без сверки с мастером."""
    try:
        path = inside_template(template_dir, rel, "pptx")
    except ValueError as e:
        raise MappingError(str(e)) from None
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        raise MappingError(f"pptx: нет файла {rel}") from None
    except (OSError, ValueError) as e:
        raise MappingError(f"{rel} не читается: {e}") from None
    try:
        m = Mapping.model_validate(raw)
    except ValidationError as e:
        raise MappingError(f"{rel}: " + "; ".join(
            f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())) from None
    problems = _completeness(m)
    try:
        master = inside_template(template_dir, m.master, "master")
    except ValueError as e:
        problems.append(str(e))
    else:
        if not master.is_file():
            problems.append(f"master: нет файла {m.master}")
    if problems:
        raise MappingError(f"{rel}: " + "; ".join(problems))
    return m


def _layouts(prs) -> dict:
    """Макеты всех мастеров по имени; при совпадении имён побеждает первый мастер."""
    out: dict = {}
    for master in prs.slide_masters:
        for layout in master.slide_layouts:
            out.setdefault(layout.name, layout)
    return out


def open_master(template_dir: Path, m: Mapping):
    """Мастер шаблона, сверенный с сопоставлением: макеты, заполнители, зоны."""
    try:
        prs = Presentation(str(Path(template_dir) / m.master))
    except Exception as e:  # битый zip, не презентация — для автора шаблона это одна ошибка
        raise MappingError(f"мастер {m.master} не открывается: {type(e).__name__}: {e}") from None
    layouts = _layouts(prs)
    w, h = prs.slide_width / MM, prs.slide_height / MM
    problems = []
    for stype, sm in m.slides.items():
        layout = layouts.get(sm.layout)
        if layout is None:
            problems.append(f"slides.{stype}: в мастере нет макета «{sm.layout}»")
            continue
        have = {ph.placeholder_format.idx for ph in layout.placeholders}
        problems += [f"slides.{stype}.ph.{f}: в макете «{sm.layout}» нет заполнителя idx {i}"
                     for f, i in sm.ph.items() if i not in have]
        if sm.body is not None:
            x, y, bw, bh = sm.body
            if bw <= 0 or bh <= 0 or x < 0 or y < 0 or x + bw > w + 0.5 or y + bh > h + 0.5:
                problems.append(f"slides.{stype}.body: зона {list(sm.body)} выходит за слайд {w:.0f}×{h:.0f} мм")
    if problems:
        raise MappingError("; ".join(problems))
    return prs
```

- [ ] **Step 5: Прогнать — зелёные, и весь набор**

Run: `uv run pytest tests/test_pptx.py -q && uv run pytest -q`
Expected: 16 новых зелёных (12 поломок + 4), весь набор зелёный.

- [ ] **Step 6: Коммит**

```bash
git add src/typst_deck/pptx.py tests/conftest.py tests/test_pptx.py
git commit -m "Сопоставление шаблона с PowerPoint-мастером: формат и проверка

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: сборка PPTX — `pptx.py`, часть 2

**Files:**
- Modify: `src/typst_deck/pptx.py`
- Test: `tests/test_pptx.py`

**Interfaces:**
- Consumes: `load_mapping`, `open_master`, `_layouts`, `PH_FIELDS`, `MM`, модели (задача 2); `rasterize_svg`, `CompileError` (задача 1).
- Produces: `export_pptx(deck: Deck, template_dir: Path, mapping_rel: object, assets_dir: Path, typst_bin: str = "typst", warnings: list[str] | None = None) -> bytes`; `clean(text: str) -> str`.

- [ ] **Step 1: Падающие тесты** — импорты `tests/test_pptx.py` заменить блоком ниже, тесты — дописать в конец файла.

```python
"""Экспорт в PPTX: сопоставление шаблона и сборка файла на синтетическом мастере."""
import io
import re

import pytest
from PIL import Image
from pptx import Presentation
from pptx.enum.chart import XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Mm

from tests.conftest import make_pptx_template, requires_typst
from typst_deck.contract import SAMPLE_DECK, filled_slide
from typst_deck.model import Deck
from typst_deck.pptx import SLIDE_TYPES, MappingError, export_pptx, load_mapping, open_master

MM = 36000
ZONE = (20, 80, 600, 260)  # body синтетического сопоставления, мм
```

```python
# --- экспорт

@pytest.fixture
def tdir(tmp_path):
    return make_pptx_template(tmp_path)


def export(tdir, deck, assets=None, warnings=None):
    data = export_pptx(deck, tdir, "pptx.json", assets or tdir / "no-assets", "typst", warnings)
    return Presentation(io.BytesIO(data))


def by_idx(slide) -> dict[int, list[str]]:
    return {sh.placeholder_format.idx: [p.text for p in sh.text_frame.paragraphs] for sh in slide.placeholders}


def pictures(slide):
    return [sh for sh in slide.shapes if sh.shape_type == MSO_SHAPE_TYPE.PICTURE]


def boxes(slide):
    return [sh for sh in slide.shapes if sh.shape_type == MSO_SHAPE_TYPE.TEXT_BOX]


def chart_of(slide):
    return next(sh.chart for sh in slide.shapes if sh.has_chart)


def colors(chart, path: str) -> list[str]:
    return [e.get("val") for e in chart._chartSpace.xpath(path)]


def inside(sh, zone=ZONE) -> bool:
    x, y, w, h = (int(v * MM) for v in zone)
    return (sh.left >= x - 1 and sh.top >= y - 1
            and sh.left + sh.width <= x + w + 1 and sh.top + sh.height <= y + h + 1)


def png(path, w=400, h=200):
    Image.new("RGB", (w, h), (255, 222, 0)).save(path)


def image_deck(size="medium", **kw) -> Deck:
    return Deck(slides=[{"type": "image", "title": "Рост", "bullets": ["Тезис"], "image": "pic.png",
                         "image_size": size, "caption": "Подпись", **kw}])


def test_every_type_lands_on_its_layout_at_the_masters_size(tdir):
    prs = export(tdir, SAMPLE_DECK)
    assert [s.slide_layout.name for s in prs.slides] == [
        "Title Slide", "Section Header", "Title and Content", "Title Only", "Title Only", "Title Slide"]
    assert (prs.slide_width, prs.slide_height) == (Mm(677), Mm(381))
    # слайд-образец мастера не пережил экспорт: первый слайд — титул колоды
    assert by_idx(prs.slides[0])[0] == ["Название презентации"]


def test_fields_fill_placeholders_and_share_one_in_model_order(tdir):
    title = by_idx(export(tdir, SAMPLE_DECK).slides[0])
    assert title[1] == ["Подзаголовок и дата"]
    assert title[21] == ["Имя Фамилия", "Подразделение"]


def test_empty_and_unmapped_placeholders_are_removed(tdir):
    deck = Deck(slides=[{"type": "title", "title": "Итоги"}, {"type": "image", "title": "Рост"}])
    prs = export(tdir, deck)
    # ни подзаголовка, ни подписи, ни idx 1 «Title and Content»; дату и колонтитул python-pptx не переносит
    assert set(by_idx(prs.slides[0])) == {0, 12}
    assert set(by_idx(prs.slides[1])) == {0, 12}


def test_slide_number_is_a_field(tdir):
    for n, slide in enumerate(export(tdir, SAMPLE_DECK).slides, 1):
        num = next(sh for sh in slide.placeholders if sh.placeholder_format.idx == 12)
        assert num._element.xpath(".//a:fld[@type='slidenum']"), n
        assert num.text_frame.text == str(n)


def test_titles_shrink_on_edit(tdir):
    for slide in export(tdir, SAMPLE_DECK).slides:
        assert slide.shapes.title._element.xpath(".//a:bodyPr/a:normAutofit")


def test_image_keeps_proportions_inside_the_zone(tdir, tmp_path):
    (tmp_path / "assets").mkdir()
    png(tmp_path / "assets" / "pic.png")
    widths = []
    for size in ("small", "medium", "large"):
        slide = export(tdir, image_deck(size), assets=tmp_path / "assets").slides[0]
        [pic] = pictures(slide)
        text, caption = boxes(slide)
        assert inside(pic) and inside(text) and inside(caption)
        assert abs(pic.width / pic.height - 2) < 0.01
        assert text.left + text.width <= pic.left  # тезисы слева от картинки
        assert caption.top >= pic.top + pic.height and caption.text_frame.text == "Подпись"
        widths.append(pic.width)
    assert widths == sorted(widths) and len(set(widths)) == 3


def test_missing_image_leaves_bullets_the_whole_zone(tdir, tmp_path):
    warnings: list[str] = []
    slide = export(tdir, image_deck(), assets=tmp_path, warnings=warnings).slides[0]
    assert pictures(slide) == [] and "pic.png не найдена" in warnings[0]
    [text] = boxes(slide)
    assert (text.left, text.width) == (int(ZONE[0] * MM), int(ZONE[2] * MM))


@requires_typst
def test_svg_goes_in_as_png(tdir, tmp_path):
    (tmp_path / "vec.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="300" height="100">'
                                      '<rect width="300" height="100" fill="#00FFE0"/></svg>')
    slide = export(tdir, image_deck(image="vec.svg"), assets=tmp_path).slides[0]
    [pic] = pictures(slide)
    assert pic.image.content_type == "image/png" and abs(pic.width / pic.height - 3) < 0.05


def test_bar_colors_follow_the_sign(tdir):
    deck = Deck(slides=[{"type": "bar-chart", "title": "Итоги", "unit": "млн",
                         "data": [{"label": "Центр", "value": 42}, {"label": "Север", "value": -17},
                                  {"label": "Юг", "value": 28}]}])
    chart = chart_of(export(tdir, deck).slides[0])
    assert colors(chart, ".//c:dPt//a:srgbClr") == ["FFDE00", "FF2E00", "FFDE00"]
    assert chart._chartSpace.xpath(".//c:invertIfNegative[@val='0']")
    assert chart.plots[0].data_labels.number_format == 'General" млн"'
    assert not chart.has_legend


def test_line_series_cycle_the_palette(tdir):
    deck = Deck(slides=[{"type": "chart", "title": "Итоги", "unit": "млн", "labels": ["Q1", "Q2"],
                         "series": [{"name": f"Ряд {j}", "values": [j, j + 1]} for j in range(4)]}])
    chart = chart_of(export(tdir, deck).slides[0])
    assert colors(chart, ".//c:ser/c:spPr/a:ln//a:srgbClr") == ["FFDE00", "1E1E1E", "00FFE0", "FFDE00"]
    assert chart.legend.position == XL_LEGEND_POSITION.TOP
    assert chart.value_axis.axis_title.text_frame.text == "млн"


def test_chart_takes_the_zone_or_shares_it_with_bullets(tdir):
    base = {"type": "bar-chart", "title": "Итоги", "data": [{"label": "A", "value": 1}]}
    alone, shared = export(tdir, Deck(slides=[base, base | {"bullets": ["Рост"]}])).slides
    frame = next(sh for sh in alone.shapes if sh.has_chart)
    assert (frame.left, frame.top, frame.width, frame.height) == tuple(int(v * MM) for v in ZONE)
    [text] = boxes(shared)
    frame = next(sh for sh in shared.shapes if sh.has_chart)
    assert text.left == int(ZONE[0] * MM) and text.width == int(ZONE[2] * MM * 38 / 100)
    assert frame.left == text.left + text.width + 12 * MM
    heading, bullet = text.text_frame.paragraphs
    assert heading.text == "Выводы" and not heading._p.xpath("./a:pPr/a:buChar")
    assert bullet._p.xpath("./a:pPr/a:buChar[@char='•']")


def test_notes_go_to_speaker_notes(tdir):
    deck = Deck(slides=[{"type": "final", "notes": "Сказать спасибо"}])
    assert export(tdir, deck).slides[0].notes_slide.notes_text_frame.text == "Сказать спасибо"


def test_control_characters_dropped_and_newline_breaks_the_line(tdir):
    deck = Deck(slides=[{"type": "title", "title": "\x0bИтоги\x1f", "subtitle": "первая\nвторая"},
                        {"type": "image", "title": "T", "bullets": ["тезис\nпродолжение"]}])
    prs = export(tdir, deck)
    assert by_idx(prs.slides[0])[0] == ["Итоги"]
    sub = next(sh for sh in prs.slides[0].placeholders if sh.placeholder_format.idx == 1)
    assert len(sub.text_frame.paragraphs) == 1 and sub._element.xpath(".//a:br")
    [text] = boxes(prs.slides[1])
    assert len(text.text_frame.paragraphs) == 1 and text._element.xpath(".//a:br")


def test_text_at_global_limits_exports(tdir):
    title = {"title": {"max": 120, "lines": 2}}
    bullets = {"image": 6, "bar-chart": 4, "chart": 4}
    deck = Deck(slides=[filled_slide(t, title | ({"bullets": {"count": bullets[t], "max": 200}}
                                                 if t in bullets else {})) for t in SLIDE_TYPES])
    assert len(export(tdir, deck).slides) == len(SLIDE_TYPES)
```

- [ ] **Step 2: Прогнать — падают**

Run: `uv run pytest tests/test_pptx.py -q`
Expected: FAIL — `ImportError: cannot import name 'export_pptx'`.

- [ ] **Step 3: Реализация.** Импорты `pptx.py` заменить блоком:

```python
from __future__ import annotations

import copy
import io
import json
import re
import tempfile
import uuid
from pathlib import Path
from typing import Annotated, Literal

from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.shapes import PP_PLACEHOLDER
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.oxml.ns import qn
from pptx.util import Emu, Mm, Pt
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .model import Deck
from .render import CompileError, inside_template, rasterize_svg
```

После `OPTIONAL_KEYS` добавить константы:

```python
CAPTION_STRIP = 15   # мм под подпись к картинке
CAPTION_SCALE = 0.7  # кегль подписи от кегля тезисов
# Управляющие символы, которых не бывает в тексте слайда; \t и \n остаются.
# python-pptx на них не падает, а пишет в текст видимый мусор вида _x001F_.
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f]")
```

В конец файла:

```python
def clean(text: str) -> str:
    return CONTROL.sub("", text)


def _drop_slides(prs) -> None:
    """Слайды-образцы мастера не нужны: сначала ссылка из списка, потом связь.
    Недостижимые части python-pptx при сохранении не пишет."""
    ids = prs.slides._sldIdLst
    for sld in list(ids):
        ids.remove(sld)
        prs.part.drop_rel(sld.rId)


def _fill(slide, s, sm: SlideMap) -> None:
    """Поля — в заполнители по idx; пустые и несопоставленные заполнители удаляются,
    иначе при правке в PowerPoint видна подсказка макета («Уровень текста 1…»)."""
    groups: dict[int, list[str]] = {}
    for f in PH_FIELDS[s.type]:
        value = clean(getattr(s, f) or "")
        if value.strip():
            groups.setdefault(sm.ph[f], []).append(value)
    for ph in list(slide.placeholders):
        idx = ph.placeholder_format.idx
        texts = groups.get(idx)
        if not texts:
            ph._element.getparent().remove(ph._element)
            continue
        tf = ph.text_frame
        for i, t in enumerate(texts):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = t.replace("\n", "\v")  # \v — разрыв строки внутри абзаца
        if idx == 0:
            # автоподбор PowerPoint: пересчитывается, когда заголовок правят
            tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE


def _slide_number(slide, layout, n: int) -> None:
    """python-pptx номер слайда не переносит: копия заполнителя макета с полем номера,
    чтобы PowerPoint пересчитал его при перестановке слайдов."""
    for ph in layout.placeholders:
        if ph.placeholder_format.type != PP_PLACEHOLDER.SLIDE_NUMBER:
            continue
        el = copy.deepcopy(ph._element)
        el.find(qn("p:nvSpPr")).find(qn("p:cNvPr")).set("id", str(slide.shapes._next_shape_id))
        body = el.find(qn("p:txBody"))
        for p in body.findall(qn("a:p")):
            body.remove(p)
        p = etree.SubElement(body, qn("a:p"))
        fld = etree.SubElement(p, qn("a:fld"), id="{" + str(uuid.uuid4()).upper() + "}", type="slidenum")
        etree.SubElement(fld, qn("a:t")).text = str(n)
        slide.shapes._spTree.append(el)
        return


def _bullets(slide, box, items: list[str], style: TextStyle, heading: str | None = None) -> None:
    """Тезисы надписью в зоне: маркер цвета style.bullet, шрифт — из темы мастера."""
    x, y, w, h = box
    tf = slide.shapes.add_textbox(Emu(x), Emu(y), Emu(w), Emu(h)).text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    paras = ([(heading, False)] if heading else []) + [(i, True) for i in items]
    for k, (text, bullet) in enumerate(paras):
        p = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
        p.text = clean(text).replace("\n", "\v")
        if k:
            p.space_before = Pt(style.size * 0.5)
        if bullet:
            ppr = p._p.get_or_add_pPr()
            ppr.set("marL", str(Mm(8)))
            ppr.set("indent", str(-Mm(8)))
            clr = etree.SubElement(ppr, qn("a:buClr"))
            etree.SubElement(clr, qn("a:srgbClr"), val=style.bullet.upper())
            etree.SubElement(ppr, qn("a:buChar"), char="•")
        for r in p.runs:
            r.font.size = Pt(style.size)
            if not bullet:
                r.font.bold = True


def _mm_box(zone) -> tuple[int, int, int, int]:
    return tuple(int(v * MM) for v in zone)


def _columns(box, left_pct: float, gap_mm: float) -> tuple[tuple, tuple]:
    """Левая колонка шириной left_pct % зоны и правая — остаток за вычетом зазора."""
    x, y, w, h = box
    lw = int(w * left_pct / 100)
    g = int(gap_mm * MM)
    return (x, y, lw, h), (x + lw + g, y, w - lw - g, h)


def _picture(slide, path: Path, box) -> int:
    """Картинка вписана в box с сохранением пропорций, по центру и к верху; возвращает её низ."""
    x, y, w, h = box
    with Image.open(path) as im:
        iw, ih = im.size
    k = min(w / iw, h / ih)
    pw, ph = int(iw * k), int(ih * k)
    slide.shapes.add_picture(str(path), Emu(x + (w - pw) // 2), Emu(y), Emu(pw), Emu(ph))
    return y + ph


def _caption(slide, text: str, x: int, y: int, w: int, style: TextStyle) -> None:
    tf = slide.shapes.add_textbox(Emu(x), Emu(y), Emu(w), Emu(int((CAPTION_STRIP - 2) * MM))).text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = clean(text).replace("\n", " ")
    for r in p.runs:
        r.font.size = Pt(style.size * CAPTION_SCALE)
        r.font.italic = True
        r.font.color.rgb = RGBColor.from_string(style.caption.upper())


def _image_file(s, assets_dir: Path, tmp: Path, typst_bin: str, warnings: list[str], n: int) -> Path | None:
    """Файл картинки слайда; SVG — растром. Пропавшая или нерастеризуемая — None и предупреждение,
    как у PDF: слайд собирается без неё."""
    if not s.image:
        return None
    src = Path(assets_dir) / s.image
    if not src.is_file():
        warnings.append(f"слайд {n}: картинка {s.image} не найдена")
        return None
    if src.suffix.lower() != ".svg":
        return src
    try:
        return rasterize_svg(src, tmp / f"{src.stem}.png", typst_bin)
    except CompileError as e:
        warnings.append(f"слайд {n}: SVG {s.image} не растеризуется: {e}")
        return None


def _image_body(slide, s, sm: SlideMap, style: TextStyle, img: Path | None) -> None:
    box = _mm_box(sm.body)
    if img is None:
        if s.bullets:
            _bullets(slide, box, s.bullets, style)
        return
    text_box, img_box = _columns(box, 100 - sm.image_width[s.image_size], sm.gap)
    if s.bullets:
        _bullets(slide, text_box, s.bullets, style)
    x, y, w, h = img_box
    strip = int(CAPTION_STRIP * MM) if s.caption else 0
    bottom = _picture(slide, img, (x, y, w, h - strip))
    if s.caption:
        _caption(slide, s.caption, x, bottom + int(2 * MM), w, style)


def _number_format(unit: str) -> str:
    unit = unit.replace('"', "").strip()
    return f'General" {unit}"' if unit else "General"


def _bar_chart(slide, s, box, cs: ChartStyle) -> None:
    """Гистограмма: цвет столбца по знаку — рост palette[0], падение negative."""
    fmt = _number_format(s.unit)
    data = CategoryChartData(number_format=fmt)
    data.categories = [clean(d.label) for d in s.data]
    data.add_series(clean(s.unit) or "Значение", [d.value for d in s.data])
    x, y, w, h = box
    chart = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Emu(x), Emu(y), Emu(w), Emu(h), data).chart
    chart.has_legend = False
    chart.value_axis.has_major_gridlines = False
    plot = chart.plots[0]
    plot.has_data_labels = True
    plot.data_labels.number_format = fmt
    plot.data_labels.number_format_is_linked = False
    plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    series = plot.series[0]
    series.invert_if_negative = False
    for i, d in enumerate(s.data):
        fill = series.points[i].format.fill
        fill.solid()
        fill.fore_color.rgb = RGBColor.from_string((cs.negative if d.value < 0 else cs.palette[0]).upper())


def _line_chart(slide, s, box, cs: ChartStyle) -> None:
    """Линейный график: серии по палитре по кругу, легенда сверху, единица — подпись оси."""
    data = CategoryChartData()
    data.categories = [clean(lb) for lb in s.labels]
    for ser in s.series:
        data.add_series(clean(ser.name), ser.values)
    x, y, w, h = box
    chart = slide.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Emu(x), Emu(y), Emu(w), Emu(h), data).chart
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.TOP
    chart.legend.include_in_layout = False
    chart.value_axis.has_major_gridlines = False
    if s.unit:
        chart.value_axis.has_title = True
        chart.value_axis.axis_title.text_frame.text = clean(s.unit)
    for i, series in enumerate(chart.plots[0].series):
        color = RGBColor.from_string(cs.palette[i % len(cs.palette)].upper())
        series.smooth = False
        series.format.line.color.rgb = color
        series.format.line.width = Pt(3)
        series.marker.format.fill.solid()
        series.marker.format.fill.fore_color.rgb = color
        series.marker.format.line.color.rgb = color


def _chart_body(slide, s, sm: SlideMap, m: Mapping) -> None:
    box = _mm_box(sm.body)
    draw = _bar_chart if s.type == "bar-chart" else _line_chart
    if not s.bullets:
        draw(slide, s, box, m.chart)
        return
    text_box, chart_box = _columns(box, sm.text_width, sm.gap)
    _bullets(slide, text_box, s.bullets, m.text, heading=sm.heading)
    draw(slide, s, chart_box, m.chart)


def export_pptx(deck: Deck, template_dir: Path, mapping_rel: object, assets_dir: Path,
                typst_bin: str = "typst", warnings: list[str] | None = None) -> bytes:
    """Колода → байты .pptx на мастере шаблона.

    Сопоставление читается на каждый вызов: канон могли обновить после старта,
    и ошибка должна прийти MappingError с причиной, а не 500. Пропавшие картинки
    и нерастеризуемые SVG — в warnings, слайд собирается без них.
    """
    warnings = [] if warnings is None else warnings
    m = load_mapping(template_dir, mapping_rel)
    prs = open_master(template_dir, m)
    layouts = _layouts(prs)
    _drop_slides(prs)
    with tempfile.TemporaryDirectory() as tmp:
        for n, s in enumerate(deck.slides, 1):
            sm = m.slides[s.type]
            layout = layouts[sm.layout]
            slide = prs.slides.add_slide(layout)
            _fill(slide, s, sm)
            _slide_number(slide, layout, n)
            if s.type == "image":
                _image_body(slide, s, sm, m.text, _image_file(s, assets_dir, Path(tmp), typst_bin, warnings, n))
            elif s.type in ("bar-chart", "chart"):
                _chart_body(slide, s, sm, m)
            if s.notes.strip():
                slide.notes_slide.notes_text_frame.text = clean(s.notes)
        buf = io.BytesIO()
        prs.save(buf)
    return buf.getvalue()
```

- [ ] **Step 4: Прогнать — зелёные, и весь набор**

Run: `uv run pytest tests/test_pptx.py -q && uv run pytest -q`
Expected: `tests/test_pptx.py` — 30 passed; весь набор зелёный.

- [ ] **Step 5: Коммит**

```bash
git add src/typst_deck/pptx.py tests/test_pptx.py
git commit -m "Сборка PPTX на мастере шаблона: заполнители, зоны, графики, заметки

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: реестр, правило 7 контракта, `/api/health`, документ контракта

**Files:**
- Modify: `src/typst_deck/templates.py` (`TemplateInfo`, `__init__`, `_info`, `check_all`)
- Modify: `src/typst_deck/contract.py` (докстринг модуля, `Report`, новое правило, `check_template`)
- Modify: `src/typst_deck/service.py:100-104` (`templates_health`)
- Modify: `docs/template-contract.md`
- Test: `tests/test_templates.py`, `tests/test_contract.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: `export_pptx`, `MappingError` (задача 3); `inside_template` (задача 1); `make_pptx_template` (задача 2).
- Produces: `TemplateInfo.pptx: str | None` (значение поля `pptx` из `template.json`; `None` — поля нет, путь наружу или PPTX выключен); `TemplateInfo.public()["pptx"]: bool`; `TemplateRegistry.pptx_off: dict[str, str]` (id → причина); `Report.pptx: list[str]`; `/api/health` → `templates.pptx_off`.

- [ ] **Step 1: Падающие тесты**

`tests/test_templates.py` — в импорт из `tests.conftest` добавить `make_pptx_template`; в `test_registry_without_slots_declares_nothing` ожидание `public()` заменить на:

```python
    assert reg.get("plain").public() == {"id": "plain", "name": "Простой", "description": "", "pptx": False}
```

В конец файла:

```python
def test_registry_reads_the_pptx_mapping_path(tmp_path, caplog):
    root = tmp_path / "templates"
    for name, meta in (("with", {"name": "С", "pptx": "typst-deck/pptx.json"}),
                       ("without", {"name": "Без"}),
                       ("outside", {"name": "Н", "pptx": "../pptx.json"})):
        d = root / name
        d.mkdir(parents=True)
        (d / "deck.typ").write_text("// stub")
        (d / "template.json").write_text(json.dumps(meta, ensure_ascii=False))
    reg = TemplateRegistry(TEMPLATE_DIR, root)
    assert reg.get("with").pptx == "typst-deck/pptx.json" and reg.get("with").public()["pptx"] is True
    assert reg.get("without").pptx is None and reg.get("without").public()["pptx"] is False
    assert reg.get("outside").pptx is None
    assert "экспорт в PPTX выключен" in caplog.text


@requires_typst
def test_start_check_turns_pptx_off_but_keeps_the_template(tmp_path):
    root = tmp_path / "templates"
    make_pptx_template(root, "badpptx",
                       mapping_edit=lambda m: m["slides"]["section"].update(layout="Нет такого"))
    make_pptx_template(root, "goodpptx")
    reg = TemplateRegistry(TEMPLATE_DIR, root)
    reg.check_all("typst", tmp_path / "work")
    assert "badpptx" not in reg.broken and "нет макета «Нет такого»" in reg.pptx_off["badpptx"]
    assert reg.get("badpptx").pptx is None and reg.get("badpptx").public()["pptx"] is False
    assert "goodpptx" not in reg.pptx_off and reg.get("goodpptx").pptx == "pptx.json"
    assert any("нет макета" in w for w in reg.warnings["badpptx"])
```

`tests/test_contract.py` — в импорт из `tests.conftest` добавить `make_pptx_template`; в конец:

```python
@requires_typst
def test_good_pptx_mapping_passes_the_full_contract(tmp_path):
    rep = check_template(make_pptx_template(tmp_path), "typst", tmp_path / "w")
    assert rep.errors == [] and rep.pptx == []


@requires_typst
def test_broken_pptx_is_an_error_in_full_mode_and_a_warning_at_start(tmp_path):
    d = make_pptx_template(tmp_path, mapping_edit=lambda m: m["slides"]["title"]["ph"].update(author=42))
    full = check_template(d, "typst", tmp_path / "w1")
    start = check_template(d, "typst", tmp_path / "w2", full=False)
    assert any(e.startswith("pptx:") and "idx 42" in e for e in full.errors)
    assert start.errors == [] and start.pptx and any("idx 42" in w for w in start.warnings)


@requires_typst
def test_template_without_pptx_has_no_rule_7_findings(tmp_path):
    assert check_template(TEMPLATE_DIR, "typst", tmp_path).pptx == []
```

`tests/test_api.py` — в конец:

```python
async def test_health_names_templates_with_pptx_off(client):
    client.app.state.service.templates.pptx_off["x"] = "в мастере нет макета «Y»"
    t = (await client.get("/api/health")).json()["templates"]
    assert t["pptx_off"] == {"x": "в мастере нет макета «Y»"}
```

- [ ] **Step 2: Прогнать — падают**

Run: `uv run pytest tests/test_templates.py tests/test_contract.py tests/test_api.py -q`
Expected: FAIL — нет атрибутов `pptx`, `pptx_off`, `Report.pptx`, ключа `pptx_off` в health; `public()` без `pptx`.

- [ ] **Step 3: Реализация `templates.py`**

Импорт: `from .render import resolve_fonts` → `from .render import inside_template, resolve_fonts`.

`TemplateInfo` — после `fonts`, и новый `public()`:

```python
    # поле pptx из template.json — путь к сопоставлению с PowerPoint-мастером от корня
    # шаблона; None — поля нет, путь ведёт наружу или стартовая проверка выключила PPTX
    pptx: str | None = None

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "description": self.description,
                "pptx": self.pptx is not None}
```

В `TemplateRegistry.__init__` после `self.warnings`:

```python
        self.pptx_off: dict[str, str] = {}        # id → почему экспорт в PPTX выключен; заполняет check_all
```

`_info` — после блока `fonts` и до `name = ...`:

```python
        pptx = meta.get("pptx")
        if pptx is not None:
            try:
                inside_template(path, pptx, "pptx")
            except ValueError as e:
                self._warn(mp, f"{e} — экспорт в PPTX выключен")
                pptx = None
        if tid in self.pptx_off:
            pptx = None
```

и возврат:

```python
        return TemplateInfo(tid, name, meta.get("description", ""), path,
                            clamp(meta.get("slots"), tid), fonts, pptx)
```

`check_all` — цикл и присваивание:

```python
        broken: dict[str, str] = {}
        warnings: dict[str, list[str]] = {}
        pptx_off: dict[str, str] = {}
        for t in templates:
            rep = check_template(t.path, typst_bin, work_dir / t.id, full=False)
            if rep.errors:
                broken[t.id] = "; ".join(rep.errors)
            if rep.warnings:
                warnings[t.id] = rep.warnings
            if rep.pptx:
                # шаблон работает, выключается только экспорт в PPTX (правило 7)
                pptx_off[t.id] = "; ".join(rep.pptx)
        for tid, missing in incomplete.items():
            broken[tid] = f"нет {', '.join(missing)}"
        self.broken, self.warnings, self.pptx_off, self.checked = broken, warnings, pptx_off, True
```

- [ ] **Step 4: Реализация `contract.py`**

Докстринг модуля: «Полный — для автора шаблона и CI: шесть правил, строго.» → «Полный — для автора шаблона и CI: семь правил, строго.» и в конец докстринга абзац:

```
Правило 7 (PowerPoint-мастер) при старте тоже мягкое: нарушение выключает
экспорт в PPTX у шаблона, а PDF продолжает работать.
```

Импорты — добавить `import io`, `from pptx import Presentation` и `from .pptx import MappingError, export_pptx`.

`Report`:

```python
@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # правило 7 отдельно: при старте по нему выключается экспорт в PPTX, а не шаблон
    pptx: list[str] = field(default_factory=list)
```

Перед `check_template`:

```python
def _rule_pptx(path: Path, meta: dict, typst_bin: str, work_dir: Path) -> list[str]:
    """Правило 7: сопоставление читается, мастер с ним сходится, образец экспортируется."""
    if "pptx" not in meta:
        return []
    try:
        data = export_pptx(SAMPLE_DECK, path, meta["pptx"], work_dir / "no-assets", typst_bin)
    except MappingError as e:
        return [f"pptx: {e}"]
    except Exception as e:  # сбой python-pptx на мастере — нарушение, а не падение проверки
        return [f"pptx: образец не экспортируется: {type(e).__name__}: {e}"]
    n = len(Presentation(io.BytesIO(data)).slides)
    if n != len(SAMPLE_DECK.slides):
        return [f"pptx: в файле {n} слайдов при {len(SAMPLE_DECK.slides)} в образце"]
    return []
```

В `check_template` сразу после `strict.extend(f"slots: {m}" for m in notes)`:

```python
    report.pptx = _rule_pptx(path, meta, typst_bin, work_dir)
    strict.extend(report.pptx)
```

- [ ] **Step 5: `service.py`, `templates_health`**

```python
    def templates_health(self) -> dict:
        t = self.templates
        return {"checked": t.checked, "ok": [x.id for x in t.list()],
                "broken": dict(t.broken), "warnings": dict(t.warnings),
                "pptx_off": dict(t.pptx_off), "error": self.template_check_error}
```

- [ ] **Step 6: `docs/template-contract.md`**

В дереве раздела «Шаблон — это каталог» после строки `measure.json`:

```
│   ├── measure.json  геометрия слотов для замера
│   └── pptx.json     сопоставление с PowerPoint-мастером (если он есть)
```

(у строки `measure.json` знак `└──` меняется на `├──`).

В таблицу `template.json` после строки `slots`:

```
| `pptx` | нет | сопоставление с PowerPoint-мастером от корня; без него экспорта в PPTX нет |
```

Новый раздел перед «## Проверка»:

````markdown
## PowerPoint-мастер

Если у шаблона есть PowerPoint-мастер, typst-deck умеет отдавать колоду
редактируемым PPTX: текст в заполнителях и зонах мастера, нативные графики,
заметки докладчика. Шрифт не задаётся — текст берёт шрифты темы мастера.
Мастер и сопоставление лежат в шаблоне, поле `pptx` в `template.json` — путь к
сопоставлению:

```json
{
  "master": "references/master.pptx",
  "text": {"size": 28, "bullet": "FFDE00", "caption": "666666"},
  "chart": {"palette": ["FFDE00", "1E1E1E", "00FFE0", "FF8700"], "negative": "FF2E00"},
  "slides": {
    "title":     {"layout": "Титульный слайд", "ph": {"title": 0, "subtitle": 1, "author": 21, "department": 21}},
    "section":   {"layout": "Отбивочный слайд", "ph": {"title": 0, "subtitle": 1}},
    "image":     {"layout": "Стандартный", "ph": {"title": 0}, "body": [83, 100, 564, 240],
                  "image_width": {"small": 30, "medium": 42, "large": 55}, "gap": 15},
    "bar-chart": {"layout": "Стандартный", "ph": {"title": 0}, "body": [83, 100, 564, 240],
                  "text_width": 38, "gap": 12, "heading": "Выводы"},
    "chart":     {"layout": "Стандартный", "ph": {"title": 0}, "body": [83, 100, 564, 240],
                  "text_width": 38, "gap": 12},
    "final":     {"layout": "Заключительный", "ph": {"title": 0, "contact": 1}}
  }
}
```

| ключ | смысл |
|---|---|
| `master` | путь к `.pptx` от корня шаблона |
| `text.size`, `text.bullet`, `text.caption` | кегль тезисов (пт), цвет маркера, цвет подписи к картинке |
| `chart.palette`, `chart.negative` | цвета серий по кругу (первый — рост у гистограммы), цвет падения |
| `slides.<тип>.layout` | имя макета мастера |
| `slides.<тип>.ph` | поле → idx заполнителя макета; у заголовка idx 0 |
| `body` | зона тела `[x, y, w, h]` в мм — у `image`, `bar-chart`, `chart` |
| `image_width` | ширина картинки в % от зоны для `small`/`medium`/`large` |
| `text_width` | ширина колонки тезисов у графиков, % от зоны |
| `gap` | зазор между колонками, мм |
| `heading` | заголовок колонки тезисов у графиков, необязателен |

Все ключи, кроме `heading`, обязательны, неизвестные — ошибка. Каждое поле,
которое не идёт в зону тела, обязано быть в `ph`: у `title` — `title`,
`subtitle`, `author`, `department`; у `section` — `title`, `subtitle`; у
`final` — `title`, `contact`; у остальных — `title`. Несколько полей на одном
idx становятся абзацами в порядке модели. Заполнитель макета, которому нечего
дать, удаляется со слайда; номер слайда переносится, если он есть в макете.
Посмотреть имена макетов и idx заполнителей:

```sh
uv run --project ~/projects/typst-deck python -c "
from pptx import Presentation; import sys
for l in Presentation(sys.argv[1]).slide_layouts:
    print(l.name, [(p.placeholder_format.idx, p.name) for p in l.placeholders])" <мастер.pptx>
```
````

Раздел «Проверка»: «Шесть правил; нарушение любого — ошибка:» → «Семь правил; нарушение любого — ошибка:»; после пункта 6:

```markdown
7. если есть `pptx`: сопоставление читается, макеты с такими именами и
   заполнители с такими idx есть в мастере, зоны лежат внутри слайда, образец
   экспортируется.
```

Абзац про старт дополнить последним предложением:

```markdown
Нарушение правила 7 при старте выключает у шаблона только экспорт в PPTX:
причина видна в `/api/health` (`templates.pptx_off`), PDF работает.
```

- [ ] **Step 7: Прогнать — зелёные, и весь набор**

Run: `uv run pytest tests/test_templates.py tests/test_contract.py tests/test_api.py -q && uv run pytest -q`
Expected: всё зелёное.

- [ ] **Step 8: Коммит**

```bash
git add src/typst_deck/templates.py src/typst_deck/contract.py src/typst_deck/service.py docs/template-contract.md tests/test_templates.py tests/test_contract.py tests/test_api.py
git commit -m "Правило 7 контракта: PowerPoint-мастер; при старте выключает только PPTX

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: скачивание PPTX, `pptx_url` и флаги в API

**Files:**
- Modify: `src/typst_deck/service.py` (импорт, `deck_response`, `list_decks`, `agent_response`, новый `pptx`)
- Modify: `src/typst_deck/api/decks.py` (эндпоинт)
- Modify: `README.md` (раздел API)
- Modify: `tests/conftest.py` (фикстуры `pptx_settings`, `pptx_client`)
- Test: `tests/test_api.py`, `tests/test_agent_api.py`

**Interfaces:**
- Consumes: `TemplateInfo.pptx`, `TemplateRegistry.pptx_off` (задача 4); `export_pptx`, `MappingError` (задача 3).
- Produces: `DeckService.pptx(deck_id) -> tuple[bytes, str]` (байты и название колоды); `GET /api/decks/{id}/deck.pptx`; `pptx_url` (строка или `null`) в ответе колоды и агента; `pptx: bool` у каждой колоды в `GET /api/decks`.

- [ ] **Step 1: Фикстуры** — в `tests/conftest.py` после `tight_client`:

```python
@pytest.fixture
def pptx_settings(tmp_path):
    """Корень шаблонов с одним шаблоном «withpptx», у которого есть PowerPoint-мастер."""
    from typst_deck.config import Settings

    root = tmp_path / "templates"
    make_pptx_template(root, "withpptx")
    return Settings(data_dir=tmp_path / "data", template_dir=TEMPLATE_DIR, templates_dir=str(root),
                    public_base_url="http://t", llm_model="deepseek-chat", check_templates_on_start=False)


@pytest.fixture
async def pptx_client(pptx_settings, fake_llm):
    import httpx

    from typst_deck.app import create_app

    app = create_app(pptx_settings, llm=fake_llm)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        c.app = app
        yield c
```

- [ ] **Step 2: Падающие тесты** — `tests/test_api.py`, в импорты добавить `import io`, `import json`, `from urllib.parse import quote`, `from pptx import Presentation`, `from typst_deck.model import Deck` (тех, что ещё нет); в конец:

```python
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def put_deck(client, template="withpptx"):
    return client.app.state.store.create(Deck(title="Итоги квартала", template=template, slides=[
        {"type": "title", "title": "Итоги"}, {"type": "final"}]))


async def test_pptx_download_changes_nothing(pptx_client):
    deck = put_deck(pptx_client)
    r = await pptx_client.get(f"/api/decks/{deck.id}/deck.pptx")
    assert r.status_code == 200 and r.headers["content-type"] == PPTX_MIME
    assert r.headers["content-disposition"] == "attachment; filename*=utf-8''" + quote("Итоги квартала.pptx")
    assert len(Presentation(io.BytesIO(r.content)).slides) == 2
    d = (await pptx_client.get(f"/api/decks/{deck.id}")).json()
    assert d["version"] == deck.version, "скачивание PPTX не даёт новой версии"
    assert (await pptx_client.get(f"/api/decks/{deck.id}/chat")).json() == []


async def test_pptx_url_and_flags_follow_the_master(pptx_client):
    with_master, without = put_deck(pptx_client), put_deck(pptx_client, template="default")
    d = (await pptx_client.get(f"/api/decks/{with_master.id}")).json()
    assert d["pptx_url"] == f"http://t/api/decks/{with_master.id}/deck.pptx" and d["template"]["pptx"] is True
    assert (await pptx_client.get(f"/api/decks/{without.id}")).json()["pptx_url"] is None
    flags = {x["id"]: x["pptx"] for x in (await pptx_client.get("/api/decks")).json()}
    assert flags == {with_master.id: True, without.id: False}
    tpl = {t["id"]: t["pptx"] for t in (await pptx_client.get("/api/templates")).json()}
    assert tpl == {"default": False, "withpptx": True}
    r = await pptx_client.get(f"/api/decks/{without.id}/deck.pptx")
    assert r.status_code == 422 and "нет PowerPoint-мастера" in r.json()["error"]["message"]


async def test_pptx_off_and_broken_mapping_are_422_with_reason(pptx_client):
    svc = pptx_client.app.state.service
    deck = put_deck(pptx_client)
    svc.templates.pptx_off["withpptx"] = "в мастере нет макета «X»"
    r = await pptx_client.get(f"/api/decks/{deck.id}/deck.pptx")
    assert r.status_code == 422 and "выключен: в мастере нет макета «X»" in r.json()["error"]["message"]
    svc.templates.pptx_off.clear()
    mp = svc.templates.get("withpptx").path / "pptx.json"
    m = json.loads(mp.read_text())
    m["slides"]["final"]["layout"] = "Пропал"
    mp.write_text(json.dumps(m, ensure_ascii=False))
    r = await pptx_client.get(f"/api/decks/{deck.id}/deck.pptx")
    assert r.status_code == 422 and "нет макета «Пропал»" in r.json()["error"]["message"]
    assert (await pptx_client.get("/api/decks/nope/deck.pptx")).status_code == 404


async def test_pptx_export_failure_is_500(pptx_client, monkeypatch):
    import typst_deck.service as service

    def boom(*args, **kwargs):
        raise RuntimeError("битый мастер")

    monkeypatch.setattr(service, "export_pptx", boom)
    r = await pptx_client.get(f"/api/decks/{put_deck(pptx_client).id}/deck.pptx")
    assert r.status_code == 500 and r.json()["error"]["code"] == "render"
    assert "битый мастер" in r.json()["error"]["message"]
```

`tests/test_agent_api.py` — в `test_agent_create_and_revise` после строки с `pdf_url`:

```python
    assert j["pptx_url"] is None  # у шаблона default нет PowerPoint-мастера
```

в конец файла:

```python
async def test_agent_gets_pptx_url_when_the_template_has_a_master(pptx_client):
    from typst_deck.model import Deck

    deck = pptx_client.app.state.store.create(Deck(title="T", template="withpptx", slides=[{"type": "final"}]))
    j = (await pptx_client.get(f"/api/agent/decks/{deck.id}")).json()
    assert j["pptx_url"] == f"http://t/api/decks/{deck.id}/deck.pptx"
```

- [ ] **Step 3: Прогнать — падают**

Run: `uv run pytest tests/test_api.py tests/test_agent_api.py -q -k "pptx or agent_create"`
Expected: FAIL — 404 на `deck.pptx`, нет `pptx_url`, нет `pptx` у колод.

- [ ] **Step 4: Реализация `service.py`**

Импорт после строки `from .model import Deck, utcnow`:

```python
from .pptx import MappingError, export_pptx
```

`deck_response` — перед `try:` добавить `has_pptx = False`, внутри `try` после `template = info.public()`:

```python
            has_pptx = info.pptx is not None
```

в словаре ответа после `pdf_url`:

```python
            # только у шаблона с PowerPoint-мастером; ключ есть всегда, чтобы схема не менялась
            "pptx_url": f"{base}/api/decks/{deck_id}/deck.pptx" if has_pptx else None,
```

`list_decks` целиком:

```python
    def list_decks(self) -> list[dict]:
        out = []
        pptx: dict[str, bool] = {}  # шаблон → есть ли мастер; реестр читает template.json на каждый get
        for d in self.store.list_decks():
            active, last = self.jobs.active_for(d.id), self.jobs.last_for(d.id)
            status = "generating" if active else ("failed" if last and last.status == "failed" else "ready")
            if d.template not in pptx:
                pptx[d.template] = self._has_pptx(d.template)
            out.append({
                "id": d.id, "title": d.title, "slide_count": len(d.slides), "version": d.version,
                "created_at": d.created_at.isoformat(), "updated_at": d.updated_at.isoformat(),
                "status": status,
                "has_build": (self.store.deck_dir(d.id) / "build" / "slide-1.svg").exists(),
                "pptx": pptx[d.template],
            })
        return out

    def _has_pptx(self, tid: str) -> bool:
        try:
            return self.templates.get(tid).pptx is not None
        except TemplateNotFound:
            return False
```

`agent_response` — в словарь после `"pdf_url": r["pdf_url"],`:

```python
            "pptx_url": r["pptx_url"],
```

Новый метод после `pdf`:

```python
    async def pptx(self, deck_id: str) -> tuple[bytes, str]:
        """PPTX на мастере шаблона — на каждый запрос, без кэша (24 слайда — 0,3 с).

        Колода читается снимком, без блокировки: экспорт ничего не пишет —
        ни версии, ни записи в чате, build/ не трогает.
        """
        t0 = time.perf_counter_ns()
        deck = self.load(deck_id)
        t = self.template(deck.template)  # сломанный или пропавший шаблон — 422 с причиной
        if t.pptx is None:
            reason = self.templates.pptx_off.get(t.id)
            if reason:
                raise ApiError(422, "validation", f"экспорт в PPTX у шаблона «{t.id}» выключен: {reason}")
            raise ApiError(422, "validation", f"у шаблона «{t.id}» нет PowerPoint-мастера")
        warnings: list[str] = []
        try:
            data = await asyncio.to_thread(export_pptx, deck, t.path, t.pptx, self.store.deck_dir(deck_id) / "assets",
                                           self.settings.typst_bin, warnings)
        except MappingError as e:
            # канон обновили после старта — причина та же, что дала бы стартовая проверка
            raise ApiError(422, "validation", f"экспорт в PPTX у шаблона «{t.id}»: {e}")
        except Exception as e:
            log.exception("экспорт PPTX упал: колода %s", deck_id)
            raise ApiError(500, "render", f"экспорт в PPTX не удался: {type(e).__name__}: {e}")
        for w in warnings:
            log_event(log, "pptx.warning", deck=deck_id, warning=w, level=logging.WARNING)
        log_event(log, "pptx.done", deck=deck_id, slides=len(deck.slides), kb=len(data) // 1024, ms=_ms(t0))
        return data, deck.title
```

- [ ] **Step 5: Эндпоинт** — `api/decks.py`: в импорты `from urllib.parse import quote`; после маршрута `deck.pdf`:

```python
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


@router.get("/{deck_id}/deck.pptx")
async def pptx(deck_id: str, s: DeckService = Depends(svc)):
    data, title = await s.pptx(deck_id)
    name = f"{title[:60] or 'deck'}.pptx"
    # filename* — имя по-русски; так же его кодирует FileResponse у PDF
    return Response(data, media_type=PPTX_MIME,
                    headers={"Content-Disposition": f"attachment; filename*=utf-8''{quote(name)}"})
```

- [ ] **Step 6: README** — в списке маршрутов веб-интерфейса `…/deck.pdf, …/positions` → `…/deck.pdf, …/deck.pptx, …/positions`; ответ агента:

```
→ {deck_id, status, pdf_url, pptx_url, edit_url, outline: [{n, type, title}], reply}
```

и после абзаца «Бот про слайды не знает…» новый абзац:

```markdown
`pptx_url` — редактируемый PPTX на PowerPoint-мастере шаблона; `null`, если у
шаблона мастера нет (`docs/template-contract.md`, раздел «PowerPoint-мастер»).
Файл собирается на каждый запрос и колоду не меняет.
```

- [ ] **Step 7: Прогнать — зелёные, и весь набор**

Run: `uv run pytest tests/test_api.py tests/test_agent_api.py -q && uv run pytest -q`
Expected: всё зелёное.

- [ ] **Step 8: Коммит**

```bash
git add src/typst_deck/service.py src/typst_deck/api/decks.py README.md tests/conftest.py tests/test_api.py tests/test_agent_api.py
git commit -m "Скачивание PPTX колоды и pptx_url для интерфейса и бота

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: кнопки «Скачать PPTX» в интерфейсе

**Files:**
- Modify: `src/typst_deck/static/deck.html:37`, `src/typst_deck/static/deck.js:105-107`, `src/typst_deck/static/decks.js:36`
- Test: `tests/test_pages.py`

**Interfaces:**
- Consumes: `template.pptx` и `slide_count` в ответе колоды, `pptx` у колоды в списке (задачи 4–5).

- [ ] **Step 1: Падающий тест** — в конец `tests/test_pages.py`:

```python
async def test_pptx_buttons_are_wired(client):
    assert 'id="pptx"' in (await client.get("/d/x")).text
    for name in ("deck.js", "decks.js"):
        assert "deck.pptx" in (await client.get(f"/static/{name}")).text, name
```

- [ ] **Step 2: Прогнать — падает**

Run: `uv run pytest tests/test_pages.py -q`
Expected: FAIL на `id="pptx"`.

- [ ] **Step 3: Реализация**

`deck.html` — перед строкой с `id="pdf"`:

```html
        <a id="pptx" class="btn hidden" href="#" download title="Редактируемая презентация на мастере шаблона">Скачать PPTX</a>
```

`deck.js` — в конец `renderTopbar()` после строк про `pdf`:

```js
  // PPTX собирается из модели на лету и сборки не ждёт; есть только у шаблона с PowerPoint-мастером
  const pptx = $("pptx");
  pptx.href = `api/decks/${deckId}/deck.pptx`;
  pptx.classList.toggle("hidden", !(state.info.template.pptx && state.info.slide_count > 0));
```

`decks.js` — после элемента с `deck.pdf`:

```js
          d.pptx && d.slide_count ? el("a", { class: "btn sm", href: `api/decks/${d.id}/deck.pptx`, download: true }, "PPTX") : null,
```

- [ ] **Step 4: Прогнать — зелёные, и весь набор**

Run: `uv run pytest tests/test_pages.py -q && uv run pytest -q`
Expected: всё зелёное.

- [ ] **Step 5: Проверка глазами** (координатор, навык `run`): поднять `scripts/dev.sh` с `~/corp-templates`; после задачи 7 у колоды на Lemana Tech на странице колоды и в списке видна кнопка PPTX и файл скачивается; у колоды на `default` кнопки нет. До задачи 7 — только что кнопки нет у `default` и страница не сломалась (консоль браузера без ошибок).

- [ ] **Step 6: Коммит**

```bash
git add src/typst_deck/static/deck.html src/typst_deck/static/deck.js src/typst_deck/static/decks.js tests/test_pages.py
git commit -m "Кнопки «Скачать PPTX» на странице колоды и в списке

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: сопоставление Lemana Tech в каноне и корпоративный тест

**Files:**
- Create: `~/projects/lmru--hr-analytics--design-template/typst-deck/pptx.json`
- Modify: `~/projects/lmru--hr-analytics--design-template/template.json`
- Test: `tests/test_corporate.py`

**Interfaces:**
- Consumes: `export_pptx` (задача 3), `TemplateInfo.pptx` (задача 4), правило 7 (задача 4).

- [ ] **Step 1: Падающий тест** — `tests/test_corporate.py`, в импорты `import io`, `from pptx import Presentation`, `from typst_deck.contract import SAMPLE_DECK` (к существующему импорту из `typst_deck.contract`), `from typst_deck.pptx import export_pptx`; в конец:

```python
@pytest.mark.parametrize("t", CORP_PARAMS)
def test_corp_pptx_exports_the_sample_and_declared_limits(t, tmp_path):
    if t.pptx is None:
        pytest.skip(f"{t.id}: нет PowerPoint-мастера")
    declared = Deck(slides=[filled_slide(s, lim) for s, lim in t.slots.items()])
    for deck in (SAMPLE_DECK, declared):
        data = export_pptx(deck, t.path, t.pptx, tmp_path, "typst")
        assert len(Presentation(io.BytesIO(data)).slides) == len(deck.slides)


def test_corp_lemana_tech_has_a_master():
    """Страховка от тихого отката: у канона Lemana Tech мастер обязан быть подключён."""
    lemana = [t for t in (p.values[0] for p in CORP_PARAMS) if t is not None and t.id == "lemana-tech"]
    if not lemana:
        pytest.skip("lemana-tech не подключён в TYPST_DECK_TEST_TEMPLATES")
    assert lemana[0].pptx == "typst-deck/pptx.json"
```

- [ ] **Step 2: Прогнать — падает**

Run: `TYPST_DECK_TEST_TEMPLATES=~/corp-templates uv run pytest tests/test_corporate.py -q`
Expected: `test_corp_lemana_tech_has_a_master` FAIL (`pptx is None`), тест экспорта — SKIP.

- [ ] **Step 3: Сопоставление в каноне** — файл `~/projects/lmru--hr-analytics--design-template/typst-deck/pptx.json`:

```json
{
  "master": "references/lm-tech_template.pptx",
  "text": {"size": 28, "bullet": "FFDE00", "caption": "666666"},
  "chart": {"palette": ["FFDE00", "1E1E1E", "00FFE0", "FF8700"], "negative": "FF2E00"},
  "slides": {
    "title":     {"layout": "Титульный слайд", "ph": {"title": 0, "subtitle": 1, "author": 21, "department": 21}},
    "section":   {"layout": "Отбивочный слайд 2", "ph": {"title": 0, "subtitle": 1}},
    "image":     {"layout": "Стандартный", "ph": {"title": 0}, "body": [83, 100, 564, 240],
                  "image_width": {"small": 30, "medium": 42, "large": 55}, "gap": 15},
    "bar-chart": {"layout": "Стандартный", "ph": {"title": 0}, "body": [83, 100, 564, 240],
                  "text_width": 38, "gap": 12, "heading": "Выводы"},
    "chart":     {"layout": "Стандартный", "ph": {"title": 0}, "body": [83, 100, 564, 240],
                  "text_width": 38, "gap": 12, "heading": "Выводы"},
    "final":     {"layout": "Заключительный", "ph": {"title": 0, "contact": 1}}
  }
}
```

В `~/projects/lmru--hr-analytics--design-template/template.json` после строки `"measure": "typst-deck/measure.json",` добавить строку:

```json
  "pptx": "typst-deck/pptx.json",
```

Остальные поля не трогать.

- [ ] **Step 4: Контракт канона и корпоративные тесты**

Run: `uv run python -m typst_deck.templates ~/projects/lmru--hr-analytics--design-template`
Expected: `lmru--hr-analytics--design-template: контракт соблюдён`.

Run: `TYPST_DECK_TEST_TEMPLATES=~/corp-templates uv run pytest -q`
Expected: всё зелёное, корпоративные тесты не пропущены.

- [ ] **Step 5: Образец для ручной приёмки**

```bash
uv run python - <<'EOF'
from pathlib import Path
from typst_deck.contract import SAMPLE_DECK
from typst_deck.pptx import export_pptx
t = Path.home() / "projects/lmru--hr-analytics--design-template"
out = Path.home() / "lemana-tech-sample.pptx"
out.write_bytes(export_pptx(SAMPLE_DECK, t, "typst-deck/pptx.json", t, "typst"))
print(out)
EOF
```

Файл `~/lemana-tech-sample.pptx` — для ручной приёмки в задаче 8.

- [ ] **Step 6: Коммиты** — канон и продукт отдельно:

```bash
git -C ~/projects/lmru--hr-analytics--design-template add typst-deck/pptx.json template.json
git -C ~/projects/lmru--hr-analytics--design-template commit -m "feat(typst-deck): сопоставление с PowerPoint-мастером для экспорта в PPTX

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git add tests/test_corporate.py
git commit -m "Корпоративный тест экспорта в PPTX

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: выкатка (выполняет координатор, не субагент)

Затрагивает живой сервис; выполнять только после зелёных задач 1–7.

- [ ] **Step 1: Финальные прогоны**

Run: `uv run pytest -q && TYPST_DECK_TEST_TEMPLATES=~/corp-templates uv run pytest -q`
Expected: оба зелёные.

- [ ] **Step 2: Образ с меткой отката**

```bash
podman tag localhost/typst-deck:latest localhost/typst-deck:pre-pptx
podman build -t localhost/typst-deck:latest -t localhost/typst-deck:pptx ~/projects/typst-deck
podman image ls localhost/typst-deck --format "{{.Tag}} {{.Size}}"
```

Expected: сборка прошла (в ней `RUN python -m typst_deck.templates` — встроенные шаблоны без `pptx`, правило 7 молчит); размер нового образа записать в отчёт — спека §12 просила замерить рост.

- [ ] **Step 3: Перезапуск** — канон смонтирован из репозитория только на чтение, его коммит уже виден; перезапуск нужен новому образу и стартовой проверке правила 7.

```bash
systemctl --user restart typst-deck
systemctl --user is-active typst-deck
```

- [ ] **Step 4: Проверка на живом сервисе**

```bash
for i in $(seq 1 40); do c=$(curl -s 127.0.0.1:8088/api/health | python3 -c "import json,sys; print(json.load(sys.stdin)['templates']['checked'])"); [ "$c" = True ] && break; sleep 0.5; done
curl -s 127.0.0.1:8088/api/health | python3 -c "import json,sys; t=json.load(sys.stdin)['templates']; print(t['broken'], t['pptx_off'])"
curl -s 127.0.0.1:8088/api/templates
for id in $(curl -s 127.0.0.1:8088/api/decks | python3 -c "import json,sys; print(' '.join(d['id'] for d in json.load(sys.stdin) if d['pptx']))"); do
  curl -s -o /dev/null -w "$id PPTX %{http_code} %{size_download} B\n" 127.0.0.1:8088/api/decks/$id/deck.pptx
done
```

Expected: `{} {}`; у `lemana-tech` в `/api/templates` `"pptx": true`; каждая колода на Lemana Tech — PPTX 200.

- [ ] **Step 5: Ручная приёмка — делает пользователь.** Открыть в PowerPoint `~/lemana-tech-sample.pptx` и файл, скачанный кнопкой с живой колоды:
  - открывается без предложения восстановить файл;
  - текст стоит в зонах мастера;
  - «Изменить данные» у графиков работает;
  - заметки докладчика на месте.

  Если PowerPoint просит восстановить файл: пересохранить его в PowerPoint и сравнить XML слайдов с нашим (спека §12) — это новая задача, выкатку откатить (шаг 6).

- [ ] **Step 6: Откат (только если шаг 4 или 5 не прошёл)**

```bash
podman tag localhost/typst-deck:pre-pptx localhost/typst-deck:latest
systemctl --user restart typst-deck
```

Канон откатывать не нужно: старый образ поле `pptx` не читает. Колоды экспорт не менял.
