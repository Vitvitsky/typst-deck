"""Порождение deck.typ из модели и компиляция через typst."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .logs import log_event
from .model import (
    AgendaSlide, ChartSlide, ColumnsSlide, ComparisonSlide, Deck, DualChartSlide, FinalSlide,
    GallerySlide, ImageSlide, MetricsSlide, QuoteSlide, SectionSlide, TableSlide, TextSlide,
    TitleSlide, VideoSlide,
)

HEADER = '#import "/template/deck.typ": *\n#import "/fields.typ": field\n'
log = logging.getLogger(__name__)

# запасной размер страницы: 16:9 в миллиметрах, как у шаблона по умолчанию
DEFAULT_PAGE = {"w": 453.543307087, "h": 255.118110236}
_VIEWBOX = re.compile(r'viewBox="0 0 ([\d.]+) ([\d.]+)"')


def page_size(svg: Path) -> dict[str, float]:
    """Размер страницы из viewBox. Шаблоны различаются кратно (453×255 против
    1919×1080), поэтому фронту нужен точный размер, чтобы разложить зоны правки."""
    try:
        head = svg.open("rb").read(2048).decode("utf-8", "replace")
    except OSError:
        return dict(DEFAULT_PAGE)
    m = _VIEWBOX.search(head)
    return {"w": float(m[1]), "h": float(m[2])} if m else dict(DEFAULT_PAGE)


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


def overflowing_slide(deck: Deck, positions: list[dict], pages: int | None = None) -> int | None:
    """Номер слайда (с единицы), который не поместился на свою страницу, или None.

    Переполнившийся слайд оставляет свои поля на своей странице, а всё, что
    после него, съезжает на страницу вперёд. Поэтому виновник — последний слайд
    перед первым съехавшим. Если не съехал никто, а страниц больше, чем слайдов,
    вылез последний слайд.
    """
    culprit = None
    for i, s in enumerate(deck.slides, 1):
        slide_pages = [p["page"] for p in positions if p.get("slide") == s.id]
        if not slide_pages:
            continue  # у слайда нет размеченных полей — судить по нему нельзя
        if min(slide_pages) != i:
            return culprit
        culprit = i
    if pages is not None and pages > len(deck.slides):
        return culprit
    return None


def link_url(url: str) -> str:
    """Адрес ссылки для typst: «"», «<», «>» — процентами (RFC 3986: в адресе им
    место только так). typst 0.15 пишет адрес в атрибут SVG без экранирования, и
    кавычка оборвала бы атрибут; ссылка в PDF с %22 ведёт туда же. «&» так не
    кодируется — это изменило бы адрес; его экранирует _fix_svg_links."""
    return url.replace('"', "%22").replace("<", "%3C").replace(">", "%3E")


# голый & в значении href: не начало сущности &amp; &lt; &#38; …
_BARE_AMP = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)")
_HREF = re.compile(r'((?:xlink:)?href=")([^"]*)(")')


def _fix_svg_links(svg: Path) -> None:
    """typst 0.15 не экранирует «&» в адресе ссылки SVG: «watch?v=…&t=260s» делал SVG
    невалидным XML, и браузер не показывал слайд (2026-10-13). Чиним только значения
    href — в остальном SVG typst текста нет (глифы — пути)."""
    text = svg.read_text(encoding="utf-8")
    if "href=" not in text or "&" not in text:
        return
    fixed = _HREF.sub(lambda m: m.group(1) + _BARE_AMP.sub("&amp;", m.group(2)) + m.group(3), text)
    if fixed != text:
        svg.write_text(fixed, encoding="utf-8")


def typ_str(s: str) -> str:
    """Строковый литерал Typst: содержимое не трактуется как разметка."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def typ_value(v) -> str:
    """Скаляры, списки и словари Python → литералы Typst."""
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
    if not value:
        return "none"
    return f"field({typ_str(slide_id)}, {typ_str(name)}, {typ_str(value)})"


def _bullets(slide_id: str, items: list[str]) -> str:
    if not items:
        return "none"
    return f'field({typ_str(slide_id)}, "bullets", list({", ".join(typ_str(i) for i in items)}))'


def _opt(value: str) -> str:
    return typ_str(value) if value else "none"


