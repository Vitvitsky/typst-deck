"""Экспорт колоды в редактируемый PPTX на PowerPoint-мастере шаблона.

Спека: docs/superpowers/specs/2026-09-11-pptx-export-design.md. Сопоставление
(pptx.json в шаблоне, путь — поле pptx в template.json) говорит, на какой макет
мастера ложится каждый тип слайда, в какой заполнитель — каждое поле и где зона
тела. Продукт ничего корпоративного не знает: мастер, макеты и цвета приходят
из шаблона. Контракт (правило 7) и сам экспорт проверяют сопоставление одними
и теми же load_mapping и open_master.
"""
from __future__ import annotations

import copy
import io
import json
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Callable, Literal

from lxml import etree
from PIL import Image, ImageDraw
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.shapes import PP_PLACEHOLDER
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn
from pptx.util import Emu, Mm, Pt
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import charts
from .model import SLIDE_TYPES, Deck
from .render import CompileError, inside_template, numeric_columns, rasterize_svg, trend_of

MM = 36000  # EMU в миллиметре
EMU_PER_PT = 12700
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
# Наибольшее число колонок в зоне у типов, которые делят её поровну (пределы model.py):
# сопоставление обязано оставить каждой колонке место, иначе размеры уходят в минус
# и PowerPoint предлагает восстановить файл.
ACROSS = {"columns": BLOCKS, "comparison": 2, "dual-chart": 2, "metrics": 4, "gallery": 3}

CAPTION_STRIP = 15   # мм под подпись к картинке
CAPTION_SCALE = 0.7  # кегль подписи от кегля тезисов
ROW_MAX = 15        # мм — предел высоты строки таблицы: короткая таблица не тянется на всю зону
GRID = {2: (1, 2), 3: (1, 3), 4: (2, 2)}  # картинок галереи → (строк, колонок)
POSTER = (1600, 900)  # заглушка обложки видео, 16:9
RULE_W = 6350       # EMU — 0.5 пт, тонкая линия таблицы
# Управляющие символы, которых не бывает в тексте слайда; \t и \n остаются.
# python-pptx на них не падает, а пишет в текст видимый мусор вида _x001F_.
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f]")

Hex = Annotated[str, Field(pattern=r"^[0-9A-Fa-f]{6}$")]
Percent = Annotated[float, Field(ge=1, le=90)]


class MappingError(ValueError):
    """Сопоставление или мастер шаблона не годятся; текст — для человека."""


class _Strict(BaseModel):
    # опечатка в ключе не должна тихо выключать настройку
    model_config = ConfigDict(extra="forbid")


class TextStyle(_Strict):
    size: float = Field(gt=0)    # кегль тезисов, пт
    bullet: Hex                  # цвет маркера тезисов и номеров повестки
    caption: Hex                 # цвет подписей: картинки, автора цитаты, метрики
    quote: float = Field(gt=0)   # кегль цитаты, пт
    metric: float = Field(gt=0)  # кегль крупного числа метрики, пт


class ChartStyle(_Strict):
    palette: list[Hex] = Field(min_length=1)  # серии по кругу; первый — рост у гистограммы
    negative: Hex                             # столбцы с отрицательным значением


class TrendStyle(_Strict):
    up: Hex    # изменение метрики со знаком «+»
    down: Hex  # изменение со знаком «-» или тире


class TableStyle(_Strict):
    size: float = Field(gt=0)  # кегль ячеек, пт
    header_fill: Hex           # заливка шапки
    stripe_fill: Hex           # заливка чётных строк («зебра»)
    rule: Hex                  # цвет тонких линий


class SlideMap(_Strict):
    layout: str                                   # имя макета мастера (<p:cSld name>)
    # поле → idx заполнителя; у заголовка 0. Список — только у columns.blocks
    ph: dict[str, int | list[int]]
    body: tuple[float, float, float, float] | None = None  # зона тела x, y, w, h в мм
    image_width: dict[Literal["small", "medium", "large"], Percent] | None = None
    text_width: Percent | None = None
    gap: float | None = Field(default=None, ge=0)  # зазор между колонками, мм
    heading: str | None = None                     # заголовок колонки тезисов у графиков


