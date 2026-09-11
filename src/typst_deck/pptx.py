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