# Числовая ячейка: число с разделителями и необязательной единицей из букв
# («17,5 %», «1 200», «42 млн»). Дата «2026-09-13» числом не считается:
# единицу от числа отделяет пробел, и цифр с дефисами в ней не бывает.
#
# Якоря \A…\Z, а пробелы разрешены с обеих сторон: с ^…$ разбор был несимметричен —
# «42\n» считалось числом, а «  42» нет, и ячейка со случайным пробелом слева тихо
# отнимала выключку вправо у всей колонки.
NUMBER = re.compile(r"\A\s*[-+−]?\d[\d\s ]*([.,]\d+)?\s*[%‰]?(\s+[^\W\d_]{1,12})?\s*\Z")


def _dict(pairs: dict[str, str]) -> str:
    """Словарь Typst из готовых выражений: (k: expr, …)."""
    return "(" + ", ".join(f"{k}: {v}" for k, v in pairs.items()) + ")"


def _seq(items: list[str]) -> str:
    return "(" + ", ".join(items) + ",)" if items else "()"


def _mark(slide_id: str, name: str, value: str) -> str:
    """Текст составного поля: маркер с именем поля верхнего уровня (спека §6)."""
    return _text(slide_id, name, value)


def numeric_columns(header: list[str], rows: list[list[str]]) -> list[bool]:
    """Колонки, где каждая ячейка читается как число: шаблон и PPTX выравнивают их вправо."""
    return [all(NUMBER.match(row[i] or "") for row in rows) if rows else False
            for i in range(len(header))]


def trend_of(delta: str) -> Literal["up", "down"] | None:
    """Направление изменения метрики по знаку в начале delta — для шаблона и для PPTX."""
    # Тире пишет модель, по-русски: кроме дефиса (U+002D) и минуса (U+2212) там
    # бывают короткое (U+2013) и длинное (U+2014) тире — «–12 %» читается падением
    # и обязано его получить, а не остаться метрикой без цвета.
    d = delta.strip()
    if d.startswith("+"):
        return "up"
    if d.startswith(("-", "−", "–", "—")):
        return "down"
    return None


def _trend(delta: str) -> str:
    t = trend_of(delta)
    return typ_str(t) if t else "none"


def _image_field(slide_id: str, name: str, asset: str) -> str:
    """Картинка в маркере поля: контейнер задаёт шаблон, отсюда width/height 100%."""
    return (f'field({typ_str(slide_id)}, {typ_str(name)}, '
            f'image({typ_str("/assets/" + asset)}, width: 100%, height: 100%, fit: "contain"))')