SlideType = Literal["title", "agenda", "section", "text", "image", "columns", "comparison",
                    "quote", "chart", "dual-chart", "metrics", "table", "gallery", "video", "final"]
assert set(SlideType.__args__) == set(SLIDE_TYPES), "pptx.SlideType разошёлся с model.SLIDE_TYPES"


class Mapping(_Strict):
    master: str
    # шрифт всего текста в PPTX; None — шрифты мастера как есть (см. _set_font)
    font: str | None = Field(default=None, min_length=1)
    text: TextStyle
    chart: ChartStyle
    trend: TrendStyle
    table: TableStyle
    slides: dict[SlideType, SlideMap]


def ph_fields(stype: str) -> tuple[str, ...]:
    return PH_FIELDS.get(stype, ("title",))


def _body_keys(stype: str, sm: SlideMap) -> tuple[str, ...]:
    if stype == "columns" and "blocks" in sm.ph:
        return ()  # блоки в заполнителях мастера — зона и зазор не нужны
    return BODY_KEYS.get(stype, ())


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
                    continue
                taken = {i for k, i in sm.ph.items() if k != "blocks" and isinstance(i, int)}
                for i in sorted(set(v)):
                    if v.count(i) > 1:
                        problems.append(f"slides.{stype}.ph.blocks: idx {i} повторяется")
                    if i in taken:
                        # блок занял бы заполнитель заголовка, и заголовок слайда пропал бы молча
                        problems.append(f"slides.{stype}.ph.blocks: idx {i} занят другим полем")
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
        if sm.image_width is not None and len(sm.image_width) != 3:
            problems.append(f"slides.{stype}.image_width: нужны small, medium и large")
        if stype == "image" and sm.body is not None and sm.image_width is not None and sm.gap is not None:
            body_w, body_h = sm.body[2], sm.body[3]
            p = max(sm.image_width.values())
            if not (body_w * (100 - p) / 100 - sm.gap > 0):
                problems.append(f"slides.image: при image_width {p:g} % и gap {sm.gap:g} мм "
                                 "колонке тезисов не остаётся места")
            if not (body_h > CAPTION_STRIP):
                problems.append(f"slides.image.body: высота {body_h:g} мм не больше "
                                 f"полосы подписи {CAPTION_STRIP} мм")
        if stype in ACROSS and sm.body is not None and sm.gap is not None:
            n = ACROSS[stype]
            if not ((sm.body[2] - sm.gap * (n - 1)) / n > 0):
                problems.append(f"slides.{stype}: при gap {sm.gap:g} мм на колонку не остаётся места "
                                f"(колонок до {n}, ширина зоны {sm.body[2]:g} мм)")
        if stype == "gallery" and sm.body is not None and sm.gap is not None:
            if not ((sm.body[3] - sm.gap) / 2 > CAPTION_STRIP):
                problems.append(f"slides.gallery.body: высота {sm.body[3]:g} мм мала для двух рядов с подписями")
        if stype in ("video", "dual-chart") and sm.body is not None and not (sm.body[3] > CAPTION_STRIP):
            problems.append(f"slides.{stype}.body: высота {sm.body[3]:g} мм не больше "
                            f"полосы подписи {CAPTION_STRIP} мм")
        if stype == "chart" and sm.body is not None and sm.text_width is not None and sm.gap is not None:
            body_w = sm.body[2]
            if not (body_w * (100 - sm.text_width) / 100 - sm.gap > 0):
                problems.append(f"slides.{stype}: при text_width {sm.text_width:g} % и gap {sm.gap:g} мм "
                                 "графику не остаётся места")
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


