"""Проверка шаблона на контракт typst-deck (docs/template-contract.md).

Два режима. Полный — для автора шаблона и CI: семь правил, строго.
Стартовый — для работающего сервиса: сломанным считается только шаблон, который
не может работать; шрифты и ключи slots там — предупреждения, а не поломка,
иначе одна опечатка в корпоративной вёрстке остановила бы все колоды на ней.

Правило 7 (PowerPoint-мастер) при старте тоже мягкое: нарушение выключает
экспорт в PPTX у шаблона, а PDF продолжает работать.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from pptx import Presentation

from .model import Deck
from .pptx import MappingError, export_pptx, load_mapping
from .render import CompileError, CompileResult, compile_deck, resolve_fonts
from .slots import clamp

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


STRING_LISTS = ("bullets", "labels")
FONT_WARNING = re.compile(r"unknown font family: ([^\n]+)")
OVERSIZED = "Очень длинный текст, который заведомо не помещается в отведённое место " * 6
FILL = "Итоги квартала по направлению данных и аналитики "


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # правило 7 отдельно: при старте по нему выключается экспорт в PPTX, а не шаблон
    pptx: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class _Collect(logging.Handler):
    """Предупреждения clamp своего потока: clamp зовут и параллельные запросы."""

    def __init__(self):
        super().__init__(logging.WARNING)
        self.thread = threading.get_ident()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.thread == self.thread:
            self.messages.append(record.getMessage())


def _clamp_collect(raw: object, tid: str) -> tuple[dict, list[str]]:
    handler = _Collect()
    lg = logging.getLogger("typst_deck.slots")
    lg.addHandler(handler)
    try:
        declared = clamp(raw, tid)
    finally:
        lg.removeHandler(handler)
    return declared, handler.messages


def _text(sample: str, n: int, lines: int = 1) -> str:
    """Ровно n знаков из sample; при lines > 1 — с lines-1 явными переводами строки внутри."""
    body = (sample * (n // max(len(sample), 1) + 2))[: max(n - (lines - 1), 1)]
    if lines <= 1:
        return body
    step = max(len(body) // lines, 1)
    parts = [body[i * step:(i + 1) * step] for i in range(lines - 1)] + [body[(lines - 1) * step:]]
    return "\n".join(parts)


def filled_slide(stype: str, limits: dict[str, dict[str, int]], sample: str = FILL) -> dict:
    """Слайд типа stype, где каждое объявленное поле заполнено ровно по его пределам.
    Обязательные поля без объявления получают короткие значения."""
    slide: dict = {"type": stype}
    for fld, lim in limits.items():
        if fld in STRING_LISTS:
            slide[fld] = [_text(sample, lim.get("max", 40))] * lim.get("count", 3)
        elif fld == "data":
            slide["data"] = [{"label": f"Пункт {i + 1}", "value": i + 1} for i in range(lim.get("count", 3))]
        elif fld != "series":  # ряды собираются ниже, под число подписей
            slide[fld] = _text(sample, lim.get("max", 40), lim.get("lines", 1))
    # agenda и final уже несут собственный короткий title по умолчанию, а у quote поля title вовсе нет
    if stype not in ("agenda", "quote", "final"):
        slide.setdefault("title", "Итоги")
    if stype == "chart":
        slide.setdefault("labels", ["Q1", "Q2"])
        k = limits.get("series", {}).get("count", 1)
        slide["series"] = [{"name": f"Ряд {j + 1}", "values": list(range(len(slide["labels"])))}
                           for j in range(k)]
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
    return slide


def _read_meta(path: Path, report: Report) -> dict | None:
    """Правило 1, файлы: deck.typ и читаемый template.json с name."""
    if not (path / "deck.typ").is_file():
        report.errors.append("нет deck.typ в корне шаблона")
    mp = path / "template.json"
    if not mp.is_file():
        report.errors.append("нет template.json в корне шаблона")
        return None
    try:
        meta = json.loads(mp.read_text())
    except ValueError as e:
        report.errors.append(f"template.json не читается: {e}")
        return None
    if not isinstance(meta, dict) or not meta.get("name"):
        report.errors.append("в template.json нет поля name")
        return None
    return meta


def _rule_fonts_used(path: Path, typst_bin: str, work_dir: Path, fonts: Path | None) -> list[str]:
    """Правило 6: шрифты из каталога шаблона реально используются.

    Образец собирается без системных шрифтов дважды — с каталогом и без него.
    Одинаковый вывод значит, что семейства, которые называет шаблон, не совпадают
    с файлами. Ровно так канон Lemana Tech просил «…Pro Trl», которого в его же
    архиве нет, и молча получал чужой шрифт.
    """
    if fonts is None:
        return []
    empty = work_dir / "no-fonts"
    empty.mkdir(parents=True, exist_ok=True)
    write_sample_assets(work_dir / "fonts-with")
    write_sample_assets(work_dir / "fonts-without")
    try:
        a = compile_deck(SAMPLE_DECK, work_dir / "fonts-with", path, typst_bin, fonts_dir=fonts, system_fonts=False)
        b = compile_deck(SAMPLE_DECK, work_dir / "fonts-without", path, typst_bin, fonts_dir=empty, system_fonts=False)
    except CompileError as e:
        return [f"образец без системных шрифтов не собирается: {e}"]
    if a.pages == b.pages:
        return [f"шрифты из {fonts.relative_to(path)}/ не используются: "
                "семейства, которые называет шаблон, не совпадают с файлами"]
    return []


def _rule_oversized(path: Path, typst_bin: str, work_dir: Path, fonts: Path | None) -> list[str]:
    """Правило 3: переросший вход не выносит слайд на вторую страницу."""
    big = OVERSIZED[:120]
    breaks = big[:60] + "\n" * 8 + big[:40]  # переводы строки — механизм инцидента 2026-09-09
    # heading (Block, Metric.label) ограничены моделью 60 знаками — переросший текст
    # даём им по максимуму допустимого, а не общий big, иначе Deck() не соберётся
    deck = Deck(slides=[
        {"type": "title", "title": big, "subtitle": breaks, "author": big, "department": big},
        {"type": "section", "title": big, "subtitle": breaks},
        {"type": "quote", "text": big + breaks, "author": big},
        {"type": "columns", "title": big, "blocks": [{"heading": big[:60], "text": big + breaks}] * 2},
        {"type": "metrics", "title": big, "items": [{"value": big[:16], "label": big[:60], "delta": big[:12]}] * 2},
        {"type": "table", "title": big, "header": [big[:40], big[:40]], "rows": [[big[:60], big[:60]]] * 2},
        {"type": "final", "title": big, "contact": breaks},
    ])
    try:
        compile_deck(deck, work_dir / "oversized", path, typst_bin, fonts_dir=fonts)
    except CompileError as e:
        return [f"переросший текст ломает страницу: {e}"]
    return []


def _rule_markers(sample: CompileResult) -> list[str]:
    """Правило 4: у каждого непустого текстового поля образца есть маркер <edit>."""
    have = {(p.get("slide"), p.get("field")) for p in sample.positions}
    missing = []
    for n, s in enumerate(SAMPLE_DECK.slides, 1):
        for fld in TEXT_FIELDS:
            if not getattr(s, fld, None):
                continue
            if fld == "caption" and s.type == "image" and not s.image:
                continue  # подпись — к картинке; без картинки шаблон вправе её не рисовать
            if (s.id, fld) not in have:
                missing.append(f"слайд {n} ({s.type}): поле {fld} не размечено — "
                               "шаблон не выводит его или выводит без маркера")
    return missing


def _rule_declared_fit(path: Path, typst_bin: str, work_dir: Path, fonts: Path | None,
                       declared: dict) -> list[str]:
    """Правило 5: слайды, заполненные ровно по объявленным пределам, — по одной странице."""
    if not declared:
        return []
    write_sample_assets(work_dir / "declared")  # filled_slide тоже ссылается на картинки образца
    try:
        deck = Deck(slides=[filled_slide(t, lim) for t, lim in declared.items()])
        compile_deck(deck, work_dir / "declared", path, typst_bin, fonts_dir=fonts)
    except CompileError as e:
        return [f"текст по объявленным пределам slots не помещается: {e}"]
    except ValueError as e:
        return [f"по пределам slots нельзя собрать слайд: {e}"]
    return []


def _rule_pptx(path: Path, meta: dict, typst_bin: str, work_dir: Path) -> list[str]:
    """Правило 7: сопоставление читается, мастер с ним сходится, образец экспортируется.

    Экспортируются только слайды тех типов, которые называет само сопоставление:
    PowerPoint-мастер пока обещает не все пятнадцать типов слайда (см. SLIDE_TYPES
    в src/typst_deck/pptx.py), и рано валить шаблон за типы, которых сопоставление
    и не брало на себя.
    """
    if "pptx" not in meta:
        return []
    try:
        m = load_mapping(path, meta["pptx"])
    except MappingError as e:
        return [f"pptx: {e}"]
    sample = SAMPLE_DECK.model_copy(update={"slides": [s for s in SAMPLE_DECK.slides if s.type in m.slides]})
    try:
        data = export_pptx(sample, path, meta["pptx"], work_dir / "no-assets", typst_bin)
        n = len(Presentation(io.BytesIO(data)).slides)
    except MappingError as e:
        return [f"pptx: {e}"]
    except Exception as e:  # сбой python-pptx на мастере или на повторном открытии — нарушение, а не падение проверки
        return [f"pptx: образец не экспортируется: {type(e).__name__}: {e}"]
    if n != len(sample.slides):
        return [f"pptx: в файле {n} слайдов при {len(sample.slides)} в образце"]
    return []


def check_template(path: Path, typst_bin: str, work_dir: Path, full: bool = True) -> Report:
    """Правила контракта для каталога шаблона; full=False — стартовый режим сервиса."""
    path, work_dir = Path(path), Path(work_dir)
    report = Report()
    strict = report.errors if full else report.warnings
    meta = _read_meta(path, report)
    if meta is None or report.errors:
        return report
    declared, notes = _clamp_collect(meta.get("slots"), path.name)
    strict.extend(f"slots: {m}" for m in notes)
    report.pptx = _rule_pptx(path, meta, typst_bin, work_dir)
    strict.extend(report.pptx)
    try:
        fonts = resolve_fonts(path, meta.get("fonts", "fonts"))
    except ValueError as e:
        # реестр на этот же случай не падает, а откатывается на fonts/ (templates.py
        # _info) — сервис продолжает отдавать шаблон. В стартовом режиме сообщение
        # уходит в предупреждения, и проверка идёт тем же откатом, а не обрывается.
        strict.append(str(e))
        if full:
            return report
        fonts = resolve_fonts(path)
    write_sample_assets(work_dir / "sample")
    try:  # правило 2: образец собирается, одна функция — одна страница
        sample = compile_deck(SAMPLE_DECK, work_dir / "sample", path, typst_bin, fonts_dir=fonts)
    except CompileError as e:
        report.errors.append(f"образец не собирается: {e} {e.stderr.strip()}".strip())
        return report
    report.warnings.extend(f"typst не нашёл семейство шрифта «{f}»"
                           for f in sorted(set(FONT_WARNING.findall(sample.stderr))))
    strict.extend(_rule_fonts_used(path, typst_bin, work_dir, fonts))
    if full:
        report.errors.extend(_rule_oversized(path, typst_bin, work_dir, fonts))
        report.errors.extend(_rule_markers(sample))
        report.errors.extend(_rule_declared_fit(path, typst_bin, work_dir, fonts, declared))
    return report