def render_typ(deck: Deck, assets: set[str]) -> tuple[str, list[str]]:
    """Возвращает текст deck.typ и предупреждения (например, о пропавших картинках)."""
    out = [HEADER, f"#show: deck.with(title: {typ_str(deck.title)})\n"]
    warnings: list[str] = []
    for n, s in enumerate(deck.slides, 1):
        sid = s.id
        if isinstance(s, TitleSlide):
            out.append(
                f"#slide-title(title: {_text(sid, 'title', s.title)}, "
                f"subtitle: {_text(sid, 'subtitle', s.subtitle)}, "
                f"author: {_text(sid, 'author', s.author)}, "
                f"department: {_text(sid, 'department', s.department)})\n"
            )
        elif isinstance(s, AgendaSlide):
            items = _seq([_mark(sid, "items", i) for i in s.items])
            out.append(f"#slide-agenda(title: {_text(sid, 'title', s.title)}, items: {items})\n")
        elif isinstance(s, SectionSlide):
            out.append(
                f"#slide-section(title: {_text(sid, 'title', s.title)}, "
                f"subtitle: {_text(sid, 'subtitle', s.subtitle)})\n"
            )
        elif isinstance(s, TextSlide):
            out.append(f"#slide-text(title: {_text(sid, 'title', s.title)}, "
                       f"bullets: {_bullets(sid, s.bullets)})\n")
        elif isinstance(s, ImageSlide):
            img = "none"
            if s.image:
                if s.image in assets:
                    img = _image_field(sid, "image", s.image)
                else:
                    warnings.append(f"слайд {n}: картинка {s.image} не найдена")
            out.append(
                f"#slide-image(title: {_text(sid, 'title', s.title)}, "
                f"bullets: {_bullets(sid, s.bullets)}, image: {img}, "
                f"image-size: {typ_str(s.image_size)}, caption: {_text(sid, 'caption', s.caption)})\n"
            )
        elif isinstance(s, ColumnsSlide):
            blocks = _seq([_dict({"heading": _mark(sid, "blocks", b.heading),
                                  "text": _mark(sid, "blocks", b.text)}) for b in s.blocks])
            out.append(f"#slide-columns(title: {_text(sid, 'title', s.title)}, blocks: {blocks})\n")
        elif isinstance(s, ComparisonSlide):
            def side(name: str, v):
                bullets_items = _seq([_mark(sid, name, b) for b in v.bullets]) if v.bullets else "none"
                return _dict({"heading": _mark(sid, name, v.heading),
                              "bullets": bullets_items})
            out.append(f"#slide-comparison(title: {_text(sid, 'title', s.title)}, "
                       f"left: {side('left', s.left)}, right: {side('right', s.right)})\n")
        elif isinstance(s, QuoteSlide):
            out.append(f"#slide-quote(text: {_text(sid, 'text', s.text)}, "
                       f"author: {_text(sid, 'author', s.author)})\n")
        elif isinstance(s, ChartSlide):
            out.append(
                f"#slide-chart(title: {_text(sid, 'title', s.title)}, kind: {typ_str(s.kind)}, "
                f"labels: {typ_value(s.labels)}, "
                f"series: {typ_value([x.model_dump() for x in s.series])}, "
                f"unit: {_opt(s.unit)}, bullets: {_bullets(sid, s.bullets)})\n"
            )
        elif isinstance(s, DualChartSlide):
            def chart(name: str, v):
                # Маркер стороны обязан существовать и без подписи. Единственный
                # текст стороны — caption, и при пустой подписи у слайда не было
                # зоны клика ни для одной стороны: починить его можно было только
                # через панель свойств, а будущий образец без подписей завалил бы
                # правило 4, обвинив шаблон. Пустая подпись даёт не пустой маркер,
                # а полосу во всю ширину стороны — по ней и кликают.
                caption = _mark(sid, name, v.caption) if v.caption else (
                    f'field({typ_str(sid)}, {typ_str(name)}, box(width: 100%, height: 8pt))')
                return _dict({"caption": caption, "kind": typ_str(v.kind),
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
                       f"rows: {rows}, numeric: {typ_value(numeric_columns(s.header, s.rows))})\n")
        elif isinstance(s, GallerySlide):
            pics = []
            for pic in s.images:
                if pic.image not in assets:
                    warnings.append(f"слайд {n}: картинка {pic.image} не найдена")
                    continue
                pics.append(_dict({
                    "image": _image_field(sid, "images", pic.image),
                    "caption": _mark(sid, "images", pic.caption)}))
            if not pics:
                # Пропали все картинки — поле images осталось бы вовсе без маркера,
                # и зона неклика­бельна: слайд чинится только через панель свойств.
                # Высоту кадра задаёт шаблон своим боксом, здесь она нужна лишь
                # затем, чтобы у зоны был ненулевой размер.
                pics.append(_dict({
                    "image": f'field({typ_str(sid)}, "images", box(width: 100%, height: 2cm))',
                    "caption": "none"}))
            out.append(f"#slide-gallery(title: {_text(sid, 'title', s.title)}, images: {_seq(pics)})\n")
        elif isinstance(s, VideoSlide):
            poster = "none"
            if s.poster:
                if s.poster in assets:
                    poster = _image_field(sid, "poster", s.poster)
                else:
                    warnings.append(f"слайд {n}: обложка {s.poster} не найдена")
            out.append(f"#slide-video(title: {_text(sid, 'title', s.title)}, poster: {poster}, "
                       f"url: {_opt(link_url(s.url))}, caption: {_text(sid, 'caption', s.caption)})\n")
        elif isinstance(s, FinalSlide):
            out.append(
                f"#slide-final(title: {_text(sid, 'title', s.title)}, "
                f"contact: {_text(sid, 'contact', s.contact)})\n"
            )
        else:  # pragma: no cover
            raise TypeError(type(s))
    return "".join(out), warnings


FIELDS_TYP = Path(__file__).parent / "typst" / "fields.typ"
# Версия того, как колода превращается в deck.typ (render_typ). Входит в метку
# сборки (build/stamp.txt): поднять при правке render_typ, меняющей вывод, — и
# устаревшие сборки колод пересоберутся сами при первом обращении. fields.typ
# в метку входит своим хешем, его правка версии не требует.
RENDER_VERSION = 1
FIELDS_HASH = hashlib.blake2b(FIELDS_TYP.read_bytes(), digest_size=8).hexdigest()


class CompileError(Exception):
    def __init__(self, message: str, stderr: str = ""):
        super().__init__(message)
        self.stderr = stderr


@dataclass
class CompileResult:
    pdf: Path  # путь, по которому его соберёт compile_pdf(); сразу после сборки файла нет
    svgs: list[Path]
    positions: list[dict]
    warnings: list[str] = field(default_factory=list)
    typ: str = ""
    timings: dict[str, int] = field(default_factory=dict)  # svg_ms, query_ms, ms
    pages: list[str] = field(default_factory=list)  # хеш содержимого каждой страницы
    # предупреждения typst при сборке SVG (например, «unknown font family»): сборка при них проходит
    stderr: str = ""


def _run(cmd: list[str], timeout: int) -> tuple[subprocess.CompletedProcess, int]:
    """Запуск typst; возвращает результат и потраченные миллисекунды."""
    t0 = time.perf_counter_ns()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as e:
        raise CompileError(f"typst не найден: {cmd[0]}") from e
    except subprocess.TimeoutExpired as e:
        raise CompileError(f"typst не уложился в {timeout} с") from e
    return r, (time.perf_counter_ns() - t0) // 1_000_000


def compile_deck(
    deck: Deck, deck_dir: Path, template_dir: Path, typst_bin: str = "typst", timeout: int = 60,
    fonts_dir: Path | None = None, system_fonts: bool = True, stamp: str = "",
) -> CompileResult:
    """Собирает build/: deck.typ, slide-N.svg, positions.json, warnings.json, pages.json
    и stamp.txt — метку, чем собрано (DeckService.build_stamp), если она передана.

    PDF не собирается — его делает compile_pdf() по требованию.

    Сборка идёт в build.tmp/ и подменяет build/ целиком, чтобы превью
    не читало полуготовые файлы.
    """
    assets_dir = deck_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    assets = {p.name for p in assets_dir.iterdir() if p.is_file()}
    typ, warnings = render_typ(deck, assets)

    tmp = deck_dir / "build.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    os.symlink(Path(template_dir).resolve(), tmp / "template")
    os.symlink(assets_dir.resolve(), tmp / "assets")
    shutil.copy(FIELDS_TYP, tmp / "fields.typ")
    (tmp / "deck.typ").write_text(typ)

    # каталог шрифтов — из template.json шаблона (TemplateInfo.fonts); без него прежнее место
    fonts = Path(fonts_dir) if fonts_dir is not None else Path(template_dir) / "fonts"
    font_args = ["--font-path", str(fonts)] if fonts.is_dir() else []
    if not system_fonts:
        # проверка контракта: чем шаблон набирает текст, когда системных шрифтов нет
        font_args.append("--ignore-system-fonts")
    src = str(tmp / "deck.typ")
    t_all = time.perf_counter_ns()
    timings: dict[str, int] = {}
    # PDF здесь не собирается: он нужен раз в конце работы, а стоил 161 мс из 341
    # на каждой правке. Его делает compile_pdf() по запросу — см. api/decks.py.
    r, timings["svg_ms"] = _run(
        [typst_bin, "compile", "--root", str(tmp), *font_args, src, str(tmp / "slide-{p}.svg")], timeout
    )
    if r.returncode != 0:
        raise CompileError("ошибка компиляции", r.stderr)
    svg_stderr = r.stderr
    svgs = sorted(tmp.glob("slide-*.svg"), key=lambda p: int(p.stem.split("-")[1]))
    for p in svgs:
        _fix_svg_links(p)
    # Позиции запрашиваются до проверки контракта: по ним видно, какой именно
    # слайд вылез за свою страницу, а без этого сообщение винит шаблон вслепую.
    r, timings["query_ms"] = _run(
        [typst_bin, "eval", "query(<edit>).map(it => it.value)", "--root", str(tmp),
         *font_args, "--in", src, "--format", "json"],
        timeout,
    )
    positions = json.loads(r.stdout) if r.returncode == 0 else []
    if len(svgs) != len(deck.slides):
        n = overflowing_slide(deck, positions, pages=len(svgs))
        if n:
            title = getattr(deck.slides[n - 1], "title", "") or ""
            where = f"слайд {n}" + (f" «{title}»" if title else "")
            raise CompileError(
                f"{where} не помещается на страницу: содержимого больше, чем вмещает шаблон. "
                "Сократите текст на этом слайде."
            )
        raise CompileError(
            f"страниц {len(svgs)}, слайдов {len(deck.slides)}: "
            "шаблон нарушает контракт «одна функция — одна страница»"
        )
    if r.returncode != 0:
        raise CompileError("ошибка запроса позиций", r.stderr)
    # Вывод typst детерминирован, поэтому хеш страницы годится как её версия в URL:
    # правка одного слайда меняет ссылку только у него, остальные берутся из кеша.
    pages = [hashlib.blake2b(p.read_bytes(), digest_size=8).hexdigest() for p in svgs]
    (tmp / "positions.json").write_text(json.dumps(positions, ensure_ascii=False))
    (tmp / "warnings.json").write_text(json.dumps(warnings, ensure_ascii=False))
    (tmp / "pages.json").write_text(json.dumps(pages))
    if stamp:
        (tmp / "stamp.txt").write_text(stamp)

    build = deck_dir / "build"
    old = deck_dir / "build.old"
    shutil.rmtree(old, ignore_errors=True)
    if build.exists():
        os.rename(build, old)
    os.rename(tmp, build)
    shutil.rmtree(old, ignore_errors=True)
    out_svgs = [build / p.name for p in svgs]
    timings["ms"] = (time.perf_counter_ns() - t_all) // 1_000_000
    svg_kb = sum(p.stat().st_size for p in out_svgs) // 1024
    log_event(log, "render.done", deck=deck.id, slides=len(out_svgs), svg_kb=svg_kb,
              svg_ms=timings["svg_ms"], query_ms=timings["query_ms"], ms=timings["ms"])
    return CompileResult(
        pdf=build / "deck.pdf",
        svgs=out_svgs,
        positions=positions,
        warnings=warnings,
        typ=typ,
        timings=timings,
        pages=pages,
        stderr=svg_stderr,
    )


def compile_pdf(build_dir: Path, typst_bin: str = "typst", timeout: int = 60,
                fonts_dir: Path | None = None) -> Path:
    """PDF из уже готового build/: deck.typ, шаблон и ассеты там уже лежат.

    Собирается по запросу и остаётся в build/, поэтому повторное скачивание
    бесплатно, а любая правка колоды заменяет build/ целиком и снимает его сама.
    """
    src = build_dir / "deck.typ"
    if not src.exists():
        raise CompileError("нет сборки колоды: нечего превращать в PDF")
    fonts = Path(fonts_dir) if fonts_dir is not None else build_dir / "template" / "fonts"
    font_args = ["--font-path", str(fonts)] if fonts.is_dir() else []
    out = build_dir / "deck.pdf"
    r, ms = _run(
        [typst_bin, "compile", "--root", str(build_dir), *font_args, str(src), str(out)], timeout
    )
    if r.returncode != 0:
        raise CompileError("ошибка сборки PDF", r.stderr)
    log_event(log, "pdf.done", kb=out.stat().st_size // 1024, ms=ms)
    return out


RASTER_TYP = '#set page(width: auto, height: auto, margin: 0pt)\n#image("image.svg")\n'
# вписать в рамку w×h pt с сохранением пропорций: и огромный width, и значок 16×16
# растеризуются под место на слайде, а не в собственном размере
RASTER_FIT_TYP = """#set page(width: auto, height: auto, margin: 0pt)
#context {{
  let s = measure(image("image.svg"))
  let k = calc.min({w}pt / s.width, {h}pt / s.height)
  image("image.svg", width: s.width * k)
}}
"""


def rasterize_svg(svg: Path, out: Path, typst_bin: str = "typst", ppi: int = 200, timeout: int = 60,
                  box_pt: tuple[float, float] | None = None) -> Path:
    """SVG → PNG средствами typst: python-pptx SVG не вставляет, а колода их принимает.

    typst уже есть в образе, так что растеризатор не тянет новых зависимостей.
    Рабочий каталог — рядом с out: песочница typst видит только его.
    box_pt — рамка на слайде: картинка вписывается в неё, иначе — собственный размер SVG.
    """
    work = out.parent / f"{out.stem}.raster"
    work.mkdir(parents=True, exist_ok=True)
    shutil.copy(svg, work / "image.svg")
    typ = RASTER_TYP if box_pt is None else RASTER_FIT_TYP.format(w=f"{box_pt[0]:.2f}", h=f"{box_pt[1]:.2f}")
    (work / "raster.typ").write_text(typ)
    r, _ = _run([typst_bin, "compile", "--root", str(work), "--format", "png", "--ppi", str(ppi),
                 str(work / "raster.typ"), str(out)], timeout)
    if r.returncode != 0:
        raise CompileError("SVG не растеризуется", r.stderr)
    return out