# add_slide не копирует эти заполнители макета (кроме номера слайда — его
# переносит _slide_number отдельно): поле, сопоставленное на их idx,
# провалилось бы молча, поэтому open_master их из «have» не считает.
_NOT_COPIED = {PP_PLACEHOLDER.DATE, PP_PLACEHOLDER.FOOTER, PP_PLACEHOLDER.SLIDE_NUMBER}


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
        have = {ph.placeholder_format.idx for ph in layout.placeholders
                if ph.placeholder_format.type not in _NOT_COPIED}
        for f, i in sm.ph.items():
            for idx in (i if isinstance(i, list) else [i]):
                if idx not in have:
                    problems.append(f"slides.{stype}.ph.{f}: в макете «{sm.layout}» нет заполнителя idx {idx}")
        if sm.body is not None:
            x, y, bw, bh = sm.body
            if bw <= 0 or bh <= 0 or x < 0 or y < 0 or x + bw > w + 0.5 or y + bh > h + 0.5:
                problems.append(f"slides.{stype}.body: зона {list(sm.body)} выходит за слайд {w:.0f}×{h:.0f} мм")
    if problems:
        raise MappingError("; ".join(problems))
    return prs


def clean(text: str) -> str:
    return CONTROL.sub("", text)


def _drop_slides(prs) -> None:
    """Слайды-образцы мастера не нужны: сначала ссылка из списка, потом связь.
    Недостижимые части python-pptx при сохранении не пишет."""
    ids = prs.slides._sldIdLst
    for sld in list(ids):
        ids.remove(sld)
        prs.part.drop_rel(sld.rId)


def _retype(root, font: str) -> None:
    """Явные латинские гарнитуры (a:latin) — на font. Ссылки на шрифт темы
    (+mj-lt, +mn-lt) остаются ссылками, слоты ea/cs/sym не трогаются: кириллицу
    и латиницу PowerPoint набирает из a:latin."""
    for latin in root.iter(qn("a:latin")):
        if not latin.get("typeface", "").startswith("+"):
            latin.set("typeface", font)


def _retype_part(part, font: str) -> None:
    """Мастера и макеты python-pptx разбирает в XML, а темы и мастер раздаточных
    материалов держит байтами — те правятся как XML и кладутся обратно."""
    if hasattr(part, "_element"):
        _retype(part._element, font)
        return
    root = etree.fromstring(part.blob)
    _retype(root, font)
    part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _set_font(prs, font: str) -> None:
    """Шрифт шаблона для всего текста: мастера слайдов с макетами, мастер заметок и
    мастер раздаточных материалов — и тема каждого (заголовки, основной текст,
    умолчания новых фигур). Отсутствующие мастера не создаются. Зовётся после
    сборки слайдов: мастер заметок python-pptx заводит на первой заметке."""
    parts = []
    for master in prs.slide_masters:
        parts += [master.part, *(layout.part for layout in master.slide_layouts)]
    for reltype in (RT.NOTES_MASTER, RT.HANDOUT_MASTER):
        try:
            parts.append(prs.part.part_related_by(reltype))
        except KeyError:
            pass
    themes = []
    for part in parts:
        try:
            theme = part.part_related_by(RT.THEME)
        except KeyError:  # у макетов своей темы нет
            continue
        if theme not in themes:
            themes.append(theme)
    for part in parts + themes:
        _retype_part(part, font)


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
    # правило ориентации столбцов шаблона (charts.columns в template.json) или None
    rule: dict | None = None


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


def _paragraph(tf, k: int, text: str, size: float, *, bold: bool = False, color: str | None = None,
               align=None, keep_newlines: bool = True):
    """k-й абзац надписи: первый уже есть, остальные добавляются."""
    p = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
    text = clean(text)
    p.text = text.replace("\n", "\v") if keep_newlines else text.replace("\n", " ")
    if align is not None:
        p.alignment = align
    for r in p.runs:
        r.font.size = Pt(size)
        if bold:
            r.font.bold = True
        if color:
            r.font.color.rgb = RGBColor.from_string(color.upper())
    return p


def _textbox(slide, box):
    x, y, w, h = box
    tf = slide.shapes.add_textbox(Emu(x), Emu(y), Emu(w), Emu(h)).text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    return tf


