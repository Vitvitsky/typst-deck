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
import copy
import io
import json
import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from pptx import Presentation

from .model import CELL_MAX, SIDE_CAPTION_MAX, Deck
from .pptx import MappingError, export_pptx, load_mapping
from .render import CompileError, CompileResult, compile_deck, resolve_fonts
from .slots import clamp, field_kind

# Образец: по слайду каждого типа в порядке SLIDE_TYPES. Им же рисуются превью
# шаблонов в интерфейсе, поэтому картинки и ролик кладутся рядом (write_sample_assets).
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
SAMPLE_ASSETS = {"sample-1.png": PNG_1PX, "sample-2.png": PNG_1PX, "sample-3.png": PNG_1PX,
                 "sample.mp4": b"\x00\x00\x00\x18ftypmp42"}
# только картинки образца, без ролика: gallery.images подставляет их по кругу,
# а взять sample.mp4 в качестве картинки нельзя (инцидент — при count 3 и выше
# list(SAMPLE_ASSETS) утыкался в ролик, идущий в словаре последним)
SAMPLE_IMAGES = tuple(name for name in SAMPLE_ASSETS if name != "sample.mp4")

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


def _skeleton(stype: str, sample: str) -> dict:
    """Слайд типа stype на коротких значениях по умолчанию — до наложения объявления.

    Обязательные поля получают минимум, при котором слайд собирается; тяжёлые
    необязательные (текст блока, тезис колонки, ячейка) — глобальный предел
    model.py: именно он и действует, пока шаблон ничего не сузил.
    """
    slide: dict = {"type": stype}
    # agenda и final несут собственный короткий title по умолчанию, а у quote его вовсе нет
    if stype not in ("agenda", "quote", "final"):
        slide["title"] = "Итоги"
    if stype == "agenda":
        slide["items"] = [_text(sample, 80)] * 3
    elif stype == "text":
        slide["bullets"] = [_text(sample, 80)] * 3
    elif stype == "image":
        slide["image"] = "sample-1.png"
    elif stype == "columns":
        slide["blocks"] = [{"heading": _text(sample, 40), "text": _text(sample, 300)}] * 3
    elif stype == "comparison":
        side = {"heading": _text(sample, 60), "bullets": [_text(sample, 120)] * 3}
        slide["left"], slide["right"] = dict(side), dict(side)
    elif stype == "quote":
        slide["text"] = _text(sample, 300)
    elif stype == "chart":
        slide["kind"] = "line"
        slide["labels"] = ["Q1", "Q2"]
        slide["series"] = [{"name": "Ряд 1", "values": [0, 1]}]
    elif stype == "dual-chart":
        # длина — из константы модели, а не литералом: подпись стороны уже́ общего
        # Short (80), и зашитое число разъезжается с пределом при первой же правке
        side = {"caption": _text(sample, SIDE_CAPTION_MAX), "labels": ["Q1", "Q2"],
                "series": [{"name": "Ряд 1", "values": [0, 1]}]}
        slide["left"], slide["right"] = dict(side), dict(side)
    elif stype == "metrics":
        slide["items"] = [{"value": "12,5 млн", "label": _text(sample, 60), "delta": "+12 %"}] * 3
    elif stype == "table":
        slide["header"] = [_text(sample, 40)] * 3
        slide["rows"] = [[_text(sample, CELL_MAX)] * 3] * 3
    elif stype == "gallery":
        slide["images"] = [{"image": SAMPLE_IMAGES[0], "caption": _text(sample, 80)}] * 2
    elif stype == "video":
        slide["video"], slide["poster"] = "sample.mp4", "sample-1.png"
    return slide


