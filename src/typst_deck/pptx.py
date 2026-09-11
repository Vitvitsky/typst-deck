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

CAPTION_STRIP = 15   # мм под подпись к картинке
CAPTION_SCALE = 0.7  # кегль подписи от кегля тезисов
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
        if stype == "image" and sm.body is not None and sm.image_width is not None and sm.gap is not None:
            body_w, body_h = sm.body[2], sm.body[3]
            p = max(sm.image_width.values())
            if not (body_w * (100 - p) / 100 - sm.gap > 0):
                problems.append(f"slides.image: при image_width {p:g} % и gap {sm.gap:g} мм "
                                 "колонке тезисов не остаётся места")
            if not (body_h > CAPTION_STRIP):
                problems.append(f"slides.image.body: высота {body_h:g} мм не больше "
                                 f"полосы подписи {CAPTION_STRIP} мм")
        if stype in ("bar-chart", "chart") and sm.body is not None and sm.text_width is not None and sm.gap is not None:
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
        problems += [f"slides.{stype}.ph.{f}: в макете «{sm.layout}» нет заполнителя idx {i}"
                     for f, i in sm.ph.items() if i not in have]
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
    if Path(s.image).name != s.image:  # «/», «..»-путь или абсолютный путь — за пределы assets/
        warnings.append(f"слайд {n}: картинка {s.image} не найдена")
        return None
    src = Path(assets_dir) / s.image
    if not src.is_file():
        warnings.append(f"слайд {n}: картинка {s.image} не найдена")
        return None
    if src.suffix.lower() != ".svg":
        try:
            with Image.open(src) as im:
                fmt = im.format
        except OSError:  # в т.ч. PIL.UnidentifiedImageError — подтип OSError
            fmt = None
        if fmt not in {"PNG", "JPEG", "GIF", "BMP", "TIFF"}:
            warnings.append(f"слайд {n}: картинка {s.image} не читается")
            return None
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
    # картинка — ровно image_width % зоны справа, тезисы слева — остаток за вычетом зазора (спека §5.3)
    x, y, w, h = box
    iw = int(w * sm.image_width[s.image_size] / 100)
    g = int(sm.gap * MM)
    text_box, img_box = (x, y, w - iw - g, h), (x + w - iw, y, iw, h)
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
    """Гистограмма: цвет столбца по знаку — рост palette[0], падение negative.

    number_format не идёт в CategoryChartData: python-pptx пишет его в
    <c:formatCode> текстовым узлом без экранирования (pptx/chart/xmlwriter.py),
    и «&», «<» в unit ломают XML графика. plot.data_labels.number_format —
    атрибут, его пишет lxml и экранирует сам (спека §5.5)."""
    unit = clean(s.unit)
    fmt = _number_format(unit)
    data = CategoryChartData()
    data.categories = [clean(d.label) for d in s.data]
    data.add_series(unit or "Значение", [d.value for d in s.data])
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