def _bullets(slide, box, items: list[str], style: TextStyle, heading: str | None = None,
             numbered: bool = False) -> None:
    """Тезисы надписью в зоне: маркер (или номер) цвета style.bullet, шрифт — из темы мастера.
    Порядок в a:pPr — по схеме: spcBef, buClr, затем buAutoNum или buChar."""
    tf = _textbox(slide, box)
    paras = ([(heading, False)] if heading else []) + [(i, True) for i in items]
    indent = Mm(10 if numbered else 8)
    for k, (text, bullet) in enumerate(paras):
        p = _paragraph(tf, k, text, style.size, bold=not bullet)
        if k:
            p.space_before = Pt(style.size * 0.5)
        if bullet:
            ppr = p._p.get_or_add_pPr()
            ppr.set("marL", str(indent))
            ppr.set("indent", str(-indent))
            clr = etree.SubElement(ppr, qn("a:buClr"))
            etree.SubElement(clr, qn("a:srgbClr"), val=style.bullet.upper())
            if numbered:
                etree.SubElement(ppr, qn("a:buAutoNum"), type="arabicPeriod")
            else:
                etree.SubElement(ppr, qn("a:buChar"), char="•")


def _split(box, n: int, gap_mm: float) -> list[tuple[int, int, int, int]]:
    """n равных колонок зоны с зазором gap_mm между ними."""
    x, y, w, h = box
    g = int(gap_mm * MM)
    cw = (w - g * (n - 1)) // n
    return [(x + i * (cw + g), y, cw, h) for i in range(n)]


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


def _caption(slide, text: str, x: int, y: int, w: int, style: TextStyle, italic: bool = True) -> None:
    tf = slide.shapes.add_textbox(Emu(x), Emu(y), Emu(w), Emu(int((CAPTION_STRIP - 2) * MM))).text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = clean(text).replace("\n", " ")
    for r in p.runs:
        r.font.size = Pt(style.size * CAPTION_SCALE)
        r.font.italic = italic
        r.font.color.rgb = RGBColor.from_string(style.caption.upper())


def _image_file(name: str, assets_dir: Path, tmp: Path, typst_bin: str,
                warnings: list[str], n: int, box: tuple[int, int] | None = None) -> Path | None:
    """Файл картинки; SVG — растром, вписанным в рамку box (w, h в EMU). Пропавшая или
    нерастеризуемая — None и предупреждение, как у PDF: слайд собирается без неё."""
    if not name:
        return None
    if Path(name).name != name:  # «/», «..»-путь или абсолютный путь — за пределы assets/
        warnings.append(f"слайд {n}: картинка {name} не найдена")
        return None
    src = Path(assets_dir) / name
    if not src.is_file():
        warnings.append(f"слайд {n}: картинка {name} не найдена")
        return None
    if src.suffix.lower() != ".svg":
        try:
            with Image.open(src) as im:
                fmt = im.format
        except OSError:  # в т.ч. PIL.UnidentifiedImageError — подтип OSError
            fmt = None
        if fmt not in {"PNG", "JPEG", "GIF", "BMP", "TIFF"}:
            warnings.append(f"слайд {n}: картинка {name} не читается")
            return None
        return src
    try:
        box_pt = None if box is None else (box[0] / EMU_PER_PT, box[1] / EMU_PER_PT)
        return rasterize_svg(src, tmp / f"{src.stem}.png", typst_bin, box_pt=box_pt)
    except CompileError as e:
        warnings.append(f"слайд {n}: SVG {name} не растеризуется: {e}")
        return None


def _image_body(c: Ctx) -> set[int]:
    slide, s, sm, style = c.slide, c.s, c.sm, c.m.text
    box = _mm_box(sm.body)
    # картинка — ровно image_width % зоны справа, тезисы слева — остаток за вычетом зазора (спека §5.3)
    x, y, w, h = box
    iw = int(w * sm.image_width[s.image_size] / 100)
    g = int(sm.gap * MM)
    text_box, img_box = (x, y, w - iw - g, h), (x + w - iw, y, iw, h)
    strip = int(CAPTION_STRIP * MM) if s.caption else 0
    img = _image_file(s.image, c.assets, c.tmp, c.typst_bin, c.warnings, c.n, (iw, h - strip))
    if img is None:
        if s.bullets:
            _bullets(slide, box, s.bullets, style)
        return set()
    if s.bullets:
        _bullets(slide, text_box, s.bullets, style)
    x, y, w, h = img_box
    bottom = _picture(slide, img, (x, y, w, h - strip))
    if s.caption:
        _caption(slide, s.caption, x, bottom + int(2 * MM), w, style)
    return set()