def _fill(kind: str | None, current: object, lim: dict[str, int], sample: str):
    """Значение поля ровно по его объявленным пределам.

    Форму берём у схемы (field_kind), а не у имени поля: «items» — строки у
    повестки и объекты у метрик, и угадывание по имени однажды уже превращало
    пункты повестки в строку.
    """
    if kind == "strings":
        n = lim.get("count", len(current) if isinstance(current, list) and current else 3)
        item = (_text(sample, lim["max"]) if "max" in lim
                else current[0] if isinstance(current, list) and current else _text(sample, 40))
        return [item] * n
    if kind == "list":  # список объектов или строк-ячеек: длину элементов задаёт не max, а его поля
        items = current if isinstance(current, list) and current else [{}]
        return [copy.deepcopy(items[0]) for _ in range(lim.get("count", len(items)))]
    return _text(sample, lim.get("max", 40), lim.get("lines", 1))


def _consistent(slide: dict, stype: str, sample: str) -> None:
    """Поля, которые обязаны сойтись между собой после наложения пределов."""
    if stype == "chart":
        slide["series"] = [{"name": f"Ряд {j + 1}", "values": list(range(len(slide["labels"])))}
                           for j in range(len(slide["series"]))]
    if stype == "dual-chart":
        for name in ("left", "right"):
            side = slide[name]
            side["series"] = [{"name": f"Ряд {j + 1}", "values": list(range(len(side["labels"])))}
                              for j in range(len(side["series"]))]
    if stype == "table":
        width = len(slide["header"])
        cell = slide["rows"][0][0] if slide["rows"] and slide["rows"][0] else _text(sample, CELL_MAX)
        slide["rows"] = [[cell] * width for _ in slide["rows"]]
    if stype == "gallery":
        # Картинок образца три, а gallery допускает четыре: пускаем по кругу, иначе
        # при count=4 собиралось три и самый тугой случай шаблона не проверялся.
        slide["images"] = [dict(p, image=SAMPLE_IMAGES[i % len(SAMPLE_IMAGES)])
                           for i, p in enumerate(slide["images"])]


def filled_slide(stype: str, limits: dict[str, dict[str, int]], sample: str = FILL) -> dict:
    """Слайд типа stype, где каждое объявленное поле заполнено ровно по его пределам.
    Обязательные поля без объявления получают короткие значения.

    Ключ с точкой («blocks.text», «left.bullets») — тот же путь во вложенное поле,
    что понимают clamp и check_slide: он кладётся в подполе, а не в поле с точкой
    в имени, которое модель с extra="forbid" не приняла бы вовсе. И объём берётся
    объявленный: шаблон, честно сузивший blocks.text до 180, проверяется на 180,
    а не на глобальные 300, которых он не обещал.
    """
    slide = _skeleton(stype, sample)
    # Сначала поля верхнего уровня, потом вложенные: число блоков задаёт «blocks»,
    # а «blocks.text» обязан лечь в каждый из них.
    for path in sorted(limits, key=lambda p: "." in p):
        head, _, tail = path.partition(".")
        lim = limits[path]
        if not tail:
            slide[head] = _fill(field_kind(stype, head), slide.get(head), lim, sample)
            continue
        kind, target = field_kind(stype, path), slide.get(head)
        if isinstance(target, list):  # массив объектов: подполе у каждого элемента
            slide[head] = [dict(x) | {tail: _fill(kind, x.get(tail), lim, sample)}
                           for x in target if isinstance(x, dict)]
        elif isinstance(target, dict):
            slide[head] = dict(target) | {tail: _fill(kind, target.get(tail), lim, sample)}
    _consistent(slide, stype, sample)
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
    # heading (Block, Metric.label) ограничены моделью 60 знаками, ячейка таблицы —
    # CELL_MAX: переросший текст даём им по максимуму допустимого, а не общий big,
    # иначе Deck() не соберётся
    deck = Deck(slides=[
        {"type": "title", "title": big, "subtitle": breaks, "author": big, "department": big},
        {"type": "section", "title": big, "subtitle": breaks},
        {"type": "quote", "text": big + breaks, "author": big},
        {"type": "columns", "title": big, "blocks": [{"heading": big[:60], "text": big + breaks}] * 2},
        {"type": "metrics", "title": big, "items": [{"value": big[:16], "label": big[:60], "delta": big[:12]}] * 2},
        {"type": "table", "title": big, "header": [big[:40], big[:40]],
         "rows": [[big[:CELL_MAX], big[:CELL_MAX]]] * 2},
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
