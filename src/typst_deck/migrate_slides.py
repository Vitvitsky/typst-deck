"""Разовый перенос сохранённых колод на набор типов из спеки 2026-09-13.

`python -m typst_deck.migrate_slides [--check]`

Переписывает deck.json и все снимки versions/ в decks/ и в trash/: id слайдов
сохраняются, версия не поднимается — это смена формата, а не правка. Повторный
запуск ничего не меняет. Запускать при остановленном сервисе.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from .model import Deck
from .store import write_atomic


def upgrade_slide(raw: dict) -> dict:
    """Старый слайд → новый. Слайд нового формата возвращается как есть."""
    kind = raw.get("type")
    if kind == "image" and not raw.get("image") and not raw.get("bullets"):
        # ни картинки, ни тезисов — остался один заголовок: это разделитель, а не
        # текстовый слайд (TextSlide требует хотя бы один тезис, и колода не прошла
        # бы проверку переноса). Убирать слайд нельзя — сдвинулась бы нумерация.
        return {"id": raw["id"], "type": "section", "title": raw.get("title", ""),
                "notes": raw.get("notes", "")}
    if kind == "image" and not raw.get("image"):
        # картинки нет — это текстовый слайд; подпись к картинке без картинки не рисовалась
        return {
            "id": raw["id"],
            "type": "text",
            "title": raw.get("title", ""),
            "bullets": raw.get("bullets", []),
            "notes": raw.get("notes", ""),
        }
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
        except (OSError, ValueError, KeyError, AttributeError, TypeError) as e:
            # upgrade_slide умеет бросить KeyError (raw["id"], d["label"]),
            # AttributeError (слайд не словарь) и TypeError (колода не объект).
            # Перенос запускают один раз при остановленном сервисе: оператору нужна
            # сводка, какие колоды переписаны, а не трассировка на первой битой.
            print(f"{d.name}: пропущена, {type(e).__name__}: {e}", file=sys.stderr)
            continue
        if not planned:
            continue
        if not check:
            for p, text in planned:
                write_atomic(p, text)
            # Сборка переписанной колоды устарела: её deck.typ вызывает функции
            # старого контракта, а deck.pdf и превью — старый вид. После выкатки
            # 2026-10-13 PDF такой колоды отвечал 500. Сервис соберёт её заново
            # при первом обращении (DeckService.ensure_build).
            shutil.rmtree(d / "build", ignore_errors=True)
        # Extract deck ID (before dash for trash items, full name for decks)
        deck_id = d.name.split('-')[0]
        done.append((deck_id, len(planned)))
    if not check:
        # Спека §5: кэш превью шаблонов очищается. Шаблон, чьи файлы при выкатке
        # меняются, спасала бы отметка по mtime (service.py), но примонтированный
        # канон остаётся прежним файл в файл — и отдавал бы превью на шесть страниц
        # там, где интерфейс ждёт пятнадцать.
        shutil.rmtree(Path(data_dir) / "template-previews", ignore_errors=True)
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