def _number_format(unit: str) -> str:
    unit = unit.replace('"', "").strip()
    return f'General" {unit}"' if unit else "General"


def _chart_data(src) -> CategoryChartData:
    data = CategoryChartData()
    data.categories = [clean(lb) for lb in src.labels]
    for ser in src.series:
        data.add_series(clean(ser.name), ser.values)
    return data


def _bar_chart(slide, src, box, cs: ChartStyle, horizontal: bool = False) -> None:
    """Гистограмма. Одна серия — цвет столбца по знаку (рост palette[0], падение negative),
    подписи значений с единицей; несколько — серии по палитре и легенда сверху.

    number_format не идёт в CategoryChartData: python-pptx пишет его в
    <c:formatCode> текстовым узлом без экранирования (pptx/chart/xmlwriter.py),
    и «&», «<» в unit ломают XML графика. plot.data_labels.number_format —
    атрибут, его пишет lxml и экранирует сам (спека §5.5).

    horizontal — линейчатая диаграмма (подписи категорий строками слева), как решило
    правило шаблона (charts.py) — то же, что у PDF. Категории сверху вниз в порядке
    колоды: у линейчатой PowerPoint по умолчанию кладёт первую категорию вниз."""
    x, y, w, h = box
    kind = XL_CHART_TYPE.BAR_CLUSTERED if horizontal else XL_CHART_TYPE.COLUMN_CLUSTERED
    chart = slide.shapes.add_chart(kind, Emu(x), Emu(y), Emu(w), Emu(h), _chart_data(src)).chart
    if horizontal:
        chart.category_axis.reverse_order = True
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
    if src.unit:  # подписей значений нет — единица уходит в подпись оси, как у линии
        chart.value_axis.has_title = True
        chart.value_axis.axis_title.text_frame.text = clean(src.unit)
    for i, series in enumerate(plot.series):
        series.invert_if_negative = False
        series.format.fill.solid()
        series.format.fill.fore_color.rgb = RGBColor.from_string(cs.palette[i % len(cs.palette)].upper())


def _line_chart(slide, src, box, cs: ChartStyle) -> None:
    """Линейный график: серии по палитре по кругу, легенда сверху, единица — подпись оси."""
    x, y, w, h = box
    chart = slide.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Emu(x), Emu(y), Emu(w), Emu(h),
                                   _chart_data(src)).chart
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.TOP
    chart.legend.include_in_layout = False
    chart.value_axis.has_major_gridlines = False
    if src.unit:
        chart.value_axis.has_title = True
        chart.value_axis.axis_title.text_frame.text = clean(src.unit)
    for i, series in enumerate(chart.plots[0].series):
        color = RGBColor.from_string(cs.palette[i % len(cs.palette)].upper())
        series.smooth = False
        series.format.line.color.rgb = color
        series.format.line.width = Pt(3)
        series.marker.format.fill.solid()
        series.marker.format.fill.fore_color.rgb = color
        series.marker.format.line.color.rgb = color


def _draw_chart(slide, src, box, cs: ChartStyle, layout: str = "full", rule: dict | None = None) -> None:
    """src — ChartSlide или сторона dual-chart: у обоих kind, labels, series, unit.
    layout — раскладка для правила ориентации столбцов: full, bullets, dual."""
    if src.kind == "bar":
        _bar_chart(slide, src, box, cs, horizontal=charts.horizontal(src.labels, layout, rule))
    else:
        _line_chart(slide, src, box, cs)


def _chart_body(c: Ctx) -> set[int]:
    box = _mm_box(c.sm.body)
    if not c.s.bullets:
        _draw_chart(c.slide, c.s, box, c.m.chart, "full", c.rule)
        return set()
    text_box, chart_box = _columns(box, c.sm.text_width, c.sm.gap)
    _bullets(c.slide, text_box, c.s.bullets, c.m.text, heading=c.sm.heading)
    _draw_chart(c.slide, c.s, chart_box, c.m.chart, "bullets", c.rule)
    return set()


