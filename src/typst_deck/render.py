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

from .logs import log_event
from .model import (
    BarChartSlide,
    ChartSlide,
    Deck,
    FinalSlide,
    ImageSlide,
    SectionSlide,
    TitleSlide,
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


def render_typ(deck: Deck, assets: set[str]) -> tuple[str, list[str]]:
    """Возвращает текст deck.typ и предупреждения (например, о пропавших картинках)."""
    out = [HEADER, f"#show: deck.with(title: {typ_str(deck.title)})\n"]
    warnings: list[str] = []
    for n, s in enumerate(deck.slides, 1):
        sid = s.id
        if isinstance(s, TitleSlide):
            out.append(
                f"#slide-title(title: {_text(sid, 'title', s.title)}, "
                f"subtitle: {_text(sid, 'subtitle', s.subtitle)})\n"
            )
        elif isinstance(s, SectionSlide):
            out.append(
                f"#slide-section(title: {_text(sid, 'title', s.title)}, "
                f"subtitle: {_text(sid, 'subtitle', s.subtitle)})\n"
            )
        elif isinstance(s, ImageSlide):
            img = "none"
            if s.image:
                if s.image in assets:
                    img = f'field({typ_str(sid)}, "image", image({typ_str("/assets/" + s.image)}, width: 100%, height: 100%, fit: "contain"))'
                else:
                    warnings.append(f"слайд {n}: картинка {s.image} не найдена")
            out.append(
                f"#slide-image(title: {_text(sid, 'title', s.title)}, "
                f"bullets: {_bullets(sid, s.bullets)}, image: {img}, "
                f"image-size: {typ_str(s.image_size)}, caption: {_text(sid, 'caption', s.caption)})\n"
            )
        elif isinstance(s, BarChartSlide):
            data = typ_value([i.model_dump() for i in s.data])
            out.append(
                f"#slide-bar-chart(title: {_text(sid, 'title', s.title)}, data: {data}, "
                f"unit: {_opt(s.unit)}, bullets: {_bullets(sid, s.bullets)})\n"
            )
        elif isinstance(s, ChartSlide):
            out.append(
                f"#slide-chart(title: {_text(sid, 'title', s.title)}, "
                f"labels: {typ_value(s.labels)}, "
                f"series: {typ_value([x.model_dump() for x in s.series])}, "
                f"unit: {_opt(s.unit)}, bullets: {_bullets(sid, s.bullets)})\n"
            )
        elif isinstance(s, FinalSlide):
            out.append(
                f"#slide-final(title: {_text(sid, 'title', s.title)}, "
                f"contact: {_text(sid, 'contact', s.contact)})\n"
            )
        else:  # pragma: no cover
            raise TypeError(type(s))
    return "".join(out), warnings


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
    timings: dict[str, int] = field(default_factory=dict)  # pdf_ms, svg_ms, query_ms, ms
    pages: list[str] = field(default_factory=list)  # хеш содержимого каждой страницы


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
    deck: Deck, deck_dir: Path, template_dir: Path, typst_bin: str = "typst", timeout: int = 60
) -> CompileResult:
    """Собирает build/: deck.typ, deck.pdf, slide-N.svg, positions.json, warnings.json.

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

    fonts = Path(template_dir) / "fonts"
    font_args = ["--font-path", str(fonts)] if fonts.is_dir() else []
    src = str(tmp / "deck.typ")
    t_all = time.perf_counter_ns()
    timings: dict[str, int] = {}
    for target, key in (("deck.pdf", "pdf_ms"), ("slide-{p}.svg", "svg_ms")):
        r, timings[key] = _run(
            [typst_bin, "compile", "--root", str(tmp), *font_args, src, str(tmp / target)], timeout
        )
        if r.returncode != 0:
            raise CompileError("ошибка компиляции", r.stderr)
    svgs = sorted(tmp.glob("slide-*.svg"), key=lambda p: int(p.stem.split("-")[1]))
    if len(svgs) != len(deck.slides):
        raise CompileError(
            f"страниц {len(svgs)}, слайдов {len(deck.slides)}: "
            "шаблон нарушает контракт «одна функция — одна страница»"
        )
    r, timings["query_ms"] = _run(
        [typst_bin, "eval", "query(<edit>).map(it => it.value)", "--root", str(tmp),
         *font_args, "--in", src, "--format", "json"],
        timeout,
    )
    if r.returncode != 0:
        raise CompileError("ошибка запроса позиций", r.stderr)
    positions = json.loads(r.stdout)
    # Вывод typst детерминирован, поэтому хеш страницы годится как её версия в URL:
    # правка одного слайда меняет ссылку только у него, остальные берутся из кеша.
    pages = [hashlib.blake2b(p.read_bytes(), digest_size=8).hexdigest() for p in svgs]
    (tmp / "positions.json").write_text(json.dumps(positions, ensure_ascii=False))
    (tmp / "warnings.json").write_text(json.dumps(warnings, ensure_ascii=False))
    (tmp / "pages.json").write_text(json.dumps(pages))

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
              pdf_ms=timings["pdf_ms"], svg_ms=timings["svg_ms"], query_ms=timings["query_ms"],
              ms=timings["ms"])
    return CompileResult(
        pdf=build / "deck.pdf",
        svgs=out_svgs,
        positions=positions,
        warnings=warnings,
        typ=typ,
        timings=timings,
        pages=pages,
    )
