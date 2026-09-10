"""Разовый перенос колод со старого id шаблона на новый.

`python -m typst_deck.migrate_template старый-id новый-id`

Переписывает только поле template в deck.json — без подъёма версии: это
переименование, а не правка. Снимки versions/ не трогаются: откат колоды
копирует из снимка только title и slides. Запускать при остановленном сервисе,
иначе его запись и эта могут разойтись.
"""
from __future__ import annotations

import re
import sys

from .model import TEMPLATE_PATTERN, Deck
from .store import DeckStore, write_atomic


def migrate(store: DeckStore, old: str, new: str) -> list[str]:
    """Колоды на шаблоне old переводит на new; возвращает их id."""
    if not re.fullmatch(TEMPLATE_PATTERN, new):
        raise ValueError(f"некорректный id шаблона «{new}»")
    moved = []
    root = store.data_dir / "decks"
    for p in sorted(root.glob("*/deck.json")) if root.is_dir() else []:
        try:
            deck = Deck.model_validate_json(p.read_text())
        except ValueError:
            continue  # битый deck.json не наш вопрос: list_decks его тоже пропускает
        if deck.template != old:
            continue
        deck.template = new
        write_atomic(p, deck.model_dump_json(indent=2))
        moved.append(deck.id)
    return moved


def main(argv: list[str] | None = None) -> int:
    from .config import get_settings

    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("использование: python -m typst_deck.migrate_template старый-id новый-id", file=sys.stderr)
        return 2
    old, new = argv
    moved = migrate(DeckStore(get_settings().data_dir), old, new)
    print(f"{old} → {new}: колод {len(moved)}" + (f" ({', '.join(moved)})" if moved else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