def _dual_chart_body(c: Ctx) -> set[int]:
    """Два графика рядом; над каждым — подпись стороны полосой CAPTION_STRIP, если она есть."""
    for side, (x, y, w, h) in zip((c.s.left, c.s.right), _split(_mm_box(c.sm.body), 2, c.sm.gap)):
        if clean(side.caption).strip():
            strip = int(CAPTION_STRIP * MM)
            _caption(c.slide, side.caption, x, y, w, c.m.text, italic=False)
            y, h = y + strip, h - strip
        _draw_chart(c.slide, side, (x, y, w, h), c.m.chart, "dual", c.rule)
    return set()


def _agenda_body(c: Ctx) -> set[int]:
    _bullets(c.slide, _mm_box(c.sm.body), c.s.items, c.m.text, numbered=True)
    return set()


def _text_body(c: Ctx) -> set[int]:
    _bullets(c.slide, _mm_box(c.sm.body), c.s.bullets, c.m.text)
    return set()


def _block_text(tf, block, style: TextStyle) -> None:
    """Блок columns: жирный заголовок (если есть), затем текст."""
    k = 0
    if clean(block.heading).strip():
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
        _bullets(c.slide, box, side.bullets, c.m.text, heading=clean(side.heading).strip() or None)
    return set()


def _quote_body(c: Ctx) -> set[int]:
    tf = _textbox(c.slide, _mm_box(c.sm.body))
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    _paragraph(tf, 0, c.s.text, c.m.text.quote, align=PP_ALIGN.CENTER)
    if clean(c.s.author).strip():
        p = _paragraph(tf, 1, c.s.author, c.m.text.size, color=c.m.text.caption, align=PP_ALIGN.CENTER)
        p.space_before = Pt(c.m.text.size)
    return set()


def _metrics_body(c: Ctx) -> set[int]:
    """Равные колонки: крупное число, подпись цветом подписи, изменение цветом тренда."""
    st = c.m.text
    colors = {"up": c.m.trend.up, "down": c.m.trend.down}
    for item, box in zip(c.s.items, _split(_mm_box(c.sm.body), len(c.s.items), c.sm.gap)):
        tf = _textbox(c.slide, box)
        _paragraph(tf, 0, item.value, st.metric, bold=True, align=PP_ALIGN.CENTER, keep_newlines=False)
        k = 1
        for text, color in ((item.label, st.caption),
                            (item.delta, colors.get(trend_of(item.delta), st.caption))):
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
    tbl.first_row = False     # стиль таблицы по умолчанию не красит шапку и полосы —
    tbl.horz_banding = False  # это делает сопоставление
    numeric = numeric_columns(c.s.header, c.s.rows)
    for r, row in enumerate([c.s.header, *c.s.rows]):
        tbl.rows[r].height = Emu(rh)
        for col, text in enumerate(row):
            cell = tbl.cell(r, col)
            _cell_rules(cell, st.rule)
            fill = st.header_fill if r == 0 else (st.stripe_fill if r % 2 == 0 else None)
            if fill:
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor.from_string(fill.upper())
            else:
                cell.fill.background()
            align = PP_ALIGN.RIGHT if r and numeric[col] else None
            _paragraph(cell.text_frame, 0, text, st.size, bold=(r == 0), align=align)
    return set()


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
    # полоса подписи — у всех клеток или ни у одной: иначе картинки одного ряда разной высоты
    strip = int(CAPTION_STRIP * MM) if any(clean(p.caption).strip() for p in c.s.images) else 0
    for pic, (cx, cy, cw, chh) in zip(c.s.images, cells):
        img = _image_file(pic.image, c.assets, c.tmp, c.typst_bin, c.warnings, c.n, (cw, chh - strip))
        if img is None:
            continue  # клетка остаётся пустой, сетка не сдвигается
        bottom = _picture(c.slide, img, (cx, cy, cw, chh - strip))
        if clean(pic.caption).strip():
            _caption(c.slide, pic.caption, cx, bottom + int(2 * MM), cw, c.m.text)
    return set()


def _placeholder_poster(m: Mapping, tmp: Path) -> Path:
    """Заглушка обложки — как кадр видео в PDF: светлый фон table.stripe_fill, круг
    цвета text.bullet, «▶» тёмный или белый — что контрастнее к кругу. Прежде «▶»
    цвета text.bullet лежал прямо на table.header_fill: у Lemana оба FFDE00, и в
    PowerPoint был сплошной жёлтый прямоугольник (2026-10-13)."""
    w, h = POSTER
    im = Image.new("RGB", POSTER, _rgb(m.table.stripe_fill))
    d = ImageDraw.Draw(im)
    circle = _rgb(m.text.bullet)
    R = h // 6
    d.ellipse([w / 2 - R, h / 2 - R, w / 2 + R, h / 2 + R], fill=circle)
    luma = 0.2126 * circle[0] + 0.7152 * circle[1] + 0.0722 * circle[2]
    mark = (0x1E, 0x1E, 0x1E) if luma > 140 else (0xFF, 0xFF, 0xFF)
    r = R * 0.45
    d.polygon([(w / 2 - r * 0.8, h / 2 - r), (w / 2 - r * 0.8, h / 2 + r), (w / 2 + r, h / 2)], fill=mark)
    path = tmp / "poster-placeholder.png"
    im.save(path)
    return path


def _video_body(c: Ctx) -> set[int]:
    """Обложка (или заглушка) с гиперссылкой на ролик и подпись под ней (ADR 0022)."""
    x, y, w, h = _mm_box(c.sm.body)
    strip = int(CAPTION_STRIP * MM) if clean(c.s.caption).strip() else 0
    poster = (_image_file(c.s.poster, c.assets, c.tmp, c.typst_bin, c.warnings, c.n, (w, h - strip))
              or _placeholder_poster(c.m, c.tmp))
    with Image.open(poster) as im:
        aspect = im.width / im.height
    fx, fy, fw, fh = _fit((x, y, w, h - strip), aspect)
    pic = c.slide.shapes.add_picture(str(poster), Emu(fx), Emu(fy), Emu(fw), Emu(fh))
    pic.click_action.hyperlink.address = c.s.url
    if strip:
        _caption(c.slide, c.s.caption, fx, fy + fh + int(2 * MM), fw, c.m.text)
    return set()


BODIES: dict[str, Callable[[Ctx], set[int]]] = {
    "agenda": _agenda_body, "text": _text_body, "image": _image_body, "columns": _columns_body,
    "comparison": _comparison_body, "quote": _quote_body, "chart": _chart_body,
    "dual-chart": _dual_chart_body, "metrics": _metrics_body, "table": _table_body,
    "gallery": _gallery_body, "video": _video_body,
}


def export_pptx(deck: Deck, template_dir: Path, mapping_rel: object, assets_dir: Path,
                typst_bin: str = "typst", warnings: list[str] | None = None) -> bytes:
    """Колода → байты .pptx на мастере шаблона.

    Сопоставление читается на каждый вызов: канон могли обновить после старта,
    и ошибка должна прийти MappingError с причиной, а не 500. Пропавшие картинки
    и нерастеризуемые SVG — в warnings, слайд собирается без них.
    """
    warnings = [] if warnings is None else warnings
    m = load_mapping(template_dir, mapping_rel)
    try:
        rule = charts.load_rule(template_dir)
    except ValueError as e:  # сломанное правило — столбцы вертикально, как без него
        warnings.append(f"template.json: {e}")
        rule = None
    prs = open_master(template_dir, m)
    layouts = _layouts(prs)
    _drop_slides(prs)
    with tempfile.TemporaryDirectory() as tmp:
        for n, s in enumerate(deck.slides, 1):
            sm = m.slides[s.type]
            layout = layouts[sm.layout]
            slide = prs.slides.add_slide(layout)
            body = BODIES.get(s.type)
            keep = body(Ctx(slide, s, sm, m, Path(assets_dir), Path(tmp), typst_bin, warnings, n, rule)) if body else set()
            _fill(slide, s, sm, keep)
            _slide_number(slide, layout, n)
            if s.notes.strip():
                slide.notes_slide.notes_text_frame.text = clean(s.notes)
        if m.font:
            _set_font(prs, m.font)
        buf = io.BytesIO()
        prs.save(buf)
    return buf.getvalue()
